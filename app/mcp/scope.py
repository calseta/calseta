"""
MCP scope enforcement helper.

The MCP SDK validates API keys at connection time via ``CalsetaTokenVerifier``.
On success it stores an ``AuthenticatedUser`` (with the resolved
``AccessToken``) on the Starlette request scope as ``request["user"]``. Per
the SDK's ``BearerAuthBackend`` (mcp.server.auth.middleware.bearer_auth),
``user.scopes`` are exactly the scopes returned by ``verify_token()`` for
the AUTHENTICATED record — i.e. the row whose bcrypt hash matched.

S17 fix: ``check_scope`` now reads scopes from that authenticated record
(via ``request["user"].scopes``) instead of re-querying the DB by
``client_id`` (the key prefix). Re-querying by prefix is wrong on principle
because two keys can share a 16-char plaintext prefix — granting access to
ANY candidate sharing the prefix would let a low-scope key inherit the
scopes of a high-scope key whose prefix happened to collide.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context
from sqlalchemy.ext.asyncio import AsyncSession


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


def _resolve_authenticated_scopes(ctx: Context) -> list[str] | None:
    """
    Read the scopes of the authenticated user off the Starlette request.

    Returns the list of scopes from the AccessToken that ``CalsetaTokenVerifier``
    issued for this connection — i.e. scopes from the row whose bcrypt hash
    matched, NOT from a re-query by prefix.

    Returns None when no authenticated user is present (e.g. unit tests that
    construct ``Context`` without going through the MCP middleware stack).
    """
    try:
        request = ctx.request_context.request
        if request is None or "user" not in request:
            return None
        user: Any = request["user"]
    except Exception:
        return None

    scopes = getattr(user, "scopes", None)
    if scopes is None:
        return None
    # Defensive copy — never let downstream code mutate the AuthenticatedUser.
    return list(scopes)


async def check_scope(
    ctx: Context,
    session: AsyncSession,  # noqa: ARG001 — kept for back-compat with callers
    *required_scopes: str,
) -> str | None:
    """
    Check that the connected API key has at least one of the required scopes.

    Returns None if the check passes, or a JSON error string if it fails.
    Tools should return the error string directly if non-None.

    The ``admin`` scope is a superscope and passes every check.

    The ``session`` argument is unused (scopes are read from the authenticated
    user record, not via a DB lookup) but kept in the signature so existing
    callers don't have to change. Removing it would be a wide API churn for
    no functional gain.
    """
    client_id = _resolve_client_id(ctx)
    if not client_id:
        return json.dumps({"error": "Authentication required."})

    scopes_list = _resolve_authenticated_scopes(ctx)
    if scopes_list is None:
        # No authenticated user attached to the request — treat as invalid.
        # Don't fall back to a DB re-query: that's the bug S17 is fixing.
        return json.dumps({"error": "Invalid API key."})

    scopes = set(scopes_list)
    if "admin" in scopes:
        return None
    if any(s in scopes for s in required_scopes):
        return None

    required = " or ".join(required_scopes)
    return json.dumps({
        "error": f"Insufficient scope. Required: {required}",
    })
