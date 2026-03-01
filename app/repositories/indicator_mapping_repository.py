"""IndicatorFieldMapping repository — CRUD for indicator extraction field mappings."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.indicator_field_mapping import IndicatorFieldMapping
from app.schemas.indicator_mappings import (
    IndicatorFieldMappingCreate,
    IndicatorFieldMappingPatch,
)


class IndicatorMappingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_uuid(self, mapping_uuid: uuid.UUID) -> IndicatorFieldMapping | None:
        result = await self._db.execute(
            select(IndicatorFieldMapping).where(
                IndicatorFieldMapping.uuid == mapping_uuid
            )
        )
        return result.scalar_one_or_none()

    async def list_mappings(
        self,
        *,
        source_name: str | None = None,
        is_system: bool | None = None,
        is_active: bool | None = None,
        extraction_target: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IndicatorFieldMapping], int]:
        """Return (mappings, total_count) matching filters."""
        from sqlalchemy import func

        stmt = select(IndicatorFieldMapping)
        count_stmt = select(func.count()).select_from(IndicatorFieldMapping)

        if source_name is not None:
            stmt = stmt.where(IndicatorFieldMapping.source_name == source_name)
            count_stmt = count_stmt.where(IndicatorFieldMapping.source_name == source_name)
        if is_system is not None:
            stmt = stmt.where(IndicatorFieldMapping.is_system == is_system)
            count_stmt = count_stmt.where(IndicatorFieldMapping.is_system == is_system)
        if is_active is not None:
            stmt = stmt.where(IndicatorFieldMapping.is_active == is_active)
            count_stmt = count_stmt.where(IndicatorFieldMapping.is_active == is_active)
        if extraction_target is not None:
            stmt = stmt.where(
                IndicatorFieldMapping.extraction_target == extraction_target
            )
            count_stmt = count_stmt.where(
                IndicatorFieldMapping.extraction_target == extraction_target
            )

        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            stmt.order_by(IndicatorFieldMapping.created_at.asc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_active_for_extraction(
        self,
        source_name: str,
        extraction_target: str,
    ) -> list[IndicatorFieldMapping]:
        """
        Return all active mappings applicable to the given source and target.
        Includes global mappings (source_name IS NULL) and source-specific ones.
        """
        result = await self._db.execute(
            select(IndicatorFieldMapping).where(
                IndicatorFieldMapping.is_active.is_(True),
                IndicatorFieldMapping.extraction_target == extraction_target,
                (IndicatorFieldMapping.source_name == source_name)
                | (IndicatorFieldMapping.source_name.is_(None)),
            )
        )
        return list(result.scalars().all())

    async def create(self, data: IndicatorFieldMappingCreate) -> IndicatorFieldMapping:
        mapping = IndicatorFieldMapping(
            source_name=data.source_name,
            field_path=data.field_path,
            indicator_type=data.indicator_type,
            extraction_target=data.extraction_target,
            is_system=False,
            is_active=data.is_active,
            description=data.description,
        )
        self._db.add(mapping)
        await self._db.flush()
        await self._db.refresh(mapping)
        return mapping

    async def patch(
        self,
        mapping: IndicatorFieldMapping,
        data: IndicatorFieldMappingPatch,
    ) -> IndicatorFieldMapping:
        """Apply partial updates. System mappings can only have is_active toggled."""
        updates = data.model_dump(exclude_none=True)
        for field, value in updates.items():
            setattr(mapping, field, value)
        await self._db.flush()
        await self._db.refresh(mapping)
        return mapping

    async def delete(self, mapping: IndicatorFieldMapping) -> None:
        await self._db.delete(mapping)
        await self._db.flush()
