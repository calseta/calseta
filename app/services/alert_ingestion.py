"""
AlertIngestionService — shared ingest pipeline for all alert sources.

Called by both the webhook route (POST /v1/ingest/{source_name}) and
the generic ingest route (POST /v1/alerts).

Pipeline (all synchronous within the request):
  1. Normalize raw payload → CalsetaAlert
  2. Persist alert to DB
  3. Associate detection rule (if source provides one)
  4. Enqueue enrichment task (async worker handles indicator extraction + enrichment)
  5. Write alert_ingested activity event (fire-and-forget)

Returns 202 Accepted immediately after enqueue.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.integrations.sources.base import AlertSourceBase
from app.queue.base import TaskQueueBase
from app.repositories.alert_repository import AlertRepository
from app.schemas.activity_events import ActivityEventType
from app.services.activity_event import ActivityEventService
from app.services.detection_rules import DetectionRuleService

logger = structlog.get_logger(__name__)


class AlertIngestionService:
    def __init__(self, db: AsyncSession, queue: TaskQueueBase) -> None:
        self._db = db
        self._queue = queue
        self._alert_repo = AlertRepository(db)
        self._rule_service = DetectionRuleService(db)
        self._activity_service = ActivityEventService(db)

    async def ingest(
        self,
        source: AlertSourceBase,
        raw_payload: dict[str, Any],
        *,
        actor_type: str = "api",
        actor_key_prefix: str | None = None,
    ) -> Alert:
        """
        Execute the full ingest pipeline.

        Args:
            source:           The source plugin (already validated).
            raw_payload:      The raw webhook/API payload.
            actor_type:       "api" or "system" (for activity log).
            actor_key_prefix: API key prefix (for activity log).

        Returns the created Alert row (with id and uuid populated).
        """
        # Step 1: Normalize
        normalized = source.normalize(raw_payload)

        # Step 2: Persist alert
        alert = await self._alert_repo.create(normalized, raw_payload)
        logger.info(
            "alert_ingested",
            alert_uuid=str(alert.uuid),
            source_name=normalized.source_name,
            severity=normalized.severity,
        )

        # Step 3: Associate detection rule (best-effort)
        rule_ref = source.extract_detection_rule_ref(raw_payload)
        if rule_ref:
            try:
                await self._rule_service.associate_detection_rule(
                    alert,
                    source_name=normalized.source_name,
                    source_rule_id=rule_ref,
                )
            except Exception:
                logger.exception(
                    "detection_rule_association_failed",
                    alert_uuid=str(alert.uuid),
                    rule_ref=rule_ref,
                )

        # Step 4: Enqueue enrichment (indicator extraction + provider enrichment)
        try:
            task_id = await self._queue.enqueue(
                "enrich_alert",
                {"alert_id": alert.id},
                queue="enrichment",
            )
            logger.debug(
                "enrichment_task_enqueued",
                alert_uuid=str(alert.uuid),
                task_id=task_id,
            )
        except Exception:
            logger.exception(
                "enrichment_enqueue_failed",
                alert_uuid=str(alert.uuid),
            )

        # Step 5: Activity event (fire-and-forget — never raises)
        await self._activity_service.write(
            ActivityEventType.ALERT_INGESTED,
            actor_type=actor_type,
            actor_key_prefix=actor_key_prefix,
            alert_id=alert.id,
            references={
                "source_name": normalized.source_name,
                "severity": normalized.severity,
                "title": normalized.title,
            },
        )

        return alert
