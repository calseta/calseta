"""Integration tests for approval callback endpoints — /v1/approvals/callback."""

from __future__ import annotations

import json
from collections.abc import Generator
from unittest.mock import patch

import pytest
from httpx import AsyncClient


class TestSlackCallback:
    """POST /v1/workflow-approvals/callback/slack — no auth required.

    Tests run with SLACK_SIGNING_SECRET disabled so they are not gated behind
    signature validation (which is tested separately via the real secret path).
    """

    @pytest.fixture(autouse=True)
    def _disable_slack_signing(self) -> Generator[None, None, None]:
        """Disable Slack signature validation for these tests."""
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
        """Payload with no actions should return 200 ok."""
        resp = await test_client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": json.dumps({"actions": []})},
        )
        assert resp.status_code == 200

    async def test_no_auth_required(self, test_client: AsyncClient) -> None:
        """Callback endpoints must not require Authorization header."""
        resp = await test_client.post(
            "/v1/workflow-approvals/callback/slack",
            data={"payload": json.dumps({"actions": []})},
        )
        # Should not be 401 or 403 (no standard auth required — Slack signature only)
        assert resp.status_code not in (401, 403)


class TestTeamsCallback:
    """POST /v1/workflow-approvals/callback/teams — no auth required."""

    async def test_returns_info_message(self, test_client: AsyncClient) -> None:
        resp = await test_client.post("/v1/workflow-approvals/callback/teams")
        assert resp.status_code == 200
        body = resp.json()
        assert "message" in body
        assert "not supported" in body["message"].lower() or "REST API" in body["message"]

    async def test_no_auth_required(self, test_client: AsyncClient) -> None:
        resp = await test_client.post("/v1/workflow-approvals/callback/teams")
        assert resp.status_code not in (401, 403)
