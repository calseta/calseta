"""
Agent concurrency guard — enforces max_concurrent_alerts as FIFO queue.

Before starting a run, check if the agent has capacity. On release,
start the next queued run for the same agent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


async def can_start_run(
    agent_id: int,
    max_concurrent: int,
    db: AsyncSession,
) -> bool:
    """Check if an agent has capacity to start a new run.

    Args:
        agent_id: Agent registration ID.
        max_concurrent: Agent's max_concurrent_alerts setting.
            0 means unlimited.
        db: Database session.

    Returns:
        True if the agent can start a new run.
    """
    if max_concurrent <= 0:
        return True  # Unlimited

    from sqlalchemy import func, select

    from app.db.models.alert_assignment import AlertAssignment

    result = await db.execute(
        select(func.count())
        .select_from(AlertAssignment)
        .where(
            AlertAssignment.agent_registration_id == agent_id,
        )
        .where(AlertAssignment.status == "in_progress")
    )
    running_count: int = result.scalar_one()
    return running_count < max_concurrent


async def start_next_queued_run(
    agent_id: int,
    db: AsyncSession,
) -> None:
    """Start the next queued HeartbeatRun for an agent (FIFO).

    Called after a run completes or is cancelled to backfill
    the concurrency slot.
    """
    from sqlalchemy import select

    from app.db.models.heartbeat_run import HeartbeatRun

    # Find the oldest queued run for this agent
    result = await db.execute(
        select(HeartbeatRun)
        .where(
            HeartbeatRun.agent_registration_id == agent_id,
        )
        .where(HeartbeatRun.status == "queued")
        .order_by(HeartbeatRun.created_at.asc())
        .limit(1)
    )
    next_run = result.scalar_one_or_none()

    if next_run is None:
        return

    # Enqueue the task to execute this run
    try:
        from app.queue.factory import get_queue_backend

        queue = get_queue_backend()
        await queue.enqueue(
            "run_managed_agent_task",
            {
                "agent_registration_id": agent_id,
                "assignment_id": (
                    next_run.context_snapshot or {}
                ).get("assignment_id", 0),
                "heartbeat_run_id": next_run.id,
            },
            queue="agents",
        )
        logger.info(
            "concurrency.next_run_started",
            agent_id=agent_id,
            heartbeat_run_id=next_run.id,
        )
    except Exception as exc:
        logger.error(
            "concurrency.next_run_failed",
            agent_id=agent_id,
            error=str(exc),
        )
