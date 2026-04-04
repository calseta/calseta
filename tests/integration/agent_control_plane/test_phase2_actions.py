"""
Integration tests for Phase 2 agent control plane — action proposal and lifecycle.

Covers:
  POST /v1/actions            Propose an action
  GET  /v1/actions            List actions (with status filter)
  GET  /v1/actions/{uuid}     Get a single action
  POST /v1/actions/{uuid}/cancel  Cancel an action

Approval mode defaults (from ActionIntegration base):
  notification → never    → auto-executes (status=executing)
  containment  → always   → pending_approval
  confidence >= 0.95      → auto_approve  → executing
  confidence <  0.70      → block         → rejected
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_action import AgentAction
from app.db.models.alert import Alert
from app.db.models.alert_assignment import AlertAssignment
from app.repositories.agent_action_repository import AgentActionRepository
from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.agent_control_plane.fixtures.mock_alerts import create_enriched_alert
from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _checkout_alert_for_agent(
    test_client: AsyncClient,
    alert: Alert,
    agent_headers: dict[str, str],
) -> dict[str, Any]:
    """Helper: checkout an alert and return the assignment data."""
    resp = await test_client.post(
        f"/v1/queue/{alert.uuid}/checkout",
        headers=agent_headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def _propose_action(
    test_client: AsyncClient,
    alert: Alert,
    assignment_uuid: str,
    headers: dict[str, str],
    action_type: str = "notification",
    action_subtype: str = "send_slack",
    payload: dict[str, Any] | None = None,
    confidence: float | None = None,
) -> Any:
    """Helper: propose an action and return the raw response."""
    body: dict[str, Any] = {
        "alert_id": str(alert.uuid),
        "assignment_id": assignment_uuid,
        "action_type": action_type,
        "action_subtype": action_subtype,
        "payload": payload or {"channel": "#security", "message": "Test alert"},
    }
    if confidence is not None:
        body["confidence"] = confidence
    return await test_client.post("/v1/actions", json=body, headers=headers)


# ---------------------------------------------------------------------------
# Direct DB helper: create an action row in a specific status for list/cancel tests
# ---------------------------------------------------------------------------


async def _create_action_directly(
    db: AsyncSession,
    alert: Alert,
    assignment: AlertAssignment,
    agent_registration_id: int,
    status: str = "proposed",
    action_type: str = "notification",
    action_subtype: str = "send_slack",
) -> AgentAction:
    """Insert an AgentAction row directly, bypassing the service layer."""
    repo = AgentActionRepository(db)
    action = await repo.create(
        alert_id=alert.id,
        agent_registration_id=agent_registration_id,
        assignment_id=assignment.id,
        action_type=action_type,
        action_subtype=action_subtype,
        payload={"channel": "#security", "message": "direct insert"},
        confidence=Decimal("0.80"),
    )
    # Override the default "proposed" status if needed
    if status != "proposed":
        action.status = status
        await db.flush()
        await db.refresh(action)
    return action


# ---------------------------------------------------------------------------
# TestProposeAction
# ---------------------------------------------------------------------------


class TestProposeAction:
    async def test_propose_notification_action_auto_executes(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        enriched_alert: Alert,
    ) -> None:
        """notification defaults to approval_mode=never → auto-executes (status=executing)."""
        agent, headers = agent_and_auth
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        resp = await _propose_action(
            test_client,
            enriched_alert,
            assignment["uuid"],
            headers,
            action_type="notification",
            action_subtype="send_slack",
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()["data"]
        assert data["status"] == "executing", data
        assert data["action_id"] is not None

    async def test_propose_containment_action_requires_approval(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        enriched_alert: Alert,
    ) -> None:
        """containment defaults to approval_mode=always → pending_approval with approval_request_uuid."""
        agent, headers = agent_and_auth
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        resp = await _propose_action(
            test_client,
            enriched_alert,
            assignment["uuid"],
            headers,
            action_type="containment",
            action_subtype="block_ip",
            payload={"ip": "1.2.3.4"},
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()["data"]
        assert data["status"] == "pending_approval", data
        assert data["approval_request_uuid"] is not None

    async def test_propose_action_with_high_confidence_auto_approves(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        enriched_alert: Alert,
    ) -> None:
        """Confidence >= 0.95 overrides containment's always mode → auto_approve → executing."""
        agent, headers = agent_and_auth
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        resp = await _propose_action(
            test_client,
            enriched_alert,
            assignment["uuid"],
            headers,
            action_type="containment",
            action_subtype="block_ip",
            payload={"ip": "5.6.7.8"},
            confidence=0.97,
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()["data"]
        assert data["status"] == "executing", data

    async def test_propose_action_with_low_confidence_blocks(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        enriched_alert: Alert,
    ) -> None:
        """Confidence < 0.70 overrides to block mode → immediately rejected."""
        agent, headers = agent_and_auth
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        resp = await _propose_action(
            test_client,
            enriched_alert,
            assignment["uuid"],
            headers,
            action_type="containment",
            action_subtype="block_ip",
            payload={"ip": "9.10.11.12"},
            confidence=0.60,
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()["data"]
        assert data["status"] == "rejected", data

    async def test_propose_action_unknown_alert_returns_404(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        enriched_alert: Alert,
    ) -> None:
        """Proposing an action for a non-existent alert UUID returns 404."""
        agent, headers = agent_and_auth
        # Need a valid assignment UUID — create one with the real alert first
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        body = {
            "alert_id": "00000000-0000-0000-0000-000000000000",
            "assignment_id": assignment["uuid"],
            "action_type": "notification",
            "action_subtype": "send_slack",
            "payload": {"channel": "#security", "message": "test"},
        }
        resp = await test_client.post("/v1/actions", json=body, headers=headers)
        assert resp.status_code == 404, resp.text

    async def test_propose_action_wrong_assignment_returns_403(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        db_session: AsyncSession,
    ) -> None:
        """Agent A proposing an action using Agent B's assignment returns 403."""
        agent_a, headers_a = agent_and_auth

        # Create Agent B and its alert/assignment
        _, key_b = await _create_agent_with_key(db_session, name="agent-b-ownership")
        headers_b = auth_header(key_b)

        alert_b = await create_enriched_alert(db_session, title="Alert for Agent B")
        await db_session.flush()

        assignment_b = await _checkout_alert_for_agent(test_client, alert_b, headers_b)

        # Agent A tries to propose an action using Agent B's assignment against alert_b
        body = {
            "alert_id": str(alert_b.uuid),
            "assignment_id": assignment_b["uuid"],
            "action_type": "notification",
            "action_subtype": "send_slack",
            "payload": {"channel": "#security", "message": "should fail"},
        }
        resp = await test_client.post("/v1/actions", json=body, headers=headers_a)
        assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# TestGetAction
# ---------------------------------------------------------------------------


class TestGetAction:
    async def test_get_action_by_uuid(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        admin_auth_headers: dict[str, str],
        enriched_alert: Alert,
    ) -> None:
        """GET /v1/actions/{uuid} returns the action with all expected fields."""
        _, headers = agent_and_auth
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        propose_resp = await _propose_action(
            test_client,
            enriched_alert,
            assignment["uuid"],
            headers,
            action_type="notification",
            action_subtype="send_slack",
        )
        assert propose_resp.status_code == 202, propose_resp.text
        action_uuid = propose_resp.json()["data"]["action_id"]

        # GET with admin headers (agents:read)
        resp = await test_client.get(
            f"/v1/actions/{action_uuid}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["uuid"] == action_uuid
        assert "action_type" in data
        assert "action_subtype" in data
        assert "status" in data
        assert "payload" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_get_action_not_found_returns_404(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET /v1/actions/{unknown_uuid} returns 404."""
        resp = await test_client.get(
            "/v1/actions/00000000-0000-0000-0000-000000000000",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# TestListActions
# ---------------------------------------------------------------------------


class TestListActions:
    async def test_list_actions_returns_all(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        enriched_alert: Alert,
    ) -> None:
        """Create 3 actions via the API, verify all appear in GET /v1/actions."""
        agent, headers = agent_and_auth
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        # Propose 3 actions (all notification → auto-executes)
        for i in range(3):
            r = await _propose_action(
                test_client,
                enriched_alert,
                assignment["uuid"],
                headers,
                action_type="notification",
                action_subtype=f"send_slack_{i}",
            )
            assert r.status_code == 202, r.text

        resp = await test_client.get("/v1/actions", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meta"]["total"] >= 3
        assert len(body["data"]) >= 3

    async def test_list_actions_filter_by_status(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
        enriched_alert: Alert,
    ) -> None:
        """Filter GET /v1/actions?status=pending_approval returns only matching rows."""
        agent, headers = agent_and_auth
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        # 2 containment actions → pending_approval (no confidence override)
        for i in range(2):
            r = await _propose_action(
                test_client,
                enriched_alert,
                assignment["uuid"],
                headers,
                action_type="containment",
                action_subtype=f"block_ip_{i}",
                payload={"ip": f"1.2.3.{i + 10}"},
            )
            assert r.status_code == 202, r.text

        # 1 notification action → executing
        r = await _propose_action(
            test_client,
            enriched_alert,
            assignment["uuid"],
            headers,
            action_type="notification",
            action_subtype="send_slack",
        )
        assert r.status_code == 202, r.text

        resp = await test_client.get(
            "/v1/actions?status=pending_approval",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meta"]["total"] >= 2
        for action in body["data"]:
            assert action["status"] == "pending_approval", action


# ---------------------------------------------------------------------------
# TestCancelAction
# ---------------------------------------------------------------------------


class TestCancelAction:
    async def test_cancel_proposed_action(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        db_session: AsyncSession,
        enriched_alert: Alert,
    ) -> None:
        """Cancel a proposed action — status transitions to cancelled."""
        agent, headers = agent_and_auth
        assignment_data = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        # Create the action directly in "proposed" state
        assignment_result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(
                AlertAssignment
            ).where(AlertAssignment.uuid == assignment_data["uuid"])
        )
        assignment = assignment_result.scalar_one()

        action = await _create_action_directly(
            db_session,
            enriched_alert,
            assignment,
            agent_registration_id=agent.id,
            status="proposed",
        )

        resp = await test_client.post(
            f"/v1/actions/{action.uuid}/cancel",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "cancelled", data

    async def test_cancel_pending_approval_action(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        enriched_alert: Alert,
    ) -> None:
        """Cancel a pending_approval action — status becomes cancelled, approval_request also cancelled."""
        agent, headers = agent_and_auth
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        # Containment without high confidence → pending_approval
        propose_resp = await _propose_action(
            test_client,
            enriched_alert,
            assignment["uuid"],
            headers,
            action_type="containment",
            action_subtype="block_ip",
            payload={"ip": "99.88.77.66"},
        )
        assert propose_resp.status_code == 202, propose_resp.text
        propose_data = propose_resp.json()["data"]
        assert propose_data["status"] == "pending_approval"
        action_uuid = propose_data["action_id"]

        # Cancel it
        cancel_resp = await test_client.post(
            f"/v1/actions/{action_uuid}/cancel",
            headers=headers,
        )
        assert cancel_resp.status_code == 200, cancel_resp.text
        cancel_data = cancel_resp.json()["data"]
        assert cancel_data["status"] == "cancelled", cancel_data

    async def test_cancel_completed_action_returns_409(
        self,
        test_client: AsyncClient,
        agent_and_auth: tuple[Any, dict[str, str]],
        db_session: AsyncSession,
        enriched_alert: Alert,
    ) -> None:
        """Cancelling a completed action returns 409 CONFLICT."""
        agent, headers = agent_and_auth
        assignment_data = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        # Create directly in "completed" status
        assignment_result = await db_session.execute(
            __import__("sqlalchemy", fromlist=["select"]).select(
                AlertAssignment
            ).where(AlertAssignment.uuid == assignment_data["uuid"])
        )
        assignment = assignment_result.scalar_one()

        action = await _create_action_directly(
            db_session,
            enriched_alert,
            assignment,
            agent_registration_id=agent.id,
            status="completed",
        )

        resp = await test_client.post(
            f"/v1/actions/{action.uuid}/cancel",
            headers=headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["error"]["code"] == "CONFLICT"
