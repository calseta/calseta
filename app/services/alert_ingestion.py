"""
AlertIngestionService — shared ingest pipeline for all alert sources.

Called by both the webhook route (POST /v1/ingest/{source_name}) and
the generic ingest route (POST /v1/alerts).

Pipeline (all synchronous within the request):
  1. Normalize raw payload → CalsetaAlert
  2. Extract indicators (Pass 1 + Pass 2) for fingerprinting
  3. Generate indicator-based fingerprint
  4. Check for duplicates within configured time window
  5. If duplicate: increment counter, write activity event, return early
  6. If new: persist alert, associate detection rule, enqueue enrichment,
     write alert_ingested activity event

Returns IngestResult with the alert and is_duplicate flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.alert import Alert
from app.integrations.sources.base import AlertSourceBase
from app.queue.base import TaskQueueBase
from app.repositories.alert_repository import AlertRepository, generate_fingerprint
from app.schemas.activity_events import ActivityEventType
from app.services.activity_event import ActivityEventService
from app.services.detection_rules import DetectionRuleService
from app.services.indicator_extraction import extract_for_fingerprint
from app.services.indicator_mapping_cache import get_normalized_mappings

logger = structlog.get_logger(__name__)


@dataclass
class IngestResult:
    alert: Alert
    is_duplicate: bool


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
    ) -> IngestResult:
        """
        Execute the full ingest pipeline.

        Args:
            source:           The source plugin (already validated).
            raw_payload:      The raw webhook/API payload.
            actor_type:       "api" or "system" (for activity log).
            actor_key_prefix: API key prefix (for activity log).

        Returns IngestResult with the alert and whether it was deduplicated.
        """
        # Step 1: Normalize
        normalized = source.normalize(raw_payload)

        # Step 2: Extract indicators for fingerprinting (Pass 1 + Pass 2, no persistence)
        cached_mappings = get_normalized_mappings(normalized.source_name)
        indicators = extract_for_fingerprint(
            source, normalized, raw_payload, cached_mappings
        )
        indicator_tuples = [(str(ind.type), ind.value.strip()) for ind in indicators]

        # Step 3: Generate indicator-based fingerprint
        fingerprint = generate_fingerprint(
            normalized.title, normalized.source_name, indicator_tuples
        )

        # Step 4: Check for duplicates within the configured time window
        dedup_hours = settings.ALERT_DEDUP_WINDOW_HOURS
        if dedup_hours > 0:
            window_start = datetime.now(UTC) - timedelta(hours=dedup_hours)
            existing = await self._alert_repo.find_duplicate(fingerprint, window_start)
            if existing is not None:
                updated = await self._alert_repo.increment_duplicate(existing)
                logger.info(
                    "alert_deduplicated",
                    original_uuid=str(updated.uuid),
                    duplicate_count=updated.duplicate_count,
                    source_name=normalized.source_name,
                    fingerprint=fingerprint,
                )
                await self._activity_service.write(
                    ActivityEventType.ALERT_DEDUPLICATED,
                    actor_type=actor_type,
                    actor_key_prefix=actor_key_prefix,
                    alert_id=updated.id,
                    references={
                        "fingerprint": fingerprint,
                        "duplicate_count": updated.duplicate_count,
                        "source_name": normalized.source_name,
                        "title": normalized.title,
                    },
                )
                return IngestResult(alert=updated, is_duplicate=True)

        # Step 5: Persist new alert
        alert = await self._alert_repo.create(
            normalized, raw_payload, fingerprint=fingerprint
        )
        logger.info(
            "alert_ingested",
            alert_uuid=str(alert.uuid),
            source_name=normalized.source_name,
            severity=normalized.severity,
            fingerprint=fingerprint,
        )

        # Step 6: Associate detection rule (best-effort)
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

        # Step 7: Enqueue enrichment (indicator extraction + provider enrichment)
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

        # Step 8: Activity event (fire-and-forget — never raises)
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

        return IngestResult(alert=alert, is_duplicate=False)
