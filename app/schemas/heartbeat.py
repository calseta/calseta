"""Heartbeat and heartbeat-run API schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class HeartbeatSource(StrEnum):
    SCHEDULER = "scheduler"
    MANUAL = "manual"
    DISPATCH = "dispatch"
    CALLBACK = "callback"


class HeartbeatStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class HeartbeatRequest(BaseModel):
    assignment_id: UUID | None = None
    status: str = "running"  # "running", "idle", "completed", "error"
    progress_note: str | None = None
    findings_count: int = 0
    actions_proposed: int = 0


class HeartbeatResponse(BaseModel):
    heartbeat_run_id: UUID
    acknowledged_at: datetime
    agent_status: str
    supervisor_directive: str | None  # null | "pause" | "terminate"


class HeartbeatRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    agent_registration_id: int
    source: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None
    alerts_processed: int
    actions_proposed: int
    context_snapshot: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    # Runtime hardening fields
    process_pid: int | None = None
    error_code: str | None = None
    log_store: str = "local_file"
    log_ref: str | None = None
    log_sha256: str | None = None
    log_bytes: int | None = None
    invocation_source: str | None = None
