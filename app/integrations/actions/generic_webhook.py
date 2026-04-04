"""GenericWebhookIntegration — POST action payload to a configurable URL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.integrations.actions.base import ActionIntegration, ExecutionResult
from app.services.url_validation import validate_outbound_url

if TYPE_CHECKING:
    from app.db.models.agent_action import AgentAction

logger = structlog.get_logger()

_DEFAULT_TIMEOUT_SECONDS = 30


class GenericWebhookIntegration(ActionIntegration):
    """
    Generic webhook integration — POST action payload to a configurable URL.

    Required action.payload fields:
      - url: str             — the webhook endpoint to POST to
    Optional action.payload fields:
      - headers: dict        — additional HTTP headers to include
      - timeout_seconds: int — request timeout (default 30)
      - body: dict           — override the default body; defaults to full payload

    SSRF protection: ``url`` is validated via ``validate_outbound_url()`` before
    any network call is made. Private/loopback/metadata addresses are blocked.

    Approval mode defaults to "never" — these are notification-style webhooks that
    don't require human sign-off. Override via action-level approval_mode if needed.
    """

    default_approval_mode = "never"

    def is_configured(self) -> bool:
        # No global credentials required — URL comes from action.payload at execution time.
        return True

    async def execute(self, action: AgentAction) -> ExecutionResult:
        try:
            return await self._do_execute(action)
        except Exception as exc:
            logger.exception(
                "generic_webhook_unexpected_error",
                action_id=str(action.uuid),
                error=str(exc),
            )
            return ExecutionResult.fail(
                f"Unexpected error executing webhook: {exc}",
                {"action_id": str(action.uuid)},
            )

    async def _do_execute(self, action: AgentAction) -> ExecutionResult:
        payload: dict[str, Any] = action.payload or {}

        url = payload.get("url")
        if not url:
            return ExecutionResult.fail(
                "action.payload.url is required for webhook_post actions",
                {"action_id": str(action.uuid)},
            )

        # SSRF protection — raises ValueError if URL is unsafe
        try:
            validate_outbound_url(str(url))
        except ValueError as exc:
            logger.warning(
                "generic_webhook_ssrf_blocked",
                action_id=str(action.uuid),
                url=url,
                reason=str(exc),
            )
            return ExecutionResult.fail(
                f"Webhook URL blocked: {exc}",
                {"action_id": str(action.uuid), "url": url},
            )

        extra_headers: dict[str, str] = payload.get("headers") or {}
        timeout_seconds: int = int(payload.get("timeout_seconds") or _DEFAULT_TIMEOUT_SECONDS)

        # Default body: full payload minus the transport-control keys
        body: dict[str, Any] = payload.get("body") or {
            k: v
            for k, v in payload.items()
            if k not in ("url", "headers", "timeout_seconds", "body")
        }
        # Always include action metadata so the receiver can correlate
        body.setdefault("action_id", str(action.uuid))
        body.setdefault("action_type", action.action_type)
        body.setdefault("action_subtype", action.action_subtype)

        headers = {"Content-Type": "application/json", **extra_headers}

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.TimeoutException:
            logger.warning(
                "generic_webhook_timeout",
                action_id=str(action.uuid),
                url=url,
                timeout_seconds=timeout_seconds,
            )
            return ExecutionResult.fail(
                f"Webhook request timed out after {timeout_seconds}s",
                {"action_id": str(action.uuid), "url": url},
            )
        except httpx.RequestError as exc:
            logger.warning(
                "generic_webhook_request_error",
                action_id=str(action.uuid),
                url=url,
                error=str(exc),
            )
            return ExecutionResult.fail(
                f"Webhook request failed: {exc}",
                {"action_id": str(action.uuid), "url": url},
            )

        if response.is_success:
            logger.info(
                "generic_webhook_success",
                action_id=str(action.uuid),
                url=url,
                status_code=response.status_code,
            )
            return ExecutionResult.ok(
                f"Webhook delivered: HTTP {response.status_code}",
                {
                    "action_id": str(action.uuid),
                    "url": url,
                    "status_code": response.status_code,
                },
            )

        logger.warning(
            "generic_webhook_non_2xx",
            action_id=str(action.uuid),
            url=url,
            status_code=response.status_code,
        )
        return ExecutionResult.fail(
            f"Webhook returned non-2xx status: HTTP {response.status_code}",
            {
                "action_id": str(action.uuid),
                "url": url,
                "status_code": response.status_code,
            },
        )

    def supported_actions(self) -> list[str]:
        return ["webhook_post"]
