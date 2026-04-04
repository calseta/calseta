"""Routine Scheduler API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RoutineStatus:
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ALL = ["active", "paused", "completed"]


class ConcurrencyPolicy:
    SKIP_IF_ACTIVE = "skip_if_active"
    COALESCE_IF_ACTIVE = "coalesce_if_active"
    ALWAYS_RUN = "always_run"
    ALL = ["skip_if_active", "coalesce_if_active", "always_run"]


class CatchUpPolicy:
    SKIP_MISSED = "skip_missed"
    CATCH_UP = "catch_up"
    ALL = ["skip_missed", "catch_up"]


class TriggerKind:
    CRON = "cron"
    WEBHOOK = "webhook"
    MANUAL = "manual"
    ALL = ["cron", "webhook", "manual"]


class RoutineRunStatus:
    RECEIVED = "received"
    ENQUEUED = "enqueued"
    RUNNING = "running"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    ALL = ["received", "enqueued", "running", "completed", "skipped", "failed"]


class TriggerCreate(BaseModel):
    kind: str = Field(..., description="cron, webhook, or manual")
    cron_expression: str | None = None
    timezone: str | None = "UTC"
    webhook_replay_window_sec: int | None = 300
    is_active: bool = True


class TriggerPatch(BaseModel):
    cron_expression: str | None = None
    timezone: str | None = None
    webhook_replay_window_sec: int | None = None
    is_active: bool | None = None


class TriggerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    kind: str
    cron_expression: str | None
    timezone: str | None
    webhook_public_id: str | None
    next_run_at: datetime | None
    last_fired_at: datetime | None
    is_active: bool
    created_at: datetime


class RoutineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    agent_registration_uuid: UUID
    concurrency_policy: str = "skip_if_active"
    catch_up_policy: str = "skip_missed"
    task_template: dict[str, Any] = Field(...)
    max_consecutive_failures: int = Field(default=3, ge=1)
    triggers: list[TriggerCreate] = Field(default_factory=list)


class RoutinePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    concurrency_policy: str | None = None
    catch_up_policy: str | None = None
    task_template: dict[str, Any] | None = None
    max_consecutive_failures: int | None = Field(default=None, ge=1)


class RoutineInvokeRequest(BaseModel):
    payload: dict[str, Any] | None = None


class RoutineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    name: str
    description: str | None
    status: str
    concurrency_policy: str
    catch_up_policy: str
    task_template: dict[str, Any]
    max_consecutive_failures: int
    consecutive_failures: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    agent_registration_uuid: UUID | None = None
    triggers: list[TriggerResponse] = Field(default_factory=list)


class RoutineRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    source: str
    status: str
    trigger_payload: dict[str, Any] | None
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    trigger_uuid: UUID | None = None
