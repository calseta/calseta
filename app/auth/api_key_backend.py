"""
APIKeyAuthBackend — bcrypt-based API key authentication.

Auth flow:
  1. Extract `Authorization: Bearer cai_xxx` header
  2. Slice `key_prefix` = first 16 chars (defense-in-depth: longer prefix
     means fewer candidate rows on lookup, but we still iterate-and-bcrypt
     because two keys CAN share a prefix — see S17 hardening notes)
  3. List APIKey rows whose key_prefix matches
  4. Iterate candidates and verify bcrypt hash; pick the matching row
  5. Check expiry (raises KEY_EXPIRED if past)
  6. Update last_used_at in the session (committed with the request)
  7. Return AuthContext on success — scopes are read from the resolved
     record only, never from the prefix lookup result set

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
# First 16 chars of the full key (e.g. "cai_xxxxxxxxxxxx"). 16 chars makes
# accidental prefix collisions astronomically unlikely while still leaving
# the iterate-and-bcrypt pattern in place for safety.
_KEY_PREFIX_LEN = 16


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
        candidates = await self._repo.list_by_prefix(key_prefix)
        if not candidates:
            log_auth_failure("invalid_key", request, key_prefix=key_prefix)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid API key.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        # Iterate-and-bcrypt: at most a handful of candidates share a 16-char
        # prefix in pathological cases. Pick the first one whose hash matches.
        record = None
        for candidate in candidates:
            if bcrypt.checkpw(plain_key.encode(), candidate.key_hash.encode()):
                record = candidate
                break

        if record is None:
            log_auth_failure("invalid_key", request, key_prefix=key_prefix)
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid API key.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        # Expiry check — read from the resolved record only.
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

        # IMPORTANT: scopes are read from the AUTHENTICATED record (the row
        # whose bcrypt hash matched) — never from the candidate set.
        return AuthContext(
            key_prefix=record.key_prefix,
            scopes=list(record.scopes),
            key_id=record.id,
            key_type=record.key_type,
            allowed_sources=(
                list(record.allowed_sources) if record.allowed_sources else None
            ),
        )
