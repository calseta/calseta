"""
Tests for the workflow approval gate (Chunks 4.11–4.13).

Covers:
  - ApprovalNotifierBase contract (null, slack, teams)
  - Factory resolution from config
  - create_approval_request()
  - process_approval_decision() — approve, reject, expired, terminal, not found
  - Slack callback endpoint — signature validation, approve/reject routing
  - Teams callback endpoint — stub response
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

if TYPE_CHECKING:
    from app.workflows.notifiers.base import ApprovalRequest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_approval_request(**overrides: Any) -> ApprovalRequest:
    """Build an ApprovalRequest dataclass with sensible defaults."""
    from app.workflows.notifiers.base import ApprovalRequest

    defaults: dict[str, Any] = dict(
        approval_uuid=uuid4(),
        workflow_name="Test Workflow",
        workflow_risk_level="high",
        indicator_type="ip",
        indicator_value="1.2.3.4",
        trigger_source="agent",
        reason="Anomalous traffic detected",
        confidence=0.85,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    defaults.update(overrides)
    return ApprovalRequest(**defaults)


# ---------------------------------------------------------------------------
# NullApprovalNotifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_null_notifier_is_configured() -> None:
    from app.workflows.notifiers.null_notifier import NullApprovalNotifier

    notifier = NullApprovalNotifier()
    assert notifier.is_configured() is True


@pytest.mark.asyncio
async def test_null_notifier_send_approval_returns_empty_string() -> None:
    from app.workflows.notifiers.null_notifier import NullApprovalNotifier

    notifier = NullApprovalNotifier()
    req = _make_approval_request()
    result = await notifier.send_approval_request(req)
    assert result == ""


@pytest.mark.asyncio
async def test_null_notifier_send_result_notification_does_not_raise() -> None:
    from app.workflows.notifiers.null_notifier import NullApprovalNotifier

    notifier = NullApprovalNotifier()
    req = _make_approval_request()
    # Must not raise
    await notifier.send_result_notification(req, approved=True, responder_id="U123")


# ---------------------------------------------------------------------------
# SlackApprovalNotifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_slack_notifier_is_configured_with_token() -> None:
    from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

    cfg = MagicMock()
    cfg.SLACK_BOT_TOKEN = "xoxb-token"
    notifier = SlackApprovalNotifier(cfg)
    assert notifier.is_configured() is True


@pytest.mark.asyncio
async def test_slack_notifier_is_not_configured_without_token() -> None:
    from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

    cfg = MagicMock(spec=[])  # no attributes
    notifier = SlackApprovalNotifier(cfg)
    assert notifier.is_configured() is False


@pytest.mark.asyncio
async def test_slack_notifier_send_approval_returns_ts_on_success() -> None:
    from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

    cfg = MagicMock()
    cfg.SLACK_BOT_TOKEN = "xoxb-token"
    cfg.APPROVAL_DEFAULT_CHANNEL = "#soc"

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": True, "ts": "1234567890.000001"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        notifier = SlackApprovalNotifier(cfg)
        req = _make_approval_request()
        ts = await notifier.send_approval_request(req)

    assert ts == "1234567890.000001"


@pytest.mark.asyncio
async def test_slack_notifier_send_approval_returns_empty_on_slack_error() -> None:
    from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

    cfg = MagicMock()
    cfg.SLACK_BOT_TOKEN = "xoxb-token"
    cfg.APPROVAL_DEFAULT_CHANNEL = "#soc"

    mock_response = MagicMock()
    mock_response.json.return_value = {"ok": False, "error": "channel_not_found"}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        notifier = SlackApprovalNotifier(cfg)
        req = _make_approval_request()
        ts = await notifier.send_approval_request(req)

    assert ts == ""


@pytest.mark.asyncio
async def test_slack_notifier_send_approval_returns_empty_on_exception() -> None:
    from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

    cfg = MagicMock()
    cfg.SLACK_BOT_TOKEN = "xoxb-token"
    cfg.APPROVAL_DEFAULT_CHANNEL = "#soc"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("network error"))
        mock_client_cls.return_value = mock_client

        notifier = SlackApprovalNotifier(cfg)
        req = _make_approval_request()
        ts = await notifier.send_approval_request(req)

    assert ts == ""


@pytest.mark.asyncio
async def test_slack_notifier_send_result_does_not_raise_on_exception() -> None:
    from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

    cfg = MagicMock()
    cfg.SLACK_BOT_TOKEN = "xoxb-token"
    cfg.APPROVAL_DEFAULT_CHANNEL = "#soc"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(side_effect=Exception("network error"))
        mock_client_cls.return_value = mock_client

        notifier = SlackApprovalNotifier(cfg)
        req = _make_approval_request()
        # Must not raise
        await notifier.send_result_notification(req, approved=True, responder_id="U123")


def test_slack_build_blocks_contain_approve_reject_actions() -> None:
    from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

    cfg = MagicMock()
    notifier = SlackApprovalNotifier(cfg)
    req = _make_approval_request()
    blocks = notifier._build_approval_blocks(req)

    # Find the actions block
    action_blocks = [b for b in blocks if b["type"] == "actions"]
    assert len(action_blocks) == 1
    elements = action_blocks[0]["elements"]
    action_ids = {e["action_id"] for e in elements}
    assert f"approve:{req.approval_uuid}" in action_ids
    assert f"reject:{req.approval_uuid}" in action_ids


def test_slack_block_id_contains_approval_uuid() -> None:
    from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

    cfg = MagicMock()
    notifier = SlackApprovalNotifier(cfg)
    req = _make_approval_request()
    blocks = notifier._build_approval_blocks(req)

    action_blocks = [b for b in blocks if b["type"] == "actions"]
    assert str(req.approval_uuid) in action_blocks[0]["block_id"]


# ---------------------------------------------------------------------------
# TeamsApprovalNotifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_teams_notifier_is_configured_with_url() -> None:
    from app.workflows.notifiers.teams_notifier import TeamsApprovalNotifier

    cfg = MagicMock()
    cfg.TEAMS_WEBHOOK_URL = "https://outlook.office.com/webhook/test"
    notifier = TeamsApprovalNotifier(cfg)
    assert notifier.is_configured() is True


@pytest.mark.asyncio
async def test_teams_notifier_is_not_configured_without_url() -> None:
    from app.workflows.notifiers.teams_notifier import TeamsApprovalNotifier

    cfg = MagicMock(spec=[])  # no attributes
    notifier = TeamsApprovalNotifier(cfg)
    assert notifier.is_configured() is False


@pytest.mark.asyncio
async def test_teams_notifier_send_approval_returns_empty_string() -> None:
    """Teams webhooks don't return a threaded message ID."""
    from app.workflows.notifiers.teams_notifier import TeamsApprovalNotifier

    cfg = MagicMock()
    cfg.TEAMS_WEBHOOK_URL = "https://outlook.office.com/webhook/test"
    cfg.CALSETA_BASE_URL = "http://localhost:8000"

    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        notifier = TeamsApprovalNotifier(cfg)
        req = _make_approval_request()
        result = await notifier.send_approval_request(req)

    assert result == ""


