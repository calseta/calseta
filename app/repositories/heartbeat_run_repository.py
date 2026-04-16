"""HeartbeatRun repository — all DB reads/writes for the heartbeat_runs table."""

from __future__ import annotations

import uuid as uuid_module
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models.heartbeat_run import HeartbeatRun
from app.repositories.base import BaseRepository


def _utcnow() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(UTC)


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
        # Runtime hardening fields
        "process_pid",
        "process_started_at",
        "error_code",
        "log_store",
        "log_ref",
        "log_sha256",
        "log_bytes",
        "stdout_excerpt",
        "stderr_excerpt",
        "process_loss_retry_count",
        "retry_of_run_id",
        "invocation_source",
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

    # --- State transition helpers ---

    async def cancel(self, run: HeartbeatRun) -> HeartbeatRun:
        """Transition a run to cancelled status."""
        run.status = "cancelled"
        run.error_code = "cancelled"
        run.finished_at = _utcnow()
        await self._db.flush()
        await self._db.refresh(run)
        return run

    async def mark_timed_out(self, run: HeartbeatRun) -> HeartbeatRun:
        """Transition a run to timed_out status."""
        run.status = "timed_out"
        run.error_code = "timeout"
        run.finished_at = _utcnow()
        await self._db.flush()
        await self._db.refresh(run)
        return run

    async def mark_orphaned(self, run: HeartbeatRun) -> HeartbeatRun:
        """Mark a run as failed due to process loss."""
        run.status = "failed"
        run.error_code = "process_lost"
        run.finished_at = _utcnow()
        await self._db.flush()
        await self._db.refresh(run)
        return run

    async def list_running_with_pid(self) -> list[HeartbeatRun]:
        """Return all running HeartbeatRuns that have a process_pid set."""
        result = await self._db.execute(
            select(HeartbeatRun)
            .where(HeartbeatRun.status == "running")
            .where(HeartbeatRun.process_pid.isnot(None))
        )
        return list(result.scalars().all())
