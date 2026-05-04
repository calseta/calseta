"""
APIKeyRepository — all DB operations for API keys.

Never import this directly from route handlers — use it from services
or auth backends only. Route files depend on the service layer.
"""

from __future__ import annotations

import secrets
from datetime import datetime

import bcrypt
from sqlalchemy import select

from app.db.models.api_key import APIKey
from app.repositories.base import BaseRepository

_UNSET = object()  # sentinel for "field not provided"


class APIKeyRepository(BaseRepository[APIKey]):
    model = APIKey

    async def list_by_prefix(self, key_prefix: str) -> list[APIKey]:
        """
        Return all active APIKey rows whose key_prefix matches.

        Returns a list (possibly empty) so the auth backend can iterate
        candidates and bcrypt-check each one. Two keys MAY share the same
        plaintext prefix (the bcrypt hash is what makes them distinct), so
        callers must always verify the hash before trusting any candidate.
        """
        result = await self._db.execute(
            select(APIKey).where(APIKey.key_prefix == key_prefix, APIKey.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def get_by_prefix(self, key_prefix: str) -> APIKey | None:
        """
        DEPRECATED — use ``list_by_prefix`` and iterate-and-bcrypt instead.

        Returns the first matching APIKey row, or None. Kept for back-compat
        with tests that mock this method directly. New code MUST go through
        ``list_by_prefix`` so prefix collisions cannot grant the wrong key's
        scopes.
        """
        candidates = await self.list_by_prefix(key_prefix)
        return candidates[0] if candidates else None

    async def create(
        self,
        name: str,
        scopes: list[str],
        key_type: str = "human",
        expires_at: datetime | None = None,
        allowed_sources: list[str] | None = None,
    ) -> tuple[APIKey, str]:
        """
        Generate and persist a new API key.

        Returns (APIKey row, plain_text_key). The plain key is never stored —
        callers must surface it to the user immediately and discard it.
        """
        plain_key = "cai_" + secrets.token_urlsafe(32)
        # Mirror the auth backend's _KEY_PREFIX_LEN. Bumped from 8 to 16 in
        # S17 for defense-in-depth against prefix collisions.
        key_prefix = plain_key[:16]
        key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt(rounds=12)).decode()

        record = APIKey(
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes,
            key_type=key_type,
            is_active=True,
            expires_at=expires_at,
            allowed_sources=allowed_sources,
        )
        self._db.add(record)
        await self._db.flush()
        await self._db.refresh(record)
        return record, plain_key

    async def get_by_uuid(self, uuid: str) -> APIKey | None:  # type: ignore[override]
        """Return the APIKey row matching the UUID, or None."""
        result = await self._db.execute(
            select(APIKey).where(APIKey.uuid == uuid)  # type: ignore[arg-type]
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        uuid: str,
        *,
        scopes: list[str] | None = None,
        allowed_sources: list[str] | None | object = _UNSET,
        is_active: bool | None = None,
    ) -> APIKey | None:
        """
        Update mutable fields on an API key. Returns the updated record or None
        if not found. Fields set to their sentinel (_UNSET) are not touched.
        """
        record = await self.get_by_uuid(uuid)
        if record is None:
            return None
        if scopes is not None:
            record.scopes = scopes
        if allowed_sources is not _UNSET:
            record.allowed_sources = allowed_sources  # type: ignore[assignment]
        if is_active is not None:
            record.is_active = is_active
        await self._db.flush()
        await self._db.refresh(record)
        return record

    async def deactivate(self, uuid: str) -> bool:
        """
        Soft-delete a key by setting is_active=False.

        Returns True if the key was found and deactivated, False if not found.
        """
        result = await self._db.execute(
            select(APIKey).where(APIKey.uuid == uuid)  # type: ignore[arg-type]
        )
        record = result.scalar_one_or_none()
        if record is None:
            return False
        record.is_active = False
        await self._db.flush()
        return True

    async def list_active(
        self, offset: int = 0, limit: int = 50
    ) -> tuple[list[APIKey], int]:
        """Return (page of active API keys, total active count)."""
        where = APIKey.is_active.is_(True)

        total = await self.count(where)

        result = await self._db.execute(
            select(APIKey).where(where).order_by(APIKey.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total
