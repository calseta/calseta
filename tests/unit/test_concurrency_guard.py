"""Unit tests for agent concurrency guard."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

# Deferred import in start_next_queued_run reads from this path
_QUEUE_BACKEND_PATH = "app.queue.factory.get_queue_backend"


class TestCanStartRun:
    """Tests for concurrency slot checking."""

    async def test_unlimited_always_returns_true(self) -> None:
        """max_concurrent=0 -> unlimited, always True."""
        from app.services.concurrency_guard import can_start_run

        db = AsyncMock()
        result = await can_start_run(agent_id=1, max_concurrent=0, db=db)
        assert result is True

    async def test_under_limit_returns_true(self) -> None:
        """Running count < max -> True."""
        from app.services.concurrency_guard import can_start_run

        db = AsyncMock()
        # Mock the DB query to return count=0
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 0
        db.execute.return_value = mock_result

        result = await can_start_run(
            agent_id=1, max_concurrent=2, db=db,
        )
        assert result is True

    async def test_at_limit_returns_false(self) -> None:
        """Running count >= max -> False."""
        from app.services.concurrency_guard import can_start_run

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 2
        db.execute.return_value = mock_result

        result = await can_start_run(
            agent_id=1, max_concurrent=2, db=db,
        )
        assert result is False

    async def test_over_limit_returns_false(self) -> None:
        """Running count > max -> False."""
        from app.services.concurrency_guard import can_start_run

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 5
        db.execute.return_value = mock_result

        result = await can_start_run(
            agent_id=1, max_concurrent=3, db=db,
        )
        assert result is False


class TestStartNextQueuedRun:
    """Tests for FIFO backfill on slot release."""

    async def test_no_queued_runs_is_noop(self) -> None:
        """No queued runs -> nothing happens."""
        from app.services.concurrency_guard import (
            start_next_queued_run,
        )

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_result

        await start_next_queued_run(agent_id=1, db=db)
        # No exception = success

    async def test_queued_run_enqueued(self) -> None:
        """Queued run found -> enqueue task via queue backend."""
        from app.services.concurrency_guard import (
            start_next_queued_run,
        )

        queued_run = MagicMock()
        queued_run.id = 42
        queued_run.context_snapshot = {"assignment_id": 7}

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = queued_run
        db.execute.return_value = mock_result

        with patch(_QUEUE_BACKEND_PATH) as mock_queue_fn:
            mock_queue = AsyncMock()
            mock_queue_fn.return_value = mock_queue

            await start_next_queued_run(agent_id=1, db=db)

        mock_queue.enqueue.assert_called_once()
        call_args = mock_queue.enqueue.call_args
        assert call_args[0][0] == "run_managed_agent_task"
        assert call_args[0][1]["heartbeat_run_id"] == 42

    async def test_queue_error_does_not_raise(self) -> None:
        """Queue enqueue failure is logged, not raised."""
        from app.services.concurrency_guard import (
            start_next_queued_run,
        )

        queued_run = MagicMock()
        queued_run.id = 42
        queued_run.context_snapshot = {}

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = queued_run
        db.execute.return_value = mock_result

        with patch(_QUEUE_BACKEND_PATH) as mock_queue_fn:
            mock_queue = AsyncMock()
            mock_queue.enqueue.side_effect = RuntimeError("queue down")
            mock_queue_fn.return_value = mock_queue

            # Should not raise
            await start_next_queued_run(agent_id=1, db=db)
