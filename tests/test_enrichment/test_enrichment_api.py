"""
Integration tests for the enrichment API endpoints.

Tests:
  1. POST /v1/enrichments — on-demand enrichment endpoint
  2. GET /v1/enrichments/providers — list all providers with configuration status
  3. Auth enforcement on enrichment endpoints

These tests use the FastAPI test client with mocked enrichment providers
(no real HTTP calls to external APIs) and require a running test database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from app.schemas.enrichment import EnrichmentResult, EnrichmentStatus
from app.schemas.indicators import IndicatorType
from tests.integration.conftest import auth_header


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_provider(
    name: str,
    display_name: str,
    types: list[IndicatorType],
    result: EnrichmentResult,
    *,
    is_configured: bool = True,
) -> MagicMock:
    """Return a mock provider."""
    provider = MagicMock()
    provider.provider_name = name
    provider.display_name = display_name
    provider.supported_types = types
    provider.cache_ttl_seconds = 3600
    provider.is_configured.return_value = is_configured
    provider.get_cache_ttl.return_value = 3600
    provider.enrich = AsyncMock(return_value=result)
    return provider


def _success_result(provider_name: str, malice: str = "Benign") -> EnrichmentResult:
    return EnrichmentResult.success_result(
        provider_name=provider_name,
        extracted={"found": True, "malice": malice, "score": 42},
        raw={"full": "response"},
        enriched_at=datetime.now(UTC),
    )


def _failure_result(provider_name: str) -> EnrichmentResult:
    return EnrichmentResult.failure_result(provider_name, "API error")


# ===================================================================
# POST /v1/enrichments — On-Demand Enrichment
# ===================================================================


class TestOnDemandEnrichment:
    """POST /v1/enrichments."""

    async def test_returns_200_with_results(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        """Successful enrichment returns 200 with results dict."""
        vt = _mock_provider(
            "virustotal", "VirusTotal", [IndicatorType.IP], _success_result("virustotal")
        )

        with (
            patch(
                "app.api.v1.enrichments.enrichment_registry.list_for_type",
                return_value=[vt],
            ),
            patch(
                "app.api.v1.enrichments.EnrichmentService.enrich_indicator",
                AsyncMock(return_value={"virustotal": _success_result("virustotal")}),
            ),
        ):
            resp = await test_client.post(
                "/v1/enrichments",
                json={"type": "ip", "value": "8.8.8.8"},
                headers=auth_header(enrichments_read_key),
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["type"] == "ip"
        assert data["value"] == "8.8.8.8"
        assert "results" in data
        assert "virustotal" in data["results"]
        assert data["results"]["virustotal"]["success"] is True
        assert data["results"]["virustotal"]["extracted"]["malice"] == "Benign"
        assert "enriched_at" in data

    async def test_echoes_type_and_value(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        with patch(
            "app.api.v1.enrichments.enrichment_registry.list_for_type",
            return_value=[],
        ):
            resp = await test_client.post(
                "/v1/enrichments",
                json={"type": "domain", "value": "example.com"},
                headers=auth_header(enrichments_read_key),
            )
        data = resp.json()["data"]
        assert data["type"] == "domain"
        assert data["value"] == "example.com"

    async def test_no_providers_returns_empty_results(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        """No configured providers for the type returns empty results dict."""
        with patch(
            "app.api.v1.enrichments.enrichment_registry.list_for_type",
            return_value=[],
        ):
            resp = await test_client.post(
                "/v1/enrichments",
                json={"type": "email", "value": "x@y.com"},
                headers=auth_header(enrichments_read_key),
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["results"] == {}

    async def test_results_dict_structure(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        """Each provider result has the expected schema fields."""
        vt = _mock_provider(
            "virustotal", "VirusTotal", [IndicatorType.IP], _success_result("virustotal")
        )

        with (
            patch(
                "app.api.v1.enrichments.enrichment_registry.list_for_type",
                return_value=[vt],
            ),
            patch(
                "app.api.v1.enrichments.EnrichmentService.enrich_indicator",
                AsyncMock(return_value={"virustotal": _success_result("virustotal")}),
            ),
        ):
            resp = await test_client.post(
                "/v1/enrichments",
                json={"type": "ip", "value": "1.2.3.4"},
                headers=auth_header(enrichments_read_key),
            )

        result = resp.json()["data"]["results"]["virustotal"]
        assert "status" in result
        assert "success" in result
        assert "extracted" in result
        assert "enriched_at" in result
        assert "cache_hit" in result

    async def test_invalid_type_returns_422(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/enrichments",
            json={"type": "invalid_type", "value": "test"},
            headers=auth_header(enrichments_read_key),
        )
        assert resp.status_code == 422

    async def test_missing_value_returns_422(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/enrichments",
            json={"type": "ip"},
            headers=auth_header(enrichments_read_key),
        )
        assert resp.status_code == 422

    async def test_missing_type_returns_422(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/enrichments",
            json={"value": "1.2.3.4"},
            headers=auth_header(enrichments_read_key),
        )
        assert resp.status_code == 422

    async def test_empty_body_returns_422(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/enrichments",
            json={},
            headers=auth_header(enrichments_read_key),
        )
        assert resp.status_code == 422

    async def test_indicator_type_alias_accepted(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        """Accepts indicator_type/indicator_value as aliases for type/value."""
        with patch(
            "app.api.v1.enrichments.enrichment_registry.list_for_type",
            return_value=[],
        ):
            resp = await test_client.post(
                "/v1/enrichments",
                json={"indicator_type": "ip", "indicator_value": "1.2.3.4"},
                headers=auth_header(enrichments_read_key),
            )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["type"] == "ip"
        assert data["value"] == "1.2.3.4"

    async def test_all_indicator_types_accepted(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        """All valid indicator types are accepted without 422."""
        valid_types = ["ip", "domain", "hash_md5", "hash_sha1", "hash_sha256", "url", "email", "account"]
        for itype in valid_types:
            with patch(
                "app.api.v1.enrichments.enrichment_registry.list_for_type",
                return_value=[],
            ):
                resp = await test_client.post(
                    "/v1/enrichments",
                    json={"type": itype, "value": "test-value"},
                    headers=auth_header(enrichments_read_key),
                )
            assert resp.status_code == 200, f"Type '{itype}' returned {resp.status_code}"

    async def test_failed_provider_included_in_results(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        """Failed provider results are included with success=False."""
        vt = _mock_provider(
            "virustotal", "VirusTotal", [IndicatorType.IP], _failure_result("virustotal")
        )

        with (
            patch(
                "app.api.v1.enrichments.enrichment_registry.list_for_type",
                return_value=[vt],
            ),
            patch(
                "app.api.v1.enrichments.EnrichmentService.enrich_indicator",
                AsyncMock(return_value={"virustotal": _failure_result("virustotal")}),
            ),
        ):
            resp = await test_client.post(
                "/v1/enrichments",
                json={"type": "ip", "value": "1.2.3.4"},
                headers=auth_header(enrichments_read_key),
            )

        assert resp.status_code == 200
        result = resp.json()["data"]["results"]["virustotal"]
        assert result["success"] is False
        assert result["status"] == "failed"
        assert result["error_message"] is not None

    async def test_response_wrapped_in_data_envelope(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        """Response follows DataResponse[T] envelope convention."""
        with patch(
            "app.api.v1.enrichments.enrichment_registry.list_for_type",
            return_value=[],
        ):
            resp = await test_client.post(
                "/v1/enrichments",
                json={"type": "ip", "value": "1.2.3.4"},
                headers=auth_header(enrichments_read_key),
            )

        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], dict)


# ===================================================================
# GET /v1/enrichments/providers — Provider Listing
# ===================================================================


class TestProviderList:
    """GET /v1/enrichments/providers."""

    async def test_list_returns_200(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/enrichments/providers",
            headers=auth_header(enrichments_read_key),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_provider_entry_structure(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        """Each provider entry has the expected schema fields."""
        resp = await test_client.get(
            "/v1/enrichments/providers",
            headers=auth_header(enrichments_read_key),
        )
        providers = resp.json()["data"]
        # The global registry should have at least the 4 built-in providers
        assert len(providers) >= 4

        for p in providers:
            assert "provider_name" in p
            assert "display_name" in p
            assert "supported_types" in p
            assert "is_configured" in p
            assert "cache_ttl_seconds" in p
            assert isinstance(p["supported_types"], list)
            assert isinstance(p["is_configured"], bool)
            assert isinstance(p["cache_ttl_seconds"], int)

    async def test_all_four_builtin_providers_listed(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        """All 4 built-in providers are present in the listing."""
        resp = await test_client.get(
            "/v1/enrichments/providers",
            headers=auth_header(enrichments_read_key),
        )
        names = [p["provider_name"] for p in resp.json()["data"]]
        assert "virustotal" in names
        assert "abuseipdb" in names
        assert "okta" in names
        assert "entra" in names

    async def test_provider_display_names(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/enrichments/providers",
            headers=auth_header(enrichments_read_key),
        )
        providers = {p["provider_name"]: p for p in resp.json()["data"]}
        assert providers["virustotal"]["display_name"] == "VirusTotal"
        assert providers["abuseipdb"]["display_name"] == "AbuseIPDB"
        assert providers["okta"]["display_name"] == "Okta"
        assert providers["entra"]["display_name"] == "Microsoft Entra ID"

    async def test_supported_types_correct_per_provider(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/enrichments/providers",
            headers=auth_header(enrichments_read_key),
        )
        providers = {p["provider_name"]: p for p in resp.json()["data"]}

        vt_types = set(providers["virustotal"]["supported_types"])
        assert vt_types == {"ip", "domain", "hash_md5", "hash_sha1", "hash_sha256"}

        abuse_types = set(providers["abuseipdb"]["supported_types"])
        assert abuse_types == {"ip"}

        okta_types = set(providers["okta"]["supported_types"])
        assert okta_types == {"account"}

        entra_types = set(providers["entra"]["supported_types"])
        assert entra_types == {"account"}

    async def test_response_wrapped_in_data_envelope(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/enrichments/providers",
            headers=auth_header(enrichments_read_key),
        )
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)


# ===================================================================
# Auth Enforcement
# ===================================================================


class TestEnrichmentAuth:
    """Auth enforcement on enrichment endpoints."""

    async def test_no_auth_header_returns_401(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Request without Authorization header returns 401."""
        resp = await test_client.post(
            "/v1/enrichments",
            json={"type": "ip", "value": "1.2.3.4"},
        )
        assert resp.status_code in (401, 403)

    async def test_invalid_api_key_returns_401(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Request with invalid API key returns 401."""
        resp = await test_client.post(
            "/v1/enrichments",
            json={"type": "ip", "value": "1.2.3.4"},
            headers=auth_header("cai_invalid_key_that_does_not_exist"),
        )
        assert resp.status_code in (401, 403)

    async def test_wrong_scope_returns_403(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        """alerts:read scope cannot access enrichment endpoints."""
        resp = await test_client.post(
            "/v1/enrichments",
            json={"type": "ip", "value": "1.2.3.4"},
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_wrong_scope_for_providers_list(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        """alerts:read scope cannot access provider listing."""
        resp = await test_client.get(
            "/v1/enrichments/providers",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_enrichments_read_scope_works_for_both_endpoints(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        """enrichments:read scope can access both enrichment endpoints."""
        with patch(
            "app.api.v1.enrichments.enrichment_registry.list_for_type",
            return_value=[],
        ):
            resp1 = await test_client.post(
                "/v1/enrichments",
                json={"type": "ip", "value": "1.2.3.4"},
                headers=auth_header(enrichments_read_key),
            )
        assert resp1.status_code == 200

        resp2 = await test_client.get(
            "/v1/enrichments/providers",
            headers=auth_header(enrichments_read_key),
        )
        assert resp2.status_code == 200

    async def test_admin_scope_works(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        """admin scope can access enrichment endpoints."""
        with patch(
            "app.api.v1.enrichments.enrichment_registry.list_for_type",
            return_value=[],
        ):
            resp = await test_client.post(
                "/v1/enrichments",
                json={"type": "ip", "value": "1.2.3.4"},
                headers=auth_header(api_key),
            )
        assert resp.status_code == 200

    async def test_no_auth_providers_list_returns_401(
        self,
        test_client: AsyncClient,
    ) -> None:
        """Provider list without auth returns 401."""
        resp = await test_client.get("/v1/enrichments/providers")
        assert resp.status_code in (401, 403)


# ===================================================================
# EnrichmentResult Schema Tests
# ===================================================================


class TestEnrichmentResultSchema:
    """Test EnrichmentResult model factory methods and serialization."""

    def test_success_result_fields(self) -> None:
        result = EnrichmentResult.success_result(
            provider_name="test",
            extracted={"key": "value"},
            raw={"full": "data"},
            enriched_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        assert result.success is True
        assert result.status == EnrichmentStatus.SUCCESS
        assert result.provider_name == "test"
        assert result.extracted == {"key": "value"}
        assert result.raw == {"full": "data"}
        assert result.enriched_at is not None
        assert result.error_message is None

    def test_failure_result_fields(self) -> None:
        result = EnrichmentResult.failure_result("test", "something broke")
        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert result.provider_name == "test"
        assert result.error_message == "something broke"
        assert result.extracted is None
        assert result.raw is None
        assert result.enriched_at is None

    def test_skipped_result_fields(self) -> None:
        result = EnrichmentResult.skipped_result("test", "not configured")
        assert result.success is False
        assert result.status == EnrichmentStatus.SKIPPED
        assert result.provider_name == "test"
        assert result.error_message == "not configured"
        assert result.extracted is None

    def test_success_result_serialization_roundtrip(self) -> None:
        """Success result can be serialized and deserialized."""
        original = EnrichmentResult.success_result(
            provider_name="virustotal",
            extracted={"malice": "Benign", "score": 10},
            raw={"data": {"attributes": {}}},
            enriched_at=datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC),
        )
        dumped = original.model_dump(mode="json")
        restored = EnrichmentResult.model_validate(dumped)
        assert restored.success is True
        assert restored.provider_name == "virustotal"
        assert restored.extracted == original.extracted
        assert restored.status == EnrichmentStatus.SUCCESS

    def test_failure_result_serialization_roundtrip(self) -> None:
        original = EnrichmentResult.failure_result("abuseipdb", "rate limited")
        dumped = original.model_dump(mode="json")
        restored = EnrichmentResult.model_validate(dumped)
        assert restored.success is False
        assert restored.error_message == "rate limited"
