"""Pydantic schemas for agent invocation endpoints — Phase 5 multi-agent orchestration."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class InvocationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class DelegateTaskRequest(BaseModel):
    """Delegate a single task to a specialist agent."""

    alert_id: UUID
    child_agent_id: UUID  # UUID of the target specialist
    task_description: str
    input_context: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    timeout_seconds: int = 300
    assignment_id: UUID | None = None  # parent orchestrator's assignment


class DelegateParallelRequest(BaseModel):
    """Delegate multiple tasks simultaneously (2–10)."""

    alert_id: UUID
    tasks: list[ParallelTask]
    assignment_id: UUID | None = None  # parent orchestrator's assignment

    @field_validator("tasks")
    @classmethod
    def validate_task_count(cls, v: list[ParallelTask]) -> list[ParallelTask]:
        if len(v) < 2 or len(v) > 10:
            raise ValueError("parallel delegation requires 2–10 tasks")
        return v


class ParallelTask(BaseModel):
    """A single task within a parallel delegation batch."""

    child_agent_id: UUID
    task_description: str
    input_context: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    timeout_seconds: int = 300


class AgentInvocationResponse(BaseModel):
    """Invocation record as returned by GET /v1/invocations/{id}."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    parent_agent_id: int
    child_agent_id: int | None
    alert_id: int
    assignment_id: int | None
    task_description: str
    input_context: dict[str, Any] | None
    output_schema: dict[str, Any] | None
    status: str
    result: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    cost_cents: int
    timeout_seconds: int
    task_queue_id: str | None
    created_at: datetime
    updated_at: datetime


class DelegateTaskResponse(BaseModel):
    """Response for a single delegation request."""

    invocation_id: UUID
    status: InvocationStatus
    child_agent_id: UUID | None = None


class DelegateParallelResponse(BaseModel):
    """Response for a parallel delegation request."""

    invocations: list[DelegateTaskResponse]


class AgentCatalogEntry(BaseModel):
    """Summary of a specialist agent for orchestrator context injection."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    name: str
    role: str | None
    agent_type: str
    status: str
    capabilities: dict[str, Any] | None
    description: str | None
