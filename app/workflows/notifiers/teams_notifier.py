"""
TeamsApprovalNotifier — sends Adaptive Card approval messages via Teams incoming webhook.

Teams incoming webhooks do NOT support interactive button callbacks via webhooks.
Approval decisions must be made via the Calseta REST API:
  POST /v1/workflow-approvals/{uuid}/approve
  POST /v1/workflow-approvals/{uuid}/reject

The card includes direct links to these endpoints for approvers.
"""

from __future__ import annotations

import structlog

from app.workflows.notifiers.base import ApprovalNotifierBase, ApprovalRequest

logger = structlog.get_logger(__name__)


class TeamsApprovalNotifier(ApprovalNotifierBase):
    """
    Sends Teams Adaptive Card approval messages via incoming webhook.

    Required config:
    - TEAMS_WEBHOOK_URL: incoming webhook URL for the target channel

    Optional:
    - CALSETA_BASE_URL: base URL for constructing approve/reject links
      (default: http://localhost:8000)
    """

    notifier_name = "teams"

    def __init__(self, cfg: object) -> None:
        self._cfg = cfg  # type: ignore[assignment]

    def is_configured(self) -> bool:
        return bool(getattr(self._cfg, "TEAMS_WEBHOOK_URL", ""))

    def _base_url(self) -> str:
        return getattr(self._cfg, "CALSETA_BASE_URL", "http://localhost:8000").rstrip("/")

    def _build_approval_card(self, request: ApprovalRequest) -> dict:
        confidence_pct = f"{request.confidence * 100:.0f}%"
        base_url = self._base_url()
        approve_url = f"{base_url}/v1/workflow-approvals/{request.approval_uuid}/approve"
        reject_url = f"{base_url}/v1/workflow-approvals/{request.approval_uuid}/reject"

        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                        "type": "AdaptiveCard",
                        "version": "1.4",
                        "body": [
                            {
                                "type": "TextBlock",
                                "size": "Large",
                                "weight": "Bolder",
                                "text": (
                                    f"[{request.workflow_risk_level.upper()} RISK] "
                                    f"Workflow Approval Required"
                                ),
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": request.workflow_name,
                                "weight": "Bolder",
                                "wrap": True,
                            },
                            {
                                "type": "FactSet",
                                "facts": [
                                    {"title": "Indicator", "value": f"{request.indicator_type}: {request.indicator_value}"},
                                    {"title": "Trigger", "value": request.trigger_source},
                                    {"title": "Confidence", "value": confidence_pct},
                                    {"title": "Risk Level", "value": request.workflow_risk_level},
                                    {"title": "Expires", "value": request.expires_at.strftime("%Y-%m-%d %H:%M UTC")},
                                ],
                            },
                            {
                                "type": "TextBlock",
                                "text": f"**Agent reason:** {request.reason}",
                                "wrap": True,
                            },
                            {
                                "type": "TextBlock",
                                "text": "Use the buttons below (REST API) to approve or reject:",
                                "wrap": True,
                                "isSubtle": True,
                            },
                        ],
                        "actions": [
                            {
                                "type": "Action.OpenUrl",
                                "title": "Approve",
                                "url": approve_url,
                                "style": "positive",
                            },
                            {
                                "type": "Action.OpenUrl",
                                "title": "Reject",
                                "url": reject_url,
                                "style": "destructive",
                            },
                        ],
                    },
                }
            ],
        }

    async def send_approval_request(self, request: ApprovalRequest) -> str:
        """
        POST an Adaptive Card to the Teams webhook URL.

        Returns empty string (Teams webhooks don't return a usable message ID
        for thread replies).
        """
        import httpx

        webhook_url = getattr(self._cfg, "TEAMS_WEBHOOK_URL", "")
        if not webhook_url:
            return ""

        try:
            card = self._build_approval_card(request)
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(webhook_url, json=card)

            if resp.status_code not in (200, 201, 202):
                logger.error(
                    "teams_approval_send_failed",
                    status=resp.status_code,
                    body=resp.text[:200],
                    approval_uuid=str(request.approval_uuid),
                )
                return ""

            logger.info(
                "teams_approval_sent",
                approval_uuid=str(request.approval_uuid),
            )
            return ""  # Teams webhooks don't return a thread-able message ID

        except Exception as exc:
            logger.error(
                "teams_approval_send_exception",
                error=str(exc),
                approval_uuid=str(request.approval_uuid),
            )
            return ""

    async def send_result_notification(
        self,
        request: ApprovalRequest,
        approved: bool,
        responder_id: str | None,
    ) -> None:
        """POST a follow-up Adaptive Card with the approval decision result."""
        import httpx

        webhook_url = getattr(self._cfg, "TEAMS_WEBHOOK_URL", "")
        if not webhook_url:
            return

        try:
            outcome = "Approved" if approved else "Rejected"
            by_line = f" by {responder_id}" if responder_id else ""
            color = "Good" if approved else "Attention"

            facts = [
                {"title": "Decision", "value": f"{outcome}{by_line}"},
                {"title": "Workflow", "value": request.workflow_name},
            ]
            if request.execution_result:
                msg = request.execution_result.get("message", "")
                facts.append({"title": "Execution result", "value": msg})

            card = {
                "type": "message",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": {
                            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                            "type": "AdaptiveCard",
                            "version": "1.4",
                            "body": [
                                {
                                    "type": "TextBlock",
                                    "size": "Medium",
                                    "weight": "Bolder",
                                    "color": color,
                                    "text": f"Workflow {outcome}: {request.workflow_name}",
                                    "wrap": True,
                                },
                                {"type": "FactSet", "facts": facts},
                            ],
                        },
                    }
                ],
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.post(webhook_url, json=card)

        except Exception as exc:
            logger.error(
                "teams_result_notification_failed",
                error=str(exc),
                approval_uuid=str(request.approval_uuid),
            )
