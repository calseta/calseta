"""
Fixtures for agent control plane integration tests.

Builds on the root conftest (db_session, test_client, api_key) and the
integration conftest (scoped_api_key, auth_header). Adds:
  - Agent registration with agent API key (cak_*)
  - Bulk list of agent API keys for concurrent-checkout tests
  - Enriched alert ready for queue checkout
  - Admin / read-only header shortcuts keyed to admin and read scopes
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Coroutine
from typing import Any

import bcrypt
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_api_key import AgentAPIKey
from app.db.models.agent_registration import AgentRegistration
from app.db.models.alert import Alert
from tests.integration.agent_control_plane.fixtures.mock_alerts import create_enriched_alert
from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_agent_with_key(
    db: AsyncSession,
    *,
    name: str = "test-agent",
    budget_monthly_cents: int = 0,
    status: str = "active",
) -> tuple[AgentRegistration, str]:
    """
    Create an AgentRegistration row + an AgentAPIKey (cak_*) directly via DB.

    Returns (AgentRegistration, plain_key).
    The plain_key is shown once — bcrypt-hashed in DB.
    """
    agent = AgentRegistration(
        name=name,
        status=status,
        budget_monthly_cents=budget_monthly_cents,
        execution_mode="external",
        agent_type="standalone",
        adapter_type="webhook",
        trigger_on_sources=[],
        trigger_on_severities=[],
        timeout_seconds=30,
        retry_count=3,
    )
    db.add(agent)
    await db.flush()
    await db.refresh(agent)

    plain_key = "cak_" + secrets.token_urlsafe(32)
    key_prefix = plain_key[:8]
    key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt(rounds=4)).decode()

    api_key_record = AgentAPIKey(
        agent_registration_id=agent.id,
        name=f"key-for-{name}",
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=[
            "alerts:read",
            "alerts:write",
            "workflows:execute",
            "enrichments:read",
            "agents:read",
            "agents:write",
        ],
    )
    db.add(api_key_record)
    await db.flush()

    return agent, plain_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def agent_with_key(db_session: AsyncSession) -> tuple[AgentRegistration, str]:
    """An active AgentRegistration + its cak_* plain API key."""
    return await _create_agent_with_key(db_session, name="acp-test-agent")


@pytest_asyncio.fixture
async def agent_auth_headers(agent_with_key: tuple[AgentRegistration, str]) -> dict[str, str]:
    """Auth headers for a single test agent."""
    _, plain_key = agent_with_key
    return auth_header(plain_key)


@pytest_asyncio.fixture
async def agent_and_auth(
    agent_with_key: tuple[AgentRegistration, str],
) -> tuple[AgentRegistration, dict[str, str]]:
    """Convenience: (AgentRegistration, headers) together."""
    agent, plain_key = agent_with_key
    return agent, auth_header(plain_key)


@pytest_asyncio.fixture
async def agent_auth_headers_list(
    db_session: AsyncSession,
) -> list[dict[str, str]]:
    """
    10 distinct agent API keys for the concurrent-checkout test.

    Each key belongs to a different AgentRegistration so the uniqueness
    constraint on (alert_id, agent_registration_id) can't mask races.
    """
    headers: list[dict[str, str]] = []
    for i in range(10):
        _, plain_key = await _create_agent_with_key(
            db_session, name=f"concurrent-agent-{i}"
        )
        headers.append(auth_header(plain_key))
    return headers


@pytest_asyncio.fixture
async def enriched_alert(db_session: AsyncSession) -> Alert:
    """
    An alert with enrichment_status='Enriched' and status='Open', no assignment.

    Created directly in the DB — no ingest pipeline, no worker.
    """
    return await create_enriched_alert(db_session)


@pytest_asyncio.fixture
async def admin_auth_headers(api_key: str) -> dict[str, str]:
    """Auth headers using the root conftest admin key (scopes=['admin'])."""
    return auth_header(api_key)


@pytest_asyncio.fixture
async def read_auth_headers(
    scoped_api_key: Callable[..., Coroutine[Any, Any, str]],
) -> dict[str, str]:
    """Auth headers for a read-only key (agents:read)."""
    key: str = await scoped_api_key(["agents:read"])
    return auth_header(key)
