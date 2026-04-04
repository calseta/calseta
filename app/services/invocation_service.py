"""InvocationService — orchestrator→specialist delegation logic.

Handles:
- Creating single and parallel invocations
- Enqueuing execution tasks
- Cost rollup from child to parent
- Timeout marking (called by supervisor)

Design:
- Service never executes specialists inline — always enqueues via task queue
- All DB mutations flush before enqueueing so tasks see committed state
- Cost roll-up: when invocation completes, child cost is added to parent agent spent_monthly_cents
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_invocation import AgentInvocation
from app.db.models.agent_registration import AgentRegistration
from app.repositories.agent_invocation_repository import AgentInvocationRepository
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent_invocations import (
    AgentCatalogEntry,
    DelegateParallelRequest,
    DelegateTaskRequest,
    DelegateTaskResponse,
    InvocationStatus,
)

logger = structlog.get_logger(__name__)


class InvocationService:
    """Business logic for multi-agent invocation delegation."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = AgentInvocationRepository(db)
        self._agent_repo = AgentRepository(db)

    # ----------------------------------------------------------------
    # Catalog
    # ----------------------------------------------------------------

    async def get_catalog(self) -> list[AgentCatalogEntry]:
        """Return all active specialist agents available for delegation."""
        from sqlalchemy import select

        result = await self._db.execute(
            select(AgentRegistration).where(
                AgentRegistration.status == "active",
                AgentRegistration.agent_type.in_(["specialist", "resolver"]),
            )
        )
        agents = list(result.scalars().all())
        return [AgentCatalogEntry.model_validate(a) for a in agents]

    # ----------------------------------------------------------------
    # Single delegation
    # ----------------------------------------------------------------

    async def delegate_task(
        self,
        orchestrator: AgentRegistration,
        request: DelegateTaskRequest,
        actor_key_prefix: str | None = None,
    ) -> DelegateTaskResponse:
        """Create a single invocation and enqueue the execution task.

        Raises CalsetaException on validation failures.
        """
        from fastapi import status as http_status

        from app.api.errors import CalsetaException

        # Verify orchestrator role
        if orchestrator.agent_type not in ("orchestrator",):
            raise CalsetaException(
                code="NOT_ORCHESTRATOR",
                message=(
                    f"Agent '{orchestrator.name}' is not an orchestrator "
                    f"(agent_type={orchestrator.agent_type}). "
                    "Only orchestrator agents may delegate tasks."
                ),
                status_code=http_status.HTTP_403_FORBIDDEN,
            )

        # Resolve alert
        from sqlalchemy import select

        from app.db.models.alert import Alert

        alert_result = await self._db.execute(
            select(Alert).where(Alert.uuid == request.alert_id)
        )
        alert = alert_result.scalar_one_or_none()
        if alert is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Alert not found: {request.alert_id}",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )

        # Resolve target specialist
        child_agent = await self._agent_repo.get_by_uuid(request.child_agent_id)
        if child_agent is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Specialist agent not found: {request.child_agent_id}",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )
        if child_agent.status != "active":
            raise CalsetaException(
                code="AGENT_NOT_AVAILABLE",
                message=(
                    f"Specialist '{child_agent.name}' is not active "
                    f"(status={child_agent.status})."
                ),
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Resolve optional assignment
        assignment_id: int | None = None
        if request.assignment_id is not None:
            from app.db.models.alert_assignment import AlertAssignment

            asgn_result = await self._db.execute(
                select(AlertAssignment).where(
                    AlertAssignment.uuid == request.assignment_id
                )
            )
            asgn = asgn_result.scalar_one_or_none()
            if asgn is None:
                raise CalsetaException(
                    code="NOT_FOUND",
                    message=f"Assignment not found: {request.assignment_id}",
                    status_code=http_status.HTTP_404_NOT_FOUND,
                )
            assignment_id = asgn.id

        invocation = await self._repo.create(
            parent_agent_id=orchestrator.id,
            alert_id=alert.id,
            task_description=request.task_description,
            child_agent_id=child_agent.id,
            assignment_id=assignment_id,
            input_context=request.input_context,
            output_schema=request.output_schema,
            timeout_seconds=request.timeout_seconds,
        )

        # Write audit event
        await self._write_activity(
            invocation=invocation,
            alert_id=alert.id,
            actor_key_prefix=actor_key_prefix,
            event="invocation.created",
        )

        # Enqueue execution
        await self._enqueue_invocation(invocation)

        logger.info(
            "invocation_delegated",
            invocation_uuid=str(invocation.uuid),
            parent_agent=orchestrator.name,
            child_agent=child_agent.name,
            alert_id=alert.id,
        )

        return DelegateTaskResponse(
            invocation_id=invocation.uuid,
            status=InvocationStatus.QUEUED,
            child_agent_id=child_agent.uuid,
        )

    # ----------------------------------------------------------------
    # Parallel delegation
    # ----------------------------------------------------------------

    async def delegate_parallel(
        self,
        orchestrator: AgentRegistration,
        request: DelegateParallelRequest,
        actor_key_prefix: str | None = None,
    ) -> list[DelegateTaskResponse]:
        """Create multiple invocations atomically and enqueue all tasks.

        All invocations are flushed before any task is enqueued,
        ensuring the task queue sees committed rows.
        """
        from fastapi import status as http_status
        from sqlalchemy import select

        from app.api.errors import CalsetaException
        from app.db.models.alert import Alert

        if orchestrator.agent_type not in ("orchestrator",):
            raise CalsetaException(
                code="NOT_ORCHESTRATOR",
                message=(
                    f"Agent '{orchestrator.name}' is not an orchestrator. "
                    "Only orchestrator agents may delegate tasks."
                ),
                status_code=http_status.HTTP_403_FORBIDDEN,
            )

        alert_result = await self._db.execute(
            select(Alert).where(Alert.uuid == request.alert_id)
        )
        alert = alert_result.scalar_one_or_none()
        if alert is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Alert not found: {request.alert_id}",
                status_code=http_status.HTTP_404_NOT_FOUND,
            )

        # Resolve optional assignment
        assignment_id: int | None = None
        if request.assignment_id is not None:
            from app.db.models.alert_assignment import AlertAssignment

            asgn_result = await self._db.execute(
                select(AlertAssignment).where(
                    AlertAssignment.uuid == request.assignment_id
                )
            )
            asgn = asgn_result.scalar_one_or_none()
            if asgn is None:
                raise CalsetaException(
                    code="NOT_FOUND",
                    message=f"Assignment not found: {request.assignment_id}",
                    status_code=http_status.HTTP_404_NOT_FOUND,
                )
            assignment_id = asgn.id

        # Resolve all specialists first (fail fast before creating any rows)
        resolved_children: list[AgentRegistration] = []
        for task in request.tasks:
            child = await self._agent_repo.get_by_uuid(task.child_agent_id)
            if child is None:
                raise CalsetaException(
                    code="NOT_FOUND",
                    message=f"Specialist agent not found: {task.child_agent_id}",
                    status_code=http_status.HTTP_404_NOT_FOUND,
                )
            if child.status != "active":
                raise CalsetaException(
                    code="AGENT_NOT_AVAILABLE",
                    message=(
                        f"Specialist '{child.name}' is not active "
                        f"(status={child.status})."
                    ),
                    status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            resolved_children.append(child)

        # Create all invocations atomically, then flush once
        invocations: list[AgentInvocation] = []
        for task, child in zip(request.tasks, resolved_children, strict=True):
            inv = AgentInvocation(
                parent_agent_id=orchestrator.id,
                child_agent_id=child.id,
                alert_id=alert.id,
                assignment_id=assignment_id,
                task_description=task.task_description,
                input_context=task.input_context,
                output_schema=task.output_schema,
                status="queued",
                timeout_seconds=task.timeout_seconds,
                cost_cents=0,
            )
            import uuid as _uuid

            inv.uuid = _uuid.uuid4()
            self._db.add(inv)
            invocations.append(inv)

        await self._db.flush()
        for inv in invocations:
            await self._db.refresh(inv)

        # Write audit events and enqueue all tasks
        for inv in invocations:
            await self._write_activity(
                invocation=inv,
                alert_id=alert.id,
                actor_key_prefix=actor_key_prefix,
                event="invocation.created",
            )
            await self._enqueue_invocation(inv)

        logger.info(
            "parallel_invocations_delegated",
            count=len(invocations),
            parent_agent=orchestrator.name,
            alert_id=alert.id,
        )

        return [
            DelegateTaskResponse(
                invocation_id=inv.uuid,
                status=InvocationStatus.QUEUED,
                child_agent_id=child.uuid,
            )
            for inv, child in zip(invocations, resolved_children, strict=True)
        ]

    # ----------------------------------------------------------------
    # Timeout marking (called by supervisor scan)
    # ----------------------------------------------------------------

    async def mark_timed_out(self, invocation: AgentInvocation) -> None:
        """Mark a running invocation as timed_out and write audit event."""
        await self._repo.update_status(
            invocation,
            "timed_out",
            error="Invocation exceeded timeout_seconds limit.",
        )
        await self._write_activity(
            invocation=invocation,
            alert_id=invocation.alert_id,
            actor_key_prefix=None,
            event="invocation.timed_out",
        )
        logger.warning(
            "invocation_timed_out",
            invocation_uuid=str(invocation.uuid),
            timeout_seconds=invocation.timeout_seconds,
        )

    # ----------------------------------------------------------------
    # Cost rollup
    # ----------------------------------------------------------------

    async def add_cost(
        self,
        invocation: AgentInvocation,
        cost_cents: int,
    ) -> None:
        """Accumulate child cost on invocation and roll up to parent agent budget."""
        invocation.cost_cents = (invocation.cost_cents or 0) + cost_cents
        await self._db.flush()

        # Roll up to parent agent spent_monthly_cents
        parent = await self._agent_repo.get_by_id(invocation.parent_agent_id)
        if parent is not None:
            parent.spent_monthly_cents = (parent.spent_monthly_cents or 0) + cost_cents
            await self._db.flush()

    # ----------------------------------------------------------------
    # Internal helpers
    # ----------------------------------------------------------------

    async def _enqueue_invocation(self, invocation: AgentInvocation) -> None:
        """Enqueue the invocation execution task via procrastinate."""
        try:
            from app.queue.registry import execute_invocation_task

            job_id = await execute_invocation_task.defer_async(
                invocation_id=invocation.id
            )
            if job_id is not None:
                await self._repo.update_status(
                    invocation,
                    "queued",
                    task_queue_id=str(job_id),
                )
        except Exception:
            # Enqueue failure is non-fatal — invocation stays queued for retry
            logger.exception(
                "invocation_enqueue_failed",
                invocation_uuid=str(invocation.uuid),
            )

    async def _write_activity(
        self,
        invocation: AgentInvocation,
        alert_id: int,
        actor_key_prefix: str | None,
        event: str,
    ) -> None:
        """Write an activity event for the invocation lifecycle."""
        try:
            from app.schemas.activity_events import ActivityEventType
            from app.services.activity_event import ActivityEventService

            event_map = {
                "invocation.created": ActivityEventType.INVOCATION_CREATED,
                "invocation.completed": ActivityEventType.INVOCATION_COMPLETED,
                "invocation.failed": ActivityEventType.INVOCATION_FAILED,
                "invocation.timed_out": ActivityEventType.INVOCATION_TIMED_OUT,
            }
            event_type = event_map.get(event)
            if event_type is None:
                return

            activity_svc = ActivityEventService(self._db)
            await activity_svc.write(
                event_type,
                actor_type="system",
                actor_key_prefix=actor_key_prefix,
                alert_id=alert_id,
                references={
                    "invocation_uuid": str(invocation.uuid),
                    "parent_agent_id": invocation.parent_agent_id,
                    "child_agent_id": invocation.child_agent_id,
                    "status": invocation.status,
                },
            )
        except Exception:
            logger.exception("invocation_activity_write_failed")
