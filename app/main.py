"""
FastAPI application factory.

Imports here are kept minimal — middleware, routers, and startup events are
registered in later waves. This module is the entry point for the API process.
"""

from fastapi import FastAPI

from app.config import settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Calseta AI",
        version=settings.APP_VERSION,
        description="SOC data platform for AI agent consumption",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    @app.get("/health", include_in_schema=False)
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
