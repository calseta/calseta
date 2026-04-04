"""Integration tests for campaigns and topology — /v1/campaigns, /v1/topology."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from httpx import AsyncClient

from tests.integration.conftest import auth_header


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_campaign(
    test_client: AsyncClient,
    api_key: str,
    name: str = "Test Campaign",
    status: str = "planned",
) -> dict[str, Any]:
    resp = await test_client.post(
        "/v1/campaigns",
        json={
            "name": name,
            "description": "Integration test campaign",
            "status": status,
            "category": "threat_hunting",
        },
        headers=auth_header(api_key),
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def _create_issue(
    test_client: AsyncClient,
    api_key: str,
    title: str = "Campaign Issue",
) -> dict[str, Any]:
    resp = await test_client.post(
        "/v1/issues",
        json={"title": title},
        headers=auth_header(api_key),
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


class TestCreateCampaign:
    async def test_create_campaign(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/campaigns",
            json={
                "name": "Q2 Threat Hunting",
                "description": "Hunting for lateral movement patterns",
                "status": "planned",
                "category": "threat_hunting",
                "owner_operator": "security-team",
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Q2 Threat Hunting"
        assert "uuid" in data
        assert data["status"] == "planned"
        assert data["category"] == "threat_hunting"
        assert data["owner_operator"] == "security-team"
        assert isinstance(data["items"], list)


class TestListCampaigns:
    async def test_list_campaigns_empty(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get("/v1/campaigns", headers=auth_header(api_key))
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert "total" in body["meta"]


class TestGetCampaign:
    async def test_get_campaign_not_found(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        random_uuid = str(uuid4())
        resp = await test_client.get(
            f"/v1/campaigns/{random_uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_get_campaign(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        campaign = await _create_campaign(test_client, api_key, name="Get Test Campaign")
        campaign_uuid = campaign["uuid"]

        resp = await test_client.get(
            f"/v1/campaigns/{campaign_uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["uuid"] == campaign_uuid
        assert data["name"] == "Get Test Campaign"
        assert isinstance(data["items"], list)
        assert "created_at" in data
        assert "updated_at" in data


class TestPatchCampaign:
    async def test_patch_campaign(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        campaign = await _create_campaign(test_client, api_key, name="Before Patch")
        campaign_uuid = campaign["uuid"]

        patch_resp = await test_client.patch(
            f"/v1/campaigns/{campaign_uuid}",
            json={"name": "After Patch", "status": "active"},
            headers=auth_header(api_key),
        )
        assert patch_resp.status_code == 200
        data = patch_resp.json()["data"]
        assert data["name"] == "After Patch"
        assert data["status"] == "active"


class TestCampaignItems:
    async def test_add_item(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        campaign = await _create_campaign(test_client, api_key)
        campaign_uuid = campaign["uuid"]
        issue = await _create_issue(test_client, api_key)
        issue_uuid = issue["uuid"]

        resp = await test_client.post(
            f"/v1/campaigns/{campaign_uuid}/items",
            json={"item_type": "issue", "item_uuid": issue_uuid},
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["item_type"] == "issue"
        assert "uuid" in data
        assert "created_at" in data

    async def test_remove_item(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        campaign = await _create_campaign(test_client, api_key)
        campaign_uuid = campaign["uuid"]
        issue = await _create_issue(test_client, api_key, title="Issue to Remove")
        issue_uuid = issue["uuid"]

        # Add the item
        add_resp = await test_client.post(
            f"/v1/campaigns/{campaign_uuid}/items",
            json={"item_type": "issue", "item_uuid": issue_uuid},
            headers=auth_header(api_key),
        )
        assert add_resp.status_code == 201
        item_uuid = add_resp.json()["data"]["uuid"]

        # Remove the item
        del_resp = await test_client.delete(
            f"/v1/campaigns/{campaign_uuid}/items/{item_uuid}",
            headers=auth_header(api_key),
        )
        assert del_resp.status_code == 204

        # Verify it's gone from the campaign
        get_resp = await test_client.get(
            f"/v1/campaigns/{campaign_uuid}",
            headers=auth_header(api_key),
        )
        assert get_resp.status_code == 200
        items = get_resp.json()["data"]["items"]
        item_uuids = [i["uuid"] for i in items]
        assert item_uuid not in item_uuids


class TestCampaignMetrics:
    async def test_get_metrics(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        campaign = await _create_campaign(test_client, api_key, name="Metrics Campaign")
        campaign_uuid = campaign["uuid"]

        # Add an issue item
        issue = await _create_issue(test_client, api_key, title="Metrics Issue")
        await test_client.post(
            f"/v1/campaigns/{campaign_uuid}/items",
            json={"item_type": "issue", "item_uuid": issue["uuid"]},
            headers=auth_header(api_key),
        )

        resp = await test_client.get(
            f"/v1/campaigns/{campaign_uuid}/metrics",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["campaign_uuid"] == campaign_uuid
        assert "total_items" in data
        assert "alert_count" in data
        assert "issue_count" in data
        assert "routine_count" in data
        assert "issues_done" in data
        assert "completion_pct" in data
        assert "computed_at" in data
        assert data["total_items"] >= 1
        assert data["issue_count"] >= 1


class TestTopology:
    async def test_topology(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get("/v1/topology", headers=auth_header(api_key))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "nodes" in data
        assert "edges" in data
        assert "computed_at" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    async def test_topology_routing(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/topology/routing",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "nodes" in data
        assert "edges" in data
        assert "computed_at" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    async def test_topology_delegation(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/topology/delegation",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "nodes" in data
        assert "edges" in data
        assert "computed_at" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    async def test_topology_with_registered_agent(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        """Topology should include any registered agents as nodes."""
        resp = await test_client.get("/v1/topology", headers=auth_header(api_key))
        assert resp.status_code == 200
        data = resp.json()["data"]
        node_uuids = [n["uuid"] for n in data["nodes"]]
        assert sample_agent["uuid"] in node_uuids
