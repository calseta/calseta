"""AgentTaskSession repository — all DB reads/writes for the agent_task_sessions table."""

from __future__ import annotations

import uuid as uuid_module
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models.agent_task_session import AgentTaskSession
from app.repositories.base import BaseRepository


class AgentTaskSessionRepository(BaseRepository[AgentTaskSession]):
    model = AgentTaskSession

    async def get_by_agent_and_task_key(
        self, agent_id: int, task_key: str
    ) -> AgentTaskSession | None:
        """Fetch an active (non-archived) session for a given agent+task_key pair."""
        result = await self._db.execute(
            select(AgentTaskSession).where(
                AgentTaskSession.agent_registration_id == agent_id,
                AgentTaskSession.task_key == task_key,
                AgentTaskSession.is_archived == False,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def create(
        self,
        agent_id: int,
        task_key: str,
        alert_id: int | None = None,
    ) -> AgentTaskSession:
        """Create a new session for agent+task_key.

        Handles the unique constraint on (agent_registration_id, task_key) by
        catching IntegrityError and re-fetching the existing row.
        """
        session_obj = AgentTaskSession(
            uuid=uuid_module.uuid4(),
            agent_registration_id=agent_id,
            task_key=task_key,
            alert_id=alert_id,
            session_params={},
        )
        self._db.add(session_obj)
        try:
            await self._db.flush()
            await self._db.refresh(session_obj)
            return session_obj
        except IntegrityError:
            await self._db.rollback()
            # Race condition: another worker created the row — fetch it
            existing = await self.get_by_agent_and_task_key(agent_id, task_key)
            if existing is not None:
                return existing
            raise

    async def update(
        self,
        session_obj: AgentTaskSession,
        **kwargs: Any,
    ) -> AgentTaskSession:
        """Apply updates to an existing session row."""
        _UPDATABLE = frozenset({
            "session_params",
            "session_display_id",
            "total_input_tokens",
            "total_output_tokens",
            "total_cost_cents",
            "heartbeat_count",
            "last_run_id",
            "last_error",
            "compacted_at",
            "is_archived",
        })
        for key, value in kwargs.items():
            if key not in _UPDATABLE:
                raise ValueError(f"Field '{key}' is not updatable on AgentTaskSession")
            setattr(session_obj, key, value)
        await self._db.flush()
        await self._db.refresh(session_obj)
        return session_obj

    async def list_for_agent(
        self,
        agent_id: int,
        archived: bool = False,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentTaskSession], int]:
        """Return (sessions, total_count) for a given agent, ordered newest-first."""
        return await self.paginate(
            AgentTaskSession.agent_registration_id == agent_id,
            AgentTaskSession.is_archived == archived,  # noqa: E712
            order_by=AgentTaskSession.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    async def archive(self, session_obj: AgentTaskSession) -> AgentTaskSession:
        """Mark a session as archived (operator override to reset investigation state)."""
        session_obj.is_archived = True
        await self._db.flush()
        await self._db.refresh(session_obj)
        return session_obj
