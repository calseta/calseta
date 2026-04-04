"""AlertAssignment repository — atomic checkout and assignment management."""

from __future__ import annotations

import uuid as uuid_module
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.db.models.alert_assignment import AlertAssignment
from app.repositories.base import BaseRepository


class AlertAssignmentRepository(BaseRepository[AlertAssignment]):
    model = AlertAssignment

    async def create(self, alert_id: int, agent_id: int) -> AlertAssignment:
        """Create a new assignment (non-atomic; use atomic_checkout for race-safe checkout)."""
        assignment = AlertAssignment(
            uuid=uuid_module.uuid4(),
            alert_id=alert_id,
            agent_registration_id=agent_id,
            status="in_progress",
            checked_out_at=datetime.now(UTC),
        )
        self._db.add(assignment)
        await self._db.flush()
        await self._db.refresh(assignment)
        return assignment

    async def atomic_checkout(
        self, alert_id: int, agent_registration_id: int
    ) -> AlertAssignment | None:
        """Atomically check out an alert for an agent.

        Uses INSERT ... WHERE NOT EXISTS (atomic in PostgreSQL).
        Returns the assignment row on success, None if alert is already assigned.
        """
        from sqlalchemy import text

        new_uuid = uuid_module.uuid4()
        stmt = text("""
            INSERT INTO alert_assignments
                (uuid, alert_id, agent_registration_id, status, checked_out_at,
                 created_at, updated_at)
            SELECT :new_uuid, :alert_id, :agent_id, 'in_progress', now(), now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM alert_assignments
                WHERE alert_id = :alert_id
                  AND status NOT IN ('released', 'resolved')
            )
            RETURNING uuid
        """)
        result = await self._db.execute(
            stmt,
            {
                "new_uuid": new_uuid,
                "alert_id": alert_id,
                "agent_id": agent_registration_id,
            },
        )
        row = result.fetchone()
        if row is None:
            return None

        # Reload as ORM object
        assignment = await self.get_by_uuid(row.uuid)
        return assignment

    async def get_active_for_alert(self, alert_id: int) -> AlertAssignment | None:
        """Get the non-released, non-resolved assignment for an alert, if any."""
        result = await self._db.execute(
            select(AlertAssignment)
            .where(
                AlertAssignment.alert_id == alert_id,
                AlertAssignment.status.not_in(["released", "resolved"]),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def list_for_agent(
        self,
        agent_id: int,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AlertAssignment], int]:
        """Return (assignments, total) for the given agent, optionally filtered by status."""
        filters = [AlertAssignment.agent_registration_id == agent_id]
        if status is not None:
            filters.append(AlertAssignment.status == status)
        return await self.paginate(
            *filters,
            order_by=AlertAssignment.checked_out_at.desc(),
            page=page,
            page_size=page_size,
        )

    async def release(self, assignment: AlertAssignment) -> AlertAssignment:
        """Set status='released' and clear started_at."""
        assignment.status = "released"
        assignment.started_at = None
        await self._db.flush()
        await self._db.refresh(assignment)
        return assignment

    async def patch(self, assignment: AlertAssignment, **kwargs: object) -> AlertAssignment:
        """Apply partial updates to an assignment."""
        _UPDATABLE = frozenset(
            {"status", "resolution", "resolution_type", "investigation_state",
             "started_at", "completed_at"}
        )
        for key, value in kwargs.items():
            if key not in _UPDATABLE:
                raise ValueError(f"Field '{key}' is not updatable via patch")
            setattr(assignment, key, value)
        await self._db.flush()
        await self._db.refresh(assignment)
        return assignment

    async def get_by_uuid(self, uuid: UUID) -> AlertAssignment | None:
        """Fetch a single assignment by UUID."""
        result = await self._db.execute(
            select(AlertAssignment).where(AlertAssignment.uuid == uuid)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]
