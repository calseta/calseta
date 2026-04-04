"""Actions endpoints — Phase 2 agent control plane.

POST   /v1/actions                        Propose an action
GET    /v1/actions                         List actions (filterable by status)
GET    /v1/actions/{action_uuid}           Get action details
POST   /v1/actions/{action_uuid}/cancel    Cancel action
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
from app.schemas.actions import (
    AgentActionResponse,
    ProposeActionRequest,
    ProposeActionResponse,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.services.action_service import ActionService

router = APIRouter(prefix="/actions", tags=["actions"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


async def _get_agent(auth: AuthContext, db: AsyncSession) -> AgentRegistration:
    """Resolve AgentRegistration for the current auth context.

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
            "Human API keys cannot propose actions directly."
        ),
        status_code=status.HTTP_403_FORBIDDEN,
    )


# ---------------------------------------------------------------------------
# POST /v1/actions
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DataResponse[ProposeActionResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def propose_action(
    request: Request,
    body: ProposeActionRequest,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[ProposeActionResponse]:
    """Propose an action for an alert.

    The action is evaluated for approval mode based on action_type and confidence.
    Returns 202 with the action ID and current status.
    """
    agent = await _get_agent(auth, db)
    svc = ActionService(db)
    result = await svc.propose_action(
        agent=agent,
        request=body,
        actor_key_prefix=auth.key_prefix,
    )
    await db.commit()
    return DataResponse(data=result)


# ---------------------------------------------------------------------------
# GET /v1/actions
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[AgentActionResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_actions(
    request: Request,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(None, alias="status"),
) -> PaginatedResponse[AgentActionResponse]:
    """List actions, optionally filtered by status."""
    svc = ActionService(db)
    actions, total = await svc.list_actions(
        status=status_filter,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[AgentActionResponse.model_validate(a) for a in actions],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# GET /v1/actions/{action_uuid}
# ---------------------------------------------------------------------------


@router.get("/{action_uuid}", response_model=DataResponse[AgentActionResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_action(
    request: Request,
    action_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentActionResponse]:
    """Get details for a specific action."""
    svc = ActionService(db)
    action = await svc.get_action(action_uuid)
    return DataResponse(data=AgentActionResponse.model_validate(action))


# ---------------------------------------------------------------------------
# POST /v1/actions/{action_uuid}/cancel
# ---------------------------------------------------------------------------


@router.post("/{action_uuid}/cancel", response_model=DataResponse[AgentActionResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def cancel_action(
    request: Request,
    action_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentActionResponse]:
    """Cancel a proposed or pending_approval action."""
    agent = await _get_agent(auth, db)
    svc = ActionService(db)
    action = await svc.cancel_action(
        action_uuid=action_uuid,
        agent=agent,
        actor_key_prefix=auth.key_prefix,
    )
    await db.commit()
    return DataResponse(data=AgentActionResponse.model_validate(action))
