"""Smoke tests for Phase 5.5 schema imports and instantiation."""

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.campaigns import CampaignCategory, CampaignCreate, CampaignStatus
from app.schemas.issues import IssueCategory, IssueCreate, IssuePriority, IssueStatus
from app.schemas.routines import RoutineCreate, RoutineStatus, TriggerKind
from app.schemas.topology import TopologyEdge, TopologyGraph, TopologyNode


def test_all_phase55_schemas_importable() -> None:
    """All Phase 5.5 schemas import without error."""
    assert IssueStatus.ALL
    assert IssuePriority.ALL
    assert IssueCategory.ALL
    assert RoutineStatus.ALL
    assert TriggerKind.ALL
    assert CampaignStatus.ALL
    assert CampaignCategory.ALL


def test_issue_create_defaults() -> None:
    issue = IssueCreate(title="Test issue")
    assert issue.status == "backlog"
    assert issue.priority == "medium"
    assert issue.category == "investigation"


def test_campaign_create_defaults() -> None:
    campaign = CampaignCreate(name="Test campaign")
    assert campaign.status == "planned"
    assert campaign.category == "custom"


def test_topology_graph_empty() -> None:
    graph = TopologyGraph(nodes=[], edges=[], computed_at=datetime.now(UTC))
    assert graph.nodes == []
    assert graph.edges == []


def test_topology_graph_with_nodes_and_edges() -> None:
    """TopologyGraph with nodes and edges constructs correctly."""
    now = datetime.now(UTC)
    uuid_a = uuid4()
    uuid_b = uuid4()

    node_a = TopologyNode(
        uuid=uuid_a,
        name="Orchestrator",
        role="orchestrator",
        agent_type="autonomous",
        status="running",
        execution_mode="autonomous",
        capabilities=["orchestrate"],
        active_assignments=1,
        max_concurrent_alerts=10,
        budget_monthly_cents=50000,
        spent_monthly_cents=1200,
        last_heartbeat_at=now,
    )
    node_b = TopologyNode(
        uuid=uuid_b,
        name="Worker",
        role="worker",
        agent_type="supervised",
        status="idle",
        execution_mode="supervised",
        capabilities=["enrich"],
        active_assignments=0,
        max_concurrent_alerts=5,
        budget_monthly_cents=None,
        spent_monthly_cents=0,
        last_heartbeat_at=now,
    )
    edge = TopologyEdge(from_uuid=uuid_a, to_uuid=uuid_b, edge_type="delegates_to", label="enrichment")

    graph = TopologyGraph(nodes=[node_a, node_b], edges=[edge], computed_at=now)
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1
    assert graph.edges[0].edge_type == "delegates_to"


def test_routine_create_with_triggers() -> None:
    """RoutineCreate with an embedded TriggerCreate validates."""
    from app.schemas.routines import TriggerCreate

    routine = RoutineCreate(
        name="Hourly IOC scan",
        agent_registration_uuid=uuid4(),
        task_template={"action": "scan_iocs"},
        triggers=[TriggerCreate(kind="cron", cron_expression="0 * * * *")],
    )
    assert len(routine.triggers) == 1
    assert routine.triggers[0].kind == "cron"
    assert routine.triggers[0].cron_expression == "0 * * * *"
