"""
EnrichmentRegistry — singleton registry for all enrichment providers.

Providers are registered at import time from app/integrations/enrichment/__init__.py.
Route handlers and services access the registry via `enrichment_registry`.
"""

from __future__ import annotations

import structlog

from app.integrations.enrichment.base import EnrichmentProviderBase
from app.schemas.indicators import IndicatorType

logger = structlog.get_logger(__name__)


class EnrichmentRegistry:
    """
    Singleton registry mapping provider_name → EnrichmentProviderBase instance.

    Thread-safe for reads (no writes after startup). Providers are registered
    once at process start via __init__.py; no dynamic registration at runtime.
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
