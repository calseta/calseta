"""Unit tests for run cancellation service."""

from __future__ import annotations

import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.run_cancellation import (
    _kill_subprocess,
    clear_cancellation,
    is_cancelled,
    request_cancellation,
)


class TestCancellationFlags:
    """Tests for in-process cancellation flag management."""

    def setup_method(self) -> None:
        # Clean slate for each test
        from app.services.run_cancellation import _cancellation_flags

        _cancellation_flags.clear()

    def test_is_cancelled_false_by_default(self) -> None:
        assert is_cancelled(999) is False

    def test_request_sets_flag(self) -> None:
        request_cancellation(42)
        assert is_cancelled(42) is True

    def test_clear_removes_flag(self) -> None:
        request_cancellation(42)
        clear_cancellation(42)
        assert is_cancelled(42) is False

    def test_clear_noop_for_unknown_id(self) -> None:
        clear_cancellation(9999)  # Should not raise

    def test_flags_are_independent(self) -> None:
        request_cancellation(1)
        request_cancellation(2)
        assert is_cancelled(1) is True
        assert is_cancelled(2) is True
        assert is_cancelled(3) is False


class TestKillSubprocess:
    """Tests for SIGTERM -> SIGKILL sequence."""

    async def test_sends_sigterm_then_sigkill(self) -> None:
        with (
            patch("os.kill") as mock_kill,
            patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            await _kill_subprocess(12345)

            assert mock_kill.call_count == 2
            mock_kill.assert_any_call(12345, signal.SIGTERM)
            mock_kill.assert_any_call(12345, signal.SIGKILL)
            mock_sleep.assert_called_once_with(15)

    async def test_process_already_dead_skips_sigkill(self) -> None:
        with patch("os.kill", side_effect=ProcessLookupError):
            await _kill_subprocess(12345)
            # Should not raise, just return

    async def test_process_dies_during_grace_period(self) -> None:
        call_count = 0

        def _conditional_kill(pid: int, sig: int) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ProcessLookupError

        with (
            patch("os.kill", side_effect=_conditional_kill),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            await _kill_subprocess(12345)
            assert call_count == 2

    async def test_permission_error_skips_sigkill(self) -> None:
        with patch("os.kill", side_effect=PermissionError):
            await _kill_subprocess(12345)
            # Should not raise


class TestCancelRun:
    """Tests for the cancel_run orchestrator."""

    def setup_method(self) -> None:
        from app.services.run_cancellation import _cancellation_flags

        _cancellation_flags.clear()

    async def test_terminal_state_raises_value_error(self) -> None:
        from app.services.run_cancellation import cancel_run

        for status in ("succeeded", "failed", "cancelled", "timed_out"):
            run = MagicMock()
            run.status = status
            db = AsyncMock()
            with pytest.raises(ValueError, match="terminal state"):
                await cancel_run(run, db)

    async def test_api_run_sets_cancellation_flag(self) -> None:
        from app.services.run_cancellation import cancel_run

        run = MagicMock()
        run.id = 77
        run.status = "running"
        run.process_pid = None  # API adapter, no subprocess
        run.agent_registration_id = 1

        db = AsyncMock()
        with (
            patch(
                "app.repositories.heartbeat_run_repository.HeartbeatRunRepository",
            ) as mock_repo_cls,
            patch(
                "app.services.run_cancellation._release_assignment_for_run",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.run_cancellation._log_cancel_event",
                new_callable=AsyncMock,
            ),
        ):
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            await cancel_run(run, db)

        assert is_cancelled(77) is True
        mock_repo.cancel.assert_called_once_with(run)

    async def test_running_state_does_not_raise(self) -> None:
        from app.services.run_cancellation import cancel_run

        run = MagicMock()
        run.id = 88
        run.status = "running"
        run.process_pid = None
        run.agent_registration_id = 1

        db = AsyncMock()
        with (
            patch(
                "app.repositories.heartbeat_run_repository.HeartbeatRunRepository",
            ) as mock_repo_cls,
            patch(
                "app.services.run_cancellation._release_assignment_for_run",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.run_cancellation._log_cancel_event",
                new_callable=AsyncMock,
            ),
        ):
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            # Should not raise
            await cancel_run(run, db)

    async def test_subprocess_run_calls_kill(self) -> None:
        from app.services.run_cancellation import cancel_run

        run = MagicMock()
        run.id = 99
        run.status = "running"
        run.process_pid = 54321
        run.agent_registration_id = 1

        db = AsyncMock()
        with (
            patch(
                "app.repositories.heartbeat_run_repository.HeartbeatRunRepository",
            ) as mock_repo_cls,
            patch(
                "app.services.run_cancellation._kill_subprocess",
                new_callable=AsyncMock,
            ) as mock_kill,
            patch(
                "app.services.run_cancellation._release_assignment_for_run",
                new_callable=AsyncMock,
            ),
            patch(
                "app.services.run_cancellation._log_cancel_event",
                new_callable=AsyncMock,
            ),
        ):
            mock_repo = AsyncMock()
            mock_repo_cls.return_value = mock_repo

            await cancel_run(run, db)

        mock_kill.assert_called_once_with(54321)
        assert is_cancelled(99) is True
