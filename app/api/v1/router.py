"""
v1 API router — aggregates all versioned sub-routers.

Add new route modules here as they are built in subsequent waves.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import api_keys

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(api_keys.router)
