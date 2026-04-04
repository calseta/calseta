"""HeartbeatRun repository — all DB reads/writes for the heartbeat_runs table."""

from __future__ import annotations

import uuid as uuid_module

from sqlalchemy import select

from app.db.models.heartbeat_run import HeartbeatRun
from app.repositories.base import BaseRepository


class HeartbeatRunRepository(BaseRepository[HeartbeatRun]):
    model = HeartbeatRun

    async def create(self, agent_id: int, source: str) -> HeartbeatRun:
        """Create a new heartbeat run row in 'queued' status."""
        run = HeartbeatRun(
            uuid=uuid_module.uuid4(),
            agent_registration_id=agent_id,
            source=source,
            status="queued",
        )
        self._db.add(run)
        await self._db.flush()
        await self._db.refresh(run)
        return run

    _UPDATABLE_FIELDS: frozenset[str] = frozenset({
        "status",
        "started_at",
        "finished_at",
        "error",
        "alerts_processed",
        "actions_proposed",
        "context_snapshot",
    })

    async def update_status(
        self,
        run: HeartbeatRun,
        status: str,
        **kwargs: object,
    ) -> HeartbeatRun:
        """Update status and any additional fields on a heartbeat run."""
        run.status = status
        for key, value in kwargs.items():
            if key not in self._UPDATABLE_FIELDS:
                raise ValueError(f"Field '{key}' is not updatable on HeartbeatRun")
            setattr(run, key, value)
        await self._db.flush()
        await self._db.refresh(run)
        return run

    async def list_for_agent(
        self,
        agent_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[HeartbeatRun], int]:
        """Return (runs, total_count) for an agent, ordered newest-first."""
        return await self.paginate(
            HeartbeatRun.agent_registration_id == agent_id,
            order_by=HeartbeatRun.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    async def get_latest_for_agent(self, agent_id: int) -> HeartbeatRun | None:
        """Return the most recent heartbeat run for an agent."""
        result = await self._db.execute(
            select(HeartbeatRun)
            .where(HeartbeatRun.agent_registration_id == agent_id)
            .order_by(HeartbeatRun.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]
