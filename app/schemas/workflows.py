"""Workflow schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.indicators import IndicatorType

WORKFLOW_TYPES = frozenset({"indicator", "alert"})
WORKFLOW_STATES = frozenset({"draft", "active", "inactive"})
RISK_LEVELS = frozenset({"low", "medium", "high", "critical"})
APPROVAL_MODES = frozenset({"always", "agent_only", "never"})


class WorkflowCreate(BaseModel):
    """Request body for POST /v1/workflows."""

    name: str
    workflow_type: str | None = None
    indicator_types: list[str] = []
    code: str
    state: str = "draft"
    timeout_seconds: int = 300
    retry_count: int = 0
    is_active: bool = True
    tags: list[str] = []
    time_saved_minutes: int | None = None
    approval_mode: str = "always"
    approval_channel: str | None = None
    approval_timeout_seconds: int = 3600
    risk_level: str = "medium"
    documentation: str | None = None

    @field_validator("workflow_type")
    @classmethod
    def _validate_workflow_type(cls, v: str | None) -> str | None:
        if v is not None and v not in WORKFLOW_TYPES:
            raise ValueError(f"workflow_type must be one of: {sorted(WORKFLOW_TYPES)}")
        return v

    @field_validator("indicator_types", mode="before")
    @classmethod
    def _validate_indicator_types(cls, v: list[Any]) -> list[str]:
        valid = {t.value for t in IndicatorType}
        for item in v:
            if item not in valid:
                raise ValueError(
                    f"indicator_types contains invalid value '{item}'. "
                    f"Must be one of: {sorted(valid)}"
                )
        return v

    @field_validator("state")
    @classmethod
    def _validate_state(cls, v: str) -> str:
        if v not in WORKFLOW_STATES:
            raise ValueError(f"state must be one of: {sorted(WORKFLOW_STATES)}")
        return v

    @field_validator("risk_level")
    @classmethod
    def _validate_risk_level(cls, v: str) -> str:
        if v not in RISK_LEVELS:
            raise ValueError(f"risk_level must be one of: {sorted(RISK_LEVELS)}")
        return v

    @field_validator("approval_mode")
    @classmethod
    def _validate_approval_mode(cls, v: str) -> str:
        if v not in APPROVAL_MODES:
            raise ValueError(f"approval_mode must be one of: {sorted(APPROVAL_MODES)}")
        return v


class WorkflowPatch(BaseModel):
    """Request body for PATCH /v1/workflows/{uuid}."""

    name: str | None = None
    workflow_type: str | None = None
    indicator_types: list[str] | None = None
    code: str | None = None
    state: str | None = None
    timeout_seconds: int | None = None
    retry_count: int | None = None
    is_active: bool | None = None
    tags: list[str] | None = None
    time_saved_minutes: int | None = None
    approval_mode: str | None = None
    approval_channel: str | None = None
    approval_timeout_seconds: int | None = None
    risk_level: str | None = None
    documentation: str | None = None

    @field_validator("workflow_type")
    @classmethod
    def _validate_workflow_type(cls, v: str | None) -> str | None:
        if v is not None and v not in WORKFLOW_TYPES:
            raise ValueError(f"workflow_type must be one of: {sorted(WORKFLOW_TYPES)}")
        return v

    @field_validator("indicator_types", mode="before")
    @classmethod
    def _validate_indicator_types(cls, v: list[Any] | None) -> list[str] | None:
        if v is None:
            return None
        valid = {t.value for t in IndicatorType}
        for item in v:
            if item not in valid:
                raise ValueError(
                    f"indicator_types contains invalid value '{item}'. "
                    f"Must be one of: {sorted(valid)}"
                )
        return v

    @field_validator("state")
    @classmethod
    def _validate_state(cls, v: str | None) -> str | None:
        if v is not None and v not in WORKFLOW_STATES:
            raise ValueError(f"state must be one of: {sorted(WORKFLOW_STATES)}")
        return v

    @field_validator("risk_level")
    @classmethod
    def _validate_risk_level(cls, v: str | None) -> str | None:
        if v is not None and v not in RISK_LEVELS:
            raise ValueError(f"risk_level must be one of: {sorted(RISK_LEVELS)}")
        return v

    @field_validator("approval_mode")
    @classmethod
    def _validate_approval_mode(cls, v: str | None) -> str | None:
        if v is not None and v not in APPROVAL_MODES:
            raise ValueError(f"approval_mode must be one of: {sorted(APPROVAL_MODES)}")
        return v


class WorkflowSummary(BaseModel):
    """List response — omits code to save tokens."""

    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    name: str
    workflow_type: str | None
    indicator_types: list[str]
    state: str
    code_version: int
    is_active: bool
    is_system: bool
    tags: list[str]
    time_saved_minutes: int | None
    approval_mode: str
    risk_level: str
    documentation: str | None
    created_at: datetime
    updated_at: datetime


class WorkflowResponse(WorkflowSummary):
    """Full response — includes code and approval config."""

    code: str
    timeout_seconds: int
    retry_count: int
    approval_channel: str | None
    approval_timeout_seconds: int


# ---------------------------------------------------------------------------
# Workflow execution schemas (Chunk 4.8)
# ---------------------------------------------------------------------------

TRIGGER_SOURCES = frozenset({"human", "agent", "system"})


class WorkflowExecuteRequest(BaseModel):
    """Request body for POST /v1/workflows/{uuid}/execute.

    Note: trigger_source is derived server-side from the API key's key_type.
    """

    indicator_type: str
    indicator_value: str
    alert_uuid: uuid.UUID | None = None

    @field_validator("indicator_type")
    @classmethod
    def _validate_indicator_type(cls, v: str) -> str:
        valid = {t.value for t in IndicatorType}
        if v not in valid:
            raise ValueError(
                f"indicator_type must be one of: {sorted(valid)}"
            )
        return v


class WorkflowExecuteResponse(BaseModel):
    """Response for POST /v1/workflows/{uuid}/execute (202 Accepted)."""

    run_uuid: uuid.UUID
    status: str  # "queued"


# ---------------------------------------------------------------------------
# Workflow run schemas (Chunk 4.9)
# ---------------------------------------------------------------------------


class WorkflowRunResponse(BaseModel):
    """Full workflow run audit record."""

    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    workflow_id: int
    trigger_type: str
    trigger_context: dict[str, Any] | None
    code_version_executed: int
    status: str
    attempt_count: int
    log_output: str | None
    result: dict[str, Any] | None
    duration_ms: int | None
    started_at: str | None
    completed_at: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Workflow generation schemas (Chunk 4.7)
# ---------------------------------------------------------------------------


class WorkflowGenerateRequest(BaseModel):
    """Request body for POST /v1/workflows/generate."""

    description: str
    workflow_type: str | None = None
    indicator_types: list[str] = []

    @field_validator("workflow_type")
    @classmethod
    def _validate_workflow_type(cls, v: str | None) -> str | None:
        if v is not None and v not in WORKFLOW_TYPES:
            raise ValueError(f"workflow_type must be one of: {sorted(WORKFLOW_TYPES)}")
        return v


class WorkflowGenerateResponse(BaseModel):
    """Response for POST /v1/workflows/generate."""

    generated_code: str
    suggested_name: str
    suggested_documentation: str
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Workflow test schemas (Chunk 4.7)
# ---------------------------------------------------------------------------


class WorkflowTestRequest(BaseModel):
    """Request body for POST /v1/workflows/{uuid}/test."""

    indicator_type: str = "ip"
    indicator_value: str = "1.2.3.4"
    mock_http_responses: dict[str, Any] = {}
    live_http: bool = False

    @field_validator("indicator_type")
    @classmethod
    def _validate_indicator_type(cls, v: str) -> str:
        valid = {t.value for t in IndicatorType}
        if v not in valid:
            raise ValueError(f"indicator_type must be one of: {sorted(valid)}")
        return v


class WorkflowTestResponse(BaseModel):
    """Response for POST /v1/workflows/{uuid}/test."""

    success: bool
    message: str
    log_output: str
    duration_ms: int
    result_data: dict[str, Any]


# ---------------------------------------------------------------------------
# Workflow version schemas (Chunk 4.7)
# ---------------------------------------------------------------------------


class WorkflowVersionResponse(BaseModel):
    """Single entry in GET /v1/workflows/{uuid}/versions."""

    model_config = ConfigDict(from_attributes=True)

    version: int
    code_preview: str
    saved_at: datetime
