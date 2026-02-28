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
Structlog configured in chunk 1.10.
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

WORKER_QUEUES = ["enrichment", "dispatch", "workflows", "default"]


async def main() -> None:
    """Start the Calseta worker process."""
    # Import registry to register all task decorators before worker starts.
    import app.queue.registry  # noqa: F401
    from app.queue.factory import get_queue_backend

    logger.info("Calseta worker starting on queues: %s", WORKER_QUEUES)

    try:
        backend = get_queue_backend()
    except ValueError as exc:
        logger.critical("Worker startup failed — invalid queue config: %s", exc)
        sys.exit(1)

    logger.info("Calseta worker ready, consuming from %s", WORKER_QUEUES)
    await backend.start_worker(queues=WORKER_QUEUES)


if __name__ == "__main__":
    asyncio.run(main())
