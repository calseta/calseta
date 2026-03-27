"""EnrichmentFieldExtraction repository — CRUD for enrichment field extraction mappings."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete

from app.db.models.enrichment_field_extraction import EnrichmentFieldExtraction
from app.repositories.base import BaseRepository


class EnrichmentFieldExtractionRepository(BaseRepository[EnrichmentFieldExtraction]):
    model = EnrichmentFieldExtraction

    async def list_extractions(
        self,
        *,
        provider_name: str | None = None,
        indicator_type: str | None = None,
        is_system: bool | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[EnrichmentFieldExtraction], int]:
        """Return (extractions, total_count) matching filters."""
        filters = []

        if provider_name is not None:
            filters.append(
                EnrichmentFieldExtraction.provider_name == provider_name
            )
        if indicator_type is not None:
            filters.append(
                EnrichmentFieldExtraction.indicator_type == indicator_type
            )
        if is_system is not None:
            filters.append(EnrichmentFieldExtraction.is_system == is_system)
        if is_active is not None:
            filters.append(EnrichmentFieldExtraction.is_active == is_active)

        return await self.paginate(
            *filters,
            order_by=EnrichmentFieldExtraction.created_at.asc(),
            page=page,
            page_size=page_size,
        )

    async def create(
        self,
        *,
        provider_name: str,
        indicator_type: str,
        source_path: str,
        target_key: str,
        value_type: str = "string",
        description: str | None = None,
    ) -> EnrichmentFieldExtraction:
        extraction = EnrichmentFieldExtraction(
            provider_name=provider_name,
            indicator_type=indicator_type,
            source_path=source_path,
            target_key=target_key,
            value_type=value_type,
            is_system=False,
            is_active=True,
            description=description,
        )
        self._db.add(extraction)
        await self._db.flush()
        await self._db.refresh(extraction)
        return extraction

    async def bulk_create(
        self, items: list[dict[str, Any]]
    ) -> list[EnrichmentFieldExtraction]:
        """Create multiple extractions. Each dict must have provider_name,
        indicator_type, source_path, target_key; optionally value_type and
        description. All are created as non-system, active."""
        extractions: list[EnrichmentFieldExtraction] = []
        for item in items:
            extraction = EnrichmentFieldExtraction(
                provider_name=item["provider_name"],
                indicator_type=item["indicator_type"],
                source_path=item["source_path"],
                target_key=item["target_key"],
                value_type=item.get("value_type", "string"),
                is_system=False,
                is_active=True,
                description=item.get("description"),
            )
            self._db.add(extraction)
            extractions.append(extraction)
        await self._db.flush()
        for extraction in extractions:
            await self._db.refresh(extraction)
        return extractions

    async def patch(
        self, extraction: EnrichmentFieldExtraction, updates: dict[str, Any]
    ) -> EnrichmentFieldExtraction:
        """Apply partial updates to an extraction."""
        for field, value in updates.items():
            setattr(extraction, field, value)
        await self._db.flush()
        await self._db.refresh(extraction)
        return extraction

    async def delete_by_provider(self, provider_name: str) -> int:
        """Delete all non-system extractions for a provider. Returns count deleted."""
        result = await self._db.execute(
            delete(EnrichmentFieldExtraction).where(
                EnrichmentFieldExtraction.provider_name == provider_name,
                EnrichmentFieldExtraction.is_system.is_(False),
            )
        )
        await self._db.flush()
        count: int = result.rowcount  # type: ignore[attr-defined]
        return count
