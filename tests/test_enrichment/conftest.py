"""
Fixtures for enrichment API tests.

Re-exports scoped API key fixtures needed by test_enrichment_api.py.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Coroutine
from typing import Any

import bcrypt
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.api_key import APIKey


@pytest_asyncio.fixture  # type: ignore[type-var]
def scoped_api_key(
    db_session: AsyncSession,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """Factory fixture: create an API key with specific scopes."""

    async def _create(
        scopes: list[str],
        allowed_sources: list[str] | None = None,
        key_type: str = "human",
    ) -> str:
        plain_key = "cai_" + secrets.token_urlsafe(32)
        key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt()).decode()
        key_prefix = plain_key[:8]

        record = APIKey(
            name=f"test-{'-'.join(scopes)}-key",
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes,
            is_active=True,
            allowed_sources=allowed_sources,
            key_type=key_type,
        )
        db_session.add(record)
        await db_session.flush()
        return plain_key

    return _create


@pytest_asyncio.fixture
async def enrichments_read_key(scoped_api_key: Any) -> str:
    result: str = await scoped_api_key(["enrichments:read"])
    return result


@pytest_asyncio.fixture
async def alerts_read_key(scoped_api_key: Any) -> str:
    result: str = await scoped_api_key(["alerts:read"])
    return result
