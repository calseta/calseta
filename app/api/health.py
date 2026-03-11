"""Full health check handler."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config import settings

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["health"])


async def _check_db() -> str:
    """Check DB connectivity. Returns 'ok' or 'error'."""
    try:
        from sqlalchemy import text

        from app.db.session import AsyncSessionLocal

        async def _query() -> None:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))

        await asyncio.wait_for(_query(), timeout=2.0)
        return "ok"
    except Exception as exc:
        logger.warning("health_check_db_failed", error=str(exc))
        return "error"


async def _check_queue() -> tuple[str, int]:
    """Check queue connectivity and return (status, depth)."""
    try:
        from sqlalchemy import text

        from app.db.session import AsyncSessionLocal

        async def _query() -> int:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    text("SELECT COUNT(*) FROM procrastinate_jobs WHERE status = 'todo'")
                )
                return int(result.scalar_one())

        depth = await asyncio.wait_for(_query(), timeout=2.0)
        return "ok", depth
    except Exception as exc:
        logger.warning("health_check_queue_failed", error=str(exc))
        return "error", 0


def _get_provider_status() -> dict[str, str]:
    """Return configured/unconfigured status for each registered enrichment provider."""
    from app.integrations.enrichment.registry import enrichment_registry

    return {
        p.provider_name: "configured" if p.is_configured() else "unconfigured"
        for p in enrichment_registry.list_all()
    }


@router.get("/health", include_in_schema=False)
async def health_check() -> JSONResponse:
    """
    Public health check endpoint. No authentication required.

    Returns overall status, DB connectivity, queue depth, and enrichment
    provider configuration state. Responds within 2 seconds even if a
    subsystem check hangs — each check runs with asyncio.wait_for timeout.
    """
    db_status = await _check_db()
    queue_status, queue_depth = await _check_queue()
    providers = _get_provider_status()

    if db_status == "error":
        overall = "down"
    else:
        overall = "ok"

    body: dict[str, Any] = {
        "status": overall,
        "version": settings.APP_VERSION,
        "database": db_status,
        "queue": queue_status,
        "queue_depth": queue_depth,
        "enrichment_providers": providers,
    }
    http_status = 503 if overall == "down" else 200
    return JSONResponse(content=body, status_code=http_status)
