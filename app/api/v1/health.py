"""
Health monitoring API — CRUD for sources, metric configs, and time-series data.

Routes:
  POST   /v1/health-sources                           — Create health source
  GET    /v1/health-sources                           — List health sources
  PATCH  /v1/health-sources/{uuid}                     — Update source config
  DELETE /v1/health-sources/{uuid}                     — Delete source + metrics
  POST   /v1/health-sources/{uuid}/test                — Test connection
  POST   /v1/health-sources/{uuid}/metrics             — Add metric config
  POST   /v1/health-sources/{uuid}/presets/{preset}    — Apply preset with discovery
  GET    /v1/health-sources/{uuid}/metrics             — List metric configs
  DELETE /v1/health-metrics-config/{uuid}              — Remove a metric config
  GET    /v1/health/metrics                            — Time-series data query
  GET    /v1/health/agents/summary                     — Agent fleet health summary
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.db.session import get_db
from app.repositories.health_metric_repository import HealthMetricRepository
from app.repositories.health_source_repository import (
    HealthMetricConfigRepository,
    HealthSourceRepository,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.health import (
    AgentFleetSummary,
    HealthMetricConfigCreate,
    HealthMetricConfigResponse,
    HealthMetricDatapointResponse,
    HealthMetricSeriesResponse,
    HealthSourceCreate,
    HealthSourcePatch,
    HealthSourceResponse,
    HealthSourceTestResult,
)
from app.services.health_service import HealthService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["health"])

_Admin = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]


def _source_response(source: Any) -> HealthSourceResponse:
    """Build a response from an ORM HealthSource, including metric_count."""
    configs = getattr(source, "metric_configs", []) or []
    return HealthSourceResponse(
        uuid=source.uuid,
        name=source.name,
        provider=source.provider,
        is_active=source.is_active,
        config=source.config,
        polling_interval_seconds=source.polling_interval_seconds,
        last_poll_at=source.last_poll_at,
        last_poll_error=source.last_poll_error,
        created_at=source.created_at,
        updated_at=source.updated_at,
        metric_count=len(configs),
    )


# ---------------------------------------------------------------------------
# Health Sources CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/health-sources",
    response_model=DataResponse[HealthSourceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_health_source(
    body: HealthSourceCreate,
    auth: _Admin,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[HealthSourceResponse]:
    repo = HealthSourceRepository(db)
    source = await repo.create(
        name=body.name,
        provider=body.provider,
        config=body.config,
        auth_config=body.auth_config,
        polling_interval_seconds=body.polling_interval_seconds,
        is_active=body.is_active,
    )
    return DataResponse(data=_source_response(source))


@router.get(
    "/health-sources",
    response_model=PaginatedResponse[HealthSourceResponse],
)
async def list_health_sources(
    auth: _Admin,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[HealthSourceResponse]:
    repo = HealthSourceRepository(db)
    from app.db.models.health_source import HealthSource

    rows, total = await repo.paginate(
        order_by=HealthSource.created_at.desc(),
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse(
        data=[_source_response(s) for s in rows],
        meta=PaginationMeta.from_total(total, page, page_size),
    )


@router.patch(
    "/health-sources/{source_uuid}",
    response_model=DataResponse[HealthSourceResponse],
)
async def patch_health_source(
    source_uuid: UUID,
    body: HealthSourcePatch,
    auth: _Admin,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[HealthSourceResponse]:
    repo = HealthSourceRepository(db)
    source = await repo.get_by_uuid(source_uuid)
    if source is None:
        raise CalsetaException(
            status_code=404,
            code="health_source_not_found",
            message=f"Health source {source_uuid} not found",
        )
    source = await repo.patch(
        source,
        name=body.name,
        config=body.config,
        auth_config=body.auth_config,
        polling_interval_seconds=body.polling_interval_seconds,
        is_active=body.is_active,
    )
    return DataResponse(data=_source_response(source))


@router.delete(
    "/health-sources/{source_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_health_source(
    source_uuid: UUID,
    auth: _Admin,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = HealthSourceRepository(db)
    source = await repo.get_by_uuid(source_uuid)
    if source is None:
        raise CalsetaException(
            status_code=404,
            code="health_source_not_found",
            message=f"Health source {source_uuid} not found",
        )
    await repo.delete(source)


@router.post(
    "/health-sources/{source_uuid}/test",
    response_model=DataResponse[HealthSourceTestResult],
)
async def test_health_source_connection(
    source_uuid: UUID,
    auth: _Admin,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[HealthSourceTestResult]:
    repo = HealthSourceRepository(db)
    source = await repo.get_by_uuid(source_uuid)
    if source is None:
        raise CalsetaException(
            status_code=404,
            code="health_source_not_found",
            message=f"Health source {source_uuid} not found",
        )

    svc = HealthService(db)
    result = await svc.test_source_connection(source.id)
    return DataResponse(data=HealthSourceTestResult(**result))


# ---------------------------------------------------------------------------
# Metric Configs CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/health-sources/{source_uuid}/metrics",
    response_model=DataResponse[HealthMetricConfigResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_metric_config(
    source_uuid: UUID,
    body: HealthMetricConfigCreate,
    auth: _Admin,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[HealthMetricConfigResponse]:
    source_repo = HealthSourceRepository(db)
    source = await source_repo.get_by_uuid(source_uuid)
    if source is None:
        raise CalsetaException(
            status_code=404,
            code="health_source_not_found",
            message=f"Health source {source_uuid} not found",
        )

    config_repo = HealthMetricConfigRepository(db)
    config = await config_repo.create(
        health_source_id=source.id,
        display_name=body.display_name,
        namespace=body.namespace,
        metric_name=body.metric_name,
        dimensions=body.dimensions,
        statistic=body.statistic,
        unit=body.unit,
        category=body.category,
        card_size=body.card_size,
        warning_threshold=body.warning_threshold,
        critical_threshold=body.critical_threshold,
    )
    return DataResponse(data=HealthMetricConfigResponse.model_validate(config))


@router.post(
    "/health-sources/{source_uuid}/presets/{preset_name}",
    response_model=DataResponse[list[HealthMetricConfigResponse]],
    status_code=status.HTTP_201_CREATED,
)
async def apply_preset(
    source_uuid: UUID,
    preset_name: str,
    auth: _Admin,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[list[HealthMetricConfigResponse]]:
    source_repo = HealthSourceRepository(db)
    source = await source_repo.get_by_uuid(source_uuid)
    if source is None:
        raise CalsetaException(
            status_code=404,
            code="health_source_not_found",
            message=f"Health source {source_uuid} not found",
        )

    from app.integrations.health.presets import apply_preset_for_source

    config_repo = HealthMetricConfigRepository(db)
    configs = await apply_preset_for_source(
        source=source,
        preset_name=preset_name,
        config_repo=config_repo,
        source_repo=source_repo,
    )
    return DataResponse(
        data=[HealthMetricConfigResponse.model_validate(c) for c in configs]
    )


@router.get(
    "/health-sources/{source_uuid}/metrics",
    response_model=PaginatedResponse[HealthMetricConfigResponse],
)
async def list_metric_configs(
    source_uuid: UUID,
    auth: _Admin,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[HealthMetricConfigResponse]:
    source_repo = HealthSourceRepository(db)
    source = await source_repo.get_by_uuid(source_uuid)
    if source is None:
        raise CalsetaException(
            status_code=404,
            code="health_source_not_found",
            message=f"Health source {source_uuid} not found",
        )

    config_repo = HealthMetricConfigRepository(db)
    from app.db.models.health_metric_config import HealthMetricConfig

    rows, total = await config_repo.paginate(
        HealthMetricConfig.health_source_id == source.id,
        order_by=HealthMetricConfig.created_at.desc(),
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse(
        data=[HealthMetricConfigResponse.model_validate(c) for c in rows],
        meta=PaginationMeta.from_total(total, page, page_size),
    )


@router.delete(
    "/health-metrics-config/{config_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_metric_config(
    config_uuid: UUID,
    auth: _Admin,
    db: AsyncSession = Depends(get_db),
) -> None:
    config_repo = HealthMetricConfigRepository(db)
    config = await config_repo.get_by_uuid(config_uuid)
    if config is None:
        raise CalsetaException(
            status_code=404,
            code="health_metric_config_not_found",
            message=f"Health metric config {config_uuid} not found",
        )
    await config_repo.delete(config)


# ---------------------------------------------------------------------------
# Time-Series Data Query
# ---------------------------------------------------------------------------


@router.get(
    "/health/metrics",
    response_model=DataResponse[list[HealthMetricSeriesResponse]],
)
async def query_health_metrics(
    auth: _Admin,
    source_uuid: UUID | None = Query(None),
    metric_config_uuid: UUID | None = Query(None),
    window: str = Query("1h", pattern=r"^(1h|6h|24h|7d)$"),
    db: AsyncSession = Depends(get_db),
) -> DataResponse[list[HealthMetricSeriesResponse]]:
    """Query time-series health metrics. Filter by source or specific metric config."""
    # Parse window
    window_map = {"1h": 1, "6h": 6, "24h": 24, "7d": 168}
    hours = window_map.get(window, 1)
    now = datetime.now(UTC)
    start = now - timedelta(hours=hours)

    config_repo = HealthMetricConfigRepository(db)
    metric_repo = HealthMetricRepository(db)

    # Determine which configs to query
    configs = []
    if metric_config_uuid:
        config = await config_repo.get_by_uuid(metric_config_uuid)
        if config:
            configs = [config]
    elif source_uuid:
        source_repo = HealthSourceRepository(db)
        source = await source_repo.get_by_uuid(source_uuid)
        if source:
            configs = await config_repo.list_by_source(source.id, active_only=True)
    else:
        raise CalsetaException(
            status_code=400,
            code="missing_filter",
            message="Provide source_uuid or metric_config_uuid query parameter",
        )

    if not configs:
        return DataResponse(data=[])

    # Fetch time-series data
    config_ids = [c.id for c in configs]
    grouped = await metric_repo.query_range_multi(
        config_ids, start=start, end=now
    )

    series: list[HealthMetricSeriesResponse] = []
    for config in configs:
        datapoints = grouped.get(config.id, [])
        latest = datapoints[-1] if datapoints else None
        series.append(
            HealthMetricSeriesResponse(
                metric_config_id=config.id,
                display_name=config.display_name,
                datapoints=[
                    HealthMetricDatapointResponse(
                        value=dp.value,
                        timestamp=dp.timestamp,
                        raw_datapoints=dp.raw_datapoints,
                    )
                    for dp in datapoints
                ],
                latest_value=latest.value if latest else None,
                latest_timestamp=latest.timestamp if latest else None,
            )
        )

    return DataResponse(data=series)


# ---------------------------------------------------------------------------
# Agent Fleet Health Summary
# ---------------------------------------------------------------------------


@router.get(
    "/health/agents/summary",
    response_model=DataResponse[AgentFleetSummary],
)
async def agent_fleet_summary(
    auth: _Admin,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[AgentFleetSummary]:
    """Agent fleet health — built-in, no cloud source needed."""
    from app.repositories.agent_repository import AgentRepository

    agent_repo = AgentRepository(db)

    # Total and active agents
    all_agents, total = await agent_repo.paginate(page=1, page_size=1)
    total_agents = total

    # Active = agents with recent runs (last 24h)
    seven_days_ago = datetime.now(UTC) - timedelta(days=7)
    from sqlalchemy import func, select

    from app.db.models.heartbeat_run import HeartbeatRun

    # Run stats over last 7 days
    run_stats = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(HeartbeatRun.status == "succeeded").label("succeeded"),
            func.count().filter(HeartbeatRun.status == "failed").label("failed"),
        ).where(HeartbeatRun.created_at >= seven_days_ago)
    )
    row = run_stats.one()
    total_runs = row.total or 0
    succeeded = row.succeeded or 0
    failed = row.failed or 0

    # Active agents (have a run in last 24h)
    one_day_ago = datetime.now(UTC) - timedelta(days=1)
    active_result = await db.execute(
        select(func.count(func.distinct(HeartbeatRun.agent_registration_id))).where(
            HeartbeatRun.created_at >= one_day_ago,
        )
    )
    active_agents = active_result.scalar_one() or 0

    # Cost MTD
    from app.db.models.cost_event import CostEvent

    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cost_result = await db.execute(
        select(func.coalesce(func.sum(CostEvent.cost_cents), 0)).where(
            CostEvent.created_at >= month_start,
        )
    )
    total_cost_mtd = cost_result.scalar_one() or 0

    success_rate = (succeeded / total_runs * 100) if total_runs > 0 else 0.0

    summary = AgentFleetSummary(
        total_agents=total_agents,
        active_agents=active_agents,
        idle_agents=max(0, total_agents - active_agents),
        error_agents=0,
        total_runs_7d=total_runs,
        successful_runs_7d=succeeded,
        failed_runs_7d=failed,
        success_rate_7d=round(success_rate, 1),
        total_cost_mtd_cents=total_cost_mtd,
        active_investigations=0,
        stall_detections_7d=0,
    )
    return DataResponse(data=summary)
