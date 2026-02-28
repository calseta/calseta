"""
APIKeyRepository — all DB operations for API keys.

Never import this directly from route handlers — use it from services
or auth backends only. Route files depend on the service layer.
"""

from __future__ import annotations

import secrets
from datetime import datetime

import bcrypt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.api_key import APIKey


class APIKeyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_prefix(self, key_prefix: str) -> APIKey | None:
        """Return the APIKey row whose key_prefix matches, or None."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.key_prefix == key_prefix, APIKey.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        name: str,
        scopes: list[str],
        expires_at: datetime | None = None,
        allowed_sources: list[str] | None = None,
    ) -> tuple[APIKey, str]:
        """
        Generate and persist a new API key.

        Returns (APIKey row, plain_text_key). The plain key is never stored —
        callers must surface it to the user immediately and discard it.
        """
        plain_key = "cai_" + secrets.token_urlsafe(32)
        key_prefix = plain_key[:8]
        key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt()).decode()

        record = APIKey(
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes,
            is_active=True,
            expires_at=expires_at,
            allowed_sources=allowed_sources,
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        return record, plain_key

    async def deactivate(self, uuid: str) -> bool:
        """
        Soft-delete a key by setting is_active=False.

        Returns True if the key was found and deactivated, False if not found.
        """
        result = await self.db.execute(
            select(APIKey).where(APIKey.uuid == uuid)  # type: ignore[arg-type]
        )
        record = result.scalar_one_or_none()
        if record is None:
            return False
        record.is_active = False
        await self.db.flush()
        return True

    async def list_active(
        self, offset: int = 0, limit: int = 50
    ) -> tuple[list[APIKey], int]:
        """Return (page of active API keys, total active count)."""
        where = APIKey.is_active.is_(True)

        count_result = await self.db.execute(
            select(func.count()).select_from(APIKey).where(where)
        )
        total: int = count_result.scalar_one()

        result = await self.db.execute(
            select(APIKey).where(where).order_by(APIKey.created_at.desc()).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total
