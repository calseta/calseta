"""
SlackApprovalNotifier — sends Block Kit approval messages via Slack chat.postMessage.

Approval buttons embed the approval_request_uuid in the block_id so the
callback endpoint can route decisions without a state lookup.

Thread replies use thread_ts = external_message_id (the ts of the original message).
"""

from __future__ import annotations

import structlog

from app.workflows.notifiers.base import ApprovalNotifierBase, ApprovalRequest

logger = structlog.get_logger(__name__)


class SlackApprovalNotifier(ApprovalNotifierBase):
    """
    Sends Slack Block Kit approval messages.

    Required config:
    - SLACK_BOT_TOKEN: bot token with chat:write scope
    - SLACK_APPROVAL_CHANNEL: channel ID or name (default: APPROVAL_DEFAULT_CHANNEL)

    Optional:
    - SLACK_SIGNING_SECRET: validates callback signatures
    """

    notifier_name = "slack"

    def __init__(self, cfg: object) -> None:
        self._cfg = cfg  # type: ignore[assignment]

    def is_configured(self) -> bool:
        return bool(getattr(self._cfg, "SLACK_BOT_TOKEN", ""))

    def _channel(self, request: ApprovalRequest) -> str:
        """Resolve the target channel: per-workflow channel or default."""
        return (
            request.approval_channel
            or getattr(self._cfg, "APPROVAL_DEFAULT_CHANNEL", "")
            or "#general"
        )

    def _base_url(self) -> str:
        return getattr(self._cfg, "CALSETA_BASE_URL", "http://localhost:8000").rstrip("/")

    def _build_approval_blocks(self, request: ApprovalRequest) -> list[dict]:
        confidence_pct = f"{request.confidence * 100:.0f}%"
        approve_action = f"approve:{request.approval_uuid}"
        reject_action = f"reject:{request.approval_uuid}"

        blocks: list[dict] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": (
                        f"[{request.workflow_risk_level.upper()} RISK] "
                        f"Workflow Approval: {request.workflow_name}"
                    ),
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Indicator:* `{request.indicator_type}: {request.indicator_value}`"},
                    {"type": "mrkdwn", "text": f"*Trigger:* {request.trigger_source}"},
                    {"type": "mrkdwn", "text": f"*Confidence:* {confidence_pct}"},
                    {"type": "mrkdwn", "text": f"*Expires:* {request.expires_at.strftime('%Y-%m-%d %H:%M UTC')}"},
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Agent reason:*\n{request.reason}"},
            },
            {
                "type": "actions",
                "block_id": f"approval:{request.approval_uuid}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": approve_action,
                        "value": str(request.approval_uuid),
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": reject_action,
                        "value": str(request.approval_uuid),
                    },
                ],
            },
        ]

        # Browser-based approval fallback link
        if request.decide_token:
            base_url = self._base_url()
            decide_url = (
                f"{base_url}/v1/workflow-approvals/{request.approval_uuid}"
                f"/decide?token={request.decide_token}"
            )
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Or <{decide_url}|decide via browser>",
                    }
                ],
            })

        return blocks

    async def send_approval_request(self, request: ApprovalRequest) -> str:
        """
        Post a Block Kit approval message to the configured Slack channel.

        Returns the message timestamp (ts) for use as thread_ts in replies.
        Returns empty string on failure.
        """
        import httpx

        try:
            channel = self._channel(request)
            blocks = self._build_approval_blocks(request)

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {getattr(self._cfg, 'SLACK_BOT_TOKEN', '')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "channel": channel,
                        "blocks": blocks,
                        "text": (
                            f"Workflow approval needed: {request.workflow_name} "
                            f"({request.workflow_risk_level} risk)"
                        ),
                    },
                )

            data = resp.json()
            if not data.get("ok"):
                logger.error(
                    "slack_approval_send_failed",
                    error=data.get("error", "unknown"),
                    approval_uuid=str(request.approval_uuid),
                )
                return ""

            ts = data.get("ts", "")
            logger.info(
                "slack_approval_sent",
                approval_uuid=str(request.approval_uuid),
                channel=channel,
                ts=ts,
            )
            return str(ts)

        except Exception as exc:
            logger.error(
                "slack_approval_send_exception",
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
        """Post a follow-up message to the original approval thread."""
        import httpx

        try:
            channel = self._channel(request)
            outcome = "Approved" if approved else "Rejected"
            by_line = f"by {responder_id}" if responder_id else ""

            result_text = f"*Decision:* {outcome} {by_line}".strip()
            if request.execution_result:
                msg = request.execution_result.get("message", "")
                success = request.execution_result.get("success", False)
                status_icon = ":white_check_mark:" if success else ":x:"
                result_text += f"\n{status_icon} *Execution result:* {msg}"

            payload: dict = {
                "channel": channel,
                "text": f"Workflow {outcome}: {request.workflow_name}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": result_text},
                    }
                ],
            }

            # Thread reply if we have the original message ts
            if request.execution_result and "ts" in (request.execution_result or {}):
                payload["thread_ts"] = request.execution_result["ts"]

            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {getattr(self._cfg, 'SLACK_BOT_TOKEN', '')}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except Exception as exc:
            logger.error(
                "slack_result_notification_failed",
                error=str(exc),
                approval_uuid=str(request.approval_uuid),
            )
