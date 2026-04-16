"""Health source repository — CRUD for health_sources and health_metrics_config tables."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select

from app.auth.encryption import decrypt_value, encrypt_value
from app.db.models.health_metric_config import HealthMetricConfig
from app.db.models.health_source import HealthSource
from app.repositories.base import BaseRepository

_UNSET = object()  # sentinel for "not provided" (distinct from None)


class HealthSourceRepository(BaseRepository[HealthSource]):
    model = HealthSource

    async def create(
        self,
        *,
        name: str,
        provider: str,
        config: dict[str, Any],
        auth_config: dict[str, Any] | None = None,
        polling_interval_seconds: int = 60,
        is_active: bool = True,
    ) -> HealthSource:
        encrypted = encrypt_value(json.dumps(auth_config)) if auth_config else None
        source = HealthSource(
            uuid=uuid.uuid4(),
            name=name,
            provider=provider,
            config=config,
            auth_config_encrypted=encrypted,
            polling_interval_seconds=max(polling_interval_seconds, 60),
            is_active=is_active,
        )
        self._db.add(source)
        return await self.flush_and_refresh(source)

    async def patch(
        self,
        source: HealthSource,
        *,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        auth_config: dict[str, Any] | None = None,
        polling_interval_seconds: int | None = None,
        is_active: bool | None = None,
    ) -> HealthSource:
        if name is not None:
            source.name = name
        if config is not None:
            source.config = config
        if auth_config is not None:
            source.auth_config_encrypted = encrypt_value(json.dumps(auth_config))
        if polling_interval_seconds is not None:
            source.polling_interval_seconds = max(polling_interval_seconds, 60)
        if is_active is not None:
            source.is_active = is_active
        return await self.flush_and_refresh(source)

    async def list_active(self) -> list[HealthSource]:
        result = await self._db.execute(
            select(HealthSource).where(HealthSource.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def update_poll_status(
        self,
        source: HealthSource,
        *,
        last_poll_at: Any,
        last_poll_error: str | None = None,
    ) -> HealthSource:
        source.last_poll_at = last_poll_at
        source.last_poll_error = last_poll_error
        return await self.flush_and_refresh(source)

    def decrypt_auth_config(self, source: HealthSource) -> dict[str, Any]:
        if not source.auth_config_encrypted:
            return {}
        return json.loads(decrypt_value(source.auth_config_encrypted))  # type: ignore[arg-type]


class HealthMetricConfigRepository(BaseRepository[HealthMetricConfig]):
    model = HealthMetricConfig

    async def create(
        self,
        *,
        health_source_id: int,
        display_name: str,
        namespace: str,
        metric_name: str,
        dimensions: dict[str, Any] | None = None,
        statistic: str = "Average",
        unit: str = "None",
        category: str = "custom",
        card_size: str = "wide",
        warning_threshold: float | None = None,
        critical_threshold: float | None = None,
    ) -> HealthMetricConfig:
        config = HealthMetricConfig(
            uuid=uuid.uuid4(),
            health_source_id=health_source_id,
            display_name=display_name,
            namespace=namespace,
            metric_name=metric_name,
            dimensions=dimensions or {},
            statistic=statistic,
            unit=unit,
            category=category,
            card_size=card_size,
            warning_threshold=warning_threshold,
            critical_threshold=critical_threshold,
        )
        self._db.add(config)
        return await self.flush_and_refresh(config)

    async def create_batch(
        self,
        configs: list[dict[str, Any]],
    ) -> list[HealthMetricConfig]:
        """Bulk-create metric configs from a list of dicts (used by presets)."""
        objects = []
        for c in configs:
            obj = HealthMetricConfig(uuid=uuid.uuid4(), **c)
            self._db.add(obj)
            objects.append(obj)
        await self._db.flush()
        for obj in objects:
            await self._db.refresh(obj)
        return objects

    async def patch(
        self,
        config: HealthMetricConfig,
        *,
        display_name: str | None = None,
        warning_threshold: Any = _UNSET,
        critical_threshold: Any = _UNSET,
        is_active: bool | None = None,
        card_size: str | None = None,
    ) -> HealthMetricConfig:
        if display_name is not None:
            config.display_name = display_name
        if warning_threshold is not _UNSET:
            config.warning_threshold = warning_threshold
        if critical_threshold is not _UNSET:
            config.critical_threshold = critical_threshold
        if is_active is not None:
            config.is_active = is_active
        if card_size is not None:
            config.card_size = card_size
        return await self.flush_and_refresh(config)

    async def list_by_source(
        self,
        health_source_id: int,
        *,
        active_only: bool = False,
    ) -> list[HealthMetricConfig]:
        stmt = select(HealthMetricConfig).where(
            HealthMetricConfig.health_source_id == health_source_id
        )
        if active_only:
            stmt = stmt.where(HealthMetricConfig.is_active.is_(True))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
