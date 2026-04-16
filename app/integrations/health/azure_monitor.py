"""
Azure Monitor health metrics provider.

Uses azure-monitor-query SDK with DefaultAzureCredential (Managed Identity)
or ClientSecretCredential (Service Principal).
Graceful when azure SDK is not installed — import errors are caught at init time.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.integrations.health.base import (
    DiscoveredResource,
    HealthConnectionResult,
    HealthMetricsProvider,
    MetricDatapoint,
    MetricQuery,
)

logger = structlog.get_logger(__name__)

# Map our statistic names to Azure aggregation types
_STAT_MAP: dict[str, str] = {
    "Average": "average",
    "Sum": "total",
    "Maximum": "maximum",
    "Minimum": "minimum",
    "Count": "count",
}


class AzureMonitorProvider(HealthMetricsProvider):
    """Azure Monitor metrics via azure-monitor-query SDK."""

    provider_type = "azure"

    def __init__(
        self,
        *,
        subscription_id: str,
        auth_method: str = "managed_identity",
        tenant_id: str = "",
        client_id: str = "",
        client_secret: str = "",
    ) -> None:
        self._subscription_id = subscription_id
        self._auth_method = auth_method
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret

        self._credential: Any = None
        self._metrics_client: Any = None

    def _get_credential(self) -> Any:
        """Get or create Azure credential."""
        if self._credential is not None:
            return self._credential

        try:
            if self._auth_method == "service_principal":
                from azure.identity import ClientSecretCredential  # type: ignore[import-untyped]

                self._credential = ClientSecretCredential(
                    tenant_id=self._tenant_id,
                    client_id=self._client_id,
                    client_secret=self._client_secret,
                )
            else:
                from azure.identity import DefaultAzureCredential  # type: ignore[import-untyped]

                self._credential = DefaultAzureCredential()

            return self._credential
        except ImportError as exc:
            raise ImportError(
                "azure-identity is required for Azure Monitor health monitoring. "
                "Install with: pip install calseta[azure]"
            ) from exc

    def _get_metrics_client(self) -> Any:
        """Get or create MetricsQueryClient."""
        if self._metrics_client is not None:
            return self._metrics_client

        try:
            from azure.monitor.query import MetricsQueryClient  # type: ignore[import-untyped]

            credential = self._get_credential()
            self._metrics_client = MetricsQueryClient(credential)
            return self._metrics_client
        except ImportError as exc:
            raise ImportError(
                "azure-monitor-query is required for Azure Monitor health monitoring. "
                "Install with: pip install calseta[azure]"
            ) from exc

    def _get_resource_client(self) -> Any:
        """Get Azure Resource Management client for discovery."""
        try:
            from azure.mgmt.resource import ResourceManagementClient  # type: ignore[import-untyped]

            credential = self._get_credential()
            return ResourceManagementClient(credential, self._subscription_id)
        except ImportError as exc:
            raise ImportError(
                "azure-mgmt-resource is required for Azure resource discovery. "
                "Install with: pip install calseta[azure]"
            ) from exc

    async def test_connection(self) -> HealthConnectionResult:
        try:
            self._get_metrics_client()
            credential = self._get_credential()
            # Get a token to verify credentials
            token = credential.get_token("https://management.azure.com/.default")
            if token:
                return HealthConnectionResult.ok(
                    f"Connected to Azure Monitor for subscription {self._subscription_id}"
                )
            return HealthConnectionResult.fail("Could not obtain Azure credential token")
        except ImportError as exc:
            return HealthConnectionResult.fail(str(exc))
        except Exception as exc:
            logger.warning(
                "azure_monitor.test_connection_failed",
                error=str(exc),
                subscription_id=self._subscription_id,
            )
            return HealthConnectionResult.fail(
                f"Failed to connect: {exc}",
                error_type=type(exc).__name__,
            )

    async def fetch_metrics(
        self,
        queries: list[MetricQuery],
        period: timedelta,
    ) -> list[MetricDatapoint]:
        if not queries:
            return []

        try:
            client = self._get_metrics_client()
        except (ImportError, Exception) as exc:
            logger.error("azure_monitor.fetch_metrics_client_failed", error=str(exc))
            return []

        results: list[MetricDatapoint] = []
        now = datetime.now(UTC)
        start = now - period

        # Group queries by resource_id (namespace used as resource path for Azure)
        for query in queries:
            try:
                dp = self._fetch_single(client, query, start, now)
                if dp:
                    results.append(dp)
            except Exception as exc:
                logger.error(
                    "azure_monitor.fetch_single_failed",
                    error=str(exc),
                    metric_name=query.metric_name,
                    namespace=query.namespace,
                )

        return results

    def _fetch_single(
        self,
        client: Any,
        query: MetricQuery,
        start: datetime,
        end: datetime,
    ) -> MetricDatapoint | None:
        """Fetch a single metric from Azure Monitor."""

        # Map statistic to Azure aggregation
        aggregation = _STAT_MAP.get(query.statistic, "average")

        # For Azure, the resource_id is stored in dimensions
        resource_id = query.dimensions.get("resource_id", "")
        if not resource_id:
            # Build resource ID from namespace and dimensions
            resource_id = query.namespace

        try:
            response = client.query_resource(
                resource_uri=resource_id,
                metric_names=[query.metric_name],
                timespan=(start, end),
                granularity=timedelta(minutes=5),
                aggregations=[aggregation],
            )

            for metric in response.metrics:
                for ts_element in reversed(metric.timeseries):
                    for data_point in reversed(ts_element.data):
                        value = getattr(data_point, aggregation, None)
                        if value is not None:
                            return MetricDatapoint(
                                metric_config_id=query.config_id,
                                value=float(value),
                                timestamp=data_point.timestamp,
                            )
        except Exception as exc:
            logger.warning(
                "azure_monitor.query_resource_failed",
                error=str(exc),
                resource_id=resource_id,
                metric_name=query.metric_name,
            )

        return None

    async def discover_resources(
        self,
        preset: str,
    ) -> list[DiscoveredResource]:
        try:
            resource_client = self._get_resource_client()
        except (ImportError, Exception) as exc:
            logger.error("azure_monitor.discover_import_error", error=str(exc))
            return []

        try:
            discover_fn = {
                "app_service": self._discover_app_services,
                "azure_sql": self._discover_azure_sql,
                "service_bus": self._discover_service_bus,
                "application_gateway": self._discover_app_gateways,
            }.get(preset)

            if discover_fn is None:
                logger.warning("azure_monitor.unknown_preset", preset=preset)
                return []

            return discover_fn(resource_client)
        except Exception as exc:
            logger.error(
                "azure_monitor.discover_failed",
                error=str(exc),
                preset=preset,
            )
            return []

    def _discover_app_services(self, client: Any) -> list[DiscoveredResource]:
        resources: list[DiscoveredResource] = []
        for resource in client.resources.list(filter="resourceType eq 'Microsoft.Web/sites'"):
            resources.append(
                DiscoveredResource(
                    resource_type="app_service",
                    resource_id=resource.id,
                    display_name=resource.name,
                    dimensions={"resource_id": resource.id},
                    metadata={
                        "location": resource.location,
                        "kind": getattr(resource, "kind", ""),
                    },
                )
            )
        return resources

    def _discover_azure_sql(self, client: Any) -> list[DiscoveredResource]:
        resources: list[DiscoveredResource] = []
        for resource in client.resources.list(
            filter="resourceType eq 'Microsoft.Sql/servers/databases'"
        ):
            resources.append(
                DiscoveredResource(
                    resource_type="azure_sql",
                    resource_id=resource.id,
                    display_name=resource.name,
                    dimensions={"resource_id": resource.id},
                    metadata={"location": resource.location},
                )
            )
        return resources

    def _discover_service_bus(self, client: Any) -> list[DiscoveredResource]:
        resources: list[DiscoveredResource] = []
        for resource in client.resources.list(
            filter="resourceType eq 'Microsoft.ServiceBus/namespaces'"
        ):
            resources.append(
                DiscoveredResource(
                    resource_type="service_bus",
                    resource_id=resource.id,
                    display_name=resource.name,
                    dimensions={"resource_id": resource.id},
                    metadata={"location": resource.location},
                )
            )
        return resources

    def _discover_app_gateways(self, client: Any) -> list[DiscoveredResource]:
        resources: list[DiscoveredResource] = []
        for resource in client.resources.list(
            filter="resourceType eq 'Microsoft.Network/applicationGateways'"
        ):
            resources.append(
                DiscoveredResource(
                    resource_type="application_gateway",
                    resource_id=resource.id,
                    display_name=resource.name,
                    dimensions={"resource_id": resource.id},
                    metadata={"location": resource.location},
                )
            )
        return resources
