"""
Multi-agent invocation routes — Phase 5 orchestration.

POST   /v1/invocations                    — Delegate single task to a specialist
POST   /v1/invocations/parallel           — Delegate 2–10 tasks simultaneously
GET    /v1/invocations/{uuid}             — Get invocation status + result
GET    /v1/invocations/{uuid}/poll        — Long-poll until complete (timeout_ms param)
GET    /v1/agents/{uuid}/invocations      — Invocation history for an orchestrator
"""

from __future__ import annotations

import asyncio
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
from app.repositories.agent_invocation_repository import AgentInvocationRepository
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent_invocations import (
    AgentInvocationResponse,
    DelegateParallelRequest,
    DelegateParallelResponse,
    DelegateTaskRequest,
    DelegateTaskResponse,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/invocations", tags=["invocations"])
agents_invocations_router = APIRouter(prefix="/agents", tags=["invocations"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]

# Maximum long-poll wait (cap regardless of caller request)
_MAX_POLL_MS = 60_000
_POLL_INTERVAL_MS = 500


# ---------------------------------------------------------------------------
# POST /v1/invocations
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DataResponse[DelegateTaskResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delegate_task(
    request: Request,
    body: DelegateTaskRequest,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[DelegateTaskResponse]:
    """Delegate a single task to a specialist agent."""
    orchestrator = await _require_orchestrator(auth, db)

    from app.services.invocation_service import InvocationService

    svc = InvocationService(db)
    result = await svc.delegate_task(
        orchestrator=orchestrator,
        request=body,
        actor_key_prefix=auth.key_prefix,
    )
    await db.commit()
    return DataResponse(data=result)


# ---------------------------------------------------------------------------
# POST /v1/invocations/parallel
# ---------------------------------------------------------------------------


@router.post(
    "/parallel",
    response_model=DataResponse[DelegateParallelResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delegate_parallel(
    request: Request,
    body: DelegateParallelRequest,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[DelegateParallelResponse]:
    """Delegate multiple tasks simultaneously (2–10 specialists)."""
    orchestrator = await _require_orchestrator(auth, db)

    from app.services.invocation_service import InvocationService

    svc = InvocationService(db)
    results = await svc.delegate_parallel(
        orchestrator=orchestrator,
        request=body,
        actor_key_prefix=auth.key_prefix,
    )
    await db.commit()
    return DataResponse(data=DelegateParallelResponse(invocations=results))


# ---------------------------------------------------------------------------
# GET /v1/invocations/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{invocation_uuid}", response_model=DataResponse[AgentInvocationResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_invocation(
    request: Request,
    invocation_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentInvocationResponse]:
    """Get invocation status and result."""
    repo = AgentInvocationRepository(db)
    invocation = await repo.get_by_uuid(invocation_uuid)
    if invocation is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Invocation not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=AgentInvocationResponse.model_validate(invocation))


# ---------------------------------------------------------------------------
# GET /v1/invocations/{uuid}/poll
# ---------------------------------------------------------------------------


@router.get(
    "/{invocation_uuid}/poll",
    response_model=DataResponse[AgentInvocationResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def poll_invocation(
    request: Request,
    invocation_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
    timeout_ms: int = Query(30_000, ge=1000, le=_MAX_POLL_MS),
) -> DataResponse[AgentInvocationResponse]:
    """Long-poll until the invocation reaches a terminal state.

    Returns immediately if the invocation is already terminal.
    Polls every 500ms up to timeout_ms (max 60s).
    """
    repo = AgentInvocationRepository(db)
    terminal_statuses = {"completed", "failed", "timed_out"}
    elapsed_ms = 0

    while elapsed_ms <= timeout_ms:
        # Re-fetch on each iteration for a fresh DB read
        await db.reset_transaction()  # type: ignore[attr-defined]
        invocation = await repo.get_by_uuid(invocation_uuid)
        if invocation is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message="Invocation not found.",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if invocation.status in terminal_statuses:
            return DataResponse(data=AgentInvocationResponse.model_validate(invocation))

        if elapsed_ms + _POLL_INTERVAL_MS > timeout_ms:
            # Final check — return current state even if not terminal
            return DataResponse(data=AgentInvocationResponse.model_validate(invocation))

        await asyncio.sleep(_POLL_INTERVAL_MS / 1000)
        elapsed_ms += _POLL_INTERVAL_MS

    # Shouldn't reach here, but return whatever state we have
    invocation = await repo.get_by_uuid(invocation_uuid)
    if invocation is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Invocation not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=AgentInvocationResponse.model_validate(invocation))


# ---------------------------------------------------------------------------
# GET /v1/agents/{uuid}/invocations
# ---------------------------------------------------------------------------


@agents_invocations_router.get(
    "/{agent_uuid}/invocations",
    response_model=PaginatedResponse[AgentInvocationResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_agent_invocations(
    request: Request,
    agent_uuid: UUID,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(None, alias="status"),
) -> PaginatedResponse[AgentInvocationResponse]:
    """List invocation history for an orchestrator agent."""
    agent_repo = AgentRepository(db)
    agent = await agent_repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    inv_repo = AgentInvocationRepository(db)
    invocations, total = await inv_repo.list_for_agent(
        parent_agent_id=agent.id,
        status=status_filter,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[AgentInvocationResponse.model_validate(i) for i in invocations],
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _require_orchestrator(
    auth: AuthContext,
    db: AsyncSession,
) -> AgentRegistration:
    """Resolve the calling agent and verify it is an orchestrator.

    Raises 403 if the caller is not an orchestrator-type agent.
    Raises 401 if no agent API key context is available.
    """
    # The auth object carries the agent_registration_id for agent keys
    agent_id: int | None = getattr(auth, "agent_registration_id", None)
    if agent_id is None:
        raise CalsetaException(
            code="AGENT_AUTH_REQUIRED",
            message="Delegation endpoints require an agent API key (cak_*).",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    agent_repo = AgentRepository(db)
    agent = await agent_repo.get_by_id(agent_id)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if agent.agent_type != "orchestrator":
        raise CalsetaException(
            code="NOT_ORCHESTRATOR",
            message=(
                f"Agent '{agent.name}' is not an orchestrator "
                f"(agent_type={agent.agent_type}). "
                "Only orchestrator agents may delegate tasks."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return agent
