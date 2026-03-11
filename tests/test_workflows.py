"""
Comprehensive tests for the workflow engine and approval gate (Chunk 8.3).

Covers:
  - Workflow sandbox: happy path, failure, timeout, syntax errors, missing run()
  - Workflow AST validation: allowed imports, blocked imports, blocked builtins
  - WorkflowResult and WorkflowLogger
  - Workflow version history: code updates increment version, old code preserved
  - Workflow execute endpoint: enqueues task, validates state
  - Workflow test endpoint: sandboxed execution
  - Workflow approval gate:
    - Agent-triggered with approval_mode="always" creates approval request
    - Human-triggered bypasses approval gate
    - Approve -> workflow executes (enqueues task)
    - Reject -> workflow does NOT execute
    - Double approve/reject -> 409 Conflict
    - Expired approval -> 409 Conflict
  - Workflow run audit logging

This file tests workflows at the unit level (no DB) and at the
integration level (via the FastAPI test client with a real DB session).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio

from app.services.workflow_ast import validate_workflow_code
from app.workflows.context import WorkflowContext, WorkflowLogger, WorkflowResult
from app.workflows.sandbox import run_workflow_code

# ---------------------------------------------------------------------------
# Fixtures — mock_queue for integration tests that need a task queue
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_queue() -> AsyncGenerator[AsyncMock, None]:
    """
    Mock the task queue in both DI-injected and direct-import paths.

    Mirrors the same fixture in tests/integration/conftest.py.
    """
    from app.main import app
    from app.queue.dependencies import get_queue

    mock = AsyncMock()
    mock.enqueue.return_value = "mock-task-id"

    app.dependency_overrides[get_queue] = lambda: mock

    with patch("app.queue.factory.get_queue_backend", return_value=mock):
        yield mock

    app.dependency_overrides.pop(get_queue, None)


@pytest_asyncio.fixture
async def agent_api_key(db_session: Any) -> str:
    """
    Creates a test API key with admin scope and key_type='agent'.

    Used for tests that need agent-triggered workflow execution.
    """
    import secrets as _secrets

    import bcrypt

    from app.db.models.api_key import APIKey

    plain_key = "cai_" + _secrets.token_urlsafe(32)
    key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt()).decode()
    key_prefix = plain_key[:8]

    record = APIKey(
        name="test-agent-key",
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=["admin"],
        is_active=True,
        key_type="agent",
    )
    db_session.add(record)
    await db_session.flush()

    return plain_key


# ===========================================================================
# Helpers
# ===========================================================================


def _make_ctx() -> WorkflowContext:
    """Create a minimal WorkflowContext for sandbox testing."""
    from app.workflows.context import (
        IndicatorContext,
        IntegrationClients,
        SecretsAccessor,
    )

    indicator = IndicatorContext(
        uuid=uuid4(),
        type="ip",
        value="1.2.3.4",
        malice="Pending",
        is_enriched=False,
        enrichment_results=None,
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    return WorkflowContext(
        indicator=indicator,
        alert=None,
        http=MagicMock(),
        log=WorkflowLogger(),
        secrets=SecretsAccessor(),
        integrations=IntegrationClients(),
    )


# ===========================================================================
# Unit: WorkflowResult
# ===========================================================================


class TestWorkflowResult:
    def test_ok_creates_success_true(self) -> None:
        r = WorkflowResult.ok("all good", {"count": 3})
        assert r.success is True
        assert r.message == "all good"
        assert r.data["count"] == 3

    def test_ok_default_message(self) -> None:
        r = WorkflowResult.ok()
        assert r.success is True
        assert r.message == "OK"
        assert r.data == {}

    def test_fail_creates_success_false(self) -> None:
        r = WorkflowResult.fail("bad thing")
        assert r.success is False
        assert r.message == "bad thing"
        assert r.data == {}

    def test_fail_with_data(self) -> None:
        r = WorkflowResult.fail("error", {"detail": "info"})
        assert r.success is False
        assert r.data["detail"] == "info"


# ===========================================================================
# Unit: WorkflowLogger
# ===========================================================================


class TestWorkflowLogger:
    def test_info_appended(self) -> None:
        log = WorkflowLogger()
        log.info("test message", key="value")
        output = log.render()
        assert "test message" in output
        assert "info" in output

    def test_multiple_levels(self) -> None:
        log = WorkflowLogger()
        log.info("info msg")
        log.warning("warn msg")
        log.error("error msg")
        log.debug("debug msg")
        output = log.render()
        assert "info msg" in output
        assert "warn msg" in output
        assert "error msg" in output
        assert "debug msg" in output

    def test_render_is_json_lines(self) -> None:
        import json

        log = WorkflowLogger()
        log.info("hello")
        log.error("world")
        lines = log.render().split("\n")
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert "level" in parsed
            assert "message" in parsed
            assert "ts" in parsed

    def test_callable_shorthand(self) -> None:
        """ctx.log('msg') should work as shorthand for ctx.log.info('msg')."""
        log = WorkflowLogger()
        log("shorthand message")
        output = log.render()
        assert "shorthand message" in output
        assert "info" in output

    def test_empty_render(self) -> None:
        log = WorkflowLogger()
        assert log.render() == ""

    def test_extra_kwargs_captured(self) -> None:
        import json

        log = WorkflowLogger()
        log.info("with extras", ip="1.2.3.4", count=5)
        output = log.render()
        parsed = json.loads(output)
        assert parsed["extra"]["ip"] == "1.2.3.4"
        assert parsed["extra"]["count"] == 5


# ===========================================================================
# Unit: Workflow sandbox — successful execution
# ===========================================================================


class TestSandboxHappyPath:
    @pytest.mark.asyncio
    async def test_successful_execution_returns_ok(self) -> None:
        code = """\
