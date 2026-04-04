"""CrowdStrikeIntegration — endpoint isolation and containment via Falcon API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.config import settings
from app.integrations.actions.base import ActionIntegration, ExecutionResult

if TYPE_CHECKING:
    from app.db.models.agent_action import AgentAction

logger = structlog.get_logger()

_DEFAULT_BASE_URL = "https://api.crowdstrike.com"
_TOKEN_TIMEOUT = 15
_ACTION_TIMEOUT = 30


class CrowdStrikeIntegration(ActionIntegration):
    """
    CrowdStrike Falcon integration for endpoint containment actions.

    Supported action subtypes:
      - isolate_host:      Network-isolate an endpoint (contain)
      - lift_containment:  Remove network isolation from an endpoint

    Config (env vars):
      - CROWDSTRIKE_CLIENT_ID
      - CROWDSTRIKE_CLIENT_SECRET
      - CROWDSTRIKE_BASE_URL  (optional, defaults to "https://api.crowdstrike.com")

    Required action.payload fields:
      - device_id: str  — CrowdStrike Device/Host ID (also accepted as host_id)

    Approval mode is "always" and ``bypass_confidence_override`` is False, meaning
    these containment actions always require human approval regardless of confidence.
    ``rollback()`` lifts containment, reversing an ``isolate_host`` action.
    """

    default_approval_mode = "always"
    bypass_confidence_override = False

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._client_id = client_id or settings.CROWDSTRIKE_CLIENT_ID or None
        self._client_secret = client_secret or settings.CROWDSTRIKE_CLIENT_SECRET or None
        self._base_url = (
            base_url
            or settings.CROWDSTRIKE_BASE_URL
            or _DEFAULT_BASE_URL
        ).rstrip("/")

    def is_configured(self) -> bool:
        return bool(self._client_id and self._client_secret)

    async def execute(self, action: AgentAction) -> ExecutionResult:
        if not self.is_configured():
            return ExecutionResult.fail(
                "CrowdStrike integration not configured: "
                "CROWDSTRIKE_CLIENT_ID and CROWDSTRIKE_CLIENT_SECRET are required",
                {"action_id": str(action.uuid)},
            )
        try:
            return await self._dispatch(action)
        except Exception as exc:
            logger.exception(
                "crowdstrike_unexpected_error",
                action_id=str(action.uuid),
                action_subtype=action.action_subtype,
                error=str(exc),
            )
            return ExecutionResult.fail(
                f"Unexpected error executing CrowdStrike action: {exc}",
                {"action_id": str(action.uuid)},
            )

    async def _dispatch(self, action: AgentAction) -> ExecutionResult:
        subtype = action.action_subtype
        if subtype == "isolate_host":
            return await self._contain_device(action, contain=True)
        if subtype == "lift_containment":
            return await self._contain_device(action, contain=False)
        return ExecutionResult.fail(
            f"Unknown CrowdStrike action subtype: {subtype}",
            {"action_id": str(action.uuid), "action_subtype": subtype},
        )

    async def rollback(self, action: AgentAction) -> ExecutionResult:
        """Lift containment — reverses isolate_host."""
        if not self.is_configured():
            return ExecutionResult.fail(
                "CrowdStrike integration not configured",
                {"action_id": str(action.uuid)},
            )
        try:
            return await self._contain_device(action, contain=False)
        except Exception as exc:
            logger.exception(
                "crowdstrike_rollback_unexpected_error",
                action_id=str(action.uuid),
                error=str(exc),
            )
            return ExecutionResult.fail(
                f"Unexpected error during CrowdStrike rollback: {exc}",
                {"action_id": str(action.uuid)},
            )

    async def _contain_device(self, action: AgentAction, contain: bool) -> ExecutionResult:
        payload: dict[str, Any] = action.payload or {}
        device_id = payload.get("device_id") or payload.get("host_id")
        if not device_id:
            return ExecutionResult.fail(
                "action.payload.device_id (or host_id) is required",
                {"action_id": str(action.uuid)},
            )

        token = await self._get_token()
        if not token:
            return ExecutionResult.fail(
                "Failed to obtain CrowdStrike OAuth2 token",
                {"action_id": str(action.uuid)},
            )

        action_name = "contain" if contain else "lift_containment"
        url = f"{self._base_url}/devices/entities/devices-actions/v2?action_name={action_name}"
        body = {"ids": [str(device_id)]}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=_ACTION_TIMEOUT) as client:
                response = await client.post(url, json=body, headers=headers)
        except httpx.RequestError as exc:
            logger.warning(
                "crowdstrike_request_error",
                action_id=str(action.uuid),
                device_id=device_id,
                action_name=action_name,
                error=str(exc),
            )
            return ExecutionResult.fail(
                f"CrowdStrike API request failed: {exc}",
                {"action_id": str(action.uuid), "device_id": device_id},
            )

        if response.status_code in (200, 202):
            verb = "isolated" if contain else "containment lifted for"
            logger.info(
                "crowdstrike_action_success",
                action_id=str(action.uuid),
                device_id=device_id,
                action_name=action_name,
                status_code=response.status_code,
            )
            return ExecutionResult.ok(
                f"Host {verb}: {device_id}",
                {
                    "action_id": str(action.uuid),
                    "device_id": device_id,
                    "action_name": action_name,
                    "status_code": response.status_code,
                    "rollback_supported": True,
                },
                rollback_supported=True,
            )

        logger.warning(
            "crowdstrike_action_non_2xx",
            action_id=str(action.uuid),
            device_id=device_id,
            action_name=action_name,
            status_code=response.status_code,
        )
        return ExecutionResult.fail(
            f"CrowdStrike API returned HTTP {response.status_code}",
            {
                "action_id": str(action.uuid),
                "device_id": device_id,
                "status_code": response.status_code,
            },
        )

    async def _get_token(self) -> str | None:
        """Obtain an OAuth2 access token via client credentials flow."""
        url = f"{self._base_url}/oauth2/token"
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        try:
            async with httpx.AsyncClient(timeout=_TOKEN_TIMEOUT) as client:
                response = await client.post(
                    url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            if response.status_code == 201:
                token: str | None = response.json().get("access_token")
                return token
            logger.warning(
                "crowdstrike_token_error",
                status_code=response.status_code,
            )
            return None
        except Exception as exc:
            logger.warning("crowdstrike_token_exception", error=str(exc))
            return None

    def supported_actions(self) -> list[str]:
        return ["isolate_host", "lift_containment"]
