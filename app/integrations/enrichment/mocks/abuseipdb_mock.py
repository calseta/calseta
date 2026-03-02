"""
Mock AbuseIPDB enrichment provider.

Returns deterministic canned responses with the same `extracted` field structure
as the real AbuseIPDBProvider. No HTTP calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.integrations.enrichment.base import EnrichmentProviderBase
from app.integrations.enrichment.mocks.variant_selector import select_variant
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

# ---------------------------------------------------------------------------
# IP variants (4): clean / low / suspicious / malicious
# ---------------------------------------------------------------------------
_IP_VARIANTS: list[dict[str, Any]] = [
    # 0 — clean IP
    {
        "abuse_confidence_score": 0,
        "total_reports": 0,
        "country_code": "US",
        "isp": "Cloudflare, Inc.",
        "usage_type": "Content Delivery Network",
        "is_whitelisted": True,
        "is_tor": False,
        "is_public": True,
        "num_distinct_users": 0,
        "last_reported_at": None,
        "malice": "Benign",
    },
    # 1 — low activity
    {
        "abuse_confidence_score": 12,
        "total_reports": 3,
        "country_code": "DE",
        "isp": "Hetzner Online GmbH",
        "usage_type": "Data Center/Web Hosting/Transit",
        "is_whitelisted": False,
        "is_tor": False,
        "is_public": True,
        "num_distinct_users": 2,
        "last_reported_at": "2026-02-28T14:30:00+00:00",
        "malice": "Benign",
    },
    # 2 — suspicious
    {
        "abuse_confidence_score": 45,
        "total_reports": 28,
        "country_code": "RU",
        "isp": "PJSC Rostelecom",
        "usage_type": "Fixed Line ISP",
        "is_whitelisted": False,
        "is_tor": False,
        "is_public": True,
        "num_distinct_users": 12,
        "last_reported_at": "2026-03-01T08:15:00+00:00",
        "malice": "Suspicious",
    },
    # 3 — malicious (TOR exit)
    {
        "abuse_confidence_score": 100,
        "total_reports": 347,
        "country_code": "NL",
        "isp": "LeaseWeb Netherlands B.V.",
        "usage_type": "Data Center/Web Hosting/Transit",
        "is_whitelisted": False,
        "is_tor": True,
        "is_public": True,
        "num_distinct_users": 89,
        "last_reported_at": "2026-03-01T11:00:00+00:00",
        "malice": "Malicious",
    },
]


def _raw_for(extracted: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal raw dict mimicking the AbuseIPDB v2 response structure."""
    return {
        "data": {
            "ipAddress": "mock-ip",
            "isPublic": extracted.get("is_public", True),
            "abuseConfidenceScore": extracted.get("abuse_confidence_score", 0),
            "countryCode": extracted.get("country_code"),
            "isp": extracted.get("isp"),
            "usageType": extracted.get("usage_type"),
            "totalReports": extracted.get("total_reports", 0),
            "numDistinctUsers": extracted.get("num_distinct_users", 0),
            "lastReportedAt": extracted.get("last_reported_at"),
            "isWhitelisted": extracted.get("is_whitelisted", False),
            "isTor": extracted.get("is_tor", False),
        }
    }


class MockAbuseIPDBProvider(EnrichmentProviderBase):
    """Mock AbuseIPDB provider — deterministic canned responses, no HTTP."""

    provider_name = "abuseipdb"
    display_name = "AbuseIPDB"
    supported_types = [IndicatorType.IP]
    cache_ttl_seconds = 3600

    def is_configured(self) -> bool:
        return True

    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        if indicator_type != IndicatorType.IP:
            return EnrichmentResult.skipped_result(
                self.provider_name,
                f"AbuseIPDB only supports IP indicators; got '{indicator_type}'",
            )

        idx = select_variant(value, len(_IP_VARIANTS))
        extracted = dict(_IP_VARIANTS[idx])
        raw = _raw_for(extracted)

        return EnrichmentResult.success_result(
            provider_name=self.provider_name,
            extracted=extracted,
            raw=raw,
            enriched_at=datetime.now(UTC),
        )
