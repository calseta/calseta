"""Integration tests for alert management — /v1/alerts."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestAlertList:
    async def test_list_empty(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get("/v1/alerts", headers=auth_header(api_key))
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_list_with_data(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        resp = await test_client.get("/v1/alerts", headers=auth_header(api_key))
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    async def test_filter_by_status(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts?status=Open",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_filter_by_severity(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts?severity=High",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        for alert in resp.json()["data"]:
            assert alert["severity"] == "High"

    async def test_filter_by_source(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts?source_name=generic",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200


class TestAlertDetail:
    async def test_get_detail(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.get(
            f"/v1/alerts/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["uuid"] == uuid

    async def test_get_detail_has_metadata(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.get(
            f"/v1/alerts/{uuid}",
            headers=auth_header(api_key),
        )
        meta = resp.json()["meta"]
        assert "generated_at" in meta
        assert "alert_source" in meta
        assert "indicator_count" in meta
        assert "enrichment" in meta
        assert "detection_rule_matched" in meta
        assert "context_documents_applied" in meta

    async def test_get_detail_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestAlertPatch:
    async def test_patch_status(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.patch(
            f"/v1/alerts/{uuid}",
            json={"status": "Open"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "Open"

    async def test_patch_severity(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.patch(
            f"/v1/alerts/{uuid}",
            json={"severity": "Critical"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["severity"] == "Critical"

    async def test_patch_tags(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.patch(
            f"/v1/alerts/{uuid}",
            json={"tags": ["phishing", "urgent"]},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert "phishing" in resp.json()["data"]["tags"]

    async def test_close_requires_classification(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.patch(
            f"/v1/alerts/{uuid}",
            json={"status": "Closed"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 422

    async def test_close_with_classification(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.patch(
            f"/v1/alerts/{uuid}",
            json={
                "status": "Closed",
                "close_classification": "True Positive - Suspicious Activity",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "Closed"

    async def test_patch_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.patch(
            "/v1/alerts/00000000-0000-0000-0000-000000000000",
            json={"status": "Open"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestAlertDelete:
    async def test_delete_204(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.delete(
            f"/v1/alerts/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 204


class TestAlertFindings:
    async def test_add_finding_201(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.post(
            f"/v1/alerts/{uuid}/findings",
            json={
                "agent_name": "test-agent",
                "summary": "IP matches known C2",
                "confidence": "high",
                "recommended_action": "Block",
                "evidence": {"source": "test"},
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["agent_name"] == "test-agent"
        assert "id" in data

    async def test_list_findings(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        # Add a finding first
        await test_client.post(
            f"/v1/alerts/{uuid}/findings",
            json={
                "agent_name": "test-agent",
                "summary": "Finding for list test",
            },
            headers=auth_header(api_key),
        )

        resp = await test_client.get(
            f"/v1/alerts/{uuid}/findings",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)
        assert len(resp.json()["data"]) >= 1

    async def test_finding_on_nonexistent_alert_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/alerts/00000000-0000-0000-0000-000000000000/findings",
            json={"agent_name": "test", "summary": "test"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestAlertContext:
    async def test_get_context(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
        sample_context_document: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.get(
            f"/v1/alerts/{uuid}/context",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_context_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts/00000000-0000-0000-0000-000000000000/context",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestAlertIndicators:
    async def test_list_indicators(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.get(
            f"/v1/alerts/{uuid}/indicators",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_add_indicators_201(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
        mock_queue: AsyncMock,
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.post(
            f"/v1/alerts/{uuid}/indicators",
            json={
                "indicators": [
                    {"type": "ip", "value": "10.0.0.1"},
                    {"type": "domain", "value": "evil.com"},
                ]
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["added_count"] == 2
        assert data["enrich_requested"] is True

    async def test_add_indicators_without_enrich(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
        mock_queue: AsyncMock,
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.post(
            f"/v1/alerts/{uuid}/indicators?enrich=false",
            json={"indicators": [{"type": "ip", "value": "10.0.0.2"}]},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["enrich_requested"] is False


class TestAlertActivity:
    async def test_list_activity(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.get(
            f"/v1/alerts/{uuid}/activity",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert "meta" in body

    async def test_activity_has_ingested_event(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.get(
            f"/v1/alerts/{uuid}/activity",
            headers=auth_header(api_key),
        )
        events = resp.json()["data"]
        event_types = [e["event_type"] for e in events]
        assert "alert_ingested" in event_types

    async def test_activity_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts/00000000-0000-0000-0000-000000000000/activity",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestAlertRelationshipGraph:
    async def test_relationship_graph(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.get(
            f"/v1/alerts/{uuid}/relationship-graph",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "alert" in data
        assert "indicators" in data
        assert data["alert"]["uuid"] == uuid

    async def test_relationship_graph_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts/00000000-0000-0000-0000-000000000000/relationship-graph",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestAlertTriggerAgents:
    async def test_trigger_agents_202(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_alert: dict[str, Any],
        mock_queue: AsyncMock,
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.post(
            f"/v1/alerts/{uuid}/trigger-agents",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 202
        data = resp.json()["data"]
        assert "queued_agent_count" in data
        assert "agent_names" in data

    async def test_trigger_agents_scope_check(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
        sample_alert: dict[str, Any],
    ) -> None:
        uuid = sample_alert["uuid"]
        resp = await test_client.post(
            f"/v1/alerts/{uuid}/trigger-agents",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403

    async def test_trigger_agents_404(
        self,
        test_client: AsyncClient,
        api_key: str,
        mock_queue: AsyncMock,
    ) -> None:
        resp = await test_client.post(
            "/v1/alerts/00000000-0000-0000-0000-000000000000/trigger-agents",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404
