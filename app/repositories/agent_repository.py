"""Agent registration repository — all DB reads/writes for the agent_registrations table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import AgentRegistration
from app.schemas.agents import AgentRegistrationCreate


class AgentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

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
            is_active=data.is_active,
            documentation=data.documentation,
        )
        self._db.add(agent)
        await self._db.flush()
        await self._db.refresh(agent)
        return agent

    async def get_by_uuid(self, agent_uuid: uuid.UUID) -> AgentRegistration | None:
        result = await self._db.execute(
            select(AgentRegistration).where(AgentRegistration.uuid == agent_uuid)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, agent_id: int) -> AgentRegistration | None:
        result = await self._db.execute(
            select(AgentRegistration).where(AgentRegistration.id == agent_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentRegistration], int]:
        """Return (agents, total_count) ordered by created_at descending."""
        count_stmt = select(func.count()).select_from(AgentRegistration)
        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = (
            select(AgentRegistration)
            .order_by(AgentRegistration.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    _UPDATABLE_FIELDS: frozenset[str] = frozenset({
        "name",
        "description",
        "endpoint_url",
        "is_active",
        "auth_header_name",
        "auth_header_value_encrypted",
        "trigger_on_sources",
        "trigger_on_severities",
        "trigger_filter",
        "timeout_seconds",
        "retry_count",
        "documentation",
    })

    _NULLABLE_FIELDS: frozenset[str] = frozenset({
        "description",
        "auth_header_name",
        "auth_header_value_encrypted",
        "trigger_filter",
        "documentation",
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

    async def delete(self, agent: AgentRegistration) -> None:
        await self._db.delete(agent)
        await self._db.flush()

    async def list_active(self) -> list[AgentRegistration]:
        """Return all active agent registrations. Used by trigger evaluation."""
        result = await self._db.execute(
            select(AgentRegistration)
            .where(AgentRegistration.is_active.is_(True))
            .order_by(AgentRegistration.created_at.asc())
        )
        return list(result.scalars().all())
