"""EntraIDActionIntegration — Microsoft Entra ID (Azure AD) identity response actions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.config import settings
from app.integrations.actions.base import ActionIntegration, ExecutionResult

if TYPE_CHECKING:
    from app.db.models.agent_action import AgentAction

logger = structlog.get_logger()

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TOKEN_ENDPOINT = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
_GRAPH_SCOPE = "https://graph.microsoft.com/.default"
_TOKEN_TIMEOUT = 15
_ACTION_TIMEOUT = 30


class EntraIDActionIntegration(ActionIntegration):
    """
    Microsoft Entra ID (Azure AD) integration for identity response actions.

    Supported action subtypes:
      - disable_user:     Disable a user account (accountEnabled = false)
      - revoke_sessions:  Revoke all active sign-in sessions for a user
      - force_mfa:        Require re-registration of MFA methods (delete existing methods)

    Config (env vars — reuses existing Entra enrichment credentials):
      - ENTRA_TENANT_ID
      - ENTRA_CLIENT_ID
      - ENTRA_CLIENT_SECRET

    Required action.payload fields:
      - user_id: str  — user UPN (user@domain.com) or Entra object ID

    ``bypass_confidence_override`` is True — identity actions ALWAYS require human
    approval regardless of the agent's confidence score. This is a deliberate safety
    constraint for account-level actions.

    ``rollback()`` supports re-enabling a user (reverses disable_user).
    """

    default_approval_mode = "always"
    bypass_confidence_override = True  # Identity actions always require human approval

    def __init__(
        self,
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._tenant_id = tenant_id or settings.ENTRA_TENANT_ID or None
        self._client_id = client_id or settings.ENTRA_CLIENT_ID or None
        self._client_secret = client_secret or settings.ENTRA_CLIENT_SECRET or None

    def is_configured(self) -> bool:
        return bool(self._tenant_id and self._client_id and self._client_secret)

    async def execute(self, action: AgentAction) -> ExecutionResult:
        if not self.is_configured():
            return ExecutionResult.fail(
                "Entra ID integration not configured: "
                "ENTRA_TENANT_ID, ENTRA_CLIENT_ID, and ENTRA_CLIENT_SECRET are required",
                {"action_id": str(action.uuid)},
            )
        try:
            return await self._dispatch(action)
        except Exception as exc:
            logger.exception(
                "entra_id_unexpected_error",
                action_id=str(action.uuid),
                action_subtype=action.action_subtype,
                error=str(exc),
            )
            return ExecutionResult.fail(
                f"Unexpected error executing Entra ID action: {exc}",
                {"action_id": str(action.uuid)},
            )

    async def _dispatch(self, action: AgentAction) -> ExecutionResult:
        subtype = action.action_subtype
        if subtype == "disable_user":
            return await self._set_account_enabled(action, enabled=False)
        if subtype == "revoke_sessions":
            return await self._revoke_sessions(action)
        if subtype == "force_mfa":
            return await self._force_mfa_reregistration(action)
        return ExecutionResult.fail(
            f"Unknown Entra ID action subtype: {subtype}",
            {"action_id": str(action.uuid), "action_subtype": subtype},
        )

    async def rollback(self, action: AgentAction) -> ExecutionResult:
        """Re-enable a user account — reverses disable_user."""
        if not self.is_configured():
            return ExecutionResult.fail(
                "Entra ID integration not configured",
                {"action_id": str(action.uuid)},
            )
        try:
            return await self._set_account_enabled(action, enabled=True)
        except Exception as exc:
            logger.exception(
                "entra_id_rollback_unexpected_error",
                action_id=str(action.uuid),
                error=str(exc),
            )
            return ExecutionResult.fail(
                f"Unexpected error during Entra ID rollback: {exc}",
                {"action_id": str(action.uuid)},
            )

    async def _set_account_enabled(self, action: AgentAction, enabled: bool) -> ExecutionResult:
        user_id = self._get_user_id(action)
        if not user_id:
            return ExecutionResult.fail(
                "action.payload.user_id is required",
                {"action_id": str(action.uuid)},
            )

        token = await self._get_token()
        if not token:
            return ExecutionResult.fail(
                "Failed to obtain Entra ID access token",
                {"action_id": str(action.uuid)},
            )

        url = f"{_GRAPH_BASE}/users/{user_id}"
        body = {"accountEnabled": enabled}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=_ACTION_TIMEOUT) as client:
                response = await client.patch(url, json=body, headers=headers)
        except httpx.RequestError as exc:
            return ExecutionResult.fail(
                f"Graph API request failed: {exc}",
                {"action_id": str(action.uuid), "user_id": user_id},
            )

        if response.status_code == 204:
            verb = "enabled" if enabled else "disabled"
            logger.info(
                "entra_id_account_updated",
                action_id=str(action.uuid),
                user_id=user_id,
                enabled=enabled,
            )
            return ExecutionResult.ok(
                f"User account {verb}: {user_id}",
                {
                    "action_id": str(action.uuid),
                    "user_id": user_id,
                    "account_enabled": enabled,
                    "rollback_supported": True,
                },
                rollback_supported=True,
            )

        return self._graph_error_result(action, response, user_id, "set_account_enabled")

    async def _revoke_sessions(self, action: AgentAction) -> ExecutionResult:
        user_id = self._get_user_id(action)
        if not user_id:
            return ExecutionResult.fail(
                "action.payload.user_id is required",
                {"action_id": str(action.uuid)},
            )

        token = await self._get_token()
        if not token:
            return ExecutionResult.fail(
                "Failed to obtain Entra ID access token",
                {"action_id": str(action.uuid)},
            )

        url = f"{_GRAPH_BASE}/users/{user_id}/revokeSignInSessions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=_ACTION_TIMEOUT) as client:
                response = await client.post(url, json={}, headers=headers)
        except httpx.RequestError as exc:
            return ExecutionResult.fail(
                f"Graph API request failed: {exc}",
                {"action_id": str(action.uuid), "user_id": user_id},
            )

        if response.status_code == 200:
            logger.info(
                "entra_id_sessions_revoked",
                action_id=str(action.uuid),
                user_id=user_id,
            )
            return ExecutionResult.ok(
                f"All sign-in sessions revoked for user: {user_id}",
                {"action_id": str(action.uuid), "user_id": user_id},
            )

        return self._graph_error_result(action, response, user_id, "revoke_sessions")

    async def _force_mfa_reregistration(self, action: AgentAction) -> ExecutionResult:
        """
        Force MFA re-registration by deleting all authentication methods
        (excluding password). The user must re-enroll on next sign-in.

        Graph API: GET /users/{id}/authentication/methods → DELETE each non-password method.
        """
        user_id = self._get_user_id(action)
        if not user_id:
            return ExecutionResult.fail(
                "action.payload.user_id is required",
                {"action_id": str(action.uuid)},
            )

        token = await self._get_token()
        if not token:
            return ExecutionResult.fail(
                "Failed to obtain Entra ID access token",
                {"action_id": str(action.uuid)},
            )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        # Enumerate auth methods
        list_url = f"{_GRAPH_BASE}/users/{user_id}/authentication/methods"
        try:
            async with httpx.AsyncClient(timeout=_ACTION_TIMEOUT) as client:
                list_resp = await client.get(list_url, headers=headers)
        except httpx.RequestError as exc:
            return ExecutionResult.fail(
                f"Graph API request failed listing auth methods: {exc}",
                {"action_id": str(action.uuid), "user_id": user_id},
            )

        if list_resp.status_code != 200:
            return self._graph_error_result(action, list_resp, user_id, "list_auth_methods")

        methods: list[dict[str, Any]] = list_resp.json().get("value", [])
        # Password method (#microsoft.graph.passwordAuthenticationMethod) cannot be deleted
        deletable = [
            m for m in methods
            if "#microsoft.graph.passwordAuthenticationMethod" not in m.get("@odata.type", "")
        ]

        deleted_count = 0
        errors: list[str] = []
        async with httpx.AsyncClient(timeout=_ACTION_TIMEOUT) as client:
            for method in deletable:
                method_id = method.get("id")
                odata_type = method.get("@odata.type", "")
                # Derive the resource segment from @odata.type
                segment = _odata_type_to_segment(odata_type)
                if not method_id or not segment:
                    continue
                delete_url = f"{_GRAPH_BASE}/users/{user_id}/authentication/{segment}/{method_id}"
                try:
                    del_resp = await client.delete(delete_url, headers=headers)
                    if del_resp.status_code == 204:
                        deleted_count += 1
                    else:
                        errors.append(f"{segment}/{method_id}: HTTP {del_resp.status_code}")
                except httpx.RequestError as exc:
                    errors.append(f"{segment}/{method_id}: {exc}")

        logger.info(
            "entra_id_mfa_reset",
            action_id=str(action.uuid),
            user_id=user_id,
            deleted_count=deleted_count,
            errors=errors,
        )

        if errors:
            return ExecutionResult.fail(
                f"MFA reset partial: {deleted_count} methods deleted, {len(errors)} errors",
                {
                    "action_id": str(action.uuid),
                    "user_id": user_id,
                    "deleted_count": deleted_count,
                    "errors": errors,
                },
            )

        return ExecutionResult.ok(
            f"MFA methods cleared for user: {user_id} ({deleted_count} methods deleted)",
            {
                "action_id": str(action.uuid),
                "user_id": user_id,
                "deleted_count": deleted_count,
            },
        )

    async def _get_token(self) -> str | None:
        """Obtain an OAuth2 access token from the Microsoft identity platform."""
        url = _TOKEN_ENDPOINT.format(tenant_id=self._tenant_id)
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": _GRAPH_SCOPE,
            "grant_type": "client_credentials",
        }
        try:
            async with httpx.AsyncClient(timeout=_TOKEN_TIMEOUT) as client:
                response = await client.post(
                    url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            if response.status_code == 200:
                token: str | None = response.json().get("access_token")
                return token
            logger.warning(
                "entra_id_token_error",
                status_code=response.status_code,
            )
            return None
        except Exception as exc:
            logger.warning("entra_id_token_exception", error=str(exc))
            return None

    @staticmethod
    def _get_user_id(action: AgentAction) -> str | None:
        payload: dict[str, Any] = action.payload or {}
        return payload.get("user_id") or None

    @staticmethod
    def _graph_error_result(
        action: AgentAction,
        response: httpx.Response,
        user_id: str,
        operation: str,
    ) -> ExecutionResult:
        logger.warning(
            "entra_id_graph_api_error",
            action_id=str(action.uuid),
            user_id=user_id,
            operation=operation,
            status_code=response.status_code,
        )
        return ExecutionResult.fail(
            f"Graph API returned HTTP {response.status_code} for {operation}",
            {
                "action_id": str(action.uuid),
                "user_id": user_id,
                "status_code": response.status_code,
            },
        )

    def supported_actions(self) -> list[str]:
        return ["disable_user", "revoke_sessions", "force_mfa"]


def _odata_type_to_segment(odata_type: str) -> str | None:
    """
    Map a Graph @odata.type to the authentication method resource segment.

    Example: "#microsoft.graph.microsoftAuthenticatorAuthenticationMethod"
             → "microsoftAuthenticatorMethods"
    """
    _MAP = {
        "microsoftAuthenticatorAuthenticationMethod": "microsoftAuthenticatorMethods",
        "phoneAuthenticationMethod": "phoneMethods",
        "fido2AuthenticationMethod": "fido2Methods",
        "windowsHelloForBusinessAuthenticationMethod": "windowsHelloForBusinessMethods",
        "softwareOathAuthenticationMethod": "softwareOathMethods",
        "temporaryAccessPassAuthenticationMethod": "temporaryAccessPassMethods",
        "emailAuthenticationMethod": "emailMethods",
    }
    # Strip the "#microsoft.graph." prefix if present
    short = odata_type.split(".")[-1] if "." in odata_type else odata_type
    return _MAP.get(short)
