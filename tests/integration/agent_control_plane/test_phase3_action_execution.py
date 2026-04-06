"""
Integration tests for Phase 3 — action execution engine.

Covers:
  Group 1: resolve_approval_mode_for_action() — pure unit tests
  Group 2: Registry behavior (subtype → integration mapping)
  Group 3: GenericWebhookIntegration.execute() — mocked HTTP
  Group 4: SlackActionIntegration.execute() — mocked HTTP
  Group 5: CrowdStrikeIntegration.execute() — mocked HTTP
  Group 6: EntraIDActionIntegration.execute() — mocked HTTP
  Group 7: Full pipeline via API (real DB, mocked external HTTP)

Constraints:
  - execute() and rollback() MUST NEVER RAISE — all error paths
    must return ExecutionResult.fail(), not raise.
  - No real external API calls — all HTTP is mocked.
  - Group 7 uses the real test PostgreSQL instance.
  - reset_registry() is called before any test that patches env vars
    to prevent registry cache poisoning between tests.
"""

from __future__ import annotations

import uuid as uuid_module
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx as httpx_module
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_action import AgentAction
from app.db.models.alert import Alert
from app.integrations.actions.base import (
    resolve_approval_mode_for_action,
)
from app.integrations.actions.crowdstrike_integration import CrowdStrikeIntegration
from app.integrations.actions.entra_id_integration import EntraIDActionIntegration
from app.integrations.actions.generic_webhook import GenericWebhookIntegration
from app.integrations.actions.null_integration import NullActionIntegration
from app.integrations.actions.registry import (
    get_integration_for_action,
    reset_registry,
)
from app.integrations.actions.slack_integration import SlackActionIntegration
from app.queue.handlers.execute_action import ExecuteResponseActionHandler
from app.queue.handlers.payloads import ExecuteResponseActionPayload
from app.repositories.agent_action_repository import AgentActionRepository

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _mock_action(
    action_type: str = "notification",
    action_subtype: str = "webhook_post",
    payload: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a minimal AgentAction mock suitable for unit tests (no DB required)."""
    action = MagicMock(spec=AgentAction)
    action.uuid = uuid_module.uuid4()
    action.action_type = action_type
    action.action_subtype = action_subtype
    action.payload = payload or {}
    return action


def _make_httpx_client(
    status_code: int,
    json_body: dict[str, Any] | None = None,
    is_success: bool | None = None,
    raise_exc: Exception | None = None,
) -> AsyncMock:
    """
    Build a mock `httpx.AsyncClient` async context manager.

    Supports post / patch / get / delete — all return the same response unless
    ``raise_exc`` is set, in which case they raise it instead.
    """
    if is_success is None:
        is_success = 200 <= status_code < 300

    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = is_success
    if json_body is not None:
        resp.json.return_value = json_body
    resp.raise_for_status = MagicMock()  # no-op unless overridden

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    if raise_exc is not None:
        client.post = AsyncMock(side_effect=raise_exc)
        client.patch = AsyncMock(side_effect=raise_exc)
        client.get = AsyncMock(side_effect=raise_exc)
        client.delete = AsyncMock(side_effect=raise_exc)
    else:
        client.post = AsyncMock(return_value=resp)
        client.patch = AsyncMock(return_value=resp)
        client.get = AsyncMock(return_value=resp)
        client.delete = AsyncMock(return_value=resp)

    return client


# ---------------------------------------------------------------------------
# Group 1: resolve_approval_mode_for_action() — pure unit tests (no DB)
# ---------------------------------------------------------------------------


class TestResolveApprovalMode:
    """Pure function tests — no fixtures, no DB, no mocking."""

    def test_never_base_mode_always_returns_never(self) -> None:
        """base_approval_mode='never' bypasses all confidence logic."""
        assert resolve_approval_mode_for_action("notification", 0.99, "never") == "never"
        assert resolve_approval_mode_for_action("notification", 0.10, "never") == "never"
        assert resolve_approval_mode_for_action("notification", None, "never") == "never"

    def test_high_confidence_returns_auto_approve(self) -> None:
        """confidence >= 0.95 → auto_approve."""
        assert resolve_approval_mode_for_action("containment", 0.97, "always") == "auto_approve"
        # Boundary: exactly 0.95
        assert resolve_approval_mode_for_action("containment", 0.95, "always") == "auto_approve"

    def test_mid_high_confidence_returns_quick_review(self) -> None:
        """0.85 <= confidence < 0.95 → quick_review."""
        assert resolve_approval_mode_for_action("containment", 0.88, "always") == "quick_review"
        # Boundary: exactly 0.85
        assert resolve_approval_mode_for_action("containment", 0.85, "always") == "quick_review"

    def test_mid_confidence_returns_human_review(self) -> None:
        """0.70 <= confidence < 0.85 → human_review."""
        assert resolve_approval_mode_for_action("containment", 0.75, "always") == "human_review"
        # Boundary: exactly 0.70
        assert resolve_approval_mode_for_action("containment", 0.70, "always") == "human_review"

    def test_low_confidence_returns_block(self) -> None:
        """confidence < 0.70 → block."""
        assert resolve_approval_mode_for_action("containment", 0.60, "always") == "block"
        assert resolve_approval_mode_for_action("containment", 0.00, "always") == "block"

    def test_bypass_confidence_override_returns_base_mode(self) -> None:
        """bypass_confidence_override=True → base_approval_mode returned, confidence ignored."""
        result = resolve_approval_mode_for_action(
            "user_validation", 0.99, "always", bypass_confidence_override=True
        )
        assert result == "always"

        # Even when confidence would otherwise auto-approve a high-stakes action
        result = resolve_approval_mode_for_action(
            "containment", 0.97, "always", bypass_confidence_override=True
        )
        assert result == "always"

    def test_none_confidence_returns_base_mode(self) -> None:
        """confidence=None (no score provided) → base_approval_mode unchanged."""
        result = resolve_approval_mode_for_action("containment", None, "always")
        assert result == "always"

        result = resolve_approval_mode_for_action("escalation", None, "quick_review")
        assert result == "quick_review"


# ---------------------------------------------------------------------------
# Group 2: Registry behavior
# ---------------------------------------------------------------------------


class TestRegistry:
    """Tests for get_integration_for_action() and _build_registry()."""

    def test_unconfigured_integrations_return_null(self) -> None:
        """With CrowdStrike/Slack unconfigured, isolate_host → NullActionIntegration."""
        # Patch is_configured on both integrations to return False
        with (
            patch.object(CrowdStrikeIntegration, "is_configured", return_value=False),
            patch.object(SlackActionIntegration, "is_configured", return_value=False),
            patch.object(EntraIDActionIntegration, "is_configured", return_value=False),
        ):
            reset_registry()
            integration = get_integration_for_action("isolate_host")
        assert isinstance(integration, NullActionIntegration)

    def test_configured_crowdstrike_registers(self) -> None:
        """When CrowdStrike is configured, isolate_host maps to CrowdStrikeIntegration."""
        with patch.object(CrowdStrikeIntegration, "is_configured", return_value=True):
            reset_registry()
            integration = get_integration_for_action("isolate_host")
        assert isinstance(integration, CrowdStrikeIntegration)

    def test_generic_webhook_always_registered(self) -> None:
        """GenericWebhookIntegration is always registered regardless of env vars."""
        reset_registry()
        integration = get_integration_for_action("webhook_post")
        assert isinstance(integration, GenericWebhookIntegration)

    def test_unknown_subtype_returns_null(self) -> None:
        """An unregistered subtype always falls back to NullActionIntegration."""
        reset_registry()
        integration = get_integration_for_action("does_not_exist_xyzzy")
        assert isinstance(integration, NullActionIntegration)


# ---------------------------------------------------------------------------
# Group 3: GenericWebhookIntegration.execute() — mocked HTTP
# ---------------------------------------------------------------------------


class TestGenericWebhookExecution:
    """Tests for GenericWebhookIntegration.execute() with mocked HTTP."""

    async def test_happy_path_returns_success(self) -> None:
        """200 response → ExecutionResult.success=True, status_code in data."""
        action = _mock_action(
            action_type="notification",
            action_subtype="webhook_post",
            payload={"url": "https://example.com/webhook", "body": {"event": "test"}},
        )
        integration = GenericWebhookIntegration()
        mock_client = _make_httpx_client(status_code=200, is_success=True)

        with (
            patch("app.integrations.actions.generic_webhook.validate_outbound_url"),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await integration.execute(action)

        assert result.success is True
        assert "200" in result.message
        assert result.data.get("status_code") == 200

    async def test_server_error_returns_failure(self) -> None:
        """500 response → ExecutionResult.success=False, message contains status code."""
        action = _mock_action(
            action_type="notification",
            action_subtype="webhook_post",
            payload={"url": "https://example.com/webhook"},
        )
        integration = GenericWebhookIntegration()
        mock_client = _make_httpx_client(status_code=500, is_success=False)

        with (
            patch("app.integrations.actions.generic_webhook.validate_outbound_url"),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await integration.execute(action)

        assert result.success is False
        assert "500" in result.message

    async def test_network_error_never_raises(self) -> None:
        """ConnectError → ExecutionResult.success=False, no exception raised."""
        action = _mock_action(
            action_type="notification",
            action_subtype="webhook_post",
            payload={"url": "https://example.com/webhook"},
        )
        integration = GenericWebhookIntegration()
        connect_error = httpx_module.ConnectError("Connection refused")
        mock_client = _make_httpx_client(status_code=0, raise_exc=connect_error)

        with (
            patch("app.integrations.actions.generic_webhook.validate_outbound_url"),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await integration.execute(action)

        # Must never raise — always returns ExecutionResult
        assert result.success is False
        assert result.message  # has some error message

    async def test_missing_url_returns_failure(self) -> None:
        """action.payload with no 'url' key → ExecutionResult.fail before any HTTP call."""
        action = _mock_action(
            action_type="notification",
            action_subtype="webhook_post",
            payload={},  # no url
        )
        integration = GenericWebhookIntegration()

        result = await integration.execute(action)

        assert result.success is False
        assert "url" in result.message.lower()


# ---------------------------------------------------------------------------
# Group 4: SlackActionIntegration.execute() — mocked HTTP
# ---------------------------------------------------------------------------


class TestSlackIntegrationExecution:
    """Tests for SlackActionIntegration.execute() with mocked Slack API."""

    async def test_send_alert_happy_path(self) -> None:
        """send_alert → Slack returns ok=True → ExecutionResult.success=True."""
        action = _mock_action(
            action_type="notification",
            action_subtype="send_alert",
            payload={"channel": "#security", "message": "Test alert triggered"},
        )
        integration = SlackActionIntegration(bot_token="xoxb-test-token")
        mock_client = _make_httpx_client(
            status_code=200,
            json_body={"ok": True, "ts": "1234567890.123456"},
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await integration.execute(action)

        assert result.success is True
        assert "#security" in result.message

    async def test_slack_api_error_returns_failure(self) -> None:
        """send_alert → Slack returns ok=False → ExecutionResult.success=False, error in message."""
        action = _mock_action(
            action_type="notification",
            action_subtype="send_alert",
            payload={"channel": "#unknown-channel", "message": "Test alert"},
        )
        integration = SlackActionIntegration(bot_token="xoxb-test-token")
        mock_client = _make_httpx_client(
            status_code=200,
            json_body={"ok": False, "error": "channel_not_found"},
        )

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await integration.execute(action)

        assert result.success is False
        assert "channel_not_found" in result.message


# ---------------------------------------------------------------------------
# Group 5: CrowdStrikeIntegration.execute() — mocked HTTP
# ---------------------------------------------------------------------------


class TestCrowdStrikeExecution:
    """Tests for CrowdStrikeIntegration with mocked OAuth + Falcon API."""

    def _configured_integration(self) -> CrowdStrikeIntegration:
        return CrowdStrikeIntegration(
            client_id="test-client-id",
            client_secret="test-client-secret",
            base_url="https://mock-api.crowdstrike.com",
        )

    async def test_isolate_host_happy_path(self) -> None:
        """isolate_host → OAuth token + contain call → success=True, rollback_supported=True."""
        action = _mock_action(
            action_type="containment",
            action_subtype="isolate_host",
            payload={"device_id": "abc123device"},
        )
        integration = self._configured_integration()

        # Two HTTP clients: token (201) then action (202)
        token_client = _make_httpx_client(
            status_code=201,
            json_body={"access_token": "mock-bearer-token", "expires_in": 1800},
        )
        action_client = _make_httpx_client(status_code=202)

        with patch("httpx.AsyncClient", side_effect=[token_client, action_client]):
            result = await integration.execute(action)

        assert result.success is True
        assert result.rollback_supported is True
        assert "abc123device" in result.message

    async def test_lift_containment_rollback(self) -> None:
        """rollback() lifts containment — reverses isolate_host. Must never raise."""
        action = _mock_action(
            action_type="containment",
            action_subtype="isolate_host",
            payload={"device_id": "abc123device"},
        )
        integration = self._configured_integration()

        token_client = _make_httpx_client(
            status_code=201,
            json_body={"access_token": "mock-bearer-token"},
        )
        rollback_client = _make_httpx_client(status_code=200)

        with patch("httpx.AsyncClient", side_effect=[token_client, rollback_client]):
            result = await integration.rollback(action)

        assert result.success is True


# ---------------------------------------------------------------------------
# Group 6: EntraIDActionIntegration.execute() — mocked HTTP
# ---------------------------------------------------------------------------


class TestEntraIDExecution:
    """Tests for EntraIDActionIntegration with mocked Microsoft Graph API."""

    def _configured_integration(self) -> EntraIDActionIntegration:
        return EntraIDActionIntegration(
            tenant_id="test-tenant-id",
            client_id="test-client-id",
            client_secret="test-client-secret",
        )

    async def test_disable_user_happy_path(self) -> None:
        """disable_user → token + PATCH /users/{id} 204 → success=True."""
        action = _mock_action(
            action_type="containment",
            action_subtype="disable_user",
            payload={"user_id": "jsmith@example.com"},
        )
        integration = self._configured_integration()

        token_client = _make_httpx_client(
            status_code=200,
            json_body={"access_token": "mock-graph-token", "expires_in": 3600},
        )
        # Graph PATCH returns 204 (No Content)
        patch_client = _make_httpx_client(status_code=204)

        with patch("httpx.AsyncClient", side_effect=[token_client, patch_client]):
            result = await integration.execute(action)

        assert result.success is True
        assert "jsmith@example.com" in result.message

    async def test_revoke_sessions_happy_path(self) -> None:
        """revoke_sessions → token + POST /revokeSignInSessions 200 → success=True."""
        action = _mock_action(
            action_type="containment",
            action_subtype="revoke_sessions",
            payload={"user_id": "jsmith@example.com"},
        )
        integration = self._configured_integration()

        token_client = _make_httpx_client(
            status_code=200,
            json_body={"access_token": "mock-graph-token"},
        )
        revoke_client = _make_httpx_client(
            status_code=200,
            json_body={"@odata.context": "...", "value": True},
        )

        with patch("httpx.AsyncClient", side_effect=[token_client, revoke_client]):
            result = await integration.execute(action)

        assert result.success is True
        assert "jsmith@example.com" in result.message


# ---------------------------------------------------------------------------
# Group 7: Full pipeline via API (real DB + mocked external HTTP)
# ---------------------------------------------------------------------------


async def _checkout_alert_for_agent(
    test_client: AsyncClient,
    alert: Alert,
    headers: dict[str, str],
) -> dict[str, Any]:
    resp = await test_client.post(
        f"/v1/queue/{alert.uuid}/checkout",
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return dict(resp.json()["data"])


class TestFullExecutionPipeline:
    """
    End-to-end tests: propose action via API → call handler directly →
    assert execution_result stored on AgentAction.

    Uses real PostgreSQL. External HTTP is mocked.
    """

    async def test_webhook_post_action_executes_and_stores_result(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        agent_and_auth: tuple[Any, dict[str, str]],
        enriched_alert: Alert,
    ) -> None:
        """
        notification/webhook_post auto-executes (approval_mode=never).
        After the handler runs, execution_result is stored on AgentAction.
        """
        agent, headers = agent_and_auth
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        body: dict[str, Any] = {
            "alert_id": str(enriched_alert.uuid),
            "assignment_id": assignment["uuid"],
            "action_type": "notification",
            "action_subtype": "webhook_post",
            "payload": {
                "url": "https://example.com/webhook",
                "body": {"event": "test_alert"},
            },
        }
        resp = await test_client.post("/v1/actions", json=body, headers=headers)
        assert resp.status_code == 202, resp.text
        action_uuid = resp.json()["data"]["action_id"]
        assert resp.json()["data"]["status"] == "executing"

        # Fetch the action from DB to get its integer ID
        action_repo = AgentActionRepository(db_session)
        action = await action_repo.get_by_uuid(uuid_module.UUID(action_uuid))
        assert action is not None
        assert action.status == "executing"

        # Simulate the worker: call the handler directly with mocked HTTP
        mock_client = _make_httpx_client(status_code=200, is_success=True)
        with (
            patch("app.integrations.actions.generic_webhook.validate_outbound_url"),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            handler = ExecuteResponseActionHandler()
            payload = ExecuteResponseActionPayload(agent_action_id=action.id)
            await handler.execute(payload, db_session)

        await db_session.refresh(action)

        assert action.execution_result is not None
        assert action.execution_result["success"] is True
        assert action.status == "completed"
        assert action.executed_at is not None

    async def test_null_integration_records_graceful_skip(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        agent_and_auth: tuple[Any, dict[str, str]],
        enriched_alert: Alert,
    ) -> None:
        """
        Unknown action_subtype → NullActionIntegration handles it gracefully.
        execution_result.success=False, message names the unhandled subtype.
        No unhandled exception is raised.
        """
        agent, headers = agent_and_auth
        assignment = await _checkout_alert_for_agent(test_client, enriched_alert, headers)

        body: dict[str, Any] = {
            "alert_id": str(enriched_alert.uuid),
            "assignment_id": assignment["uuid"],
            "action_type": "notification",
            "action_subtype": "unknown_integration_xyz",
            "payload": {"detail": "no real integration handles this"},
        }
        resp = await test_client.post("/v1/actions", json=body, headers=headers)
        assert resp.status_code == 202, resp.text
        action_uuid = resp.json()["data"]["action_id"]
        assert resp.json()["data"]["status"] == "executing"

        # Fetch action from DB
        action_repo = AgentActionRepository(db_session)
        action = await action_repo.get_by_uuid(uuid_module.UUID(action_uuid))
        assert action is not None

        # Run the handler — no HTTP mocking needed for NullActionIntegration
        reset_registry()  # ensure clean registry for this test
        handler = ExecuteResponseActionHandler()
        payload = ExecuteResponseActionPayload(agent_action_id=action.id)
        await handler.execute(payload, db_session)

        await db_session.refresh(action)

        # NullActionIntegration returns fail() — graceful, not an exception
        assert action.execution_result is not None
        assert action.execution_result["success"] is False
        assert "unknown_integration_xyz" in action.execution_result["message"]
        assert action.status == "failed"  # null = success=False → "failed"


# ---------------------------------------------------------------------------
# Phase 3 exit-criteria gap: SlackUserValidationIntegration
# ---------------------------------------------------------------------------


class TestSlackUserValidationIntegration:
    """Phase 3 exit criterion: SlackUserValidationIntegration sends DM, confirm/deny paths.

    DM sending is tested here with mocked HTTP.
    The confirm/deny callback paths (Slack button responses via webhook) are not
    yet wired to alert-status transitions; those tests are marked xfail.
    """

    def _make_integration(self) -> Any:
        from app.integrations.actions.slack_user_validation import (
            SlackUserValidationIntegration,
        )

        return SlackUserValidationIntegration(
            bot_token="xoxb-test-token-for-validation",
            db=MagicMock(),
        )

    def _make_action(
        self,
        slack_user_id: str = "U0TESTUSER",
        template_name: str | None = None,
        alert_context: dict[str, Any] | None = None,
        assignment_id: str | None = "assign-001",
    ) -> MagicMock:
        action = MagicMock(spec=AgentAction)
        action.uuid = uuid_module.uuid4()
        action.payload = {
            "slack_user_id": slack_user_id,
            "template_name": template_name,
            "alert_context": alert_context or {"title": "Suspicious login", "severity": "High"},
            "assignment_id": assignment_id,
        }
        return action

    async def test_dm_sent_returns_success_with_channel_and_ts(self) -> None:
        """execute() opens DM + posts message → ExecutionResult.ok with channel_id and ts."""
        integration = self._make_integration()
        action = self._make_action()

        open_dm_response = {"ok": True, "channel": {"id": "D0DMCHANNEL"}}
        post_msg_response = {"ok": True, "ts": "1700000000.123456"}

        # Patch _api_call to return sequential responses
        call_counter = {"n": 0}
        responses = [open_dm_response, post_msg_response]

        async def _fake_api_call(method: str, body: dict, **kwargs: Any) -> dict:
            r = responses[call_counter["n"]]
            call_counter["n"] += 1
            return r

        integration._api_call = _fake_api_call  # type: ignore[method-assign]

        result = await integration.execute(action)

        assert result.success is True, f"Expected success=True, got: {result.message}"
        assert result.data["channel_id"] == "D0DMCHANNEL"
        assert result.data["ts"] == "1700000000.123456"
        assert result.data["slack_user_id"] == "U0TESTUSER"

    async def test_execute_returns_fail_when_dm_channel_open_fails(self) -> None:
        """If conversations.open returns ok=False, execute() returns ExecutionResult.fail."""
        integration = self._make_integration()
        action = self._make_action()

        async def _fail_open(method: str, body: dict, **kwargs: Any) -> dict:
            return {"ok": False, "error": "user_not_found"}

        integration._api_call = _fail_open  # type: ignore[method-assign]

        result = await integration.execute(action)

        assert result.success is False, "Expected fail when DM channel cannot be opened"
        assert "DM channel" in result.message or "Slack" in result.message

    async def test_execute_returns_fail_when_post_message_fails(self) -> None:
        """If chat.postMessage returns ok=False, execute() returns ExecutionResult.fail."""
        integration = self._make_integration()
        action = self._make_action()

        call_counter = {"n": 0}
        responses = [
            {"ok": True, "channel": {"id": "D0TESTCHAN"}},  # conversations.open OK
            {"ok": False, "error": "channel_not_found"},    # chat.postMessage fails
        ]

        async def _partial_fail(method: str, body: dict, **kwargs: Any) -> dict:
            r = responses[call_counter["n"]]
            call_counter["n"] += 1
            return r

        integration._api_call = _partial_fail  # type: ignore[method-assign]

        result = await integration.execute(action)

        assert result.success is False
        assert "channel_not_found" in result.message or "Slack API error" in result.message

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Slack confirm/deny callback → alert status transition not yet implemented.  "
            "The SlackUserValidationIntegration sends the DM but the webhook callback "
            "handler that transitions alert status on user confirm/deny is Phase 3+ work."
        ),
    )
    async def test_confirm_callback_transitions_alert_status(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Slack confirm button callback should transition the alert to 'Closed' status."""
        # This test documents the expected confirm-path behavior.
        # When a Slack user clicks the confirm button Calseta should:
        #   1. Receive the Slack interaction payload via a callback endpoint
        #   2. Locate the alert_assignment by assignment_id in the payload
        #   3. Transition the alert status to 'Closed' (or execute on_confirm action)
        raise AssertionError(
            "Confirm callback → alert status transition not yet implemented."
        )

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Slack deny callback → denial audit log not yet implemented.  "
            "The deny path should log an activity event recording the user denial."
        ),
    )
    async def test_deny_callback_logs_denial(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Slack deny button callback should emit an activity event recording the denial."""
        raise AssertionError(
            "Deny callback activity event logging not yet implemented."
        )
