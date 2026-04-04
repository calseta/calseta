"""Cost event and budget API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CostEventCreate(BaseModel):
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_cents: int
    alert_id: UUID | None = None
    heartbeat_run_id: UUID | None = None
    billing_type: str = "api"  # "api" or "subscription"


class CostEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_registration_id: int
    llm_integration_id: int | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_cents: int
    billing_type: str
    occurred_at: datetime
    created_at: datetime


class AgentBudgetStatus(BaseModel):
    monthly_cents: int
    spent_cents: int
    remaining_cents: int
    hard_stop_triggered: bool


class CostReportResponse(BaseModel):
    cost_event_id: int
    agent_budget: AgentBudgetStatus


class CostSummaryResponse(BaseModel):
    total_cost_cents: int
    total_input_tokens: int
    total_output_tokens: int
    by_billing_type: dict[str, int]  # {"api": 1234, "subscription": 0}
    period_start: datetime | None
    period_end: datetime | None
