"""Integration tests for detection rule management — /v1/detection-rules."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestDetectionRuleCRUD:
    async def test_create_201(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/detection-rules",
            json={
                "name": "CRUD Test Rule",
                "source_name": "generic",
                "is_active": True,
                "mitre_tactics": ["Execution"],
                "mitre_techniques": ["T1059"],
                "mitre_subtechniques": [],
                "data_sources": [],
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "CRUD Test Rule"
        assert "uuid" in data

    async def test_created_by_auto_populated(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/detection-rules",
            json={
                "name": "Auto Created By Rule",
                "is_active": True,
                "mitre_tactics": [],
                "mitre_techniques": [],
                "mitre_subtechniques": [],
                "data_sources": [],
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["created_by"] is not None
        assert data["created_by"].startswith("cai_")

    async def test_list_200(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_detection_rule: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/detection-rules",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    async def test_filter_by_source(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_detection_rule: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/detection-rules?source_name=generic",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_filter_by_active(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_detection_rule: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/detection-rules?is_active=true",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_get_by_uuid(
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
        assert resp.status_code == 200
        assert resp.json()["data"]["uuid"] == uuid

    async def test_get_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/detection-rules/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_patch(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_detection_rule: dict[str, Any],
    ) -> None:
        uuid = sample_detection_rule["uuid"]
        resp = await test_client.patch(
            f"/v1/detection-rules/{uuid}",
            json={"name": "Updated Rule Name"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated Rule Name"

    async def test_delete_204(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_detection_rule: dict[str, Any],
    ) -> None:
        uuid = sample_detection_rule["uuid"]
        resp = await test_client.delete(
            f"/v1/detection-rules/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 204


class TestDetectionRuleScope:
    async def test_alerts_read_can_list(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/detection-rules",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 200

    async def test_alerts_read_cannot_create(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.post(
            "/v1/detection-rules",
            json={
                "name": "Forbidden Rule",
                "is_active": True,
                "mitre_tactics": [],
                "mitre_techniques": [],
                "mitre_subtechniques": [],
                "data_sources": [],
            },
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_alerts_write_cannot_create(
        self,
        test_client: AsyncClient,
        alerts_write_key: str,
    ) -> None:
        """Detection rule write requires admin, not just alerts:write."""
        resp = await test_client.post(
            "/v1/detection-rules",
            json={
                "name": "Forbidden Rule",
                "is_active": True,
                "mitre_tactics": [],
                "mitre_techniques": [],
                "mitre_subtechniques": [],
                "data_sources": [],
            },
            headers=auth_header(alerts_write_key),
        )
        assert resp.status_code == 403

    async def test_alerts_read_can_get(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
        sample_detection_rule: dict[str, Any],
    ) -> None:
        uuid = sample_detection_rule["uuid"]
        resp = await test_client.get(
            f"/v1/detection-rules/{uuid}",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 200
