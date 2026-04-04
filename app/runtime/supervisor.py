"""AgentSupervisor — periodic deterministic supervision of running managed agents.

Called by supervise_running_agents_task (procrastinate periodic task).
Checks all in-progress assignments for: stuck agents (timeout), budget breach.
Never makes LLM calls. All decisions are deterministic rules against DB state.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.runtime.models import SupervisionReport

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class AgentSupervisor:
    """Periodic supervision loop for managed agents."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def supervise(self) -> SupervisionReport:
        """Check all active assignments and enforce timeout/budget rules.

        Steps:
        1. Find all alert_assignments with status='in_progress'
        2. For each: load the agent and check timeout against last_heartbeat_at
        3. If stuck (elapsed > agent.timeout_seconds): release assignment + log
        4. Return supervision summary
        """
        from sqlalchemy import select

        from app.db.models.agent_registration import AgentRegistration
        from app.db.models.alert_assignment import AlertAssignment
        from app.repositories.alert_assignment_repository import AlertAssignmentRepository

        report = SupervisionReport()
        now = datetime.now(UTC)

        # Load all in-progress assignments
        result = await self._db.execute(
            select(AlertAssignment).where(
                AlertAssignment.status == "in_progress",
            )
        )
        assignments = list(result.scalars().all())
        report.checked = len(assignments)

        if not assignments:
            return report

        # Load agents for these assignments in bulk
        agent_ids = {a.agent_registration_id for a in assignments}
        agents_result = await self._db.execute(
            select(AgentRegistration).where(
                AgentRegistration.id.in_(agent_ids)
            )
        )
        agents_by_id: dict[int, AgentRegistration] = {
            a.id: a for a in agents_result.scalars().all()
        }

        assign_repo = AlertAssignmentRepository(self._db)

        for assignment in assignments:
            agent = agents_by_id.get(assignment.agent_registration_id)
            if agent is None:
                continue

            # Only supervise managed agents
            if agent.execution_mode != "managed":
                continue

            try:
                timed_out = await self._check_timeout(
                    assignment=assignment,
                    agent=agent,
                    now=now,
                    assign_repo=assign_repo,
                )
                if timed_out:
                    report.timed_out += 1
            except Exception as exc:
                error_msg = (
                    f"Error supervising assignment {assignment.id}: {exc}"
                )
                logger.error(
                    "supervisor.check_error",
                    assignment_id=assignment.id,
                    error=str(exc),
                )
                report.errors.append(error_msg)

        logger.info(
            "supervisor.completed",
            checked=report.checked,
            timed_out=report.timed_out,
            errors=len(report.errors),
        )
        return report

    async def _check_timeout(
        self,
        assignment: AlertAssignment,  # type: ignore[name-defined]  # noqa: F821
        agent: AgentRegistration,  # type: ignore[name-defined]  # noqa: F821
        now: datetime,
        assign_repo: AlertAssignmentRepository,  # type: ignore[name-defined]  # noqa: F821
    ) -> bool:
        """Check if this assignment has timed out. Returns True if released."""
        timeout_seconds = agent.timeout_seconds
        if timeout_seconds <= 0:
            return False

        # Use last_heartbeat_at if available, otherwise fall back to checked_out_at
        reference_time = agent.last_heartbeat_at or assignment.checked_out_at

        elapsed_seconds = (now - reference_time).total_seconds()
        if elapsed_seconds <= timeout_seconds:
            return False

        # Agent has exceeded timeout — release the assignment
        logger.warning(
            "supervisor.timeout_detected",
            assignment_id=assignment.id,
            agent_id=agent.id,
            elapsed_seconds=elapsed_seconds,
            timeout_seconds=timeout_seconds,
        )

        await assign_repo.release(assignment)

        # Log activity event
        try:
            await self._log_timeout_event(
                assignment=assignment,
                agent=agent,
                elapsed_seconds=elapsed_seconds,
            )
        except Exception as exc:
            logger.warning(
                "supervisor.activity_log_failed",
                assignment_id=assignment.id,
                error=str(exc),
            )

        return True

    async def _log_timeout_event(
        self,
        assignment: AlertAssignment,  # type: ignore[name-defined]  # noqa: F821
        agent: AgentRegistration,  # type: ignore[name-defined]  # noqa: F821
        elapsed_seconds: float,
    ) -> None:
        """Append an activity event recording the timeout."""
        import uuid as uuid_module

        from app.db.models.activity_event import ActivityEvent

        event = ActivityEvent(
            uuid=uuid_module.uuid4(),
            event_type="heartbeat.timed_out",
            actor_type="system",
            actor_key_prefix=None,
            alert_id=assignment.alert_id,
            references={
                "agent_id": agent.id,
                "assignment_id": assignment.id,
                "elapsed_seconds": elapsed_seconds,
                "timeout_seconds": agent.timeout_seconds,
            },
        )
        self._db.add(event)
        await self._db.flush()
