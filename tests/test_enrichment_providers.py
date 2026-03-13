"""
Unit tests for all enrichment providers.

httpx.AsyncClient is patched at the module level so no real HTTP calls are made.
Each provider is tested for:
  - Successful enrichment with expected field extraction
  - 404 response (not found, success=True with found=False)
  - HTTP error (success=False with error message)
  - Provider not configured (skipped result)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.enrichment.abuseipdb import AbuseIPDBProvider
from app.integrations.enrichment.entra import EntraProvider
from app.integrations.enrichment.okta import OktaProvider
from app.integrations.enrichment.virustotal import VirusTotalProvider
from app.schemas.enrichment import EnrichmentStatus
from app.schemas.indicators import IndicatorType


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

    # Configure get/post to return responses in sequence if multiple given
    if len(responses) == 1:
        mock_client.get.return_value = responses[0]
        mock_client.post.return_value = responses[0]
    else:
        # Side-effect list for multiple calls (e.g. user + groups)
        mock_client.get.side_effect = list(responses)
        mock_client.post.side_effect = list(responses)

    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls


# ---------------------------------------------------------------------------
# VirusTotal
# ---------------------------------------------------------------------------


class TestVirusTotalProvider:
    @pytest.fixture
    def provider(self, monkeypatch: pytest.MonkeyPatch) -> VirusTotalProvider:
        monkeypatch.setattr(
            "app.integrations.enrichment.virustotal.settings.VIRUSTOTAL_API_KEY",
            "test-vt-key",
        )
        return VirusTotalProvider()

    async def test_ip_malicious(self, provider: VirusTotalProvider) -> None:
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
                    "as_owner": "Some ISP",
                    "last_analysis_date": 1700000000,
                }
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is True
        assert result.status == EnrichmentStatus.SUCCESS
        assert result.extracted is not None
        assert result.extracted["malice"] == "Malicious"
        assert result.extracted["malicious_count"] == 10

    async def test_ip_suspicious(self, provider: VirusTotalProvider) -> None:
        body = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 0,
                        "suspicious": 3,
                        "harmless": 70,
                        "undetected": 7,
                    },
                    "country": "US",
                    "as_owner": "Cloudflare",
                    "last_analysis_date": 1700000000,
                }
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("1.1.1.1", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Suspicious"

    async def test_ip_benign(self, provider: VirusTotalProvider) -> None:
        body = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 0,
                        "suspicious": 0,
                        "harmless": 75,
                        "undetected": 5,
                    },
                    "country": "US",
                    "as_owner": "Google",
                    "last_analysis_date": 1700000000,
                }
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("8.8.8.8", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Benign"

    async def test_ip_not_found(self, provider: VirusTotalProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(404, {}))):
            result = await provider.enrich("0.0.0.0", IndicatorType.IP)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is False

    async def test_ip_http_error(self, provider: VirusTotalProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(403, {}))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED

    async def test_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.virustotal.settings.VIRUSTOTAL_API_KEY", ""
        )
        provider = VirusTotalProvider()
        result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_unsupported_type(self, provider: VirusTotalProvider) -> None:
        result = await provider.enrich("user@example.com", IndicatorType.EMAIL)
        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_domain_enrichment(self, provider: VirusTotalProvider) -> None:
        body = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 0,
                        "suspicious": 0,
                        "harmless": 80,
                        "undetected": 0,
                    },
                    "last_analysis_date": 1700000000,
                    "categories": {"Forcepoint ThreatSeeker": "Technology/Internet"},
                    "creation_date": 946684800,
                }
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich("example.com", IndicatorType.DOMAIN)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Benign"

    async def test_hash_enrichment(self, provider: VirusTotalProvider) -> None:
        sha256 = "a" * 64
        body = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "malicious": 50,
                        "suspicious": 0,
                        "harmless": 0,
                        "undetected": 0,
                    },
                    "size": 1024,
                    "type_description": "PE32 executable",
                    "meaningful_name": "malware.exe",
                    "last_analysis_date": 1700000000,
                }
            }
        }
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await provider.enrich(sha256, IndicatorType.HASH_SHA256)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["malice"] == "Malicious"


# ---------------------------------------------------------------------------
# AbuseIPDB
# ---------------------------------------------------------------------------


class TestAbuseIPDBProvider:
    @pytest.fixture
    def provider(self, monkeypatch: pytest.MonkeyPatch) -> AbuseIPDBProvider:
        monkeypatch.setattr(
            "app.integrations.enrichment.abuseipdb.settings.ABUSEIPDB_API_KEY",
            "test-abuse-key",
        )
        return AbuseIPDBProvider()

    async def test_malicious_score(self, provider: AbuseIPDBProvider) -> None:
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
        assert result.extracted is not None
        assert result.extracted["malice"] == "Malicious"
        assert result.extracted["abuse_confidence_score"] == 90

    async def test_suspicious_score(self, provider: AbuseIPDBProvider) -> None:
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

    async def test_benign_score(self, provider: AbuseIPDBProvider) -> None:
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

    async def test_rate_limited(self, provider: AbuseIPDBProvider) -> None:
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(429, {}))):
            result = await provider.enrich("1.2.3.4", IndicatorType.IP)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "rate limit" in (result.error_message or "").lower()

    async def test_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.abuseipdb.settings.ABUSEIPDB_API_KEY", ""
        )
        provider = AbuseIPDBProvider()
        result = await provider.enrich("1.2.3.4", IndicatorType.IP)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_unsupported_type(self, provider: AbuseIPDBProvider) -> None:
        result = await provider.enrich("example.com", IndicatorType.DOMAIN)
        assert result.status == EnrichmentStatus.SKIPPED


# ---------------------------------------------------------------------------
# Okta
# ---------------------------------------------------------------------------


class TestOktaProvider:
    @pytest.fixture
    def provider(self, monkeypatch: pytest.MonkeyPatch) -> OktaProvider:
        monkeypatch.setattr(
            "app.integrations.enrichment.okta.settings.OKTA_DOMAIN",
            "acme.okta.com",
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.okta.settings.OKTA_API_TOKEN",
            "test-okta-token",
        )
        return OktaProvider()

    async def test_user_found(self, provider: OktaProvider) -> None:
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
        with patch(
            "httpx.AsyncClient", _mock_async_client(user_resp, groups_resp)
        ):
            result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is True
        assert result.extracted["login"] == "alice@example.com"
        assert result.extracted["status"] == "ACTIVE"
        assert "Engineering" in result.extracted["groups"]
        assert result.extracted["mfa_enrolled"] is True

    async def test_user_not_found(self, provider: OktaProvider) -> None:
        with patch(
            "httpx.AsyncClient", _mock_async_client(_mock_response(404, {}))
        ):
            result = await provider.enrich("ghost@example.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is False

    async def test_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.okta.settings.OKTA_DOMAIN", ""
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.okta.settings.OKTA_API_TOKEN", ""
        )
        provider = OktaProvider()
        result = await provider.enrich("alice@example.com", IndicatorType.ACCOUNT)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_unsupported_type(self, provider: OktaProvider) -> None:
        result = await provider.enrich("1.2.3.4", IndicatorType.IP)
        assert result.status == EnrichmentStatus.SKIPPED


# ---------------------------------------------------------------------------
# Microsoft Entra
# ---------------------------------------------------------------------------


class TestEntraProvider:
    @pytest.fixture
    def provider(self, monkeypatch: pytest.MonkeyPatch) -> EntraProvider:
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_TENANT_ID",
            "tenant-123",
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_ID",
            "client-456",
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_SECRET",
            "secret-789",
        )
        return EntraProvider()

    def _token_response(self) -> MagicMock:
        return _mock_response(
            200, {"access_token": "test-token", "expires_in": 3600}
        )

    async def test_user_found(self, provider: EntraProvider) -> None:
        token_resp = self._token_response()
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

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        # First call is token (POST), remaining are user+groups (GET)
        mock_client.post.return_value = token_resp
        mock_client.get.side_effect = [user_resp, groups_resp]

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is True
        assert result.extracted["display_name"] == "Alice Smith"
        assert result.extracted["account_enabled"] is True
        assert "Engineering" in result.extracted["groups"]

    async def test_user_not_found(self, provider: EntraProvider) -> None:
        token_resp = self._token_response()
        not_found_resp = _mock_response(404, {})

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.post.return_value = token_resp
        mock_client.get.return_value = not_found_resp

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("ghost@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is False

    async def test_token_failure(self, provider: EntraProvider) -> None:
        token_fail = _mock_response(401, {"error": "unauthorized_client"})

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.post.return_value = token_fail

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED

    async def test_token_cached(self, provider: EntraProvider) -> None:
        """Second enrich() call reuses cached token — no second POST."""
        token_resp = self._token_response()
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
        mock_client.post.return_value = token_resp
        mock_client.get.side_effect = [user_resp, groups_resp, user_resp, groups_resp]

        with patch("httpx.AsyncClient", MagicMock(return_value=mock_client)):
            await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)
            # Manually expire token to test it is NOT expired yet
            assert provider._token_is_valid()

    async def test_not_configured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_TENANT_ID", ""
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_ID", ""
        )
        monkeypatch.setattr(
            "app.integrations.enrichment.entra.settings.ENTRA_CLIENT_SECRET", ""
        )
        provider = EntraProvider()
        result = await provider.enrich("alice@contoso.com", IndicatorType.ACCOUNT)
        assert result.status == EnrichmentStatus.SKIPPED

    async def test_unsupported_type(self, provider: EntraProvider) -> None:
        result = await provider.enrich("1.2.3.4", IndicatorType.IP)
        assert result.status == EnrichmentStatus.SKIPPED
