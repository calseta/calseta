"""
Mock Okta enrichment provider.

Returns deterministic canned responses with the same `extracted` field structure
as the real OktaProvider. No HTTP calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.integrations.enrichment.base import EnrichmentProviderBase
from app.integrations.enrichment.mocks.variant_selector import select_variant
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

# ---------------------------------------------------------------------------
# Account variants (4): active+MFA / active-noMFA / suspended / not-found
# ---------------------------------------------------------------------------
_ACCOUNT_VARIANTS: list[dict[str, Any]] = [
    # 0 — not found
    {"found": False},
    # 1 — active user with MFA
    {
        "found": True,
        "user_id": "00u1a2b3c4d5e6f7g8h9",
        "login": "j.martinez@contoso.com",
        "email": "j.martinez@contoso.com",
        "first_name": "Julia",
        "last_name": "Martinez",
        "status": "ACTIVE",
        "created": "2024-03-15T10:30:00.000Z",
        "last_login": "2026-03-01T08:22:00.000Z",
        "password_changed": "2026-01-10T14:00:00.000Z",
        "groups": ["Everyone", "SOC-Analysts", "VPN-Users"],
        "mfa_enrolled": True,
    },
    # 2 — active user without MFA
    {
        "found": True,
        "user_id": "00u9h8g7f6e5d4c3b2a1",
        "login": "svc_backup@contoso.com",
        "email": "svc_backup@contoso.com",
        "first_name": "Service",
        "last_name": "Backup",
        "status": "ACTIVE",
        "created": "2023-08-22T09:00:00.000Z",
        "last_login": "2026-02-28T23:45:00.000Z",
        "password_changed": "2025-06-01T12:00:00.000Z",
        "groups": ["Everyone", "Service-Accounts"],
        "mfa_enrolled": False,
    },
    # 3 — suspended user
    {
        "found": True,
        "user_id": "00u5e4d3c2b1a0z9y8x7",
        "login": "r.chen@contoso.com",
        "email": "r.chen@contoso.com",
        "first_name": "Robert",
        "last_name": "Chen",
        "status": "SUSPENDED",
        "created": "2022-11-01T08:00:00.000Z",
        "last_login": "2026-03-01T09:47:00.000Z",
        "password_changed": "2025-12-15T10:00:00.000Z",
        "groups": ["Everyone", "Global-Admins", "Azure-AD-Admins"],
        "mfa_enrolled": True,
    },
]


def _raw_for(extracted: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal raw dict mimicking the Okta Users API response."""
    if not extracted.get("found"):
        return {"status_code": 404}
    return {
        "id": extracted.get("user_id", ""),
        "status": extracted.get("status"),
        "created": extracted.get("created"),
        "lastLogin": extracted.get("last_login"),
        "passwordChanged": extracted.get("password_changed"),
        "profile": {
            "login": extracted.get("login"),
            "email": extracted.get("email"),
            "firstName": extracted.get("first_name"),
            "lastName": extracted.get("last_name"),
        },
        "credentials": {"provider": {"type": "OKTA"}} if extracted.get("mfa_enrolled") else {},
    }


class MockOktaProvider(EnrichmentProviderBase):
    """Mock Okta provider — deterministic canned responses, no HTTP."""

    provider_name = "okta"
    display_name = "Okta"
    supported_types = [IndicatorType.ACCOUNT]
    cache_ttl_seconds = 900

    def is_configured(self) -> bool:
        return True

    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        if indicator_type != IndicatorType.ACCOUNT:
            return EnrichmentResult.skipped_result(
                self.provider_name,
                f"Okta only supports account indicators; got '{indicator_type}'",
            )

        idx = select_variant(value, len(_ACCOUNT_VARIANTS))
        extracted = dict(_ACCOUNT_VARIANTS[idx])
        raw = _raw_for(extracted)

        return EnrichmentResult.success_result(
            provider_name=self.provider_name,
            extracted=extracted,
            raw=raw,
            enriched_at=datetime.now(UTC),
        )
