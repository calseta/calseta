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
                    continue  # Don't also check budget if already timed out

                budget_stopped = await self._check_budget(
                    assignment=assignment,
                    agent=agent,
                    assign_repo=assign_repo,
                )
                if budget_stopped:
                    report.budget_stopped += 1
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

        # Phase 5: scan for timed-out invocations
        await self._scan_timed_out_invocations(now, report)

        logger.info(
            "supervisor.completed",
            checked=report.checked,
            timed_out=report.timed_out,
            budget_stopped=report.budget_stopped,
            errors=len(report.errors),
        )
        return report

    async def _scan_timed_out_invocations(
        self,
        now: datetime,
        report: SupervisionReport,
    ) -> None:
        """Mark running invocations whose deadline has passed as timed_out."""
        try:
            from app.repositories.agent_invocation_repository import AgentInvocationRepository
            from app.services.invocation_service import InvocationService

            inv_repo = AgentInvocationRepository(self._db)
            inv_svc = InvocationService(self._db)

            timed_out_candidates = await inv_repo.list_timed_out_candidates(cutoff=now)
            for invocation in timed_out_candidates:
                try:
                    await inv_svc.mark_timed_out(invocation)
                    report.timed_out += 1
                    logger.warning(
                        "supervisor.invocation_timed_out",
                        invocation_uuid=str(invocation.uuid),
                        started_at=invocation.started_at.isoformat()
                        if invocation.started_at
                        else None,
                        timeout_seconds=invocation.timeout_seconds,
                    )
                except Exception as exc:
                    report.errors.append(
                        f"Error marking invocation {invocation.id} timed_out: {exc}"
                    )
        except Exception as exc:
            logger.error(
                "supervisor.invocation_scan_failed",
                error=str(exc),
            )
            report.errors.append(f"Invocation scan error: {exc}")

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

    async def _check_budget(
        self,
        assignment: AlertAssignment,  # type: ignore[name-defined]  # noqa: F821
        agent: AgentRegistration,  # type: ignore[name-defined]  # noqa: F821
        assign_repo: AlertAssignmentRepository,  # type: ignore[name-defined]  # noqa: F821
    ) -> bool:
        """Check if this agent has exceeded its monthly budget. Returns True if stopped."""
        budget = agent.budget_monthly_cents
        if budget <= 0:
            return False

        spent = agent.spent_monthly_cents or 0
        if spent < budget:
            return False

        # Agent is over budget — pause if not already
        if agent.status in ("paused", "terminated"):
            return False

        logger.warning(
            "supervisor.budget_hard_stop",
            agent_id=agent.id,
            budget_monthly_cents=budget,
            spent_monthly_cents=spent,
            assignment_id=assignment.id,
        )

        agent.status = "paused"
        await self._db.flush()

        await assign_repo.release(assignment)

        # Log activity events
        try:
            await self._log_budget_stop_events(
                assignment=assignment,
                agent=agent,
                budget=budget,
                spent=spent,
            )
        except Exception as exc:
            logger.warning(
                "supervisor.budget_event_failed",
                assignment_id=assignment.id,
                error=str(exc),
            )

        return True

    async def _log_budget_stop_events(
        self,
        assignment: AlertAssignment,  # type: ignore[name-defined]  # noqa: F821
        agent: AgentRegistration,  # type: ignore[name-defined]  # noqa: F821
        budget: int,
        spent: int,
    ) -> None:
        """Emit cost.hard_stop and agent.budget_exceeded activity events."""
        import uuid as uuid_module

        from app.db.models.activity_event import ActivityEvent

        refs = {
            "agent_id": agent.id,
            "assignment_id": assignment.id,
            "budget_monthly_cents": budget,
            "spent_monthly_cents": spent,
        }
        for event_type in ("cost.hard_stop", "agent.budget_exceeded"):
            self._db.add(ActivityEvent(
                uuid=uuid_module.uuid4(),
                event_type=event_type,
                actor_type="system",
                actor_key_prefix=None,
                alert_id=assignment.alert_id,
                references=refs,
            ))
        await self._db.flush()

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
