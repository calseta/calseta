"""Unit tests for supervisor orphan detection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.runtime.models import SupervisionReport
from app.runtime.supervisor import AgentSupervisor

# The deferred import in _check_orphans reads from this module path
_HR_REPO_PATH = (
    "app.repositories.heartbeat_run_repository.HeartbeatRunRepository"
)


class TestCheckOrphans:
    """Tests for _check_orphans PID liveness checks."""

    async def test_dead_pid_marks_run_as_orphaned(self) -> None:
        """Dead PID -> mark_orphaned called."""
        db = AsyncMock()
        supervisor = AgentSupervisor(db)
        report = SupervisionReport()

        run = MagicMock()
        run.id = 1
        run.process_pid = 99999
        run.agent_registration_id = 10
        run.process_loss_retry_count = 0
        run.source = "scheduler"
        run.context_snapshot = {}
        run.invocation_source = "alert"

        with (
            patch(_HR_REPO_PATH) as mock_repo_cls,
            patch("os.kill", side_effect=ProcessLookupError),
            patch.object(
                supervisor, "_log_orphan_event",
                new_callable=AsyncMock,
            ),
            patch.object(
                supervisor, "_retry_orphaned_run",
                new_callable=AsyncMock,
            ),
        ):
            mock_repo = AsyncMock()
            mock_repo.list_running_with_pid.return_value = [run]
            mock_repo_cls.return_value = mock_repo

            await supervisor._check_orphans(report)

        mock_repo.mark_orphaned.assert_called_once_with(run)
        assert report.timed_out == 1

    async def test_alive_pid_skipped(self) -> None:
        """Alive PID (os.kill succeeds) -> no action."""
        db = AsyncMock()
        supervisor = AgentSupervisor(db)
        report = SupervisionReport()

        run = MagicMock()
        run.id = 1
        run.process_pid = 12345
        run.agent_registration_id = 10

        with (
            patch(_HR_REPO_PATH) as mock_repo_cls,
            patch("os.kill"),  # Succeeds = process alive
        ):
            mock_repo = AsyncMock()
            mock_repo.list_running_with_pid.return_value = [run]
            mock_repo_cls.return_value = mock_repo

            await supervisor._check_orphans(report)

        mock_repo.mark_orphaned.assert_not_called()
        assert report.timed_out == 0

    async def test_permission_error_treated_as_alive(self) -> None:
        """PermissionError -> process exists, skip."""
        db = AsyncMock()
        supervisor = AgentSupervisor(db)
        report = SupervisionReport()

        run = MagicMock()
        run.id = 1
        run.process_pid = 12345
        run.agent_registration_id = 10

        with (
            patch(_HR_REPO_PATH) as mock_repo_cls,
            patch("os.kill", side_effect=PermissionError),
        ):
            mock_repo = AsyncMock()
            mock_repo.list_running_with_pid.return_value = [run]
            mock_repo_cls.return_value = mock_repo

            await supervisor._check_orphans(report)

        mock_repo.mark_orphaned.assert_not_called()

    async def test_auto_retry_when_count_below_1(self) -> None:
        """process_loss_retry_count=0 -> retry enqueued."""
        db = AsyncMock()
        supervisor = AgentSupervisor(db)
        report = SupervisionReport()

        run = MagicMock()
        run.id = 1
        run.process_pid = 99999
        run.agent_registration_id = 10
        run.process_loss_retry_count = 0
        run.source = "scheduler"
        run.context_snapshot = {"alert_id": 5}
        run.invocation_source = "alert"

        with (
            patch(_HR_REPO_PATH) as mock_repo_cls,
            patch("os.kill", side_effect=ProcessLookupError),
            patch.object(
                supervisor, "_log_orphan_event",
                new_callable=AsyncMock,
            ),
            patch.object(
                supervisor, "_retry_orphaned_run",
                new_callable=AsyncMock,
            ) as mock_retry,
        ):
            mock_repo = AsyncMock()
            mock_repo.list_running_with_pid.return_value = [run]
            mock_repo_cls.return_value = mock_repo

            await supervisor._check_orphans(report)

        mock_retry.assert_called_once()

    async def test_no_retry_when_count_at_1(self) -> None:
        """process_loss_retry_count=1 -> no retry."""
        db = AsyncMock()
        supervisor = AgentSupervisor(db)
        report = SupervisionReport()

        run = MagicMock()
        run.id = 1
        run.process_pid = 99999
        run.agent_registration_id = 10
        run.process_loss_retry_count = 1

        with (
            patch(_HR_REPO_PATH) as mock_repo_cls,
            patch("os.kill", side_effect=ProcessLookupError),
            patch.object(
                supervisor, "_log_orphan_event",
                new_callable=AsyncMock,
            ),
            patch.object(
                supervisor, "_retry_orphaned_run",
                new_callable=AsyncMock,
            ) as mock_retry,
        ):
            mock_repo = AsyncMock()
            mock_repo.list_running_with_pid.return_value = [run]
            mock_repo_cls.return_value = mock_repo

            await supervisor._check_orphans(report)

        mock_retry.assert_not_called()

    async def test_no_runs_with_pid(self) -> None:
        """No running runs with PID -> no action."""
        db = AsyncMock()
        supervisor = AgentSupervisor(db)
        report = SupervisionReport()

        with patch(_HR_REPO_PATH) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.list_running_with_pid.return_value = []
            mock_repo_cls.return_value = mock_repo

            await supervisor._check_orphans(report)

        assert report.timed_out == 0
