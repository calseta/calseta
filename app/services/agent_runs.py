"""
AgentRun service — write delivery audit records to agent_runs table.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_run import AgentRun


async def record_agent_run(
    db: AsyncSession,
    *,
    agent_registration_id: int,
    alert_id: int,
    status: str,  # "success" | "failed" | "timeout"
    attempt_count: int,
    request_payload: dict[str, Any] | None = None,
    response_status_code: int | None = None,
    response_body: dict[str, Any] | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> AgentRun:
    """Create and flush an AgentRun audit record."""
    run = AgentRun(
        uuid=_uuid.uuid4(),
        agent_registration_id=agent_registration_id,
        alert_id=alert_id,
        status=status,
        attempt_count=attempt_count,
        request_payload=request_payload,
        response_status_code=response_status_code,
        response_body=response_body,
        started_at=started_at.isoformat() if started_at else None,
        completed_at=completed_at.isoformat() if completed_at else None,
    )
    db.add(run)
    await db.flush()
    return run
