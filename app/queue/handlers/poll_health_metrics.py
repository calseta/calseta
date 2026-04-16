"""Handler for the health metric polling periodic task."""

from __future__ import annotations

import structlog

from app.queue.handlers.base import task_session
from app.services.health_service import HealthService

logger = structlog.get_logger(__name__)


async def handle_poll_health_metrics() -> None:
    """Poll all active health sources and persist metric datapoints."""
    async with task_session() as db:
        svc = HealthService(db)
        summary = await svc.poll_all_sources()
        logger.info(
            "poll_health_metrics.completed",
            **summary,
        )
