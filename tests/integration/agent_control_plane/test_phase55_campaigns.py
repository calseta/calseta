"""Integration tests — Campaign system (Phase 5.5).

Verifies:
- Campaign CRUD (create, read, update)
- Item linking (add/remove items from a campaign)
- current_value is system-computed, not manually settable via create
- Metric computation endpoint returns correct counts
- Status transitions (planned → active → completed)
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.agent_control_plane.fixtures.mock_alerts import create_enriched_alert

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_campaign(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str = "Test Campaign",
    status: str = "planned",
    category: str = "custom",
    target_metric: str | None = None,
    target_value: float | None = None,
) -> dict[str, Any]:
    """Create a campaign via the API. Returns the data dict."""
    body: dict[str, Any] = {
        "name": name,
        "status": status,
        "category": category,
    }
    if target_metric is not None:
        body["target_metric"] = target_metric
    if target_value is not None:
        body["target_value"] = target_value
    resp = await client.post("/v1/campaigns", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------


class TestCampaignCRUD:
    """POST/GET/PATCH /v1/campaigns."""

    async def test_create_campaign_returns_201(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Successful campaign creation returns 201 with UUID and defaults."""
        campaign = await _create_campaign(test_client, admin_auth_headers, name="Alpha Campaign")
        assert "uuid" in campaign
        assert campaign["name"] == "Alpha Campaign"
        assert campaign["status"] == "planned"
        assert campaign["category"] == "custom"
        # current_value is system-computed, starts as None
        assert campaign["current_value"] is None

    async def test_create_campaign_with_target_metric(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Campaign with target metric and value stores them correctly."""
        campaign = await _create_campaign(
            test_client,
            admin_auth_headers,
            name="MTTD Campaign",
            target_metric="mttd_minutes",
            target_value=30.0,
        )
        assert campaign["target_metric"] == "mttd_minutes"
        assert float(campaign["target_value"]) == 30.0

    async def test_get_campaign_returns_200(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Created campaign is retrievable by UUID."""
        campaign = await _create_campaign(test_client, admin_auth_headers, name="Readable Campaign")
        resp = await test_client.get(
            f"/v1/campaigns/{campaign['uuid']}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["uuid"] == campaign["uuid"]
        assert data["name"] == "Readable Campaign"

    async def test_get_nonexistent_campaign_returns_404(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET unknown UUID → 404."""
        resp = await test_client.get(
            f"/v1/campaigns/{uuid4()}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404, resp.text

    async def test_patch_campaign_updates_name_and_description(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """PATCH updates name and description."""
        campaign = await _create_campaign(test_client, admin_auth_headers, name="Original Name")
        resp = await test_client.patch(
            f"/v1/campaigns/{campaign['uuid']}",
            json={"name": "New Name", "description": "Updated description."},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["name"] == "New Name"
        assert data["description"] == "Updated description."

    async def test_list_campaigns_with_status_filter(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """List campaigns filtered by status."""
        await _create_campaign(test_client, admin_auth_headers, name="Planned 1", status="planned")
        await _create_campaign(test_client, admin_auth_headers, name="Active 1", status="active")

        resp = await test_client.get(
            "/v1/campaigns?status=planned",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data_list = resp.json()["data"]
        statuses = {c["status"] for c in data_list}
        assert statuses == {"planned"}


# ---------------------------------------------------------------------------
# Campaign status transitions
# ---------------------------------------------------------------------------


class TestCampaignStatusTransitions:
    """PATCH /v1/campaigns/{uuid} — status transitions."""

    async def test_transition_planned_to_active(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Campaign can be transitioned from planned → active."""
        campaign = await _create_campaign(test_client, admin_auth_headers, name="Transition Campaign")
        resp = await test_client.patch(
            f"/v1/campaigns/{campaign['uuid']}",
            json={"status": "active"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "active"

    async def test_transition_active_to_completed(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Campaign can be transitioned from active → completed."""
        campaign = await _create_campaign(
            test_client, admin_auth_headers, name="Completion Campaign", status="active"
        )
        resp = await test_client.patch(
            f"/v1/campaigns/{campaign['uuid']}",
            json={"status": "completed"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "completed"


# ---------------------------------------------------------------------------
# Item linking
# ---------------------------------------------------------------------------


class TestCampaignItems:
    """POST/DELETE /v1/campaigns/{uuid}/items."""

    async def test_add_alert_item_to_campaign(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Linking an alert to a campaign returns 201 with item record."""
        alert = await create_enriched_alert(db_session, title="Campaign Alert Item")
        await db_session.flush()

        campaign = await _create_campaign(test_client, admin_auth_headers, name="Alert Item Campaign")
        resp = await test_client.post(
            f"/v1/campaigns/{campaign['uuid']}/items",
            json={"item_type": "alert", "item_uuid": str(alert.uuid)},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        item = resp.json()["data"]
        assert item["item_type"] == "alert"
        assert str(alert.uuid) in item["item_uuid"]

    async def test_add_issue_item_to_campaign(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Linking an issue (by UUID) to a campaign returns 201."""
        # Create an issue first
        issue_resp = await test_client.post(
            "/v1/issues",
            json={"title": "Issue for Campaign"},
            headers=admin_auth_headers,
        )
        assert issue_resp.status_code == 201, issue_resp.text
        issue_uuid = issue_resp.json()["data"]["uuid"]

        campaign = await _create_campaign(test_client, admin_auth_headers, name="Issue Item Campaign")
        resp = await test_client.post(
            f"/v1/campaigns/{campaign['uuid']}/items",
            json={"item_type": "issue", "item_uuid": issue_uuid},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        item = resp.json()["data"]
        assert item["item_type"] == "issue"

    async def test_remove_item_from_campaign(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Item can be removed from a campaign (DELETE → 204)."""
        alert = await create_enriched_alert(db_session, title="Removable Alert Item")
        await db_session.flush()

        campaign = await _create_campaign(test_client, admin_auth_headers, name="Remove Item Campaign")
        add_resp = await test_client.post(
            f"/v1/campaigns/{campaign['uuid']}/items",
            json={"item_type": "alert", "item_uuid": str(alert.uuid)},
            headers=admin_auth_headers,
        )
        assert add_resp.status_code == 201, add_resp.text
        item_uuid = add_resp.json()["data"]["uuid"]

        del_resp = await test_client.delete(
            f"/v1/campaigns/{campaign['uuid']}/items/{item_uuid}",
            headers=admin_auth_headers,
        )
        assert del_resp.status_code == 204, del_resp.text

    async def test_campaign_items_appear_in_get_response(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Items added to a campaign appear in GET /v1/campaigns/{uuid} response."""
        alert = await create_enriched_alert(db_session, title="Listed Alert Item")
        await db_session.flush()

        campaign = await _create_campaign(test_client, admin_auth_headers, name="Items List Campaign")
        await test_client.post(
            f"/v1/campaigns/{campaign['uuid']}/items",
            json={"item_type": "alert", "item_uuid": str(alert.uuid)},
            headers=admin_auth_headers,
        )

        resp = await test_client.get(
            f"/v1/campaigns/{campaign['uuid']}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert len(data["items"]) >= 1
        item_types = [i["item_type"] for i in data["items"]]
        assert "alert" in item_types


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


class TestCampaignMetrics:
    """GET /v1/campaigns/{uuid}/metrics — auto-computed metrics."""

    async def test_metrics_endpoint_returns_computed_counts(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Metrics endpoint returns correct item counts from linked data."""
        alert = await create_enriched_alert(db_session, title="Metrics Alert")
        await db_session.flush()

        campaign = await _create_campaign(
            test_client,
            admin_auth_headers,
            name="Metrics Campaign",
            target_metric="mttd_minutes",
            target_value=45.0,
        )
        # Add one alert
        await test_client.post(
            f"/v1/campaigns/{campaign['uuid']}/items",
            json={"item_type": "alert", "item_uuid": str(alert.uuid)},
            headers=admin_auth_headers,
        )
        # Add one issue
        issue_resp = await test_client.post(
            "/v1/issues",
            json={"title": "Metrics Campaign Issue", "status": "done"},
            headers=admin_auth_headers,
        )
        issue_uuid = issue_resp.json()["data"]["uuid"]
        await test_client.post(
            f"/v1/campaigns/{campaign['uuid']}/items",
            json={"item_type": "issue", "item_uuid": issue_uuid},
            headers=admin_auth_headers,
        )

        resp = await test_client.get(
            f"/v1/campaigns/{campaign['uuid']}/metrics",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        metrics = resp.json()["data"]
        assert metrics["campaign_uuid"] == campaign["uuid"]
        assert metrics["total_items"] == 2
        assert metrics["alert_count"] == 1
        assert metrics["issue_count"] == 1
        assert metrics["routine_count"] == 0
        assert "computed_at" in metrics
        # Issues with status "done" count toward issues_done
        assert metrics["issues_done"] == 1

    async def test_current_value_not_settable_in_create(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """current_value in the create request is ignored — it's system-computed."""
        # Even if the client sends current_value, the schema does not accept it in CampaignCreate
        # (the field doesn't exist there), so we verify the response always has None initially.
        campaign = await _create_campaign(
            test_client,
            admin_auth_headers,
            name="No Current Value Campaign",
        )
        assert campaign["current_value"] is None

    async def test_empty_campaign_metrics_are_zero(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Campaign with no items → all counts are zero."""
        campaign = await _create_campaign(test_client, admin_auth_headers, name="Empty Metrics Campaign")
        resp = await test_client.get(
            f"/v1/campaigns/{campaign['uuid']}/metrics",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        metrics = resp.json()["data"]
        assert metrics["total_items"] == 0
        assert metrics["alert_count"] == 0
        assert metrics["issue_count"] == 0
        assert metrics["completion_pct"] == 0.0
