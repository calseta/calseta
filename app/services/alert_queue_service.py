"""AlertQueueService — manages agent alert assignment queue with atomic checkout."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.errors import CalsetaException
from app.db.models.agent_registration import AgentRegistration
from app.db.models.alert import Alert
from app.db.models.alert_assignment import AlertAssignment
from app.repositories.alert_assignment_repository import AlertAssignmentRepository
from app.repositories.alert_repository import AlertRepository
from app.schemas.alert_assignments import AssignmentUpdate

logger = structlog.get_logger(__name__)


class AlertQueueService:
    """Manages the agent alert queue: queue view, checkout, release, assignment updates."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_queue(
        self,
        agent: AgentRegistration,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Alert], int]:
        """Get pending alerts matching agent's trigger filters.

        Returns only:
          - Enriched alerts (enrichment_status='Enriched')
          - Alerts with status 'Open' or 'Triaging'
          - Alerts with no active assignment (no non-released/resolved assignment)

        Filters on agent.trigger_on_sources and agent.trigger_on_severities if set.
        """
        from sqlalchemy import func

        # Subquery: alert IDs that already have an active assignment
        active_assignment_alert_ids = (
            select(AlertAssignment.alert_id)
            .where(AlertAssignment.status.not_in(["released", "resolved"]))
            .scalar_subquery()
        )

        stmt = select(Alert).options(selectinload(Alert.detection_rule)).where(
            Alert.enrichment_status == "Enriched",
            Alert.status.in_(["Open", "Triaging"]),
            Alert.id.not_in(active_assignment_alert_ids),
        )
        count_stmt = select(func.count()).select_from(Alert).where(
            Alert.enrichment_status == "Enriched",
            Alert.status.in_(["Open", "Triaging"]),
            Alert.id.not_in(active_assignment_alert_ids),
        )

        # Apply source filter if agent has trigger_on_sources configured
        sources = agent.trigger_on_sources or []
        if sources:
            stmt = stmt.where(Alert.source_name.in_(sources))
            count_stmt = count_stmt.where(Alert.source_name.in_(sources))

        # Apply severity filter if agent has trigger_on_severities configured
        severities = agent.trigger_on_severities or []
        if severities:
            stmt = stmt.where(Alert.severity.in_(severities))
            count_stmt = count_stmt.where(Alert.severity.in_(severities))

        total_result = await self._db.execute(count_stmt)
        total: int = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = stmt.order_by(Alert.occurred_at.desc()).offset(offset).limit(page_size)
        result = await self._db.execute(stmt)
        alerts = list(result.scalars().all())

        return alerts, total

    async def checkout(
        self,
        alert_uuid: UUID,
        agent: AgentRegistration,
    ) -> AlertAssignment:
        """Atomically check out an alert for the agent.

        Raises CalsetaException(409) if alert is already assigned to any agent.
        Raises CalsetaException(404) if the alert does not exist.
        """
        alert_repo = AlertRepository(self._db)
        alert = await alert_repo.get_by_uuid(alert_uuid)
        if alert is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Alert {alert_uuid} not found.",
                status_code=404,
            )

        assignment_repo = AlertAssignmentRepository(self._db)
        assignment = await assignment_repo.atomic_checkout(
            alert_id=alert.id,
            agent_registration_id=agent.id,
        )

        if assignment is None:
            raise CalsetaException(
                code="CONFLICT",
                message=(
                    f"Alert {alert_uuid} is already checked out by another agent. "
                    "Release the current assignment before checking out again."
                ),
                status_code=409,
            )

        logger.info(
            "alert_checked_out",
            alert_uuid=str(alert_uuid),
            agent_id=agent.id,
            assignment_uuid=str(assignment.uuid),
        )
        await self._db.commit()
        await self._db.refresh(assignment)
        return assignment

    async def release(
        self,
        alert_uuid: UUID,
        agent: AgentRegistration,
    ) -> AlertAssignment:
        """Release an assignment back to the queue.

        Only the assigned agent can release. Raises CalsetaException(403) if
        the assignment belongs to a different agent.
        Raises CalsetaException(404) if no active assignment exists.
        """
        alert_repo = AlertRepository(self._db)
        alert = await alert_repo.get_by_uuid(alert_uuid)
        if alert is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Alert {alert_uuid} not found.",
                status_code=404,
            )

        assignment_repo = AlertAssignmentRepository(self._db)
        assignment = await assignment_repo.get_active_for_alert(alert.id)
        if assignment is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"No active assignment found for alert {alert_uuid}.",
                status_code=404,
            )

        if assignment.agent_registration_id != agent.id:
            raise CalsetaException(
                code="FORBIDDEN",
                message="You can only release assignments that belong to your agent.",
                status_code=403,
            )

        released = await assignment_repo.release(assignment)
        logger.info(
            "alert_released",
            alert_uuid=str(alert_uuid),
            agent_id=agent.id,
            assignment_uuid=str(released.uuid),
        )
        await self._db.commit()
        await self._db.refresh(released)
        return released

    async def get_my_assignments(
        self,
        agent: AgentRegistration,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AlertAssignment], int]:
        """Return the agent's current assignments, optionally filtered by status."""
        repo = AlertAssignmentRepository(self._db)
        return await repo.list_for_agent(
            agent_id=agent.id,
            status=status,
            page=page,
            page_size=page_size,
        )

    async def update_assignment(
        self,
        assignment_uuid: UUID,
        agent: AgentRegistration,
        data: AssignmentUpdate,
    ) -> AlertAssignment:
        """Update assignment status/resolution/investigation_state.

        Only the owning agent can update its assignment.
        Raises CalsetaException(404) if not found.
        Raises CalsetaException(403) if owned by a different agent.
        """
        from datetime import UTC, datetime

        repo = AlertAssignmentRepository(self._db)
        assignment = await repo.get_by_uuid(assignment_uuid)
        if assignment is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Assignment {assignment_uuid} not found.",
                status_code=404,
            )

        if assignment.agent_registration_id != agent.id:
            raise CalsetaException(
                code="FORBIDDEN",
                message="You can only update assignments that belong to your agent.",
                status_code=403,
            )

        updates: dict[str, Any] = {}
        if data.status is not None:
            updates["status"] = data.status.value
            # Set completed_at on terminal transitions
            if data.status.value in ("resolved", "escalated"):
                updates["completed_at"] = datetime.now(UTC)
            # Set started_at on first in_progress transition
            if data.status.value == "in_progress" and assignment.started_at is None:
                updates["started_at"] = datetime.now(UTC)
        if data.resolution is not None:
            updates["resolution"] = data.resolution
        if data.resolution_type is not None:
            updates["resolution_type"] = data.resolution_type
        if data.investigation_state is not None:
            updates["investigation_state"] = data.investigation_state

        updated = await repo.patch(assignment, **updates)
        await self._db.commit()
        await self._db.refresh(updated)
        return updated

    async def get_dashboard_data(self) -> dict[str, Any]:
        """Aggregate control plane dashboard data.

        Returns:
          - agent counts by status
          - queue depths by alert status
          - costs MTD (month-to-date)
        """
        from datetime import UTC, datetime

        from sqlalchemy import func

        from app.db.models.agent_registration import AgentRegistration
        from app.db.models.cost_event import CostEvent

        # Agent counts by status
        agent_status_result = await self._db.execute(
            select(
                AgentRegistration.status,
                func.count(AgentRegistration.id).label("count"),
            ).group_by(AgentRegistration.status)
        )
        agent_counts: dict[str, int] = {
            row.status: row._mapping["count"] for row in agent_status_result  # type: ignore[misc]
        }

        # Queue depth: alerts available (enriched, open/triaging, unassigned)
        active_assignment_alert_ids = (
            select(AlertAssignment.alert_id)
            .where(AlertAssignment.status.not_in(["released", "resolved"]))
            .scalar_subquery()
        )
        queue_count_result = await self._db.execute(
            select(func.count()).select_from(Alert).where(
                Alert.enrichment_status == "Enriched",
                Alert.status.in_(["Open", "Triaging"]),
                Alert.id.not_in(active_assignment_alert_ids),
            )
        )
        queue_depth = queue_count_result.scalar_one()

        # Active assignments by status
        assignment_status_result = await self._db.execute(
            select(
                AlertAssignment.status,
                func.count(AlertAssignment.id).label("count"),
            )
            .where(AlertAssignment.status.not_in(["released", "resolved"]))
            .group_by(AlertAssignment.status)
        )
        assignment_counts: dict[str, int] = {
            row.status: row._mapping["count"] for row in assignment_status_result  # type: ignore[misc]
        }

        # Costs MTD
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        costs_result = await self._db.execute(
            select(func.sum(CostEvent.cost_cents)).where(
                CostEvent.occurred_at >= month_start,
            )
        )
        total_cost_cents_mtd: int = costs_result.scalar_one() or 0

        return {
            "agents": {
                "by_status": agent_counts,
                "total": sum(agent_counts.values()),
            },
            "queue": {
                "available": queue_depth,
                "active_by_status": assignment_counts,
            },
            "costs_mtd": {
                "total_cents": total_cost_cents_mtd,
                "total_usd": round(total_cost_cents_mtd / 100, 2),
                "period_start": month_start.isoformat(),
            },
        }
