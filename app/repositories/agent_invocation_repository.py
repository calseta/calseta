"""AgentInvocation repository — create, query, and update invocation records."""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.models.agent_invocation import AgentInvocation
from app.repositories.base import BaseRepository


class AgentInvocationRepository(BaseRepository[AgentInvocation]):
    model = AgentInvocation

    async def create(
        self,
        parent_agent_id: int,
        alert_id: int,
        task_description: str,
        child_agent_id: int | None = None,
        assignment_id: int | None = None,
        input_context: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
        timeout_seconds: int = 300,
    ) -> AgentInvocation:
        """Create a new invocation in ``queued`` status."""
        invocation = AgentInvocation(
            uuid=uuid_module.uuid4(),
            parent_agent_id=parent_agent_id,
            child_agent_id=child_agent_id,
            alert_id=alert_id,
            assignment_id=assignment_id,
            task_description=task_description,
            input_context=input_context,
            output_schema=output_schema,
            status="queued",
            timeout_seconds=timeout_seconds,
            cost_cents=0,
        )
        self._db.add(invocation)
        await self._db.flush()
        await self._db.refresh(invocation)
        return invocation

    async def get_by_uuid(self, uuid: UUID) -> AgentInvocation | None:
        """Fetch a single invocation by UUID."""
        result = await self._db.execute(
            select(AgentInvocation).where(AgentInvocation.uuid == uuid)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def list_for_agent(
        self,
        parent_agent_id: int,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentInvocation], int]:
        """Return (invocations, total) for the given orchestrator."""
        filters = [AgentInvocation.parent_agent_id == parent_agent_id]
        if status is not None:
            filters.append(AgentInvocation.status == status)
        return await self.paginate(
            *filters,
            order_by=AgentInvocation.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    async def list_for_alert(
        self,
        alert_id: int,
        parent_agent_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentInvocation], int]:
        """Return all invocations for an alert, optionally filtered by orchestrator."""
        filters = [AgentInvocation.alert_id == alert_id]
        if parent_agent_id is not None:
            filters.append(AgentInvocation.parent_agent_id == parent_agent_id)
        return await self.paginate(
            *filters,
            order_by=AgentInvocation.created_at.asc(),
            page=page,
            page_size=page_size,
        )

    async def list_timed_out_candidates(
        self,
        cutoff: datetime,
    ) -> list[AgentInvocation]:
        """Return running invocations whose deadline has passed.

        A running invocation times out when:
            started_at + timeout_seconds <= cutoff (now)
        """
        from sqlalchemy import and_, cast, func, literal
        from sqlalchemy.dialects.postgresql import TIMESTAMP

        # Cast Python datetime to a SQLAlchemy literal so extract() accepts it
        cutoff_literal = cast(literal(cutoff), TIMESTAMP(timezone=True))

        result = await self._db.execute(
            select(AgentInvocation).where(
                and_(
                    AgentInvocation.status == "running",
                    AgentInvocation.started_at.isnot(None),
                    func.extract(
                        "epoch",
                        AgentInvocation.started_at,
                    )
                    + AgentInvocation.timeout_seconds
                    <= func.extract("epoch", cutoff_literal),
                )
            )
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        invocation: AgentInvocation,
        status: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        cost_cents: int | None = None,
        task_queue_id: str | None = None,
    ) -> AgentInvocation:
        """Update invocation status and optional lifecycle fields."""
        invocation.status = status
        if result is not None:
            invocation.result = result
        if error is not None:
            invocation.error = error
        if started_at is not None:
            invocation.started_at = started_at
        if completed_at is not None:
            invocation.completed_at = completed_at
        if cost_cents is not None:
            invocation.cost_cents = cost_cents
        if task_queue_id is not None:
            invocation.task_queue_id = task_queue_id
        await self._db.flush()
        await self._db.refresh(invocation)
        return invocation
