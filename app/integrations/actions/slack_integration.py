"""SlackActionIntegration — Slack notifications, channel creation, and user validation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.config import settings
from app.integrations.actions.base import ActionIntegration, ExecutionResult

if TYPE_CHECKING:
    from app.db.models.agent_action import AgentAction

logger = structlog.get_logger()

_SLACK_API_BASE = "https://slack.com/api"
_DEFAULT_TIMEOUT = 15


class SlackActionIntegration(ActionIntegration):
    """
    Slack integration for notification and escalation actions.

    Supported action subtypes:
      - send_alert:          Post a formatted alert message to a channel
      - notify_oncall:       DM or channel post with urgency formatting
      - create_channel:      Create a new Slack channel (for incident response)
      - validate_user_activity: Delegate to SlackUserValidationIntegration pattern
                                (basic fallback — prefer SlackUserValidationIntegration
                                 when DB access is available)

    Config: ``SLACK_BOT_TOKEN`` env var (or constructor override).

    Required payload fields per subtype:
      send_alert / notify_oncall:
        - channel: str     — Slack channel ID (e.g. "C0123456789") or user ID for DMs
        - message: str     — message text
        - alert_uuid: str  — optional, appended to message for context

      create_channel:
        - channel_name: str — channel name (lower-case, no spaces)
        - is_private: bool  — optional, default False
    """

    default_approval_mode = "never"

    def __init__(self, bot_token: str | None = None) -> None:
        self._token = bot_token or settings.SLACK_BOT_TOKEN or None

    def is_configured(self) -> bool:
        return bool(self._token)

    async def execute(self, action: AgentAction) -> ExecutionResult:
        if not self.is_configured():
            return ExecutionResult.fail(
                "Slack integration not configured: SLACK_BOT_TOKEN is missing",
                {"action_id": str(action.uuid)},
            )
        try:
            return await self._dispatch(action)
        except Exception as exc:
            logger.exception(
                "slack_integration_unexpected_error",
                action_id=str(action.uuid),
                action_subtype=action.action_subtype,
                error=str(exc),
            )
            return ExecutionResult.fail(
                f"Unexpected error executing Slack action: {exc}",
                {"action_id": str(action.uuid)},
            )

    async def _dispatch(self, action: AgentAction) -> ExecutionResult:
        subtype = action.action_subtype
        if subtype in ("send_alert", "notify_oncall"):
            return await self._post_message(action)
        if subtype == "create_channel":
            return await self._create_channel(action)
        if subtype == "validate_user_activity":
            # Fallback path — use SlackUserValidationIntegration when DB is available.
            return await self._post_message(action)
        return ExecutionResult.fail(
            f"Unknown Slack action subtype: {subtype}",
            {"action_id": str(action.uuid), "action_subtype": subtype},
        )

    async def _post_message(self, action: AgentAction) -> ExecutionResult:
        payload: dict[str, Any] = action.payload or {}

        channel = payload.get("channel")
        if not channel:
            return ExecutionResult.fail(
                "action.payload.channel is required",
                {"action_id": str(action.uuid)},
            )

        message = payload.get("message", "")
        alert_uuid = payload.get("alert_uuid")

        is_urgent = action.action_subtype == "notify_oncall"
        text = self._format_message(message, alert_uuid, urgent=is_urgent)

        body: dict[str, Any] = {"channel": channel, "text": text}

        result = await self._api_call("chat.postMessage", body)
        if not result.get("ok"):
            error = result.get("error", "unknown")
            logger.warning(
                "slack_post_message_failed",
                action_id=str(action.uuid),
                channel=channel,
                slack_error=error,
            )
            return ExecutionResult.fail(
                f"Slack API error: {error}",
                {"action_id": str(action.uuid), "slack_error": error},
            )

        ts = result.get("ts") or result.get("message", {}).get("ts")
        logger.info(
            "slack_message_sent",
            action_id=str(action.uuid),
            channel=channel,
            ts=ts,
        )
        return ExecutionResult.ok(
            f"Slack message sent to {channel}",
            {"action_id": str(action.uuid), "channel": channel, "ts": ts},
        )

    async def _create_channel(self, action: AgentAction) -> ExecutionResult:
        payload: dict[str, Any] = action.payload or {}

        channel_name = payload.get("channel_name")
        if not channel_name:
            return ExecutionResult.fail(
                "action.payload.channel_name is required",
                {"action_id": str(action.uuid)},
            )

        is_private = bool(payload.get("is_private", False))

        body: dict[str, Any] = {
            "name": channel_name.lower().replace(" ", "-"),
            "is_private": is_private,
        }
        result = await self._api_call("conversations.create", body)
        if not result.get("ok"):
            error = result.get("error", "unknown")
            logger.warning(
                "slack_create_channel_failed",
                action_id=str(action.uuid),
                channel_name=channel_name,
                slack_error=error,
            )
            return ExecutionResult.fail(
                f"Slack API error creating channel: {error}",
                {"action_id": str(action.uuid), "slack_error": error},
            )

        channel_id = result.get("channel", {}).get("id")
        logger.info(
            "slack_channel_created",
            action_id=str(action.uuid),
            channel_name=channel_name,
            channel_id=channel_id,
        )
        return ExecutionResult.ok(
            f"Slack channel '{channel_name}' created",
            {
                "action_id": str(action.uuid),
                "channel_name": channel_name,
                "channel_id": channel_id,
            },
        )

    async def _api_call(self, method: str, body: dict[str, Any]) -> dict[str, Any]:
        """Make a Slack Web API call. Returns the JSON response dict."""
        url = f"{_SLACK_API_BASE}/{method}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

    @staticmethod
    def _format_message(message: str, alert_uuid: str | None, urgent: bool) -> str:
        prefix = ":rotating_light: *URGENT* " if urgent else ""
        suffix = f"\n_Alert ID: `{alert_uuid}`_" if alert_uuid else ""
        return f"{prefix}{message}{suffix}"

    def supported_actions(self) -> list[str]:
        return ["send_alert", "notify_oncall", "create_channel", "validate_user_activity"]
