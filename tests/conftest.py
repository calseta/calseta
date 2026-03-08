"""
Shared pytest fixtures for the Calseta test suite.

Fixture hierarchy:
    event_loop        — module-scoped async event loop
    db_session        — function-scoped async DB session, rolled back after each test
    test_client       — function-scoped httpx AsyncClient with db_session injected
    api_key           — plain-text admin API key created via the DB (not HTTP)

DB setup:
    Tests require a running PostgreSQL instance pointed to by TEST_DATABASE_URL
    (falls back to DATABASE_URL). The schema must already exist (run migrations
    before the test suite). Each test gets a fresh session that is rolled back
    at teardown — no data leaks between tests.

Usage:
    async def test_health(test_client: AsyncClient) -> None:
        resp = await test_client.get("/health")
        assert resp.status_code == 200
"""

from __future__ import annotations

import os
import secrets
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.db.session import get_db
from app.main import app

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    os.environ.get("DATABASE_URL", ""),
)

_DB_AVAILABLE = bool(TEST_DATABASE_URL and "://" in TEST_DATABASE_URL)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def db_engine() -> AsyncGenerator[object, None]:
    """Session-scoped async engine for the test database."""
    if not _DB_AVAILABLE:
        pytest.skip("No TEST_DATABASE_URL configured — skipping DB tests")
    engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: object) -> AsyncGenerator[AsyncSession, None]:
    """
    Function-scoped async session.

    Each test runs inside a SAVEPOINT so the outer transaction can be rolled
    back at teardown, leaving the DB pristine for the next test.
    """
    from sqlalchemy.ext.asyncio import AsyncEngine

    assert isinstance(db_engine, AsyncEngine)

    async with db_engine.connect() as conn:
        await conn.begin()
        # Use a nested SAVEPOINT so we can roll back without affecting the outer transaction.
        await conn.begin_nested()

        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await conn.rollback()


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    httpx AsyncClient wrapping the FastAPI app.

    Overrides the get_db dependency so all route handlers use the
    rolled-back test session.
    """

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# API key fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def api_key(db_session: AsyncSession) -> str:
    """
    Creates a test API key with admin scope directly via the DB.

    Returns the plain-text key (format: cai_<32-char urlsafe string>).
    The key is cleaned up automatically when db_session rolls back.

    NOTE: This fixture inserts directly into api_keys without going through
    the auth service, since that service is built in chunk 1.4. Once the
    auth service exists, this fixture should delegate to it.
    """
    import bcrypt

    from app.db.models.api_key import APIKey

    plain_key = "cai_" + secrets.token_urlsafe(32)
    key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt()).decode()
    key_prefix = plain_key[:8]

    record = APIKey(
        name="test-admin-key",
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=["admin"],
        is_active=True,
    )
    db_session.add(record)
    await db_session.flush()

    return plain_key
