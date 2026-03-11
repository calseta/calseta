"""
Shared fixtures for integration tests.

These fixtures build on the root conftest (db_session, test_client, api_key) and
add scoped API keys, sample entities, and a mock task queue so tests can hit
real API endpoints through the FastAPI test client against a real DB without
requiring a running worker process.
"""

from __future__ import annotations

import secrets
from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, patch

import bcrypt
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.api_key import APIKey
from app.main import app
from app.queue.dependencies import get_queue

# ---------------------------------------------------------------------------
# Mock task queue
# ---------------------------------------------------------------------------

VALID_WORKFLOW_CODE = (
    "async def run(ctx):\n"
    "    return ctx.success('ok')\n"
)


@pytest_asyncio.fixture
async def mock_queue() -> AsyncGenerator[AsyncMock, None]:
    """
    Mock the task queue in both DI-injected and direct-import paths.

    - Ingest/alerts routes use Depends(get_queue) → overridden via dependency_overrides.
    - Workflow routes import get_queue_backend() directly → patched via unittest.mock.
    """
    mock = AsyncMock()
    mock.enqueue.return_value = "mock-task-id"

    app.dependency_overrides[get_queue] = lambda: mock

    with patch("app.queue.factory.get_queue_backend", return_value=mock):
        yield mock

    app.dependency_overrides.pop(get_queue, None)


# ---------------------------------------------------------------------------
# Scoped API key factory
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture  # type: ignore[type-var]
def scoped_api_key(
    db_session: AsyncSession,
) -> Callable[..., Coroutine[Any, Any, str]]:
    """
    Factory fixture: create an API key with specific scopes.

    Usage:
        key = await scoped_api_key(["alerts:read", "alerts:write"])
    """

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


# ---------------------------------------------------------------------------
# Convenience scoped key fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def alerts_read_key(scoped_api_key: Any) -> str:
    result: str = await scoped_api_key(["alerts:read"])
    return result


@pytest_asyncio.fixture
async def alerts_write_key(scoped_api_key: Any) -> str:
    result: str = await scoped_api_key(["alerts:write"])
    return result


@pytest_asyncio.fixture
async def enrichments_read_key(scoped_api_key: Any) -> str:
    result: str = await scoped_api_key(["enrichments:read"])
    return result


@pytest_asyncio.fixture
async def workflows_read_key(scoped_api_key: Any) -> str:
    result: str = await scoped_api_key(["workflows:read"])
    return result


@pytest_asyncio.fixture
async def workflows_write_key(scoped_api_key: Any) -> str:
    result: str = await scoped_api_key(["workflows:write"])
    return result


@pytest_asyncio.fixture
async def workflows_execute_key(scoped_api_key: Any) -> str:
    result: str = await scoped_api_key(["workflows:execute"])
    return result


@pytest_asyncio.fixture
async def agents_read_key(scoped_api_key: Any) -> str:
    result: str = await scoped_api_key(["agents:read"])
    return result


@pytest_asyncio.fixture
async def agents_write_key(scoped_api_key: Any) -> str:
    result: str = await scoped_api_key(["agents:write"])
    return result


# ---------------------------------------------------------------------------
# Auth header helper
# ---------------------------------------------------------------------------


def auth_header(key: str) -> dict[str, str]:
    """Return a dict suitable for passing as ``headers=`` to httpx."""
    return {"Authorization": f"Bearer {key}"}


# ---------------------------------------------------------------------------
# Sample entity fixtures — created via the API
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def sample_alert(
    test_client: AsyncClient,
    api_key: str,
    mock_queue: AsyncMock,
) -> dict[str, Any]:
    """Create a sample alert via the generic ingest endpoint."""
    resp = await test_client.post(
        "/v1/alerts",
        json={
            "source_name": "generic",
            "payload": {
                "title": "Test Alert — Integration",
                "severity": "High",
                "occurred_at": "2026-01-15T10:00:00Z",
                "tags": ["test"],
            },
        },
        headers=auth_header(api_key),
    )
    assert resp.status_code == 202, resp.text
    alert_uuid = resp.json()["data"]["alert_uuid"]

    # Fetch full alert
    detail = await test_client.get(
        f"/v1/alerts/{alert_uuid}",
        headers=auth_header(api_key),
    )
    assert detail.status_code == 200, detail.text
    data: dict[str, Any] = detail.json()["data"]
    return data


