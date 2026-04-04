"""Unit tests for app/services/campaign_service.py — no DB, no network."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.campaigns import (
    CampaignCategory,
    CampaignCreate,
    CampaignItemCreate,
    CampaignItemType,
    CampaignMetrics,
    CampaignStatus,
)
from app.schemas.topology import TopologyNode

# ---------------------------------------------------------------------------
# Constant tests
# ---------------------------------------------------------------------------


def test_campaign_status_constants() -> None:
    """CampaignStatus.ALL has 4 values."""
    assert len(CampaignStatus.ALL) == 4
    expected = {
        CampaignStatus.PLANNED,
        CampaignStatus.ACTIVE,
        CampaignStatus.COMPLETED,
        CampaignStatus.CANCELLED,
    }
    assert set(CampaignStatus.ALL) == expected


def test_campaign_category_constants() -> None:
    """CampaignCategory.ALL has 6 values."""
    assert len(CampaignCategory.ALL) == 6
    expected = {
        CampaignCategory.DETECTION_IMPROVEMENT,
        CampaignCategory.RESPONSE_OPTIMIZATION,
        CampaignCategory.VULNERABILITY_MANAGEMENT,
        CampaignCategory.COMPLIANCE,
        CampaignCategory.THREAT_HUNTING,
        CampaignCategory.CUSTOM,
    }
    assert set(CampaignCategory.ALL) == expected


def test_campaign_item_type_constants() -> None:
    """CampaignItemType.ALL has 3 values."""
    assert len(CampaignItemType.ALL) == 3
    expected = {
        CampaignItemType.ALERT,
        CampaignItemType.ISSUE,
        CampaignItemType.ROUTINE,
    }
    assert set(CampaignItemType.ALL) == expected


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


def test_campaign_create_schema_valid() -> None:
    """CampaignCreate(name='test') validates with correct defaults."""
    campaign = CampaignCreate(name="Q2 Threat Hunting")
    assert campaign.name == "Q2 Threat Hunting"
    assert campaign.status == "planned"
    assert campaign.category == "custom"
    assert campaign.description is None
    assert campaign.owner_agent_uuid is None
    assert campaign.owner_operator is None
    assert campaign.target_metric is None
    assert campaign.target_value is None
    assert campaign.target_date is None


def test_campaign_create_schema_name_too_short() -> None:
    """CampaignCreate with empty name raises ValidationError."""
    with pytest.raises(ValidationError):
        CampaignCreate(name="")


def test_campaign_create_with_all_fields() -> None:
    """CampaignCreate with all optional fields validates."""
    campaign = CampaignCreate(
        name="Reduce MTTR",
        description="Track MTTR improvements across Q2",
        status="active",
        category="response_optimization",
        owner_operator="security-lead",
        target_metric="mttr_hours",
        target_value=Decimal("4.0"),
    )
    assert campaign.status == "active"
    assert campaign.category == "response_optimization"
    assert campaign.target_value == Decimal("4.0")


def test_campaign_item_create_valid() -> None:
    """CampaignItemCreate(item_type='alert', item_uuid=uuid4()) validates."""
    item = CampaignItemCreate(item_type="alert", item_uuid=uuid4())
    assert item.item_type == "alert"
    assert item.item_uuid is not None


def test_campaign_item_create_issue_type() -> None:
    """CampaignItemCreate(item_type='issue') validates."""
    item = CampaignItemCreate(item_type="issue", item_uuid=uuid4())
    assert item.item_type == "issue"


def test_campaign_item_create_routine_type() -> None:
    """CampaignItemCreate(item_type='routine') validates."""
    item = CampaignItemCreate(item_type="routine", item_uuid=uuid4())
    assert item.item_type == "routine"


def test_campaign_metrics_schema() -> None:
    """CampaignMetrics can be constructed with all required fields."""
    now = datetime.now(UTC)
    metrics = CampaignMetrics(
        campaign_uuid=uuid4(),
        computed_at=now,
        total_items=10,
        alert_count=5,
        issue_count=4,
        routine_count=1,
        issues_done=2,
        issues_in_progress=1,
        issues_backlog=1,
        completion_pct=50.0,
        current_value=Decimal("2.5"),
        target_value=Decimal("5.0"),
        target_metric="alerts_resolved",
    )
    assert metrics.total_items == 10
    assert metrics.alert_count == 5
    assert metrics.issue_count == 4
    assert metrics.routine_count == 1
    assert metrics.completion_pct == 50.0
    assert metrics.current_value == Decimal("2.5")
    assert metrics.target_metric == "alerts_resolved"


def test_campaign_metrics_schema_nullable_fields() -> None:
    """CampaignMetrics can be constructed with nullable fields set to None."""
    now = datetime.now(UTC)
    metrics = CampaignMetrics(
        campaign_uuid=uuid4(),
        computed_at=now,
        total_items=0,
        alert_count=0,
        issue_count=0,
        routine_count=0,
        issues_done=0,
        issues_in_progress=0,
        issues_backlog=0,
        completion_pct=0.0,
        current_value=None,
        target_value=None,
        target_metric=None,
    )
    assert metrics.total_items == 0
    assert metrics.current_value is None
    assert metrics.target_metric is None


def test_topology_node_schema() -> None:
    """TopologyNode can be constructed from a dict of valid fields."""
    now = datetime.now(UTC)
    node = TopologyNode(
        uuid=uuid4(),
        name="Alert Triage Agent",
        role="triage",
        agent_type="autonomous",
        status="idle",
        execution_mode="autonomous",
        capabilities=["alert_triage", "enrichment"],
        active_assignments=0,
        max_concurrent_alerts=5,
        budget_monthly_cents=10000,
        spent_monthly_cents=250,
        last_heartbeat_at=now,
    )
    assert node.name == "Alert Triage Agent"
    assert node.status == "idle"
    assert node.capabilities == ["alert_triage", "enrichment"]
    assert node.active_assignments == 0
    assert node.budget_monthly_cents == 10000
    assert node.spent_monthly_cents == 250


def test_topology_node_schema_nullable_fields() -> None:
    """TopologyNode can be constructed with nullable fields set to None."""
    node = TopologyNode(
        uuid=uuid4(),
        name="Minimal Agent",
        role=None,
        agent_type="supervised",
        status="offline",
        execution_mode="supervised",
        capabilities=[],
        active_assignments=0,
        max_concurrent_alerts=1,
        budget_monthly_cents=None,
        spent_monthly_cents=0,
        last_heartbeat_at=None,
    )
    assert node.role is None
    assert node.budget_monthly_cents is None
    assert node.last_heartbeat_at is None
