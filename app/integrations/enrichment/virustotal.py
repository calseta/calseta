"""
VirusTotal enrichment provider.

API: VirusTotal v3 (https://docs.virustotal.com/reference/overview)
Auth: x-apikey header (64-char hex key)
Supports: IP, domain, MD5, SHA1, SHA256

Field mapping reference: docs/integrations/virustotal/api_notes.md
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.config import settings
from app.integrations.enrichment.base import EnrichmentProviderBase
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

logger = structlog.get_logger(__name__)

_BASE_URL = "https://www.virustotal.com/api/v3"
_REQUEST_TIMEOUT = 30.0

# Per-type cache TTLs matching PRD Section 7.2
_TTL_MAP: dict[IndicatorType, int] = {
    IndicatorType.IP: 3600,
    IndicatorType.DOMAIN: 21600,
    IndicatorType.HASH_MD5: 86400,
    IndicatorType.HASH_SHA1: 86400,
    IndicatorType.HASH_SHA256: 86400,
}


def _endpoint(indicator_type: IndicatorType, value: str) -> str:
    if indicator_type == IndicatorType.IP:
        return f"{_BASE_URL}/ip_addresses/{value}"
    if indicator_type == IndicatorType.DOMAIN:
        return f"{_BASE_URL}/domains/{value}"
    # All hash types use the same files endpoint
    return f"{_BASE_URL}/files/{value}"


def _extract_malice(stats: dict[str, Any]) -> str:
    """Derive Calseta malice verdict from VT last_analysis_stats."""
    if stats.get("malicious", 0) > 0:
        return "Malicious"
    if stats.get("suspicious", 0) > 0:
        return "Suspicious"
    return "Benign"


def _build_extracted(attrs: dict[str, Any], indicator_type: IndicatorType) -> dict[str, Any]:
    """Build the extracted field subset surfaced to agents."""
    stats = attrs.get("last_analysis_stats", {})
    malicious_count = stats.get("malicious", 0)
    suspicious_count = stats.get("suspicious", 0)
    total = sum(stats.values()) if stats else 0

    extracted: dict[str, Any] = {
        "malicious_count": malicious_count,
        "suspicious_count": suspicious_count,
        "total_engines": total,
        "reputation": attrs.get("reputation"),
        "categories": attrs.get("categories", {}),
        "tags": attrs.get("tags", []),
        "malice": _extract_malice(stats),
    }

    # Type-specific fields
    if indicator_type == IndicatorType.IP:
        extracted["country"] = attrs.get("country")
        extracted["as_owner"] = attrs.get("as_owner")
        extracted["asn"] = attrs.get("asn")
        extracted["network"] = attrs.get("network")
    elif indicator_type == IndicatorType.DOMAIN:
        extracted["registrar"] = attrs.get("registrar")
        extracted["creation_date"] = attrs.get("creation_date")
    else:
        # Hash types
        extracted["meaningful_name"] = attrs.get("meaningful_name")
        extracted["type_description"] = attrs.get("type_description")
        extracted["size"] = attrs.get("size")

    last_mod = attrs.get("last_modification_date")
    if last_mod:
        extracted["last_analysis_date"] = datetime.fromtimestamp(last_mod, tz=UTC).isoformat()

    return extracted


class VirusTotalProvider(EnrichmentProviderBase):
    """Enrichment provider for VirusTotal API v3."""

    provider_name = "virustotal"
    display_name = "VirusTotal"
    supported_types = [
        IndicatorType.IP,
        IndicatorType.DOMAIN,
        IndicatorType.HASH_MD5,
        IndicatorType.HASH_SHA1,
        IndicatorType.HASH_SHA256,
    ]
    cache_ttl_seconds = 3600
    _TTL_BY_TYPE = _TTL_MAP

    def is_configured(self) -> bool:
        return bool(settings.VIRUSTOTAL_API_KEY)

    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        """
        Query VirusTotal for the given indicator.

        Must never raise — all exceptions returned as failure_result.
        """
        try:
            if not self.is_configured():
                return EnrichmentResult.skipped_result(
                    self.provider_name, "VirusTotal API key not configured"
                )
            if indicator_type not in self.supported_types:
                return EnrichmentResult.skipped_result(
                    self.provider_name,
                    f"VirusTotal does not support indicator type '{indicator_type}'",
                )

            url = _endpoint(indicator_type, value)
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                response = await client.get(
                    url, headers={"x-apikey": settings.VIRUSTOTAL_API_KEY}
                )

            if response.status_code == 404:
                return EnrichmentResult.success_result(
                    provider_name=self.provider_name,
                    extracted={"found": False, "malice": "Pending"},
                    raw={"status_code": 404},
                    enriched_at=datetime.now(UTC),
                )

            if response.status_code != 200:
                return EnrichmentResult.failure_result(
                    self.provider_name,
                    f"VirusTotal returned HTTP {response.status_code}",
                )

            body = response.json()
            attrs = body.get("data", {}).get("attributes", {})
            extracted = _build_extracted(attrs, indicator_type)

            return EnrichmentResult.success_result(
                provider_name=self.provider_name,
                extracted=extracted,
                raw=body,
                enriched_at=datetime.now(UTC),
            )
        except Exception as exc:
            logger.exception(
                "virustotal_enrich_error",
                indicator_type=str(indicator_type),
                value=value[:64],
            )
            return EnrichmentResult.failure_result(self.provider_name, str(exc))
