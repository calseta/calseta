"""
Memory routes.

Memory entries are KB pages in /memory/ folders. These REST routes are for
operator review and management of agent memory.

GET    /v1/agents/{agent_uuid}/memory     List memory entries for a specific agent
GET    /v1/memory/shared                  List shared memory entries
GET    /v1/memory/{memory_id}             Get memory entry details (memory_id = KB page UUID)
PATCH  /v1/memory/{memory_id}             Update memory entry
DELETE /v1/memory/{memory_id}             Delete (archive) memory entry
POST   /v1/memory/{memory_id}/promote     Promote private memory to shared
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, status
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
from app.repositories.kb_repository import KBPageRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.kb import KBPagePatch, KBPageResponse, KBPageSummary
from app.services.kb_service import KBService

# Router for agent sub-resource: GET /v1/agents/{agent_uuid}/memory
agents_memory_router = APIRouter(prefix="/agents", tags=["memory"])

# Router for global memory operations: /v1/memory/...
router = APIRouter(prefix="/memory", tags=["memory"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]

_MEMORY_FOLDER_PREFIX = "/memory/"


def _assert_memory_page(folder: str, memory_id: UUID) -> None:
    """Raise 404 if the KB page is not in a /memory/ folder."""
    if not folder.startswith(_MEMORY_FOLDER_PREFIX):
        raise CalsetaException(
            status_code=404,
            code="memory_not_found",
            message=f"Memory entry '{memory_id}' not found",
        )


# ---------------------------------------------------------------------------
# Agent sub-route: GET /v1/agents/{agent_uuid}/memory
# ---------------------------------------------------------------------------


@agents_memory_router.get("/{agent_uuid}/memory", response_model=PaginatedResponse[KBPageSummary])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_agent_memory(
    request: Request,
    agent_uuid: UUID,
    auth: _Read,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[KBPageSummary]:
    """List memory entries for a specific agent."""
    # Verify the agent exists
    agent_repo = AgentRepository(db)
    agent = await agent_repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            status_code=404,
            code="agent_not_found",
            message=f"Agent '{agent_uuid}' not found",
        )

    svc = KBService(db)
    folder = f"/memory/agents/{agent.id}/"
    pages, total = await svc.list_pages(
        folder=folder,
        status="published",
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=pages,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


# ---------------------------------------------------------------------------
# Shared memory
# ---------------------------------------------------------------------------


@router.get("/shared", response_model=PaginatedResponse[KBPageSummary])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_shared_memory(
    request: Request,
    auth: _Read,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[KBPageSummary]:
    """List all shared memory entries visible across agents."""
    svc = KBService(db)
    pages, total = await svc.list_pages(
        folder="/memory/shared/",
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=pages,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


# ---------------------------------------------------------------------------
# Memory entry CRUD (by KB page UUID)
# ---------------------------------------------------------------------------


@router.get("/{memory_id}", response_model=DataResponse[KBPageResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_memory(
    request: Request,
    memory_id: UUID,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[KBPageResponse]:
    """Get a memory entry by its KB page UUID."""
    repo = KBPageRepository(db)
    page = await repo.get_by_uuid(memory_id)
    if page is None:
        raise CalsetaException(
            status_code=404,
            code="memory_not_found",
            message=f"Memory entry '{memory_id}' not found",
        )
    _assert_memory_page(page.folder, memory_id)

    svc = KBService(db)
    return DataResponse(data=await svc.get_page(page.slug), meta={})


@router.patch("/{memory_id}", response_model=DataResponse[KBPageResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_memory(
    request: Request,
    memory_id: UUID,
    auth: _Write,
    body: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> DataResponse[KBPageResponse]:
    """Update a memory entry's body, metadata, or inject_scope."""
    repo = KBPageRepository(db)
    page = await repo.get_by_uuid(memory_id)
    if page is None:
        raise CalsetaException(
            status_code=404,
            code="memory_not_found",
            message=f"Memory entry '{memory_id}' not found",
        )
    _assert_memory_page(page.folder, memory_id)

    patch = KBPagePatch(
        body=body.get("body"),
        metadata=body.get("metadata"),
        inject_scope=body.get("inject_scope"),
    )
    svc = KBService(db)
    updated = await svc.update_page(
        slug=page.slug,
        patch=patch,
        updated_by_operator=auth.key_prefix,
    )
    await db.commit()
    return DataResponse(data=updated, meta={})


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_memory(
    request: Request,
    memory_id: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Archive (soft-delete) a memory entry."""
    repo = KBPageRepository(db)
    page = await repo.get_by_uuid(memory_id)
    if page is None:
        raise CalsetaException(
            status_code=404,
            code="memory_not_found",
            message=f"Memory entry '{memory_id}' not found",
        )
    _assert_memory_page(page.folder, memory_id)

    svc = KBService(db)
    await svc.delete_page(page.slug)
    await db.commit()


# ---------------------------------------------------------------------------
# Promote memory to shared
# ---------------------------------------------------------------------------


@router.post("/{memory_id}/promote", response_model=DataResponse[KBPageResponse | dict[str, str]])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def promote_memory(
    request: Request,
    memory_id: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[KBPageResponse | dict[str, str]]:
    """Promote a private agent memory entry to the shared memory pool.

    If the owning agent has memory_promotion_requires_approval=True, returns 202
    with a pending status. Otherwise, moves the page to /memory/shared/ immediately.
    """
    repo = KBPageRepository(db)
    page = await repo.get_by_uuid(memory_id)
    if page is None:
        raise CalsetaException(
            status_code=404,
            code="memory_not_found",
            message=f"Memory entry '{memory_id}' not found",
        )
    _assert_memory_page(page.folder, memory_id)

    # Only agent-owned pages can be promoted (not already-shared pages)
    if page.folder.startswith("/memory/shared"):
        raise CalsetaException(
            status_code=400,
            code="already_shared",
            message="This memory entry is already in the shared memory pool",
        )

    # Extract agent int ID from folder path: /memory/agents/{agent_id}/
    parts = page.folder.strip("/").split("/")
    # expected parts: ["memory", "agents", "<agent_id>"]
    agent_int_id: int | None = None
    if len(parts) >= 3 and parts[0] == "memory" and parts[1] == "agents":
        import contextlib

        with contextlib.suppress(ValueError):
            agent_int_id = int(parts[2])

    requires_approval = False
    agent_role: str | None = None
    if agent_int_id is not None:
        from sqlalchemy import select

        from app.db.models.agent_registration import AgentRegistration

        result = await db.execute(
            select(AgentRegistration).where(AgentRegistration.id == agent_int_id)
        )
        agent = result.scalar_one_or_none()
        if agent is not None:
            requires_approval = agent.memory_promotion_requires_approval
            agent_role = agent.role

    if requires_approval:
        return DataResponse(
            data={"status": "pending", "message": "Memory promotion is pending operator approval"},
            meta={},
        )

    # Build inject_scope for shared memory
    if agent_role:
        new_inject_scope: dict[str, Any] = {"roles": [agent_role]}
    else:
        new_inject_scope = {"global": True}

    patch = KBPagePatch(
        folder="/memory/shared/",
        inject_scope=new_inject_scope,
    )
    svc = KBService(db)
    updated = await svc.update_page(
        slug=page.slug,
        patch=patch,
        updated_by_operator=auth.key_prefix,
    )
    await db.commit()
    return DataResponse(data=updated, meta={})
