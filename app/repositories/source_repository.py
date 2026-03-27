"""Source integration repository — all DB reads/writes for the source_integrations table."""

from __future__ import annotations

import uuid
from typing import Any

from app.db.models.source_integration import SourceIntegration
from app.repositories.base import BaseRepository
from app.schemas.sources import SourceIntegrationCreate


class SourceRepository(BaseRepository[SourceIntegration]):
    model = SourceIntegration

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

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SourceIntegration], int]:
        """Return (integrations, total_count) ordered by created_at descending."""
        return await self.paginate(
            order_by=SourceIntegration.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    _UPDATABLE_FIELDS: frozenset[str] = frozenset({
        "display_name",
        "is_active",
        "auth_type",
        "auth_config",
        "documentation",
    })

    _NULLABLE_FIELDS: frozenset[str] = frozenset({
        "auth_type",
        "auth_config",
        "documentation",
    })

    async def patch(
        self,
        integration: SourceIntegration,
        **kwargs: Any,
    ) -> SourceIntegration:
        """Apply partial updates to a source integration."""
        for key, value in kwargs.items():
            if key not in self._UPDATABLE_FIELDS:
                raise ValueError(f"Field '{key}' is not updatable")
            if value is not None or key in self._NULLABLE_FIELDS:
                setattr(integration, key, value)
        await self._db.flush()
        await self._db.refresh(integration)
        return integration
