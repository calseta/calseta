"""
Mock VirusTotal enrichment provider.

Returns deterministic canned responses with the same `extracted` field structure
as the real VirusTotalProvider. No HTTP calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.integrations.enrichment.base import EnrichmentProviderBase
from app.integrations.enrichment.mocks.variant_selector import select_variant
from app.schemas.enrichment import EnrichmentResult
from app.schemas.indicators import IndicatorType

# ---------------------------------------------------------------------------
# IP variants (5)
# ---------------------------------------------------------------------------
_IP_VARIANTS: list[dict[str, Any]] = [
    # 0 — not found (~20%)
    {"found": False, "malice": "Pending"},
    # 1 — clean IP
    {
        "malicious_count": 0,
        "suspicious_count": 0,
        "total_engines": 91,
        "reputation": 5,
        "categories": {},
        "tags": [],
        "malice": "Benign",
        "last_analysis_date": "2026-02-28T12:00:00+00:00",
        "country": "US",
        "as_owner": "Cloudflare, Inc.",
        "asn": 13335,
        "network": "104.16.0.0/12",
    },
    # 2 — suspicious IP
    {
        "malicious_count": 2,
        "suspicious_count": 5,
        "total_engines": 91,
        "reputation": -12,
        "categories": {"Webroot": "Proxy/Anonymizer"},
        "tags": ["proxy"],
        "malice": "Suspicious",
        "last_analysis_date": "2026-02-27T08:30:00+00:00",
        "country": "RU",
        "as_owner": "PJSC Rostelecom",
        "asn": 12389,
        "network": "91.234.0.0/16",
    },
    # 3 — malicious IP
    {
        "malicious_count": 14,
        "suspicious_count": 3,
        "total_engines": 91,
        "reputation": -47,
        "categories": {"Forcepoint ThreatSeeker": "Malicious Sources/Malnets"},
        "tags": ["c2", "tor-exit-node"],
        "malice": "Malicious",
        "last_analysis_date": "2026-03-01T06:15:00+00:00",
        "country": "DE",
        "as_owner": "Hetzner Online GmbH",
        "asn": 24940,
        "network": "185.220.101.0/24",
    },
    # 4 — benign (high rep)
    {
        "malicious_count": 0,
        "suspicious_count": 0,
        "total_engines": 91,
        "reputation": 42,
        "categories": {"BitDefender": "Business"},
        "tags": [],
        "malice": "Benign",
        "last_analysis_date": "2026-02-26T18:00:00+00:00",
        "country": "US",
        "as_owner": "Microsoft Corporation",
        "asn": 8075,
        "network": "20.0.0.0/11",
    },
]

# ---------------------------------------------------------------------------
# Domain variants (5)
# ---------------------------------------------------------------------------
_DOMAIN_VARIANTS: list[dict[str, Any]] = [
    # 0 — not found
    {"found": False, "malice": "Pending"},
    # 1 — clean domain
    {
        "malicious_count": 0,
        "suspicious_count": 0,
        "total_engines": 91,
        "reputation": 10,
        "categories": {"BitDefender": "Business"},
        "tags": [],
        "malice": "Benign",
        "last_analysis_date": "2026-02-28T10:00:00+00:00",
        "registrar": "MarkMonitor Inc.",
        "creation_date": 874296000,
    },
    # 2 — suspicious domain
    {
        "malicious_count": 1,
        "suspicious_count": 4,
        "total_engines": 91,
        "reputation": -8,
        "categories": {"Sophos": "Suspicious"},
        "tags": ["newly-registered"],
        "malice": "Suspicious",
        "last_analysis_date": "2026-02-27T14:00:00+00:00",
        "registrar": "Namecheap, Inc.",
        "creation_date": 1708992000,
    },
    # 3 — malicious domain (C2)
    {
        "malicious_count": 18,
        "suspicious_count": 5,
        "total_engines": 91,
        "reputation": -65,
        "categories": {"Forcepoint ThreatSeeker": "Malicious Sources/Malnets"},
        "tags": ["c2", "phishing"],
        "malice": "Malicious",
        "last_analysis_date": "2026-03-01T04:00:00+00:00",
        "registrar": "NameSilo, LLC",
        "creation_date": 1709078400,
    },
    # 4 — benign well-known domain
    {
        "malicious_count": 0,
        "suspicious_count": 0,
        "total_engines": 91,
        "reputation": 80,
        "categories": {"BitDefender": "Computers and Technology"},
        "tags": [],
        "malice": "Benign",
        "last_analysis_date": "2026-02-25T22:00:00+00:00",
        "registrar": "MarkMonitor Inc.",
        "creation_date": 1059436800,
    },
]

# ---------------------------------------------------------------------------
# Hash variants (5) — shared across MD5, SHA1, SHA256
# ---------------------------------------------------------------------------
_HASH_VARIANTS: list[dict[str, Any]] = [
    # 0 — not found
    {"found": False, "malice": "Pending"},
    # 1 — clean file
    {
        "malicious_count": 0,
        "suspicious_count": 0,
        "total_engines": 74,
        "reputation": 0,
        "categories": {},
        "tags": ["signed", "trusted"],
        "malice": "Benign",
        "last_analysis_date": "2026-02-28T09:00:00+00:00",
        "meaningful_name": "update.exe",
        "type_description": "Win32 EXE",
        "size": 1048576,
    },
    # 2 — suspicious file
    {
        "malicious_count": 3,
        "suspicious_count": 8,
        "total_engines": 74,
        "reputation": -15,
        "categories": {},
        "tags": ["packed", "upx"],
        "malice": "Suspicious",
        "last_analysis_date": "2026-02-27T16:00:00+00:00",
        "meaningful_name": "svchost_helper.exe",
        "type_description": "Win32 EXE",
        "size": 524288,
    },
    # 3 — malicious file (malware)
    {
        "malicious_count": 48,
        "suspicious_count": 6,
        "total_engines": 74,
        "reputation": -92,
        "categories": {},
        "tags": ["trojan", "ransomware", "packed"],
        "malice": "Malicious",
        "last_analysis_date": "2026-03-01T02:00:00+00:00",
        "meaningful_name": "payload.dll",
        "type_description": "Win32 DLL",
        "size": 262144,
    },
    # 4 — benign known tool
    {
        "malicious_count": 0,
        "suspicious_count": 1,
        "total_engines": 74,
        "reputation": 8,
        "categories": {},
        "tags": ["peexe"],
        "malice": "Benign",
        "last_analysis_date": "2026-02-26T20:00:00+00:00",
        "meaningful_name": "powershell.exe",
        "type_description": "Win32 EXE",
        "size": 450048,
    },
]


def _raw_for(extracted: dict[str, Any], indicator_type: IndicatorType) -> dict[str, Any]:
    """Build a minimal raw dict mimicking the VT v3 API response structure."""
    if extracted.get("found") is False:
        return {"status_code": 404}
    return {
        "data": {
            "type": {
                IndicatorType.IP: "ip_address",
                IndicatorType.DOMAIN: "domain",
            }.get(indicator_type, "file"),
            "id": "mock-virustotal-id",
            "attributes": {
                "last_analysis_stats": {
                    "malicious": extracted.get("malicious_count", 0),
                    "suspicious": extracted.get("suspicious_count", 0),
                    "undetected": extracted.get("total_engines", 0)
                    - extracted.get("malicious_count", 0)
                    - extracted.get("suspicious_count", 0),
                    "harmless": 0,
                    "timeout": 0,
                },
                "reputation": extracted.get("reputation", 0),
                "tags": extracted.get("tags", []),
            },
        }
    }


class MockVirusTotalProvider(EnrichmentProviderBase):
    """Mock VirusTotal provider — deterministic canned responses, no HTTP."""

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

    def is_configured(self) -> bool:
        return True

    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        if indicator_type not in self.supported_types:
            return EnrichmentResult.skipped_result(
                self.provider_name,
                f"VirusTotal does not support indicator type '{indicator_type}'",
            )

        if indicator_type == IndicatorType.IP:
            variants = _IP_VARIANTS
        elif indicator_type == IndicatorType.DOMAIN:
            variants = _DOMAIN_VARIANTS
        else:
            variants = _HASH_VARIANTS

        idx = select_variant(value, len(variants))
        extracted = dict(variants[idx])  # shallow copy
        raw = _raw_for(extracted, indicator_type)

        return EnrichmentResult.success_result(
            provider_name=self.provider_name,
            extracted=extracted,
            raw=raw,
            enriched_at=datetime.now(UTC),
        )
