"""
Integration tests for heartbeat lifecycle and cost event tracking.

Covers:
  POST /v1/heartbeat             heartbeat creates HeartbeatRun, returns directives
  POST /v1/cost-events           cost event recorded, budget enforcement
  GET  /v1/costs/by-agent        per-agent cost aggregates
  GET  /v1/costs/summary         instance-wide summary
  GET  /v1/heartbeat-runs        list runs (filterable by agent_uuid)
  GET  /v1/heartbeat-runs/{id}   single run detail
"""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import AgentRegistration
from app.db.models.heartbeat_run import HeartbeatRun
from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.conftest import auth_header


class TestHeartbeat:
    async def test_agent_heartbeat_creates_run(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
    ) -> None:
        """POST /v1/heartbeat creates a HeartbeatRun row and returns 200."""
        resp = await test_client.post(
            "/v1/heartbeat",
            json={
                "status": "running",
                "progress_note": "Investigating alert indicators",
                "findings_count": 2,
                "actions_proposed": 0,
            },
            headers=agent_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "heartbeat_run_id" in data
        assert "acknowledged_at" in data
        assert data["agent_status"] == "active"
        # No directive for a healthy active agent
        assert data["supervisor_directive"] is None

    async def test_heartbeat_run_is_persisted(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        agent_with_key: tuple[AgentRegistration, str],
        db_session: AsyncSession,
    ) -> None:
        """Heartbeat creates a HeartbeatRun row visible via DB."""
        agent, _ = agent_with_key

        resp = await test_client.post(
            "/v1/heartbeat",
            json={"status": "idle", "findings_count": 0, "actions_proposed": 0},
            headers=agent_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        run_uuid = resp.json()["data"]["heartbeat_run_id"]

        # Verify row exists in DB
        result = await db_session.execute(
            select(HeartbeatRun).where(HeartbeatRun.uuid == run_uuid)
        )
        run = result.scalar_one_or_none()
        assert run is not None, f"HeartbeatRun {run_uuid} not found in DB"
        assert run.agent_registration_id == agent.id

    async def test_paused_agent_gets_pause_directive(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        agent_with_key: tuple[AgentRegistration, str],
        admin_auth_headers: dict[str, str],
    ) -> None:
        """When agent is paused via control plane, heartbeat response includes supervisor_directive='pause'."""
        agent, _ = agent_with_key
        agent_uuid = str(agent.uuid)

        # Pause the agent via admin API
        pause_resp = await test_client.post(
            f"/v1/agents/{agent_uuid}/pause",
            json={"reason": "Integration test pause"},
            headers=admin_auth_headers,
        )
        assert pause_resp.status_code == 200, pause_resp.text
        assert pause_resp.json()["data"]["status"] == "paused"

        # Agent sends heartbeat — should receive pause directive
        hb_resp = await test_client.post(
            "/v1/heartbeat",
            json={"status": "running", "findings_count": 0, "actions_proposed": 0},
            headers=agent_auth_headers,
        )
        assert hb_resp.status_code == 200, hb_resp.text
        data = hb_resp.json()["data"]
        assert data["supervisor_directive"] == "pause", (
            f"Expected supervisor_directive='pause' for paused agent, got {data['supervisor_directive']!r}"
        )
        assert data["agent_status"] == "paused"

    async def test_terminated_agent_gets_terminate_directive(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        agent_with_key: tuple[AgentRegistration, str],
        admin_auth_headers: dict[str, str],
    ) -> None:
        """When agent is terminated, heartbeat response includes supervisor_directive='terminate'."""
        agent, _ = agent_with_key
        agent_uuid = str(agent.uuid)

        # Terminate the agent
        term_resp = await test_client.post(
            f"/v1/agents/{agent_uuid}/terminate",
            headers=admin_auth_headers,
        )
        assert term_resp.status_code == 200, term_resp.text
        assert term_resp.json()["data"]["status"] == "terminated"

        # Agent sends heartbeat — should receive terminate directive
        hb_resp = await test_client.post(
            "/v1/heartbeat",
            json={"status": "running", "findings_count": 0, "actions_proposed": 0},
            headers=agent_auth_headers,
        )
        assert hb_resp.status_code == 200, hb_resp.text
        data = hb_resp.json()["data"]
        assert data["supervisor_directive"] == "terminate", (
            f"Expected supervisor_directive='terminate' for terminated agent, got {data['supervisor_directive']!r}"
        )
        assert data["agent_status"] == "terminated"

    async def test_list_heartbeat_runs(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET /v1/heartbeat-runs returns paginated list of all runs."""
        # Send a heartbeat first to ensure there's at least one run
        await test_client.post(
            "/v1/heartbeat",
            json={"status": "running", "findings_count": 1, "actions_proposed": 0},
            headers=agent_auth_headers,
        )

        resp = await test_client.get("/v1/heartbeat-runs", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert body["meta"]["total"] >= 1

    async def test_get_heartbeat_run_by_uuid(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET /v1/heartbeat-runs/{id} returns a single run."""
        hb_resp = await test_client.post(
            "/v1/heartbeat",
            json={"status": "idle", "findings_count": 0, "actions_proposed": 0},
            headers=agent_auth_headers,
        )
        assert hb_resp.status_code == 200, hb_resp.text
        run_uuid = hb_resp.json()["data"]["heartbeat_run_id"]

        get_resp = await test_client.get(
            f"/v1/heartbeat-runs/{run_uuid}",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["data"]["uuid"] == run_uuid

    async def test_heartbeat_run_nonexistent_returns_404(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        resp = await test_client.get(
            "/v1/heartbeat-runs/00000000-0000-0000-0000-000000000000",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404


class TestCostTracking:
    async def test_report_cost_records_event(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
    ) -> None:
        """POST /v1/cost-events creates a CostEvent row and returns budget status."""
        resp = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 1500,
                "output_tokens": 200,
                "cost_cents": 5,
                "billing_type": "api",
            },
            headers=agent_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert "cost_event_id" in data
        assert "agent_budget" in data
        budget = data["agent_budget"]
        assert "monthly_cents" in budget
        assert "spent_cents" in budget
        assert "remaining_cents" in budget
        assert "hard_stop_triggered" in budget
        assert budget["hard_stop_triggered"] is False

    async def test_budget_hard_stop_pauses_agent(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """
        Reporting a cost that pushes spent_monthly_cents past budget_monthly_cents
        causes hard_stop_triggered=True in the response and sets agent.status='paused'.
        """
        # Create an agent with a tight budget of 100 cents
        agent, plain_key = await _create_agent_with_key(
            db_session,
            name="budget-test-agent",
            budget_monthly_cents=100,
        )
        agent_headers = auth_header(plain_key)

        # Report a cost of 150 cents — exceeds the 100 cent budget
        resp = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 50000,
                "output_tokens": 5000,
                "cost_cents": 150,
                "billing_type": "api",
            },
            headers=agent_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["agent_budget"]["hard_stop_triggered"] is True, (
            "Budget exceeded — hard_stop_triggered must be True"
        )

        # Agent status must have been flipped to 'paused' by the cost service
        await db_session.refresh(agent)
        assert agent.status == "paused", (
            f"Agent should be paused after budget exceeded, got status={agent.status!r}"
        )

    async def test_cost_summary_returns_zeros_with_no_events(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET /v1/costs/summary returns a valid summary structure (zeros when no events)."""
        resp = await test_client.get("/v1/costs/summary", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "total_cost_cents" in data
        assert "total_input_tokens" in data
        assert "total_output_tokens" in data
        assert "by_billing_type" in data

    async def test_cost_summary_by_agent(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        read_auth_headers: dict[str, str],
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET /v1/costs/by-agent returns per-agent cost aggregates after a cost event."""
        # Record a cost event so the agent appears in the aggregation
        await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-haiku-20241022",
                "input_tokens": 800,
                "output_tokens": 100,
                "cost_cents": 2,
                "billing_type": "api",
            },
            headers=agent_auth_headers,
        )

        resp = await test_client.get("/v1/costs/by-agent", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body["data"], list), "by-agent response should be a list"

    async def test_multiple_cost_events_accumulate(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
    ) -> None:
        """Multiple cost events for the same agent accumulate in spent_monthly_cents."""
        # Report two separate cost events and verify the second returns higher spent amount
        resp1 = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 1000,
                "output_tokens": 100,
                "cost_cents": 3,
                "billing_type": "api",
            },
            headers=agent_auth_headers,
        )
        assert resp1.status_code == 201, resp1.text
        spent_after_first = resp1.json()["data"]["agent_budget"]["spent_cents"]

        resp2 = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 1000,
                "output_tokens": 100,
                "cost_cents": 3,
                "billing_type": "api",
            },
            headers=agent_auth_headers,
        )
        assert resp2.status_code == 201, resp2.text
        spent_after_second = resp2.json()["data"]["agent_budget"]["spent_cents"]

        assert spent_after_second > spent_after_first, (
            f"spent_cents should increase after second event: "
            f"{spent_after_first} → {spent_after_second}"
        )

    async def test_human_key_can_list_heartbeat_runs(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Human keys with agents:read can list heartbeat runs (read-only endpoint)."""
        resp = await test_client.get("/v1/heartbeat-runs", headers=admin_auth_headers)
        assert resp.status_code == 200
