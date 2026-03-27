"""Repository for enrichment_providers table."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db.models.enrichment_provider import EnrichmentProvider
from app.repositories.base import BaseRepository


class EnrichmentProviderRepository(BaseRepository[EnrichmentProvider]):
    model = EnrichmentProvider

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
        filters = []
        if is_active is not None:
            filters.append(EnrichmentProvider.is_active == is_active)
        if is_builtin is not None:
            filters.append(EnrichmentProvider.is_builtin == is_builtin)

        return await self.paginate(
            *filters,
            order_by=EnrichmentProvider.created_at.asc(),
            page=page,
            page_size=page_size,
        )

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
