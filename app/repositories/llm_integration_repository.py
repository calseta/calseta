"""LLM integration repository — all DB reads/writes for the llm_integrations table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select, update

from app.db.models.llm_integration import LLMIntegration
from app.repositories.base import BaseRepository
from app.schemas.llm_integrations import LLMIntegrationCreate


class LLMIntegrationRepository(BaseRepository[LLMIntegration]):
    model = LLMIntegration

    async def create(self, data: LLMIntegrationCreate) -> LLMIntegration:
        """Persist a new LLM integration. Returns the created ORM object with id populated."""
        integration = LLMIntegration(
            uuid=uuid.uuid4(),
            name=data.name,
            provider=data.provider,
            model=data.model,
            api_key_ref=data.api_key_ref,
            base_url=data.base_url,
            config=data.config,
            cost_per_1k_input_tokens_cents=data.cost_per_1k_input_tokens_cents,
            cost_per_1k_output_tokens_cents=data.cost_per_1k_output_tokens_cents,
            is_default=data.is_default,
        )
        self._db.add(integration)
        await self._db.flush()
        await self._db.refresh(integration)
        return integration

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[LLMIntegration], int]:
        """Return (integrations, total_count) ordered by created_at descending."""
        return await self.paginate(
            order_by=LLMIntegration.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    async def get_by_name(self, name: str) -> LLMIntegration | None:
        """Fetch a single integration by unique name."""
        result = await self._db.execute(
            select(LLMIntegration).where(LLMIntegration.name == name)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def get_default(self) -> LLMIntegration | None:
        """Return the integration flagged as is_default=True, or None."""
        result = await self._db.execute(
            select(LLMIntegration).where(LLMIntegration.is_default.is_(True))
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def set_default(self, integration: LLMIntegration) -> LLMIntegration:
        """
        Mark the given integration as the default.

        Unsets is_default on all other integrations first to maintain a single default.
        """
        # Clear all existing defaults
        await self._db.execute(
            update(LLMIntegration)
            .where(LLMIntegration.id != integration.id)
            .values(is_default=False)
        )
        integration.is_default = True
        await self._db.flush()
        await self._db.refresh(integration)
        return integration

    _UPDATABLE_FIELDS: frozenset[str] = frozenset({
        "name",
        "provider",
        "model",
        "api_key_ref",
        "base_url",
        "config",
        "cost_per_1k_input_tokens_cents",
        "cost_per_1k_output_tokens_cents",
        "is_default",
    })

    _NULLABLE_FIELDS: frozenset[str] = frozenset({
        "api_key_ref",
        "base_url",
        "config",
    })

    async def patch(
        self,
        integration: LLMIntegration,
        **kwargs: Any,
    ) -> LLMIntegration:
        """Apply partial updates to an LLM integration."""
        for key, value in kwargs.items():
            if key not in self._UPDATABLE_FIELDS:
                raise ValueError(f"Field '{key}' is not updatable")
            if value is not None or key in self._NULLABLE_FIELDS:
                setattr(integration, key, value)
        await self._db.flush()
        await self._db.refresh(integration)
        return integration
