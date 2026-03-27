"""Handler for the enrich_alert task."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.factory import get_cache_backend
from app.integrations.sources.registry import source_registry
from app.queue.handlers.payloads import EnrichAlertPayload
from app.repositories.alert_repository import AlertRepository
from app.services.enrichment import EnrichmentService
from app.services.indicator_extraction import IndicatorExtractionService

logger = structlog.get_logger()


class EnrichAlertHandler:
    """Run indicator extraction + enrichment pipeline for an alert.

    Steps:
      1. Load the alert and its source plugin
      2. Extract indicators via 3-pass pipeline (IndicatorExtractionService)
      3. Enrich all extracted indicators via configured providers
      4. Defer agent dispatch task (best-effort)

    Idempotent: re-running after success updates last_seen on indicators and
    refreshes enrichment results; no duplicate records are created.
    """

    async def execute(self, payload: EnrichAlertPayload, session: AsyncSession) -> None:
        alert_id = payload.alert_id
        alert_repo = AlertRepository(session)
        alert = await alert_repo.get_by_id(alert_id)
        if alert is None:
            logger.error("enrich_alert_not_found", alert_id=alert_id)
            return

        # Step 1: Extract indicators (3-pass pipeline)
        source = source_registry.get(alert.source_name)
        if source is not None and alert.raw_payload:
            try:
                normalized = source.normalize(alert.raw_payload)
                extraction_svc = IndicatorExtractionService(session)
                count = await extraction_svc.extract_and_persist(
                    alert, normalized, alert.raw_payload, source
                )
                logger.info(
                    "indicators_extracted",
                    alert_id=alert_id,
                    indicator_count=count,
                )
            except Exception:
                logger.exception(
                    "indicator_extraction_failed", alert_id=alert_id
                )
            await session.flush()

        # Step 2: Enrich all indicators
        cache = get_cache_backend()
        enrichment_svc = EnrichmentService(session, cache)
        try:
            await enrichment_svc.enrich_alert(alert_id)
        except Exception:
            logger.exception("enrich_alert_task_failed", alert_id=alert_id)
            # Mark enrichment as failed so status doesn't stay stuck
            try:
                alert = await alert_repo.get_by_id(alert_id)
                if alert is not None:
                    await alert_repo.mark_enrichment_failed(alert)
            except Exception:
                logger.exception(
                    "mark_enrichment_failed_error", alert_id=alert_id
                )
