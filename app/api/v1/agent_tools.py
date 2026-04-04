"""Agent tool registry routes.

GET    /v1/tools              List tools (filterable by tier, category)
GET    /v1/tools/{id}         Get tool details
POST   /v1/tools              Register custom tool
PATCH  /v1/tools/{id}         Update tool config
DELETE /v1/tools/{id}         Remove tool
POST   /v1/tools/sync         Re-sync MCP tools (stub — 501)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.repositories.agent_tool_repository import AgentToolRepository
from app.schemas.agent_tools import (
    AgentToolCreate,
    AgentToolPatch,
    AgentToolResponse,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/tools", tags=["agent-tools"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


# ---------------------------------------------------------------------------
# GET /v1/tools
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[AgentToolResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_tools(
    request: Request,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    tier: str | None = Query(None, description="Filter by tier"),
    category: str | None = Query(None, description="Filter by category"),
) -> PaginatedResponse[AgentToolResponse]:
    repo = AgentToolRepository(db)
    tools, total = await repo.list_all(
        tier=tier,
        category=category,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[AgentToolResponse.model_validate(t) for t in tools],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# GET /v1/tools/{tool_id}
# ---------------------------------------------------------------------------


@router.get("/{tool_id}", response_model=DataResponse[AgentToolResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_tool(
    request: Request,
    tool_id: str,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentToolResponse]:
    repo = AgentToolRepository(db)
    tool = await repo.get_by_id(tool_id)
    if tool is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Tool '{tool_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=AgentToolResponse.model_validate(tool))


# ---------------------------------------------------------------------------
# POST /v1/tools
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DataResponse[AgentToolResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_tool(
    request: Request,
    body: AgentToolCreate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentToolResponse]:
    repo = AgentToolRepository(db)
    existing = await repo.get_by_id(body.id)
    if existing is not None:
        raise CalsetaException(
            code="CONFLICT",
            message=f"A tool with id '{body.id}' already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )
    tool = await repo.create(body)
    await db.commit()
    await db.refresh(tool)
    return DataResponse(data=AgentToolResponse.model_validate(tool))


# ---------------------------------------------------------------------------
# PATCH /v1/tools/{tool_id}
# ---------------------------------------------------------------------------


@router.patch("/{tool_id}", response_model=DataResponse[AgentToolResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_tool(
    request: Request,
    tool_id: str,
    body: AgentToolPatch,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentToolResponse]:
    repo = AgentToolRepository(db)
    tool = await repo.get_by_id(tool_id)
    if tool is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Tool '{tool_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    updates: dict[str, object] = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.description is not None:
        updates["description"] = body.description
    if body.documentation is not None:
        updates["documentation"] = body.documentation
    if body.tier is not None:
        updates["tier"] = body.tier.value
    if body.is_active is not None:
        updates["is_active"] = body.is_active

    updated = await repo.patch(tool, **updates)
    await db.commit()
    await db.refresh(updated)
    return DataResponse(data=AgentToolResponse.model_validate(updated))


# ---------------------------------------------------------------------------
# DELETE /v1/tools/{tool_id}
# ---------------------------------------------------------------------------


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_tool(
    request: Request,
    tool_id: str,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = AgentToolRepository(db)
    tool = await repo.get_by_id(tool_id)
    if tool is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Tool '{tool_id}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await repo.delete(tool)
    await db.commit()


# ---------------------------------------------------------------------------
# POST /v1/tools/sync  (stub)
# ---------------------------------------------------------------------------


@router.post("/sync", status_code=status.HTTP_501_NOT_IMPLEMENTED)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def sync_mcp_tools(
    request: Request,
    auth: _Write,
) -> JSONResponse:
    """Re-sync MCP tools from connected MCP servers. Not yet implemented."""
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content={
            "error": {
                "code": "NOT_IMPLEMENTED",
                "message": "MCP tool sync is not yet implemented.",
                "details": {},
            }
        },
    )
