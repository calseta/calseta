"""
Routine Scheduler routes.

POST   /v1/routines                                                    Create routine
GET    /v1/routines                                                    List routines
GET    /v1/routines/{routine_uuid}                                     Get routine
PATCH  /v1/routines/{routine_uuid}                                     Update routine
DELETE /v1/routines/{routine_uuid}                                     Delete routine
POST   /v1/routines/{routine_uuid}/pause                               Pause routine
POST   /v1/routines/{routine_uuid}/resume                              Resume routine
POST   /v1/routines/{routine_uuid}/invoke                              Manual trigger
POST   /v1/routines/{routine_uuid}/triggers                            Add trigger
PATCH  /v1/routines/{routine_uuid}/triggers/{trigger_uuid}             Update trigger
DELETE /v1/routines/{routine_uuid}/triggers/{trigger_uuid}             Delete trigger
POST   /v1/routines/{routine_uuid}/triggers/{trigger_uuid}/webhook  Webhook invocation (HMAC)
GET    /v1/routines/{routine_uuid}/runs                                List runs
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.routines import (
    RoutineCreate,
    RoutineInvokeRequest,
    RoutinePatch,
    RoutineResponse,
    RoutineRunResponse,
    TriggerCreate,
    TriggerPatch,
    TriggerResponse,
)
from app.services.routine_service import RoutineService

router = APIRouter(prefix="/routines", tags=["routines"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


# ---------------------------------------------------------------------------
# Routine CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=DataResponse[RoutineResponse], status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_routine(
    request: Request,
    body: RoutineCreate,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[RoutineResponse]:
    """Create a new routine with optional triggers."""
    svc = RoutineService(db)
    routine = await svc.create_routine(body)
    await db.commit()
    return DataResponse(data=routine, meta={})


@router.get("", response_model=PaginatedResponse[RoutineResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_routines(
    request: Request,
    auth: _Read,
    agent_uuid: UUID | None = Query(default=None, description="Filter by agent registration UUID"),
    routine_status: str | None = Query(default=None, alias="status", description="Status filter"),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[RoutineResponse]:
    """List routines with optional filters."""
    svc = RoutineService(db)
    routines, total = await svc.list_routines(
        agent_uuid=agent_uuid,
        routine_status=routine_status,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=routines,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


@router.get("/{routine_uuid}", response_model=DataResponse[RoutineResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_routine(
    request: Request,
    routine_uuid: UUID,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[RoutineResponse]:
    """Get a routine by UUID."""
    svc = RoutineService(db)
    routine = await svc.get_routine(routine_uuid)
    return DataResponse(data=routine, meta={})


@router.patch("/{routine_uuid}", response_model=DataResponse[RoutineResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_routine(
    request: Request,
    routine_uuid: UUID,
    body: RoutinePatch,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[RoutineResponse]:
    """Partially update a routine."""
    svc = RoutineService(db)
    routine = await svc.patch_routine(routine_uuid, body)
    await db.commit()
    return DataResponse(data=routine, meta={})


@router.delete("/{routine_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_routine(
    request: Request,
    routine_uuid: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a routine and all its triggers and runs."""
    svc = RoutineService(db)
    await svc.delete_routine(routine_uuid)
    await db.commit()


# ---------------------------------------------------------------------------
# Lifecycle transitions
# ---------------------------------------------------------------------------


@router.post("/{routine_uuid}/pause", response_model=DataResponse[RoutineResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def pause_routine(
    request: Request,
    routine_uuid: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[RoutineResponse]:
    """Pause a routine. Returns 409 if already paused."""
    svc = RoutineService(db)
    routine = await svc.pause_routine(routine_uuid)
    await db.commit()
    return DataResponse(data=routine, meta={})


@router.post("/{routine_uuid}/resume", response_model=DataResponse[RoutineResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def resume_routine(
    request: Request,
    routine_uuid: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[RoutineResponse]:
    """Resume a paused routine. Returns 409 if already active."""
    svc = RoutineService(db)
    routine = await svc.resume_routine(routine_uuid)
    await db.commit()
    return DataResponse(data=routine, meta={})


# ---------------------------------------------------------------------------
# Manual invocation
# ---------------------------------------------------------------------------


@router.post(
    "/{routine_uuid}/invoke",
    response_model=DataResponse[RoutineRunResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def invoke_routine(
    request: Request,
    routine_uuid: UUID,
    body: RoutineInvokeRequest,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[RoutineRunResponse]:
    """Manually trigger a routine. Returns a run record in 'enqueued' status."""
    svc = RoutineService(db)
    run = await svc.invoke_routine(routine_uuid, body)
    await db.commit()
    return DataResponse(data=run, meta={})


# ---------------------------------------------------------------------------
# Trigger management
# ---------------------------------------------------------------------------


@router.post(
    "/{routine_uuid}/triggers",
    response_model=DataResponse[TriggerResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def add_trigger(
    request: Request,
    routine_uuid: UUID,
    body: TriggerCreate,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[TriggerResponse]:
    """Add a trigger to an existing routine."""
    svc = RoutineService(db)
    trigger = await svc.add_trigger(routine_uuid, body)
    await db.commit()
    return DataResponse(data=trigger, meta={})


@router.patch(
    "/{routine_uuid}/triggers/{trigger_uuid}",
    response_model=DataResponse[TriggerResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_trigger(
    request: Request,
    routine_uuid: UUID,
    trigger_uuid: UUID,
    body: TriggerPatch,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[TriggerResponse]:
    """Partially update a trigger."""
    svc = RoutineService(db)
    trigger = await svc.patch_trigger(routine_uuid, trigger_uuid, body)
    await db.commit()
    return DataResponse(data=trigger, meta={})


@router.delete(
    "/{routine_uuid}/triggers/{trigger_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_trigger(
    request: Request,
    routine_uuid: UUID,
    trigger_uuid: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a trigger from a routine."""
    svc = RoutineService(db)
    await svc.delete_trigger(routine_uuid, trigger_uuid)
    await db.commit()


# ---------------------------------------------------------------------------
# Webhook invocation — no auth scope; uses HMAC signature only
# ---------------------------------------------------------------------------


@router.post(
    "/{routine_uuid}/triggers/{trigger_uuid}/webhook",
    response_model=DataResponse[RoutineRunResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def webhook_trigger(
    request: Request,
    routine_uuid: UUID,
    trigger_uuid: UUID,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
    x_timestamp: str | None = Header(default=None, alias="X-Timestamp"),
    db: AsyncSession = Depends(get_db),
) -> DataResponse[RoutineRunResponse]:
    """Receive an inbound webhook and fire the routine.

    Authentication is via HMAC-SHA256 signature (X-Signature header).
    No API key is required for this endpoint — it is meant to be called
    by external systems (CI, monitoring, SIEMs, etc.).

    If the trigger has no secret configured, the signature check is skipped.
    """
    body = await request.body()
    svc = RoutineService(db)
    run = await svc.handle_webhook_trigger(
        routine_uuid=routine_uuid,
        trigger_uuid=trigger_uuid,
        body=body,
        signature=x_signature,
        timestamp=x_timestamp,
    )
    await db.commit()
    return DataResponse(data=run, meta={})


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------


@router.get("/{routine_uuid}/runs", response_model=PaginatedResponse[RoutineRunResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_runs(
    request: Request,
    routine_uuid: UUID,
    auth: _Read,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[RoutineRunResponse]:
    """List runs for a routine, newest first."""
    svc = RoutineService(db)
    runs, total = await svc.list_runs(
        routine_uuid=routine_uuid,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=runs,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )
