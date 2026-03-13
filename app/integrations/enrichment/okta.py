"""
Okta enrichment provider.

API: Okta Management API v1 (https://developer.okta.com/docs/api/)
Auth: SSWS API token (Authorization: SSWS {token})
Supports: account only

Okta resolves by login (email) or Okta user ID.
A user not found in Okta returns success=True with found=False.

Field mapping reference: docs/integrations/okta/api_notes.md
"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import quote

import httpx
import structlog

from app.config import settings
from app.integrations.enrichment.base import EnrichmentProviderBase
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

logger = structlog.get_logger(__name__)

_REQUEST_TIMEOUT = 30.0


class OktaProvider(EnrichmentProviderBase):
    """Enrichment provider for the Okta Management API."""

    provider_name = "okta"
    display_name = "Okta"
    supported_types = [IndicatorType.ACCOUNT]
    cache_ttl_seconds = 900

    def is_configured(self) -> bool:
        return bool(settings.OKTA_DOMAIN and settings.OKTA_API_TOKEN)

    def _base_url(self) -> str:
        domain = settings.OKTA_DOMAIN.rstrip("/")
        return f"https://{domain}/api/v1"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"SSWS {settings.OKTA_API_TOKEN}",
            "Accept": "application/json",
        }

    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        """
        Look up an account in Okta by login (email) or user ID.

        Must never raise — all exceptions returned as failure_result.
        """
        try:
            if not self.is_configured():
                return EnrichmentResult.skipped_result(
                    self.provider_name, "Okta domain or API token not configured"
                )
            if indicator_type != IndicatorType.ACCOUNT:
                return EnrichmentResult.skipped_result(
                    self.provider_name,
                    f"Okta only supports account indicators; got '{indicator_type}'",
                )

            base = self._base_url()
            headers = self._headers()
            encoded_value = quote(value, safe="")

            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                user_response = await client.get(
                    f"{base}/users/{encoded_value}", headers=headers
                )

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
                        f"Okta returned HTTP {user_response.status_code}",
                    )

                user = user_response.json()
                user_id = user.get("id", "")
                profile = user.get("profile", {})

                # Fetch groups for this user
                groups: list[str] = []
                if user_id:
                    groups_response = await client.get(
                        f"{base}/users/{user_id}/groups", headers=headers
                    )
                    if groups_response.status_code == 200:
                        groups = [
                            g.get("profile", {}).get("name", "")
                            for g in groups_response.json()
                            if g.get("profile", {}).get("name")
                        ]

            extracted = {
                "found": True,
                "user_id": user_id,
                "login": profile.get("login"),
                "email": profile.get("email"),
                "first_name": profile.get("firstName"),
                "last_name": profile.get("lastName"),
                "status": user.get("status"),
                "created": user.get("created"),
                "last_login": user.get("lastLogin"),
                "password_changed": user.get("passwordChanged"),
                "groups": groups,
                "mfa_enrolled": bool(user.get("credentials", {}).get("provider")),
            }

            return EnrichmentResult.success_result(
                provider_name=self.provider_name,
                extracted=extracted,
                raw=user,
                enriched_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception("okta_enrich_error", value=value[:64])
            return EnrichmentResult.failure_result(self.provider_name, str(exc))
