"""
FastAPI auth dependencies.

Usage in route handlers:
    # Require authentication only:
    @router.get("/items")
    async def list_items(auth: AuthContext = Depends(get_auth_context)) -> ...:
        ...

    # Require a specific scope (also implies authentication):
    @router.post("/items")
    async def create_item(
        auth: AuthContext = Depends(require_scope(Scope.ALERTS_WRITE)),
    ) -> ...:
        ...

    # Require one of several scopes (OR logic):
    @router.get("/items")
    async def read_items(
        auth: AuthContext = Depends(require_scope(Scope.ALERTS_READ, Scope.ADMIN)),
    ) -> ...:
        ...

`admin` is a superscope — a key with `admin` passes every scope check.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.errors import CalsetaException
from app.auth.agent_api_key_backend import AgentAPIKeyAuthBackend
from app.auth.api_key_backend import APIKeyAuthBackend
from app.auth.audit import log_auth_failure
from app.auth.base import AuthBackendBase, AuthContext
from app.auth.scopes import Scope
from app.db.session import get_db

_BEARER_PREFIX = "Bearer "


async def get_auth_context(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthContext:
    """
    FastAPI dependency — authenticates the request and returns AuthContext.

    Routes `cak_*` keys to AgentAPIKeyAuthBackend and `cai_*` keys to the
    standard APIKeyAuthBackend.

    Stores the result in `request.state.auth` so the rate limiter key
    function can read the key_prefix without a second DB lookup.

    Raises CalsetaException(UNAUTHORIZED, 401) on any auth failure.
    Routes that need only authentication use this directly.
    """
    authorization = request.headers.get("Authorization", "")
    plain_key = ""
    if authorization.startswith(_BEARER_PREFIX):
        plain_key = authorization[len(_BEARER_PREFIX):]

    backend: AuthBackendBase
    if plain_key.startswith("cak_"):
        backend = AgentAPIKeyAuthBackend(db)
    else:
        backend = APIKeyAuthBackend(db)

    ctx = await backend.authenticate(request)
    request.state.auth = ctx  # Store for rate limiter key function
    return ctx


def require_scope(*scopes: Scope) -> Callable[..., Awaitable[AuthContext]]:
    """
    Dependency factory that enforces scope requirements.

    Returns a FastAPI dependency that:
      1. Authenticates the request (calls get_auth_context)
      2. Checks that the key has at least one of the required scopes,
         OR has the `admin` superscope.

    Usage:
        Depends(require_scope(Scope.ALERTS_WRITE))
    """

    async def _check_scope(
        request: Request,
        auth: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> AuthContext:
        if Scope.ADMIN in auth.scopes:
            return auth
        if any(s in auth.scopes for s in scopes):
            return auth
        required = " or ".join(str(s) for s in scopes)
        log_auth_failure(
            "insufficient_scope",
            request,
            key_prefix=auth.key_prefix,
            required_scope=required,
        )
        raise CalsetaException(
            code="FORBIDDEN",
            message=f"Insufficient scope. Required: {required}",
            status_code=status.HTTP_403_FORBIDDEN,
            details={"required_scopes": [str(s) for s in scopes]},
        )

    return _check_scope
