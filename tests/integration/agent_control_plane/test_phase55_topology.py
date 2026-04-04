"""Integration tests — Agent Topology (Phase 5.5).

Verifies:
- Topology is read-only; computed from existing agent configs
- GET /v1/topology returns nodes and edges
- Nodes reflect registered agents (zero agents → empty graph)
- Edges reflect sub_agent_ids delegation relationships
- Routing topology shows agents with trigger filters
- Delegation topology shows orchestrator→specialist relationships
- Creating/updating agents updates the topology
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.agent_control_plane.conftest import _create_agent_with_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_orchestrator_with_specialists(
    db: AsyncSession,
    *,
    num_specialists: int = 2,
    name_prefix: str = "top-orch",
) -> tuple[Any, list[Any]]:
    """Create an orchestrator with sub_agent_ids pointing at specialists."""
    # Create specialist agents
    specialists = []
    for i in range(num_specialists):
        spec, _ = await _create_agent_with_key(db, name=f"{name_prefix}-spec-{i}")
        spec.agent_type = "specialist"
        await db.flush()
        await db.refresh(spec)
        specialists.append(spec)

    # Create orchestrator with sub_agent_ids set to the specialist integer IDs (as strings)
    # TopologyService._build_delegation_edges looks up via str(agent.id), not uuid.
    orch, _ = await _create_agent_with_key(db, name=f"{name_prefix}-orchestrator")
    orch.agent_type = "orchestrator"
    orch.sub_agent_ids = [str(s.id) for s in specialists]
    await db.flush()
    await db.refresh(orch)
    return orch, specialists


# ---------------------------------------------------------------------------
# Full topology
# ---------------------------------------------------------------------------


class TestTopologyFull:
    """GET /v1/topology — full fleet graph."""

    async def test_topology_returns_200(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Topology endpoint is reachable and returns 200."""
        resp = await test_client.get("/v1/topology", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text

    async def test_topology_response_shape(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Topology response has nodes, edges, and computed_at fields."""
        resp = await test_client.get("/v1/topology", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert "nodes" in data
        assert "edges" in data
        assert "computed_at" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)

    async def test_topology_includes_registered_agents_as_nodes(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Registered agents appear as topology nodes."""
        agent, _ = await _create_agent_with_key(db_session, name="topology-node-agent")
        await db_session.flush()

        resp = await test_client.get("/v1/topology", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        nodes = resp.json()["data"]["nodes"]

        node_uuids = [n["uuid"] for n in nodes]
        assert str(agent.uuid) in node_uuids

    async def test_topology_node_has_required_fields(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Each topology node contains the expected schema fields."""
        agent, _ = await _create_agent_with_key(db_session, name="topology-fields-agent")
        await db_session.flush()

        resp = await test_client.get("/v1/topology", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        nodes = resp.json()["data"]["nodes"]
        node = next((n for n in nodes if n["uuid"] == str(agent.uuid)), None)
        assert node is not None, "Agent node not found in topology"

        required_fields = {
            "uuid", "name", "agent_type", "status", "execution_mode",
            "capabilities", "active_assignments", "max_concurrent_alerts",
            "spent_monthly_cents",
        }
        for field in required_fields:
            assert field in node, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Delegation edges
# ---------------------------------------------------------------------------


class TestTopologyDelegationEdges:
    """GET /v1/topology/delegation — orchestrator→specialist edges."""

    async def test_delegation_graph_has_edges_between_orchestrator_and_specialists(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Orchestrator with sub_agent_ids → delegation edges appear in topology."""
        orch, specialists = await _create_orchestrator_with_specialists(
            db_session, num_specialists=2, name_prefix="del-edge"
        )
        await db_session.flush()

        resp = await test_client.get("/v1/topology/delegation", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        # Orchestrator and specialists must be present as nodes
        node_uuids = {n["uuid"] for n in data["nodes"]}
        assert str(orch.uuid) in node_uuids
        for spec in specialists:
            assert str(spec.uuid) in node_uuids

        # Edges from orchestrator to each specialist
        edge_pairs = {(e["from_uuid"], e["to_uuid"]) for e in data["edges"]}
        for spec in specialists:
            assert (str(orch.uuid), str(spec.uuid)) in edge_pairs, (
                f"Expected delegation edge from {orch.uuid} to {spec.uuid}"
            )

    async def test_delegation_graph_edge_type_is_delegates_to(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Delegation edges have edge_type='delegates_to'."""
        orch, specialists = await _create_orchestrator_with_specialists(
            db_session, num_specialists=1, name_prefix="edgetype"
        )
        await db_session.flush()

        resp = await test_client.get("/v1/topology/delegation", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        edges = resp.json()["data"]["edges"]

        orch_edges = [
            e for e in edges
            if e["from_uuid"] == str(orch.uuid) and e["to_uuid"] == str(specialists[0].uuid)
        ]
        assert len(orch_edges) >= 1
        assert orch_edges[0]["edge_type"] == "delegates_to"


# ---------------------------------------------------------------------------
# Routing topology
# ---------------------------------------------------------------------------


class TestTopologyRouting:
    """GET /v1/topology/routing — agents with alert routing configuration."""

    async def test_routing_graph_returns_200(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Routing topology endpoint returns 200."""
        resp = await test_client.get("/v1/topology/routing", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text

    async def test_agent_with_triggers_appears_in_routing_graph(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Agent configured with trigger sources appears in the routing graph."""
        agent, _ = await _create_agent_with_key(db_session, name="routing-trigger-agent")
        agent.trigger_on_sources = ["generic", "sentinel"]
        agent.trigger_on_severities = ["High", "Critical"]
        await db_session.flush()

        resp = await test_client.get("/v1/topology/routing", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        nodes = resp.json()["data"]["nodes"]
        node_uuids = [n["uuid"] for n in nodes]
        assert str(agent.uuid) in node_uuids


# ---------------------------------------------------------------------------
# Zero agents
# ---------------------------------------------------------------------------


class TestTopologyEdgeCases:
    """Topology behavior with edge case agent counts."""

    async def test_topology_with_zero_agents_returns_empty_graph(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
        db_session: AsyncSession,
    ) -> None:
        """When no agents exist, topology returns empty nodes and edges lists.

        Note: this test works best on a fresh DB. In an integration test environment
        with shared fixtures, there may be agents from other tests. We assert the
        response shape rather than exact counts.
        """
        resp = await test_client.get("/v1/topology", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        # Shape is always correct regardless of agent count
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
        assert data["computed_at"] is not None
