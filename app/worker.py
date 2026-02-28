"""
Worker process entry point.

Starts the procrastinate task queue worker. All async task handlers
(enrichment, dispatch, workflows) are registered via the queue registry
imported here. The worker subscribes to all four named queues:
  - enrichment
  - dispatch
  - workflows
  - default

Chunk 1.1: stub that starts cleanly. Task handlers registered in chunk 1.6.
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the Calseta worker process."""
    logger.info("Calseta worker starting...")
    # Task queue and handlers wired in chunk 1.6
    # Structlog configured in chunk 1.10
    logger.info("Calseta worker ready (stub — queue registration in chunk 1.6)")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
