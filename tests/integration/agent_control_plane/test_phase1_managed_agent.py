"""Integration tests — full managed agent execution cycle (Phase 1).

Verifies the complete API-driven workflow that a managed agent follows:
checkout → heartbeat → cost events → assignment state updates → resolution.

Also tests session continuity via heartbeat run IDs and budget accumulation
across multiple LLM calls within a single agent run.
"""

from __future__ import annotations

import os
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.conftest import auth_header


class TestManagedAgentExecutionCycle:
    """Full API-driven execution cycle: checkout → heartbeat → cost → resolve."""

    async def test_full_checkout_to_resolution_cycle(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        enriched_alert: Any,
    ) -> None:
        """Complete cycle: checkout alert, report heartbeat, post cost, resolve assignment."""
        agent, headers = agent_and_auth
        alert_uuid = str(enriched_alert.uuid)

        # Step 1: Checkout the alert
        checkout_resp = await test_client.post(
            f"/v1/queue/{alert_uuid}/checkout",
            headers=headers,
        )
        assert checkout_resp.status_code == 201, checkout_resp.text
        assignment_data = checkout_resp.json()["data"]
        assignment_uuid = assignment_data["uuid"]
        assert assignment_data["status"] == "in_progress"

        # Step 2: Post running heartbeat → creates HeartbeatRun
        hb_resp = await test_client.post(
            "/v1/heartbeat",
            json={
                "status": "running",
                "progress_note": "Analyzing alert indicators",
                "findings_count": 0,
                "actions_proposed": 0,
            },
            headers=headers,
        )
        assert hb_resp.status_code == 200, hb_resp.text
        hb_data = hb_resp.json()["data"]
        heartbeat_run_id = hb_data["heartbeat_run_id"]
        assert heartbeat_run_id is not None
        assert hb_data["supervisor_directive"] is None

        # Step 3: Post cost event (simulates one LLM call)
        cost_resp = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 1500,
                "output_tokens": 200,
                "cost_cents": 5,
                "billing_type": "api",
                "heartbeat_run_id": heartbeat_run_id,
            },
            headers=headers,
        )
        assert cost_resp.status_code == 201, cost_resp.text
        budget = cost_resp.json()["data"]["agent_budget"]
        assert budget["hard_stop_triggered"] is False
        assert budget["spent_cents"] >= 5

        # Step 4: Update assignment with intermediate investigation state
        upd_resp = await test_client.patch(
            f"/v1/assignments/{assignment_uuid}",
            json={
                "status": "in_progress",
                "investigation_state": {
                    "phase": "analyzing",
                    "indicators_checked": 3,
                    "findings": [],
                },
            },
            headers=headers,
        )
        assert upd_resp.status_code == 200, upd_resp.text

        # Step 5: Post completion heartbeat
        final_hb = await test_client.post(
            "/v1/heartbeat",
            json={
                "status": "idle",
                "findings_count": 1,
                "actions_proposed": 0,
            },
            headers=headers,
        )
        assert final_hb.status_code == 200, final_hb.text
        assert final_hb.json()["data"]["supervisor_directive"] is None

        # Step 6: Resolve the assignment
        resolve_resp = await test_client.patch(
            f"/v1/assignments/{assignment_uuid}",
            json={
                "status": "resolved",
                "resolution": "False positive — benign internal traffic pattern confirmed",
            },
            headers=headers,
        )
        assert resolve_resp.status_code == 200, resolve_resp.text
        resolved = resolve_resp.json()["data"]
        assert resolved["status"] == "resolved"

    async def test_heartbeat_run_ids_are_distinct_across_runs(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
    ) -> None:
        """Each heartbeat creates a new run with a distinct UUID."""
        agent, headers = agent_and_auth

        hb1 = await test_client.post(
            "/v1/heartbeat",
            json={"status": "running", "findings_count": 0, "actions_proposed": 0},
            headers=headers,
        )
        assert hb1.status_code == 200
        run_a_id = hb1.json()["data"]["heartbeat_run_id"]

        hb2 = await test_client.post(
            "/v1/heartbeat",
            json={"status": "running", "findings_count": 0, "actions_proposed": 0},
            headers=headers,
        )
        assert hb2.status_code == 200
        run_b_id = hb2.json()["data"]["heartbeat_run_id"]

        assert run_a_id != run_b_id

    async def test_cost_events_reference_heartbeat_run_by_uuid(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
    ) -> None:
        """Cost events tied to heartbeat_run_id link LLM calls to execution sessions.

        This is the mechanism agents use for session continuity: each heartbeat
        creates a run, and cost events record which run incurred the cost.
        """
        agent, headers = agent_and_auth

        # First heartbeat — session start
        hb1 = await test_client.post(
            "/v1/heartbeat",
            json={"status": "running", "findings_count": 0, "actions_proposed": 0},
            headers=headers,
        )
        assert hb1.status_code == 200
        run_a_id = hb1.json()["data"]["heartbeat_run_id"]

        # Cost event references run A (first LLM call)
        cost1 = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 1000,
                "output_tokens": 150,
                "cost_cents": 4,
                "heartbeat_run_id": run_a_id,
            },
            headers=headers,
        )
        assert cost1.status_code == 201

        # Second heartbeat — session resumed
        hb2 = await test_client.post(
            "/v1/heartbeat",
            json={"status": "running", "findings_count": 0, "actions_proposed": 0},
            headers=headers,
        )
        assert hb2.status_code == 200
        run_b_id = hb2.json()["data"]["heartbeat_run_id"]
        assert run_b_id != run_a_id

        # Cost event references run B (second LLM call)
        cost2 = await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 2000,
                "output_tokens": 300,
                "cost_cents": 8,
                "heartbeat_run_id": run_b_id,
            },
            headers=headers,
        )
        assert cost2.status_code == 201

        # Both runs appear in the heartbeat-runs list
        list_resp = await test_client.get(
            f"/v1/heartbeat-runs?agent_uuid={agent.uuid}",
            headers=headers,
        )
        assert list_resp.status_code == 200
        run_ids = {r["uuid"] for r in list_resp.json()["data"]}
        assert run_a_id in run_ids
        assert run_b_id in run_ids

    async def test_multiple_llm_calls_accumulate_spent_cents(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
    ) -> None:
        """Multiple cost events accumulate on the agent's spent_monthly_cents."""
        agent, headers = agent_and_auth

        calls = [
            {"input_tokens": 1000, "output_tokens": 100, "cost_cents": 3},
            {"input_tokens": 2000, "output_tokens": 200, "cost_cents": 7},
            {"input_tokens": 500, "output_tokens": 50, "cost_cents": 2},
        ]
        running_total = 0

        for call in calls:
            resp = await test_client.post(
                "/v1/cost-events",
                json={
                    "provider": "anthropic",
                    "model": "claude-3-5-sonnet-20241022",
                    "billing_type": "api",
                    **call,
                },
                headers=headers,
            )
            assert resp.status_code == 201
            running_total += call["cost_cents"]
            budget = resp.json()["data"]["agent_budget"]
            assert budget["spent_cents"] >= running_total
            assert budget["hard_stop_triggered"] is False

    async def test_agent_registration_status_unchanged_through_cycle(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        agent_and_auth: tuple[Any, dict[str, str]],
        enriched_alert: Any,
    ) -> None:
        """Agent status stays 'active' throughout a normal execution cycle."""
        from app.db.models.agent_registration import AgentRegistration

        agent, headers = agent_and_auth
        alert_uuid = str(enriched_alert.uuid)

        # Run through the standard cycle
        await test_client.post(f"/v1/queue/{alert_uuid}/checkout", headers=headers)
        await test_client.post(
            "/v1/heartbeat",
            json={"status": "running", "findings_count": 0, "actions_proposed": 0},
            headers=headers,
        )
        await test_client.post(
            "/v1/cost-events",
            json={
                "provider": "anthropic",
                "model": "claude-3-5-sonnet-20241022",
                "input_tokens": 500,
                "output_tokens": 50,
                "cost_cents": 2,
            },
            headers=headers,
        )

        # DB state: agent still active
        result = await db_session.execute(
            select(AgentRegistration).where(AgentRegistration.id == agent.id)
        )
        db_agent = result.scalar_one()
        assert db_agent.status == "active"

    async def test_supervisor_directive_pause_returned_when_agent_paused(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """When agent status is 'paused', heartbeat returns supervisor_directive='pause'."""
        agent, plain_key = await _create_agent_with_key(
            db_session, name="pause-directive-agent", status="active"
        )
        agent.status = "paused"
        await db_session.flush()

        hb = await test_client.post(
            "/v1/heartbeat",
            json={"status": "running", "findings_count": 0, "actions_proposed": 0},
            headers=auth_header(plain_key),
        )
        assert hb.status_code == 200, hb.text
        assert hb.json()["data"]["supervisor_directive"] == "pause"


# ---------------------------------------------------------------------------
# Phase 1 exit-criteria gap: Agent home directory created on registration
# ---------------------------------------------------------------------------


class TestAgentHomeDirectory:
    """Phase 1 exit criterion: agent home directory created at
    $CALSETA_DATA_DIR/agents/{id}/ when an agent is registered.

    The filesystem creation is not yet implemented — the current codebase only
    tracks agent memory as KB-page folder paths in the database.  This test is
    marked xfail so the gap is visible in CI output without blocking the suite.
    """

    async def test_agent_home_directory_created_on_registration(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """POST /v1/agents creates $CALSETA_DATA_DIR/agents/{agent.id}/ on disk."""
        from app.config import settings

        # Register a new managed agent
        resp = await test_client.post(
            "/v1/agents",
            json={
                "name": "home-dir-test-agent",
                "execution_mode": "managed",
                "agent_type": "standalone",
                "adapter_type": "webhook",
                "webhook_url": "https://example.com/webhook",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
            },
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        agent_id = resp.json()["data"]["id"]

        data_dir = getattr(settings, "CALSETA_DATA_DIR", "/tmp/calseta")
        expected_path = os.path.join(str(data_dir), "agents", str(agent_id))

        assert os.path.isdir(expected_path), (
            f"Expected agent home directory at {expected_path!r} but it does not exist. "
            "Agent home directory creation is a Phase 1 exit criterion."
        )
