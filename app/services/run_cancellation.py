"""
Run cancellation service — handles graceful shutdown of running agents.

For subprocess adapters (Claude Code): SIGTERM -> 15s grace -> SIGKILL.
For API adapters: sets a cancellation flag checked between tool loop
iterations.
"""

from __future__ import annotations

import asyncio
import os
import signal
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# In-process cancellation flags for API-based adapters.
# Key: heartbeat_run_id (int), Value: True when cancel requested.
_cancellation_flags: dict[int, bool] = {}

SIGTERM_GRACE_SECONDS = 15


def request_cancellation(heartbeat_run_id: int) -> None:
    """Set the cancellation flag for an API-based adapter run."""
    _cancellation_flags[heartbeat_run_id] = True


def is_cancelled(heartbeat_run_id: int) -> bool:
    """Check if cancellation was requested for a run."""
    return _cancellation_flags.get(heartbeat_run_id, False)


def clear_cancellation(heartbeat_run_id: int) -> None:
    """Remove the cancellation flag after run completes."""
    _cancellation_flags.pop(heartbeat_run_id, None)


async def cancel_run(run: Any, db: AsyncSession) -> Any:
    """Cancel a running HeartbeatRun.

    Returns the updated run.
    Raises ValueError if run is already in a terminal state.
    """
    from app.repositories.heartbeat_run_repository import (
        HeartbeatRunRepository,
    )

    terminal = {
        "succeeded", "failed", "cancelled", "timed_out",
    }
    if run.status in terminal:
        raise ValueError(
            f"Run is already in terminal state '{run.status}'"
        )

    hr_repo = HeartbeatRunRepository(db)

    # For subprocess runs: send SIGTERM, then SIGKILL after grace
    if run.process_pid:
        await _kill_subprocess(run.process_pid)

    # For API-based runs: set cancellation flag
    request_cancellation(run.id)

    # Mark as cancelled in DB
    await hr_repo.cancel(run)

    # Release alert assignment if present
    await _release_assignment_for_run(run, db)

    # Log activity event
    await _log_cancel_event(run, db)

    logger.info(
        "run_cancelled",
        heartbeat_run_id=run.id,
        process_pid=run.process_pid,
        agent_id=run.agent_registration_id,
    )

    return run


async def _kill_subprocess(pid: int) -> None:
    """Send SIGTERM, wait grace period, then SIGKILL if alive."""
    try:
        os.kill(pid, signal.SIGTERM)
        logger.info("sigterm_sent", pid=pid)
    except ProcessLookupError:
        return  # Already dead
    except PermissionError:
        logger.warning("sigterm_permission_denied", pid=pid)
        return

    # Wait grace period, then SIGKILL
    await asyncio.sleep(SIGTERM_GRACE_SECONDS)
    try:
        os.kill(pid, signal.SIGKILL)
        logger.info("sigkill_sent", pid=pid)
    except ProcessLookupError:
        pass  # Terminated during grace period


async def _release_assignment_for_run(
    run: Any,
    db: AsyncSession,
) -> None:
    """Release alert assignment associated with this run."""
    from sqlalchemy import select

    from app.db.models.alert_assignment import AlertAssignment
    from app.repositories.alert_assignment_repository import (
        AlertAssignmentRepository,
    )

    result = await db.execute(
        select(AlertAssignment)
        .where(
            AlertAssignment.agent_registration_id
            == run.agent_registration_id,
        )
        .where(AlertAssignment.status == "in_progress")
    )
    assignment = result.scalar_one_or_none()
    if assignment:
        repo = AlertAssignmentRepository(db)
        await repo.release(assignment)


async def _log_cancel_event(
    run: Any,
    db: AsyncSession,
) -> None:
    """Emit heartbeat.cancelled activity event."""
    import uuid as uuid_module

    from app.db.models.activity_event import ActivityEvent

    db.add(ActivityEvent(
        uuid=uuid_module.uuid4(),
        event_type="heartbeat.cancelled",
        actor_type="api",
        actor_key_prefix=None,
        references={
            "heartbeat_run_id": run.id,
            "agent_id": run.agent_registration_id,
            "process_pid": run.process_pid,
        },
    ))
    await db.flush()
