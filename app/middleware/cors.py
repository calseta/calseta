"""
CORS configuration helper.

Reads CORS_ALLOWED_ORIGINS and CORS_ALLOW_ALL_ORIGINS from settings and
registers CORSMiddleware on the app only when origins are configured.
Disabled by default — no CORS headers unless explicitly enabled.

WARNING: CORS_ALLOW_ALL_ORIGINS=true must never be used in production.
It disables origin checking, allowing any web page to make cross-origin
requests to the API. Use CORS_ALLOWED_ORIGINS with specific origins.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

logger = structlog.get_logger(__name__)


def setup_cors(app: FastAPI) -> None:
    """
    Register CORSMiddleware if CORS origins are configured.

    Called from app/main.py create_app() AFTER all other middleware so that
    CORS is added in the correct stack position (outer = before auth).
    """
    if settings.CORS_ALLOW_ALL_ORIGINS:
        logger.warning(
            "cors_allow_all_origins_enabled",
            msg=(
                "CORS_ALLOW_ALL_ORIGINS is enabled — all origins can make "
                "cross-origin requests. This is intended for local development "
                "only. Set CORS_ALLOWED_ORIGINS to specific origins in production."
            ),
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            allow_credentials=False,  # Cannot use credentials with allow_origins=["*"]
        )
        return

    origins = [
        o.strip()
        for o in settings.CORS_ALLOWED_ORIGINS.split(",")
        if o.strip()
    ]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            allow_credentials=True,
        )
