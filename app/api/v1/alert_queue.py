"""Alert queue and assignment routes — agent-facing endpoints.

GET    /v1/queue                              Get available alerts for agent
POST   /v1/queue/{alert_uuid}/checkout        Atomic checkout
POST   /v1/queue/{alert_uuid}/release         Release back to queue
GET    /v1/assignments/mine                   Get agent's current assignments
PATCH  /v1/assignments/{assignment_uuid}      Update assignment status/resolution
GET    /v1/dashboard                          Control plane dashboard data
"""

from __future__ import annotations

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
from app.schemas.alert_assignments import AlertAssignmentResponse, AssignmentUpdate
from app.schemas.alerts import AlertResponse
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.services.alert_queue_service import AlertQueueService

queue_router = APIRouter(prefix="/queue", tags=["alert-queue"])
assignments_router = APIRouter(prefix="/assignments", tags=["alert-queue"])
dashboard_router = APIRouter(tags=["dashboard"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


async def _get_agent(auth: AuthContext, db: AsyncSession) -> AgentRegistration:
    """Resolve the AgentRegistration for the current auth context.

    Works for both agent API keys (cak_* with agent_registration_id set) and
    human API keys with agents:write scope (admin/operator use).

    Raises CalsetaException(403) if no agent context is available.
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

    raise CalsetaException(
        code="FORBIDDEN",
        message=(
            "This endpoint requires an agent API key (cak_*). "
            "Human API keys cannot access the alert queue directly."
        ),
        status_code=status.HTTP_403_FORBIDDEN,
    )


# ---------------------------------------------------------------------------
# GET /v1/queue
# ---------------------------------------------------------------------------


@queue_router.get("", response_model=PaginatedResponse[AlertResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_queue(
    request: Request,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[AlertResponse]:
    """Get available (unassigned, enriched) alerts for this agent."""
    agent = await _get_agent(auth, db)
    svc = AlertQueueService(db)
    alerts, total = await svc.get_queue(
        agent=agent,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[AlertResponse.model_validate(a) for a in alerts],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# POST /v1/queue/{alert_uuid}/checkout
# ---------------------------------------------------------------------------


@queue_router.post(
    "/{alert_uuid}/checkout",
    response_model=DataResponse[AlertAssignmentResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def checkout_alert(
    request: Request,
    alert_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AlertAssignmentResponse]:
    """Atomically check out an alert. Returns 409 if already assigned."""
    agent = await _get_agent(auth, db)
    svc = AlertQueueService(db)
    assignment = await svc.checkout(alert_uuid=alert_uuid, agent=agent)
    return DataResponse(data=AlertAssignmentResponse.model_validate(assignment))


# ---------------------------------------------------------------------------
# POST /v1/queue/{alert_uuid}/release
# ---------------------------------------------------------------------------


@queue_router.post(
    "/{alert_uuid}/release",
    response_model=DataResponse[AlertAssignmentResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def release_alert(
    request: Request,
    alert_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AlertAssignmentResponse]:
    """Release an assignment back to the queue."""
    agent = await _get_agent(auth, db)
    svc = AlertQueueService(db)
    assignment = await svc.release(alert_uuid=alert_uuid, agent=agent)
    return DataResponse(data=AlertAssignmentResponse.model_validate(assignment))


# ---------------------------------------------------------------------------
# GET /v1/assignments/mine
# ---------------------------------------------------------------------------


@assignments_router.get("/mine", response_model=PaginatedResponse[AlertAssignmentResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_my_assignments(
    request: Request,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(None, alias="status"),
) -> PaginatedResponse[AlertAssignmentResponse]:
    """Get all assignments for the authenticated agent."""
    agent = await _get_agent(auth, db)
    svc = AlertQueueService(db)
    assignments, total = await svc.get_my_assignments(
        agent=agent,
        status=status_filter,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[AlertAssignmentResponse.model_validate(a) for a in assignments],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# PATCH /v1/assignments/{assignment_uuid}
# ---------------------------------------------------------------------------


@assignments_router.patch(
    "/{assignment_uuid}",
    response_model=DataResponse[AlertAssignmentResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def update_assignment(
    request: Request,
    assignment_uuid: UUID,
    body: AssignmentUpdate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AlertAssignmentResponse]:
    """Update assignment status, resolution, or investigation state."""
    agent = await _get_agent(auth, db)
    svc = AlertQueueService(db)
    assignment = await svc.update_assignment(
        assignment_uuid=assignment_uuid,
        agent=agent,
        data=body,
    )
    return DataResponse(data=AlertAssignmentResponse.model_validate(assignment))


# ---------------------------------------------------------------------------
# GET /v1/dashboard
# ---------------------------------------------------------------------------


@dashboard_router.get("/dashboard", tags=["dashboard"])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_dashboard(
    request: Request,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[dict]:
    """Control plane dashboard — agent counts, queue depths, costs MTD."""
    svc = AlertQueueService(db)
    data = await svc.get_dashboard_data()
    return DataResponse(data=data)
