"""HeartbeatService — records agent heartbeats and returns supervisor directives."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import AgentRegistration
from app.repositories.heartbeat_run_repository import HeartbeatRunRepository

logger = structlog.get_logger(__name__)


class HeartbeatService:
    """Records agent heartbeats and exposes supervisor directives."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record_heartbeat(
        self,
        agent: AgentRegistration,
        request: object,  # HeartbeatRequest — imported inline to avoid circular import
    ) -> tuple[object, str | None]:
        """Record a heartbeat for the agent and return (run, supervisor_directive).

        Steps:
          1. Create a HeartbeatRun row for this invocation.
          2. Update agent.last_heartbeat_at to now.
          3. Derive supervisor_directive from current agent status.
          4. Return (run, directive).

        Directive values:
          - None      — no directive; agent may continue
          - "pause"   — agent should pause after current task
          - "terminate" — agent should terminate immediately
        """
        from app.schemas.heartbeat import HeartbeatRequest

        req: HeartbeatRequest = request  # type: ignore[assignment]

        repo = HeartbeatRunRepository(self._db)

        # Create heartbeat run — source defaults to "manual" for API-triggered heartbeats
        run = await repo.create(agent_id=agent.id, source="manual")

        # Transition run to running/completed based on request status
        now = datetime.now(UTC)
        status_map = {
            "running": "running",
            "idle": "running",
            "completed": "succeeded",
            "error": "failed",
        }
        run_status = status_map.get(req.status, "running")

        updates: dict[str, object] = {
            "started_at": now,
            "actions_proposed": req.actions_proposed,
        }
        if run_status in ("succeeded", "failed"):
            updates["finished_at"] = now
        if req.progress_note and run_status == "failed":
            updates["error"] = req.progress_note

        run = await repo.update_status(run, run_status, **updates)

        # Update agent.last_heartbeat_at
        agent.last_heartbeat_at = now
        await self._db.flush()
        await self._db.refresh(agent)

        # Derive supervisor directive
        directive: str | None = None
        if agent.status == "paused":
            directive = "pause"
        elif agent.status == "terminated":
            directive = "terminate"

        logger.info(
            "heartbeat_recorded",
            agent_id=agent.id,
            agent_status=agent.status,
            run_uuid=str(run.uuid),
            request_status=req.status,
            directive=directive,
        )

        await self._db.commit()
        await self._db.refresh(run)
        return run, directive
