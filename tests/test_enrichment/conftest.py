"""
Fixtures for enrichment API tests.

Provides scoped API key fixtures and enrichment registry seeding
needed by test_enrichment_api.py.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any

import bcrypt
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.api_key import APIKey


@pytest_asyncio.fixture(autouse=True)
async def _seed_enrichment_providers(db_session: AsyncSession) -> AsyncGenerator[None, None]:
    """Seed builtin enrichment providers and load the registry before each test."""
    from app.integrations.enrichment.registry import enrichment_registry
    from app.seed.enrichment_providers import (
        seed_builtin_field_extractions,
        seed_builtin_providers,
    )

    try:
        await seed_builtin_providers(db_session)
        await seed_builtin_field_extractions(db_session)
        await db_session.flush()
        await enrichment_registry.load_from_database(db_session)
    except Exception:
        pass  # Table may not exist in some test configs
    yield
    # Clear registry after test to avoid cross-test contamination
    enrichment_registry._providers.clear()


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
