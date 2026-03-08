"""Workflow approval request schemas (Chunk 4.11)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.indicators import IndicatorType
from app.schemas.workflows import TRIGGER_SOURCES


class WorkflowApprovalRequestResponse(BaseModel):
    """Full approval request state — used by GET /v1/workflow-approvals/{uuid}."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    workflow_id: int
    workflow_name: str | None = None
    workflow_uuid: UUID | None = None
    trigger_type: str
    trigger_context: dict[str, Any] | None
    reason: str
    confidence: float
    notifier_type: str
    notifier_channel: str | None
    status: str
    responder_id: str | None
    responded_at: datetime | None
    expires_at: datetime
    execution_result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class WorkflowExecuteAgentRequest(BaseModel):
    """
    Request body for POST /v1/workflows/{uuid}/execute when trigger_source="agent".

    Extends the base execute request with required `reason` and `confidence` fields
    that the approval gate uses to populate the approval notification.
    """

    indicator_type: str
    indicator_value: str
    alert_uuid: UUID | None = None
    trigger_source: str = "human"
    reason: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("indicator_type")
    @classmethod
    def _validate_indicator_type(cls, v: str) -> str:
        valid = {t.value for t in IndicatorType}
        if v not in valid:
            raise ValueError(f"indicator_type must be one of: {sorted(valid)}")
        return v

    @field_validator("trigger_source")
    @classmethod
    def _validate_trigger_source(cls, v: str) -> str:
        if v not in TRIGGER_SOURCES:
            raise ValueError(f"trigger_source must be one of: {sorted(TRIGGER_SOURCES)}")
        return v

    def validate_agent_fields(self) -> list[str]:
        """Return validation errors specific to agent-triggered executes."""
        errors: list[str] = []
        if self.trigger_source == "agent":
            if not self.reason:
                errors.append("reason is required when trigger_source='agent'")
            if self.confidence is None:
                errors.append("confidence is required when trigger_source='agent'")
        return errors


class WorkflowApproveRequest(BaseModel):
    """Request body for POST /v1/workflow-approvals/{uuid}/approve."""

    responder_id: str | None = None


class WorkflowRejectRequest(BaseModel):
    """Request body for POST /v1/workflow-approvals/{uuid}/reject."""

    responder_id: str | None = None
    reason: str | None = None


class WorkflowPendingApprovalResponse(BaseModel):
    """Response when execute is gated behind an approval request."""

    run_uuid: UUID | None = None
    approval_request_uuid: UUID
    status: str  # "pending_approval"
    expires_at: datetime
