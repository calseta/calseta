"""
Comprehensive per-provider unit tests for all enrichment providers.

Covers for each provider (VirusTotal, AbuseIPDB, Okta, Entra):
  1. Happy path — mocked HTTP response, verify EnrichmentResult fields correct
  2. Unconfigured provider — is_configured() returns False, enrichment skipped gracefully
  3. Network error — provider returns success=False, no exception raised
  4. Timeout — provider returns success=False, no exception raised
  5. Response field extraction — extracted fields correctly mapped from raw response

httpx.AsyncClient is patched at call-site so no real HTTP calls are made.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.integrations.enrichment.abuseipdb import AbuseIPDBProvider, _abuse_score_to_malice
from app.integrations.enrichment.base import EnrichmentProviderBase
from app.integrations.enrichment.entra import EntraProvider
from app.integrations.enrichment.okta import OktaProvider
from app.integrations.enrichment.virustotal import (
    VirusTotalProvider,
    _build_extracted,
    _endpoint,
    _extract_malice,
)
from app.schemas.enrichment import EnrichmentStatus
from app.schemas.indicators import IndicatorType

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, body: object) -> MagicMock:
    """Build a minimal fake httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    return resp


def _mock_async_client(*responses: MagicMock) -> MagicMock:
    """
    Return a mock httpx.AsyncClient context manager that yields a client
    whose get/post return responses in sequence.
    """
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    if len(responses) == 1:
        mock_client.get.return_value = responses[0]
        mock_client.post.return_value = responses[0]
    else:
        mock_client.get.side_effect = list(responses)
        mock_client.post.side_effect = list(responses)

    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls


# ===================================================================
# VirusTotal Provider Tests
# ===================================================================


class TestVirusTotalProviderAttributes:
    """Verify VirusTotal provider static attributes and helpers."""

    def test_provider_name(self) -> None:
        p = VirusTotalProvider()
        assert p.provider_name == "virustotal"

    def test_display_name(self) -> None:
        p = VirusTotalProvider()
        assert p.display_name == "VirusTotal"

    def test_supported_types(self) -> None:
        p = VirusTotalProvider()
        assert IndicatorType.IP in p.supported_types
        assert IndicatorType.DOMAIN in p.supported_types
        assert IndicatorType.HASH_MD5 in p.supported_types
        assert IndicatorType.HASH_SHA1 in p.supported_types
        assert IndicatorType.HASH_SHA256 in p.supported_types
        assert IndicatorType.ACCOUNT not in p.supported_types
        assert IndicatorType.EMAIL not in p.supported_types

    def test_endpoint_ip(self) -> None:
        url = _endpoint(IndicatorType.IP, "1.2.3.4")
        assert "/ip_addresses/1.2.3.4" in url

    def test_endpoint_domain(self) -> None:
        url = _endpoint(IndicatorType.DOMAIN, "evil.com")
        assert "/domains/evil.com" in url

    def test_endpoint_hash(self) -> None:
        url = _endpoint(IndicatorType.HASH_SHA256, "abc123")
        assert "/files/abc123" in url

    def test_extract_malice_malicious(self) -> None:
        assert _extract_malice({"malicious": 5, "suspicious": 0}) == "Malicious"

    def test_extract_malice_suspicious(self) -> None:
        assert _extract_malice({"malicious": 0, "suspicious": 3}) == "Suspicious"

    def test_extract_malice_benign(self) -> None:
        assert _extract_malice({"malicious": 0, "suspicious": 0}) == "Benign"

    def test_extract_malice_empty_stats(self) -> None:
        assert _extract_malice({}) == "Benign"

    def test_build_extracted_ip_fields(self) -> None:
        attrs = {
            "last_analysis_stats": {"malicious": 2, "suspicious": 0, "harmless": 50},
            "country": "US",
            "as_owner": "Google",
            "asn": 15169,
            "network": "8.8.8.0/24",
            "reputation": 50,
            "categories": {},
            "tags": ["cdn"],
            "last_modification_date": 1700000000,
        }
        extracted = _build_extracted(attrs, IndicatorType.IP)
        assert extracted["country"] == "US"
        assert extracted["as_owner"] == "Google"
        assert extracted["asn"] == 15169
        assert extracted["network"] == "8.8.8.0/24"
        assert extracted["malice"] == "Malicious"
        assert extracted["malicious_count"] == 2
        assert extracted["total_engines"] == 52
        assert "last_analysis_date" in extracted

    def test_build_extracted_domain_fields(self) -> None:
        attrs = {
            "last_analysis_stats": {"malicious": 0, "suspicious": 0, "harmless": 80},
            "registrar": "NameCheap",
            "creation_date": 946684800,
            "categories": {"Forcepoint ThreatSeeker": "Technology/Internet"},
            "tags": [],
        }
        extracted = _build_extracted(attrs, IndicatorType.DOMAIN)
        assert extracted["registrar"] == "NameCheap"
        assert extracted["creation_date"] == 946684800
        assert "country" not in extracted  # IP-specific
        assert "meaningful_name" not in extracted  # hash-specific

    def test_build_extracted_hash_fields(self) -> None:
        attrs = {
            "last_analysis_stats": {"malicious": 40, "suspicious": 0, "harmless": 0},
            "meaningful_name": "malware.exe",
            "type_description": "PE32 executable",
            "size": 1024,
            "tags": [],
        }
        extracted = _build_extracted(attrs, IndicatorType.HASH_SHA256)
        assert extracted["meaningful_name"] == "malware.exe"
        assert extracted["type_description"] == "PE32 executable"
        assert extracted["size"] == 1024
        assert "country" not in extracted
        assert "registrar" not in extracted

    def test_cache_ttl_by_type(self) -> None:
        p = VirusTotalProvider()
        assert p.get_cache_ttl(IndicatorType.IP) == 3600
        assert p.get_cache_ttl(IndicatorType.DOMAIN) == 21600
        assert p.get_cache_ttl(IndicatorType.HASH_SHA256) == 86400


