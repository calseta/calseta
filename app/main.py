"""
FastAPI application factory.

Middleware registration order (outermost → innermost):
  1. RequestIDMiddleware   — assigns X-Request-ID first
  2. RequestLoggingMiddleware — reads request_id from context vars set above

Exception handlers are registered before middleware so they wrap
everything uniformly.

Startup events:
  - seed_system_mappings: inserts 14 CalsetaAlert → indicator type system
    mappings into indicator_field_mappings if not already present.
    Failure logs a warning but does not crash the server.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.v1.router import v1_router
from app.config import settings
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.request_id import RequestIDMiddleware

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Run startup tasks before yielding, teardown tasks after."""
    await _on_startup()
    yield
    # Teardown (if needed) goes here


async def _on_startup() -> None:
    """Run all startup tasks. Failures are logged but never crash the server."""
    from app.db.session import AsyncSessionLocal
    from app.seed.indicator_mappings import seed_system_mappings

    try:
        async with AsyncSessionLocal() as db:
            await seed_system_mappings(db)
            await db.commit()
    except Exception as exc:
        logger.warning(
            "startup_seed_failed",
            error=str(exc),
            hint="Indicator field mappings may be missing — extraction pipeline degraded",
        )


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    application = FastAPI(
        title="Calseta AI",
        version=settings.APP_VERSION,
        description="SOC data platform for AI agent consumption",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # Global exception handlers — registered before middleware.
    register_exception_handlers(application)

    # Middleware stack — added in reverse order of execution.
    # Starlette processes middleware last-added-first, so add logging before
    # request_id to ensure request_id is outermost (runs first on ingress).
    application.add_middleware(RequestLoggingMiddleware)
    application.add_middleware(RequestIDMiddleware)

    # Routers
    application.include_router(v1_router)

    @application.get("/health", include_in_schema=False)
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
