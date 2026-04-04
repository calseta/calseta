"""Campaign API schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CampaignStatus:
    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ALL = ["planned", "active", "completed", "cancelled"]


class CampaignCategory:
    DETECTION_IMPROVEMENT = "detection_improvement"
    RESPONSE_OPTIMIZATION = "response_optimization"
    VULNERABILITY_MANAGEMENT = "vulnerability_management"
    COMPLIANCE = "compliance"
    THREAT_HUNTING = "threat_hunting"
    CUSTOM = "custom"
    ALL = [
        "detection_improvement",
        "response_optimization",
        "vulnerability_management",
        "compliance",
        "threat_hunting",
        "custom",
    ]


class CampaignItemType:
    ALERT = "alert"
    ISSUE = "issue"
    ROUTINE = "routine"
    ALL = ["alert", "issue", "routine"]


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    status: str = "planned"
    category: str = "custom"
    owner_agent_uuid: UUID | None = None
    owner_operator: str | None = None
    target_metric: str | None = None
    target_value: Decimal | None = None
    target_date: datetime | None = None


class CampaignPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: str | None = None
    category: str | None = None
    owner_agent_uuid: UUID | None = None
    owner_operator: str | None = None
    target_metric: str | None = None
    target_value: Decimal | None = None
    target_date: datetime | None = None


class CampaignItemCreate(BaseModel):
    item_type: str
    item_uuid: UUID


class CampaignItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    item_type: str
    item_uuid: str
    created_at: datetime


class CampaignResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    name: str
    description: str | None
    status: str
    category: str
    owner_operator: str | None
    target_metric: str | None
    target_value: Decimal | None
    current_value: Decimal | None
    target_date: datetime | None
    created_at: datetime
    updated_at: datetime
    owner_agent_uuid: UUID | None = None
    items: list[CampaignItemResponse] = Field(default_factory=list)


class CampaignMetrics(BaseModel):
    """Auto-computed metrics for a campaign — derived from linked alerts and issues."""

    campaign_uuid: UUID
    computed_at: datetime
    total_items: int
    alert_count: int
    issue_count: int
    routine_count: int
    issues_done: int
    issues_in_progress: int
    issues_backlog: int
    completion_pct: float
    current_value: Decimal | None
    target_value: Decimal | None
    target_metric: str | None
