"""Integration tests — Phase 6 pre-flight cleanup.

Verifies that:
- Approval endpoints are consolidated under /v1/workflow-approvals
- Old /v1/approvals routes are gone (404)
- Slack callback works without signing secret
- Teams callback returns expected informational message
"""

from __future__ import annotations

import json
from collections.abc import Generator
from unittest.mock import patch

import pytest
from httpx import AsyncClient


class TestApprovalRouteConsolidation:
    """All approval endpoints live under /v1/workflow-approvals."""

    def test_old_approvals_prefix_not_registered(self) -> None:
        """The old /v1/approvals prefix must not exist as a registered API route."""
        from starlette.routing import Route

        from app.main import app

        api_paths = [
            route.path
            for route in app.routes
            if isinstance(route, Route) and hasattr(route, "path")
        ]
        # All approval routes must use the /v1/workflow-approvals prefix
        old_paths = [p for p in api_paths if p.startswith("/v1/approvals")]
        assert old_paths == [], f"Found old /v1/approvals routes still registered: {old_paths}"

    async def test_workflow_approvals_list_exists(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        """GET /v1/workflow-approvals returns 200 (empty list)."""
        resp = await test_client.get(
            "/v1/workflow-approvals",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    async def test_slack_callback_path(self, test_client: AsyncClient) -> None:
        """POST /v1/workflow-approvals/callback/slack exists."""
        with patch("app.api.v1.workflow_approvals.settings") as mock_settings:
            mock_settings.SLACK_SIGNING_SECRET = None
            resp = await test_client.post(
                "/v1/workflow-approvals/callback/slack",
                data={"payload": json.dumps({"actions": []})},
            )
        assert resp.status_code == 200

    async def test_teams_callback_path(self, test_client: AsyncClient) -> None:
        """POST /v1/workflow-approvals/callback/teams exists."""
        resp = await test_client.post("/v1/workflow-approvals/callback/teams")
        assert resp.status_code == 200

    def test_decide_route_registered(self) -> None:
        """GET /v1/workflow-approvals/{uuid}/decide must be registered."""
        from starlette.routing import Route

        from app.main import app

        api_paths = [
            route.path
            for route in app.routes
            if isinstance(route, Route) and hasattr(route, "path")
        ]
        decide_paths = [p for p in api_paths if "/decide" in p]
        assert any("/workflow-approvals/" in p for p in decide_paths), (
            "GET /v1/workflow-approvals/{uuid}/decide route not found"
        )


class TestSlackCallbackConsolidated:
    """Slack callback under consolidated route."""

    @pytest.fixture(autouse=True)
    def _disable_slack_signing(self) -> Generator[None, None, None]:
        with patch("app.api.v1.workflow_approvals.settings") as mock_settings:
            mock_settings.SLACK_SIGNING_SECRET = None
            yield

    async def test_missing_payload_400(self, test_client: AsyncClient) -> None:
        resp = await test_client.post(
            "/v1/workflow-approvals/callback/slack",
            data={},
        )
        assert resp.status_code == 400

    async def test_invalid_json_400(self, test_client: AsyncClient) -> None:
        resp = await test_client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": "not-valid-json{{{"},
        )
        assert resp.status_code == 400

    async def test_no_actions_returns_ok(self, test_client: AsyncClient) -> None:
        resp = await test_client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": json.dumps({"actions": []})},
        )
        assert resp.status_code == 200

    async def test_no_auth_required(self, test_client: AsyncClient) -> None:
        resp = await test_client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": json.dumps({"actions": []})},
        )
        assert resp.status_code not in (401, 403)


class TestTeamsCallbackConsolidated:
    """Teams callback under consolidated route."""

    async def test_returns_info_message(self, test_client: AsyncClient) -> None:
        resp = await test_client.post("/v1/workflow-approvals/callback/teams")
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body

    async def test_no_auth_required(self, test_client: AsyncClient) -> None:
        resp = await test_client.post("/v1/workflow-approvals/callback/teams")
        assert resp.status_code not in (401, 403)
