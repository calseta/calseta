"""
MCP scope enforcement helper.

The MCP SDK validates API keys at connection time via CalsetaTokenVerifier,
but doesn't expose the AccessToken scopes on the tool/resource request context.
This module provides a lightweight helper to enforce scope requirements per
tool call by looking up the key's scopes from the client_id (key_prefix).
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.api_key_repository import APIKeyRepository


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
    client_id = ctx.client_id
    if not client_id:
        return json.dumps({"error": "Authentication required."})

    repo = APIKeyRepository(session)
    record = await repo.get_by_prefix(client_id)
    if record is None:
        return json.dumps({"error": "Invalid API key."})

    scopes = set(record.scopes)
    if "admin" in scopes:
        return None
    if any(s in scopes for s in required_scopes):
        return None

    required = " or ".join(required_scopes)
    return json.dumps({
        "error": f"Insufficient scope. Required: {required}",
    })
