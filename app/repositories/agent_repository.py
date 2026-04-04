"""Agent registration repository — all DB reads/writes for the agent_registrations table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from app.db.models.agent_registration import AgentRegistration
from app.repositories.base import BaseRepository
from app.schemas.agents import AgentRegistrationCreate


class AgentRepository(BaseRepository[AgentRegistration]):
    model = AgentRegistration

    async def create(
        self,
        data: AgentRegistrationCreate,
        auth_header_value_encrypted: str | None,
    ) -> AgentRegistration:
        """Persist a new agent registration. Returns the created ORM object with id populated."""
        agent = AgentRegistration(
            uuid=uuid.uuid4(),
            name=data.name,
            description=data.description,
            endpoint_url=data.endpoint_url,
            auth_header_name=data.auth_header_name,
            auth_header_value_encrypted=auth_header_value_encrypted,
            trigger_on_sources=data.trigger_on_sources,
            trigger_on_severities=data.trigger_on_severities,
            trigger_filter=data.trigger_filter,
            timeout_seconds=data.timeout_seconds,
            retry_count=data.retry_count,
            documentation=data.documentation,
            # --- Control plane: status ---
            status="active",
            # --- Control plane: identity & type ---
            execution_mode=data.execution_mode,
            agent_type=data.agent_type,
            role=data.role,
            capabilities=data.capabilities,
            # --- Control plane: adapter ---
            adapter_type=data.adapter_type,
            adapter_config=data.adapter_config,
            # --- Control plane: managed agent config ---
            llm_integration_id=data.llm_integration_id,
            system_prompt=data.system_prompt,
            methodology=data.methodology,
            tool_ids=data.tool_ids,
            max_tokens=data.max_tokens,
            enable_thinking=data.enable_thinking,
            instruction_files=data.instruction_files,
            # --- Control plane: orchestrator config ---
            sub_agent_ids=data.sub_agent_ids,
            max_sub_agent_calls=data.max_sub_agent_calls,
            # --- Control plane: budget ---
            budget_monthly_cents=data.budget_monthly_cents,
            # --- Control plane: runtime limits ---
            max_concurrent_alerts=data.max_concurrent_alerts,
            max_cost_per_alert_cents=data.max_cost_per_alert_cents,
            max_investigation_minutes=data.max_investigation_minutes,
            stall_threshold=data.stall_threshold,
            memory_promotion_requires_approval=data.memory_promotion_requires_approval,
        )
        self._db.add(agent)
        await self._db.flush()
        await self._db.refresh(agent)
        return agent

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentRegistration], int]:
        """Return (agents, total_count) ordered by created_at descending."""
        return await self.paginate(
            order_by=AgentRegistration.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    async def list_filtered(
        self,
        status: str | None = None,
        agent_type: str | None = None,
        role: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentRegistration], int]:
        """Return (agents, total_count) with optional filters on status, agent_type, and role."""
        filters = []
        if status is not None:
            filters.append(AgentRegistration.status == status)
        if agent_type is not None:
            filters.append(AgentRegistration.agent_type == agent_type)
        if role is not None:
            filters.append(AgentRegistration.role == role)
        return await self.paginate(
            *filters,
            order_by=AgentRegistration.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    _UPDATABLE_FIELDS: frozenset[str] = frozenset({
        "name",
        "description",
        "endpoint_url",
        "status",
        "auth_header_name",
        "auth_header_value_encrypted",
        "trigger_on_sources",
        "trigger_on_severities",
        "trigger_filter",
        "timeout_seconds",
        "retry_count",
        "documentation",
        # --- Control plane fields ---
        "execution_mode",
        "agent_type",
        "role",
        "capabilities",
        "adapter_type",
        "adapter_config",
        "llm_integration_id",
        "system_prompt",
        "methodology",
        "tool_ids",
        "max_tokens",
        "enable_thinking",
        "instruction_files",
        "sub_agent_ids",
        "max_sub_agent_calls",
        "budget_monthly_cents",
        "max_concurrent_alerts",
        "max_cost_per_alert_cents",
        "max_investigation_minutes",
        "stall_threshold",
        "memory_promotion_requires_approval",
    })

    _NULLABLE_FIELDS: frozenset[str] = frozenset({
        "description",
        "endpoint_url",
        "auth_header_name",
        "auth_header_value_encrypted",
        "trigger_filter",
        "documentation",
        "role",
        "capabilities",
        "adapter_config",
        "llm_integration_id",
        "system_prompt",
        "methodology",
        "tool_ids",
        "max_tokens",
        "instruction_files",
        "sub_agent_ids",
        "max_sub_agent_calls",
    })

    async def patch(
        self,
        agent: AgentRegistration,
        **kwargs: Any,
    ) -> AgentRegistration:
        """Apply partial updates to an agent registration."""
        for key, value in kwargs.items():
            if key not in self._UPDATABLE_FIELDS:
                raise ValueError(f"Field '{key}' is not updatable")
            if value is not None or key in self._NULLABLE_FIELDS:
                setattr(agent, key, value)
        await self._db.flush()
        await self._db.refresh(agent)
        return agent

    async def list_active(self) -> list[AgentRegistration]:
        """Return all active agent registrations. Used by trigger evaluation."""
        result = await self._db.execute(
            select(AgentRegistration)
            .where(AgentRegistration.status == "active")
            .order_by(AgentRegistration.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_active_managed(self) -> list[AgentRegistration]:
        """Return all managed agents that are currently active."""
        result = await self._db.execute(
            select(AgentRegistration)
            .where(
                AgentRegistration.execution_mode == "managed",
                AgentRegistration.status == "active",
            )
            .order_by(AgentRegistration.created_at.asc())
        )
        return list(result.scalars().all())
