"""
v1 API router — aggregates all versioned sub-routers.

Add new route modules here as they are built in subsequent waves.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    alerts,
    api_keys,
    detection_rules,
    enrichments,
    indicator_mappings,
    ingest,
)

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(api_keys.router)
v1_router.include_router(alerts.router)
v1_router.include_router(ingest.router)
v1_router.include_router(indicator_mappings.router)
v1_router.include_router(detection_rules.router)
v1_router.include_router(enrichments.router)
