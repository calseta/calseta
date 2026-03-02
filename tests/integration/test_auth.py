"""Integration tests for authentication and authorization enforcement."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestUnauthorized:
    """401 enforcement — missing or invalid credentials."""

    async def test_no_auth_header(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/v1/alerts")
        assert resp.status_code == 401

    async def test_invalid_bearer_format(self, test_client: AsyncClient) -> None:
        resp = await test_client.get(
            "/v1/alerts",
            headers={"Authorization": "Token invalid"},
        )
        assert resp.status_code == 401

    async def test_wrong_api_key(self, test_client: AsyncClient) -> None:
        resp = await test_client.get(
            "/v1/alerts",
            headers=auth_header("cai_thiskeyisnotinthedatabaseatall12"),
        )
        assert resp.status_code == 401

    async def test_401_error_shape(self, test_client: AsyncClient) -> None:
        resp = await test_client.get("/v1/alerts")
        body = resp.json()
        assert "error" in body
        assert "code" in body["error"]
        assert "message" in body["error"]


class TestForbidden:
    """403 enforcement — valid key, wrong scope."""

    async def test_alerts_read_cannot_write(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.patch(
            "/v1/alerts/00000000-0000-0000-0000-000000000000",
            json={"status": "Open"},
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_alerts_read_cannot_access_api_keys(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/api-keys",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_workflows_read_cannot_execute(
        self,
        test_client: AsyncClient,
        workflows_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/workflows/00000000-0000-0000-0000-000000000000/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                "trigger_source": "human",
            },
            headers=auth_header(workflows_read_key),
        )
        assert resp.status_code == 403

    async def test_agents_read_cannot_write(
        self,
        test_client: AsyncClient,
        agents_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/agents",
            json={
                "name": "forbidden-agent",
                "endpoint_url": "http://localhost/",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
                "is_active": True,
            },
            headers=auth_header(agents_read_key),
        )
        assert resp.status_code == 403

    async def test_403_error_shape(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/api-keys",
            headers=auth_header(alerts_read_key),
        )
        body = resp.json()
        assert resp.status_code == 403
        assert "error" in body
        assert body["error"]["code"] == "FORBIDDEN"


class TestAdminBypass:
    """Admin scope passes all scope checks."""

    async def test_admin_can_read_alerts(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        resp = await test_client.get("/v1/alerts", headers=auth_header(api_key))
        assert resp.status_code == 200

    async def test_admin_can_list_api_keys(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        resp = await test_client.get("/v1/api-keys", headers=auth_header(api_key))
        assert resp.status_code == 200
