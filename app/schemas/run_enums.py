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
    # LLM provider / CLI failure codes (S12)
    LLM_QUOTA_EXCEEDED = "llm_quota_exceeded"
    LLM_RATE_LIMITED = "llm_rate_limited"
    LLM_AUTH_FAILED = "llm_auth_failed"
    LLM_PROVIDER_ERROR = "llm_provider_error"
    LLM_CLI_MISSING = "llm_cli_missing"
