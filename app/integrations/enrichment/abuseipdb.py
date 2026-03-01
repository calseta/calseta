"""
AbuseIPDB enrichment provider.

API: AbuseIPDB v2 (https://docs.abuseipdb.com/)
Auth: Key header
Supports: IP only

Field mapping reference: docs/integrations/abuseipdb/api_notes.md
"""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import structlog

from app.config import settings
from app.integrations.enrichment.base import EnrichmentProviderBase
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

logger = structlog.get_logger(__name__)

_CHECK_URL = "https://api.abuseipdb.com/api/v2/check"
_REQUEST_TIMEOUT = 30.0
_MAX_AGE_DAYS = 90


def _abuse_score_to_malice(score: int) -> str:
    """Map AbuseIPDB confidence score (0–100) to Calseta malice verdict."""
    if score >= 75:
        return "Malicious"
    if score >= 25:
        return "Suspicious"
    return "Benign"


class AbuseIPDBProvider(EnrichmentProviderBase):
    """Enrichment provider for AbuseIPDB v2 API."""

    provider_name = "abuseipdb"
    display_name = "AbuseIPDB"
    supported_types = [IndicatorType.IP]
    cache_ttl_seconds = 3600

    def is_configured(self) -> bool:
        return bool(settings.ABUSEIPDB_API_KEY)

    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        """
        Query AbuseIPDB for the given IP address.

        Must never raise — all exceptions returned as failure_result.
        """
        try:
            if not self.is_configured():
                return EnrichmentResult.skipped_result(
                    self.provider_name, "AbuseIPDB API key not configured"
                )
            if indicator_type != IndicatorType.IP:
                return EnrichmentResult.skipped_result(
                    self.provider_name,
                    f"AbuseIPDB only supports IP indicators; got '{indicator_type}'",
                )

            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await client.get(
                    _CHECK_URL,
                    headers={
                        "Key": settings.ABUSEIPDB_API_KEY,
                        "Accept": "application/json",
                    },
                    params={"ipAddress": value, "maxAgeInDays": _MAX_AGE_DAYS},
                )

            if response.status_code == 429:
                return EnrichmentResult.failure_result(
                    self.provider_name, "AbuseIPDB rate limit exceeded"
                )
            if response.status_code != 200:
                return EnrichmentResult.failure_result(
                    self.provider_name, f"AbuseIPDB returned HTTP {response.status_code}"
                )

            body = response.json()
            data = body.get("data", {})
            score = data.get("abuseConfidenceScore", 0)

            extracted = {
                "abuse_confidence_score": score,
                "total_reports": data.get("totalReports", 0),
                "country_code": data.get("countryCode"),
                "isp": data.get("isp"),
                "usage_type": data.get("usageType"),
                "is_whitelisted": data.get("isWhitelisted", False),
                "is_tor": data.get("isTor", False),
                "is_public": data.get("isPublic", True),
                "num_distinct_users": data.get("numDistinctUsers", 0),
                "last_reported_at": data.get("lastReportedAt"),
                "malice": _abuse_score_to_malice(score),
            }

            return EnrichmentResult.success_result(
                provider_name=self.provider_name,
                extracted=extracted,
                raw=body,
                enriched_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception("abuseipdb_enrich_error", value=value[:64])
            return EnrichmentResult.failure_result(self.provider_name, str(exc))