@pytest.mark.asyncio
async def test_teams_notifier_send_approval_returns_empty_on_error() -> None:
    from app.workflows.notifiers.teams_notifier import TeamsApprovalNotifier

    cfg = MagicMock()
    cfg.TEAMS_WEBHOOK_URL = "https://outlook.office.com/webhook/test"
    cfg.CALSETA_BASE_URL = "http://localhost:8000"

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        notifier = TeamsApprovalNotifier(cfg)
        req = _make_approval_request()
        result = await notifier.send_approval_request(req)

    assert result == ""


@pytest.mark.asyncio
async def test_teams_notifier_skips_when_no_webhook_url() -> None:
    from app.workflows.notifiers.teams_notifier import TeamsApprovalNotifier

    cfg = MagicMock(spec=[])  # no attributes — is_configured returns False
    notifier = TeamsApprovalNotifier(cfg)
    req = _make_approval_request()
    result = await notifier.send_approval_request(req)
    assert result == ""


def test_teams_build_card_contains_approve_reject_urls() -> None:
    from app.workflows.notifiers.teams_notifier import TeamsApprovalNotifier

    cfg = MagicMock()
    cfg.CALSETA_BASE_URL = "http://localhost:8000"
    notifier = TeamsApprovalNotifier(cfg)
    req = _make_approval_request()
    card = notifier._build_approval_card(req)

    content_str = json.dumps(card)
    assert f"/v1/workflow-approvals/{req.approval_uuid}/approve" in content_str
    assert f"/v1/workflow-approvals/{req.approval_uuid}/reject" in content_str


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_null_for_none() -> None:
    from app.workflows.notifiers.factory import get_approval_notifier
    from app.workflows.notifiers.null_notifier import NullApprovalNotifier

    cfg = MagicMock()
    cfg.APPROVAL_NOTIFIER = "none"
    assert isinstance(get_approval_notifier(cfg), NullApprovalNotifier)


