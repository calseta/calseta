"""Agent task session management routes.

GET    /v1/sessions                         List all agent task sessions
GET    /v1/sessions/{task_key}              Get session by task_key (URL-encoded)
DELETE /v1/sessions/{task_key}              Archive session (operator override)
GET    /v1/agents/{uuid}/sessions           List sessions for a specific agent
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.repositories.agent_repository import AgentRepository
from app.repositories.agent_task_session_repository import AgentTaskSessionRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta

router = APIRouter(tags=["sessions"])

_AgentsRead = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_AgentsWrite = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class AgentTaskSessionResponse(BaseModel):
    """Serialized agent task session."""

    id: int
    uuid: UUID
    agent_registration_id: int
    alert_id: int | None
    task_key: str
    session_display_id: str | None
    total_input_tokens: int
    total_output_tokens: int
    total_cost_cents: int
    heartbeat_count: int
    last_run_id: int | None
    last_error: str | None
    is_archived: bool

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# GET /v1/sessions
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=PaginatedResponse[AgentTaskSessionResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_sessions(
    request: Request,
    auth: _AgentsRead,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    archived: bool = Query(False, description="Include archived sessions"),
) -> PaginatedResponse[AgentTaskSessionResponse]:
    """List all agent task sessions, optionally including archived ones."""
    from app.db.models.agent_task_session import AgentTaskSession

    repo = AgentTaskSessionRepository(db)
    sessions, total = await repo.paginate(
        AgentTaskSession.is_archived == archived,  # noqa: E712
        order_by=AgentTaskSession.created_at.desc(),
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[AgentTaskSessionResponse.model_validate(s) for s in sessions],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# GET /v1/sessions/{task_key}
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{task_key:path}",
    response_model=DataResponse[AgentTaskSessionResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_session(
    request: Request,
    task_key: Annotated[str, Path(description="Task key e.g. 'alert:123'")],
    auth: _AgentsRead,
    db: Annotated[AsyncSession, Depends(get_db)],
    agent_uuid: UUID | None = Query(
        None, description="Agent UUID (required if task_key is ambiguous)"
    ),
) -> DataResponse[AgentTaskSessionResponse]:
    """Get the active session for a given task_key."""
    if agent_uuid is None:
        raise CalsetaException(
            code="BAD_REQUEST",
            message="agent_uuid query parameter is required.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    agent_repo = AgentRepository(db)
    agent = await agent_repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Agent {agent_uuid} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    repo = AgentTaskSessionRepository(db)
    session = await repo.get_by_agent_and_task_key(agent.id, task_key)
    if session is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"No active session for task_key '{task_key}' on agent {agent_uuid}.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=AgentTaskSessionResponse.model_validate(session))


# ---------------------------------------------------------------------------
# DELETE /v1/sessions/{task_key} — archive (operator override)
# ---------------------------------------------------------------------------


@router.delete(
    "/sessions/{task_key:path}",
    response_model=DataResponse[AgentTaskSessionResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def archive_session(
    request: Request,
    task_key: Annotated[str, Path(description="Task key to archive")],
    auth: _AgentsWrite,
    db: Annotated[AsyncSession, Depends(get_db)],
    agent_uuid: UUID | None = Query(None, description="Agent UUID"),
) -> DataResponse[AgentTaskSessionResponse]:
    """Archive a session. The agent will restart from scratch on next heartbeat."""
    if agent_uuid is None:
        raise CalsetaException(
            code="BAD_REQUEST",
            message="agent_uuid query parameter is required.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    agent_repo = AgentRepository(db)
    agent = await agent_repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Agent {agent_uuid} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    repo = AgentTaskSessionRepository(db)
    session = await repo.get_by_agent_and_task_key(agent.id, task_key)
    if session is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"No active session for task_key '{task_key}' on agent {agent_uuid}.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    archived = await repo.archive(session)
    return DataResponse(data=AgentTaskSessionResponse.model_validate(archived))


# ---------------------------------------------------------------------------
# GET /v1/agents/{uuid}/sessions
# ---------------------------------------------------------------------------


agents_sessions_router = APIRouter(tags=["sessions"])


@agents_sessions_router.get(
    "/agents/{agent_uuid}/sessions",
    response_model=PaginatedResponse[AgentTaskSessionResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_agent_sessions(
    request: Request,
    agent_uuid: UUID,
    auth: _AgentsRead,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    archived: bool = Query(False, description="Include archived sessions"),
) -> PaginatedResponse[AgentTaskSessionResponse]:
    """List all sessions for a specific agent."""
    agent_repo = AgentRepository(db)
    agent = await agent_repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Agent {agent_uuid} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    repo = AgentTaskSessionRepository(db)
    sessions, total = await repo.list_for_agent(
        agent_id=agent.id,
        archived=archived,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[AgentTaskSessionResponse.model_validate(s) for s in sessions],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )
