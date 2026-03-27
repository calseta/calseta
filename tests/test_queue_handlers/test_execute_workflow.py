"""Unit tests for ExecuteWorkflowHandler.

Tests the execute_workflow_run task handler with mocked dependencies:
- WorkflowRunRepository (get_by_id, update_after_execution)
- session.execute (for loading Workflow model)
- execute_workflow (sandbox executor)
- ActivityEventService (write)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.queue.handlers.execute_workflow import ExecuteWorkflowHandler
from app.queue.handlers.payloads import ExecuteWorkflowRunPayload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeWorkflowResult:
    success: bool
    message: str
    data: dict = field(default_factory=dict)


@dataclass
class _FakeExecutionResult:
    result: _FakeWorkflowResult
    log_output: str
    duration_ms: int
    code_version_executed: int


def _make_workflow_run(
    *,
    workflow_id: int = 1,
    trigger_type: str = "api",
    trigger_context: dict | None = None,
) -> MagicMock:
    run = MagicMock()
    run.workflow_id = workflow_id
    run.trigger_type = trigger_type
    run.trigger_context = trigger_context or {
        "indicator_type": "ip",
        "indicator_value": "8.8.8.8",
        "alert_id": 100,
    }
    run.uuid = uuid4()
    run.started_at = None
    return run


def _make_workflow(*, wf_id: int = 1, name: str = "test-wf") -> MagicMock:
    wf = MagicMock()
    wf.id = wf_id
    wf.uuid = uuid4()
    wf.name = name
    wf.code_version = 1
    return wf


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def handler() -> ExecuteWorkflowHandler:
    return ExecuteWorkflowHandler()


@pytest.fixture
def session() -> AsyncMock:
    return AsyncMock()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestExecuteWorkflowHappyPath:
    @pytest.mark.asyncio
    async def test_successful_execution(
        self,
        handler: ExecuteWorkflowHandler,
        session: AsyncMock,
    ) -> None:
        """Workflow run found, execution succeeds, run updated with success status."""
        payload = ExecuteWorkflowRunPayload(workflow_run_id=42)

        mock_run = _make_workflow_run()
        mock_workflow = _make_workflow()

        mock_run_repo = MagicMock()
        mock_run_repo.get_by_id = AsyncMock(return_value=mock_run)
        mock_run_repo.update_after_execution = AsyncMock()

        exec_result = _FakeExecutionResult(
            result=_FakeWorkflowResult(
                success=True, message="Workflow completed", data={"key": "val"}
            ),
            log_output="log line 1\nlog line 2",
            duration_ms=150,
            code_version_executed=1,
        )

        # session.execute is called once to load the Workflow model
        session.execute.return_value = _scalar_result(mock_workflow)

        with (
            patch(
                "app.queue.handlers.execute_workflow.WorkflowRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.queue.handlers.execute_workflow.execute_workflow",
                new_callable=AsyncMock,
                return_value=exec_result,
            ) as mock_exec,
            patch(
                "app.queue.handlers.execute_workflow.ActivityEventService"
            ),
        ):
            await handler.execute(payload, session)

        # Verify workflow executor was called
        mock_exec.assert_awaited_once()

        # Verify run was updated with success
        mock_run_repo.update_after_execution.assert_awaited_once()
        call_kwargs = mock_run_repo.update_after_execution.call_args
        assert call_kwargs[1]["status"] == "success"
        assert call_kwargs[1]["result_data"]["success"] is True
        assert call_kwargs[1]["duration_ms"] == 150

    @pytest.mark.asyncio
    async def test_failed_execution(
        self,
        handler: ExecuteWorkflowHandler,
        session: AsyncMock,
    ) -> None:
        """Workflow execution fails -> run updated with 'failed' status."""
        payload = ExecuteWorkflowRunPayload(workflow_run_id=42)

        mock_run = _make_workflow_run()
        mock_workflow = _make_workflow()

        mock_run_repo = MagicMock()
        mock_run_repo.get_by_id = AsyncMock(return_value=mock_run)
        mock_run_repo.update_after_execution = AsyncMock()

        exec_result = _FakeExecutionResult(
            result=_FakeWorkflowResult(
                success=False, message="HTTP 500 from target"
            ),
            log_output="error log",
            duration_ms=200,
            code_version_executed=1,
        )

        session.execute.return_value = _scalar_result(mock_workflow)

        with (
            patch(
                "app.queue.handlers.execute_workflow.WorkflowRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.queue.handlers.execute_workflow.execute_workflow",
                new_callable=AsyncMock,
                return_value=exec_result,
            ),
            patch(
                "app.queue.handlers.execute_workflow.ActivityEventService"
            ),
        ):
            await handler.execute(payload, session)

        call_kwargs = mock_run_repo.update_after_execution.call_args
        assert call_kwargs[1]["status"] == "failed"
        assert call_kwargs[1]["result_data"]["success"] is False

    @pytest.mark.asyncio
    async def test_timed_out_execution(
        self,
        handler: ExecuteWorkflowHandler,
        session: AsyncMock,
    ) -> None:
        """Workflow execution times out -> run updated with 'timed_out' status."""
        payload = ExecuteWorkflowRunPayload(workflow_run_id=42)

        mock_run = _make_workflow_run()
        mock_workflow = _make_workflow()

        mock_run_repo = MagicMock()
        mock_run_repo.get_by_id = AsyncMock(return_value=mock_run)
        mock_run_repo.update_after_execution = AsyncMock()

        exec_result = _FakeExecutionResult(
            result=_FakeWorkflowResult(
                success=False, message="Execution timed out after 30s"
            ),
            log_output="",
            duration_ms=30000,
            code_version_executed=1,
        )

        session.execute.return_value = _scalar_result(mock_workflow)

        with (
            patch(
                "app.queue.handlers.execute_workflow.WorkflowRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.queue.handlers.execute_workflow.execute_workflow",
                new_callable=AsyncMock,
                return_value=exec_result,
            ),
            patch(
                "app.queue.handlers.execute_workflow.ActivityEventService"
            ),
        ):
            await handler.execute(payload, session)

        call_kwargs = mock_run_repo.update_after_execution.call_args
        assert call_kwargs[1]["status"] == "timed_out"


# ---------------------------------------------------------------------------
# Not found cases
# ---------------------------------------------------------------------------


class TestExecuteWorkflowNotFound:
    @pytest.mark.asyncio
    async def test_run_not_found(
        self,
        handler: ExecuteWorkflowHandler,
        session: AsyncMock,
    ) -> None:
        """Handler returns gracefully when workflow run doesn't exist."""
        payload = ExecuteWorkflowRunPayload(workflow_run_id=999)

        mock_run_repo = MagicMock()
        mock_run_repo.get_by_id = AsyncMock(return_value=None)

        with patch(
            "app.queue.handlers.execute_workflow.WorkflowRunRepository",
            return_value=mock_run_repo,
        ):
            # Should not raise
            await handler.execute(payload, session)

        # session.execute should NOT have been called (no Workflow query)
        session.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_workflow_not_found(
        self,
        handler: ExecuteWorkflowHandler,
        session: AsyncMock,
    ) -> None:
        """Handler returns gracefully when the parent workflow doesn't exist."""
        payload = ExecuteWorkflowRunPayload(workflow_run_id=42)

        mock_run = _make_workflow_run()

        mock_run_repo = MagicMock()
        mock_run_repo.get_by_id = AsyncMock(return_value=mock_run)

        # Workflow query returns None
        session.execute.return_value = _scalar_result(None)

        with (
            patch(
                "app.queue.handlers.execute_workflow.WorkflowRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.queue.handlers.execute_workflow.execute_workflow",
                new_callable=AsyncMock,
            ) as mock_exec,
        ):
            # Should not raise
            await handler.execute(payload, session)

        # execute_workflow should NOT have been called
        mock_exec.assert_not_awaited()


