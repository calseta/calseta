"""
Worker process entry point.

Imports the task registry to register all @app.task decorated functions,
then starts the procrastinate worker consuming from all four named queues:
  - enrichment  (alert enrichment pipeline)
  - dispatch    (trigger evaluation + webhook delivery)
  - workflows   (workflow execution)
  - default     (catch-all)

Concurrency is controlled by QUEUE_CONCURRENCY env var (default 10).
SIGTERM is handled by procrastinate — current job finishes, then exits.
"""

from __future__ import annotations

import asyncio
import sys

from app.logging_config import configure_logging

configure_logging("worker")

import structlog  # noqa: E402 (must be after configure_logging)

logger = structlog.get_logger(__name__)

WORKER_QUEUES = ["enrichment", "dispatch", "workflows", "default"]


async def _load_enrichment_registry() -> None:
    """Load enrichment providers from DB into the in-memory registry."""
    from app.db.session import AsyncSessionLocal
    from app.integrations.enrichment.registry import enrichment_registry

    try:
        async with AsyncSessionLocal() as db:
            await enrichment_registry.load_from_database(db)
    except Exception as exc:
        logger.warning(
            "enrichment_registry_load_skipped",
            error=str(exc),
            hint="Worker enrichment tasks will find zero providers.",
        )


async def main() -> None:
    """Start the Calseta worker process."""
    # Import registry to register all task decorators before worker starts.
    import app.queue.registry  # noqa: F401
    from app.queue.factory import get_queue_backend

    logger.info("calseta_worker_starting", queues=WORKER_QUEUES)

    try:
        backend = get_queue_backend()
    except ValueError as exc:
        logger.critical("worker_startup_failed", error=str(exc))
        sys.exit(1)

    # Load enrichment providers from DB so worker tasks can enrich indicators.
    await _load_enrichment_registry()

    logger.info("calseta_worker_ready", queues=WORKER_QUEUES)
    await backend.start_worker(queues=WORKER_QUEUES)


if __name__ == "__main__":
    asyncio.run(main())
