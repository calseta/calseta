"""ActionService — business logic for agent-proposed actions.

Flow:
  1. propose_action: validate, create AgentAction row, determine approval mode,
     either auto-execute or create WorkflowApprovalRequest + enqueue notification.
  2. get_action / list_actions: read-only queries via repository.
  3. cancel_action: cancel a proposed or pending_approval action.
"""

from __future__ import annotations

import secrets
import uuid as uuid_module
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.db.models.agent_action import AgentAction
from app.db.models.agent_registration import AgentRegistration
from app.db.models.alert import Alert
from app.db.models.alert_assignment import AlertAssignment
from app.db.models.workflow_approval_request import WorkflowApprovalRequest
from app.integrations.actions.base import (
    ACTION_TYPE_DEFAULT_APPROVAL_MODE,
    resolve_approval_mode_for_action,
)
from app.repositories.agent_action_repository import AgentActionRepository
from app.schemas.actions import ActionStatus, ProposeActionRequest, ProposeActionResponse
from app.schemas.activity_events import ActivityEventType
from app.services.activity_event import ActivityEventService

logger = structlog.get_logger(__name__)

# Default approval timeout for agent actions (30 minutes)
_ACTION_APPROVAL_TIMEOUT_SECONDS = 30 * 60

# Approval modes that require human review
_APPROVAL_REQUIRED_MODES = {"always", "quick_review", "human_review"}


class ActionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._action_repo = AgentActionRepository(db)

    async def propose_action(
        self,
        agent: AgentRegistration,
        request: ProposeActionRequest,
        actor_key_prefix: str | None = None,
    ) -> ProposeActionResponse:
        """Propose an action for an alert.

        1. Resolve alert and assignment by UUID to get int IDs.
        2. Create AgentAction row (status=proposed).
        3. Determine effective approval mode.
        4. Either auto-execute or create approval request.
        5. Write ACTION_PROPOSED activity event.
        """
        # -- Resolve alert --
        alert_result = await self._db.execute(
            select(Alert).where(Alert.uuid == request.alert_id)
        )
        alert = alert_result.scalar_one_or_none()
        if alert is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Alert {request.alert_id} not found.",
                status_code=404,
            )

        # -- Resolve assignment --
        assignment_result = await self._db.execute(
            select(AlertAssignment).where(AlertAssignment.uuid == request.assignment_id)
        )
        assignment = assignment_result.scalar_one_or_none()
        if assignment is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Assignment {request.assignment_id} not found.",
                status_code=404,
            )

        # Verify assignment belongs to this agent and alert
        if assignment.agent_registration_id != agent.id:
            raise CalsetaException(
                code="FORBIDDEN",
                message="Assignment does not belong to this agent.",
                status_code=403,
            )
        if assignment.alert_id != alert.id:
            raise CalsetaException(
                code="BAD_REQUEST",
                message="Assignment does not belong to the specified alert.",
                status_code=400,
            )

        confidence_decimal: Decimal | None = (
            Decimal(str(request.confidence)) if request.confidence is not None else None
        )

        # -- Create action row --
        action = await self._action_repo.create(
            alert_id=alert.id,
            agent_registration_id=agent.id,
            assignment_id=assignment.id,
            action_type=request.action_type.value,
            action_subtype=request.action_subtype,
            payload=request.payload,
            confidence=confidence_decimal,
        )

        # -- Determine approval mode --
        base_mode = ACTION_TYPE_DEFAULT_APPROVAL_MODE.get(
            request.action_type.value, "always"
        )
        effective_mode = resolve_approval_mode_for_action(
            action_type=request.action_type.value,
            confidence=request.confidence,
            base_approval_mode=base_mode,
        )

        logger.info(
            "action_proposed",
            action_uuid=str(action.uuid),
            action_type=request.action_type.value,
            action_subtype=request.action_subtype,
            effective_mode=effective_mode,
            confidence=request.confidence,
        )

        approval_request_uuid: UUID | None = None
        expires_at: datetime | None = None
        final_status: ActionStatus

        if effective_mode == "block":
            # Confidence too low — reject immediately
            action.status = ActionStatus.REJECTED.value
            action.execution_result = {
                "success": False,
                "message": "Action blocked: confidence below threshold for this action type.",
                "data": {"effective_mode": effective_mode, "confidence": request.confidence},
            }
            await self._db.flush()
            final_status = ActionStatus.REJECTED

        elif effective_mode in _APPROVAL_REQUIRED_MODES:
            # Create a WorkflowApprovalRequest for human review
            approval = await self._create_approval_request(
                action=action,
                alert_id=alert.id,
                agent=agent,
                request=request,
                effective_mode=effective_mode,
                actor_key_prefix=actor_key_prefix,
            )
            action.status = ActionStatus.PENDING_APPROVAL.value
            action.approval_request_id = approval.id
            await self._db.flush()

            # Enqueue approval notification (best-effort)
            await self._enqueue_approval_notification(approval.id)

            approval_request_uuid = approval.uuid
            expires_at = approval.expires_at
            final_status = ActionStatus.PENDING_APPROVAL

        else:
            # auto_approve or never — enqueue for immediate execution
            action.status = ActionStatus.EXECUTING.value
            await self._db.flush()
            await self._enqueue_execute_action(action.id)
            final_status = ActionStatus.EXECUTING

        # -- Write activity event --
        try:
            activity_svc = ActivityEventService(self._db)
            await activity_svc.write(
                ActivityEventType.ACTION_PROPOSED,
                actor_type="api",
                actor_key_prefix=actor_key_prefix,
                alert_id=alert.id,
                references={
                    "action_uuid": str(action.uuid),
                    "action_type": request.action_type.value,
                    "action_subtype": request.action_subtype,
                    "status": final_status.value,
                    "effective_approval_mode": effective_mode,
                    "confidence": request.confidence,
                    "reasoning": request.reasoning,
                },
            )
        except Exception:
            pass

        return ProposeActionResponse(
            action_id=action.uuid,
            status=final_status,
            approval_request_uuid=approval_request_uuid,
            expires_at=expires_at,
        )

    async def get_action(self, action_uuid: UUID) -> AgentAction:
        """Get action by UUID. Raises CalsetaException(404) if not found."""
        action = await self._action_repo.get_by_uuid(action_uuid)
        if action is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Action {action_uuid} not found.",
                status_code=404,
            )
        return action

    async def list_actions(
        self,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentAction], int]:
        """List actions, optionally filtered by status."""
        return await self._action_repo.list_all(
            status=status,
            page=page,
            page_size=page_size,
        )

    async def cancel_action(
        self,
        action_uuid: UUID,
        agent: AgentRegistration | None = None,
        actor_key_prefix: str | None = None,
    ) -> AgentAction:
        """Cancel a proposed or pending_approval action.

        Only ``proposed`` and ``pending_approval`` actions can be cancelled.
        If the action has an approval_request_id, that approval request is also
        cancelled.
        """
        action = await self.get_action(action_uuid)

        cancellable = {ActionStatus.PROPOSED.value, ActionStatus.PENDING_APPROVAL.value}
        if action.status not in cancellable:
            raise CalsetaException(
                code="CONFLICT",
                message=(
                    f"Action {action_uuid} cannot be cancelled (current status: "
                    f"{action.status}). Only proposed or pending_approval actions "
                    "can be cancelled."
                ),
                status_code=409,
            )

        # If called by an agent, verify ownership
        if agent is not None and action.agent_registration_id != agent.id:
            raise CalsetaException(
                code="FORBIDDEN",
                message="You can only cancel your own actions.",
                status_code=403,
            )

        action.status = ActionStatus.CANCELLED.value
        await self._db.flush()

        # Cancel linked approval request if present
        if action.approval_request_id is not None:
            ar_result = await self._db.execute(
                select(WorkflowApprovalRequest).where(
                    WorkflowApprovalRequest.id == action.approval_request_id
                )
            )
            approval = ar_result.scalar_one_or_none()
            if approval is not None and approval.status == "pending":
                approval.status = "cancelled"
                await self._db.flush()

        # Write activity event
        try:
            activity_svc = ActivityEventService(self._db)
            await activity_svc.write(
                ActivityEventType.ACTION_CANCELLED,
                actor_type="api",
                actor_key_prefix=actor_key_prefix,
                alert_id=action.alert_id,
                references={
                    "action_uuid": str(action.uuid),
                    "action_type": action.action_type,
                    "action_subtype": action.action_subtype,
                },
            )
        except Exception:
            pass

        await self._db.refresh(action)
        return action

    async def approve_or_reject_action(
        self,
        action_uuid: UUID,
        status: str,
        reason: str | None = None,
        actor_key_prefix: str | None = None,
    ) -> AgentAction:
        """Approve or reject a pending_approval action.

        Only ``pending_approval`` actions can be approved or rejected.
        Raises CalsetaException(404) if not found.
        Raises CalsetaException(409) if the action is not in pending_approval status.

        For "approved": transitions action to executing and enqueues execution.
        For "rejected": transitions action to rejected.

        In both cases, the linked WorkflowApprovalRequest (if any) is updated
        to match the new status.
        """
        action = await self.get_action(action_uuid)

        if action.status != ActionStatus.PENDING_APPROVAL.value:
            raise CalsetaException(
                code="CONFLICT",
                message=(
                    f"Action {action_uuid} cannot be approved/rejected "
                    f"(current status: {action.status}). "
                    "Only pending_approval actions can be approved or rejected."
                ),
                status_code=409,
            )

        if status == "approved":
            action.status = ActionStatus.EXECUTING.value
            await self._db.flush()
            await self._enqueue_execute_action(action.id)
            final_status = ActionStatus.EXECUTING
            approval_status = "approved"
            event_type = ActivityEventType.ACTION_APPROVED
        else:
            action.status = ActionStatus.REJECTED.value
            await self._db.flush()
            final_status = ActionStatus.REJECTED
            approval_status = "rejected"
            event_type = ActivityEventType.ACTION_REJECTED

        # Update linked WorkflowApprovalRequest if present
        if action.approval_request_id is not None:
            ar_result = await self._db.execute(
                select(WorkflowApprovalRequest).where(
                    WorkflowApprovalRequest.id == action.approval_request_id
                )
            )
            approval = ar_result.scalar_one_or_none()
            if approval is not None and approval.status == "pending":
                approval.status = approval_status
                if reason:
                    approval.reason = reason
                await self._db.flush()

        # Write activity event
        try:
            activity_svc = ActivityEventService(self._db)
            await activity_svc.write(
                event_type,
                actor_type="api",
                actor_key_prefix=actor_key_prefix,
                alert_id=action.alert_id,
                references={
                    "action_uuid": str(action.uuid),
                    "action_type": action.action_type,
                    "action_subtype": action.action_subtype,
                    "status": final_status.value,
                    "reason": reason,
                },
            )
        except Exception:
            pass

        await self._db.refresh(action)
        return action

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    async def _create_approval_request(
        self,
        action: AgentAction,
        alert_id: int,
        agent: AgentRegistration,
        request: ProposeActionRequest,
        effective_mode: str,
        actor_key_prefix: str | None = None,
    ) -> WorkflowApprovalRequest:
        """Create a WorkflowApprovalRequest for the given action."""
        from app.config import settings

        expires_at = datetime.now(UTC) + timedelta(seconds=_ACTION_APPROVAL_TIMEOUT_SECONDS)
        decide_token = secrets.token_urlsafe(32)

        trigger_context: dict[str, Any] = {
            "agent_action_id": action.id,
            "agent_action_uuid": str(action.uuid),
            "alert_id": alert_id,
            "alert_uuid": str(request.alert_id),
            "assignment_uuid": str(request.assignment_id),
            "action_type": request.action_type.value,
            "action_subtype": request.action_subtype,
            "payload": request.payload,
            "confidence": request.confidence,
            "reasoning": request.reasoning,
            "effective_mode": effective_mode,
        }

        # Determine notifier type from settings
        notifier_type = getattr(settings, "APPROVAL_NOTIFIER", "none") or "none"

        approval = WorkflowApprovalRequest(
            uuid=uuid_module.uuid4(),
            workflow_id=None,  # not associated with a workflow
            trigger_type="agent_action",
            trigger_agent_key_prefix=actor_key_prefix,
            trigger_context=trigger_context,
            reason=request.reasoning or f"Agent proposed {request.action_subtype} action",
            confidence=float(request.confidence) if request.confidence is not None else 0.0,
            notifier_type=notifier_type,
            status="pending",
            expires_at=expires_at,
            decide_token=decide_token,
        )
        self._db.add(approval)
        await self._db.flush()
        await self._db.refresh(approval)
        return approval

    async def _enqueue_approval_notification(self, approval_request_id: int) -> None:
        """Enqueue send_approval_notification_task (best-effort)."""
        try:
            from app.queue.registry import procrastinate_app

            task = procrastinate_app.tasks.get("send_approval_notification_task")
            if task is not None:
                await task.defer_async(approval_request_id=approval_request_id)
        except Exception:
            logger.warning(
                "approval_notification_enqueue_failed",
                approval_request_id=approval_request_id,
            )

    async def _enqueue_execute_action(self, agent_action_id: int) -> None:
        """Enqueue execute_response_action_task (best-effort)."""
        try:
            from app.queue.registry import procrastinate_app

            task = procrastinate_app.tasks.get("execute_response_action_task")
            if task is not None:
                await task.defer_async(agent_action_id=agent_action_id)
        except Exception:
            logger.warning(
                "execute_action_enqueue_failed",
                agent_action_id=agent_action_id,
            )
