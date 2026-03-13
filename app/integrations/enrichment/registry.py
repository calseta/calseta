"""
EnrichmentRegistry — singleton registry for all enrichment providers.

Providers are loaded from the database at startup via load_from_database().
Route handlers and services access the registry via `enrichment_registry`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.integrations.enrichment.base import EnrichmentProviderBase
from app.schemas.indicators import IndicatorType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class EnrichmentRegistry:
    """
    Singleton registry mapping provider_name → EnrichmentProviderBase instance.

    Thread-safe for reads (no writes after startup). Providers are loaded
    from the database once at process start; no dynamic registration at runtime.
    """

    def __init__(self) -> None:
        self._providers: dict[str, EnrichmentProviderBase] = {}

    def register(self, provider: EnrichmentProviderBase) -> None:
        """
        Register an enrichment provider.

        Raises:
            ValueError: If a provider with the same provider_name is already registered.
        """
        if provider.provider_name in self._providers:
            raise ValueError(
                f"Enrichment provider '{provider.provider_name}' is already registered. "
                "Each provider_name must be unique."
            )
        self._providers[provider.provider_name] = provider
        logger.debug(
            "enrichment_provider_registered",
            provider_name=provider.provider_name,
            configured=provider.is_configured(),
        )

    def clear(self) -> None:
        """Remove all registered providers. Used before reloading from DB."""
        self._providers.clear()

    async def load_from_database(self, db: AsyncSession) -> None:
        """Load all active providers from the database and register them.

        Clears existing registrations first, then creates DatabaseDrivenProvider
        instances from each active enrichment_providers row.
        """
        from sqlalchemy import select

        from app.db.models.enrichment_field_extraction import EnrichmentFieldExtraction
        from app.db.models.enrichment_provider import EnrichmentProvider
        from app.integrations.enrichment.database_provider import DatabaseDrivenProvider

        self.clear()

        # Load all active providers
        result = await db.execute(
            select(EnrichmentProvider).where(EnrichmentProvider.is_active.is_(True))
        )
        providers = list(result.scalars().all())

        if not providers:
            logger.info("enrichment_registry_no_providers")
            return

        # Load all active field extractions in one query
        ext_result = await db.execute(
            select(EnrichmentFieldExtraction).where(
                EnrichmentFieldExtraction.is_active.is_(True)
            )
        )
        all_extractions = list(ext_result.scalars().all())

        # Group extractions by (provider_name, indicator_type)
        extraction_map: dict[str, list[dict[str, object]]] = {}
        for ext in all_extractions:
            key = ext.provider_name
            if key not in extraction_map:
                extraction_map[key] = []
            extraction_map[key].append({
                "source_path": ext.source_path,
                "target_key": ext.target_key,
                "value_type": ext.value_type,
                "is_active": ext.is_active,
            })

        for row in providers:
            field_extractions = extraction_map.get(row.provider_name, [])
            try:
                provider = DatabaseDrivenProvider.from_db_row(row, field_extractions)
                self.register(provider)
            except Exception:
                logger.exception(
                    "enrichment_provider_load_failed",
                    provider_name=row.provider_name,
                )

        logger.info(
            "enrichment_registry_loaded",
            provider_count=len(self._providers),
            configured_count=len(self.list_configured()),
        )

    def get(self, provider_name: str) -> EnrichmentProviderBase | None:
        """Return provider by name, or None if not registered."""
        return self._providers.get(provider_name)

    def list_all(self) -> list[EnrichmentProviderBase]:
        """Return all registered providers (configured and unconfigured)."""
        return list(self._providers.values())

    def list_configured(self) -> list[EnrichmentProviderBase]:
        """Return only providers where is_configured() is True."""
        return [p for p in self._providers.values() if p.is_configured()]

    def list_for_type(self, indicator_type: IndicatorType) -> list[EnrichmentProviderBase]:
        """Return all configured providers that support the given indicator type."""
        return [
            p
            for p in self._providers.values()
            if p.is_configured() and indicator_type in p.supported_types
        ]


enrichment_registry = EnrichmentRegistry()
