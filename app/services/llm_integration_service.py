"""
LLMIntegrationService — business logic for LLM integration management.

Handles validation, lifecycle management, and usage aggregation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.db.models.cost_event import CostEvent
from app.db.models.llm_integration import LLMIntegration
from app.repositories.llm_integration_repository import LLMIntegrationRepository
from app.schemas.llm_integrations import LLMIntegrationCreate, LLMIntegrationPatch, LLMProvider

logger = structlog.get_logger(__name__)

_VALID_PROVIDERS: frozenset[str] = frozenset(p.value for p in LLMProvider)


class LLMIntegrationService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = LLMIntegrationRepository(db)

    async def create(self, data: LLMIntegrationCreate) -> LLMIntegration:
        """
        Create a new LLM integration.

        Validates that the name is unique and the provider is a known value.
        If is_default=True, unsets any existing default first.
        """
        if data.provider not in _VALID_PROVIDERS:
            raise CalsetaException(
                code="INVALID_PROVIDER",
                message=(
                    f"Unknown provider '{data.provider}'. "
                    f"Valid values: {sorted(_VALID_PROVIDERS)}"
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        existing = await self._repo.get_by_name(data.name)
        if existing is not None:
            raise CalsetaException(
                code="DUPLICATE_NAME",
                message=f"An LLM integration with name '{data.name}' already exists.",
                status_code=status.HTTP_409_CONFLICT,
            )

        integration = await self._repo.create(data)

        if data.is_default:
            integration = await self._repo.set_default(integration)

        logger.info(
            "llm_integration_created",
            uuid=str(integration.uuid),
            name=integration.name,
            provider=integration.provider,
        )
        return integration

    async def update(
        self,
        integration: LLMIntegration,
        data: LLMIntegrationPatch,
    ) -> LLMIntegration:
        """
        Apply a partial update to an existing LLM integration.

        If name is changing, ensures the new name doesn't conflict.
        If is_default is being set to True, unsets the existing default.
        """
        updates: dict[str, Any] = {}

        if data.name is not None and data.name != integration.name:
            conflict = await self._repo.get_by_name(data.name)
            if conflict is not None:
                raise CalsetaException(
                    code="DUPLICATE_NAME",
                    message=f"An LLM integration with name '{data.name}' already exists.",
                    status_code=status.HTTP_409_CONFLICT,
                )
            updates["name"] = data.name

        if data.provider is not None:
            if data.provider not in _VALID_PROVIDERS:
                raise CalsetaException(
                    code="INVALID_PROVIDER",
                    message=f"Unknown provider '{data.provider}'.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            updates["provider"] = data.provider

        if data.model is not None:
            updates["model"] = data.model
        if data.api_key_ref is not None:
            updates["api_key_ref"] = data.api_key_ref
        if data.base_url is not None:
            updates["base_url"] = data.base_url
        if data.config is not None:
            updates["config"] = data.config
        if data.cost_per_1k_input_tokens_cents is not None:
            updates["cost_per_1k_input_tokens_cents"] = data.cost_per_1k_input_tokens_cents
        if data.cost_per_1k_output_tokens_cents is not None:
            updates["cost_per_1k_output_tokens_cents"] = data.cost_per_1k_output_tokens_cents

        set_default = data.is_default is True

        if updates:
            integration = await self._repo.patch(integration, **updates)

        if set_default and not integration.is_default:
            integration = await self._repo.set_default(integration)
        elif data.is_default is False and integration.is_default:
            # Explicitly unsetting the default — just clear the flag
            integration = await self._repo.patch(integration, is_default=False)

        logger.info("llm_integration_updated", uuid=str(integration.uuid))
        return integration

    async def delete(self, integration: LLMIntegration) -> None:
        """
        Delete an LLM integration.

        Raises HTTP 409 if any agent_registration references this integration via
        llm_integration_id — removing it would orphan those agents.
        """
        from app.db.models.agent_registration import AgentRegistration

        result = await self._db.execute(
            select(func.count())
            .select_from(AgentRegistration)
            .where(AgentRegistration.llm_integration_id == integration.id)
        )
        ref_count: int = result.scalar_one()

        if ref_count > 0:
            raise CalsetaException(
                code="INTEGRATION_IN_USE",
                message=(
                    f"Cannot delete LLM integration '{integration.name}': "
                    f"{ref_count} agent registration(s) reference it. "
                    "Update or delete those agents first."
                ),
                status_code=status.HTTP_409_CONFLICT,
                details={"agent_count": ref_count},
            )

        logger.info(
            "llm_integration_deleted",
            uuid=str(integration.uuid),
            name=integration.name,
        )
        await self._repo.delete(integration)

    async def get_usage(
        self,
        integration_id: int,
        from_dt: datetime,
        to_dt: datetime,
    ) -> dict[str, Any]:
        """
        Aggregate cost_events for the given llm_integration_id within a time range.

        Returns totals for input_tokens, output_tokens, cost_cents, event count,
        and a breakdown of event counts by billing_type.
        """
        stmt = select(
            func.coalesce(func.sum(CostEvent.input_tokens), 0).label("total_input_tokens"),
            func.coalesce(func.sum(CostEvent.output_tokens), 0).label("total_output_tokens"),
            func.coalesce(func.sum(CostEvent.cost_cents), 0).label("total_cost_cents"),
            func.count(CostEvent.id).label("event_count"),
        ).where(
            CostEvent.llm_integration_id == integration_id,
            CostEvent.occurred_at >= from_dt,
            CostEvent.occurred_at <= to_dt,
        )
        result = await self._db.execute(stmt)
        row = result.one()

        # Billing type breakdown
        billing_stmt = select(
            CostEvent.billing_type,
            func.count(CostEvent.id).label("cnt"),
        ).where(
            CostEvent.llm_integration_id == integration_id,
            CostEvent.occurred_at >= from_dt,
            CostEvent.occurred_at <= to_dt,
        ).group_by(CostEvent.billing_type)
        billing_result = await self._db.execute(billing_stmt)
        billing_types: dict[str, int] = {
            bt: count for bt, count in billing_result.all()
        }

        return {
            "total_input_tokens": row.total_input_tokens,
            "total_output_tokens": row.total_output_tokens,
            "total_cost_cents": row.total_cost_cents,
            "event_count": row.event_count,
            "billing_types": billing_types,
        }
