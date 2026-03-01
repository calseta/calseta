"""
Microsoft Entra (Azure AD) enrichment provider.

API: Microsoft Graph v1.0 (https://learn.microsoft.com/en-us/graph/api/)
Auth: OAuth2 client credentials; token cached until expiry
Supports: account only

A user not found in Entra returns success=True with found=False.
Token acquisition failure returns success=False.

Field mapping reference: docs/integrations/entra/api_notes.md
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from urllib.parse import quote

import httpx
import structlog

from app.config import settings
from app.integrations.enrichment.base import EnrichmentProviderBase
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

logger = structlog.get_logger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_REQUEST_TIMEOUT = 30.0
_TOKEN_BUFFER_SECONDS = 60  # Refresh token 60s before expiry


class EntraProvider(EnrichmentProviderBase):
    """Enrichment provider for Microsoft Entra ID (Graph API)."""

    provider_name = "entra"
    display_name = "Microsoft Entra ID"
    supported_types = [IndicatorType.ACCOUNT]
    cache_ttl_seconds = 900

    def __init__(self) -> None:
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0

    def is_configured(self) -> bool:
        return bool(
            settings.ENTRA_TENANT_ID
            and settings.ENTRA_CLIENT_ID
            and settings.ENTRA_CLIENT_SECRET
        )

    def _token_is_valid(self) -> bool:
        return (
            self._access_token is not None
            and time.monotonic() < self._token_expires_at
        )

    async def _get_access_token(self) -> str:
        """Acquire or return cached access token. Raises on failure."""
        if self._token_is_valid():
            assert self._access_token is not None
            return self._access_token

        token_url = (
            f"https://login.microsoftonline.com/{settings.ENTRA_TENANT_ID}"
            "/oauth2/v2.0/token"
        )
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(
                token_url,
                data={
                    "client_id": settings.ENTRA_CLIENT_ID,
                    "client_secret": settings.ENTRA_CLIENT_SECRET,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Entra token acquisition failed: HTTP {response.status_code}"
            )

        body = response.json()
        self._access_token = body["access_token"]
        expires_in = int(body.get("expires_in", 3600))
        self._token_expires_at = time.monotonic() + expires_in - _TOKEN_BUFFER_SECONDS
        return self._access_token

    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        """
        Look up an account in Microsoft Entra ID.

        Must never raise — all exceptions returned as failure_result.
        """
        try:
            if not self.is_configured():
                return EnrichmentResult.skipped_result(
                    self.provider_name,
                    "Entra tenant ID, client ID, or client secret not configured",
                )
            if indicator_type != IndicatorType.ACCOUNT:
                return EnrichmentResult.skipped_result(
                    self.provider_name,
                    f"Entra only supports account indicators; got '{indicator_type}'",
                )

            token = await self._get_access_token()
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            _fields = (
                "id,displayName,userPrincipalName,mail,accountEnabled,"
                "department,jobTitle,lastPasswordChangeDateTime"
            )
            encoded = quote(value, safe="")
            user_url = f"{_GRAPH_BASE}/users/{encoded}?$select={_fields}"

            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                user_response = await client.get(user_url, headers=headers)

                if user_response.status_code == 404:
                    return EnrichmentResult.success_result(
                        provider_name=self.provider_name,
                        extracted={"found": False},
                        raw={"status_code": 404},
                        enriched_at=datetime.now(UTC),
                    )

                if user_response.status_code != 200:
                    return EnrichmentResult.failure_result(
                        self.provider_name,
                        f"Entra user lookup returned HTTP {user_response.status_code}",
                    )

                user = user_response.json()
                user_id = user.get("id", "")

                # Fetch group membership
                groups: list[str] = []
                if user_id:
                    groups_url = f"{_GRAPH_BASE}/users/{user_id}/memberOf?$select=displayName"
                    groups_response = await client.get(groups_url, headers=headers)
                    if groups_response.status_code == 200:
                        groups = [
                            g.get("displayName", "")
                            for g in groups_response.json().get("value", [])
                            if g.get("displayName")
                        ]

            extracted = {
                "found": True,
                "object_id": user_id,
                "user_principal_name": user.get("userPrincipalName"),
                "display_name": user.get("displayName"),
                "mail": user.get("mail"),
                "account_enabled": user.get("accountEnabled"),
                "department": user.get("department"),
                "job_title": user.get("jobTitle"),
                "last_password_change": user.get("lastPasswordChangeDateTime"),
                "groups": groups,
            }

            return EnrichmentResult.success_result(
                provider_name=self.provider_name,
                extracted=extracted,
                raw=user,
                enriched_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception("entra_enrich_error", value=value[:64])
            return EnrichmentResult.failure_result(self.provider_name, str(exc))
