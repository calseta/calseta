"""Integration tests for workflow approvals — /v1/workflow-approvals."""

from __future__ import annotations

from httpx import AsyncClient

from tests.integration.conftest import auth_header


class TestWorkflowApprovalList:
    async def test_list_empty(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/workflow-approvals",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    async def test_filter_by_status(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/workflow-approvals?status=pending",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200


class TestWorkflowApprovalGet:
    async def test_get_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/workflow-approvals/00000000-0000-0000-0000-000000000000",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestWorkflowApprovalActions:
    async def test_approve_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/workflow-approvals/00000000-0000-0000-0000-000000000000/approve",
            json={"responder_id": "test"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_reject_404(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/workflow-approvals/00000000-0000-0000-0000-000000000000/reject",
            json={"responder_id": "test"},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404


class TestWorkflowApprovalScope:
    async def test_workflows_execute_required(
        self,
        test_client: AsyncClient,
        alerts_read_key: str,
    ) -> None:
        resp = await test_client.get(
            "/v1/workflow-approvals",
            headers=auth_header(alerts_read_key),
        )
        assert resp.status_code == 403
