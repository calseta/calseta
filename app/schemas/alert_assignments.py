"""Pydantic schemas for alert queue and assignment endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PENDING_REVIEW = "pending_review"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    RELEASED = "released"


class AlertAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    alert_id: int
    agent_registration_id: int
    status: str
    checked_out_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    resolution: str | None
    resolution_type: str | None
    created_at: datetime
    updated_at: datetime


class AlertAssignmentWithAlert(AlertAssignmentResponse):
    alert: dict[str, Any]  # serialized alert data


class AssignmentUpdate(BaseModel):
    status: AssignmentStatus | None = None
    resolution: str | None = None
    # "true_positive", "false_positive", "benign", "inconclusive"
    resolution_type: str | None = None
    investigation_state: dict[str, Any] | None = None
