"""Integration tests for global workflow runs — /v1/workflow-runs."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestGlobalWorkflowRuns:
    """GET /v1/workflow-runs — global run history across all workflows."""

    async def test_list_200(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/workflow-runs",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)
        assert "meta" in resp.json()

    async def test_filter_by_status(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/workflow-runs?status=queued",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_filter_by_workflow_uuid(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        uuid = sample_workflow["uuid"]
        resp = await test_client.get(
            f"/v1/workflow-runs?workflow_uuid={uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_invalid_workflow_uuid_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/workflow-runs?workflow_uuid=00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404
