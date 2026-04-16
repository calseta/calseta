"""
Health metrics provider factory.

Creates the correct provider implementation based on the health source's
``provider`` field and decrypted auth config.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.integrations.health.base import HealthMetricsProvider

logger = structlog.get_logger(__name__)

# Supported provider types
_SUPPORTED_PROVIDERS = {"aws", "azure"}


class ProviderNotAvailableError(Exception):
    """Raised when a cloud SDK is not installed."""


def create_provider(
    provider_type: str,
    config: dict[str, Any],
    auth_config: dict[str, Any],
) -> HealthMetricsProvider:
    """
    Instantiate a HealthMetricsProvider for the given type.

    Args:
        provider_type: "aws" or "azure".
        config: Provider-specific configuration (region, subscription_id, etc.).
        auth_config: Decrypted credentials (role_arn, external_id, client_secret, etc.).

    Raises:
        ProviderNotAvailableError: If the required SDK is not installed.
        ValueError: If the provider type is not supported.
    """
    if provider_type == "aws":
        return _create_aws_provider(config, auth_config)
    elif provider_type == "azure":
        return _create_azure_provider(config, auth_config)
    else:
        raise ValueError(
            f"Unsupported health provider type: {provider_type!r}. "
            f"Supported: {', '.join(sorted(_SUPPORTED_PROVIDERS))}"
        )


def _create_aws_provider(
    config: dict[str, Any],
    auth_config: dict[str, Any],
) -> HealthMetricsProvider:
    try:
        import boto3  # type: ignore[import-untyped]  # noqa: F401
    except ImportError as exc:
        raise ProviderNotAvailableError(
            "boto3 is required for AWS CloudWatch health monitoring. "
            "Install with: pip install calseta[aws]"
        ) from exc

    from app.integrations.health.aws_cloudwatch import AWSCloudWatchProvider

    return AWSCloudWatchProvider(
        role_arn=auth_config.get("role_arn", ""),
        external_id=auth_config.get("external_id", ""),
        region=config.get("region", "us-east-1"),
    )


def _create_azure_provider(
    config: dict[str, Any],
    auth_config: dict[str, Any],
) -> HealthMetricsProvider:
    try:
        import azure.monitor.query  # type: ignore[import-untyped]  # noqa: F401
    except ImportError as exc:
        raise ProviderNotAvailableError(
            "azure-monitor-query is required for Azure Monitor health monitoring. "
            "Install with: pip install calseta[azure]"
        ) from exc

    from app.integrations.health.azure_monitor import AzureMonitorProvider

    return AzureMonitorProvider(
        subscription_id=config.get("subscription_id", ""),
        auth_method=auth_config.get("auth_method", "managed_identity"),
        tenant_id=auth_config.get("tenant_id", ""),
        client_id=auth_config.get("client_id", ""),
        client_secret=auth_config.get("client_secret", ""),
    )
