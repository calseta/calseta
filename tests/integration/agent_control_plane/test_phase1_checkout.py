"""
Integration tests for alert queue atomic checkout invariant.

Covers:
  GET  /v1/queue                             queue visibility rules
  POST /v1/queue/{uuid}/checkout             atomic checkout (happy path + 409)
  POST /v1/queue/{uuid}/release              release → re-checkout cycle
  PATCH /v1/assignments/{uuid}               update status and resolution

Key invariant: exactly one checkout succeeds when N concurrent requests race.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.db.session import get_db
from app.main import app
from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.agent_control_plane.fixtures.mock_alerts import create_enriched_alert
from tests.integration.conftest import auth_header


class TestAtomicCheckout:
    async def test_checkout_succeeds(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        enriched_alert: Alert,
    ) -> None:
        """Single checkout of an available enriched alert succeeds with 201."""
        alert_uuid = str(enriched_alert.uuid)
        resp = await test_client.post(
            f"/v1/queue/{alert_uuid}/checkout",
            headers=agent_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["status"] == "in_progress"
        assert "uuid" in data
        assert "checked_out_at" in data

    async def test_checkout_already_assigned_returns_409(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        enriched_alert: Alert,
        db_session: AsyncSession,
    ) -> None:
        """Checking out an alert that already has an active assignment returns 409 CONFLICT."""
        alert_uuid = str(enriched_alert.uuid)

        # First checkout — must succeed
        resp1 = await test_client.post(
            f"/v1/queue/{alert_uuid}/checkout",
            headers=agent_auth_headers,
        )
        assert resp1.status_code == 201, resp1.text

        # Create a second agent to attempt the same alert
        _, second_key = await _create_agent_with_key(db_session, name="second-checkout-agent")
        second_headers = auth_header(second_key)

        # Second checkout on the same alert — must fail
        resp2 = await test_client.post(
            f"/v1/queue/{alert_uuid}/checkout",
            headers=second_headers,
        )
        assert resp2.status_code == 409, resp2.text
        assert resp2.json()["error"]["code"] == "CONFLICT"

    async def test_concurrent_checkout_exactly_one_wins(
        self,
        db_session: AsyncSession,
        agent_auth_headers_list: list[dict[str, str]],
        enriched_alert: Alert,
    ) -> None:
        """
        10 concurrent checkout requests for the same alert → exactly 1 succeeds (201),
        9 fail (409). This is the atomic checkout invariant test.

        Each request runs through its own AsyncClient but shares the overridden DB
        session, so the INSERT WHERE NOT EXISTS serializes correctly.
        """
        alert_uuid = str(enriched_alert.uuid)

        # All 10 clients share the same overridden session so the atomic INSERT is visible
        async def _override_get_db() -> Any:
            yield db_session

        app.dependency_overrides[get_db] = _override_get_db

        async def attempt_checkout(headers: dict[str, str]) -> int:
            transport = ASGITransport(app=app)  # type: ignore[arg-type]
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post(
                    f"/v1/queue/{alert_uuid}/checkout",
                    headers=headers,
                )
                return r.status_code

        try:
            results = await asyncio.gather(
                *[attempt_checkout(h) for h in agent_auth_headers_list]
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        successes = [r for r in results if r == 201]
        conflicts = [r for r in results if r == 409]

        assert len(successes) == 1, (
            f"Expected exactly 1 successful checkout, got {len(successes)}. "
            f"All results: {results}"
        )
        assert len(conflicts) == 9, (
            f"Expected exactly 9 conflicts, got {len(conflicts)}. "
            f"All results: {results}"
        )

    async def test_release_allows_recheckout(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        enriched_alert: Alert,
        db_session: AsyncSession,
    ) -> None:
        """After releasing an assignment, the alert is available for checkout again."""
        alert_uuid = str(enriched_alert.uuid)

        # Checkout
        co_resp = await test_client.post(
            f"/v1/queue/{alert_uuid}/checkout",
            headers=agent_auth_headers,
        )
        assert co_resp.status_code == 201, co_resp.text

        # Release
        release_resp = await test_client.post(
            f"/v1/queue/{alert_uuid}/release",
            headers=agent_auth_headers,
        )
        assert release_resp.status_code == 200, release_resp.text
        assert release_resp.json()["data"]["status"] == "released"

        # A different agent can now check it out
        _, new_key = await _create_agent_with_key(db_session, name="recheckout-agent")
        recheckout_resp = await test_client.post(
            f"/v1/queue/{alert_uuid}/checkout",
            headers=auth_header(new_key),
        )
        assert recheckout_resp.status_code == 201, recheckout_resp.text

    async def test_queue_only_shows_enriched_alerts(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        """GET /v1/queue only returns alerts with enrichment_status='Enriched'."""
        # Create a Pending (not enriched) alert directly in DB
        pending_alert = Alert(
            title="Pending Alert - Not Enriched",
            severity="Medium",
            source_name="generic",
            status="Open",
            enrichment_status="Pending",
            occurred_at=datetime.now(UTC),
            tags=["test"],
            raw_payload={"title": "Pending Alert"},
        )
        db_session.add(pending_alert)

        # Create an Enriched alert
        enriched = await create_enriched_alert(
            db_session,
            title="Queue Visibility Test Alert",
            enrichment_status="Enriched",
        )
        await db_session.flush()

        resp = await test_client.get("/v1/queue", headers=agent_auth_headers)
        assert resp.status_code == 200, resp.text

        data = resp.json()["data"]
        alert_uuids = {a["uuid"] for a in data}

        # Enriched alert should appear
        assert str(enriched.uuid) in alert_uuids, (
            "Enriched alert should be visible in queue"
        )
        # Pending alert must not appear
        assert str(pending_alert.uuid) not in alert_uuids, (
            "Non-enriched alert must not appear in queue"
        )

    async def test_checkout_nonexistent_alert_returns_404(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
    ) -> None:
        """Checking out a UUID that doesn't exist returns 404."""
        resp = await test_client.post(
            "/v1/queue/00000000-0000-0000-0000-000000000000/checkout",
            headers=agent_auth_headers,
        )
        assert resp.status_code == 404

    async def test_update_assignment_status(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        enriched_alert: Alert,
    ) -> None:
        """PATCH /v1/assignments/{id} updates status and resolution fields."""
        alert_uuid = str(enriched_alert.uuid)

        # Checkout first
        co_resp = await test_client.post(
            f"/v1/queue/{alert_uuid}/checkout",
            headers=agent_auth_headers,
        )
        assert co_resp.status_code == 201, co_resp.text
        assignment_uuid = co_resp.json()["data"]["uuid"]

        # Update the assignment
        patch_resp = await test_client.patch(
            f"/v1/assignments/{assignment_uuid}",
            json={
                "status": "resolved",
                "resolution": "Confirmed true positive. Blocked at firewall.",
                "resolution_type": "true_positive",
            },
            headers=agent_auth_headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text
        data = patch_resp.json()["data"]
        assert data["status"] == "resolved"
        assert data["resolution"] == "Confirmed true positive. Blocked at firewall."
        assert data["resolution_type"] == "true_positive"

    async def test_get_my_assignments(
        self,
        test_client: AsyncClient,
        agent_auth_headers: dict[str, str],
        enriched_alert: Alert,
    ) -> None:
        """GET /v1/assignments/mine returns the agent's active assignments."""
        alert_uuid = str(enriched_alert.uuid)

        # Checkout to create an assignment
        await test_client.post(
            f"/v1/queue/{alert_uuid}/checkout",
            headers=agent_auth_headers,
        )

        resp = await test_client.get("/v1/assignments/mine", headers=agent_auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meta"]["total"] >= 1
        assert any(a["status"] == "in_progress" for a in body["data"])

    async def test_human_key_cannot_checkout(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
        enriched_alert: Alert,
    ) -> None:
        """Human API keys (cai_*) cannot checkout — queue endpoints require cak_* keys."""
        alert_uuid = str(enriched_alert.uuid)
        resp = await test_client.post(
            f"/v1/queue/{alert_uuid}/checkout",
            headers=admin_auth_headers,
        )
        # 403 FORBIDDEN — human keys cannot access the queue directly
        assert resp.status_code == 403
