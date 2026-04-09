"""Integration tests — invocation long-poll contract (Phase 5).

Verifies GET /v1/invocations/{uuid}/poll semantics:
- 200 immediately when invocation is in a terminal state (completed, failed, timed_out)
- 202 when invocation is still running and timeout_ms expires
- 404 for unknown invocation UUIDs

Also covers GET /v1/invocations/{uuid} point-in-time status check.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.agent_control_plane.fixtures.mock_alerts import create_enriched_alert

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_orchestrator(db: AsyncSession, name: str = "poll-orch") -> Any:
    """Create an orchestrator agent in the DB."""
    agent, _ = await _create_agent_with_key(db, name=name)
    agent.agent_type = "orchestrator"
    await db.flush()
    await db.refresh(agent)
    return agent


async def _insert_invocation(
    db: AsyncSession,
    *,
    parent_agent_id: int,
    alert_id: int,
    status: str = "queued",
    result: dict[str, Any] | None = None,
    error: str | None = None,
    timeout_seconds: int = 300,
) -> Any:
    """Insert an AgentInvocation row directly for controlled poll testing."""
    from app.db.models.agent_invocation import AgentInvocation

    inv = AgentInvocation(
        uuid=uuid4(),
        parent_agent_id=parent_agent_id,
        alert_id=alert_id,
        task_description="Poll integration test task",
        status=status,
        result=result,
        error=error,
        timeout_seconds=timeout_seconds,
        started_at=datetime.now(UTC) if status in ("running", "completed", "failed", "timed_out") else None,
        completed_at=datetime.now(UTC) if status in ("completed", "failed") else None,
    )
    db.add(inv)
    await db.flush()
    await db.refresh(inv)
    return inv


# ---------------------------------------------------------------------------
# GET /v1/invocations/{uuid} — point-in-time status
# ---------------------------------------------------------------------------


class TestGetInvocationStatus:
    """GET /v1/invocations/{uuid} returns current status without waiting."""

    async def test_get_queued_invocation_returns_status(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET invocation returns status=queued for a newly created invocation."""
        agent = await _make_orchestrator(db_session, name="get-queued-orch")
        alert = await create_enriched_alert(db_session, title="Get Queued Alert")
        await db_session.flush()

        inv = await _insert_invocation(
            db_session,
            parent_agent_id=agent.id,
            alert_id=alert.id,
            status="queued",
        )

        resp = await test_client.get(
            f"/v1/invocations/{inv.uuid}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "queued"
        assert "uuid" in data
        assert "task_description" in data

    async def test_get_completed_invocation_includes_result(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET completed invocation includes the result payload."""
        agent = await _make_orchestrator(db_session, name="get-complete-orch")
        alert = await create_enriched_alert(db_session, title="Get Complete Alert")
        await db_session.flush()

        inv = await _insert_invocation(
            db_session,
            parent_agent_id=agent.id,
            alert_id=alert.id,
            status="completed",
            result={"finding": "false_positive", "confidence": 0.95},
        )

        resp = await test_client.get(
            f"/v1/invocations/{inv.uuid}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["result"] is not None
        assert data["result"]["finding"] == "false_positive"

    async def test_get_nonexistent_invocation_returns_404(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET /v1/invocations/{uuid} with unknown UUID returns 404."""
        resp = await test_client.get(
            f"/v1/invocations/{uuid4()}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# GET /v1/invocations/{uuid}/poll — long-poll
# ---------------------------------------------------------------------------


class TestInvocationPoll:
    """GET /v1/invocations/{uuid}/poll — long-poll until terminal state."""

    async def test_poll_completed_invocation_returns_200_immediately(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Poll on a completed invocation returns 200 with full result (no waiting)."""
        agent = await _make_orchestrator(db_session, name="poll-complete-orch")
        alert = await create_enriched_alert(db_session, title="Poll Complete Alert")
        await db_session.flush()

        inv = await _insert_invocation(
            db_session,
            parent_agent_id=agent.id,
            alert_id=alert.id,
            status="completed",
            result={"classification": "true_positive", "severity": "high"},
        )

        resp = await test_client.get(
            f"/v1/invocations/{inv.uuid}/poll?timeout_ms=1000",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["result"] is not None
        assert data["result"]["classification"] == "true_positive"

    async def test_poll_running_invocation_with_short_timeout_returns_202(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Poll on a running invocation with short timeout_ms returns 202."""
        agent = await _make_orchestrator(db_session, name="poll-running-orch")
        alert = await create_enriched_alert(db_session, title="Poll Running Alert")
        await db_session.flush()

        inv = await _insert_invocation(
            db_session,
            parent_agent_id=agent.id,
            alert_id=alert.id,
            status="running",
        )

        # Short timeout — task is still running, should get 202
        resp = await test_client.get(
            f"/v1/invocations/{inv.uuid}/poll?timeout_ms=1000",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()["data"]
        assert data["status"] == "running"

    async def test_poll_queued_invocation_with_short_timeout_returns_202(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Poll on a queued (not yet started) invocation returns 202 on timeout."""
        agent = await _make_orchestrator(db_session, name="poll-queued-orch")
        alert = await create_enriched_alert(db_session, title="Poll Queued Alert")
        await db_session.flush()

        inv = await _insert_invocation(
            db_session,
            parent_agent_id=agent.id,
            alert_id=alert.id,
            status="queued",
        )

        resp = await test_client.get(
            f"/v1/invocations/{inv.uuid}/poll?timeout_ms=1000",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 202, resp.text

    async def test_poll_failed_invocation_returns_200_with_error(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Poll on a failed invocation returns 200 with status=failed and error field."""
        agent = await _make_orchestrator(db_session, name="poll-fail-orch")
        alert = await create_enriched_alert(db_session, title="Poll Fail Alert")
        await db_session.flush()

        inv = await _insert_invocation(
            db_session,
            parent_agent_id=agent.id,
            alert_id=alert.id,
            status="failed",
            error="Specialist exceeded memory limit during investigation.",
        )

        resp = await test_client.get(
            f"/v1/invocations/{inv.uuid}/poll?timeout_ms=1000",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "failed"
        assert data["error"] is not None
        assert "memory" in data["error"] or data["error"] != ""

    async def test_poll_timed_out_invocation_returns_200(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Poll on a timed_out invocation returns 200 (terminal state)."""
        agent = await _make_orchestrator(db_session, name="poll-timeout-orch")
        alert = await create_enriched_alert(db_session, title="Poll Timeout Alert")
        await db_session.flush()

        inv = await _insert_invocation(
            db_session,
            parent_agent_id=agent.id,
            alert_id=alert.id,
            status="timed_out",
        )

        resp = await test_client.get(
            f"/v1/invocations/{inv.uuid}/poll?timeout_ms=1000",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "timed_out"

    async def test_poll_nonexistent_invocation_returns_404(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Poll on an unknown UUID returns 404."""
        resp = await test_client.get(
            f"/v1/invocations/{uuid4()}/poll?timeout_ms=1000",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404, resp.text

    async def test_poll_default_timeout_ms_respected(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Poll without explicit timeout_ms uses the server default (max 60s)."""
        agent = await _make_orchestrator(db_session, name="poll-default-timeout-orch")
        alert = await create_enriched_alert(db_session, title="Poll Default Timeout Alert")
        await db_session.flush()

        # A completed invocation with default timeout should return 200 immediately
        inv = await _insert_invocation(
            db_session,
            parent_agent_id=agent.id,
            alert_id=alert.id,
            status="completed",
            result={"summary": "all clear"},
        )

        resp = await test_client.get(
            f"/v1/invocations/{inv.uuid}/poll",  # No timeout_ms
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "completed"
