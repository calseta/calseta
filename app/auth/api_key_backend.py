"""
APIKeyAuthBackend — bcrypt-based API key authentication.

Auth flow:
  1. Extract `Authorization: Bearer cai_xxx` header
  2. Slice `key_prefix` = first 8 chars
  3. Look up APIKey row by prefix
  4. Verify bcrypt hash
  5. Check expiry (raises KEY_EXPIRED if past)
  6. Update last_used_at in the session (committed with the request)
  7. Return AuthContext on success

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
from app.repositories.api_key_repository import APIKeyRepository

_BEARER_PREFIX = "Bearer "
_KEY_PREFIX_LEN = 8  # first 8 chars of the full key (e.g. "cai_xxxx")


class APIKeyAuthBackend(AuthBackendBase):
    """Authenticates requests using bcrypt-hashed `cai_*` API keys."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = APIKeyRepository(db)

    async def authenticate(self, request: Request) -> AuthContext:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith(_BEARER_PREFIX):
            log_auth_failure("missing_header", request)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message=(
                    "Missing or invalid Authorization header. "
                    "Expected: Bearer cai_..."
                ),
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        plain_key = authorization[len(_BEARER_PREFIX):]
        if not plain_key.startswith("cai_") or len(plain_key) < _KEY_PREFIX_LEN:
            log_auth_failure("invalid_format", request)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid API key format.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        key_prefix = plain_key[:_KEY_PREFIX_LEN]
        record = await self._repo.get_by_prefix(key_prefix)
        if record is None:
            log_auth_failure("invalid_key", request, key_prefix=key_prefix)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid API key.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        match = bcrypt.checkpw(plain_key.encode(), record.key_hash.encode())
        if not match:
            log_auth_failure("invalid_key", request, key_prefix=key_prefix)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid API key.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        # Expiry check
        if record.expires_at is not None:
            now = datetime.now(UTC)
            # expires_at may be timezone-naive from the DB; normalise to UTC
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if now > expires_at:
                log_auth_failure("key_expired", request, key_prefix=key_prefix)
                raise CalsetaException(
                    code="KEY_EXPIRED",
                    message="API key has expired.",
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

        # Update last_used_at — committed with the session at request end
        record.last_used_at = datetime.now(UTC)
        await self._db.flush()

        return AuthContext(
            key_prefix=key_prefix,
            scopes=list(record.scopes),
            key_id=record.id,
            allowed_sources=(
                list(record.allowed_sources) if record.allowed_sources else None
            ),
        )