# ---------------------------------------------------------------------------
# Activity event failure isolation
# ---------------------------------------------------------------------------


class TestExecuteWorkflowActivityEventIsolation:
    @pytest.mark.asyncio
    async def test_activity_event_failure_does_not_propagate(
        self,
        handler: ExecuteWorkflowHandler,
        session: AsyncMock,
    ) -> None:
        """If ActivityEventService.write() raises, handler still completes."""
        payload = ExecuteWorkflowRunPayload(workflow_run_id=42)

        mock_run = _make_workflow_run()
        mock_workflow = _make_workflow()

        mock_run_repo = MagicMock()
        mock_run_repo.get_by_id = AsyncMock(return_value=mock_run)
        mock_run_repo.update_after_execution = AsyncMock()

        exec_result = _FakeExecutionResult(
            result=_FakeWorkflowResult(success=True, message="OK"),
            log_output="",
            duration_ms=50,
            code_version_executed=1,
        )

        session.execute.return_value = _scalar_result(mock_workflow)

        mock_activity_svc = MagicMock()
        mock_activity_svc.write = AsyncMock(
            side_effect=RuntimeError("activity event boom")
        )

        with (
            patch(
                "app.queue.handlers.execute_workflow.WorkflowRunRepository",
                return_value=mock_run_repo,
            ),
            patch(
                "app.queue.handlers.execute_workflow.execute_workflow",
                new_callable=AsyncMock,
                return_value=exec_result,
            ),
            patch(
                "app.queue.handlers.execute_workflow.ActivityEventService",
                return_value=mock_activity_svc,
            ),
        ):
            # Should not raise despite activity event failure
            await handler.execute(payload, session)

        # Run should still have been updated
        mock_run_repo.update_after_execution.assert_awaited_once()
