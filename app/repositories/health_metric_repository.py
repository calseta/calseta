"""Health metric repository — time-series data reads/writes for health_metrics table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select

from app.db.models.health_metric import HealthMetric
from app.repositories.base import BaseRepository


class HealthMetricRepository(BaseRepository[HealthMetric]):
    model = HealthMetric

    async def bulk_insert(
        self,
        datapoints: list[dict],
    ) -> int:
        """Insert multiple metric datapoints in a single flush. Returns count inserted."""
        objects = [HealthMetric(**dp) for dp in datapoints]
        self._db.add_all(objects)
        await self._db.flush()
        return len(objects)

    async def query_range(
        self,
        metric_config_id: int,
        *,
        start: datetime,
        end: datetime,
        limit: int = 1000,
    ) -> list[HealthMetric]:
        """Return datapoints for a metric config within a time range, ordered by timestamp."""
        stmt = (
            select(HealthMetric)
            .where(
                HealthMetric.metric_config_id == metric_config_id,
                HealthMetric.timestamp >= start,
                HealthMetric.timestamp <= end,
            )
            .order_by(HealthMetric.timestamp.asc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def query_range_multi(
        self,
        metric_config_ids: list[int],
        *,
        start: datetime,
        end: datetime,
        limit_per_metric: int = 500,
    ) -> dict[int, list[HealthMetric]]:
        """Return datapoints for multiple metric configs, grouped by config_id."""
        stmt = (
            select(HealthMetric)
            .where(
                HealthMetric.metric_config_id.in_(metric_config_ids),
                HealthMetric.timestamp >= start,
                HealthMetric.timestamp <= end,
            )
            .order_by(
                HealthMetric.metric_config_id,
                HealthMetric.timestamp.asc(),
            )
        )
        result = await self._db.execute(stmt)
        rows = list(result.scalars().all())

        grouped: dict[int, list[HealthMetric]] = {}
        for row in rows:
            bucket = grouped.setdefault(row.metric_config_id, [])
            if len(bucket) < limit_per_metric:
                bucket.append(row)
        return grouped

    async def get_latest(
        self,
        metric_config_id: int,
    ) -> HealthMetric | None:
        """Return the most recent datapoint for a metric config."""
        stmt = (
            select(HealthMetric)
            .where(HealthMetric.metric_config_id == metric_config_id)
            .order_by(HealthMetric.timestamp.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_before(
        self,
        cutoff: datetime,
        *,
        batch_size: int = 10_000,
    ) -> int:
        """Delete datapoints older than cutoff in batches. Returns total rows deleted."""
        total_deleted = 0
        while True:
            # Find IDs to delete in this batch
            subq = (
                select(HealthMetric.id)
                .where(HealthMetric.timestamp < cutoff)
                .limit(batch_size)
            )
            stmt = delete(HealthMetric).where(HealthMetric.id.in_(subq))
            result = await self._db.execute(stmt)
            batch_count = result.rowcount  # type: ignore[assignment]
            total_deleted += batch_count
            await self._db.flush()
            if batch_count < batch_size:
                break
        return total_deleted

    async def count_by_config(self, metric_config_id: int) -> int:
        """Return total datapoint count for a metric config."""
        result = await self._db.execute(
            select(func.count())
            .select_from(HealthMetric)
            .where(HealthMetric.metric_config_id == metric_config_id)
        )
        return result.scalar_one()  # type: ignore[return-value]
