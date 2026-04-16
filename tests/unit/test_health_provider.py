"""Unit tests for health metrics provider ABC and AWS CloudWatch implementation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.health.aws_cloudwatch import AWSCloudWatchProvider
from app.integrations.health.base import (
    HealthConnectionResult,
    MetricDatapoint,
    MetricQuery,
)
from app.integrations.health.factory import ProviderNotAvailableError, create_provider

# ---------------------------------------------------------------------------
# ABC contract
# ---------------------------------------------------------------------------


class TestHealthConnectionResult:
    def test_ok(self) -> None:
        result = HealthConnectionResult.ok("Connected")
        assert result.success is True
        assert result.message == "Connected"

    def test_fail(self) -> None:
        result = HealthConnectionResult.fail("Timeout", error_type="TimeoutError")
        assert result.success is False
        assert result.message == "Timeout"
        assert result.details["error_type"] == "TimeoutError"


class TestMetricDatapoint:
    def test_creation(self) -> None:
        now = datetime.now(UTC)
        dp = MetricDatapoint(
            metric_config_id=1,
            value=42.5,
            timestamp=now,
        )
        assert dp.metric_config_id == 1
        assert dp.value == 42.5
        assert dp.timestamp == now
        assert dp.raw_datapoints is None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_unsupported_provider(self) -> None:
        with pytest.raises(ValueError, match="Unsupported health provider type"):
            create_provider("gcp", {}, {})

    @patch.dict("sys.modules", {"boto3": None})
    def test_aws_missing_boto3(self) -> None:
        with pytest.raises(ProviderNotAvailableError, match="boto3"):
            create_provider("aws", {"region": "us-east-1"}, {"role_arn": "arn:...", "external_id": "abc"})

    @patch.dict("sys.modules", {"azure.monitor.query": None, "azure": None})
    def test_azure_missing_sdk(self) -> None:
        with pytest.raises(ProviderNotAvailableError, match="azure-monitor-query"):
            create_provider("azure", {}, {})

    def test_aws_provider_created(self) -> None:
        """When boto3 is importable, factory returns AWSCloudWatchProvider."""
        fake_boto3 = MagicMock()
        with patch.dict("sys.modules", {"boto3": fake_boto3}):
            provider = create_provider(
                "aws",
                {"region": "us-west-2"},
                {"role_arn": "arn:aws:iam::123:role/Test", "external_id": "ext-123"},
            )
            assert isinstance(provider, AWSCloudWatchProvider)
            assert provider.provider_type == "aws"


# ---------------------------------------------------------------------------
# AWS CloudWatch Provider
# ---------------------------------------------------------------------------


class TestAWSCloudWatchProvider:
    """Tests with fully mocked boto3."""

    def _make_provider(self, *, use_role: bool = True) -> AWSCloudWatchProvider:
        if use_role:
            return AWSCloudWatchProvider(
                role_arn="arn:aws:iam::123456789012:role/CalsetaHealth",
                external_id="calseta-test-ext",
                region="us-east-1",
            )
        return AWSCloudWatchProvider(region="us-east-1")

    def test_ambient_credentials_mode(self) -> None:
        """No role_arn = ambient credentials (ECS task role, env vars, etc.)."""
        provider = self._make_provider(use_role=False)
        assert provider._use_role_assumption is False

    def test_role_assumption_mode(self) -> None:
        """role_arn provided = STS AssumeRole mode."""
        provider = self._make_provider(use_role=True)
        assert provider._use_role_assumption is True

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_test_connection_success(self, mock_get_boto3: MagicMock) -> None:
        mock_boto3 = MagicMock()
        mock_get_boto3.return_value = mock_boto3

        # Mock STS assume_role
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIA...",
                "SecretAccessKey": "secret",
                "SessionToken": "token",
            }
        }
        # Mock CloudWatch list_metrics
        mock_cw = MagicMock()
        mock_cw.list_metrics.return_value = {
            "Metrics": [{"MetricName": "CPUUtilization"}]
        }

        def client_factory(service, **kwargs):  # type: ignore[no-untyped-def]
            if service == "sts":
                return mock_sts
            if service == "cloudwatch":
                return mock_cw
            return MagicMock()

        mock_boto3.client.side_effect = client_factory

        provider = self._make_provider()
        result = await provider.test_connection()

        assert result.success is True
        assert "Connected" in result.message

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_test_connection_failure(self, mock_get_boto3: MagicMock) -> None:
        mock_boto3 = MagicMock()
        mock_get_boto3.return_value = mock_boto3

        mock_sts = MagicMock()
        mock_sts.assume_role.side_effect = Exception("Access Denied")
        mock_boto3.client.return_value = mock_sts

        provider = self._make_provider()
        result = await provider.test_connection()

        assert result.success is False
        assert "Access Denied" in result.message

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_fetch_metrics_batching(self, mock_get_boto3: MagicMock) -> None:
        mock_boto3 = MagicMock()
        mock_get_boto3.return_value = mock_boto3

        # STS
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIA...",
                "SecretAccessKey": "secret",
                "SessionToken": "token",
            }
        }

        now = datetime.now(UTC)
        mock_cw = MagicMock()
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {
                    "Id": "m0",
                    "Values": [23.5],
                    "Timestamps": [now],
                },
                {
                    "Id": "m1",
                    "Values": [78.2],
                    "Timestamps": [now],
                },
            ]
        }

        def client_factory(service, **kwargs):  # type: ignore[no-untyped-def]
            if service == "sts":
                return mock_sts
            if service == "cloudwatch":
                return mock_cw
            return MagicMock()

        mock_boto3.client.side_effect = client_factory

        provider = self._make_provider()
        queries = [
            MetricQuery(
                config_id=1,
                namespace="AWS/ECS",
                metric_name="CPUUtilization",
                dimensions={"ClusterName": "calseta", "ServiceName": "api"},
                statistic="Average",
                unit="Percent",
            ),
            MetricQuery(
                config_id=2,
                namespace="AWS/ECS",
                metric_name="MemoryUtilization",
                dimensions={"ClusterName": "calseta", "ServiceName": "api"},
                statistic="Average",
                unit="Percent",
            ),
        ]

        results = await provider.fetch_metrics(queries, timedelta(minutes=5))

        assert len(results) == 2
        assert results[0].metric_config_id == 1
        assert results[0].value == 23.5
        assert results[1].metric_config_id == 2
        assert results[1].value == 78.2
        mock_cw.get_metric_data.assert_called_once()

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_fetch_metrics_empty(self, mock_get_boto3: MagicMock) -> None:
        provider = self._make_provider()
        results = await provider.fetch_metrics([], timedelta(minutes=5))
        assert results == []

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_fetch_metrics_error_returns_empty(self, mock_get_boto3: MagicMock) -> None:
        mock_get_boto3.side_effect = Exception("Connection lost")
        provider = self._make_provider()
        results = await provider.fetch_metrics(
            [MetricQuery(1, "AWS/ECS", "CPUUtilization", {}, "Average", "Percent")],
            timedelta(minutes=5),
        )
        assert results == []

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_discover_ecs(self, mock_get_boto3: MagicMock) -> None:
        mock_boto3 = MagicMock()
        mock_get_boto3.return_value = mock_boto3

        # STS
        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIA...",
                "SecretAccessKey": "secret",
                "SessionToken": "token",
            }
        }

        mock_ecs = MagicMock()
        mock_ecs.list_clusters.return_value = {
            "clusterArns": ["arn:aws:ecs:us-east-1:123:cluster/calseta"]
        }
        mock_ecs.describe_clusters.return_value = {
            "clusters": [{"clusterName": "calseta"}]
        }
        mock_ecs.list_services.return_value = {
            "serviceArns": [
                "arn:aws:ecs:us-east-1:123:service/calseta/api",
                "arn:aws:ecs:us-east-1:123:service/calseta/worker",
            ]
        }
        mock_ecs.describe_services.return_value = {
            "services": [
                {"serviceName": "api", "desiredCount": 2, "runningCount": 2},
                {"serviceName": "worker", "desiredCount": 1, "runningCount": 1},
            ]
        }

        def client_factory(service, **kwargs):  # type: ignore[no-untyped-def]
            if service == "sts":
                return mock_sts
            if service == "ecs":
                return mock_ecs
            return MagicMock()

        mock_boto3.client.side_effect = client_factory

        provider = self._make_provider()
        resources = await provider.discover_resources("ecs")

        assert len(resources) == 2
        assert resources[0].resource_type == "ecs_service"
        assert resources[0].dimensions["ClusterName"] == "calseta"
        assert resources[0].dimensions["ServiceName"] == "api"
        assert resources[1].dimensions["ServiceName"] == "worker"

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_discover_rds(self, mock_get_boto3: MagicMock) -> None:
        mock_boto3 = MagicMock()
        mock_get_boto3.return_value = mock_boto3

        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIA...",
                "SecretAccessKey": "secret",
                "SessionToken": "token",
            }
        }

        mock_rds = MagicMock()
        mock_rds.describe_db_instances.return_value = {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "calseta-db",
                    "Engine": "postgres",
                    "DBInstanceClass": "db.t3.medium",
                    "DBInstanceStatus": "available",
                }
            ]
        }

        def client_factory(service, **kwargs):  # type: ignore[no-untyped-def]
            if service == "sts":
                return mock_sts
            if service == "rds":
                return mock_rds
            return MagicMock()

        mock_boto3.client.side_effect = client_factory

        provider = self._make_provider()
        resources = await provider.discover_resources("rds")

        assert len(resources) == 1
        assert resources[0].resource_type == "rds_instance"
        assert resources[0].dimensions["DBInstanceIdentifier"] == "calseta-db"

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_discover_unknown_preset(self, mock_get_boto3: MagicMock) -> None:
        provider = self._make_provider()
        resources = await provider.discover_resources("unknown_service")
        assert resources == []

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_discover_error_returns_empty(self, mock_get_boto3: MagicMock) -> None:
        mock_boto3 = MagicMock()
        mock_get_boto3.return_value = mock_boto3

        mock_sts = MagicMock()
        mock_sts.assume_role.side_effect = Exception("STS error")
        mock_boto3.client.return_value = mock_sts

        provider = self._make_provider()
        resources = await provider.discover_resources("ecs")
        assert resources == []

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_sts_credential_caching(self, mock_get_boto3: MagicMock) -> None:
        """STS credentials should be cached across calls."""
        mock_boto3 = MagicMock()
        mock_get_boto3.return_value = mock_boto3

        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "AKIA...",
                "SecretAccessKey": "secret",
                "SessionToken": "token",
            }
        }

        mock_cw = MagicMock()
        mock_cw.list_metrics.return_value = {"Metrics": []}

        def client_factory(service, **kwargs):  # type: ignore[no-untyped-def]
            if service == "sts":
                return mock_sts
            if service == "cloudwatch":
                return mock_cw
            return MagicMock()

        mock_boto3.client.side_effect = client_factory

        provider = self._make_provider()
        await provider.test_connection()
        await provider.test_connection()

        # STS should only be called once (credentials cached)
        mock_sts.assume_role.assert_called_once()

    @patch("app.integrations.health.aws_cloudwatch.AWSCloudWatchProvider._get_boto3")
    @pytest.mark.asyncio
    async def test_ambient_mode_skips_sts(self, mock_get_boto3: MagicMock) -> None:
        """In ambient mode, no STS calls are made — boto3 uses default chain."""
        mock_boto3 = MagicMock()
        mock_get_boto3.return_value = mock_boto3

        mock_cw = MagicMock()
        mock_cw.list_metrics.return_value = {"Metrics": [{"MetricName": "CPUUtilization"}]}
        mock_boto3.client.return_value = mock_cw

        provider = self._make_provider(use_role=False)
        result = await provider.test_connection()

        assert result.success is True
        assert "ambient credentials" in result.message
        # boto3.client should be called directly (cloudwatch only), never STS
        calls = [c[0][0] for c in mock_boto3.client.call_args_list]
        assert "sts" not in calls
        assert "cloudwatch" in calls