class TestVirusTotalProviderEnrich:
    """VirusTotal enrich() method tests with mocked HTTP."""

    @pytest.fixture
    def provider(self, monkeypatch: pytest.MonkeyPatch) -> VirusTotalProvider:
        monkeypatch.setattr(
            "app.integrations.enrichment.virustotal.settings.VIRUSTOTAL_API_KEY",
            "test-vt-key-64chars" + "a" * 44,
        )
        return VirusTotalProvider()

    async def test_happy_path_ip_malicious(self, provider: VirusTotalProvider) -> None:
        body = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 10,
                        "suspicious": 2,
                        "harmless": 60,
                        "undetected": 8,
                    },
                    "country": "RU",
                    "as_owner": "Evil ISP",
                    "asn": 12345,
                    "network": "1.2.3.0/24",
                    "reputation": -50,
                    "categories": {},
                    "tags": ["malware"],
                    "last_modification_date": 1700000000,
                }
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is True
        assert result.status == EnrichmentStatus.SUCCESS
        assert result.provider_name == "virustotal"
        assert result.extracted is not None
        assert result.extracted["malice"] == "Malicious"
        assert result.extracted["malicious_count"] == 10
        assert result.extracted["suspicious_count"] == 2
        assert result.extracted["total_engines"] == 80
        assert result.extracted["country"] == "RU"
        assert result.extracted["as_owner"] == "Evil ISP"
        assert result.raw is not None
        assert result.enriched_at is not None

    async def test_happy_path_domain(self, provider: VirusTotalProvider) -> None:
        body = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 0,
                        "suspicious": 0,
                        "harmless": 80,
                        "undetected": 0,
                    },
                    "categories": {"Forcepoint ThreatSeeker": "Technology/Internet"},
                    "registrar": "NameCheap",
                    "creation_date": 946684800,
                    "tags": [],
                    "last_modification_date": 1700000000,
                }
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("example.com", IndicatorType.DOMAIN)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Benign"
        assert result.extracted["registrar"] == "NameCheap"

    async def test_happy_path_hash_sha256(self, provider: VirusTotalProvider) -> None:
        sha256 = "a" * 64
        body = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {"malicious": 50, "suspicious": 0, "harmless": 0},
                    "size": 1024,
                    "type_description": "PE32 executable",
                    "meaningful_name": "malware.exe",
                    "tags": ["trojan"],
                    "last_modification_date": 1700000000,
                }
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich(sha256, IndicatorType.HASH_SHA256)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Malicious"
        assert result.extracted["size"] == 1024
        assert result.extracted["meaningful_name"] == "malware.exe"

    async def test_happy_path_hash_md5(self, provider: VirusTotalProvider) -> None:
        md5 = "d" * 32
        body = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {"malicious": 0, "suspicious": 1, "harmless": 50},
                    "size": 512,
                    "type_description": "ELF",
                    "meaningful_name": "binary",
                    "tags": [],
                }
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich(md5, IndicatorType.HASH_MD5)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Suspicious"

    async def test_happy_path_hash_sha1(self, provider: VirusTotalProvider) -> None:
        sha1 = "b" * 40
        body = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {"malicious": 0, "suspicious": 0, "harmless": 60},
                    "size": 256,
                    "tags": [],
                }
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich(sha1, IndicatorType.HASH_SHA1)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Benign"

    async def test_not_found_404(self, provider: VirusTotalProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(404, {}))):
            result = await provider.enrich("0.0.0.0", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is False
        assert result.extracted["malice"] == "Pending"

    async def test_http_error_403(self, provider: VirusTotalProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(403, {}))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "403" in (result.error_message or "")

    async def test_http_error_500(self, provider: VirusTotalProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(500, {}))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "500" in (result.error_message or "")

    async def test_not_configured_returns_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.virustotal.settings.VIRUSTOTAL_API_KEY", ""
        )
        provider = VirusTotalProvider()
        assert provider.is_configured() is False
        result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED
        assert result.provider_name == "virustotal"
        assert "not configured" in (result.error_message or "").lower()

    async def test_unsupported_type_returns_skipped(
        self, provider: VirusTotalProvider
    ) -> None:
        result = await provider.enrich("user@example.com", IndicatorType.EMAIL)
        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_unsupported_type_account(self, provider: VirusTotalProvider) -> None:
        result = await provider.enrich("jdoe", IndicatorType.ACCOUNT)
        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_network_error_returns_failure_no_raise(
        self, provider: VirusTotalProvider
    ) -> None:
        """Network error (ConnectError) must not raise — returns failure result."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "Connection refused" in (result.error_message or "")

    async def test_timeout_returns_failure_no_raise(
        self, provider: VirusTotalProvider
    ) -> None:
        """Timeout must not raise — returns failure result."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.side_effect = httpx.ReadTimeout("Read timed out")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "timed out" in (result.error_message or "").lower()

    async def test_unexpected_exception_returns_failure_no_raise(
        self, provider: VirusTotalProvider
    ) -> None:
        """Any unexpected exception must not raise — returns failure result."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.side_effect = RuntimeError("Unexpected crash")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "Unexpected crash" in (result.error_message or "")

    async def test_malformed_json_returns_failure(
        self, provider: VirusTotalProvider
    ) -> None:
        """Malformed JSON body must not raise — returns failure result."""
        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.json.side_effect = ValueError("Invalid JSON")

        with patch("httpx.AsyncClient", _mock_async_client(bad_resp)):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED

    async def test_empty_attributes_returns_benign(
        self, provider: VirusTotalProvider
    ) -> None:
        """Missing attributes in response still returns successfully with defaults."""
        body: dict[str, Any] = {"data": {"attributes": {}}}
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        # With empty stats, _extract_malice returns Benign
        assert result.extracted["malice"] == "Benign"
        assert result.extracted["malicious_count"] == 0


# ===================================================================
# AbuseIPDB Provider Tests
# ===================================================================


class TestAbuseIPDBProviderAttributes:
    """Verify AbuseIPDB provider static attributes and helpers."""

    def test_provider_name(self) -> None:
        p = AbuseIPDBProvider()
        assert p.provider_name == "abuseipdb"

    def test_display_name(self) -> None:
        p = AbuseIPDBProvider()
        assert p.display_name == "AbuseIPDB"

    def test_supported_types_ip_only(self) -> None:
        p = AbuseIPDBProvider()
        assert p.supported_types == [IndicatorType.IP]

    def test_abuse_score_to_malice_malicious(self) -> None:
        assert _abuse_score_to_malice(75) == "Malicious"
        assert _abuse_score_to_malice(100) == "Malicious"

    def test_abuse_score_to_malice_suspicious(self) -> None:
        assert _abuse_score_to_malice(25) == "Suspicious"
        assert _abuse_score_to_malice(50) == "Suspicious"
        assert _abuse_score_to_malice(74) == "Suspicious"

    def test_abuse_score_to_malice_benign(self) -> None:
        assert _abuse_score_to_malice(0) == "Benign"
        assert _abuse_score_to_malice(24) == "Benign"


class TestAbuseIPDBProviderEnrich:
    """AbuseIPDB enrich() method tests."""

    @pytest.fixture
    def provider(self, monkeypatch: pytest.MonkeyPatch) -> AbuseIPDBProvider:
        monkeypatch.setattr(
            "app.integrations.enrichment.abuseipdb.settings.ABUSEIPDB_API_KEY",
            "test-abuse-key",
        )
        return AbuseIPDBProvider()

    async def test_happy_path_malicious(self, provider: AbuseIPDBProvider) -> None:
        body = {
            "data": {
                "abuseConfidenceScore": 90,
                "totalReports": 25,
                "countryCode": "CN",
                "isp": "Evil ISP",
                "usageType": "Fixed Line ISP",
                "isWhitelisted": False,
                "isTor": False,
                "isPublic": True,
                "numDistinctUsers": 10,
                "lastReportedAt": "2024-01-01T00:00:00+00:00",
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is True
        assert result.status == EnrichmentStatus.SUCCESS
        assert result.provider_name == "abuseipdb"
        assert result.extracted is not None
        assert result.extracted["malice"] == "Malicious"
        assert result.extracted["abuse_confidence_score"] == 90
        assert result.extracted["total_reports"] == 25
        assert result.extracted["country_code"] == "CN"
        assert result.extracted["isp"] == "Evil ISP"
        assert result.extracted["is_tor"] is False
        assert result.extracted["num_distinct_users"] == 10
        assert result.raw is not None
        assert result.enriched_at is not None

    async def test_happy_path_suspicious(self, provider: AbuseIPDBProvider) -> None:
        body = {
            "data": {
                "abuseConfidenceScore": 40,
                "totalReports": 5,
                "countryCode": "US",
                "isp": "Some ISP",
                "usageType": "Data Center/Web Hosting/Transit",
                "isWhitelisted": False,
                "isTor": False,
                "isPublic": True,
                "numDistinctUsers": 3,
                "lastReportedAt": None,
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("10.0.0.1", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Suspicious"
        assert result.extracted["abuse_confidence_score"] == 40

    async def test_happy_path_benign(self, provider: AbuseIPDBProvider) -> None:
        body = {
            "data": {
                "abuseConfidenceScore": 0,
                "totalReports": 0,
                "countryCode": "US",
                "isp": "Google LLC",
                "usageType": "Search Engine Spider",
                "isWhitelisted": True,
                "isTor": False,
                "isPublic": True,
                "numDistinctUsers": 0,
                "lastReportedAt": None,
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("8.8.8.8", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Benign"
        assert result.extracted["is_whitelisted"] is True

    async def test_happy_path_tor_node(self, provider: AbuseIPDBProvider) -> None:
        body = {
            "data": {
                "abuseConfidenceScore": 50,
                "totalReports": 100,
                "countryCode": "DE",
                "isp": "Tor Exit",
                "usageType": "Reserved",
                "isWhitelisted": False,
                "isTor": True,
                "isPublic": True,
                "numDistinctUsers": 50,
                "lastReportedAt": "2024-06-01T00:00:00+00:00",
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("5.6.7.8", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["is_tor"] is True
        assert result.extracted["malice"] == "Suspicious"

    async def test_rate_limited_429(self, provider: AbuseIPDBProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(429, {}))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "rate limit" in (result.error_message or "").lower()

    async def test_http_error_500(self, provider: AbuseIPDBProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(500, {}))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "500" in (result.error_message or "")

    async def test_not_configured_returns_skipped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.abuseipdb.settings.ABUSEIPDB_API_KEY", ""
        )
        provider = AbuseIPDBProvider()
        assert provider.is_configured() is False
        result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED
        assert "not configured" in (result.error_message or "").lower()

    async def test_unsupported_type_domain(self, provider: AbuseIPDBProvider) -> None:
        result = await provider.enrich("example.com", IndicatorType.DOMAIN)
        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_unsupported_type_hash(self, provider: AbuseIPDBProvider) -> None:
        result = await provider.enrich("a" * 64, IndicatorType.HASH_SHA256)
        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_unsupported_type_account(self, provider: AbuseIPDBProvider) -> None:
        result = await provider.enrich("user@example.com", IndicatorType.ACCOUNT)
        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_network_error_returns_failure_no_raise(
        self, provider: AbuseIPDBProvider
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.side_effect = httpx.ConnectError("Connection refused")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "Connection refused" in (result.error_message or "")

    async def test_timeout_returns_failure_no_raise(
        self, provider: AbuseIPDBProvider
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.side_effect = httpx.ReadTimeout("Read timed out")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED

    async def test_unexpected_exception_returns_failure_no_raise(
        self, provider: AbuseIPDBProvider
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.side_effect = RuntimeError("Unexpected crash")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED

    async def test_field_extraction_all_fields_present(
        self, provider: AbuseIPDBProvider
    ) -> None:
        """Verify all expected extracted fields are present."""
        body = {
            "data": {
                "abuseConfidenceScore": 10,
                "totalReports": 2,
                "countryCode": "CA",
                "isp": "Bell Canada",
                "usageType": "ISP",
                "isWhitelisted": False,
                "isTor": False,
                "isPublic": True,
                "numDistinctUsers": 1,
                "lastReportedAt": "2024-03-01T00:00:00+00:00",
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("9.9.9.9", IndicatorType.IP)

        expected_keys = {
            "abuse_confidence_score",
            "total_reports",
            "country_code",
            "isp",
            "usage_type",
            "is_whitelisted",
            "is_tor",
            "is_public",
            "num_distinct_users",
            "last_reported_at",
            "malice",
        }
        assert result.extracted is not None
        assert set(result.extracted.keys()) == expected_keys


# ===================================================================
# Okta Provider Tests
# ===================================================================


class TestOktaProviderAttributes:
    """Verify Okta provider static attributes."""

    def test_provider_name(self) -> None:
        p = OktaProvider()
        assert p.provider_name == "okta"

    def test_display_name(self) -> None:
        p = OktaProvider()
        assert p.display_name == "Okta"

    def test_supported_types_account_only(self) -> None:
        p = OktaProvider()
        assert p.supported_types == [IndicatorType.ACCOUNT]

    def test_cache_ttl(self) -> None:
        p = OktaProvider()
        assert p.cache_ttl_seconds == 900


class TestOktaProviderEnrich:
    """Okta enrich() method tests."""

    @pytest.fixture
    def provider(self, monkeypatch: pytest.MonkeyPatch) -> OktaProvider:
        monkeypatch.setattr(
            "app.integrations.enrichment.okta.settings.OKTA_DOMAIN", "acme.okta.com"
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.okta.settings.OKTA_API_TOKEN", "test-okta-token"
        )
        return OktaProvider()

    async def test_happy_path_user_found(self, provider: OktaProvider) -> None:
        user_resp = _mock_response(
            200,
            {
                "id": "00u1abc",
                "status": "ACTIVE",
                "created": "2021-01-01T00:00:00.000Z",
                "lastLogin": "2024-01-01T00:00:00.000Z",
                "passwordChanged": "2023-06-01T00:00:00.000Z",
                "credentials": {"provider": {"name": "OKTA"}},
                "profile": {
                    "login": "alice@example.com",
                    "email": "alice@example.com",
                    "firstName": "Alice",
                    "lastName": "Smith",
                },
            },
        )
        groups_resp = _mock_response(
            200,
            [{"profile": {"name": "Everyone"}}, {"profile": {"name": "Engineering"}}],
        )
        with patch("httpx.AsyncClient", _mock_async_client(user_resp, groups_resp)):
            result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.status == EnrichmentStatus.SUCCESS
        assert result.provider_name == "okta"
        assert result.extracted is not None
        assert result.extracted["found"] is True
        assert result.extracted["user_id"] == "00u1abc"
        assert result.extracted["login"] == "alice@example.com"
        assert result.extracted["email"] == "alice@example.com"
        assert result.extracted["first_name"] == "Alice"
        assert result.extracted["last_name"] == "Smith"
        assert result.extracted["status"] == "ACTIVE"
        assert "Engineering" in result.extracted["groups"]
        assert "Everyone" in result.extracted["groups"]
        assert result.extracted["mfa_enrolled"] is True
        assert result.raw is not None
        assert result.enriched_at is not None

    async def test_happy_path_user_no_mfa(self, provider: OktaProvider) -> None:
        """User without MFA credentials provider shows mfa_enrolled=False."""
        user_resp = _mock_response(
            200,
            {
                "id": "00u2def",
                "status": "ACTIVE",
                "created": "2021-01-01T00:00:00.000Z",
                "lastLogin": "2024-01-01T00:00:00.000Z",
                "passwordChanged": None,
                "credentials": {},
                "profile": {
                    "login": "bob@example.com",
                    "email": "bob@example.com",
                    "firstName": "Bob",
                    "lastName": "Jones",
                },
            },
        )
        groups_resp = _mock_response(200, [])
        with patch("httpx.AsyncClient", _mock_async_client(user_resp, groups_resp)):
            result = await provider.enrich("bob@example.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["mfa_enrolled"] is False
        assert result.extracted["groups"] == []

    async def test_user_not_found_404(self, provider: OktaProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(404, {}))):
            result = await provider.enrich("ghost@example.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is False

    async def test_http_error_500(self, provider: OktaProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(500, {}))):
            result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "500" in (result.error_message or "")

    async def test_not_configured_missing_domain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.integrations.enrichment.okta.settings.OKTA_DOMAIN", "")
        monkeypatch.setattr(
            "app.integrations.enrichment.okta.settings.OKTA_API_TOKEN", "test-token"
        )
        provider = OktaProvider()
        assert provider.is_configured() is False
        result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_not_configured_missing_token(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.okta.settings.OKTA_DOMAIN", "acme.okta.com"
        )
        monkeypatch.setattr("app.integrations.enrichment.okta.settings.OKTA_API_TOKEN", "")
        provider = OktaProvider()
        assert provider.is_configured() is False
        result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_not_configured_both_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("app.integrations.enrichment.okta.settings.OKTA_DOMAIN", "")
        monkeypatch.setattr("app.integrations.enrichment.okta.settings.OKTA_API_TOKEN", "")
        provider = OktaProvider()
        assert provider.is_configured() is False

    async def test_unsupported_type_ip(self, provider: OktaProvider) -> None:
        result = await provider.enrich("1.2.3.4", IndicatorType.IP)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_unsupported_type_domain(self, provider: OktaProvider) -> None:
        result = await provider.enrich("example.com", IndicatorType.DOMAIN)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_network_error_returns_failure_no_raise(
        self, provider: OktaProvider
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.side_effect = httpx.ConnectError("DNS resolution failed")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED

    async def test_timeout_returns_failure_no_raise(
        self, provider: OktaProvider
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.get.side_effect = httpx.ReadTimeout("Read timed out")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED

    async def test_groups_endpoint_failure_does_not_break_enrichment(
        self, provider: OktaProvider
    ) -> None:
        """If the groups sub-request fails, user enrichment still succeeds."""
        user_resp = _mock_response(
            200,
            {
                "id": "00u1abc",
                "status": "ACTIVE",
                "created": "2021-01-01T00:00:00.000Z",
                "lastLogin": None,
                "passwordChanged": None,
                "credentials": {},
                "profile": {
                    "login": "alice@example.com",
                    "email": "alice@example.com",
                    "firstName": "Alice",
                    "lastName": "Smith",
                },
            },
        )
        groups_fail = _mock_response(500, {"error": "internal"})
        with patch("httpx.AsyncClient", _mock_async_client(user_resp, groups_fail)):
            result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is True
        # Groups should be empty since the groups call returned non-200
        assert result.extracted["groups"] == []

    async def test_field_extraction_all_fields_present(
        self, provider: OktaProvider
    ) -> None:
        """Verify all expected extracted fields are present."""
        user_resp = _mock_response(
            200,
            {
                "id": "00u1abc",
                "status": "ACTIVE",
                "created": "2021-01-01T00:00:00.000Z",
                "lastLogin": "2024-01-01T00:00:00.000Z",
                "passwordChanged": "2023-06-01T00:00:00.000Z",
                "credentials": {"provider": {"name": "OKTA"}},
                "profile": {
                    "login": "alice@example.com",
                    "email": "alice@example.com",
                    "firstName": "Alice",
                    "lastName": "Smith",
                },
            },
        )
        groups_resp = _mock_response(200, [])
        with patch("httpx.AsyncClient", _mock_async_client(user_resp, groups_resp)):
            result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)

        expected_keys = {
            "found",
            "user_id",
            "login",
            "email",
            "first_name",
            "last_name",
            "status",
            "created",
            "last_login",
            "password_changed",
            "groups",
            "mfa_enrolled",
        }
        assert result.extracted is not None
        assert set(result.extracted.keys()) == expected_keys


# ===================================================================
# Microsoft Entra Provider Tests
# ===================================================================


class TestEntraProviderAttributes:
    """Verify Entra provider static attributes."""

    def test_provider_name(self) -> None:
        p = EntraProvider()
        assert p.provider_name == "entra"

    def test_display_name(self) -> None:
        p = EntraProvider()
        assert p.display_name == "Microsoft Entra ID"

    def test_supported_types_account_only(self) -> None:
        p = EntraProvider()
        assert p.supported_types == [IndicatorType.ACCOUNT]

    def test_cache_ttl(self) -> None:
        p = EntraProvider()
        assert p.cache_ttl_seconds == 900


class TestEntraProviderEnrich:
    """Entra enrich() method tests."""

    @pytest.fixture
    def provider(self, monkeypatch: pytest.MonkeyPatch) -> EntraProvider:
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_TENANT_ID", "tenant-123"
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_ID", "client-456"
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_SECRET", "secret-789"
        )
        return EntraProvider()

    def _token_response(self) -> MagicMock:
        return _mock_response(200, {"access_token": "test-token", "expires_in": 3600})

    def _entra_mock_client(
        self,
        token_resp: MagicMock,
        *get_responses: MagicMock,
    ) -> MagicMock:
        """Build a mock httpx client that returns token_resp for POST and
        get_responses in sequence for GET."""
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.post.return_value = token_resp
        if len(get_responses) == 1:
            mock_client.get.return_value = get_responses[0]
        else:
            mock_client.get.side_effect = list(get_responses)
        return MagicMock(return_value=mock_client)

    async def test_happy_path_user_found(self, provider: EntraProvider) -> None:
        user_resp = _mock_response(
            200,
            {
                "id": "obj-001",
                "displayName": "Alice Smith",
                "userPrincipalName": "alice@contoso.com",
                "mail": "alice@contoso.com",
                "accountEnabled": True,
                "department": "Engineering",
                "jobTitle": "SWE",
                "lastPasswordChangeDateTime": "2024-01-01T00:00:00Z",
            },
        )
        groups_resp = _mock_response(
            200,
            {"value": [{"displayName": "All Users"}, {"displayName": "Engineering"}]},
        )

        with patch(
            "httpx.AsyncClient",
            self._entra_mock_client(self._token_response(), user_resp, groups_resp),
        ):
            result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.status == EnrichmentStatus.SUCCESS
        assert result.provider_name == "entra"
        assert result.extracted is not None
        assert result.extracted["found"] is True
        assert result.extracted["object_id"] == "obj-001"
        assert result.extracted["display_name"] == "Alice Smith"
        assert result.extracted["user_principal_name"] == "alice@contoso.com"
        assert result.extracted["mail"] == "alice@contoso.com"
        assert result.extracted["account_enabled"] is True
        assert result.extracted["department"] == "Engineering"
        assert result.extracted["job_title"] == "SWE"
        assert "Engineering" in result.extracted["groups"]
        assert "All Users" in result.extracted["groups"]
        assert result.raw is not None
        assert result.enriched_at is not None

    async def test_happy_path_disabled_account(self, provider: EntraProvider) -> None:
        user_resp = _mock_response(
            200,
            {
                "id": "obj-002",
                "displayName": "Bob Disabled",
                "userPrincipalName": "bob@contoso.com",
                "mail": None,
                "accountEnabled": False,
                "department": None,
                "jobTitle": None,
                "lastPasswordChangeDateTime": None,
            },
        )
        groups_resp = _mock_response(200, {"value": []})

        with patch(
            "httpx.AsyncClient",
            self._entra_mock_client(self._token_response(), user_resp, groups_resp),
        ):
            result = await provider.enrich("bob@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["account_enabled"] is False
        assert result.extracted["groups"] == []

    async def test_user_not_found_404(self, provider: EntraProvider) -> None:
        not_found_resp = _mock_response(404, {})
        with patch(
            "httpx.AsyncClient",
            self._entra_mock_client(self._token_response(), not_found_resp),
        ):
            result = await provider.enrich("ghost@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is False

    async def test_token_failure_401(self, provider: EntraProvider) -> None:
        token_fail = _mock_response(401, {"error": "unauthorized_client"})
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.post.return_value = token_fail

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "token acquisition" in (result.error_message or "").lower()

    async def test_user_lookup_http_error(self, provider: EntraProvider) -> None:
        user_error = _mock_response(403, {"error": "forbidden"})
        with patch(
            "httpx.AsyncClient",
            self._entra_mock_client(self._token_response(), user_error),
        ):
            result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "403" in (result.error_message or "")

    async def test_token_caching_reuses_token(self, provider: EntraProvider) -> None:
        """Second enrich() call reuses cached token."""
        user_resp = _mock_response(
            200,
            {
                "id": "obj-001",
                "displayName": "Alice",
                "userPrincipalName": "alice@contoso.com",
                "mail": None,
                "accountEnabled": True,
                "department": None,
                "jobTitle": None,
                "lastPasswordChangeDateTime": None,
            },
        )
        groups_resp = _mock_response(200, {"value": []})

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.post.return_value = self._token_response()
        # 4 GET calls: user+groups for first enrich, user+groups for second
        mock_client.get.side_effect = [
            user_resp,
            groups_resp,
            user_resp,
            groups_resp,
        ]

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)
            assert provider._token_is_valid()
            result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is True
        # Token POST should have been called only once (cached for second call)
        mock_client.post.assert_awaited_once()

    async def test_not_configured_missing_tenant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_TENANT_ID", ""
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_ID", "client"
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_SECRET", "secret"
        )
        provider = EntraProvider()
        assert provider.is_configured() is False
        result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_not_configured_missing_client_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_TENANT_ID", "tenant"
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_ID", ""
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_SECRET", "secret"
        )
        provider = EntraProvider()
        assert provider.is_configured() is False

    async def test_not_configured_missing_secret(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_TENANT_ID", "tenant"
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_ID", "client"
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_SECRET", ""
        )
        provider = EntraProvider()
        assert provider.is_configured() is False

    async def test_unsupported_type_ip(self, provider: EntraProvider) -> None:
        result = await provider.enrich("1.2.3.4", IndicatorType.IP)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_unsupported_type_domain(self, provider: EntraProvider) -> None:
        result = await provider.enrich("example.com", IndicatorType.DOMAIN)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_unsupported_type_hash(self, provider: EntraProvider) -> None:
        result = await provider.enrich("a" * 64, IndicatorType.HASH_SHA256)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_network_error_returns_failure_no_raise(
        self, provider: EntraProvider
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.post.side_effect = httpx.ConnectError("Connection refused")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED

    async def test_timeout_returns_failure_no_raise(
        self, provider: EntraProvider
    ) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.post.side_effect = httpx.ReadTimeout("Read timed out")

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED

    async def test_groups_endpoint_failure_still_returns_user(
        self, provider: EntraProvider
    ) -> None:
        """If groups sub-request fails (non-200), enrichment still succeeds."""
        user_resp = _mock_response(
            200,
            {
                "id": "obj-001",
                "displayName": "Alice",
                "userPrincipalName": "alice@contoso.com",
                "mail": None,
                "accountEnabled": True,
                "department": None,
                "jobTitle": None,
                "lastPasswordChangeDateTime": None,
            },
        )
        groups_fail = _mock_response(403, {"error": "forbidden"})

        with patch(
            "httpx.AsyncClient",
            self._entra_mock_client(self._token_response(), user_resp, groups_fail),
        ):
            result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is True
        assert result.extracted["groups"] == []

    async def test_field_extraction_all_fields_present(
        self, provider: EntraProvider
    ) -> None:
        """Verify all expected extracted fields are present."""
        user_resp = _mock_response(
            200,
            {
                "id": "obj-001",
                "displayName": "Alice",
                "userPrincipalName": "alice@contoso.com",
                "mail": "alice@contoso.com",
                "accountEnabled": True,
                "department": "Security",
                "jobTitle": "Analyst",
                "lastPasswordChangeDateTime": "2024-01-01T00:00:00Z",
            },
        )
        groups_resp = _mock_response(200, {"value": []})

        with patch(
            "httpx.AsyncClient",
            self._entra_mock_client(self._token_response(), user_resp, groups_resp),
        ):
            result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)

        expected_keys = {
            "found",
            "object_id",
            "user_principal_name",
            "display_name",
            "mail",
            "account_enabled",
            "department",
            "job_title",
            "last_password_change",
            "groups",
        }
        assert result.extracted is not None
        assert set(result.extracted.keys()) == expected_keys


# ===================================================================
# Cross-Provider Contract Tests
# ===================================================================


class TestProviderContracts:
    """Verify that ALL providers satisfy the base contract."""

    def test_all_providers_subclass_base(self) -> None:
        """Every provider must be a subclass of EnrichmentProviderBase."""
        for cls in [VirusTotalProvider, AbuseIPDBProvider, OktaProvider, EntraProvider]:
            assert issubclass(cls, EnrichmentProviderBase)

    def test_all_providers_have_required_class_attrs(self) -> None:
        """Every provider must define provider_name, display_name, supported_types."""
        for cls in [VirusTotalProvider, AbuseIPDBProvider, OktaProvider, EntraProvider]:
            inst = cls()  # type: ignore[abstract]
            assert isinstance(inst.provider_name, str)
            assert len(inst.provider_name) > 0
            assert isinstance(inst.display_name, str)
            assert len(inst.display_name) > 0
            assert isinstance(inst.supported_types, list)
            assert len(inst.supported_types) > 0
            assert all(isinstance(t, IndicatorType) for t in inst.supported_types)

    def test_all_providers_have_unique_names(self) -> None:
        names = [cls().provider_name for cls in [  # type: ignore[abstract]
            VirusTotalProvider, AbuseIPDBProvider, OktaProvider, EntraProvider
        ]]
        assert len(names) == len(set(names))

    def test_get_cache_ttl_returns_int(self) -> None:
        for cls in [VirusTotalProvider, AbuseIPDBProvider, OktaProvider, EntraProvider]:
            inst = cls()  # type: ignore[abstract]
            for itype in inst.supported_types:
                ttl = inst.get_cache_ttl(itype)
                assert isinstance(ttl, int)
                assert ttl > 0
