"""Heartbeat and cost event routes.

POST   /v1/heartbeat                        Agent reports heartbeat
GET    /v1/heartbeat-runs                   List heartbeat runs (filterable by agent_uuid)
GET    /v1/heartbeat-runs/{run_uuid}        Get run details
POST   /v1/cost-events                      Report token/cost usage
GET    /v1/costs/summary                    Instance-wide cost summary
GET    /v1/costs/by-agent                   Cost breakdown by agent
GET    /v1/costs/by-alert                   Cost breakdown by alert
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.models.agent_registration import AgentRegistration
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.repositories.agent_repository import AgentRepository
from app.repositories.heartbeat_run_repository import HeartbeatRunRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.cost_events import (
    CostEventCreate,
    CostReportResponse,
    CostSummaryResponse,
)
from app.schemas.heartbeat import HeartbeatRequest, HeartbeatResponse, HeartbeatRunResponse
from app.services.cost_service import CostService
from app.services.heartbeat_service import HeartbeatService

router = APIRouter(tags=["heartbeat"])

_AgentsRead = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_AgentsWrite = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


async def _resolve_agent(
    auth: AuthContext,
    db: AsyncSession,
    body_agent_id: UUID | None = None,
) -> AgentRegistration:
    """Resolve the AgentRegistration from auth context.

    - Agent key (cak_*): resolves from auth.agent_registration_id directly.
    - Human key (cai_*): requires body_agent_id to be specified.

    Raises CalsetaException(403) if neither is available.
    """
    if auth.agent_registration_id is not None:
        repo = AgentRepository(db)
        agent = await repo.get_by_id(auth.agent_registration_id)
        if agent is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message="Agent registration not found for this API key.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return agent

    if body_agent_id is not None:
        repo = AgentRepository(db)
        agent = await repo.get_by_uuid(body_agent_id)
        if agent is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Agent {body_agent_id} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return agent

    raise CalsetaException(
        code="FORBIDDEN",
        message=(
            "This endpoint requires an agent API key (cak_*), "
            "or a human API key with agents:write scope and agent_id in the request body."
        ),
        status_code=status.HTTP_403_FORBIDDEN,
    )


def _default_period() -> tuple[datetime, datetime]:
    """Return (start_of_current_month, now) as the default period."""
    now = datetime.now(UTC)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start, now


# ---------------------------------------------------------------------------
# POST /v1/heartbeat
# ---------------------------------------------------------------------------


class _HeartbeatRequestWithAgent(HeartbeatRequest):
    """Extended heartbeat request that optionally carries agent_id for human keys."""

    agent_id: UUID | None = None


@router.post("/heartbeat", response_model=DataResponse[HeartbeatResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def post_heartbeat(
    request: Request,
    body: _HeartbeatRequestWithAgent,
    auth: _AgentsWrite,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[HeartbeatResponse]:
    """Record a heartbeat from an agent. Returns supervisor directives if any."""
    agent = await _resolve_agent(auth, db, body_agent_id=body.agent_id)
    svc = HeartbeatService(db)
    run, directive = await svc.record_heartbeat(agent=agent, request=body)

    return DataResponse(
        data=HeartbeatResponse(
            heartbeat_run_id=run.uuid,  # type: ignore[attr-defined]
            acknowledged_at=datetime.now(UTC),
            agent_status=agent.status,
            supervisor_directive=directive,
        )
    )


# ---------------------------------------------------------------------------
# GET /v1/heartbeat-runs
# ---------------------------------------------------------------------------


@router.get("/heartbeat-runs", response_model=PaginatedResponse[HeartbeatRunResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_heartbeat_runs(
    request: Request,
    auth: _AgentsRead,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    agent_uuid: UUID | None = Query(None, description="Filter runs by agent UUID"),
) -> PaginatedResponse[HeartbeatRunResponse]:
    """List heartbeat runs. Filterable by agent_uuid."""
    repo = HeartbeatRunRepository(db)

    if agent_uuid is not None:
        agent_repo = AgentRepository(db)
        agent = await agent_repo.get_by_uuid(agent_uuid)
        if agent is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Agent {agent_uuid} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        runs, total = await repo.list_for_agent(
            agent_id=agent.id,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    else:
        # No agent filter — paginate all runs newest-first
        from app.db.models.heartbeat_run import HeartbeatRun

        runs, total = await repo.paginate(
            order_by=HeartbeatRun.created_at.desc(),
            page=pagination.page,
            page_size=pagination.page_size,
        )

    return PaginatedResponse(
        data=[HeartbeatRunResponse.model_validate(r) for r in runs],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# GET /v1/heartbeat-runs/{run_uuid}
# ---------------------------------------------------------------------------


@router.get(
    "/heartbeat-runs/{run_uuid}",
    response_model=DataResponse[HeartbeatRunResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_heartbeat_run(
    request: Request,
    run_uuid: UUID,
    auth: _AgentsRead,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[HeartbeatRunResponse]:
    """Get details for a single heartbeat run."""
    repo = HeartbeatRunRepository(db)
    run = await repo.get_by_uuid(run_uuid)
    if run is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Heartbeat run {run_uuid} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=HeartbeatRunResponse.model_validate(run))


# ---------------------------------------------------------------------------
# POST /v1/cost-events
# ---------------------------------------------------------------------------


class _CostEventCreateWithAgent(CostEventCreate):
    """Extended cost event that optionally carries agent_id for human keys."""

    agent_id: UUID | None = None


@router.post(
    "/cost-events",
    response_model=DataResponse[CostReportResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def post_cost_event(
    request: Request,
    body: _CostEventCreateWithAgent,
    auth: _AgentsWrite,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[CostReportResponse]:
    """Report token/cost usage for an agent interaction."""
    agent = await _resolve_agent(auth, db, body_agent_id=body.agent_id)

    # Resolve alert UUID → integer ID
    db_alert_id: int | None = None
    if body.alert_id is not None:
        from app.repositories.alert_repository import AlertRepository

        alert_repo = AlertRepository(db)
        alert = await alert_repo.get_by_uuid(body.alert_id)
        if alert is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Alert {body.alert_id} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        db_alert_id = alert.id

    # Resolve heartbeat_run UUID → integer ID
    db_heartbeat_run_id: int | None = None
    if body.heartbeat_run_id is not None:
        hb_repo = HeartbeatRunRepository(db)
        hb_run = await hb_repo.get_by_uuid(body.heartbeat_run_id)
        if hb_run is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Heartbeat run {body.heartbeat_run_id} not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        db_heartbeat_run_id = hb_run.id  # type: ignore[attr-defined]

    svc = CostService(db)
    cost_event, budget_status = await svc.record_cost(
        agent=agent,
        data=body,
        db_alert_id=db_alert_id,
        db_heartbeat_run_id=db_heartbeat_run_id,
    )

    return DataResponse(
        data=CostReportResponse(
            cost_event_id=cost_event.id,  # type: ignore[attr-defined]
            agent_budget=budget_status,
        )
    )


# ---------------------------------------------------------------------------
# GET /v1/costs/summary
# ---------------------------------------------------------------------------


@router.get("/costs/summary", response_model=DataResponse[CostSummaryResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_cost_summary(
    request: Request,
    auth: _AgentsRead,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_dt: datetime | None = Query(
        None, alias="from_dt", description="ISO 8601 start datetime (default: start of month)"
    ),
    to_dt: datetime | None = Query(
        None, alias="to_dt", description="ISO 8601 end datetime (default: now)"
    ),
) -> DataResponse[CostSummaryResponse]:
    """Instance-wide cost summary for the given time range (default: current month)."""
    if from_dt is None and to_dt is None:
        from_dt, to_dt = _default_period()
    svc = CostService(db)
    summary = await svc.get_instance_summary(from_dt=from_dt, to_dt=to_dt)
    return DataResponse(data=summary)


# ---------------------------------------------------------------------------
# GET /v1/costs/by-agent
# ---------------------------------------------------------------------------


@router.get("/costs/by-agent", response_model=DataResponse[list[dict]])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_costs_by_agent(
    request: Request,
    auth: _AgentsRead,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_dt: datetime | None = Query(None, alias="from_dt"),
    to_dt: datetime | None = Query(None, alias="to_dt"),
) -> DataResponse[list[dict]]:
    """Per-agent cost breakdown for the given time range (default: current month)."""
    if from_dt is None and to_dt is None:
        from_dt, to_dt = _default_period()
    svc = CostService(db)
    rows = await svc.get_summary_by_agent(from_dt=from_dt, to_dt=to_dt)
    return DataResponse(data=rows)


# ---------------------------------------------------------------------------
# GET /v1/costs/by-alert
# ---------------------------------------------------------------------------


@router.get("/costs/by-alert", response_model=DataResponse[list[dict]])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_costs_by_alert(
    request: Request,
    auth: _AgentsRead,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_dt: datetime | None = Query(None, alias="from_dt"),
    to_dt: datetime | None = Query(None, alias="to_dt"),
) -> DataResponse[list[dict]]:
    """Per-alert cost breakdown for the given time range (default: current month)."""
    if from_dt is None and to_dt is None:
        from_dt, to_dt = _default_period()
    svc = CostService(db)
    rows = await svc.get_summary_by_alert(from_dt=from_dt, to_dt=to_dt)
    return DataResponse(data=rows)