def test_factory_returns_null_for_unrecognised() -> None:
    from app.workflows.notifiers.factory import get_approval_notifier
    from app.workflows.notifiers.null_notifier import NullApprovalNotifier

    cfg = MagicMock()
    cfg.APPROVAL_NOTIFIER = "pagerduty"
    assert isinstance(get_approval_notifier(cfg), NullApprovalNotifier)


def test_factory_returns_slack_notifier() -> None:
    from app.workflows.notifiers.factory import get_approval_notifier
    from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

    cfg = MagicMock()
    cfg.APPROVAL_NOTIFIER = "slack"
    assert isinstance(get_approval_notifier(cfg), SlackApprovalNotifier)


def test_factory_returns_teams_notifier() -> None:
    from app.workflows.notifiers.factory import get_approval_notifier
    from app.workflows.notifiers.teams_notifier import TeamsApprovalNotifier

    cfg = MagicMock()
    cfg.APPROVAL_NOTIFIER = "teams"
    assert isinstance(get_approval_notifier(cfg), TeamsApprovalNotifier)


def test_factory_is_case_insensitive() -> None:
    from app.workflows.notifiers.factory import get_approval_notifier
    from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

    cfg = MagicMock()
    cfg.APPROVAL_NOTIFIER = "SLACK"
    assert isinstance(get_approval_notifier(cfg), SlackApprovalNotifier)


# ---------------------------------------------------------------------------
# Slack callback endpoint
# ---------------------------------------------------------------------------


