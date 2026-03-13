"""EnrichmentFieldExtraction repository — CRUD for enrichment field extraction mappings."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enrichment_field_extraction import EnrichmentFieldExtraction


class EnrichmentFieldExtractionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_uuid(
        self, extraction_uuid: uuid.UUID
    ) -> EnrichmentFieldExtraction | None:
        result = await self._db.execute(
            select(EnrichmentFieldExtraction).where(
                EnrichmentFieldExtraction.uuid == extraction_uuid
            )
        )
        return result.scalar_one_or_none()

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
        stmt = select(EnrichmentFieldExtraction)
        count_stmt = select(func.count()).select_from(EnrichmentFieldExtraction)

        if provider_name is not None:
            stmt = stmt.where(
                EnrichmentFieldExtraction.provider_name == provider_name
            )
            count_stmt = count_stmt.where(
                EnrichmentFieldExtraction.provider_name == provider_name
            )
        if indicator_type is not None:
            stmt = stmt.where(
                EnrichmentFieldExtraction.indicator_type == indicator_type
            )
            count_stmt = count_stmt.where(
                EnrichmentFieldExtraction.indicator_type == indicator_type
            )
        if is_system is not None:
            stmt = stmt.where(EnrichmentFieldExtraction.is_system == is_system)
            count_stmt = count_stmt.where(
                EnrichmentFieldExtraction.is_system == is_system
            )
        if is_active is not None:
            stmt = stmt.where(EnrichmentFieldExtraction.is_active == is_active)
            count_stmt = count_stmt.where(
                EnrichmentFieldExtraction.is_active == is_active
            )

        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(EnrichmentFieldExtraction.created_at.asc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

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

    async def delete(self, extraction: EnrichmentFieldExtraction) -> None:
        await self._db.delete(extraction)
        await self._db.flush()

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
