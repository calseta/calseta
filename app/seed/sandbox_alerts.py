"""
Seed sandbox alerts — ingest 5 case study fixtures and enrich them inline.

Uses AlertIngestionService with a _NoOpQueue so enrichment is NOT enqueued
asynchronously. Instead, enrichment is run inline after ingestion.

Idempotent: the fingerprint-based dedup in AlertIngestionService handles
re-runs. Alerts that already exist are skipped via the dedup window.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.factory import get_cache_backend
from app.db.models.alert import Alert
from app.integrations.sources.registry import source_registry
from app.queue.base import TaskQueueBase, TaskStatus
from app.services.alert_ingestion import AlertIngestionService
from app.services.enrichment import EnrichmentService
from app.services.indicator_extraction import IndicatorExtractionService

logger = structlog.get_logger(__name__)

_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "examples"
    / "case_study"
    / "fixtures"
)

# Fixture filename → source_name mapping
_FIXTURE_SOURCES: list[tuple[str, str]] = [
    ("01_sentinel_brute_force_tor.json", "sentinel"),
    ("02_elastic_malware_hash.json", "elastic"),
    ("03_splunk_anomalous_data_transfer.json", "splunk"),
    ("04_sentinel_impossible_travel.json", "sentinel"),
    ("05_elastic_suspicious_powershell.json", "elastic"),
]


class _NoOpQueue(TaskQueueBase):
    """Queue that silently discards enqueue requests — used during seed to skip async tasks."""

    async def enqueue(
        self,
        task_name: str,
        payload: dict[str, object],
        *,
        queue: str,
        delay_seconds: int = 0,
        priority: int = 0,
    ) -> str:
        return "noop-task-id"

    async def get_task_status(self, task_id: str) -> TaskStatus:
        return TaskStatus.SUCCESS

    async def start_worker(self, queues: list[str]) -> None:
        pass


async def seed_sandbox_alerts(db: AsyncSession) -> list[Alert]:
    """
    Ingest fixture alerts and enrich them inline.

    Steps per fixture:
      1. Load JSON from examples/case_study/fixtures/
      2. Ingest via AlertIngestionService (with _NoOpQueue to skip async enrichment)
      3. Mark the alert as is_system=True
      4. Extract indicators (via IndicatorExtractionService)
      5. Run enrichment inline (via EnrichmentService.enrich_alert)

    Returns the list of newly created alerts (skips duplicates).
    """
    noop_queue = _NoOpQueue()
    cache = get_cache_backend()
    ingestion_svc = AlertIngestionService(db, noop_queue)
    enrichment_svc = EnrichmentService(db, cache)
    created: list[Alert] = []

    for filename, source_name in _FIXTURE_SOURCES:
        fixture_path = _FIXTURES_DIR / filename
        if not fixture_path.exists():
            logger.warning("sandbox_fixture_missing", filename=filename)
            continue

        raw_payload = json.loads(fixture_path.read_text())
        source = source_registry.get(source_name)
        if source is None:
            logger.warning("sandbox_source_not_found", source_name=source_name)
            continue

        try:
            result = await ingestion_svc.ingest(
                source, raw_payload, actor_type="system"
            )

            if result.is_duplicate:
                logger.info(
                    "sandbox_alert_duplicate_skipped",
                    filename=filename,
                    alert_uuid=str(result.alert.uuid),
                )
                continue

            alert = result.alert
            alert.is_system = True
            await db.flush()

            # Extract indicators (3-pass pipeline)
            try:
                normalized = source.normalize(raw_payload)
                extraction_svc = IndicatorExtractionService(db)
                await extraction_svc.extract_and_persist(
                    alert, normalized, raw_payload, source
                )
                await db.flush()
            except Exception:
                logger.exception(
                    "sandbox_indicator_extraction_failed",
                    filename=filename,
                    alert_uuid=str(alert.uuid),
                )

            # Enrich all indicators inline
            try:
                await enrichment_svc.enrich_alert(alert.id)
            except Exception:
                logger.exception(
                    "sandbox_enrichment_failed",
                    filename=filename,
                    alert_uuid=str(alert.uuid),
                )

            created.append(alert)
            logger.info(
                "sandbox_alert_seeded",
                filename=filename,
                alert_uuid=str(alert.uuid),
                is_enriched=alert.is_enriched,
            )

        except Exception:
            logger.exception("sandbox_alert_ingest_failed", filename=filename)

    if created:
        logger.info("sandbox_alerts_seeded", count=len(created))

    return created
