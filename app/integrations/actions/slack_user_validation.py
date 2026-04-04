"""SlackUserValidationIntegration — DM users to confirm or deny security activity."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.user_validation_template import UserValidationTemplate
from app.integrations.actions.base import ActionIntegration, ExecutionResult

if TYPE_CHECKING:
    from app.db.models.agent_action import AgentAction

logger = structlog.get_logger()

_SLACK_API_BASE = "https://slack.com/api"
_DEFAULT_TIMEOUT = 15

# Substitution tokens supported in UserValidationTemplate.message_body
_SUBSTITUTION_FIELDS = (
    "title",
    "severity",
    "source_name",
    "occurred_at",
    "alert_uuid",
)


class SlackUserValidationIntegration(ActionIntegration):
    """
    Slack user validation integration.

    Sends a DM to the affected user asking them to confirm or deny the
    security activity described in the alert.

    Required action.payload fields:
      - slack_user_id: str    — Slack user ID ("U…") or email for lookup
      - template_name: str    — name of UserValidationTemplate to use
      - alert_context: dict   — alert fields for message rendering (title, occurred_at, etc.)
      - timeout_hours: int    — how long to wait for response (informational only)
      - assignment_id: str    — for linking the callback

    The ExecutionResult.data dict includes:
      - ts: str              — Slack message timestamp (for threading/tracking)
      - channel_id: str      — Slack DM channel ID

    This integration needs DB access to load the template at execution time.
    Pass ``db: AsyncSession`` to the constructor.
    """

    default_approval_mode = "never"

    def __init__(
        self,
        bot_token: str | None = None,
        db: AsyncSession | None = None,
    ) -> None:
        self._token = bot_token or settings.SLACK_BOT_TOKEN or None
        self._db = db

    def is_configured(self) -> bool:
        return bool(self._token)

    async def execute(self, action: AgentAction) -> ExecutionResult:
        if not self.is_configured():
            return ExecutionResult.fail(
                "Slack user validation not configured: SLACK_BOT_TOKEN is missing",
                {"action_id": str(action.uuid)},
            )
        try:
            return await self._do_execute(action)
        except Exception as exc:
            logger.exception(
                "slack_user_validation_unexpected_error",
                action_id=str(action.uuid),
                error=str(exc),
            )
            return ExecutionResult.fail(
                f"Unexpected error executing Slack user validation: {exc}",
                {"action_id": str(action.uuid)},
            )

    async def _do_execute(self, action: AgentAction) -> ExecutionResult:
        payload: dict[str, Any] = action.payload or {}

        slack_user_id: str | None = payload.get("slack_user_id")
        if not slack_user_id:
            return ExecutionResult.fail(
                "action.payload.slack_user_id is required",
                {"action_id": str(action.uuid)},
            )

        template_name: str | None = payload.get("template_name")
        alert_context: dict[str, Any] = payload.get("alert_context") or {}
        assignment_id: str | None = payload.get("assignment_id")

        # Resolve the Slack user ID if an email was given
        if "@" in slack_user_id:
            resolved = await self._lookup_user_by_email(slack_user_id)
            if not resolved:
                return ExecutionResult.fail(
                    f"Could not find Slack user for email: {slack_user_id}",
                    {"action_id": str(action.uuid), "email": slack_user_id},
                )
            slack_user_id = resolved

        # Build message text
        message_text = await self._render_message(template_name, alert_context, assignment_id)

        # Open a DM channel
        channel_id = await self._open_dm(slack_user_id)
        if not channel_id:
            return ExecutionResult.fail(
                f"Failed to open DM channel with Slack user: {slack_user_id}",
                {"action_id": str(action.uuid), "slack_user_id": slack_user_id},
            )

        # Post the message
        post_result = await self._api_call(
            "chat.postMessage",
            {"channel": channel_id, "text": message_text},
        )
        if not post_result.get("ok"):
            error = post_result.get("error", "unknown")
            logger.warning(
                "slack_user_validation_post_failed",
                action_id=str(action.uuid),
                slack_user_id=slack_user_id,
                slack_error=error,
            )
            return ExecutionResult.fail(
                f"Slack API error sending DM: {error}",
                {"action_id": str(action.uuid), "slack_error": error},
            )

        ts: str | None = post_result.get("ts") or post_result.get("message", {}).get("ts")
        logger.info(
            "slack_user_validation_sent",
            action_id=str(action.uuid),
            slack_user_id=slack_user_id,
            channel_id=channel_id,
            ts=ts,
            assignment_id=assignment_id,
        )
        return ExecutionResult.ok(
            f"User validation DM sent to {slack_user_id}",
            {
                "action_id": str(action.uuid),
                "slack_user_id": slack_user_id,
                "channel_id": channel_id,
                "ts": ts,
                "assignment_id": assignment_id,
            },
        )

    async def _render_message(
        self,
        template_name: str | None,
        alert_context: dict[str, Any],
        assignment_id: str | None,
    ) -> str:
        """
        Load the named template from the database and render substitution tokens.

        Falls back to a default message if template is not found or DB is unavailable.
        Tokens: {{alert.title}}, {{alert.severity}}, {{alert.occurred_at}}, etc.
        """
        template_body: str | None = None

        if template_name and self._db is not None:
            try:
                stmt = select(UserValidationTemplate).where(
                    UserValidationTemplate.name == template_name
                )
                result = await self._db.execute(stmt)
                template = result.scalar_one_or_none()
                if template:
                    template_body = template.message_body
            except Exception as exc:
                logger.warning(
                    "slack_user_validation_template_load_failed",
                    template_name=template_name,
                    error=str(exc),
                )

        if template_body is None:
            # Default message when no template is found
            title = alert_context.get("title", "a security alert")
            occurred_at = alert_context.get("occurred_at", "recently")
            template_body = (
                f"Hi! Our security system detected activity that may require your confirmation.\n\n"
                f"*Alert:* {title}\n"
                f"*Time:* {occurred_at}\n\n"
                "Was this activity initiated by you?"
            )
            if assignment_id:
                template_body += f"\n\n_Assignment ID: `{assignment_id}`_"
            return template_body

        # Perform {{alert.field}} substitutions
        for field in _SUBSTITUTION_FIELDS:
            value = str(alert_context.get(field, ""))
            template_body = template_body.replace(f"{{{{alert.{field}}}}}", value)

        if assignment_id:
            template_body = template_body.replace("{{assignment_id}}", assignment_id)

        return template_body

    async def _open_dm(self, slack_user_id: str) -> str | None:
        """Open a DM channel with the given Slack user ID and return the channel ID."""
        result = await self._api_call(
            "conversations.open",
            {"users": slack_user_id},
        )
        if result.get("ok"):
            return result.get("channel", {}).get("id")
        logger.warning(
            "slack_user_validation_open_dm_failed",
            slack_user_id=slack_user_id,
            slack_error=result.get("error"),
        )
        return None

    async def _lookup_user_by_email(self, email: str) -> str | None:
        """Look up a Slack user ID by email address."""
        result = await self._api_call(
            "users.lookupByEmail",
            {},
            params={"email": email},
        )
        if result.get("ok"):
            return result.get("user", {}).get("id")
        return None

    async def _api_call(
        self,
        method: str,
        body: dict[str, Any],
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a Slack Web API call. Returns the JSON response dict."""
        url = f"{_SLACK_API_BASE}/{method}"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            if params:
                response = await client.get(url, headers=headers, params=params)
            else:
                response = await client.post(url, json=body, headers=headers)
            response.raise_for_status()
            return response.json()

    def supported_actions(self) -> list[str]:
        return ["validate_user_activity"]