def _make_slack_signature(secret: str, ts: str, body: str) -> str:
    sig_base = f"v0:{ts}:{body}"
    return "v0=" + hmac.new(secret.encode(), sig_base.encode(), hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_slack_callback_missing_payload_returns_400() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    with patch("app.api.v1.approvals.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = ""
        resp = client.post(
            "/v1/workflow-approvals/callback/slack",
            data={},  # no payload field
            headers={
                "Authorization": "Bearer cai_test",
                "X-Slack-Request-Timestamp": str(int(time.time())),
                "X-Slack-Signature": "v0=invalid",
            },
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_slack_callback_stale_timestamp_returns_403() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    # Patch the settings object already bound in the approvals module
    with patch("app.api.v1.approvals.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = "test-secret"

        old_ts = str(int(time.time()) - 400)  # > 5 min ago
        resp = client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": "{}"},
            headers={
                "X-Slack-Request-Timestamp": old_ts,
                "X-Slack-Signature": "v0=anything",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_slack_callback_invalid_signature_returns_403() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    with patch("app.api.v1.approvals.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = "real-secret"

        ts = str(int(time.time()))
        resp = client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": json.dumps({"actions": []})},
            headers={
                "X-Slack-Request-Timestamp": ts,
                "X-Slack-Signature": "v0=wrongsignature",
            },
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_slack_callback_no_actions_returns_ok() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    payload = json.dumps({"actions": []})
    with patch("app.api.v1.approvals.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = ""
        resp = client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": payload},
        )
    assert resp.status_code == 200
    assert resp.text == "ok"


@pytest.mark.asyncio
async def test_slack_callback_invalid_action_id_format_returns_ok() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    payload = json.dumps({
        "actions": [{"action_id": "no-colon-here", "value": "x"}],
        "user": {"id": "U123"},
    })
    with patch("app.api.v1.approvals.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = ""
        resp = client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": payload},
        )
    assert resp.status_code == 200
    assert resp.text == "ok"


@pytest.mark.asyncio
async def test_slack_callback_invalid_uuid_returns_ok() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    client = TestClient(app)

    payload = json.dumps({
        "actions": [{"action_id": "approve:not-a-uuid", "value": "x"}],
        "user": {"id": "U123"},
    })
    with patch("app.api.v1.approvals.settings") as mock_settings:
        mock_settings.SLACK_SIGNING_SECRET = ""
        resp = client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": payload},
        )
    assert resp.status_code == 200
    assert resp.text == "ok"


@pytest.mark.asyncio
async def test_slack_callback_routes_approve_decision() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    approval_uuid = uuid4()
    payload = json.dumps({
        "actions": [{"action_id": f"approve:{approval_uuid}", "value": str(approval_uuid)}],
        "user": {"id": "U_APPROVER"},
    })

    mock_decide = AsyncMock(return_value=MagicMock())

    # Imports inside slack_callback are local — patch at source modules
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    app = create_app()
    client = TestClient(app)

    with patch("app.api.v1.approvals.settings") as mock_settings, \
         patch("app.db.session.AsyncSessionLocal", return_value=mock_session), \
         patch("app.workflows.approval.process_approval_decision", mock_decide):
        mock_settings.SLACK_SIGNING_SECRET = ""
        resp = client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": payload},
        )

    assert resp.status_code == 200
    assert resp.text == "ok"
    mock_decide.assert_called_once()
    call_kwargs = mock_decide.call_args.kwargs
    assert call_kwargs["approval_uuid"] == approval_uuid
    assert call_kwargs["approved"] is True
    assert call_kwargs["responder_id"] == "U_APPROVER"


@pytest.mark.asyncio
async def test_slack_callback_routes_reject_decision() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    approval_uuid = uuid4()
    payload = json.dumps({
        "actions": [{"action_id": f"reject:{approval_uuid}", "value": str(approval_uuid)}],
        "user": {"id": "U_REJECTOR"},
    })

    mock_decide = AsyncMock(return_value=MagicMock())

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()

    app = create_app()
    client = TestClient(app)

    with patch("app.api.v1.approvals.settings") as mock_settings, \
         patch("app.db.session.AsyncSessionLocal", return_value=mock_session), \
         patch("app.workflows.approval.process_approval_decision", mock_decide):
        mock_settings.SLACK_SIGNING_SECRET = ""
        resp = client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": payload},
        )

    assert resp.status_code == 200
    call_kwargs = mock_decide.call_args.kwargs
    assert call_kwargs["approved"] is False
    assert call_kwargs["responder_id"] == "U_REJECTOR"


# ---------------------------------------------------------------------------
# Teams callback endpoint — stub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_teams_callback_returns_explanation() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.post("/v1/workflow-approvals/callback/teams")
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "REST API" in data["message"]


# ---------------------------------------------------------------------------
# process_approval_decision unit tests (pure logic, mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_approval_decision_not_found_raises() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from app.workflows.approval import process_approval_decision

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="not found"):
        await process_approval_decision(
            approval_uuid=uuid4(),
            approved=True,
            responder_id=None,
            db=mock_db,
        )


@pytest.mark.asyncio
async def test_process_approval_decision_already_terminal_raises() -> None:
    from app.workflows.approval import process_approval_decision

    mock_request = MagicMock()
    mock_request.status = "approved"  # already decided

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_request

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="terminal status"):
        await process_approval_decision(
            approval_uuid=uuid4(),
            approved=True,
            responder_id=None,
            db=mock_db,
        )


@pytest.mark.asyncio
async def test_process_approval_decision_expired_raises() -> None:
    from app.workflows.approval import process_approval_decision

    mock_request = MagicMock()
    mock_request.status = "pending"
    mock_request.expires_at = datetime.now(UTC) - timedelta(hours=2)  # expired

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_request

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()

    with pytest.raises(ValueError, match="expired"):
        await process_approval_decision(
            approval_uuid=uuid4(),
            approved=True,
            responder_id=None,
            db=mock_db,
        )

    assert mock_request.status == "expired"


@pytest.mark.asyncio
async def test_process_approval_decision_approve_enqueues_task() -> None:
    from app.workflows.approval import process_approval_decision

    mock_request = MagicMock()
    mock_request.status = "pending"
    mock_request.expires_at = datetime.now(UTC) + timedelta(hours=1)
    mock_request.id = 42

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_request

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()

    mock_queue = AsyncMock()
    mock_queue.enqueue = AsyncMock()

    # get_queue_backend is a local import inside process_approval_decision
    with patch("app.queue.factory.get_queue_backend", return_value=mock_queue):
        result = await process_approval_decision(
            approval_uuid=uuid4(),
            approved=True,
            responder_id="U123",
            db=mock_db,
        )

    assert result.status == "approved"
    assert result.responder_id == "U123"
    mock_queue.enqueue.assert_called_once()
    call_args = mock_queue.enqueue.call_args
    assert call_args.args[0] == "execute_approved_workflow_task"
    assert call_args.args[1] == {"approval_request_id": 42}


@pytest.mark.asyncio
async def test_process_approval_decision_reject_does_not_enqueue() -> None:
    from app.workflows.approval import process_approval_decision

    mock_request = MagicMock()
    mock_request.status = "pending"
    mock_request.expires_at = datetime.now(UTC) + timedelta(hours=1)
    mock_request.id = 42

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_request

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.flush = AsyncMock()

    mock_queue = AsyncMock()

    with patch("app.queue.factory.get_queue_backend", return_value=mock_queue):
        result = await process_approval_decision(
            approval_uuid=uuid4(),
            approved=False,
            responder_id="U_REJECTOR",
            db=mock_db,
        )

    assert result.status == "rejected"
    mock_queue.enqueue.assert_not_called()