from app.workflows.context import WorkflowResult

async def run(ctx):
    return WorkflowResult.ok("success", {"ip": ctx.indicator.value})
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is True
        assert result.message == "success"
        assert result.data["ip"] == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_log_output_captured(self) -> None:
        code = """\
from app.workflows.context import WorkflowResult

async def run(ctx):
    ctx.log.info("starting workflow", indicator=ctx.indicator.value)
    ctx.log.warning("this is a warning")
    return WorkflowResult.ok("done")
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is True
        log_output = ctx.log.render()
        assert "starting workflow" in log_output
        assert "this is a warning" in log_output

    @pytest.mark.asyncio
    async def test_allowed_import_json(self) -> None:
        """Workflow code can import json (whitelisted stdlib module)."""
        code = """\
import json
from app.workflows.context import WorkflowResult

async def run(ctx):
    data = json.dumps({"value": ctx.indicator.value})
    return WorkflowResult.ok("ok", {"json_str": data})
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_allowed_import_datetime(self) -> None:
        code = """\
from datetime import datetime
from app.workflows.context import WorkflowResult

async def run(ctx):
    return WorkflowResult.ok("ok", {"year": datetime.now().year})
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is True


# ===========================================================================
# Unit: Workflow sandbox — failure and error handling
# ===========================================================================


class TestSandboxFailure:
    @pytest.mark.asyncio
    async def test_fail_result_returned(self) -> None:
        code = """\
from app.workflows.context import WorkflowResult

async def run(ctx):
    return WorkflowResult.fail("something went wrong")
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is False
        assert "something went wrong" in result.message

    @pytest.mark.asyncio
    async def test_exception_in_run_returns_fail(self) -> None:
        code = """\
async def run(ctx):
    raise ValueError("unexpected error in workflow")
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is False
        assert "unexpected error in workflow" in result.message

    @pytest.mark.asyncio
    async def test_module_level_exception_returns_fail(self) -> None:
        code = """\
x = 1 / 0

async def run(ctx):
    return None
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is False
        assert "module load" in result.message

    @pytest.mark.asyncio
    async def test_syntax_error_returns_fail(self) -> None:
        code = "def run(ctx\n    return None"
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is False
        assert "syntax error" in result.message.lower()

    @pytest.mark.asyncio
    async def test_missing_run_function_returns_fail(self) -> None:
        code = """\
def not_run(ctx):
    return "oops"
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is False
        assert "run" in result.message.lower()

    @pytest.mark.asyncio
    async def test_sync_run_returns_fail(self) -> None:
        code = """\
def run(ctx):
    return "sync"
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is False
        assert "async" in result.message.lower()

    @pytest.mark.asyncio
    async def test_non_workflow_result_return_type_fails(self) -> None:
        """run() returning a non-WorkflowResult object should fail."""
        code = """\
async def run(ctx):
    return {"success": True, "message": "ok"}
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is False
        assert "unexpected type" in result.message.lower() or "WorkflowResult" in result.message


# ===========================================================================
# Unit: Workflow sandbox — timeout
# ===========================================================================


class TestSandboxTimeout:
    @pytest.mark.asyncio
    async def test_timeout_returns_fail(self) -> None:
        code = """\
import asyncio

async def run(ctx):
    await asyncio.sleep(100)
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=1)
        assert result.success is False
        assert "timed out" in result.message.lower()


# ===========================================================================
# Unit: Workflow sandbox — blocked builtins
# ===========================================================================


