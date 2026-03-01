"""
Task registry — all procrastinate @procrastinate_app.task decorated functions.

This module owns the single module-level procrastinate.App instance
(`procrastinate_app`). The ProcrastinateBackend in app/queue/backends/postgres.py
imports and reuses this instance so that task registrations made here are
visible when tasks are enqueued.

This module is imported by:
  - app/worker.py            → ensures tasks are registered before worker starts
  - app/main.py (startup)    → ensures tasks are registered before API accepts requests
  - app/queue/backends/postgres.py → ProcrastinateBackend uses the shared app

Task naming:
  Always pass `name=` explicitly so the task lookup key is stable and does not
  depend on the Python function's qualified name.

Registered tasks:
  Wave 3: enrich_alert          (queue: enrichment)
  Wave 4: execute_workflow      (queue: workflows)       ← added in Wave 4
  Wave 4: deliver_agent_webhook (queue: dispatch)        ← added in Wave 4
"""

from __future__ import annotations

import procrastinate

from app.config import settings


def _to_pg_dsn(url: str) -> str:
    """Convert SQLAlchemy DSN to plain libpq DSN for procrastinate."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


# ---------------------------------------------------------------------------
# Module-level procrastinate App — shared by all task registrations and
# ProcrastinateBackend. Tasks registered here are visible to the backend.
# ---------------------------------------------------------------------------
_connector = procrastinate.PsycopgConnector(conninfo=_to_pg_dsn(settings.DATABASE_URL))
procrastinate_app = procrastinate.App(connector=_connector)


# ---------------------------------------------------------------------------
# Wave 3: Alert enrichment task
# ---------------------------------------------------------------------------

@procrastinate_app.task(
    name="enrich_alert",
    queue="enrichment",
    retry=procrastinate.RetryStrategy(
        max_attempts=settings.QUEUE_MAX_RETRIES,
        wait=settings.QUEUE_RETRY_BACKOFF_SECONDS,
    ),
)
async def enrich_alert_task(alert_id: int) -> None:
    """
    Run the enrichment pipeline for all indicators of an alert.

    Idempotent: re-running after success updates last_seen on indicators and
    refreshes enrichment results; no duplicate records are created.
    """
    from app.cache.factory import get_cache_backend
    from app.db.session import AsyncSessionLocal
    from app.services.enrichment import EnrichmentService

    cache = get_cache_backend()
    async with AsyncSessionLocal() as session:
        try:
            service = EnrichmentService(session, cache)
            await service.enrich_alert(alert_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
