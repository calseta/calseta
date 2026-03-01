"""
Workflow execution context — all types injected into the workflow's `run()` function.

Public interface (what workflow authors use):
    WorkflowContext    — the single parameter to `async def run(ctx)`
    WorkflowResult     — return type from `run()`
    WorkflowLogger     — ctx.log.info/warning/error/debug
    SecretsAccessor    — ctx.secrets.get("KEY")
    IntegrationClients — ctx.integrations.okta / .entra
    IndicatorContext   — ctx.indicator
    AlertContext       — ctx.alert (may be None for standalone indicator workflows)
    OktaClient         — ctx.integrations.okta
    EntraClient        — ctx.integrations.entra

Workflow authors must never import from app.* directly.
All platform capabilities are exposed through ctx.*
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

# ---------------------------------------------------------------------------
# WorkflowResult
# ---------------------------------------------------------------------------


@dataclass
class WorkflowResult:
    """Return value from every workflow run() function."""

    success: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "OK", data: dict[str, Any] | None = None) -> WorkflowResult:
        return cls(success=True, message=message, data=data or {})

    @classmethod
    def fail(cls, message: str, data: dict[str, Any] | None = None) -> WorkflowResult:
        return cls(success=False, message=message, data=data or {})


# ---------------------------------------------------------------------------
# WorkflowLogger
# ---------------------------------------------------------------------------


@dataclass
class WorkflowLogger:
    """
    Structured in-memory logger for workflow execution.

    All calls append to an internal buffer; the full log is captured in
    WorkflowExecutionResult.log_output after the run completes.
    """

    _entries: list[dict[str, Any]] = field(default_factory=list)

    def _append(self, level: str, message: str, **kwargs: Any) -> None:
        entry: dict[str, Any] = {
            "level": level,
            "message": message,
            "ts": datetime.now(UTC).isoformat(),
        }
        if kwargs:
            entry["extra"] = kwargs
        self._entries.append(entry)

    def info(self, message: str, **kwargs: Any) -> None:
        self._append("info", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._append("warning", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._append("error", message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._append("debug", message, **kwargs)

    def render(self) -> str:
        """Render all log entries as newline-separated JSON."""
        return "\n".join(json.dumps(e) for e in self._entries)


# ---------------------------------------------------------------------------
# SecretsAccessor
# ---------------------------------------------------------------------------


class SecretsAccessor:
    """
    Provides named secret access to workflow code.

    Reads environment variables by name. Never exposes all secrets at once.
    Returns None if the variable is not set, so workflows can handle absence gracefully.
    """

    def get(self, key: str) -> str | None:
        return os.environ.get(key)


# ---------------------------------------------------------------------------
# Integration clients — OktaClient
# ---------------------------------------------------------------------------


class OktaClient:
    """
    Workflow integration client for the Okta Management API.

    Used by pre-built and custom workflows via ctx.integrations.okta.
    Not the same as OktaProvider (enrichment) — this client exposes
    lifecycle management operations for incident response automation.

    Auth: SSWS API token (Authorization: SSWS {token})

    The client manages its own httpx session. Workflow code calls methods
    directly without needing to pass an http client:
        await ctx.integrations.okta.revoke_sessions(ctx.indicator.value)
    """

    def __init__(self, domain: str, api_token: str) -> None:
        import httpx

        self._domain = domain.rstrip("/")
        self._api_token = api_token
        self._http = httpx.AsyncClient(timeout=30.0)

    def _base_url(self) -> str:
        return f"https://{self._domain}/api/v1"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"SSWS {self._api_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _get_user_id(self, login: str) -> str:
        """Resolve a login/email to an Okta user ID."""
        from urllib.parse import quote

        url = f"{self._base_url()}/users/{quote(login, safe='')}"
        resp = await self._http.get(url, headers=self._headers())
        resp.raise_for_status()
        return str(resp.json()["id"])

    async def revoke_sessions(self, login: str) -> None:
        """Revoke all active sessions for a user (DELETE /users/{id}/sessions)."""
        user_id = await self._get_user_id(login)
        url = f"{self._base_url()}/users/{user_id}/sessions"
        resp = await self._http.delete(url, headers=self._headers())
        resp.raise_for_status()

    async def suspend_user(self, login: str) -> None:
        """Suspend a user account (POST /users/{id}/lifecycle/suspend)."""
        user_id = await self._get_user_id(login)
        url = f"{self._base_url()}/users/{user_id}/lifecycle/suspend"
        resp = await self._http.post(url, headers=self._headers())
        resp.raise_for_status()

    async def unsuspend_user(self, login: str) -> None:
        """Unsuspend a user account (POST /users/{id}/lifecycle/unsuspend)."""
        user_id = await self._get_user_id(login)
        url = f"{self._base_url()}/users/{user_id}/lifecycle/unsuspend"
        resp = await self._http.post(url, headers=self._headers())
        resp.raise_for_status()

    async def reset_password(self, login: str) -> str | None:
        """
        Trigger a password reset email (POST /users/{id}/lifecycle/reset_password).

        Returns the one-time reset URL if sendEmail=false, or None if email was sent.
        Pre-built workflows use sendEmail=true for simplicity.
        """
        user_id = await self._get_user_id(login)
        url = f"{self._base_url()}/users/{user_id}/lifecycle/reset_password?sendEmail=true"
        resp = await self._http.post(url, headers=self._headers())
        resp.raise_for_status()
        data = resp.json()
        url_value = data.get("resetPasswordUrl")
        return str(url_value) if url_value is not None else None

    async def expire_password(self, login: str) -> None:
        """Force password expiry at next login (POST /users/{id}/lifecycle/expire_password)."""
        user_id = await self._get_user_id(login)
        url = f"{self._base_url()}/users/{user_id}/lifecycle/expire_password"
        resp = await self._http.post(url, headers=self._headers())
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# Integration clients — EntraClient
# ---------------------------------------------------------------------------


class EntraClient:
    """
    Workflow integration client for Microsoft Entra (Graph API).

    Used by pre-built and custom workflows via ctx.integrations.entra.
    Not the same as EntraProvider (enrichment) — this client exposes
    lifecycle management operations for incident response automation.

    Auth: OAuth2 client credentials flow (tenant, client_id, client_secret)
    Base: https://graph.microsoft.com/v1.0

    The client manages its own httpx session. Workflow code calls methods
    directly without needing to pass an http client:
        await ctx.integrations.entra.revoke_sessions(ctx.indicator.value)
    """

    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"

    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        import httpx

        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None
        self._http = httpx.AsyncClient(timeout=30.0)

    async def _get_token(self) -> str:
        if self._access_token:
            return self._access_token
        token_url = self.TOKEN_URL_TEMPLATE.format(tenant_id=self._tenant_id)
        resp = await self._http.post(
            token_url,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
        )
        resp.raise_for_status()
        self._access_token = str(resp.json()["access_token"])
        return self._access_token

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def revoke_sessions(self, user_id: str) -> None:
        """
        Revoke all sign-in sessions (POST /users/{id}/revokeSignInSessions).

        Note: propagation delay of 1–3 minutes. Does not affect guest users.
        """
        headers = await self._auth_headers()
        url = f"{self.GRAPH_BASE}/users/{user_id}/revokeSignInSessions"
        resp = await self._http.post(url, headers=headers)
        resp.raise_for_status()

    async def disable_account(self, user_id: str) -> None:
        """
        Disable an Entra user account by setting accountEnabled=false
        (PATCH /users/{id}).

        Note: Existing sessions/tokens remain valid until they expire or are revoked.
        Combine with revoke_sessions for complete lockout.
        """
        headers = await self._auth_headers()
        url = f"{self.GRAPH_BASE}/users/{user_id}"
        resp = await self._http.patch(
            url,
            headers=headers,
            json={"accountEnabled": False},
        )
        resp.raise_for_status()

    async def enable_account(self, user_id: str) -> None:
        """Re-enable an Entra user account (PATCH /users/{id} accountEnabled=true)."""
        headers = await self._auth_headers()
        url = f"{self.GRAPH_BASE}/users/{user_id}"
        resp = await self._http.patch(
            url,
            headers=headers,
            json={"accountEnabled": True},
        )
        resp.raise_for_status()

    async def reset_mfa(self, user_id: str) -> None:
        """
        Require MFA re-registration by deleting all registered auth methods.

        Lists all authentication methods for the user and deletes each one.
        On next sign-in, the user must register a new MFA method.
        """
        headers = await self._auth_headers()
        list_url = f"{self.GRAPH_BASE}/users/{user_id}/authentication/methods"
        resp = await self._http.get(list_url, headers=headers)
        resp.raise_for_status()
        methods = resp.json().get("value", [])
        for method in methods:
            method_id = method.get("id")
            odata_type = method.get("@odata.type", "")
            # Cannot delete the password method
            if "password" in odata_type.lower() or not method_id:
                continue
            delete_url = (
                f"{self.GRAPH_BASE}/users/{user_id}/authentication/methods/{method_id}"
            )
            await self._http.delete(delete_url, headers=headers)


# ---------------------------------------------------------------------------
# IntegrationClients
# ---------------------------------------------------------------------------


@dataclass
class IntegrationClients:
    """Container for workflow-available integration clients."""

    okta: OktaClient | None = None
    entra: EntraClient | None = None


# ---------------------------------------------------------------------------
# IndicatorContext / AlertContext
# ---------------------------------------------------------------------------


@dataclass
class IndicatorContext:
    """Read-only indicator data available inside a workflow."""

    uuid: UUID
    type: str
    value: str
    malice: str
    is_enriched: bool
    enrichment_results: dict[str, Any] | None
    first_seen: datetime
    last_seen: datetime
    created_at: datetime
    updated_at: datetime


@dataclass
class AlertContext:
    """Read-only alert data available inside a workflow (may be None)."""

    uuid: UUID
    title: str
    severity: str
    severity_id: int
    source_name: str
    status: str
    occurred_at: datetime
    tags: list[str]
    raw_payload: dict[str, Any]


# ---------------------------------------------------------------------------
# TriggerContext
# ---------------------------------------------------------------------------


@dataclass
class TriggerContext:
    """
    Describes what triggered this workflow execution.

    Used by workflow_executor.py to build WorkflowContext before calling run_workflow_code().
    """

    indicator_type: str
    indicator_value: str
    trigger_source: str  # "agent" | "human" | "system"
    alert_id: int | None = None


# ---------------------------------------------------------------------------
# WorkflowContext — the single parameter to async def run(ctx)
# ---------------------------------------------------------------------------


@dataclass
class WorkflowContext:
    """Full execution context injected into each workflow's run() function."""

    indicator: IndicatorContext
    alert: AlertContext | None
    http: Any  # httpx.AsyncClient
    log: WorkflowLogger
    secrets: SecretsAccessor
    integrations: IntegrationClients
