"""AgentAction repository — create, query, and update agent-proposed actions."""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.models.agent_action import AgentAction
from app.repositories.base import BaseRepository


class AgentActionRepository(BaseRepository[AgentAction]):
    model = AgentAction

    async def create(
        self,
        alert_id: int,
        agent_registration_id: int,
        assignment_id: int,
        action_type: str,
        action_subtype: str,
        payload: dict[str, Any],
        confidence: Decimal | None = None,
    ) -> AgentAction:
        """Create a new agent action in ``proposed`` status."""
        action = AgentAction(
            uuid=uuid_module.uuid4(),
            alert_id=alert_id,
            agent_registration_id=agent_registration_id,
            assignment_id=assignment_id,
            action_type=action_type,
            action_subtype=action_subtype,
            status="proposed",
            payload=payload,
            confidence=confidence,
        )
        self._db.add(action)
        await self._db.flush()
        await self._db.refresh(action)
        return action

    async def get_by_uuid(self, uuid: UUID) -> AgentAction | None:
        """Fetch a single action by UUID."""
        result = await self._db.execute(
            select(AgentAction).where(AgentAction.uuid == uuid)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def get_by_uuid_int_id(self, id: int) -> AgentAction | None:
        """Fetch a single action by integer primary key."""
        result = await self._db.execute(
            select(AgentAction).where(AgentAction.id == id)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def get_by_approval_request_id(
        self, approval_request_id: int
    ) -> AgentAction | None:
        """Fetch the action linked to a workflow approval request."""
        result = await self._db.execute(
            select(AgentAction).where(
                AgentAction.approval_request_id == approval_request_id
            )
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def list_for_assignment(
        self,
        assignment_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentAction], int]:
        """Return (actions, total) for the given assignment, ordered by creation time."""
        return await self.paginate(
            AgentAction.assignment_id == assignment_id,
            order_by=AgentAction.created_at.asc(),
            page=page,
            page_size=page_size,
        )

    async def list_all(
        self,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentAction], int]:
        """Return (actions, total) across all assignments, optionally filtered by status."""
        filters = []
        if status is not None:
            filters.append(AgentAction.status == status)
        return await self.paginate(
            *filters,
            order_by=AgentAction.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    async def update_status(
        self,
        action: AgentAction,
        status: str,
        execution_result: dict[str, Any] | None = None,
        executed_at: datetime | None = None,
    ) -> AgentAction:
        """Update the status of an action, optionally recording the execution result."""
        action.status = status
        if execution_result is not None:
            action.execution_result = execution_result
        if executed_at is not None:
            action.executed_at = executed_at
        await self._db.flush()
        await self._db.refresh(action)
        return action
