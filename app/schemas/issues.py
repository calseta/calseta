"""Issue/Task System API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IssueStatus:
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"

    ALL = [BACKLOG, TODO, IN_PROGRESS, IN_REVIEW, DONE, BLOCKED, CANCELLED]
    TERMINAL = [DONE, CANCELLED]


class IssuePriority:
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    ALL = [CRITICAL, HIGH, MEDIUM, LOW]


class IssueCategory:
    REMEDIATION = "remediation"
    DETECTION_TUNING = "detection_tuning"
    INVESTIGATION = "investigation"
    COMPLIANCE = "compliance"
    POST_INCIDENT = "post_incident"
    MAINTENANCE = "maintenance"
    CUSTOM = "custom"
    ALL = [
        REMEDIATION, DETECTION_TUNING, INVESTIGATION,
        COMPLIANCE, POST_INCIDENT, MAINTENANCE, CUSTOM,
    ]


class IssueCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    status: str = Field(default="backlog")
    priority: str = Field(default="medium")
    category: str = Field(default="investigation")
    assignee_agent_uuid: UUID | None = None
    assignee_operator: str | None = None
    alert_uuid: UUID | None = None
    parent_uuid: UUID | None = None
    due_at: datetime | None = None
    metadata: dict[str, Any] | None = None


class IssuePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    category: str | None = None
    assignee_agent_uuid: UUID | None = None
    assignee_operator: str | None = None
    due_at: datetime | None = None
    resolution: str | None = None
    metadata: dict[str, Any] | None = None


class IssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    identifier: str
    title: str
    description: str | None
    status: str
    priority: str
    category: str
    assignee_operator: str | None
    created_by_operator: str | None
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    resolution: str | None
    created_at: datetime
    updated_at: datetime
    # Resolved FK references (UUIDs for cross-linking)
    assignee_agent_uuid: UUID | None = None
    created_by_agent_uuid: UUID | None = None
    alert_uuid: UUID | None = None
    parent_uuid: UUID | None = None
    routine_uuid: UUID | None = None


class IssueCommentCreate(BaseModel):
    body: str = Field(..., min_length=1)
    author_operator: str | None = None


class IssueCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    body: str
    author_operator: str | None
    author_agent_uuid: UUID | None = None
    created_at: datetime
    updated_at: datetime


class IssueCheckoutRequest(BaseModel):
    heartbeat_run_uuid: UUID
