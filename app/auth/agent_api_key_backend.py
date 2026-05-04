"""
AgentAPIKeyAuthBackend — bcrypt-based authentication for agent API keys.

Auth flow:
  1. Extract `Authorization: Bearer cak_xxx` header
  2. Slice `key_prefix` = first 16 chars (defense-in-depth: longer prefix
     means fewer candidate rows, but we still iterate-and-bcrypt — see
     S17 hardening notes)
  3. List AgentAPIKey rows whose key_prefix matches (non-revoked only)
  4. Iterate candidates and verify bcrypt hash; pick the matching row
  5. Check revoked_at (raises KEY_REVOKED if set — belt-and-suspenders)
  6. Update last_used_at in the session (committed with the request)
  7. Return AuthContext with key_type="agent" and agent_registration_id
     populated; scopes come from the resolved record only.

Agent keys use the `cak_` prefix to distinguish them from human `cai_` keys.
Every failure path calls log_auth_failure() before raising.
"""

from __future__ import annotations

from datetime import UTC, datetime

import bcrypt
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.errors import CalsetaException
from app.auth.audit import log_auth_failure
from app.auth.base import AuthBackendBase, AuthContext
from app.repositories.agent_api_key_repository import AgentAPIKeyRepository

_BEARER_PREFIX = "Bearer "
# First 16 chars of the full key (e.g. "cak_xxxxxxxxxxxx"). See
# api_key_backend._KEY_PREFIX_LEN for rationale.
_KEY_PREFIX_LEN = 16


class AgentAPIKeyAuthBackend(AuthBackendBase):
    """Authenticates agent requests using bcrypt-hashed `cak_*` API keys."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = AgentAPIKeyRepository(db)

    async def authenticate(self, request: Request) -> AuthContext:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith(_BEARER_PREFIX):
            log_auth_failure("missing_header", request)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message=(
                    "Missing or invalid Authorization header. "
                    "Expected: Bearer cak_..."
                ),
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        plain_key = authorization[len(_BEARER_PREFIX):]
        if not plain_key.startswith("cak_") or len(plain_key) < _KEY_PREFIX_LEN:
            log_auth_failure("invalid_format", request)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid agent API key format.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        key_prefix = plain_key[:_KEY_PREFIX_LEN]
        candidates = await self._repo.list_by_prefix(key_prefix)
        if not candidates:
            log_auth_failure("invalid_key", request, key_prefix=key_prefix)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid agent API key.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        record = None
        for candidate in candidates:
            if bcrypt.checkpw(plain_key.encode(), candidate.key_hash.encode()):
                record = candidate
                break

        if record is None:
            log_auth_failure("invalid_key", request, key_prefix=key_prefix)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid agent API key.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        # Belt-and-suspenders revocation check (repo already filters on revoked_at IS NULL)
        if record.revoked_at is not None:
            log_auth_failure("key_revoked", request, key_prefix=key_prefix)
            raise CalsetaException(
                code="KEY_REVOKED",
                message="Agent API key has been revoked.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        # Update last_used_at — committed with the session at request end
        record.last_used_at = datetime.now(UTC)

        # IMPORTANT: scopes are read from the AUTHENTICATED record only.
        return AuthContext(
            key_prefix=record.key_prefix,
            scopes=list(record.scopes),
            key_id=record.id,
            key_type="agent",
            allowed_sources=None,
            agent_registration_id=record.agent_registration_id,
        )