class TestSandboxBlockedBuiltins:
    @pytest.mark.asyncio
    async def test_open_not_available(self) -> None:
        code = """\
from app.workflows.context import WorkflowResult

async def run(ctx):
    try:
        open("/etc/passwd")
    except NameError:
        return WorkflowResult.fail("open not available")
    return WorkflowResult.ok("open was available (bad)")
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is False
        assert "open not available" in result.message

    @pytest.mark.asyncio
    async def test_exec_not_available(self) -> None:
        code = """\
from app.workflows.context import WorkflowResult

async def run(ctx):
    try:
        exec("x = 1")
    except NameError:
        return WorkflowResult.fail("exec not available")
    return WorkflowResult.ok("exec was available (bad)")
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is False
        assert "exec not available" in result.message

    @pytest.mark.asyncio
    async def test_eval_not_available(self) -> None:
        code = """\
from app.workflows.context import WorkflowResult

async def run(ctx):
    try:
        eval("1+1")
    except NameError:
        return WorkflowResult.fail("eval not available")
    return WorkflowResult.ok("eval was available (bad)")
"""
        ctx = _make_ctx()
        result = await run_workflow_code(code, ctx, timeout=10)
        assert result.success is False
        assert "eval not available" in result.message


# ===========================================================================
# Unit: Workflow AST validation
# ===========================================================================


class TestWorkflowASTValidation:
    def test_valid_minimal_code(self) -> None:
        errors = validate_workflow_code("async def run(ctx):\n    return ctx\n")
        assert errors == []

    def test_valid_with_allowed_imports(self) -> None:
        code = """\
import json
import re
from datetime import datetime

async def run(ctx):
    return ctx
"""
        assert validate_workflow_code(code) == []

    def test_valid_with_calseta_import(self) -> None:
        code = """\
from calseta.workflows import WorkflowResult

async def run(ctx):
    return WorkflowResult(success=True, message="ok", data={})
"""
        assert validate_workflow_code(code) == []

    def test_valid_with_app_workflows_import(self) -> None:
        code = """\
from app.workflows.context import WorkflowResult

async def run(ctx):
    return WorkflowResult.ok("done")
"""
        assert validate_workflow_code(code) == []

    def test_missing_run_function_error(self) -> None:
        errors = validate_workflow_code("def not_run(ctx):\n    return ctx\n")
        assert any("async function named 'run'" in e for e in errors)

    def test_sync_run_not_valid(self) -> None:
        errors = validate_workflow_code("def run(ctx):\n    return ctx\n")
        assert any("async function named 'run'" in e for e in errors)

    def test_empty_code_error(self) -> None:
        errors = validate_workflow_code("")
        assert any("async function named 'run'" in e for e in errors)

    def test_import_os_blocked(self) -> None:
        code = "import os\n\nasync def run(ctx):\n    return os.getcwd()\n"
        errors = validate_workflow_code(code)
        assert any("'os'" in e for e in errors)

    def test_import_subprocess_blocked(self) -> None:
        code = "import subprocess\n\nasync def run(ctx):\n    return None\n"
        errors = validate_workflow_code(code)
        assert any("'subprocess'" in e for e in errors)

    def test_import_sys_blocked(self) -> None:
        code = "import sys\n\nasync def run(ctx):\n    return None\n"
        errors = validate_workflow_code(code)
        assert any("'sys'" in e for e in errors)

    def test_import_socket_blocked(self) -> None:
        code = "import socket\n\nasync def run(ctx):\n    return None\n"
        errors = validate_workflow_code(code)
        assert any("'socket'" in e for e in errors)

    def test_import_importlib_blocked(self) -> None:
        code = "import importlib\n\nasync def run(ctx):\n    return None\n"
        errors = validate_workflow_code(code)
        assert any("'importlib'" in e for e in errors)

    def test_from_os_import_blocked(self) -> None:
        code = "from os import path\n\nasync def run(ctx):\n    return None\n"
        errors = validate_workflow_code(code)
        assert any("'os'" in e for e in errors)

    def test_unknown_import_blocked(self) -> None:
        code = "import requests\n\nasync def run(ctx):\n    return None\n"
        errors = validate_workflow_code(code)
        assert any("'requests'" in e for e in errors)

    def test_exec_call_blocked(self) -> None:
        code = 'async def run(ctx):\n    exec("import os")\n'
        errors = validate_workflow_code(code)
        assert any("'exec'" in e for e in errors)

    def test_eval_call_blocked(self) -> None:
        code = 'async def run(ctx):\n    result = eval("1 + 1")\n'
        errors = validate_workflow_code(code)
        assert any("'eval'" in e for e in errors)

    def test_open_call_blocked(self) -> None:
        code = 'async def run(ctx):\n    with open("/etc/passwd") as f:\n        return f.read()\n'
        errors = validate_workflow_code(code)
        assert any("'open'" in e for e in errors)

    def test_compile_call_blocked(self) -> None:
        code = 'async def run(ctx):\n    code = compile("1+1", "<string>", "eval")\n'
        errors = validate_workflow_code(code)
        assert any("'compile'" in e for e in errors)

    def test_syntax_error(self) -> None:
        errors = validate_workflow_code("def run(ctx\n    return ctx")
        assert any("Syntax error" in e for e in errors)

    def test_multiple_violations_all_reported(self) -> None:
        code = """\
import os
import sys

async def run(ctx):
    exec("bad")
    return os.getcwd()
"""
        errors = validate_workflow_code(code)
        assert len(errors) >= 3  # import os, import sys, exec


