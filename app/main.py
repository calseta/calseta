"""
FastAPI application factory.

Middleware registration order (last added = outermost = executes first on
ingress, last on egress):
  1. RequestLoggingMiddleware  — innermost
  2. RequestIDMiddleware       — inject/propagate X-Request-ID
  3. SecurityHeadersMiddleware — add security headers to all responses
  4. CORSMiddleware            — handle OPTIONS before auth (if configured)
  5. BodySizeLimitMiddleware   — outermost; reject before any processing

Rate limiting (slowapi) is applied via @limiter.limit() decorators on
individual routes — not as a middleware layer.

Exception handlers are registered before middleware so they wrap
everything uniformly.

Startup events:
  - seed_system_mappings: inserts 14 CalsetaAlert → indicator type system
    mappings into indicator_field_mappings if not already present.
    Failure logs a warning but does not crash the server.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from app.api.errors import register_exception_handlers
from app.api.v1.router import v1_router
from app.config import settings
from app.logging_config import configure_logging
from app.middleware.body_size import BodySizeLimitMiddleware
from app.middleware.cors import setup_cors
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.rate_limit import limiter
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

configure_logging("api")

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
            hint=(
                "Indicator field mappings may be missing — "
                "extraction pipeline degraded"
            ),
        )


def _rate_limit_exceeded_handler(
    request: object, exc: RateLimitExceeded
) -> object:
    """
    Custom 429 handler returning the standard ErrorResponse format.

    slowapi's default handler returns plain text. We override to return
    the Calseta error envelope with Retry-After header.
    """
    from fastapi.responses import JSONResponse

    from app.schemas.common import ErrorDetail, ErrorResponse

    retry_after = int(getattr(exc, "retry_after", 60))
    body = ErrorResponse(
        error=ErrorDetail(
            code="RATE_LIMITED",
            message=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            details={"retry_after_seconds": retry_after},
        )
    ).model_dump()
    response = JSONResponse(status_code=429, content=body)
    response.headers["Retry-After"] = str(retry_after)
    return response


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

    # slowapi: store limiter on app.state + register 429 handler
    application.state.limiter = limiter
    application.add_exception_handler(
        RateLimitExceeded, _rate_limit_exceeded_handler  # type: ignore[arg-type]
    )

    # Routers
    application.include_router(v1_router)

    # Middleware stack — added in innermost-to-outermost order.
    # Starlette processes last-added middleware first on ingress.
    application.add_middleware(RequestLoggingMiddleware)   # innermost
    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    setup_cors(application)                                # adds CORSMiddleware if configured
    application.add_middleware(BodySizeLimitMiddleware)    # outermost

    @application.get("/health", include_in_schema=False)
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
