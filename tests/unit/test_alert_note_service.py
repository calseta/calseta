"""Unit tests for AlertNoteService — C1: Comment-Driven Wakeups."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

# Paths for patching at the source module
_SVC_PATH = "app.services.alert_note_service"


def _make_service():
    """Create an AlertNoteService with a mock DB session, patching repos."""
    from app.services.alert_note_service import AlertNoteService

    db = AsyncMock()
    svc = AlertNoteService(db)
    return svc, db


def _mock_activity_event(uuid=None):
    """Return a MagicMock that behaves like an ActivityEvent row."""
    ev = MagicMock()
    ev.uuid = uuid or uuid4()
    return ev


def _mock_assignment(agent_id=10, alert_id=1, assignment_id=99):
    """Return a MagicMock that behaves like an AlertAssignment row."""
    a = MagicMock()
    a.id = assignment_id
    a.alert_id = alert_id
    a.agent_registration_id = agent_id
    a.status = "in_progress"
    a.checked_out_at = datetime.now(UTC)
    return a


def _mock_heartbeat_run(run_id=200):
    """Return a MagicMock that behaves like a HeartbeatRun row."""
    r = MagicMock()
    r.id = run_id
    r.uuid = uuid4()
    r.status = "queued"
    return r


class TestAddNote:
    """Tests for AlertNoteService.add_note()."""

    async def test_add_note_stores_activity_event_and_returns_note_id(self) -> None:
        """add_note creates an activity event and returns its UUID."""
        svc, _db = _make_service()

        expected_uuid = uuid4()
        svc._activity_repo.create = AsyncMock(
            return_value=_mock_activity_event(uuid=expected_uuid)
        )

        result = await svc.add_note(
            alert_id=1,
            content="Check the IP range",
            trigger_agent=False,
            actor_type="api",
            actor_key_prefix="cai_abc1",
        )

        assert result["note_id"] == str(expected_uuid)
        assert result["agent_triggered"] is False
        svc._activity_repo.create.assert_awaited_once()

    async def test_add_note_trigger_true_with_active_assignment(self) -> None:
        """trigger_agent=True finds active assignment and enqueues heartbeat run."""
        svc, db = _make_service()

        expected_uuid = uuid4()
        svc._activity_repo.create = AsyncMock(
            return_value=_mock_activity_event(uuid=expected_uuid)
        )

        assignment = _mock_assignment()
        svc._assignment_repo.get_active_for_alert = AsyncMock(return_value=assignment)

        run = _mock_heartbeat_run()
        svc._heartbeat_repo.create = AsyncMock(return_value=run)
        svc._heartbeat_repo.update_status = AsyncMock(return_value=run)

        # No recent triggers — DB query returns only 1 row (the one we just wrote)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MagicMock()]
        db.execute = AsyncMock(return_value=mock_result)

        queue = AsyncMock()

        result = await svc.add_note(
            alert_id=1,
            content="Please investigate this IP",
            trigger_agent=True,
            actor_type="api",
            actor_key_prefix="cai_abc1",
            queue=queue,
        )

        assert result["agent_triggered"] is True
        svc._heartbeat_repo.create.assert_awaited_once_with(
            agent_id=assignment.agent_registration_id,
            source="comment",
        )
        queue.enqueue.assert_awaited_once()
        call_args = queue.enqueue.call_args
        assert call_args[0][0] == "run_managed_agent_task"
        assert call_args[1]["queue"] == "agents"

    async def test_add_note_trigger_true_no_assignment(self) -> None:
        """trigger_agent=True but no active or recent assignment — note stored, no trigger."""
        svc, db = _make_service()

        svc._activity_repo.create = AsyncMock(return_value=_mock_activity_event())
        svc._assignment_repo.get_active_for_alert = AsyncMock(return_value=None)

        # Rate limit check: only 1 recent trigger (the one we just wrote)
        mock_rate = MagicMock()
        mock_rate.scalars.return_value.all.return_value = [MagicMock()]

        # Recent assignment fallback query returns None
        mock_recent = MagicMock()
        mock_recent.scalar_one_or_none.return_value = None

        db.execute = AsyncMock(side_effect=[mock_rate, mock_recent])

        queue = AsyncMock()

        result = await svc.add_note(
            alert_id=1,
            content="Look at this",
            trigger_agent=True,
            actor_type="api",
            actor_key_prefix="cai_abc1",
            queue=queue,
        )

        assert result["agent_triggered"] is False
        queue.enqueue.assert_not_awaited()

    async def test_add_note_trigger_true_rate_limited(self) -> None:
        """trigger_agent=True but a recent trigger exists within 5 min — rate limited."""
        svc, db = _make_service()

        svc._activity_repo.create = AsyncMock(return_value=_mock_activity_event())
        svc._assignment_repo.get_active_for_alert = AsyncMock()

        # Rate limit check: 2 recent triggers (current + a previous one)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
        db.execute = AsyncMock(return_value=mock_result)

        queue = AsyncMock()

        result = await svc.add_note(
            alert_id=1,
            content="Follow up again",
            trigger_agent=True,
            actor_type="api",
            actor_key_prefix="cai_abc1",
            queue=queue,
        )

        assert result["agent_triggered"] is False
        # Assignment repo never called because rate limit short-circuited
        svc._assignment_repo.get_active_for_alert.assert_not_awaited()

    async def test_add_note_trigger_false_no_trigger_attempted(self) -> None:
        """trigger_agent=False — note stored, no trigger attempt regardless of queue."""
        svc, _db = _make_service()

        svc._activity_repo.create = AsyncMock(return_value=_mock_activity_event())
        queue = AsyncMock()

        result = await svc.add_note(
            alert_id=1,
            content="Just a note",
            trigger_agent=False,
            actor_type="api",
            actor_key_prefix="cai_abc1",
            queue=queue,
        )

        assert result["agent_triggered"] is False
        queue.enqueue.assert_not_awaited()

    async def test_add_note_trigger_true_no_queue_provided(self) -> None:
        """trigger_agent=True but queue=None — note stored, no trigger."""
        svc, _db = _make_service()

        svc._activity_repo.create = AsyncMock(return_value=_mock_activity_event())

        result = await svc.add_note(
            alert_id=1,
            content="Please check",
            trigger_agent=True,
            actor_type="api",
            actor_key_prefix="cai_abc1",
            queue=None,
        )

        assert result["agent_triggered"] is False


class TestTryTriggerAgent:
    """Tests for AlertNoteService._try_trigger_agent() internal method."""

    async def test_fallback_to_recently_checked_out_assignment(self) -> None:
        """When no active assignment, falls back to one checked out within 1 hour."""
        svc, db = _make_service()

        svc._assignment_repo.get_active_for_alert = AsyncMock(return_value=None)

        # Rate limit check: 1 trigger (current only)
        mock_rate = MagicMock()
        mock_rate.scalars.return_value.all.return_value = [MagicMock()]

        # Recent assignment fallback query returns a match
        recent_assignment = _mock_assignment()
        mock_recent = MagicMock()
        mock_recent.scalar_one_or_none.return_value = recent_assignment

        db.execute = AsyncMock(side_effect=[mock_rate, mock_recent])

        run = _mock_heartbeat_run()
        svc._heartbeat_repo.create = AsyncMock(return_value=run)
        svc._heartbeat_repo.update_status = AsyncMock(return_value=run)

        queue = AsyncMock()

        result = await svc._try_trigger_agent(
            alert_id=1,
            content="Wake up agent",
            actor_key_prefix="cai_test",
            queue=queue,
        )

        assert result is True
        queue.enqueue.assert_awaited_once()
        # Verify the heartbeat run was created for the recent assignment's agent
        svc._heartbeat_repo.create.assert_awaited_once_with(
            agent_id=recent_assignment.agent_registration_id,
            source="comment",
        )

    async def test_enqueue_failure_returns_false(self) -> None:
        """If queue.enqueue raises, _try_trigger_agent returns False (no crash)."""
        svc, db = _make_service()

        # Rate limit: no prior triggers
        mock_rate = MagicMock()
        mock_rate.scalars.return_value.all.return_value = [MagicMock()]
        db.execute = AsyncMock(return_value=mock_rate)

        assignment = _mock_assignment()
        svc._assignment_repo.get_active_for_alert = AsyncMock(return_value=assignment)

        run = _mock_heartbeat_run()
        svc._heartbeat_repo.create = AsyncMock(return_value=run)
        svc._heartbeat_repo.update_status = AsyncMock(return_value=run)

        queue = AsyncMock()
        queue.enqueue.side_effect = RuntimeError("queue down")

        result = await svc._try_trigger_agent(
            alert_id=1,
            content="test",
            actor_key_prefix="cai_test",
            queue=queue,
        )

        assert result is False

    async def test_heartbeat_run_gets_comment_context_snapshot(self) -> None:
        """Heartbeat run update_status includes wake_comments context_snapshot."""
        svc, db = _make_service()

        # Rate limit: no prior triggers
        mock_rate = MagicMock()
        mock_rate.scalars.return_value.all.return_value = [MagicMock()]
        db.execute = AsyncMock(return_value=mock_rate)

        assignment = _mock_assignment()
        svc._assignment_repo.get_active_for_alert = AsyncMock(return_value=assignment)

        run = _mock_heartbeat_run()
        svc._heartbeat_repo.create = AsyncMock(return_value=run)
        svc._heartbeat_repo.update_status = AsyncMock(return_value=run)

        queue = AsyncMock()

        await svc._try_trigger_agent(
            alert_id=1,
            content="Check this IOC",
            actor_key_prefix="cai_analyst",
            queue=queue,
        )

        # Verify update_status was called with correct context_snapshot
        svc._heartbeat_repo.update_status.assert_awaited_once()
        call_kwargs = svc._heartbeat_repo.update_status.call_args
        assert call_kwargs[0][1] == "queued"  # status arg
        assert call_kwargs[1]["invocation_source"] == "comment"
        snapshot = call_kwargs[1]["context_snapshot"]
        assert "wake_comments" in snapshot
        assert snapshot["wake_comments"][0]["content"] == "Check this IOC"
        assert snapshot["wake_comments"][0]["author"] == "cai_analyst"
        assert snapshot["alert_id"] == 1
