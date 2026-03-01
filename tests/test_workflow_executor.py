"""Unit tests for the workflow execution sandbox (Chunk 4.6)."""

from __future__ import annotations

import asyncio

import pytest

from app.workflows.context import WorkflowContext, WorkflowLogger, WorkflowResult
from app.workflows.sandbox import run_workflow_code

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx() -> WorkflowContext:
    """Create a minimal WorkflowContext for testing."""
    from unittest.mock import MagicMock

    from app.workflows.context import (
        AlertContext,
        IndicatorContext,
        IntegrationClients,
        SecretsAccessor,
    )
    from datetime import datetime, UTC
    from uuid import uuid4

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

    ctx = WorkflowContext(
        indicator=indicator,
        alert=None,
        http=MagicMock(),
        log=WorkflowLogger(),
        secrets=SecretsAccessor(),
        integrations=IntegrationClients(),
    )
    return ctx


# ---------------------------------------------------------------------------
# Successful execution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_execution_returns_ok_result() -> None:
    code = """\
async def run(ctx):
    return ctx.log.__class__.__module__ and __import__
"""
    # Use a properly structured code
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
async def test_execution_returns_fail_result() -> None:
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
async def test_log_output_captured() -> None:
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


# ---------------------------------------------------------------------------
# Timeout enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_returns_fail_result() -> None:
    code = """\
import asyncio

async def run(ctx):
    await asyncio.sleep(100)
"""
    ctx = _make_ctx()
    result = await run_workflow_code(code, ctx, timeout=1)
    assert result.success is False
    assert "timed out" in result.message.lower()


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exception_in_run_returns_fail_not_raises() -> None:
    code = """\
async def run(ctx):
    raise ValueError("unexpected error in workflow")
"""
    ctx = _make_ctx()
    result = await run_workflow_code(code, ctx, timeout=10)
    assert result.success is False
    assert "unexpected error in workflow" in result.message


@pytest.mark.asyncio
async def test_module_level_exception_returns_fail() -> None:
    code = """\
# This raises at module load time
x = 1 / 0

async def run(ctx):
    return None
"""
    ctx = _make_ctx()
    result = await run_workflow_code(code, ctx, timeout=10)
    assert result.success is False
    assert "module load" in result.message


# ---------------------------------------------------------------------------
# Missing run function
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_run_function_returns_fail() -> None:
    code = """\
def not_run(ctx):
    return "oops"
"""
    ctx = _make_ctx()
    result = await run_workflow_code(code, ctx, timeout=10)
    assert result.success is False
    assert "run" in result.message.lower()


@pytest.mark.asyncio
async def test_sync_run_returns_fail() -> None:
    code = """\
def run(ctx):
    return "sync"
"""
    ctx = _make_ctx()
    result = await run_workflow_code(code, ctx, timeout=10)
    assert result.success is False
    assert "async" in result.message.lower()


# ---------------------------------------------------------------------------
# Syntax error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_syntax_error_in_code_returns_fail() -> None:
    code = "def run(ctx\n    return None"
    ctx = _make_ctx()
    result = await run_workflow_code(code, ctx, timeout=10)
    assert result.success is False
    assert "syntax error" in result.message.lower()


# ---------------------------------------------------------------------------
# Blocked builtins in sandbox
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_not_in_sandbox_namespace() -> None:
    """open() is blocked in sandbox — calling it raises NameError, caught as workflow failure."""
    code = """\
from app.workflows.context import WorkflowResult

async def run(ctx):
    try:
        open("/etc/passwd")
    except NameError:
        return WorkflowResult.fail("open not available as expected")
    return WorkflowResult.ok("open was available (should not reach here)")
"""
    ctx = _make_ctx()
    result = await run_workflow_code(code, ctx, timeout=10)
    assert result.success is False
    assert "open not available" in result.message


# ---------------------------------------------------------------------------
# WorkflowLogger unit tests
# ---------------------------------------------------------------------------


def test_workflow_logger_info_appended() -> None:
    log = WorkflowLogger()
    log.info("test message", key="value")
    output = log.render()
    assert "test message" in output
    assert "info" in output


def test_workflow_logger_multiple_levels() -> None:
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


def test_workflow_logger_render_is_json_lines() -> None:
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


# ---------------------------------------------------------------------------
# WorkflowResult
# ---------------------------------------------------------------------------


def test_workflow_result_ok() -> None:
    r = WorkflowResult.ok("all good", {"count": 3})
    assert r.success is True
    assert r.message == "all good"
    assert r.data["count"] == 3


def test_workflow_result_fail() -> None:
    r = WorkflowResult.fail("bad thing happened")
    assert r.success is False
    assert r.message == "bad thing happened"
    assert r.data == {}
