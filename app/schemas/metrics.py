"""Metric response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class MetricsSummaryAlerts(BaseModel):
    total: int
    active: int
    by_severity: dict[str, int]
    false_positive_rate: float
    mttd_seconds: float | None
    mtta_seconds: float | None
    mttt_seconds: float | None
    mttc_seconds: float | None


class MetricsSummaryWorkflows(BaseModel):
    total_configured: int
    executions: int
    success_rate: float
    estimated_time_saved_hours: float


class MetricsSummaryApprovals(BaseModel):
    pending: int
    approved_last_30_days: int
    approval_rate: float
    median_response_time_minutes: float | None


class MetricsSummaryResponse(BaseModel):
    period: str = "last_30_days"
    alerts: MetricsSummaryAlerts
    workflows: MetricsSummaryWorkflows
    approvals: MetricsSummaryApprovals


class WorkflowMetricsResponse(BaseModel):
    period_from: datetime
    period_to: datetime
    total_configured: int  # all workflows regardless of state
    workflows_by_type: dict[str, int]  # grouped by workflow_type
    workflow_run_count: int  # total runs in time window
    workflow_success_rate: float  # successful / total runs (0.0 if no runs)
    workflow_runs_over_time: list[dict[str, Any]]  # [{"date": "...", "count": N}]
    time_saved_hours: float  # sum(successful_runs * workflow.time_saved_minutes) / 60
    most_executed_workflows: list[dict[str, Any]]  # [{"uuid": str, "name": str, "run_count": N}]


class AlertMetricsResponse(BaseModel):
    period_from: datetime
    period_to: datetime
    total_alerts: int
    alerts_by_status: dict[str, int]
    alerts_by_severity: dict[str, int]
    alerts_by_source: dict[str, int]
    alerts_over_time: list[dict[str, Any]]  # [{"date": "2026-01-01", "count": N}]
    false_positive_rate: float  # 0.0–1.0
    mean_time_to_enrich: float | None  # seconds, null if no data
    mean_time_to_detect: float | None  # MTTD seconds, null if occurred_at always null
    mean_time_to_acknowledge: float | None  # MTTA seconds
    mean_time_to_triage: float | None  # MTTT seconds
    mean_time_to_conclusion: float | None  # MTTC seconds
    active_alerts_by_severity: dict[str, int]  # only Open/Triaging/Escalated
    top_detection_rules: list[dict[str, Any]]  # [{"uuid": str, "name": str, "count": N}]
    enrichment_coverage: float  # 0.0–1.0 (alerts with is_enriched=True / total)