@pytest_asyncio.fixture
async def sample_detection_rule(
    test_client: AsyncClient,
    api_key: str,
) -> dict[str, Any]:
    """Create a sample detection rule."""
    resp = await test_client.post(
        "/v1/detection-rules",
        json={
            "name": "Integration Test Rule",
            "source_name": "generic",
            "is_active": True,
            "mitre_tactics": ["Execution"],
            "mitre_techniques": ["T1059"],
            "mitre_subtechniques": [],
            "data_sources": [],
            "documentation": "Test detection rule",
        },
        headers=auth_header(api_key),
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


@pytest_asyncio.fixture
async def sample_context_document(
    test_client: AsyncClient,
    api_key: str,
) -> dict[str, Any]:
    """Create a sample context document."""
    resp = await test_client.post(
        "/v1/context-documents",
        json={
            "title": "Integration Test Playbook",
            "document_type": "playbook",
            "is_global": True,
            "description": "Test context document",
            "content": "# Test Playbook\nStep 1: Investigate\nStep 2: Remediate",
            "tags": ["test"],
            "targeting_rules": None,
        },
        headers=auth_header(api_key),
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


@pytest_asyncio.fixture
async def sample_workflow(
    test_client: AsyncClient,
    api_key: str,
) -> dict[str, Any]:
    """Create a sample active workflow with valid AST code."""
    resp = await test_client.post(
        "/v1/workflows",
        json={
            "name": "Integration Test Workflow",
            "workflow_type": "indicator",
            "indicator_types": ["ip"],
            "code": VALID_WORKFLOW_CODE,
            "state": "active",
            "timeout_seconds": 30,
            "retry_count": 1,
            "is_active": True,
            "tags": ["test"],
            "time_saved_minutes": 5,
            "approval_mode": "never",
            "approval_channel": None,
            "approval_timeout_seconds": 300,
            "risk_level": "low",
            "documentation": "Test workflow",
        },
        headers=auth_header(api_key),
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


@pytest_asyncio.fixture
async def sample_agent(
    test_client: AsyncClient,
    api_key: str,
) -> dict[str, Any]:
    """Create a sample agent registration."""
    resp = await test_client.post(
        "/v1/agents",
        json={
            "name": "integration-test-agent",
            "description": "Agent for integration tests",
            "endpoint_url": "http://localhost:9999/webhook",
            "auth_header_name": None,
            "auth_header_value": None,
            "trigger_on_sources": ["generic"],
            "trigger_on_severities": ["High", "Critical"],
            "trigger_filter": None,
            "timeout_seconds": 10,
            "retry_count": 1,
            "is_active": True,
            "documentation": "Test agent",
        },
        headers=auth_header(api_key),
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


@pytest_asyncio.fixture
async def sample_source(
    test_client: AsyncClient,
    api_key: str,
) -> dict[str, Any]:
    """Create a sample source integration."""
    resp = await test_client.post(
        "/v1/sources",
        json={
            "source_name": "generic",
            "display_name": "Generic Test Source",
            "is_active": True,
            "auth_type": None,
            "auth_config": None,
            "documentation": "Integration test source",
        },
        headers=auth_header(api_key),
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


@pytest_asyncio.fixture
async def sample_indicator_mapping(
    test_client: AsyncClient,
    api_key: str,
) -> dict[str, Any]:
    """Create a sample custom indicator field mapping."""
    resp = await test_client.post(
        "/v1/indicator-mappings",
        json={
            "source_name": "generic",
            "field_path": "custom.ip_field",
            "indicator_type": "ip",
            "extraction_target": "raw_payload",
            "is_active": True,
            "description": "Test custom mapping",
        },
        headers=auth_header(api_key),
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data
