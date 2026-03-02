"""Integration tests for agent registration management — /v1/agents."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestAgentCRUD:
    async def test_create_201(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/agents",
            json={
                "name": "crud-test-agent",
                "description": "Test",
                "endpoint_url": "http://localhost:9999/hook",
                "auth_header_name": None,
                "auth_header_value": None,
                "trigger_on_sources": [],
                "trigger_on_severities": [],
                "is_active": True,
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "crud-test-agent"
        assert "uuid" in data

    async def test_list_200(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        resp = await test_client.get("/v1/agents", headers=auth_header(api_key))
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    async def test_get_by_uuid(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        uuid = sample_agent["uuid"]
        resp = await test_client.get(
            f"/v1/agents/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["uuid"] == uuid

    async def test_get_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/agents/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_auth_header_value_not_returned(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        """auth_header_value should never appear in responses."""
        uuid = sample_agent["uuid"]
        resp = await test_client.get(
            f"/v1/agents/{uuid}",
            headers=auth_header(api_key),
        )
        data = resp.json()["data"]
        assert "auth_header_value" not in data

    async def test_patch(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        uuid = sample_agent["uuid"]
        resp = await test_client.patch(
            f"/v1/agents/{uuid}",
            json={"description": "Updated description"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["description"] == "Updated description"

    async def test_patch_trigger_filters(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        uuid = sample_agent["uuid"]
        resp = await test_client.patch(
            f"/v1/agents/{uuid}",
            json={"trigger_on_severities": ["Critical"]},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["trigger_on_severities"] == ["Critical"]

    async def test_delete_204(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        uuid = sample_agent["uuid"]
        resp = await test_client.delete(
            f"/v1/agents/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 204


class TestAgentTest:
    async def test_test_webhook_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/agents/00000000-0000-0000-0000-000000000000/test",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestAgentScope:
    async def test_agents_read_can_list(
        self,
        test_client: AsyncClient,
        agents_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/agents",
            headers=auth_header(agents_read_key),
        )
        assert resp.status_code == 200

    async def test_agents_read_cannot_create(
        self,
        test_client: AsyncClient,
        agents_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/agents",
            json={
                "name": "forbidden",
                "endpoint_url": "http://localhost/",
                "trigger_on_sources": [],
                "trigger_on_severities": [],
                "is_active": True,
            },
            headers=auth_header(agents_read_key),
        )
        assert resp.status_code == 403

    async def test_alerts_read_cannot_access(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/agents",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403
