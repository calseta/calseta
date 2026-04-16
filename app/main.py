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
  - seed_builtin_workflows: upserts 9 pre-built Okta/Entra system workflows.
    Failure logs a warning but does not crash the server.
  - load_normalized_mappings: loads active normalized-target mappings into
    an in-memory cache used for fingerprint extraction at ingest time.
"""

from __future__ import annotations

import pathlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.responses import FileResponse
from starlette.types import Receive, Scope, Send

from app.api.errors import register_exception_handlers
from app.api.health import router as health_router
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
    from app.integrations.enrichment.registry import enrichment_registry
    from app.seed.builtin_tools import seed_builtin_tools
    from app.seed.builtin_workflows import seed_builtin_workflows
    from app.seed.enrichment_providers import (
        seed_builtin_field_extractions,
        seed_builtin_providers,
    )
    from app.seed.indicator_mappings import seed_system_mappings
    from app.services.indicator_mapping_cache import load_normalized_mappings

    # Load external LLM adapters (graceful — failures are logged)
    if settings.CALSETA_EXTERNAL_ADAPTERS:
        from app.integrations.llm.adapter_registry import (
            load_external_adapters,
        )

        load_external_adapters(settings.CALSETA_EXTERNAL_ADAPTERS)

    try:
        async with AsyncSessionLocal() as db:
            await seed_system_mappings(db)
            await seed_builtin_workflows(db, settings)
            await load_normalized_mappings(db)

            # Seed built-in agent tools — isolated so a missing migration
            # (agent_tools table) doesn't break other startup tasks.
            try:
                await seed_builtin_tools(db)
            except Exception as exc:
                logger.warning(
                    "builtin_tools_seed_skipped",
                    error=str(exc),
                    hint="Run 'alembic upgrade head' to apply the agent_tools migration",
                )

            # Enrichment provider seeding — isolated so a missing migration
            # (0006) doesn't break the other seed tasks that already work.
            try:
                await seed_builtin_providers(db)
                await seed_builtin_field_extractions(db)
            except Exception as exc:
                logger.warning(
                    "enrichment_provider_seed_skipped",
                    error=str(exc),
                    hint=(
                        "Run 'alembic upgrade head' to apply the "
                        "enrichment_providers migration"
                    ),
                )

            if settings.SANDBOX_MODE:
                from app.seed.sandbox import seed_sandbox

                await seed_sandbox(db)

            await db.commit()

            # Load enrichment providers from DB into the in-memory registry.
            # If the table doesn't exist yet, this is a no-op.
            try:
                await enrichment_registry.load_from_database(db)
            except Exception as exc:
                logger.warning(
                    "enrichment_registry_load_skipped",
                    error=str(exc),
                )
    except Exception as exc:
        logger.warning(
            "startup_seed_failed",
            error=str(exc),
            hint=(
                "Indicator field mappings or built-in workflows "
                "may be missing — pipeline may be degraded"
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
        title="Calseta",
        version=settings.APP_VERSION,
        description="SOC data platform for security agent consumption",
        docs_url=None,
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
    application.include_router(health_router)
    application.include_router(v1_router)

    # Middleware stack — added in innermost-to-outermost order.
    # Starlette processes last-added middleware first on ingress.
    application.add_middleware(RequestLoggingMiddleware)   # innermost
    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(SecurityHeadersMiddleware)
    setup_cors(application)                                # adds CORSMiddleware if configured
    application.add_middleware(BodySizeLimitMiddleware)    # outermost

    # Admin UI: serve static build from ui/dist/ if present.
    # In production, the Dockerfile copies the built UI into the image.
    # In development with `make dev`, the build output is visible via
    # the volume mount. Run `make ui-build` once to generate ui/dist/.
    _ui_dist = pathlib.Path(__file__).resolve().parent.parent / "ui" / "dist"
    if _ui_dist.is_dir():
        application.mount(
            "/",
            _SPAStaticFiles(directory=str(_ui_dist), html=True),
            name="ui",
        )
        logger.info("admin_ui_mounted", path=str(_ui_dist))

    return application


class _SPAStaticFiles(StaticFiles):
    """StaticFiles with SPA fallback — returns index.html for unknown paths.

    Starlette's StaticFiles with ``html=True`` serves index.html for
    directory requests but returns 404 for paths like ``/alerts/abc123``
    that don't correspond to a real file.  This subclass intercepts
    those 404s and returns index.html so client-side routing can handle
    them.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        except Exception:
            # Path didn't match any static file — serve index.html
            # so the SPA router can handle it client-side.
            index = pathlib.Path(self.directory) / "index.html"  # type: ignore[arg-type]
            if index.is_file():
                response = FileResponse(str(index))
                await response(scope, receive, send)
            else:
                raise


app = create_app()
