"""Integration tests for source integration management — /v1/sources."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestSourceCRUD:
    async def test_create_201(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/sources",
            json={
                "source_name": "generic",
                "display_name": "CRUD Generic Source",
                "is_active": True,
                "auth_type": None,
                "auth_config": None,
                "documentation": "test",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["source_name"] == "generic"

    async def test_create_invalid_plugin_400(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/sources",
            json={
                "source_name": "nonexistent_plugin",
                "display_name": "Bad Source",
                "is_active": True,
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 400

    async def test_list_200(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_source: dict[str, Any],
    ) -> None:
        resp = await test_client.get("/v1/sources", headers=auth_header(api_key))
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    async def test_get_by_uuid(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_source: dict[str, Any],
    ) -> None:
        uuid = sample_source["uuid"]
        resp = await test_client.get(
            f"/v1/sources/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["uuid"] == uuid

    async def test_get_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/sources/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_patch(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_source: dict[str, Any],
    ) -> None:
        uuid = sample_source["uuid"]
        resp = await test_client.patch(
            f"/v1/sources/{uuid}",
            json={"display_name": "Updated Source Name"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["display_name"] == "Updated Source Name"

    async def test_delete_204(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_source: dict[str, Any],
    ) -> None:
        uuid = sample_source["uuid"]
        resp = await test_client.delete(
            f"/v1/sources/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 204


class TestSourceScope:
    async def test_alerts_read_can_list(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/sources",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 200

    async def test_alerts_read_cannot_create(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/sources",
            json={
                "source_name": "generic",
                "display_name": "Forbidden Source",
                "is_active": True,
            },
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_non_admin_cannot_delete(
        self,
        test_client: AsyncClient,
        alerts_write_key: str,
        sample_source: dict[str, Any],
    ) -> None:
        uuid = sample_source["uuid"]
        resp = await test_client.delete(
            f"/v1/sources/{uuid}",
            headers=auth_header(alerts_write_key),
        )
        assert resp.status_code == 403