# ===========================================================================
# Unit: process_approval_decision
# ===========================================================================


class TestProcessApprovalDecision:
    @pytest.mark.asyncio
    async def test_not_found_raises(self) -> None:
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
    async def test_already_terminal_raises(self) -> None:
        from app.workflows.approval import process_approval_decision

        mock_request = MagicMock()
        mock_request.status = "approved"

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
    async def test_already_rejected_is_terminal(self) -> None:
        from app.workflows.approval import process_approval_decision

        mock_request = MagicMock()
        mock_request.status = "rejected"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_request

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="terminal status"):
            await process_approval_decision(
                approval_uuid=uuid4(),
                approved=False,
                responder_id=None,
                db=mock_db,
            )

    @pytest.mark.asyncio
    async def test_expired_raises_and_sets_status(self) -> None:
        from app.workflows.approval import process_approval_decision

        mock_request = MagicMock()
        mock_request.status = "pending"
        mock_request.expires_at = datetime.now(UTC) - timedelta(hours=2)

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
    async def test_approve_enqueues_task(self) -> None:
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

        with patch("app.queue.factory.get_queue_backend", return_value=mock_queue):
            result = await process_approval_decision(
                approval_uuid=uuid4(),
                approved=True,
                responder_id="U123",
                db=mock_db,
            )

        assert result.status == "approved"
        assert result.responder_id == "U123"
        assert result.responded_at is not None
        mock_queue.enqueue.assert_called_once()
        call_args = mock_queue.enqueue.call_args
        assert call_args.args[0] == "execute_approved_workflow_task"
        assert call_args.args[1] == {"approval_request_id": 42}

    @pytest.mark.asyncio
    async def test_reject_does_not_enqueue(self) -> None:
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


# ===========================================================================
# Unit: create_approval_request
# ===========================================================================


class TestCreateApprovalRequest:
    @pytest.mark.asyncio
    async def test_creates_pending_request(self) -> None:
        from app.workflows.approval import create_approval_request

        mock_workflow = MagicMock()
        mock_workflow.id = 1
        mock_workflow.approval_timeout_seconds = 3600
        mock_workflow.approval_channel = "#soc"

        mock_cfg = MagicMock()
        mock_cfg.APPROVAL_DEFAULT_TIMEOUT_SECONDS = 300

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        request = await create_approval_request(
            workflow=mock_workflow,
            trigger_type="agent",
            trigger_agent_key_prefix="cai_test",
            trigger_context={"indicator_type": "ip", "indicator_value": "1.2.3.4"},
            reason="Anomalous traffic",
            confidence=0.85,
            notifier_type="slack",
            db=mock_db,
            cfg=mock_cfg,
        )

        assert request.status == "pending"
        assert request.workflow_id == 1
        assert request.trigger_type == "agent"
        assert request.reason == "Anomalous traffic"
        assert request.confidence == 0.85
        assert request.notifier_type == "slack"
        assert request.notifier_channel == "#soc"
        assert request.expires_at is not None
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_cfg_timeout_when_workflow_has_none(self) -> None:
        from app.workflows.approval import create_approval_request

        mock_workflow = MagicMock()
        mock_workflow.id = 1
        mock_workflow.approval_timeout_seconds = None
        mock_workflow.approval_channel = None

        mock_cfg = MagicMock()
        mock_cfg.APPROVAL_DEFAULT_TIMEOUT_SECONDS = 600

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        before = datetime.now(UTC)
        request = await create_approval_request(
            workflow=mock_workflow,
            trigger_type="agent",
            trigger_agent_key_prefix="cai_test",
            trigger_context={},
            reason="test",
            confidence=0.5,
            notifier_type="none",
            db=mock_db,
            cfg=mock_cfg,
        )
        after = datetime.now(UTC)

        # expires_at should be ~600 seconds from now
        expected_min = before + timedelta(seconds=599)
        expected_max = after + timedelta(seconds=601)
        assert expected_min <= request.expires_at <= expected_max


