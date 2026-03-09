"""
Workflow approval gate — creates approval requests and processes decisions.

Gate logic (applied in the execute endpoint, based on workflow.approval_mode):
  - If approval_mode="always": all triggers go through approval gate.
  - If approval_mode="agent_only": only agent triggers (trigger_source="agent") require approval.
  - If approval_mode="never": no approval required, immediate execution.

  When the gate fires:
      → Create WorkflowApprovalRequest(status="pending")
      → Enqueue send_approval_notification_task
      → Return 202 {"status": "pending_approval", "approval_request_uuid": "..."}
  Otherwise:
      → Existing execute-immediately behavior (4.8)

Decision processing:
  - approve → status="approved" → enqueue execute_approved_workflow_task
  - reject  → status="rejected" → no execution
  - expire  → checked at approve time; returns 409
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import Settings
    from app.db.models.workflow import Workflow
    from app.db.models.workflow_approval_request import WorkflowApprovalRequest

logger = structlog.get_logger(__name__)


async def create_approval_request(
    *,
    workflow: Workflow,
    trigger_type: str,
    trigger_agent_key_prefix: str,
    trigger_context: dict[str, Any],
    reason: str,
    confidence: float,
    notifier_type: str,
    db: AsyncSession,
    cfg: Settings,
) -> WorkflowApprovalRequest:
    """
    Create a WorkflowApprovalRequest row with status="pending".

    The approval timeout is taken from the workflow's approval_timeout_seconds
    field (fallback: APPROVAL_DEFAULT_TIMEOUT_SECONDS from settings).
    """
    from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR

    timeout_seconds = (
        workflow.approval_timeout_seconds
        or cfg.APPROVAL_DEFAULT_TIMEOUT_SECONDS
    )
    expires_at = datetime.now(UTC) + timedelta(seconds=timeout_seconds)

    request = WAR(
        uuid=uuid.uuid4(),
        workflow_id=workflow.id,
        trigger_type=trigger_type,
        trigger_agent_key_prefix=trigger_agent_key_prefix,
        trigger_context=trigger_context,
        reason=reason,
        confidence=confidence,
        notifier_type=notifier_type,
        notifier_channel=workflow.approval_channel,
        status="pending",
        expires_at=expires_at,
    )
    db.add(request)
    await db.flush()
    return request


async def process_approval_decision(
    *,
    approval_uuid: uuid.UUID,
    approved: bool,
    responder_id: str | None,
    db: AsyncSession,
) -> WorkflowApprovalRequest:
    """
    Process an approve or reject decision on a pending approval request.

    - Sets status to "approved" or "rejected"
    - Records responder_id and responded_at
    - If approved, enqueues execute_approved_workflow_task
    - Raises ValueError on expired, already-decided, or not-found requests

    Returns the updated WorkflowApprovalRequest.
    """
    from sqlalchemy import select

    from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR
    from app.queue.factory import get_queue_backend

    result = await db.execute(
        select(WAR).where(WAR.uuid == approval_uuid)
    )
    request = result.scalar_one_or_none()
    if request is None:
        raise ValueError(f"Approval request {approval_uuid} not found")

    if request.status != "pending":
        raise ValueError(
            f"Approval request {approval_uuid} is already in terminal status '{request.status}'"
        )

    now = datetime.now(UTC)
    # expires_at may be timezone-naive depending on DB driver; normalize
    expires_at = request.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if now > expires_at:
        request.status = "expired"
        await db.flush()
        raise ValueError(f"Approval request {approval_uuid} has expired")

    request.status = "approved" if approved else "rejected"
    request.responder_id = responder_id
    request.responded_at = now
    await db.flush()

    if approved:
        queue = get_queue_backend()
        await queue.enqueue(
            "execute_approved_workflow_task",
            {"approval_request_id": request.id},
            queue="workflows",
            delay_seconds=0,
            priority=0,
        )

    # Activity event: workflow_approval_responded
    try:
        from app.schemas.activity_events import ActivityEventType
        from app.services.activity_event import ActivityEventService

        tc = request.trigger_context or {}
        activity_svc = ActivityEventService(db)
        await activity_svc.write(
            ActivityEventType.WORKFLOW_APPROVAL_RESPONDED,
            actor_type="api",
            workflow_id=request.workflow_id,
            alert_id=tc.get("alert_id"),
            references={
                "approval_uuid": str(approval_uuid),
                "decision": "approved" if approved else "rejected",
                "responder_id": responder_id,
                "indicator_type": tc.get("indicator_type"),
                "indicator_value": tc.get("indicator_value"),
            },
        )
    except Exception:
        pass  # Never break the approval flow for audit events

    logger.info(
        "approval_decision_processed",
        approval_uuid=str(approval_uuid),
        approved=approved,
        responder_id=responder_id,
    )
    return request
