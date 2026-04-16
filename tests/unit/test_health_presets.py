"""Unit tests for health monitoring presets and auto-discovery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.health.base import DiscoveredResource
from app.integrations.health.presets import (
    AWS_PRESETS,
    AZURE_PRESETS,
    apply_preset_for_source,
    get_presets_for_provider,
    list_available_presets,
)


class TestPresetDefinitions:
    def test_aws_ecs_preset_has_three_metrics(self) -> None:
        assert len(AWS_PRESETS["ecs"]) == 3
        names = [m["metric_name"] for m in AWS_PRESETS["ecs"]]
        assert "CPUUtilization" in names
        assert "MemoryUtilization" in names

    def test_aws_rds_preset_has_four_metrics(self) -> None:
        assert len(AWS_PRESETS["rds"]) == 4

    def test_aws_sqs_preset_has_three_metrics(self) -> None:
        assert len(AWS_PRESETS["sqs"]) == 3

    def test_aws_alb_preset_has_four_metrics(self) -> None:
        assert len(AWS_PRESETS["alb"]) == 4

    def test_aws_lambda_preset_has_four_metrics(self) -> None:
        assert len(AWS_PRESETS["lambda"]) == 4

    def test_azure_app_service_preset(self) -> None:
        assert len(AZURE_PRESETS["app_service"]) == 3

    def test_azure_sql_preset(self) -> None:
        assert len(AZURE_PRESETS["azure_sql"]) == 3

    def test_azure_service_bus_preset(self) -> None:
        assert len(AZURE_PRESETS["service_bus"]) == 2

    def test_azure_application_gateway_preset(self) -> None:
        assert len(AZURE_PRESETS["application_gateway"]) == 3

    def test_all_presets_have_required_fields(self) -> None:
        required = {"display_name", "namespace", "metric_name", "statistic", "unit", "category"}
        for provider_presets in [AWS_PRESETS, AZURE_PRESETS]:
            for preset_name, templates in provider_presets.items():
                for t in templates:
                    missing = required - set(t.keys())
                    assert not missing, f"Preset {preset_name} template missing: {missing}"


class TestPresetHelpers:
    def test_get_presets_for_aws(self) -> None:
        presets = get_presets_for_provider("aws")
        assert "ecs" in presets
        assert "rds" in presets

    def test_get_presets_for_azure(self) -> None:
        presets = get_presets_for_provider("azure")
        assert "app_service" in presets

    def test_get_presets_for_unknown(self) -> None:
        presets = get_presets_for_provider("gcp")
        assert presets == {}

    def test_list_available_presets_aws(self) -> None:
        names = list_available_presets("aws")
        assert set(names) == {"ecs", "rds", "sqs", "alb", "lambda"}

    def test_list_available_presets_azure(self) -> None:
        names = list_available_presets("azure")
        assert set(names) == {"app_service", "azure_sql", "service_bus", "application_gateway"}


class TestApplyPreset:
    @pytest.mark.asyncio
    async def test_apply_ecs_preset_with_discovery(self) -> None:
        """ECS preset with 2 discovered services = 2*3 = 6 metric configs."""
        source = MagicMock()
        source.id = 1
        source.provider = "aws"
        source.config = {"region": "us-east-1"}

        source_repo = MagicMock()
        source_repo.decrypt_auth_config.return_value = {
            "role_arn": "arn:aws:iam::123:role/Test",
            "external_id": "ext-123",
        }

        config_repo = AsyncMock()
        created_configs = [MagicMock() for _ in range(6)]
        config_repo.create_batch.return_value = created_configs

        mock_provider = AsyncMock()
        mock_provider.discover_resources.return_value = [
            DiscoveredResource(
                resource_type="ecs_service",
                resource_id="calseta/api",
                display_name="api",
                dimensions={"ClusterName": "calseta", "ServiceName": "api"},
            ),
            DiscoveredResource(
                resource_type="ecs_service",
                resource_id="calseta/worker",
                display_name="worker",
                dimensions={"ClusterName": "calseta", "ServiceName": "worker"},
            ),
        ]

        with patch("app.integrations.health.presets.create_provider", return_value=mock_provider):
            result = await apply_preset_for_source(
                source=source,
                preset_name="ecs",
                config_repo=config_repo,
                source_repo=source_repo,
            )

        assert len(result) == 6
        # Verify batch was called with 6 configs (2 resources x 3 metrics)
        call_args = config_repo.create_batch.call_args[0][0]
        assert len(call_args) == 6
        # Check dimensions are from discovered resources
        assert call_args[0]["dimensions"]["ServiceName"] == "api"
        assert call_args[3]["dimensions"]["ServiceName"] == "worker"

    @pytest.mark.asyncio
    async def test_apply_preset_no_resources_fallback(self) -> None:
        """No resources discovered = create metrics without dimensions."""
        source = MagicMock()
        source.id = 1
        source.provider = "aws"
        source.config = {"region": "us-east-1"}

        source_repo = MagicMock()
        source_repo.decrypt_auth_config.return_value = {"role_arn": "arn:...", "external_id": "x"}

        config_repo = AsyncMock()
        config_repo.create_batch.return_value = [MagicMock() for _ in range(3)]

        mock_provider = AsyncMock()
        mock_provider.discover_resources.return_value = []

        with patch("app.integrations.health.presets.create_provider", return_value=mock_provider):
            result = await apply_preset_for_source(
                source=source,
                preset_name="ecs",
                config_repo=config_repo,
                source_repo=source_repo,
            )

        assert len(result) == 3  # 3 ECS metrics, no resources
        call_args = config_repo.create_batch.call_args[0][0]
        assert call_args[0]["dimensions"] == {}

    @pytest.mark.asyncio
    async def test_apply_unknown_preset_raises(self) -> None:
        source = MagicMock()
        source.provider = "aws"

        with pytest.raises(ValueError, match="Unknown preset"):
            await apply_preset_for_source(
                source=source,
                preset_name="nonexistent",
                config_repo=AsyncMock(),
                source_repo=MagicMock(),
            )

    @pytest.mark.asyncio
    async def test_apply_rds_preset(self) -> None:
        """RDS preset with 1 instance = 4 metric configs."""
        source = MagicMock()
        source.id = 1
        source.provider = "aws"
        source.config = {"region": "us-east-1"}

        source_repo = MagicMock()
        source_repo.decrypt_auth_config.return_value = {"role_arn": "arn:...", "external_id": "x"}

        config_repo = AsyncMock()
        config_repo.create_batch.return_value = [MagicMock() for _ in range(4)]

        mock_provider = AsyncMock()
        mock_provider.discover_resources.return_value = [
            DiscoveredResource(
                resource_type="rds_instance",
                resource_id="calseta-db",
                display_name="calseta-db",
                dimensions={"DBInstanceIdentifier": "calseta-db"},
            ),
        ]

        with patch("app.integrations.health.presets.create_provider", return_value=mock_provider):
            result = await apply_preset_for_source(
                source=source,
                preset_name="rds",
                config_repo=config_repo,
                source_repo=source_repo,
            )

        assert len(result) == 4
        call_args = config_repo.create_batch.call_args[0][0]
        assert all(c["dimensions"]["DBInstanceIdentifier"] == "calseta-db" for c in call_args)