# ===========================================================================
# Unit: Approval notifier factory
# ===========================================================================


class TestApprovalNotifierFactory:
    def test_returns_null_for_none(self) -> None:
        from app.workflows.notifiers.factory import get_approval_notifier
        from app.workflows.notifiers.null_notifier import NullApprovalNotifier

        cfg = MagicMock()
        cfg.APPROVAL_NOTIFIER = "none"
        assert isinstance(get_approval_notifier(cfg), NullApprovalNotifier)

    def test_returns_null_for_unknown(self) -> None:
        from app.workflows.notifiers.factory import get_approval_notifier
        from app.workflows.notifiers.null_notifier import NullApprovalNotifier

        cfg = MagicMock()
        cfg.APPROVAL_NOTIFIER = "pagerduty"
        assert isinstance(get_approval_notifier(cfg), NullApprovalNotifier)

    def test_returns_slack_notifier(self) -> None:
        from app.workflows.notifiers.factory import get_approval_notifier
        from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

        cfg = MagicMock()
        cfg.APPROVAL_NOTIFIER = "slack"
        assert isinstance(get_approval_notifier(cfg), SlackApprovalNotifier)

    def test_returns_teams_notifier(self) -> None:
        from app.workflows.notifiers.factory import get_approval_notifier
        from app.workflows.notifiers.teams_notifier import TeamsApprovalNotifier

        cfg = MagicMock()
        cfg.APPROVAL_NOTIFIER = "teams"
        assert isinstance(get_approval_notifier(cfg), TeamsApprovalNotifier)

    def test_is_case_insensitive(self) -> None:
        from app.workflows.notifiers.factory import get_approval_notifier
        from app.workflows.notifiers.slack_notifier import SlackApprovalNotifier

        cfg = MagicMock()
        cfg.APPROVAL_NOTIFIER = "SLACK"
        assert isinstance(get_approval_notifier(cfg), SlackApprovalNotifier)


# ===========================================================================
# Unit: NullApprovalNotifier
# ===========================================================================


