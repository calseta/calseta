"""Integration tests for workflow management — /v1/workflows."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from httpx import AsyncClient

from tests.integration.conftest import VALID_WORKFLOW_CODE, auth_header


class TestWorkflowCRUD:
    async def test_create_201(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "CRUD Test Workflow",
                "workflow_type": "indicator",
                "indicator_types": ["ip"],
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "timeout_seconds": 30,
                "retry_count": 1,
                "is_active": True,
                "tags": ["test"],
                "time_saved_minutes": 5,
                "approval_mode": "never",
                "approval_channel": None,
                "approval_timeout_seconds": 300,
                "risk_level": "low",
                "documentation": "test",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "CRUD Test Workflow"
        assert "uuid" in data
        assert "code" in data

    async def test_create_invalid_code_400(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Bad Code Workflow",
                "workflow_type": "indicator",
                "indicator_types": ["ip"],
                "code": "import os\nos.system('rm -rf /')",
                "state": "active",
                "timeout_seconds": 30,
                "retry_count": 1,
                "is_active": True,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "WORKFLOW_CODE_INVALID"

    async def test_list_200(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/workflows",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    async def test_list_filter_by_state(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/workflows?state=active",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_list_filter_by_type(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/workflows?workflow_type=indicator",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_list_excludes_code(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        resp = await test_client.get(
            "/v1/workflows",
            headers=auth_header(api_key),
        )
        summaries = resp.json()["data"]
        for s in summaries:
            assert "code" not in s

    async def test_get_by_uuid(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        uuid = sample_workflow["uuid"]
        resp = await test_client.get(
            f"/v1/workflows/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["uuid"] == uuid
        assert "code" in data

    async def test_get_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/workflows/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_patch(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        uuid = sample_workflow["uuid"]
        resp = await test_client.patch(
            f"/v1/workflows/{uuid}",
            json={"name": "Updated Workflow Name"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated Workflow Name"

    async def test_patch_code_validates(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        uuid = sample_workflow["uuid"]
        resp = await test_client.patch(
            f"/v1/workflows/{uuid}",
            json={"code": "import os"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 400

    async def test_patch_valid_code(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        uuid = sample_workflow["uuid"]
        new_code = "async def run(ctx):\n    return ctx.success('updated')\n"
        resp = await test_client.patch(
            f"/v1/workflows/{uuid}",
            json={"code": new_code},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200

    async def test_delete_204(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        uuid = sample_workflow["uuid"]
        resp = await test_client.delete(
            f"/v1/workflows/{uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 204

    async def test_delete_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.delete(
            "/v1/workflows/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestWorkflowExecute:
    async def test_execute_202(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
        mock_queue: AsyncMock,
    ) -> None:
        uuid = sample_workflow["uuid"]
        resp = await test_client.post(
            f"/v1/workflows/{uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 202

    async def test_execute_enqueues_task(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
        mock_queue: AsyncMock,
    ) -> None:
        uuid = sample_workflow["uuid"]
        await test_client.post(
            f"/v1/workflows/{uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers=auth_header(api_key),
        )
        mock_queue.enqueue.assert_called()

    async def test_execute_inactive_400(
        self,
        test_client: AsyncClient,
        api_key: str,
        mock_queue: AsyncMock,
    ) -> None:
        # Create an inactive workflow
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Inactive Workflow",
                "workflow_type": "indicator",
                "indicator_types": ["ip"],
                "code": VALID_WORKFLOW_CODE,
                "state": "draft",
                "timeout_seconds": 30,
                "retry_count": 1,
                "is_active": False,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers=auth_header(api_key),
        )
        uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 400

    async def test_execute_404(
        self,
        test_client: AsyncClient,
        api_key: str,
        mock_queue: AsyncMock,
    ) -> None:
        resp = await test_client.post(
            "/v1/workflows/00000000-0000-0000-0000-000000000000/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_execute_scope_check(
        self,
        test_client: AsyncClient,
        workflows_read_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        uuid = sample_workflow["uuid"]
        resp = await test_client.post(
            f"/v1/workflows/{uuid}/execute",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
            },
            headers=auth_header(workflows_read_key),
        )
        assert resp.status_code == 403


class TestWorkflowTest:
    async def test_test_200(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        uuid = sample_workflow["uuid"]
        resp = await test_client.post(
            f"/v1/workflows/{uuid}/test",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                "mock_http_responses": {"status": "ok"},
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "success" in data
        assert "message" in data

    async def test_test_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/workflows/00000000-0000-0000-0000-000000000000/test",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                "mock_http_responses": {},
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_test_inactive_400(
        self,
        test_client: AsyncClient,
        api_key: str,
    ) -> None:
        create_resp = await test_client.post(
            "/v1/workflows",
            json={
                "name": "Inactive Test Workflow",
                "workflow_type": "indicator",
                "indicator_types": ["ip"],
                "code": VALID_WORKFLOW_CODE,
                "state": "active",
                "timeout_seconds": 30,
                "retry_count": 1,
                "is_active": False,
                "tags": [],
                "approval_mode": "never",
                "approval_timeout_seconds": 300,
                "risk_level": "low",
            },
            headers=auth_header(api_key),
        )
        uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.post(
            f"/v1/workflows/{uuid}/test",
            json={
                "indicator_type": "ip",
                "indicator_value": "1.2.3.4",
                "mock_http_responses": {},
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 400


class TestWorkflowVersions:
    async def test_list_versions(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        uuid = sample_workflow["uuid"]
        resp = await test_client.get(
            f"/v1/workflows/{uuid}/versions",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_versions_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/workflows/00000000-0000-0000-0000-000000000000/versions",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestWorkflowRuns:
    async def test_list_runs_per_workflow(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_workflow: dict[str, Any],
    ) -> None:
        uuid = sample_workflow["uuid"]
        resp = await test_client.get(
            f"/v1/workflows/{uuid}/runs",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert "meta" in body

    async def test_runs_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/workflows/00000000-0000-0000-0000-000000000000/runs",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404
