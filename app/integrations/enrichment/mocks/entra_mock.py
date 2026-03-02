"""
Mock Microsoft Entra enrichment provider.

Returns deterministic canned responses with the same `extracted` field structure
as the real EntraProvider. No HTTP calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.integrations.enrichment.base import EnrichmentProviderBase
from app.integrations.enrichment.mocks.variant_selector import select_variant
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

# ---------------------------------------------------------------------------
# Account variants (4): enabled / admin / disabled / not-found
# ---------------------------------------------------------------------------
_ACCOUNT_VARIANTS: list[dict[str, Any]] = [
    # 0 — not found
    {"found": False},
    # 1 — enabled standard user
    {
        "found": True,
        "object_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "user_principal_name": "j.martinez@contoso.com",
        "display_name": "Julia Martinez",
        "mail": "j.martinez@contoso.com",
        "account_enabled": True,
        "department": "Security Operations",
        "job_title": "SOC Analyst",
        "last_password_change": "2026-01-10T14:00:00Z",
        "groups": ["SOC-Analysts", "VPN-Users", "All-Employees"],
    },
    # 2 — admin user (enabled, high privilege)
    {
        "found": True,
        "object_id": "f9e8d7c6-b5a4-3210-9876-543210fedcba",
        "user_principal_name": "r.chen@contoso.com",
        "display_name": "Robert Chen",
        "mail": "r.chen@contoso.com",
        "account_enabled": True,
        "department": "IT Infrastructure",
        "job_title": "Senior Cloud Architect",
        "last_password_change": "2025-12-15T10:00:00Z",
        "groups": ["Global-Admins", "Azure-AD-Admins", "IT-Infrastructure", "All-Employees"],
    },
    # 3 — disabled user
    {
        "found": True,
        "object_id": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
        "user_principal_name": "former.employee@contoso.com",
        "display_name": "Former Employee",
        "mail": "former.employee@contoso.com",
        "account_enabled": False,
        "department": "Former Employees",
        "job_title": None,
        "last_password_change": "2025-06-01T12:00:00Z",
        "groups": ["Disabled-Users"],
    },
]


def _raw_for(extracted: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal raw dict mimicking the Microsoft Graph v1.0 user response."""
    if not extracted.get("found"):
        return {"status_code": 404}
    return {
        "id": extracted.get("object_id", ""),
        "userPrincipalName": extracted.get("user_principal_name"),
        "displayName": extracted.get("display_name"),
        "mail": extracted.get("mail"),
        "accountEnabled": extracted.get("account_enabled"),
        "department": extracted.get("department"),
        "jobTitle": extracted.get("job_title"),
        "lastPasswordChangeDateTime": extracted.get("last_password_change"),
    }


class MockEntraProvider(EnrichmentProviderBase):
    """Mock Microsoft Entra provider — deterministic canned responses, no HTTP."""

    provider_name = "entra"
    display_name = "Microsoft Entra ID"
    supported_types = [IndicatorType.ACCOUNT]
    cache_ttl_seconds = 900

    def is_configured(self) -> bool:
        return True

    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        if indicator_type != IndicatorType.ACCOUNT:
            return EnrichmentResult.skipped_result(
                self.provider_name,
                f"Entra only supports account indicators; got '{indicator_type}'",
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
