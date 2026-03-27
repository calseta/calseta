"""Handler for the send_approval_notification_task task."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.workflow import Workflow as WorkflowModel
from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR
from app.queue.handlers.payloads import SendApprovalNotificationPayload
from app.workflows.notifiers.base import ApprovalRequest
from app.workflows.notifiers.factory import get_approval_notifier


class ApprovalNotificationHandler:
    """Send the approval request notification via the configured notifier.

    Loads the WorkflowApprovalRequest by ID, builds ApprovalRequest, calls
    the configured notifier, and stores the external_message_id for thread replies.
    """

    async def execute(
        self, payload: SendApprovalNotificationPayload, session: AsyncSession
    ) -> None:
        ar_result = await session.execute(
            select(WAR).where(WAR.id == payload.approval_request_id)
        )
        approval = ar_result.scalar_one_or_none()
        if approval is None:
            return

        wf_result = await session.execute(
            select(WorkflowModel).where(WorkflowModel.id == approval.workflow_id)
        )
        workflow = wf_result.scalar_one_or_none()
        if workflow is None:
            return

        tc = approval.trigger_context or {}
        request = ApprovalRequest(
            approval_uuid=approval.uuid,
            workflow_name=workflow.name,
            workflow_risk_level=workflow.risk_level,
            indicator_type=str(tc.get("indicator_type", "")),
            indicator_value=str(tc.get("indicator_value", "")),
            trigger_source=approval.trigger_type,
            reason=approval.reason,
            confidence=approval.confidence,
            expires_at=approval.expires_at,
            approval_channel=approval.notifier_channel,
            decide_token=approval.decide_token,
        )

        notifier = get_approval_notifier(settings)
        external_id = await notifier.send_approval_request(request)
        if external_id:
            approval.external_message_id = external_id
