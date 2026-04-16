"""Unit tests for health monitoring API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.schemas.health import (
    AgentFleetSummary,
    HealthMetricConfigCreate,
    HealthSourceCreate,
    HealthSourcePatch,
    HealthSourceResponse,
    HealthSourceTestResult,
)


class TestHealthSourceSchemas:
    """Validate Pydantic schemas for health sources."""

    def test_create_valid(self) -> None:
        body = HealthSourceCreate(
            name="Production AWS",
            provider="aws",
            config={"region": "us-east-1"},
            auth_config={"role_arn": "arn:aws:iam::123:role/Calseta", "external_id": "ext-123"},
            polling_interval_seconds=120,
        )
        assert body.provider == "aws"
        assert body.polling_interval_seconds == 120

    def test_create_invalid_provider(self) -> None:
        with pytest.raises(ValueError):
            HealthSourceCreate(
                name="Bad Provider",
                provider="gcp",
                config={},
            )

    def test_create_min_polling_interval(self) -> None:
        with pytest.raises(ValueError):
            HealthSourceCreate(
                name="Too fast",
                provider="aws",
                polling_interval_seconds=30,
            )

    def test_patch_partial(self) -> None:
        body = HealthSourcePatch(name="Updated Name")
        assert body.name == "Updated Name"
        assert body.config is None

    def test_response_from_attributes(self) -> None:
        resp = HealthSourceResponse(
            uuid=uuid4(),
            name="Test",
            provider="aws",
            is_active=True,
            config={"region": "us-east-1"},
            polling_interval_seconds=60,
            last_poll_at=None,
            last_poll_error=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            metric_count=3,
        )
        assert resp.metric_count == 3


class TestHealthMetricConfigSchemas:
    def test_create_valid(self) -> None:
        body = HealthMetricConfigCreate(
            display_name="ECS CPU Utilization",
            namespace="AWS/ECS",
            metric_name="CPUUtilization",
            dimensions={"ClusterName": "calseta", "ServiceName": "api"},
            statistic="Average",
            unit="Percent",
            category="compute",
            warning_threshold=70.0,
            critical_threshold=90.0,
        )
        assert body.statistic == "Average"

    def test_create_invalid_statistic(self) -> None:
        with pytest.raises(ValueError):
            HealthMetricConfigCreate(
                display_name="Bad",
                namespace="AWS/ECS",
                metric_name="CPUUtilization",
                statistic="Median",
            )

    def test_create_invalid_card_size(self) -> None:
        with pytest.raises(ValueError):
            HealthMetricConfigCreate(
                display_name="Bad",
                namespace="AWS/ECS",
                metric_name="CPUUtilization",
                card_size="huge",
            )


class TestAgentFleetSummary:
    def test_defaults(self) -> None:
        summary = AgentFleetSummary()
        assert summary.total_agents == 0
        assert summary.success_rate_7d == 0.0

    def test_with_data(self) -> None:
        summary = AgentFleetSummary(
            total_agents=5,
            active_agents=3,
            idle_agents=2,
            total_runs_7d=100,
            successful_runs_7d=95,
            failed_runs_7d=5,
            success_rate_7d=95.0,
            total_cost_mtd_cents=1500,
        )
        assert summary.success_rate_7d == 95.0


class TestHealthSourceTestResult:
    def test_success(self) -> None:
        result = HealthSourceTestResult(
            success=True,
            message="Connected to CloudWatch in us-east-1",
        )
        assert result.success is True

    def test_failure_with_details(self) -> None:
        result = HealthSourceTestResult(
            success=False,
            message="Access Denied",
            details={"error_type": "ClientError"},
        )
        assert result.details["error_type"] == "ClientError"
