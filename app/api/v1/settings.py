"""Settings routes — GET /v1/settings/approval-defaults."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.requests import Request

from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.middleware.rate_limit import limiter

router = APIRouter(prefix="/settings", tags=["settings"])

_Admin = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]


@router.get("/approval-defaults")
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_approval_defaults(request: Request, auth: _Admin) -> dict:
    """Return the system-level approval notifier defaults from env config."""
    return {
        "data": {
            "notifier": settings.APPROVAL_NOTIFIER,
            "default_channel": settings.APPROVAL_DEFAULT_CHANNEL or None,
            "default_timeout_seconds": settings.APPROVAL_DEFAULT_TIMEOUT_SECONDS,
            "slack_configured": bool(settings.SLACK_BOT_TOKEN),
            "teams_configured": bool(settings.TEAMS_WEBHOOK_URL),
        },
        "meta": {},
    }
