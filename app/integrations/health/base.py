"""
HealthMetricsProvider — abstract interface for cloud metric providers.

All providers must follow these contracts:
  - ``fetch_metrics()`` MUST NEVER RAISE. Catch all exceptions and return
    an empty list with the error logged.
  - ``test_connection()`` returns a HealthConnectionResult (success or failure).
  - ``discover_resources()`` returns discovered resources for a preset name.

Providers are optional dependencies — if the cloud SDK (boto3 / azure) is not
installed, the factory returns a clear error at source creation time.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any


@dataclass
class MetricDatapoint:
    """A single metric value with timestamp."""

    metric_config_id: int
    value: float
    timestamp: datetime
    raw_datapoints: dict[str, Any] | None = None


@dataclass
class HealthConnectionResult:
    """Result of a test_connection() call."""

    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str = "Connection successful") -> HealthConnectionResult:
        return cls(success=True, message=message)

    @classmethod
    def fail(cls, message: str, **details: Any) -> HealthConnectionResult:
        return cls(success=False, message=message, details=details)


@dataclass
class DiscoveredResource:
    """A cloud resource discovered for preset auto-configuration."""

    resource_type: str  # "ecs_service", "rds_instance", "sqs_queue", etc.
    resource_id: str  # service name, instance id, queue name
    display_name: str
    dimensions: dict[str, str]  # CloudWatch dimensions for this resource
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MetricQuery:
    """A single metric to fetch — maps to a HealthMetricConfig row."""

    config_id: int
    namespace: str
    metric_name: str
    dimensions: dict[str, str]
    statistic: str  # "Average", "Sum", "Maximum", "Minimum", "p99"
    unit: str


class HealthMetricsProvider(ABC):
    """
    Abstract base for cloud metric providers.

    Subclass and implement ``test_connection()``, ``fetch_metrics()``,
    and ``discover_resources()``.
    """

    provider_type: str  # "aws", "azure"

    @abstractmethod
    async def test_connection(self) -> HealthConnectionResult:
        """
        Verify that the provider can connect to the cloud API.

        Must never raise — catch exceptions and return HealthConnectionResult.fail().
        """

    @abstractmethod
    async def fetch_metrics(
        self,
        queries: list[MetricQuery],
        period: timedelta,
    ) -> list[MetricDatapoint]:
        """
        Fetch metric data for the given queries over the specified period.

        Must never raise — catch exceptions, log the error, and return
        whatever datapoints were successfully fetched.

        Args:
            queries: List of metrics to fetch.
            period: How far back to look (e.g. timedelta(minutes=5)).

        Returns:
            List of MetricDatapoint — one per query with the latest value.
        """

    @abstractmethod
    async def discover_resources(
        self,
        preset: str,
    ) -> list[DiscoveredResource]:
        """
        Discover cloud resources for a given preset (e.g. "ecs", "rds").

        Must never raise — catch exceptions and return empty list.

        Args:
            preset: The preset name (e.g. "ecs", "rds", "sqs", "alb", "lambda").

        Returns:
            List of DiscoveredResource with dimensions pre-populated.
        """
