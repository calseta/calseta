"""Integration tests for indicator field mappings — /v1/indicator-mappings."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestIndicatorMappingCRUD:
    async def test_create_201(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/indicator-mappings",
            json={
                "source_name": "generic",
                "field_path": "data.custom_ip",
                "indicator_type": "ip",
                "extraction_target": "raw_payload",
                "is_active": True,
                "description": "CRUD test mapping",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["field_path"] == "data.custom_ip"
        assert data["is_system"] is False

    async def test_list_200(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_indicator_mapping: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        # Should have at least the custom mapping + any system mappings
        assert resp.json()["meta"]["total"] >= 1

    async def test_filter_by_source(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_indicator_mapping: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings?source_name=generic",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_filter_by_system(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=true",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        for m in resp.json()["data"]:
            assert m["is_system"] is True

    async def test_get_by_uuid(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_indicator_mapping: dict[str, Any],
    ) -> None:
        uuid = sample_indicator_mapping["uuid"]
        resp = await test_client.get(
            f"/v1/indicator-mappings/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["uuid"] == uuid

    async def test_get_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_patch(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_indicator_mapping: dict[str, Any],
    ) -> None:
        uuid = sample_indicator_mapping["uuid"]
        resp = await test_client.patch(
            f"/v1/indicator-mappings/{uuid}",
            json={"is_active": False},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False

    async def test_delete_204(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_indicator_mapping: dict[str, Any],
    ) -> None:
        uuid = sample_indicator_mapping["uuid"]
        resp = await test_client.delete(
            f"/v1/indicator-mappings/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 204


class TestSystemMappingProtection:
    async def test_system_mapping_cannot_be_deleted(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        """System mappings should return 422 on delete attempts."""
        # Find a system mapping
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=true",
            headers=auth_header(api_key),
        )
        data = resp.json()["data"]
        if not data:
            return  # Skip if no system mappings exist
        uuid = data[0]["uuid"]

        resp = await test_client.delete(
            f"/v1/indicator-mappings/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 422

    async def test_system_mapping_field_path_readonly(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        """System mappings should reject field_path changes."""
        resp = await test_client.get(
            "/v1/indicator-mappings?is_system=true",
            headers=auth_header(api_key),
        )
        data = resp.json()["data"]
        if not data:
            return  # Skip if no system mappings exist
        uuid = data[0]["uuid"]

        resp = await test_client.patch(
            f"/v1/indicator-mappings/{uuid}",
            json={"field_path": "new.path"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 422


class TestIndicatorMappingScope:
    async def test_admin_required(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/indicator-mappings",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403
