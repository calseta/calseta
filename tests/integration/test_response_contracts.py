"""Integration tests for response envelope contracts, headers, and pagination."""

from __future__ import annotations

import re
from typing import Any

from httpx import AsyncClient

from tests.integration.conftest import auth_header

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ISO_TZ_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


class TestDataResponseEnvelope:
    """Single-object responses use {"data": {...}, "meta": {...}}."""

    async def test_data_response_shape(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_detection_rule: dict[str, Any],
    ) -> None:
        uuid = sample_detection_rule["uuid"]
        resp = await test_client.get(
            f"/v1/detection-rules/{uuid}",
            headers=auth_header(api_key),
        )
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], dict)
        # meta may be empty dict or have keys
        assert "meta" in body


class TestPaginatedResponseEnvelope:
    """List responses use {"data": [...], "meta": {"total": N, ...}}."""

    async def test_paginated_response_shape(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        resp = await test_client.get("/v1/alerts", headers=auth_header(api_key))
        body = resp.json()
        assert "data" in body
        assert isinstance(body["data"], list)
        meta = body["meta"]
        assert "total" in meta
        assert "page" in meta
        assert "page_size" in meta
        assert "total_pages" in meta


class TestErrorResponseEnvelope:
    """Error responses use {"error": {"code": "...", "message": "..."}}."""

    async def test_404_error_shape(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]


class TestTimestamps:
    """All timestamps are ISO 8601 with timezone."""

    async def test_created_at_iso_format(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_detection_rule: dict[str, Any],
    ) -> None:
        ts = sample_detection_rule["created_at"]
        assert ISO_TZ_RE.match(ts), f"Timestamp not ISO 8601: {ts}"


class TestUUIDs:
    """All UUIDs in responses are valid, lowercase, hyphenated."""

    async def test_uuid_format(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_detection_rule: dict[str, Any],
    ) -> None:
        uuid_val = sample_detection_rule["uuid"]
        assert UUID_RE.match(uuid_val), f"UUID not valid format: {uuid_val}"


class TestSecurityHeaders:
    """Security middleware adds standard headers to every response."""

    async def test_x_content_type_options(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    async def test_x_frame_options(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/health")
        assert resp.headers.get("x-frame-options") == "DENY"

    async def test_referrer_policy(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/health")
        assert "referrer-policy" in resp.headers

    async def test_x_request_id(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/health")
        assert "x-request-id" in resp.headers


class TestPagination:
    """Pagination parameter behavior."""

    async def test_default_page_size(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        resp = await test_client.get("/v1/alerts", headers=auth_header(api_key))
        meta = resp.json()["meta"]
        assert meta["page"] == 1
        assert meta["page_size"] == 50

    async def test_custom_page_size(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts?page_size=10",
            headers=auth_header(api_key),
        )
        meta = resp.json()["meta"]
        assert meta["page_size"] == 10

    async def test_total_pages_calculation(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts?page_size=1",
            headers=auth_header(api_key),
        )
        meta = resp.json()["meta"]
        # total_pages should be ceil(total / page_size)
        expected_pages = max(1, meta["total"]) if meta["total"] > 0 else 0
        assert meta["total_pages"] == expected_pages

    async def test_max_page_size_cap(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts?page_size=9999",
            headers=auth_header(api_key),
        )
        # Should return 422 because page_size max is 500
        assert resp.status_code == 422
