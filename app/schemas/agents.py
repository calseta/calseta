"""Agent registration API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from app.schemas.common import JSONB_SIZE_SMALL, validate_jsonb_size


class AgentRegistrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    endpoint_url: str | None = None  # optional — managed agents don't need it
    auth_header_name: str | None = None
    auth_header_value: str | None = None  # plaintext; encrypted before storage
    trigger_on_sources: list[str] = Field(default_factory=list)
    trigger_on_severities: list[str] = Field(default_factory=list)
    trigger_filter: dict[str, Any] | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=3600)
    retry_count: int = Field(default=3, ge=0, le=10)
    documentation: str | None = None

    # --- Control plane: identity & type ---
    execution_mode: str = Field(default="external")
    agent_type: str = Field(default="standalone")
    role: str | None = None
    capabilities: dict[str, Any] | None = None

    # --- Control plane: adapter ---
    adapter_type: str = Field(default="webhook")
    adapter_config: dict[str, Any] | None = None

    # --- Control plane: managed agent config ---
    llm_integration_id: int | None = None
    system_prompt: str | None = None
    methodology: str | None = None
    tool_ids: list[str] | None = None
    max_tokens: int | None = None
    enable_thinking: bool = False
    instruction_files: list[dict[str, Any]] | None = None

    # --- Control plane: orchestrator config ---
    sub_agent_ids: list[str] | None = None
    max_sub_agent_calls: int | None = None

    # --- Control plane: budget ---
    budget_monthly_cents: int = Field(default=0, ge=0)

    # --- Control plane: runtime limits ---
    heartbeat_interval_seconds: int | None = None
    max_concurrent_alerts: int = Field(default=1, ge=1)
    max_cost_per_alert_cents: int = Field(default=0, ge=0)
    max_investigation_minutes: int = Field(default=0, ge=0)
    stall_threshold: int = Field(default=0, ge=0)
    memory_promotion_requires_approval: bool = False

    @field_validator("trigger_filter")
    @classmethod
    def _validate_trigger_filter_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_SMALL, "trigger_filter")  # type: ignore[return-value]

    @model_validator(mode="after")
    def _validate_auth_header_pair(self) -> AgentRegistrationCreate:
        name_set = self.auth_header_name is not None
        value_set = self.auth_header_value is not None
        if name_set != value_set:
            raise ValueError(
                "auth_header_name and auth_header_value must both be provided or both be omitted"
            )
        return self


class AgentRegistrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    name: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def id(self) -> UUID:
        """Expose uuid as 'id' — the canonical external identifier for this agent."""
        return self.uuid
    description: str | None
    endpoint_url: str | None
    auth_header_name: str | None
    # auth_header_value is NEVER returned
    trigger_on_sources: list[str]
    trigger_on_severities: list[str]
    trigger_filter: dict[str, Any] | None
    timeout_seconds: int
    retry_count: int
    documentation: str | None
    created_at: datetime
    updated_at: datetime

    # --- Control plane: status ---
    status: str

    # --- Control plane: identity & type ---
    execution_mode: str
    agent_type: str
    role: str | None
    capabilities: dict[str, Any] | None

    # --- Control plane: adapter ---
    adapter_type: str
    adapter_config: dict[str, Any] | None

    # --- Control plane: managed agent config ---
    llm_integration_id: int | None
    system_prompt: str | None
    methodology: str | None
    tool_ids: list[str] | None
    max_tokens: int | None
    enable_thinking: bool
    instruction_files: list[dict[str, Any]] | None

    # --- Control plane: orchestrator config ---
    sub_agent_ids: list[str] | None
    max_sub_agent_calls: int | None

    # --- Control plane: budget ---
    budget_monthly_cents: int
    spent_monthly_cents: int
    budget_period_start: datetime | None

    # --- Control plane: runtime ---
    last_heartbeat_at: datetime | None
    heartbeat_interval_seconds: int | None
    max_concurrent_alerts: int
    max_cost_per_alert_cents: int
    max_investigation_minutes: int
    stall_threshold: int
    memory_promotion_requires_approval: bool


class AgentRegistrationPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    endpoint_url: str | None = None
    auth_header_name: str | None = None
    auth_header_value: str | None = None
    trigger_on_sources: list[str] | None = None
    trigger_on_severities: list[str] | None = None
    trigger_filter: dict[str, Any] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    retry_count: int | None = Field(default=None, ge=0, le=10)
    documentation: str | None = None

    # --- Control plane fields (all optional) ---
    execution_mode: str | None = None
    agent_type: str | None = None
    role: str | None = None
    capabilities: dict[str, Any] | None = None
    adapter_type: str | None = None
    adapter_config: dict[str, Any] | None = None
    llm_integration_id: int | None = None
    system_prompt: str | None = None
    methodology: str | None = None
    tool_ids: list[str] | None = None
    max_tokens: int | None = None
    enable_thinking: bool | None = None
    instruction_files: list[dict[str, Any]] | None = None
    sub_agent_ids: list[str] | None = None
    max_sub_agent_calls: int | None = None
    budget_monthly_cents: int | None = Field(default=None, ge=0)
    heartbeat_interval_seconds: int | None = None
    max_concurrent_alerts: int | None = Field(default=None, ge=1)
    max_cost_per_alert_cents: int | None = Field(default=None, ge=0)
    max_investigation_minutes: int | None = Field(default=None, ge=0)
    stall_threshold: int | None = Field(default=None, ge=0)
    memory_promotion_requires_approval: bool | None = None

    @field_validator("trigger_filter")
    @classmethod
    def _validate_trigger_filter_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_SMALL, "trigger_filter")  # type: ignore[return-value]


class AgentTestResponse(BaseModel):
    delivered: bool
    status_code: int | None = None
    duration_ms: int
    error: str | None = None


# ---------------------------------------------------------------------------
# Agent API Key schemas
# ---------------------------------------------------------------------------


class AgentKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class AgentKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class AgentKeyCreatedResponse(AgentKeyResponse):
    """Returned only on key creation — key is shown exactly once."""

    key: str  # plaintext key — never stored, shown once


# ---------------------------------------------------------------------------
# Agent lifecycle request schemas
# ---------------------------------------------------------------------------


class AgentPauseRequest(BaseModel):
    reason: str | None = None


class AgentBudgetUpdate(BaseModel):
    budget_monthly_cents: int = Field(ge=0)
    reset_spent: bool = False  # if True, also reset spent_monthly_cents=0 and period_start=now()


class AgentFileBody(BaseModel):
    content: str


class AgentFileResponse(BaseModel):
    path: str
    content: str
