"""Pydantic schemas for health monitoring API endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import JSONB_SIZE_MEDIUM, validate_jsonb_size

# ---------------------------------------------------------------------------
# Health Source
# ---------------------------------------------------------------------------


class HealthSourceCreate(BaseModel):
    """Request body for POST /v1/health-sources."""

    name: str = Field(..., min_length=1, max_length=200)
    provider: str = Field(..., pattern=r"^(aws|azure)$")
    config: dict[str, Any] = Field(default_factory=dict)
    auth_config: dict[str, Any] | None = None
    polling_interval_seconds: int = Field(default=60, ge=60, le=3600)
    is_active: bool = True

    @field_validator("config")
    @classmethod
    def _validate_config_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        return validate_jsonb_size(v, JSONB_SIZE_MEDIUM, "config")  # type: ignore[return-value]

    @field_validator("auth_config")
    @classmethod
    def _validate_auth_config_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_MEDIUM, "auth_config")  # type: ignore[return-value]


class HealthSourcePatch(BaseModel):
    """Request body for PATCH /v1/health-sources/{uuid}."""

    name: str | None = Field(None, min_length=1, max_length=200)
    config: dict[str, Any] | None = None
    auth_config: dict[str, Any] | None = None
    polling_interval_seconds: int | None = Field(None, ge=60, le=3600)
    is_active: bool | None = None


class HealthSourceResponse(BaseModel):
    """Response schema for health source endpoints."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    name: str
    provider: str
    is_active: bool
    config: dict[str, Any]
    polling_interval_seconds: int
    last_poll_at: datetime | None
    last_poll_error: str | None
    created_at: datetime
    updated_at: datetime
    metric_count: int = 0


# ---------------------------------------------------------------------------
# Health Metric Config
# ---------------------------------------------------------------------------


class HealthMetricConfigCreate(BaseModel):
    """Request body for POST /v1/health-sources/{uuid}/metrics."""

    display_name: str = Field(..., min_length=1, max_length=200)
    namespace: str = Field(..., min_length=1, max_length=200)
    metric_name: str = Field(..., min_length=1, max_length=200)
    dimensions: dict[str, str] = Field(default_factory=dict)
    statistic: str = Field(
        default="Average",
        pattern=r"^(Average|Sum|Maximum|Minimum|p99|p95|p90|p50)$",
    )
    unit: str = Field(default="None", max_length=50)
    category: str = Field(default="custom", max_length=50)
    card_size: str = Field(default="wide", pattern=r"^(small|wide|large)$")
    warning_threshold: float | None = None
    critical_threshold: float | None = None


class HealthMetricConfigPatch(BaseModel):
    """Request body for PATCH /v1/health-metrics-config/{uuid}."""

    display_name: str | None = Field(None, min_length=1, max_length=200)
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    is_active: bool | None = None
    card_size: str | None = Field(None, pattern=r"^(small|wide|large)$")


class HealthMetricConfigResponse(BaseModel):
    """Response schema for metric config endpoints."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    health_source_id: int
    display_name: str
    namespace: str
    metric_name: str
    dimensions: dict[str, Any]
    statistic: str
    unit: str
    category: str
    card_size: str
    warning_threshold: float | None
    critical_threshold: float | None
    is_active: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Health Metric Datapoints (time-series)
# ---------------------------------------------------------------------------


class HealthMetricDatapointResponse(BaseModel):
    """A single time-series datapoint."""

    value: float
    timestamp: datetime
    raw_datapoints: dict[str, Any] | None = None


class HealthMetricSeriesResponse(BaseModel):
    """Time-series data for a single metric config."""

    metric_config_id: int
    display_name: str
    datapoints: list[HealthMetricDatapointResponse]
    latest_value: float | None = None
    latest_timestamp: datetime | None = None


# ---------------------------------------------------------------------------
# Test Connection
# ---------------------------------------------------------------------------


class HealthSourceTestResult(BaseModel):
    """Result of POST /v1/health-sources/{uuid}/test."""

    success: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent Fleet Summary
# ---------------------------------------------------------------------------


class AgentFleetSummary(BaseModel):
    """Summary of agent fleet health for the Agents tab."""

    total_agents: int = 0
    active_agents: int = 0
    idle_agents: int = 0
    error_agents: int = 0
    total_runs_7d: int = 0
    successful_runs_7d: int = 0
    failed_runs_7d: int = 0
    success_rate_7d: float = 0.0
    total_cost_mtd_cents: int = 0
    active_investigations: int = 0
    stall_detections_7d: int = 0
