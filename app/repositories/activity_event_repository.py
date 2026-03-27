"""ActivityEvent repository — append-only audit log operations."""

from __future__ import annotations

from typing import Any

from app.db.models.activity_event import ActivityEvent
from app.repositories.base import BaseRepository


class ActivityEventRepository(BaseRepository[ActivityEvent]):
    model = ActivityEvent

    async def create(
        self,
        *,
        event_type: str,
        actor_type: str,
        actor_key_prefix: str | None = None,
        alert_id: int | None = None,
        workflow_id: int | None = None,
        detection_rule_id: int | None = None,
        references: dict[str, Any] | None = None,
    ) -> ActivityEvent:
        """Append a new event. This record is never modified after creation."""
        event = ActivityEvent(
            event_type=event_type,
            actor_type=actor_type,
            actor_key_prefix=actor_key_prefix,
            alert_id=alert_id,
            workflow_id=workflow_id,
            detection_rule_id=detection_rule_id,
            references=references,
        )
        self._db.add(event)
        await self._db.flush()
        return event

    async def list_for_alert(
        self,
        alert_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ActivityEvent], int]:
        """Return (events, total_count) for an alert, ordered newest-first."""
        return await self.paginate(
            ActivityEvent.alert_id == alert_id,
            order_by=ActivityEvent.created_at.desc(),
            page=page,
            page_size=page_size,
        )
