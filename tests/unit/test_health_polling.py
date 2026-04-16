"""Unit tests for health metric polling task and service."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.health.base import (
    HealthConnectionResult,
    MetricDatapoint,
)
from app.services.health_service import HealthService


def _make_source(
    *,
    id: int = 1,
    name: str = "Test AWS",
    provider: str = "aws",
    is_active: bool = True,
    config: dict | None = None,
    auth_config_encrypted: str | None = None,
) -> MagicMock:
    source = MagicMock()
    source.id = id
    source.name = name
    source.provider = provider
    source.is_active = is_active
    source.config = config or {"region": "us-east-1"}
    source.auth_config_encrypted = auth_config_encrypted
    return source


def _make_metric_config(
    *,
    id: int = 1,
    health_source_id: int = 1,
    namespace: str = "AWS/ECS",
    metric_name: str = "CPUUtilization",
    dimensions: dict | None = None,
    statistic: str = "Average",
    unit: str = "Percent",
    is_active: bool = True,
) -> MagicMock:
    config = MagicMock()
    config.id = id
    config.health_source_id = health_source_id
    config.namespace = namespace
    config.metric_name = metric_name
    config.dimensions = dimensions or {"ClusterName": "calseta", "ServiceName": "api"}
    config.statistic = statistic
    config.unit = unit
    config.is_active = is_active
    return config


class TestHealthServicePollAll:
    @pytest.mark.asyncio
    async def test_poll_no_active_sources(self) -> None:
        """No sources → no polling."""
        db = AsyncMock()
        svc = HealthService(db)

        with patch.object(svc._source_repo, "list_active", return_value=[]):
            summary = await svc.poll_all_sources()

        assert summary["sources_polled"] == 0
        assert summary["metrics_collected"] == 0

    @pytest.mark.asyncio
    async def test_poll_source_collects_metrics(self) -> None:
        """Active source with metrics → datapoints persisted."""
        db = AsyncMock()
        svc = HealthService(db)
        source = _make_source()
        configs = [_make_metric_config()]
        now = datetime.now(UTC)

        mock_provider = AsyncMock()
        mock_provider.fetch_metrics.return_value = [
            MetricDatapoint(metric_config_id=1, value=23.5, timestamp=now)
        ]

        with (
            patch.object(svc._source_repo, "list_active", return_value=[source]),
            patch.object(svc._source_repo, "decrypt_auth_config", return_value={"role_arn": "arn:...", "external_id": "x"}),
            patch.object(svc._source_repo, "update_poll_status", new_callable=AsyncMock),
            patch.object(svc._config_repo, "list_by_source", return_value=configs),
            patch.object(svc._metric_repo, "bulk_insert", new_callable=AsyncMock, return_value=1),
            patch("app.services.health_service.create_provider", return_value=mock_provider),
        ):
            summary = await svc.poll_all_sources()

        assert summary["sources_polled"] == 1
        assert summary["metrics_collected"] == 1

    @pytest.mark.asyncio
    async def test_poll_source_failure_isolated(self) -> None:
        """A failing source does not block other sources."""
        db = AsyncMock()
        svc = HealthService(db)
        good_source = _make_source(id=1, name="Good")
        bad_source = _make_source(id=2, name="Bad")
        now = datetime.now(UTC)

        mock_provider = AsyncMock()
        mock_provider.fetch_metrics.return_value = [
            MetricDatapoint(metric_config_id=1, value=10.0, timestamp=now)
        ]

        call_count = 0

        async def fake_poll(src: MagicMock) -> int:
            nonlocal call_count
            call_count += 1
            if src.id == 2:
                raise Exception("Provider unreachable")
            return 1

        with (
            patch.object(svc._source_repo, "list_active", return_value=[good_source, bad_source]),
            patch.object(svc, "_poll_source", side_effect=fake_poll),
            patch.object(svc._source_repo, "update_poll_status", new_callable=AsyncMock),
        ):
            summary = await svc.poll_all_sources()

        assert summary["sources_polled"] == 1
        assert summary["sources_failed"] == 1

    @pytest.mark.asyncio
    async def test_poll_source_no_configs(self) -> None:
        """Source with no metric configs → polled but zero metrics."""
        db = AsyncMock()
        svc = HealthService(db)
        source = _make_source()

        with (
            patch.object(svc._source_repo, "list_active", return_value=[source]),
            patch.object(svc._source_repo, "decrypt_auth_config", return_value={}),
            patch.object(svc._source_repo, "update_poll_status", new_callable=AsyncMock),
            patch.object(svc._config_repo, "list_by_source", return_value=[]),
            patch("app.services.health_service.create_provider", side_effect=Exception("should not be called")),
        ):
            # create_provider should not be called since we skip before it
            # Actually it IS called before configs check. Let me fix the mock.
            pass

        # Re-test: provider is created before configs check in the current flow
        mock_provider = AsyncMock()
        with (
            patch.object(svc._source_repo, "list_active", return_value=[source]),
            patch.object(svc._source_repo, "decrypt_auth_config", return_value={"role_arn": "arn:...", "external_id": "x"}),
            patch.object(svc._source_repo, "update_poll_status", new_callable=AsyncMock),
            patch.object(svc._config_repo, "list_by_source", return_value=[]),
            patch("app.services.health_service.create_provider", return_value=mock_provider),
        ):
            summary = await svc.poll_all_sources()

        assert summary["sources_polled"] == 1
        assert summary["metrics_collected"] == 0


class TestHealthServiceTestConnection:
    @pytest.mark.asyncio
    async def test_source_not_found(self) -> None:
        db = AsyncMock()
        svc = HealthService(db)

        with patch.object(svc._source_repo, "get_by_id", return_value=None):
            result = await svc.test_source_connection(999)

        assert result["success"] is False
        assert "not found" in result["message"]

    @pytest.mark.asyncio
    async def test_connection_success(self) -> None:
        db = AsyncMock()
        svc = HealthService(db)
        source = _make_source()

        mock_provider = AsyncMock()
        mock_provider.test_connection.return_value = HealthConnectionResult.ok("All good")

        with (
            patch.object(svc._source_repo, "get_by_id", return_value=source),
            patch.object(svc._source_repo, "decrypt_auth_config", return_value={"role_arn": "arn:...", "external_id": "x"}),
            patch("app.services.health_service.create_provider", return_value=mock_provider),
        ):
            result = await svc.test_source_connection(1)

        assert result["success"] is True


class TestHealthServiceRetention:
    @pytest.mark.asyncio
    async def test_cleanup_delegates_to_repo(self) -> None:
        db = AsyncMock()
        svc = HealthService(db)

        with patch.object(svc._metric_repo, "delete_before", new_callable=AsyncMock, return_value=500):
            deleted = await svc.cleanup_old_metrics(30)

        assert deleted == 500
