"""
FastAPI application factory.

Middleware registration order (outermost → innermost):
  1. RequestIDMiddleware   — assigns X-Request-ID first
  2. RequestLoggingMiddleware — reads request_id from context vars set above

Exception handlers are registered before middleware so they wrap
everything uniformly.
"""

from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.config import settings
from app.middleware.logging import RequestLoggingMiddleware
from app.middleware.request_id import RequestIDMiddleware


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Calseta AI",
        version=settings.APP_VERSION,
        description="SOC data platform for AI agent consumption",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Global exception handlers — registered before middleware.
    register_exception_handlers(app)

    # Middleware stack — added in reverse order of execution.
    # Starlette processes middleware last-added-first, so add logging before
    # request_id to ensure request_id is outermost (runs first on ingress).
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)

    @app.get("/health", include_in_schema=False)
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
