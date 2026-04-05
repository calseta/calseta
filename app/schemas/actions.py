"""Pydantic schemas for action endpoints — Phase 2 agent control plane."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionType(StrEnum):
    CONTAINMENT = "containment"
    REMEDIATION = "remediation"
    NOTIFICATION = "notification"
    ESCALATION = "escalation"
    ENRICHMENT = "enrichment"
    INVESTIGATION = "investigation"
    USER_VALIDATION = "user_validation"
    CUSTOM = "custom"


class ProposeActionRequest(BaseModel):
    alert_id: UUID
    assignment_id: UUID
    action_type: ActionType
    action_subtype: str  # e.g. "block_ip", "disable_user", "send_slack_notification"
    payload: dict[str, Any]
    confidence: float | None = None  # 0.0–1.0
    reasoning: str | None = None


class ProposeActionResponse(BaseModel):
    action_id: UUID  # agent_actions.uuid
    status: ActionStatus
    approval_request_uuid: UUID | None = None  # set when approval required
    expires_at: datetime | None = None  # set when approval required


class ActionStatusUpdate(BaseModel):
    status: Literal["approved", "rejected"]
    reason: str | None = None


class AgentActionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    alert_id: int
    agent_registration_id: int
    assignment_id: int
    action_type: str
    action_subtype: str
    status: str
    payload: dict[str, Any]
    confidence: float | None
    approval_request_id: int | None
    execution_result: dict[str, Any] | None
    executed_at: datetime | None
    created_at: datetime
    updated_at: datetime
