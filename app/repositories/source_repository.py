"""Source integration repository — all DB reads/writes for the source_integrations table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.source_integration import SourceIntegration
from app.schemas.sources import SourceIntegrationCreate


class SourceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        data: SourceIntegrationCreate,
        auth_config_encrypted: dict[str, Any] | None,
    ) -> SourceIntegration:
        """Persist a new source integration. Returns the created ORM object with id populated."""
        integration = SourceIntegration(
            uuid=uuid.uuid4(),
            source_name=data.source_name,
            display_name=data.display_name,
            is_active=data.is_active,
            auth_type=data.auth_type,
            auth_config=auth_config_encrypted,
            documentation=data.documentation,
        )
        self._db.add(integration)
        await self._db.flush()
        await self._db.refresh(integration)
        return integration

    async def get_by_uuid(self, integration_uuid: uuid.UUID) -> SourceIntegration | None:
        result = await self._db.execute(
            select(SourceIntegration).where(SourceIntegration.uuid == integration_uuid)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SourceIntegration], int]:
        """Return (integrations, total_count) ordered by created_at descending."""
        count_stmt = select(func.count()).select_from(SourceIntegration)
        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            select(SourceIntegration)
            .order_by(SourceIntegration.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def patch(
        self,
        integration: SourceIntegration,
        **kwargs: Any,
    ) -> SourceIntegration:
        """Apply partial updates to a source integration."""
        nullable_fields = {
            "auth_type",
            "auth_config",
            "documentation",
        }
        for key, value in kwargs.items():
            if value is not None or key in nullable_fields:
                setattr(integration, key, value)
        await self._db.flush()
        await self._db.refresh(integration)
        return integration

    async def delete(self, integration: SourceIntegration) -> None:
        await self._db.delete(integration)
        await self._db.flush()
