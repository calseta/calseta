"""Integration tests for API key management — /v1/api-keys."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestAPIKeyCreate:
    async def test_create_returns_201(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/api-keys",
            json={"name": "test-key", "scopes": ["alerts:read"]},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201

    async def test_create_returns_full_key(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/api-keys",
            json={"name": "new-key", "scopes": ["alerts:read"]},
            headers=auth_header(api_key),
        )
        data = resp.json()["data"]
        assert "key" in data
        assert data["key"].startswith("cai_")
        assert len(data["key"]) > 8

    async def test_create_missing_name_returns_422(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/api-keys",
            json={"scopes": ["alerts:read"]},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 422


class TestAPIKeyList:
    async def test_list_returns_200(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get("/v1/api-keys", headers=auth_header(api_key))
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)


class TestAPIKeyGet:
    async def test_get_by_uuid(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        # Create a key first
        create_resp = await test_client.post(
            "/v1/api-keys",
            json={"name": "get-test", "scopes": ["alerts:read"]},
            headers=auth_header(api_key),
        )
        uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.get(
            f"/v1/api-keys/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        # Full key is NOT returned on GET
        assert "key" not in resp.json()["data"]

    async def test_get_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/api-keys/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestAPIKeyPatch:
    async def test_patch_scopes(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/api-keys",
            json={"name": "patch-test", "scopes": ["alerts:read"]},
            headers=auth_header(api_key),
        )
        uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.patch(
            f"/v1/api-keys/{uuid}",
            json={"scopes": ["alerts:read", "alerts:write"]},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert "alerts:write" in resp.json()["data"]["scopes"]

    async def test_deactivate(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/api-keys",
            json={"name": "deactivate-test", "scopes": ["alerts:read"]},
            headers=auth_header(api_key),
        )
        uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.patch(
            f"/v1/api-keys/{uuid}",
            json={"is_active": False},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False


class TestAPIKeyDelete:
    async def test_delete_returns_204(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/api-keys",
            json={"name": "delete-test", "scopes": ["alerts:read"]},
            headers=auth_header(api_key),
        )
        uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.delete(
            f"/v1/api-keys/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 204


class TestAPIKeyScope:
    async def test_non_admin_gets_403(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/api-keys",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403


class TestAPIKeyCanAuthenticate:
    async def test_created_key_can_authenticate(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """A newly created API key should be usable for authentication."""
        create_resp = await test_client.post(
            "/v1/api-keys",
            json={"name": "auth-test", "scopes": ["alerts:read"]},
            headers=auth_header(api_key),
        )
        new_key = create_resp.json()["data"]["key"]

        resp = await test_client.get(
            "/v1/alerts",
            headers=auth_header(new_key),
        )
        assert resp.status_code == 200
