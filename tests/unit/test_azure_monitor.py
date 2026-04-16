"""Unit tests for Azure Monitor health metrics provider."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.health.azure_monitor import AzureMonitorProvider
from app.integrations.health.base import MetricQuery


class TestAzureMonitorProvider:
    """Tests with fully mocked azure SDK."""

    def _make_provider(
        self,
        auth_method: str = "managed_identity",
    ) -> AzureMonitorProvider:
        return AzureMonitorProvider(
            subscription_id="sub-12345",
            auth_method=auth_method,
            tenant_id="tenant-123",
            client_id="client-456",
            client_secret="secret-789",
        )

    @patch("app.integrations.health.azure_monitor.AzureMonitorProvider._get_credential")
    @patch("app.integrations.health.azure_monitor.AzureMonitorProvider._get_metrics_client")
    @pytest.mark.asyncio
    async def test_test_connection_success(
        self, mock_get_client: MagicMock, mock_get_cred: MagicMock
    ) -> None:
        mock_credential = MagicMock()
        mock_token = MagicMock()
        mock_token.token = "fake-token"
        mock_credential.get_token.return_value = mock_token
        mock_get_cred.return_value = mock_credential

        provider = self._make_provider()
        result = await provider.test_connection()

        assert result.success is True
        assert "Connected" in result.message

    @patch("app.integrations.health.azure_monitor.AzureMonitorProvider._get_metrics_client")
    @patch("app.integrations.health.azure_monitor.AzureMonitorProvider._get_credential")
    @pytest.mark.asyncio
    async def test_test_connection_failure(
        self, mock_get_cred: MagicMock, mock_get_client: MagicMock
    ) -> None:
        mock_credential = MagicMock()
        mock_credential.get_token.side_effect = Exception("Invalid credentials")
        mock_get_cred.return_value = mock_credential

        provider = self._make_provider()
        result = await provider.test_connection()

        assert result.success is False
        assert "Invalid credentials" in result.message

    @pytest.mark.asyncio
    async def test_fetch_metrics_empty(self) -> None:
        provider = self._make_provider()
        results = await provider.fetch_metrics([], timedelta(minutes=5))
        assert results == []

    @patch("app.integrations.health.azure_monitor.AzureMonitorProvider._get_metrics_client")
    @pytest.mark.asyncio
    async def test_fetch_metrics_error_returns_empty(
        self, mock_get_client: MagicMock
    ) -> None:
        mock_get_client.side_effect = Exception("SDK not available")
        provider = self._make_provider()
        results = await provider.fetch_metrics(
            [MetricQuery(1, "Microsoft.Web/sites", "CpuPercentage", {"resource_id": "/sub/123"}, "Average", "Percent")],
            timedelta(minutes=5),
        )
        assert results == []

    @patch("app.integrations.health.azure_monitor.AzureMonitorProvider._get_metrics_client")
    @pytest.mark.asyncio
    async def test_fetch_metrics_single(self, mock_get_client: MagicMock) -> None:
        """Verify a single metric is fetched correctly with mocked response."""
        now = datetime.now(UTC)

        # Mock the MetricsQueryClient response structure
        mock_data_point = MagicMock()
        mock_data_point.average = 42.5
        mock_data_point.timestamp = now

        mock_ts_element = MagicMock()
        mock_ts_element.data = [mock_data_point]

        mock_metric = MagicMock()
        mock_metric.timeseries = [mock_ts_element]

        mock_response = MagicMock()
        mock_response.metrics = [mock_metric]

        mock_client = MagicMock()
        mock_client.query_resource.return_value = mock_response
        mock_get_client.return_value = mock_client

        # Need to mock the MetricAggregationType import inside _fetch_single
        with patch.dict("sys.modules", {"azure.monitor.query": MagicMock()}):
            provider = self._make_provider()
            provider._metrics_client = mock_client
            results = await provider.fetch_metrics(
                [
                    MetricQuery(
                        config_id=1,
                        namespace="Microsoft.Web/sites",
                        metric_name="CpuPercentage",
                        dimensions={"resource_id": "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Web/sites/myapp"},
                        statistic="Average",
                        unit="Percent",
                    )
                ],
                timedelta(minutes=5),
            )

        assert len(results) == 1
        assert results[0].value == 42.5
        assert results[0].metric_config_id == 1

    @patch("app.integrations.health.azure_monitor.AzureMonitorProvider._get_resource_client")
    @pytest.mark.asyncio
    async def test_discover_app_services(self, mock_get_rc: MagicMock) -> None:
        mock_resource = MagicMock()
        mock_resource.id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Web/sites/myapp"
        mock_resource.name = "myapp"
        mock_resource.location = "eastus"
        mock_resource.kind = "app"

        mock_client = MagicMock()
        mock_client.resources.list.return_value = [mock_resource]
        mock_get_rc.return_value = mock_client

        provider = self._make_provider()
        resources = await provider.discover_resources("app_service")

        assert len(resources) == 1
        assert resources[0].resource_type == "app_service"
        assert resources[0].display_name == "myapp"
        assert "resource_id" in resources[0].dimensions

    @patch("app.integrations.health.azure_monitor.AzureMonitorProvider._get_resource_client")
    @pytest.mark.asyncio
    async def test_discover_azure_sql(self, mock_get_rc: MagicMock) -> None:
        mock_resource = MagicMock()
        mock_resource.id = "/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Sql/servers/srv/databases/calsetadb"
        mock_resource.name = "calsetadb"
        mock_resource.location = "eastus"

        mock_client = MagicMock()
        mock_client.resources.list.return_value = [mock_resource]
        mock_get_rc.return_value = mock_client

        provider = self._make_provider()
        resources = await provider.discover_resources("azure_sql")

        assert len(resources) == 1
        assert resources[0].resource_type == "azure_sql"

    @pytest.mark.asyncio
    async def test_discover_unknown_preset(self) -> None:
        provider = self._make_provider()
        # Need to mock _get_resource_client since it would fail without azure SDK
        with patch.object(provider, "_get_resource_client", return_value=MagicMock()):
            resources = await provider.discover_resources("unknown_service")
        assert resources == []

    @patch("app.integrations.health.azure_monitor.AzureMonitorProvider._get_resource_client")
    @pytest.mark.asyncio
    async def test_discover_error_returns_empty(self, mock_get_rc: MagicMock) -> None:
        mock_get_rc.side_effect = Exception("Azure SDK error")
        provider = self._make_provider()
        resources = await provider.discover_resources("app_service")
        assert resources == []

    def test_provider_type(self) -> None:
        provider = self._make_provider()
        assert provider.provider_type == "azure"

    @patch("app.integrations.health.azure_monitor.AzureMonitorProvider._get_credential")
    def test_service_principal_credential(self, mock_get_cred: MagicMock) -> None:
        """Service principal auth should use ClientSecretCredential."""
        # We can't test the actual import but we verify the path
        provider = self._make_provider(auth_method="service_principal")
        assert provider._auth_method == "service_principal"
        assert provider._tenant_id == "tenant-123"
        assert provider._client_id == "client-456"
        assert provider._client_secret == "secret-789"
