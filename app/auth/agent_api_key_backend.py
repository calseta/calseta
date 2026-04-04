"""
AgentAPIKeyAuthBackend — bcrypt-based authentication for agent API keys.

Auth flow:
  1. Extract `Authorization: Bearer cak_xxx` header
  2. Slice `key_prefix` = first 8 chars
  3. Look up AgentAPIKey row by prefix (non-revoked only)
  4. Verify bcrypt hash
  5. Check revoked_at (raises KEY_REVOKED if set — belt-and-suspenders)
  6. Update last_used_at in the session (committed with the request)
  7. Return AuthContext with key_type="agent" and agent_registration_id populated

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
_KEY_PREFIX_LEN = 8  # first 8 chars of the full key (e.g. "cak_xxxx")


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
        record = await self._repo.get_by_prefix(key_prefix)
        if record is None:
            log_auth_failure("invalid_key", request, key_prefix=key_prefix)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid agent API key.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        match = bcrypt.checkpw(plain_key.encode(), record.key_hash.encode())
        if not match:
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
        await self._db.flush()

        return AuthContext(
            key_prefix=key_prefix,
            scopes=list(record.scopes),
            key_id=record.id,
            key_type="agent",
            allowed_sources=None,
            agent_registration_id=record.agent_registration_id,
        )
