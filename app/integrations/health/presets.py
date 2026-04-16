"""
Service presets — pre-configured metric definitions for common AWS and Azure services.

Each preset maps a service name to a list of metric config templates.
When applied, Calseta discovers resources via the provider and creates
metric configs with correct dimensions pre-populated.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.integrations.health.factory import ProviderNotAvailableError, create_provider

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# AWS Preset Definitions
# ---------------------------------------------------------------------------

AWS_PRESETS: dict[str, list[dict[str, Any]]] = {
    "ecs": [
        {
            "display_name": "CPU Utilization",
            "namespace": "AWS/ECS",
            "metric_name": "CPUUtilization",
            "statistic": "Average",
            "unit": "Percent",
            "category": "compute",
            "warning_threshold": 70.0,
            "critical_threshold": 90.0,
        },
        {
            "display_name": "Memory Utilization",
            "namespace": "AWS/ECS",
            "metric_name": "MemoryUtilization",
            "statistic": "Average",
            "unit": "Percent",
            "category": "compute",
            "warning_threshold": 75.0,
            "critical_threshold": 90.0,
        },
        {
            "display_name": "Running Task Count",
            "namespace": "AWS/ECS",
            "metric_name": "RunningTaskCount",
            "statistic": "Average",
            "unit": "Count",
            "category": "compute",
            "warning_threshold": None,
            "critical_threshold": None,
        },
    ],
    "rds": [
        {
            "display_name": "CPU Utilization",
            "namespace": "AWS/RDS",
            "metric_name": "CPUUtilization",
            "statistic": "Average",
            "unit": "Percent",
            "category": "database",
            "warning_threshold": 70.0,
            "critical_threshold": 90.0,
        },
        {
            "display_name": "Database Connections",
            "namespace": "AWS/RDS",
            "metric_name": "DatabaseConnections",
            "statistic": "Average",
            "unit": "Count",
            "category": "database",
            "warning_threshold": 80.0,
            "critical_threshold": 95.0,
        },
        {
            "display_name": "Free Storage Space",
            "namespace": "AWS/RDS",
            "metric_name": "FreeStorageSpace",
            "statistic": "Average",
            "unit": "Bytes",
            "category": "database",
            "warning_threshold": None,
            "critical_threshold": None,
        },
        {
            "display_name": "Read Latency",
            "namespace": "AWS/RDS",
            "metric_name": "ReadLatency",
            "statistic": "Average",
            "unit": "Seconds",
            "category": "database",
            "warning_threshold": 0.020,
            "critical_threshold": 0.050,
        },
    ],
    "sqs": [
        {
            "display_name": "Queue Depth",
            "namespace": "AWS/SQS",
            "metric_name": "ApproximateNumberOfMessagesVisible",
            "statistic": "Sum",
            "unit": "Count",
            "category": "queue",
            "warning_threshold": 100.0,
            "critical_threshold": 1000.0,
        },
        {
            "display_name": "Age of Oldest Message",
            "namespace": "AWS/SQS",
            "metric_name": "ApproximateAgeOfOldestMessage",
            "statistic": "Maximum",
            "unit": "Seconds",
            "category": "queue",
            "warning_threshold": 300.0,
            "critical_threshold": 900.0,
        },
        {
            "display_name": "Messages Received",
            "namespace": "AWS/SQS",
            "metric_name": "NumberOfMessagesReceived",
            "statistic": "Sum",
            "unit": "Count",
            "category": "queue",
            "warning_threshold": None,
            "critical_threshold": None,
        },
    ],
    "alb": [
        {
            "display_name": "Request Count",
            "namespace": "AWS/ApplicationELB",
            "metric_name": "RequestCount",
            "statistic": "Sum",
            "unit": "Count",
            "category": "network",
            "warning_threshold": None,
            "critical_threshold": None,
        },
        {
            "display_name": "Target Response Time",
            "namespace": "AWS/ApplicationELB",
            "metric_name": "TargetResponseTime",
            "statistic": "p99",
            "unit": "Seconds",
            "category": "network",
            "warning_threshold": 1.0,
            "critical_threshold": 5.0,
        },
        {
            "display_name": "HTTP 5xx Count",
            "namespace": "AWS/ApplicationELB",
            "metric_name": "HTTPCode_ELB_5XX_Count",
            "statistic": "Sum",
            "unit": "Count",
            "category": "network",
            "warning_threshold": 10.0,
            "critical_threshold": 50.0,
        },
        {
            "display_name": "Healthy Host Count",
            "namespace": "AWS/ApplicationELB",
            "metric_name": "HealthyHostCount",
            "statistic": "Minimum",
            "unit": "Count",
            "category": "network",
            "warning_threshold": None,
            "critical_threshold": 0.0,
        },
    ],
    "lambda": [
        {
            "display_name": "Invocations",
            "namespace": "AWS/Lambda",
            "metric_name": "Invocations",
            "statistic": "Sum",
            "unit": "Count",
            "category": "compute",
            "warning_threshold": None,
            "critical_threshold": None,
        },
        {
            "display_name": "Errors",
            "namespace": "AWS/Lambda",
            "metric_name": "Errors",
            "statistic": "Sum",
            "unit": "Count",
            "category": "compute",
            "warning_threshold": 5.0,
            "critical_threshold": 20.0,
        },
        {
            "display_name": "Duration",
            "namespace": "AWS/Lambda",
            "metric_name": "Duration",
            "statistic": "p99",
            "unit": "Milliseconds",
            "category": "compute",
            "warning_threshold": None,
            "critical_threshold": None,
        },
        {
            "display_name": "Throttles",
            "namespace": "AWS/Lambda",
            "metric_name": "Throttles",
            "statistic": "Sum",
            "unit": "Count",
            "category": "compute",
            "warning_threshold": 1.0,
            "critical_threshold": 10.0,
        },
    ],
}


# ---------------------------------------------------------------------------
# Azure Preset Definitions
# ---------------------------------------------------------------------------

AZURE_PRESETS: dict[str, list[dict[str, Any]]] = {
    "app_service": [
        {
            "display_name": "CPU Percentage",
            "namespace": "Microsoft.Web/sites",
            "metric_name": "CpuPercentage",
            "statistic": "Average",
            "unit": "Percent",
            "category": "compute",
            "warning_threshold": 70.0,
            "critical_threshold": 90.0,
        },
        {
            "display_name": "Memory Percentage",
            "namespace": "Microsoft.Web/sites",
            "metric_name": "MemoryPercentage",
            "statistic": "Average",
            "unit": "Percent",
            "category": "compute",
            "warning_threshold": 75.0,
            "critical_threshold": 90.0,
        },
        {
            "display_name": "HTTP 5xx Errors",
            "namespace": "Microsoft.Web/sites",
            "metric_name": "Http5xx",
            "statistic": "Sum",
            "unit": "Count",
            "category": "compute",
            "warning_threshold": 10.0,
            "critical_threshold": 50.0,
        },
    ],
    "azure_sql": [
        {
            "display_name": "CPU Percentage",
            "namespace": "Microsoft.Sql/servers/databases",
            "metric_name": "cpu_percent",
            "statistic": "Average",
            "unit": "Percent",
            "category": "database",
            "warning_threshold": 70.0,
            "critical_threshold": 90.0,
        },
        {
            "display_name": "DTU Percentage",
            "namespace": "Microsoft.Sql/servers/databases",
            "metric_name": "dtu_consumption_percent",
            "statistic": "Average",
            "unit": "Percent",
            "category": "database",
            "warning_threshold": 80.0,
            "critical_threshold": 95.0,
        },
        {
            "display_name": "Storage Percentage",
            "namespace": "Microsoft.Sql/servers/databases",
            "metric_name": "storage_percent",
            "statistic": "Average",
            "unit": "Percent",
            "category": "database",
            "warning_threshold": 80.0,
            "critical_threshold": 95.0,
        },
    ],
    "service_bus": [
        {
            "display_name": "Active Messages",
            "namespace": "Microsoft.ServiceBus/namespaces",
            "metric_name": "ActiveMessages",
            "statistic": "Average",
            "unit": "Count",
            "category": "queue",
            "warning_threshold": 100.0,
            "critical_threshold": 1000.0,
        },
        {
            "display_name": "Dead-lettered Messages",
            "namespace": "Microsoft.ServiceBus/namespaces",
            "metric_name": "DeadletteredMessages",
            "statistic": "Average",
            "unit": "Count",
            "category": "queue",
            "warning_threshold": 10.0,
            "critical_threshold": 100.0,
        },
    ],
    "application_gateway": [
        {
            "display_name": "Total Requests",
            "namespace": "Microsoft.Network/applicationGateways",
            "metric_name": "TotalRequests",
            "statistic": "Sum",
            "unit": "Count",
            "category": "network",
            "warning_threshold": None,
            "critical_threshold": None,
        },
        {
            "display_name": "Failed Requests",
            "namespace": "Microsoft.Network/applicationGateways",
            "metric_name": "FailedRequests",
            "statistic": "Sum",
            "unit": "Count",
            "category": "network",
            "warning_threshold": 10.0,
            "critical_threshold": 50.0,
        },
        {
            "display_name": "Response Status 5xx",
            "namespace": "Microsoft.Network/applicationGateways",
            "metric_name": "ResponseStatus",
            "statistic": "Sum",
            "unit": "Count",
            "category": "network",
            "warning_threshold": 10.0,
            "critical_threshold": 50.0,
        },
    ],
}


def get_presets_for_provider(provider: str) -> dict[str, list[dict[str, Any]]]:
    """Return preset definitions for a provider type."""
    if provider == "aws":
        return AWS_PRESETS
    elif provider == "azure":
        return AZURE_PRESETS
    return {}


def list_available_presets(provider: str) -> list[str]:
    """Return list of available preset names for a provider."""
    return list(get_presets_for_provider(provider).keys())


async def apply_preset_for_source(
    *,
    source: Any,
    preset_name: str,
    config_repo: Any,
    source_repo: Any,
) -> list[Any]:
    """
    Apply a service preset to a health source with auto-discovery.

    1. Look up preset metric templates
    2. Discover resources via the provider (get dimensions)
    3. Create metric configs for each discovered resource x metric template

    Returns list of created HealthMetricConfig objects.
    """
    presets = get_presets_for_provider(source.provider)
    templates = presets.get(preset_name)
    if not templates:
        raise ValueError(
            f"Unknown preset {preset_name!r} for provider {source.provider!r}. "
            f"Available: {', '.join(presets.keys())}"
        )

    # Decrypt auth and create provider for discovery
    auth_config = source_repo.decrypt_auth_config(source)
    try:
        provider = create_provider(source.provider, source.config, auth_config)
    except ProviderNotAvailableError as exc:
        logger.warning("presets.provider_not_available", error=str(exc))
        raise

    # Discover resources
    resources = await provider.discover_resources(preset_name)
    if not resources:
        logger.info(
            "presets.no_resources_discovered",
            preset=preset_name,
            provider=source.provider,
        )
        # Fall back: create metrics without specific dimensions
        configs_to_create = [
            {
                "health_source_id": source.id,
                "display_name": t["display_name"],
                "namespace": t["namespace"],
                "metric_name": t["metric_name"],
                "dimensions": {},
                "statistic": t["statistic"],
                "unit": t["unit"],
                "category": t["category"],
                "card_size": "wide",
                "warning_threshold": t.get("warning_threshold"),
                "critical_threshold": t.get("critical_threshold"),
            }
            for t in templates
        ]
        return await config_repo.create_batch(configs_to_create)

    # Create metric configs for each resource x template
    configs_to_create = []
    for resource in resources:
        for template in templates:
            configs_to_create.append(
                {
                    "health_source_id": source.id,
                    "display_name": f"{template['display_name']}",
                    "namespace": template["namespace"],
                    "metric_name": template["metric_name"],
                    "dimensions": resource.dimensions,
                    "statistic": template["statistic"],
                    "unit": template["unit"],
                    "category": template["category"],
                    "card_size": "wide",
                    "warning_threshold": template.get("warning_threshold"),
                    "critical_threshold": template.get("critical_threshold"),
                }
            )

    created = await config_repo.create_batch(configs_to_create)
    logger.info(
        "presets.applied",
        preset=preset_name,
        resources_discovered=len(resources),
        configs_created=len(created),
    )
    return created
