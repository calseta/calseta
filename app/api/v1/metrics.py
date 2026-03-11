"""Metrics routes — GET /v1/metrics/alerts, GET /v1/metrics/workflows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.db.session import get_db
from app.queue.base import TaskQueueBase
from app.queue.dependencies import get_queue
from app.schemas.common import DataResponse
from app.schemas.metrics import (
    AlertMetricsResponse,
    MetricsSummaryResponse,
    WorkflowMetricsResponse,
)
from app.services.metrics import (
    compute_alert_metrics,
    compute_metrics_summary,
    compute_workflow_metrics,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])

_AlertsRead = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_READ))]
_WorkflowsRead = Annotated[AuthContext, Depends(require_scope(Scope.WORKFLOWS_READ))]


def _default_window() -> tuple[datetime, datetime]:
    now = datetime.now(UTC)
    return now - timedelta(days=30), now


@router.get("/alerts", response_model=DataResponse[AlertMetricsResponse])
async def get_alert_metrics(
    auth: _AlertsRead,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_time: datetime | None = Query(None),
    to_time: datetime | None = Query(None),
) -> DataResponse[AlertMetricsResponse]:
    if from_time is None or to_time is None:
        from_time, to_time = _default_window()
    metrics = await compute_alert_metrics(db, from_time, to_time)
    return DataResponse(data=metrics)


@router.get("/summary", response_model=DataResponse[MetricsSummaryResponse])
async def get_metrics_summary(
    auth: _AlertsRead,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[TaskQueueBase, Depends(get_queue)],
) -> DataResponse[MetricsSummaryResponse]:
    """
    Compact SOC health snapshot — always last 30 days.
    No time window parameters — window is fixed per PRD.
    Optimized for agent context injection (low token cost).
    """
    summary = await compute_metrics_summary(db, queue=queue)
    return DataResponse(data=summary)


@router.get("/workflows", response_model=DataResponse[WorkflowMetricsResponse])
async def get_workflow_metrics(
    auth: _WorkflowsRead,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_time: datetime | None = Query(None),
    to_time: datetime | None = Query(None),
) -> DataResponse[WorkflowMetricsResponse]:
    if from_time is None or to_time is None:
        from_time, to_time = _default_window()
    metrics = await compute_workflow_metrics(db, from_time, to_time)
    return DataResponse(data=metrics)
