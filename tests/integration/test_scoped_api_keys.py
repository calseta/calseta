"""Integration tests for scoped per-run agent API keys (S3).

Covers ``app.services.scoped_api_keys.mint_run_api_key`` and the
``key_expired`` rejection path in
``app.auth.agent_api_key_backend.AgentAPIKeyAuthBackend``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_api_key import AgentAPIKey
from app.services.scoped_api_keys import mint_run_api_key


@pytest_asyncio.fixture
async def agent_id(db_session: AsyncSession) -> int:
    """Insert a minimal agent_registrations row and return its id.

    Uses a raw INSERT to avoid the ORM trying to write
    ``spent_monthly_cents`` (mapped on the ORM but not present in any
    current migration — S5 will drop it from the ORM entirely).
    """
    from sqlalchemy import text

    result = await db_session.execute(
        text(
            """
            INSERT INTO agent_registrations
                (name, status, execution_mode, agent_type, adapter_type,
                 trigger_on_sources, trigger_on_severities,
                 timeout_seconds, retry_count, budget_monthly_cents,
                 max_concurrent_alerts)
            VALUES
                (:name, 'active', 'external', 'standalone', 'webhook',
                 ARRAY[]::text[], ARRAY[]::text[],
                 30, 3, 0, 1)
            RETURNING id
            """
        ),
        {"name": "scoped-key-test-agent"},
    )
    new_id = int(result.scalar_one())
    await db_session.flush()
    return new_id


# ---------------------------------------------------------------------------
# mint_run_api_key
# ---------------------------------------------------------------------------


class TestMintRunApiKey:
    @pytest.mark.asyncio
    async def test_returns_cak_prefixed_key(
        self, db_session: AsyncSession, agent_id: int
    ):
        key = await mint_run_api_key(
            db_session, agent_id=agent_id, run_uuid=uuid4()
        )
        assert key.startswith("cak_")

    @pytest.mark.asyncio
    async def test_persists_row_with_expires_at_set(
        self, db_session: AsyncSession, agent_id: int
    ):
        run_uuid = uuid4()
        before = datetime.now(UTC)
        key = await mint_run_api_key(
            db_session,
            agent_id=agent_id,
            run_uuid=run_uuid,
            ttl_seconds=3600,
        )
        after = datetime.now(UTC)

        # Locate the row by prefix.
        from sqlalchemy import select

        result = await db_session.execute(
            select(AgentAPIKey).where(AgentAPIKey.key_prefix == key[:16])
        )
        record = result.scalar_one()

        assert record.expires_at is not None
        # ttl 3600 means expires_at ≈ now + 1 hour, allow generous wiggle
        # for slow CI.
        expected_min = before + timedelta(seconds=3500)
        expected_max = after + timedelta(seconds=3700)
        assert expected_min <= record.expires_at <= expected_max

        # Scopes are exactly the documented narrow set.
        assert sorted(record.scopes) == sorted(["agents:write", "alerts:write"])

        # Name encodes the run_uuid for audit.
        assert str(run_uuid) in record.name

    @pytest.mark.asyncio
    async def test_rejects_zero_or_negative_ttl(
        self, db_session: AsyncSession, agent_id: int
    ):
        with pytest.raises(ValueError):
            await mint_run_api_key(
                db_session, agent_id=agent_id, run_uuid=uuid4(), ttl_seconds=0
            )

    @pytest.mark.asyncio
    async def test_default_ttl_is_3600s(
        self, db_session: AsyncSession, agent_id: int
    ):
        from app.services.scoped_api_keys import DEFAULT_TTL_SECONDS

        assert DEFAULT_TTL_SECONDS == 3600

        before = datetime.now(UTC)
        key = await mint_run_api_key(
            db_session, agent_id=agent_id, run_uuid=uuid4()
        )
        from sqlalchemy import select

        result = await db_session.execute(
            select(AgentAPIKey).where(AgentAPIKey.key_prefix == key[:16])
        )
        record = result.scalar_one()
        # Must be ~3600 seconds in the future, not the previous default
        # (which would have been 900s).
        assert record.expires_at is not None
        delta = (record.expires_at - before).total_seconds()
        assert 3500 <= delta <= 3700


# ---------------------------------------------------------------------------
# Auth backend — expired key rejection
# ---------------------------------------------------------------------------


class TestExpiredKeyRejection:
    @pytest.mark.asyncio
    async def test_expired_key_rejected_with_key_expired(
        self,
        db_session: AsyncSession,
        agent_id: int,
        test_client: AsyncClient,
    ):
        # Mint a key whose expires_at is already in the past.
        key = await mint_run_api_key(
            db_session,
            agent_id=agent_id,
            run_uuid=uuid4(),
            ttl_seconds=1,
        )

        # Manually backdate the expiry by 1 hour so it's definitely
        # expired regardless of test runtime.
        from sqlalchemy import select

        result = await db_session.execute(
            select(AgentAPIKey).where(AgentAPIKey.key_prefix == key[:16])
        )
        record = result.scalar_one()
        record.expires_at = datetime.now(UTC) - timedelta(hours=1)
        await db_session.commit()

        # Attempt to authenticate. Endpoint choice doesn't matter —
        # any agent-key-protected endpoint returns 401 with KEY_EXPIRED.
        # We use /v1/agents/me which is a thin "who am I" if it exists,
        # or any other agent-write endpoint.
        resp = await test_client.get(
            "/v1/agents",
            headers={"Authorization": f"Bearer {key}"},
        )
        # Even if the route doesn't exist, the auth backend runs first.
        # 401 with KEY_EXPIRED means the auth check fired correctly.
        assert resp.status_code == 401
        body = resp.json()
        assert body["error"]["code"] == "KEY_EXPIRED"

    @pytest.mark.asyncio
    async def test_unexpired_key_passes_expiry_check(
        self,
        db_session: AsyncSession,
        agent_id: int,
        test_client: AsyncClient,
    ):
        # Standard 1-hour key.
        key = await mint_run_api_key(
            db_session, agent_id=agent_id, run_uuid=uuid4()
        )
        await db_session.commit()

        resp = await test_client.get(
            "/v1/agents",
            headers={"Authorization": f"Bearer {key}"},
        )
        # Not 401 KEY_EXPIRED. Could be 200, 403, etc., depending on
        # scopes. We only assert the expiry path didn't fire.
        if resp.status_code == 401:
            body = resp.json()
            assert body["error"]["code"] != "KEY_EXPIRED"
