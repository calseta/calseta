"""
APIKeyAuthBackend — bcrypt-based API key authentication.

Auth flow:
  1. Extract `Authorization: Bearer cai_xxx` header
  2. Slice `key_prefix` = first 8 chars
  3. Look up APIKey row by prefix
  4. Verify bcrypt hash
  5. Return AuthContext on success

Failure semantics:
  - Missing/malformed header → 401 UNAUTHORIZED
  - Prefix not found or key inactive → 401 UNAUTHORIZED
  - Hash mismatch → 401 UNAUTHORIZED
  - Expiry check and `last_used_at` update are added in chunk 1.9
    (requires audit logging and background DB write infrastructure).
"""

from __future__ import annotations

import bcrypt
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.errors import CalsetaException
from app.auth.base import AuthBackendBase, AuthContext
from app.repositories.api_key_repository import APIKeyRepository

_BEARER_PREFIX = "Bearer "
_KEY_PREFIX_LEN = 8  # first 8 chars of the full key (e.g. "cai_xxxx")


class APIKeyAuthBackend(AuthBackendBase):
    """Authenticates requests using bcrypt-hashed `cai_*` API keys."""

    def __init__(self, db: AsyncSession) -> None:
        self._repo = APIKeyRepository(db)

    async def authenticate(self, request: Request) -> AuthContext:
        authorization = request.headers.get("Authorization", "")
        if not authorization.startswith(_BEARER_PREFIX):
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Missing or invalid Authorization header. Expected: Bearer cai_...",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        plain_key = authorization[len(_BEARER_PREFIX):]
        if not plain_key.startswith("cai_") or len(plain_key) < _KEY_PREFIX_LEN:
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid API key format.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        key_prefix = plain_key[:_KEY_PREFIX_LEN]
        record = await self._repo.get_by_prefix(key_prefix)
        if record is None:
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid API key.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        match = bcrypt.checkpw(plain_key.encode(), record.key_hash.encode())
        if not match:
            raise CalsetaException(
                code="UNAUTHORIZED",
                message="Invalid API key.",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        return AuthContext(
            key_prefix=key_prefix,
            scopes=list(record.scopes),
            key_id=record.id,
            allowed_sources=list(record.allowed_sources) if record.allowed_sources else None,
        )
