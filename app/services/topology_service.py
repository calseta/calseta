"""TopologyService — computes the agent fleet topology graph.

The topology graph is a snapshot of all registered agents (nodes) and their
relationships (edges). It is always computed on-demand from live DB state —
no caching, no stored graph.

Edge types:
  - "delegates_to": orchestrator agent delegates to specialist agent (sub_agent_ids)
  - "routes_to": alert routing relationship based on trigger_on_* fields
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import AgentRegistration
from app.db.models.alert_assignment import AlertAssignment
from app.schemas.topology import TopologyEdge, TopologyGraph, TopologyNode

logger = structlog.get_logger(__name__)

_OFFLINE_STATUSES = {"deactivated", "deleted"}


async def _batch_active_assignment_counts(
    db: AsyncSession, agent_ids: list[int]
) -> dict[int, int]:
    """Batch-count in_progress alert assignments for multiple agents in one query."""
    if not agent_ids:
        return {}
    result = await db.execute(
        select(
            AlertAssignment.agent_registration_id,
            func.count().label("cnt"),
        )
        .where(
            AlertAssignment.agent_registration_id.in_(agent_ids),
            AlertAssignment.status == "in_progress",
        )
        .group_by(AlertAssignment.agent_registration_id)
    )
    return {row.agent_registration_id: row.cnt for row in result.all()}


def _derive_node_status(agent: AgentRegistration) -> str:
    """Derive a simple topology node status from the agent's registration status."""
    status_map = {
        "active": "idle",
        "paused": "paused",
        "deactivated": "offline",
        "deleted": "offline",
        "error": "error",
    }
    return status_map.get(agent.status, "idle")


def _build_node(
    agent: AgentRegistration,
    assignment_counts: dict[int, int],
) -> TopologyNode:
    """Build a TopologyNode from an AgentRegistration row."""
    active_assignments = assignment_counts.get(agent.id, 0)

    # capabilities is JSONB — extract list of capability names if present
    caps: list[str] = []
    if agent.capabilities:
        if isinstance(agent.capabilities, dict):
            caps = list(agent.capabilities.keys())
        elif isinstance(agent.capabilities, list):
            caps = [str(c) for c in agent.capabilities]

    return TopologyNode(
        uuid=agent.uuid,
        name=agent.name,
        role=agent.role,
        agent_type=agent.agent_type,
        status=_derive_node_status(agent),
        execution_mode=agent.execution_mode,
        capabilities=caps,
        active_assignments=active_assignments,
        max_concurrent_alerts=agent.max_concurrent_alerts,
        budget_monthly_cents=(
            agent.budget_monthly_cents if agent.budget_monthly_cents != 0 else None
        ),
        spent_monthly_cents=agent.spent_monthly_cents,
        last_heartbeat_at=agent.last_heartbeat_at,
    )


async def _load_agents(db: AsyncSession) -> list[AgentRegistration]:
    """Load all non-deleted/deactivated agents."""
    result = await db.execute(
        select(AgentRegistration).where(
            AgentRegistration.status.notin_(list(_OFFLINE_STATUSES))
        )
    )
    return list(result.scalars().all())


def _build_delegation_edges(
    agents: list[AgentRegistration],
    uuid_by_id: dict[int, uuid.UUID],
) -> list[TopologyEdge]:
    """Build delegates_to edges from sub_agent_ids arrays."""
    # Build a name→uuid map for sub_agent_ids (stored as agent registration IDs as text)
    id_to_uuid: dict[str, uuid.UUID] = {str(a.id): a.uuid for a in agents}
    edges: list[TopologyEdge] = []

    for agent in agents:
        if not agent.sub_agent_ids:
            continue
        for sub_id_str in agent.sub_agent_ids:
            target_uuid = id_to_uuid.get(str(sub_id_str))
            if target_uuid is not None:
                edges.append(
                    TopologyEdge(
                        from_uuid=agent.uuid,
                        to_uuid=target_uuid,
                        edge_type="delegates_to",
                        label=None,
                    )
                )

    return edges


class TopologyService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def compute_topology(self) -> TopologyGraph:
        """Full topology: all nodes + delegation edges."""
        agents = await _load_agents(self._db)
        uuid_by_id: dict[int, uuid.UUID] = {a.id: a.uuid for a in agents}
        counts = await _batch_active_assignment_counts(self._db, [a.id for a in agents])

        nodes = [_build_node(a, counts) for a in agents]
        edges = _build_delegation_edges(agents, uuid_by_id)

        logger.info(
            "topology_computed",
            node_count=len(nodes),
            edge_count=len(edges),
        )
        return TopologyGraph(
            nodes=nodes,
            edges=edges,
            computed_at=datetime.now(UTC),
        )

    async def compute_routing_graph(self) -> TopologyGraph:
        """Routing-only topology: agents with non-empty trigger_on_* fields."""
        agents = await _load_agents(self._db)

        # Filter to agents that have routing configuration
        routing_agents = [
            a for a in agents
            if (a.trigger_on_sources and len(a.trigger_on_sources) > 0)
            or (a.trigger_on_severities and len(a.trigger_on_severities) > 0)
            or a.trigger_filter is not None
        ]
        counts = await _batch_active_assignment_counts(
            self._db, [a.id for a in routing_agents]
        )

        nodes = [_build_node(a, counts) for a in routing_agents]

        # No edges for routing graph — just shows which agents receive alerts
        return TopologyGraph(
            nodes=nodes,
            edges=[],
            computed_at=datetime.now(UTC),
        )

    async def compute_delegation_graph(self) -> TopologyGraph:
        """Delegation-only topology: orchestrators and their specialist agents."""
        agents = await _load_agents(self._db)
        uuid_by_id: dict[int, uuid.UUID] = {a.id: a.uuid for a in agents}

        edges = _build_delegation_edges(agents, uuid_by_id)

        # Include only agents that participate in delegation
        participating_uuids: set[uuid.UUID] = set()
        for edge in edges:
            participating_uuids.add(edge.from_uuid)
            participating_uuids.add(edge.to_uuid)

        involved_agents = [a for a in agents if a.uuid in participating_uuids]
        counts = await _batch_active_assignment_counts(
            self._db, [a.id for a in involved_agents]
        )
        nodes = [_build_node(a, counts) for a in involved_agents]

        return TopologyGraph(
            nodes=nodes,
            edges=edges,
            computed_at=datetime.now(UTC),
        )
