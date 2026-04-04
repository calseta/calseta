"""Integration tests for enrichment endpoints — /v1/enrichments."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestOnDemandEnrichment:
    """POST /v1/enrichments — synchronous on-demand enrichment."""

    async def test_enrich_returns_200(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/enrichments",
            json={"type": "ip", "value": "8.8.8.8"},
            headers=auth_header(enrichments_read_key),
        )
        assert resp.status_code == 200

    async def test_enrich_echoes_type_and_value(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/enrichments",
            json={"type": "domain", "value": "example.com"},
            headers=auth_header(enrichments_read_key),
        )
        data = resp.json()["data"]
        assert data["type"] == "domain"
        assert data["value"] == "example.com"

    async def test_enrich_has_results_dict(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/enrichments",
            json={"type": "ip", "value": "1.2.3.4"},
            headers=auth_header(enrichments_read_key),
        )
        data = resp.json()["data"]
        assert "results" in data
        assert isinstance(data["results"], dict)

    async def test_enrich_invalid_type_422(
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


class TestProviderList:
    """GET /v1/enrichment-providers."""

    async def test_list_providers_200(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/enrichment-providers",
            headers=auth_header(enrichments_read_key),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_provider_structure(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/enrichment-providers",
            headers=auth_header(enrichments_read_key),
        )
        providers = resp.json()["data"]
        if providers:
            p = providers[0]
            assert "provider_name" in p
            assert "display_name" in p
            assert "supported_indicator_types" in p
            assert "is_configured" in p
            assert "default_cache_ttl_seconds" in p


class TestEnrichmentScope:
    async def test_enrichments_read_required(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/enrichments",
            json={"type": "ip", "value": "1.2.3.4"},
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403
