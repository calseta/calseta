"""
ActivityEventService — fire-and-forget audit event writer.

Errors never propagate to callers. If the write fails, it is logged
and silently ignored — audit events must never break the main request flow.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.activity_event_repository import ActivityEventRepository
from app.schemas.activity_events import ActivityEventType

logger = structlog.get_logger(__name__)


class ActivityEventService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = ActivityEventRepository(db)

    async def write(
        self,
        event_type: ActivityEventType,
        *,
        actor_type: str,
        actor_key_prefix: str | None = None,
        alert_id: int | None = None,
        workflow_id: int | None = None,
        detection_rule_id: int | None = None,
        references: dict[str, Any] | None = None,
    ) -> None:
        """
        Append an activity event. Swallows all errors — never raises.

        Callers must NOT await this in a fire-and-forget pattern unless they
        are already inside an async context. Always await this method; it will
        simply log and return on failure rather than propagating.
        """
        try:
            await self._repo.create(
                event_type=event_type.value,
                actor_type=actor_type,
                actor_key_prefix=actor_key_prefix,
                alert_id=alert_id,
                workflow_id=workflow_id,
                detection_rule_id=detection_rule_id,
                references=references,
            )
        except Exception:
            logger.exception(
                "activity_event_write_failed",
                event_type=event_type.value,
                alert_id=alert_id,
            )
