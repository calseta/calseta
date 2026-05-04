"""
MCP scope enforcement helper.

The MCP SDK validates API keys at connection time via CalsetaTokenVerifier,
but doesn't expose the AccessToken scopes on the tool/resource request context.
This module provides a lightweight helper to enforce scope requirements per
tool call by looking up the key's scopes from the client_id (key_prefix).

The SDK stores the authenticated user on the Starlette request object (via
BearerAuthBackend), but does NOT inject the client_id into the JSON-RPC
``_meta`` field that ``ctx.client_id`` reads from. We fall back to extracting
the client_id from the Starlette request's auth scope when ``ctx.client_id``
is unavailable.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.api_key_repository import APIKeyRepository


def _resolve_client_id(ctx: Context) -> str | None:
    """Extract client_id from MCP context, falling back to Starlette auth."""
    # Primary: JSON-RPC _meta.client_id (set by some MCP clients)
    client_id = ctx.client_id
    if client_id:
        return client_id

    # Fallback: Starlette request auth scope (set by BearerAuthBackend).
    # Starlette's Request stores the ASGI scope as ``_scope`` (private) and
    # implements ``Mapping``, so ``request["user"]`` works. The ``.user``
    # property raises AssertionError when missing, which getattr can't catch.
    try:
        request = ctx.request_context.request
        if request is not None and "user" in request:
            user = request["user"]
            # AuthenticatedUser extends SimpleUser which stores the client_id
            # as ``username``, not ``identity`` (identity raises NotImplementedError).
            return getattr(user, "username", None)
    except Exception:
        pass

    return None


async def check_scope(
    ctx: Context,
    session: AsyncSession,
    *required_scopes: str,
) -> str | None:
    """
    Check that the connected API key has at least one of the required scopes.

    Returns None if the check passes, or a JSON error string if it fails.
    Tools should return the error string directly if non-None.

    The ``admin`` scope is a superscope and passes every check.
    """
    client_id = _resolve_client_id(ctx)
    if not client_id:
        return json.dumps({"error": "Authentication required."})

    repo = APIKeyRepository(session)
    # client_id is the (non-unique) key prefix. The token was already bcrypt-
    # validated by CalsetaTokenVerifier; here we just resolve scopes. Allow if
    # ANY candidate sharing the prefix has the required scope. This matches
    # pre-fix behavior but does not crash on prefix collisions. The broader
    # "scope check should be tied to the authenticated key, not the prefix"
    # issue is tracked separately — see Wave 5 backlog.
    candidates = await repo.list_by_prefix(client_id)
    if not candidates:
        return json.dumps({"error": "Invalid API key."})

    aggregate_scopes: set[str] = set()
    for record in candidates:
        aggregate_scopes.update(record.scopes)
    if "admin" in aggregate_scopes:
        return None
    if any(s in aggregate_scopes for s in required_scopes):
        return None

    required = " or ".join(required_scopes)
    return json.dumps({
        "error": f"Insufficient scope. Required: {required}",
    })
