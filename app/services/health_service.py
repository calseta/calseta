"""Health monitoring service — orchestrates metric polling and source management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.health.base import MetricQuery
from app.integrations.health.factory import ProviderNotAvailableError, create_provider
from app.repositories.health_metric_repository import HealthMetricRepository
from app.repositories.health_source_repository import (
    HealthMetricConfigRepository,
    HealthSourceRepository,
)

logger = structlog.get_logger(__name__)


class HealthService:
    """Business logic for health monitoring. Injected with a DB session."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._source_repo = HealthSourceRepository(db)
        self._config_repo = HealthMetricConfigRepository(db)
        self._metric_repo = HealthMetricRepository(db)

    async def poll_all_sources(self) -> dict[str, Any]:
        """Poll all active health sources. Returns a summary of results."""
        sources = await self._source_repo.list_active()
        summary: dict[str, Any] = {
            "sources_polled": 0,
            "sources_failed": 0,
            "metrics_collected": 0,
        }

        for source in sources:
            try:
                count = await self._poll_source(source)
                summary["sources_polled"] += 1
                summary["metrics_collected"] += count
            except Exception as exc:
                summary["sources_failed"] += 1
                logger.error(
                    "health_service.poll_source_failed",
                    source_id=source.id,
                    source_name=source.name,
                    error=str(exc),
                )
                await self._source_repo.update_poll_status(
                    source,
                    last_poll_at=datetime.now(UTC),
                    last_poll_error=str(exc),
                )

        return summary

    async def _poll_source(self, source: Any) -> int:
        """Poll a single health source. Returns count of metrics collected."""
        # Decrypt auth config
        auth_config = self._source_repo.decrypt_auth_config(source)

        # Create provider
        try:
            provider = create_provider(source.provider, source.config, auth_config)
        except ProviderNotAvailableError as exc:
            await self._source_repo.update_poll_status(
                source,
                last_poll_at=datetime.now(UTC),
                last_poll_error=str(exc),
            )
            logger.warning(
                "health_service.provider_not_available",
                source_id=source.id,
                provider=source.provider,
                error=str(exc),
            )
            return 0

        # Get active metric configs for this source
        configs = await self._config_repo.list_by_source(
            source.id, active_only=True
        )
        if not configs:
            await self._source_repo.update_poll_status(
                source,
                last_poll_at=datetime.now(UTC),
            )
            return 0

        # Build queries
        queries = [
            MetricQuery(
                config_id=c.id,
                namespace=c.namespace,
                metric_name=c.metric_name,
                dimensions=c.dimensions or {},
                statistic=c.statistic,
                unit=c.unit,
            )
            for c in configs
        ]

        # Fetch metrics (provider never raises)
        datapoints = await provider.fetch_metrics(
            queries, timedelta(minutes=5)
        )

        # Bulk insert to DB
        if datapoints:
            rows = [
                {
                    "metric_config_id": dp.metric_config_id,
                    "value": dp.value,
                    "timestamp": dp.timestamp,
                    "raw_datapoints": dp.raw_datapoints,
                }
                for dp in datapoints
            ]
            await self._metric_repo.bulk_insert(rows)

        # Update poll status
        await self._source_repo.update_poll_status(
            source,
            last_poll_at=datetime.now(UTC),
            last_poll_error=None,
        )

        logger.info(
            "health_service.source_polled",
            source_id=source.id,
            source_name=source.name,
            metrics_collected=len(datapoints),
        )
        return len(datapoints)

    async def test_source_connection(self, source_id: int) -> dict[str, Any]:
        """Test connection for a health source. Returns result dict."""
        source = await self._source_repo.get_by_id(source_id)
        if source is None:
            return {"success": False, "message": "Source not found"}

        auth_config = self._source_repo.decrypt_auth_config(source)

        try:
            provider = create_provider(source.provider, source.config, auth_config)
        except (ProviderNotAvailableError, ValueError) as exc:
            return {"success": False, "message": str(exc)}

        result = await provider.test_connection()
        return {
            "success": result.success,
            "message": result.message,
            "details": result.details,
        }

    async def cleanup_old_metrics(self, retention_days: int) -> int:
        """Delete metrics older than retention_days. Returns count deleted."""
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        deleted = await self._metric_repo.delete_before(cutoff)
        logger.info(
            "health_service.retention_cleanup",
            retention_days=retention_days,
            rows_deleted=deleted,
        )
        return deleted
