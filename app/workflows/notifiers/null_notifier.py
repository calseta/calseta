"""
NullApprovalNotifier — no-op notifier for when no channel is configured.

Always reports is_configured() = True so the gate logic can proceed.
Logs a warning so operators know no notification was sent.
"""

from __future__ import annotations

import structlog

from app.workflows.notifiers.base import ApprovalNotifierBase, ApprovalRequest

logger = structlog.get_logger(__name__)


class NullApprovalNotifier(ApprovalNotifierBase):
    """
    No-op approval notifier.

    Used when APPROVAL_NOTIFIER=none (the default). Approval requests are
    created and the gate works correctly — approvers must use the REST API
    directly to approve or reject.
    """

    notifier_name = "none"

    def is_configured(self) -> bool:
        return True

    async def send_approval_request(self, request: ApprovalRequest) -> str:
        logger.warning(
            "approval_notification_skipped",
            reason="No approval notifier configured (APPROVAL_NOTIFIER=none)",
            approval_uuid=str(request.approval_uuid),
            workflow=request.workflow_name,
            hint=(
                "Set APPROVAL_NOTIFIER=slack or APPROVAL_NOTIFIER=teams and "
                "configure the corresponding credentials to enable notifications"
            ),
        )
        return ""

    async def send_result_notification(
        self,
        request: ApprovalRequest,
        approved: bool,
        responder_id: str | None,
    ) -> None:
        logger.info(
            "approval_result_notification_skipped",
            reason="No approval notifier configured",
            approval_uuid=str(request.approval_uuid),
            approved=approved,
        )
