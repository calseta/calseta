"""Enums for HeartbeatRun state machine."""

from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class InvocationSource(StrEnum):
    ALERT = "alert"
    ROUTINE = "routine"
    ON_DEMAND = "on_demand"
    ISSUE = "issue"
    DELEGATION = "delegation"
    COMMENT = "comment"


class RunErrorCode(StrEnum):
    PROCESS_LOST = "process_lost"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"
    ADAPTER_FAILED = "adapter_failed"
    CANCELLED = "cancelled"
