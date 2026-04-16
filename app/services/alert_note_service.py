"""
AlertNoteService — add analyst/agent notes to alerts and optionally wake
the assigned agent via a comment-driven heartbeat run.

Notes are stored as activity events (type=alert_note_added). No new DB
columns or tables required.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.activity_event import ActivityEvent
from app.queue.base import TaskQueueBase
from app.repositories.activity_event_repository import ActivityEventRepository
from app.repositories.alert_assignment_repository import AlertAssignmentRepository
from app.repositories.heartbeat_run_repository import HeartbeatRunRepository
from app.schemas.activity_events import ActivityEventType

logger = structlog.get_logger(__name__)

# Rate limit: at most one agent trigger per alert every 5 minutes
_TRIGGER_COOLDOWN = timedelta(minutes=5)

# Consider assignments "recent" if checked out within the last hour
_ASSIGNMENT_RECENCY = timedelta(hours=1)


class AlertNoteService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._activity_repo = ActivityEventRepository(db)
        self._assignment_repo = AlertAssignmentRepository(db)
        self._heartbeat_repo = HeartbeatRunRepository(db)

    async def add_note(
        self,
        alert_id: int,
        content: str,
        trigger_agent: bool,
        actor_type: str,
        actor_key_prefix: str | None,
        queue: TaskQueueBase | None = None,
    ) -> dict[str, Any]:
        """Add a note to an alert and optionally trigger the assigned agent.

        Returns dict with ``note_id`` (activity event UUID) and ``agent_triggered`` (bool).
        """
        agent_triggered = False

        # Store the note as an activity event
        references: dict[str, Any] = {
            "content": content,
            "trigger_agent": trigger_agent,
        }
        event = await self._activity_repo.create(
            event_type=ActivityEventType.ALERT_NOTE_ADDED.value,
            actor_type=actor_type,
            actor_key_prefix=actor_key_prefix,
            alert_id=alert_id,
            references=references,
        )

        if trigger_agent and queue is not None:
            agent_triggered = await self._try_trigger_agent(
                alert_id=alert_id,
                content=content,
                actor_key_prefix=actor_key_prefix,
                queue=queue,
            )

        return {
            "note_id": str(event.uuid),
            "agent_triggered": agent_triggered,
        }

    async def _try_trigger_agent(
        self,
        alert_id: int,
        content: str,
        actor_key_prefix: str | None,
        queue: TaskQueueBase,
    ) -> bool:
        """Attempt to wake the assigned agent. Returns True if a run was enqueued."""

        # Rate limit: check for recent trigger_agent=True notes on this alert
        cutoff = datetime.now(UTC) - _TRIGGER_COOLDOWN
        result = await self._db.execute(
            select(ActivityEvent.id)
            .where(
                ActivityEvent.alert_id == alert_id,
                ActivityEvent.event_type == ActivityEventType.ALERT_NOTE_ADDED.value,
                ActivityEvent.created_at >= cutoff,
                ActivityEvent.references["trigger_agent"].as_boolean() == True,  # noqa: E712
            )
            .limit(2)  # We only need to know if >1 exists (current + previous)
        )
        recent_triggers = result.scalars().all()
        # The note we just wrote is already flushed, so if there are 2+
        # that means at least one prior trigger exists within the cooldown window
        if len(recent_triggers) > 1:
            logger.info(
                "alert_note_service.trigger_rate_limited",
                alert_id=alert_id,
            )
            return False

        # Find active assignment for this alert
        assignment = await self._assignment_repo.get_active_for_alert(alert_id)

        # If no active assignment, check for a recently checked-out one
        if assignment is None:
            recency_cutoff = datetime.now(UTC) - _ASSIGNMENT_RECENCY
            from app.db.models.alert_assignment import AlertAssignment

            recent_result = await self._db.execute(
                select(AlertAssignment)
                .where(
                    AlertAssignment.alert_id == alert_id,
                    AlertAssignment.checked_out_at >= recency_cutoff,
                )
                .order_by(AlertAssignment.checked_out_at.desc())
                .limit(1)
            )
            assignment = recent_result.scalar_one_or_none()

        if assignment is None:
            logger.info(
                "alert_note_service.no_assignment_found",
                alert_id=alert_id,
            )
            return False

        # Create a heartbeat run with invocation_source='comment'
        now = datetime.now(UTC)
        run = await self._heartbeat_repo.create(
            agent_id=assignment.agent_registration_id,
            source="comment",
        )
        # Set invocation_source and context_snapshot
        await self._heartbeat_repo.update_status(
            run,
            "queued",
            invocation_source="comment",
            context_snapshot={
                "wake_comments": [
                    {
                        "content": content,
                        "author": actor_key_prefix,
                        "timestamp": now.isoformat(),
                    }
                ],
                "alert_id": alert_id,
            },
        )

        # Enqueue the managed agent task
        try:
            await queue.enqueue(
                "run_managed_agent_task",
                {
                    "agent_registration_id": assignment.agent_registration_id,
                    "assignment_id": assignment.id,
                    "heartbeat_run_id": run.id,
                },
                queue="agents",
                delay_seconds=0,
                priority=0,
            )
        except Exception:
            logger.exception(
                "alert_note_service.enqueue_failed",
                alert_id=alert_id,
                heartbeat_run_id=run.id,
            )
            return False

        logger.info(
            "alert_note_service.agent_triggered",
            alert_id=alert_id,
            agent_registration_id=assignment.agent_registration_id,
            heartbeat_run_id=run.id,
        )
        return True