class TestNullNotifier:
    @pytest.mark.asyncio
    async def test_is_configured(self) -> None:
        from app.workflows.notifiers.null_notifier import NullApprovalNotifier

        assert NullApprovalNotifier().is_configured() is True

    @pytest.mark.asyncio
    async def test_send_returns_empty(self) -> None:
        from app.workflows.notifiers.base import ApprovalRequest
        from app.workflows.notifiers.null_notifier import NullApprovalNotifier

        notifier = NullApprovalNotifier()
        req = ApprovalRequest(
            approval_uuid=uuid4(),
            workflow_name="test",
            workflow_risk_level="low",
            indicator_type="ip",
            indicator_value="1.2.3.4",
            trigger_source="agent",
            reason="test",
            confidence=0.5,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        result = await notifier.send_approval_request(req)
        assert result == ""


# ===========================================================================
# Integration: Workflow CRUD and execution endpoints
# ===========================================================================


VALID_WORKFLOW_CODE = (
    "async def run(ctx):\n"
    "    return ctx.success('ok')\n"
)


class TestWorkflowCRUDIntegration:
    """Integration tests for workflow CRUD via the API."""

    @pytest.mark.asyncio
    async def test_create_201(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Test Create Workflow",
                "workflow_type": "indicator",
                "indicator_types": ["ip"],
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "timeout_seconds": 30,
                "retry_count": 1,
                "is_active": True,
                "tags": ["test"],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Test Create Workflow"
        assert "uuid" in data
        assert "code" in data
        assert data["code_version"] == 1

    @pytest.mark.asyncio
    async def test_create_invalid_code_400(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Bad Code",
                "workflow_type": "indicator",
                "indicator_types": ["ip"],
                "code": "import os\nos.system('rm -rf /')",
                "state": "active",
                "timeout_seconds": 30,
                "retry_count": 1,
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "WORKFLOW_CODE_INVALID"

    @pytest.mark.asyncio
    async def test_list_excludes_code(
        self, test_client: Any, api_key: str
    ) -> None:
        # Create a workflow
        await test_client.post(
            "/v1/workflows",
            json={
                "name": "List Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

        resp = await test_client.get(
            "/v1/workflows",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        for s in resp.json()["data"]:
            assert "code" not in s

    @pytest.mark.asyncio
    async def test_get_by_uuid_includes_code(
        self, test_client: Any, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Get Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.get(
            f"/v1/workflows/{wf_uuid}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        assert "code" in resp.json()["data"]

    @pytest.mark.asyncio
    async def test_get_404(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/workflows/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 404


# ===========================================================================
# Integration: Workflow version history
# ===========================================================================


class TestWorkflowVersionHistory:
    @pytest.mark.asyncio
    async def test_patch_code_increments_version(
        self, test_client: Any, api_key: str
    ) -> None:
        """Patching code should increment code_version and preserve old version."""
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Version History Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert create_resp.status_code == 201
        data = create_resp.json()["data"]
        wf_uuid = data["uuid"]
        assert data["code_version"] == 1

        # Patch with new code
        new_code = "async def run(ctx):\n    return ctx.success('updated')\n"
        patch_resp = await test_client.patch(
            f"/v1/workflows/{wf_uuid}",
            json={"code": new_code},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert patch_resp.status_code == 200
        patched = patch_resp.json()["data"]
        assert patched["code_version"] == 2

    @pytest.mark.asyncio
    async def test_versions_endpoint_returns_history(
        self, test_client: Any, api_key: str
    ) -> None:
        """After a code update, the versions endpoint should list the old version."""
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Version List Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        # Patch code to create a version entry
        new_code = "async def run(ctx):\n    return ctx.success('v2')\n"
        await test_client.patch(
            f"/v1/workflows/{wf_uuid}",
            json={"code": new_code},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        # Check versions
        versions_resp = await test_client.get(
            f"/v1/workflows/{wf_uuid}/versions",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert versions_resp.status_code == 200
        versions = versions_resp.json()["data"]
        assert len(versions) >= 1
        assert versions[0]["version"] == 1  # Old version preserved

    @pytest.mark.asyncio
    async def test_patch_non_code_field_does_not_increment_version(
        self, test_client: Any, api_key: str
    ) -> None:
        """Patching a non-code field should NOT change code_version."""
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "No Version Bump",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]
        original_version = create_resp.json()["data"]["code_version"]

        patch_resp = await test_client.patch(
            f"/v1/workflows/{wf_uuid}",
            json={"name": "Renamed Workflow"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["data"]["code_version"] == original_version

    @pytest.mark.asyncio
    async def test_patch_invalid_code_rejected_400(
        self, test_client: Any, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Patch Invalid Code",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.patch(
            f"/v1/workflows/{wf_uuid}",
            json={"code": "import os"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 400


# ===========================================================================
# Integration: Workflow test endpoint
# ===========================================================================


class TestWorkflowTestEndpointIntegration:
    @pytest.mark.asyncio
    async def test_test_endpoint_200(
        self, test_client: Any, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Test Endpoint Workflow",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{wf_uuid}/test",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                "mock_http_responses": {"status": "ok"},
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "success" in data
        assert "message" in data
        assert "log_output" in data

    @pytest.mark.asyncio
    async def test_test_endpoint_404(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/workflows/00000000-0000-0000-0000-000000000000/test",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                "mock_http_responses": {},
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_test_inactive_workflow_400(
        self, test_client: Any, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Inactive for Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": False,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{wf_uuid}/test",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                "mock_http_responses": {},
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 400


# ===========================================================================
# Integration: Workflow execute endpoint
# ===========================================================================


class TestWorkflowExecuteEndpointIntegration:
    @pytest.mark.asyncio
    async def test_execute_202(
        self, test_client: Any, api_key: str, mock_queue: Any
    ) -> None:
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Execute Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{wf_uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 202

    @pytest.mark.asyncio
    async def test_execute_enqueues_task(
        self, test_client: Any, api_key: str, mock_queue: Any
    ) -> None:
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Enqueue Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        await test_client.post(
            f"/v1/workflows/{wf_uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        mock_queue.enqueue.assert_called()

    @pytest.mark.asyncio
    async def test_execute_inactive_400(
        self, test_client: Any, api_key: str, mock_queue: Any
    ) -> None:
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Inactive Execute",
                "code": VALID_WORKFLOW_CODE,
                "state": "draft",
                "is_active": False,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{wf_uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_execute_404_nonexistent(
        self, test_client: Any, api_key: str, mock_queue: Any
    ) -> None:
        resp = await test_client.post(
            "/v1/workflows/00000000-0000-0000-0000-000000000000/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 404


# ===========================================================================
# Integration: Workflow run audit logging
# ===========================================================================


class TestWorkflowRunAuditIntegration:
    @pytest.mark.asyncio
    async def test_list_runs_per_workflow(
        self, test_client: Any, api_key: str, mock_queue: Any
    ) -> None:
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Runs Audit Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        # Execute to create a run
        await test_client.post(
            f"/v1/workflows/{wf_uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

        # List runs
        runs_resp = await test_client.get(
            f"/v1/workflows/{wf_uuid}/runs",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert runs_resp.status_code == 200
        body = runs_resp.json()
        assert isinstance(body["data"], list)
        assert body["meta"]["total"] >= 1

        # Verify run has expected fields
        if body["data"]:
            run = body["data"][0]
            assert "uuid" in run
            assert "status" in run
            assert "trigger_type" in run
            assert "code_version_executed" in run

    @pytest.mark.asyncio
    async def test_global_runs_endpoint(
        self, test_client: Any, api_key: str, mock_queue: Any
    ) -> None:
        resp = await test_client.get(
            "/v1/workflow-runs",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


# ===========================================================================
# Integration: Workflow approval gate
# ===========================================================================


class TestWorkflowApprovalGateIntegration:
    """
    Integration tests for the full approval gate flow via the API.
    """

    @pytest.mark.asyncio
    async def test_agent_trigger_with_approval_mode_always_creates_request(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        """
        When key_type=agent AND approval_mode="always",
        the execute endpoint should create an approval request.
        """
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Approval Gate Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "always",
                "approval_timeout_seconds": 3600,
                "risk_level": "high",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert create_resp.status_code == 201
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{wf_uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                "reason": "Suspicious traffic detected",
                "confidence": 0.9,
            },
            headers={"Authorization": f"Bearer {agent_api_key}"},
        )
        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data["status"] == "pending_approval"
        assert "approval_request_uuid" in data
        assert "expires_at" in data

    @pytest.mark.asyncio
    async def test_human_trigger_bypasses_approval_gate(
        self, test_client: Any, api_key: str, mock_queue: Any
    ) -> None:
        """
        When key_type=human, even if approval_mode="always",
        the workflow should be immediately queued (not gated).
        """
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Human Bypass Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "always",
                "approval_timeout_seconds": 3600,
                "risk_level": "high",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{wf_uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 202
        data = resp.json()["data"]
        # Human trigger should go straight to "queued", not "pending_approval"
        assert data.get("status") == "queued"
        assert "run_uuid" in data

    @pytest.mark.asyncio
    async def test_agent_trigger_without_approval_goes_straight_to_queue(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        """
        When key_type=agent but approval_mode="never",
        the workflow should be immediately queued.
        """
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Agent No Approval",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{wf_uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                "reason": "Test",
                "confidence": 0.5,
            },
            headers={"Authorization": f"Bearer {agent_api_key}"},
        )
        assert resp.status_code == 202
        data = resp.json()["data"]
        assert data.get("status") == "queued"

    @pytest.mark.asyncio
    async def test_agent_trigger_missing_reason_422(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        """agent trigger without reason should return 422."""
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Missing Reason Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "always",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{wf_uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                # Missing reason and confidence
            },
            headers={"Authorization": f"Bearer {agent_api_key}"},
        )
        assert resp.status_code == 422


# ===========================================================================
# Integration: Approval approve/reject/conflict endpoints
# ===========================================================================


class TestApprovalDecisionEndpointsIntegration:
    """
    Integration tests for approve/reject via /v1/workflow-approvals/{uuid}/approve|reject.
    """

    async def _create_approval(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> str:
        """Helper: create a workflow with approval gate and trigger agent execute."""
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": f"Approval Decision Test {uuid4().hex[:8]}",
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "is_active": True,
                "tags": [],
                "approval_mode": "always",
                "approval_timeout_seconds": 3600,
                "risk_level": "high",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{wf_uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                "reason": "Anomalous traffic",
                "confidence": 0.9,
            },
            headers={"Authorization": f"Bearer {agent_api_key}"},
        )
        return resp.json()["data"]["approval_request_uuid"]  # type: ignore[no-any-return]

    @pytest.mark.asyncio
    async def test_approve_returns_200(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        approval_uuid = await self._create_approval(test_client, api_key, agent_api_key, mock_queue)

        resp = await test_client.post(
            f"/v1/workflow-approvals/{approval_uuid}/approve",
            json={"responder_id": "test-user"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "approved"
        assert data["responder_id"] == "test-user"

    @pytest.mark.asyncio
    async def test_reject_returns_200(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        approval_uuid = await self._create_approval(test_client, api_key, agent_api_key, mock_queue)

        resp = await test_client.post(
            f"/v1/workflow-approvals/{approval_uuid}/reject",
            json={"responder_id": "test-rejector"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_double_approve_returns_409(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        approval_uuid = await self._create_approval(test_client, api_key, agent_api_key, mock_queue)

        # First approve
        resp1 = await test_client.post(
            f"/v1/workflow-approvals/{approval_uuid}/approve",
            json={"responder_id": "user1"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp1.status_code == 200

        # Second approve — should be 409
        resp2 = await test_client.post(
            f"/v1/workflow-approvals/{approval_uuid}/approve",
            json={"responder_id": "user2"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_double_reject_returns_409(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        approval_uuid = await self._create_approval(test_client, api_key, agent_api_key, mock_queue)

        resp1 = await test_client.post(
            f"/v1/workflow-approvals/{approval_uuid}/reject",
            json={"responder_id": "user1"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp1.status_code == 200

        resp2 = await test_client.post(
            f"/v1/workflow-approvals/{approval_uuid}/reject",
            json={"responder_id": "user2"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_approve_after_reject_returns_409(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        approval_uuid = await self._create_approval(test_client, api_key, agent_api_key, mock_queue)

        # Reject first
        await test_client.post(
            f"/v1/workflow-approvals/{approval_uuid}/reject",
            json={"responder_id": "user1"},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        # Then try to approve — 409
        resp = await test_client.post(
            f"/v1/workflow-approvals/{approval_uuid}/approve",
            json={"responder_id": "user2"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_reject_after_approve_returns_409(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        approval_uuid = await self._create_approval(test_client, api_key, agent_api_key, mock_queue)

        # Approve first
        await test_client.post(
            f"/v1/workflow-approvals/{approval_uuid}/approve",
            json={"responder_id": "user1"},
            headers={"Authorization": f"Bearer {api_key}"},
        )

        # Then try to reject — 409
        resp = await test_client.post(
            f"/v1/workflow-approvals/{approval_uuid}/reject",
            json={"responder_id": "user2"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_approve_nonexistent_404(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/workflow-approvals/00000000-0000-0000-0000-000000000000/approve",
            json={"responder_id": "test"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_nonexistent_404(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/workflow-approvals/00000000-0000-0000-0000-000000000000/reject",
            json={"responder_id": "test"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_approval_request(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        approval_uuid = await self._create_approval(test_client, api_key, agent_api_key, mock_queue)

        resp = await test_client.get(
            f"/v1/workflow-approvals/{approval_uuid}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["uuid"] == approval_uuid
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_list_approval_requests(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        await self._create_approval(test_client, api_key, agent_api_key, mock_queue)

        resp = await test_client.get(
            "/v1/workflow-approvals",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_list_filter_by_pending_status(
        self, test_client: Any, api_key: str, agent_api_key: str, mock_queue: Any
    ) -> None:
        await self._create_approval(test_client, api_key, agent_api_key, mock_queue)

        resp = await test_client.get(
            "/v1/workflow-approvals?status=pending",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        for item in resp.json()["data"]:
            assert item["status"] == "pending"


# ===========================================================================
# Integration: Workflow delete
# ===========================================================================


class TestWorkflowDeleteIntegration:
    @pytest.mark.asyncio
    async def test_delete_204(
        self, test_client: Any, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Delete Test",
                "code": VALID_WORKFLOW_CODE,
                "state": "draft",
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        wf_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.delete(
            f"/v1/workflows/{wf_uuid}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 204

        # Verify gone
        get_resp = await test_client.get(
            f"/v1/workflows/{wf_uuid}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_404(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.delete(
            "/v1/workflows/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 404


# ===========================================================================
# Unit: WorkflowExecuteAgentRequest schema validation
# ===========================================================================


class TestWorkflowExecuteAgentRequestSchema:
    def test_human_trigger_no_reason_needed(self) -> None:
        from app.schemas.workflow_approvals import WorkflowExecuteAgentRequest

        body = WorkflowExecuteAgentRequest(
            indicator_type="ip",
            indicator_value="1.2.3.4",
        )
        assert body.validate_agent_fields(trigger_source="human") == []

    def test_agent_trigger_without_reason_returns_errors(self) -> None:
        from app.schemas.workflow_approvals import WorkflowExecuteAgentRequest

        body = WorkflowExecuteAgentRequest(
            indicator_type="ip",
            indicator_value="1.2.3.4",
        )
        errors = body.validate_agent_fields(trigger_source="agent")
        assert any("reason" in e for e in errors)
        assert any("confidence" in e for e in errors)

    def test_agent_trigger_with_reason_and_confidence_valid(self) -> None:
        from app.schemas.workflow_approvals import WorkflowExecuteAgentRequest

        body = WorkflowExecuteAgentRequest(
            indicator_type="ip",
            indicator_value="1.2.3.4",
            reason="Suspicious traffic",
            confidence=0.9,
        )
        assert body.validate_agent_fields(trigger_source="agent") == []

    def test_invalid_indicator_type_raises(self) -> None:
        from app.schemas.workflow_approvals import WorkflowExecuteAgentRequest

        with pytest.raises(ValueError):
            WorkflowExecuteAgentRequest(
                indicator_type="invalid_type",
                indicator_value="1.2.3.4",
            )
