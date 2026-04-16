"""Repository for agent_run_events table."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models.agent_run_event import AgentRunEvent
from app.repositories.base import BaseRepository


class RunEventRepository(BaseRepository[AgentRunEvent]):
    model = AgentRunEvent

    async def list_for_run(
        self,
        heartbeat_run_id: int,
        after_seq: int = 0,
        limit: int = 100,
    ) -> list[AgentRunEvent]:
        """Return events for a run, ordered by seq, optionally after a given seq."""
        result = await self._db.execute(
            select(AgentRunEvent)
            .where(
                AgentRunEvent.heartbeat_run_id == heartbeat_run_id,
            )
            .where(AgentRunEvent.seq > after_seq)
            .order_by(AgentRunEvent.seq)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_event(
        self,
        heartbeat_run_id: int,
        seq: int,
        event_type: str,
        stream: str,
        level: str = "info",
        content: str | None = None,
        payload: dict | None = None,
    ) -> AgentRunEvent:
        """Insert a new run event."""
        event = AgentRunEvent(
            heartbeat_run_id=heartbeat_run_id,
            seq=seq,
            event_type=event_type,
            stream=stream,
            level=level,
            content=content,
            payload=payload,
        )
        self._db.add(event)
        await self._db.flush()
        return event
