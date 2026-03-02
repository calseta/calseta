"""Integration tests for metrics endpoints — /v1/metrics."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestAlertMetrics:
    async def test_alert_metrics_200(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/metrics/alerts",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_alert_metrics_structure(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/metrics/alerts",
            headers=auth_header(api_key),
        )
        data = resp.json()["data"]
        assert "total_alerts" in data
        assert "alerts_by_status" in data
        assert "alerts_by_severity" in data
        assert "false_positive_rate" in data

    async def test_alert_metrics_time_window(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/metrics/alerts?from_time=2026-01-01T00:00:00Z&to_time=2026-03-01T00:00:00Z",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200


class TestMetricsSummary:
    async def test_summary_200(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/metrics/summary",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_summary_structure(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/metrics/summary",
            headers=auth_header(api_key),
        )
        data = resp.json()["data"]
        assert "period" in data
        assert "alerts" in data
        assert "workflows" in data
        assert "approvals" in data


class TestWorkflowMetrics:
    async def test_workflow_metrics_200(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/metrics/workflows",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_workflow_metrics_structure(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/metrics/workflows",
            headers=auth_header(api_key),
        )
        data = resp.json()["data"]
        assert "total_configured" in data
        assert "workflow_run_count" in data
        assert "workflow_success_rate" in data


class TestMetricsScope:
    async def test_alerts_read_for_alert_metrics(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/metrics/alerts",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 200

    async def test_workflows_read_for_workflow_metrics(
        self,
        test_client: AsyncClient,
        workflows_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/metrics/workflows",
            headers=auth_header(workflows_read_key),
        )
        assert resp.status_code == 200

    async def test_enrichments_read_cannot_access_alert_metrics(
        self,
        test_client: AsyncClient,
        enrichments_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/metrics/alerts",
            headers=auth_header(enrichments_read_key),
        )
        assert resp.status_code == 403
