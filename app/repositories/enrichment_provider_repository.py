"""Repository for enrichment_providers table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enrichment_provider import EnrichmentProvider


class EnrichmentProviderRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_uuid(self, provider_uuid: uuid.UUID) -> EnrichmentProvider | None:
        result = await self._db.execute(
            select(EnrichmentProvider).where(EnrichmentProvider.uuid == provider_uuid)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, provider_name: str) -> EnrichmentProvider | None:
        result = await self._db.execute(
            select(EnrichmentProvider).where(
                EnrichmentProvider.provider_name == provider_name
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        is_active: bool | None = None,
        is_builtin: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[EnrichmentProvider], int]:
        stmt = select(EnrichmentProvider)
        count_stmt = select(func.count()).select_from(EnrichmentProvider)

        if is_active is not None:
            stmt = stmt.where(EnrichmentProvider.is_active == is_active)
            count_stmt = count_stmt.where(EnrichmentProvider.is_active == is_active)
        if is_builtin is not None:
            stmt = stmt.where(EnrichmentProvider.is_builtin == is_builtin)
            count_stmt = count_stmt.where(EnrichmentProvider.is_builtin == is_builtin)

        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = stmt.order_by(EnrichmentProvider.created_at.asc()).offset(offset).limit(page_size)
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, **kwargs: Any) -> EnrichmentProvider:
        provider = EnrichmentProvider(**kwargs)
        self._db.add(provider)
        await self._db.flush()
        await self._db.refresh(provider)
        return provider

    async def patch(
        self, provider: EnrichmentProvider, updates: dict[str, Any]
    ) -> EnrichmentProvider:
        for field, value in updates.items():
            setattr(provider, field, value)
        await self._db.flush()
        await self._db.refresh(provider)
        return provider

    async def delete(self, provider: EnrichmentProvider) -> None:
        await self._db.delete(provider)
        await self._db.flush()
