"""Skills routes.

GET    /v1/skills                               — List all skills (paginated)
POST   /v1/skills                               — Create skill
GET    /v1/skills/{uuid}                        — Get skill detail
PATCH  /v1/skills/{uuid}                        — Update skill
DELETE /v1/skills/{uuid}                        — Delete skill (204)

GET    /v1/skills/{uuid}/files                  — List all files for a skill
GET    /v1/skills/{uuid}/files/{file_uuid}      — Get single skill file
PUT    /v1/skills/{uuid}/files                  — Upsert a skill file
DELETE /v1/skills/{uuid}/files/{file_uuid}      — Delete a skill file (204)

GET    /v1/agents/{uuid}/skills                 — List assigned skills for agent
POST   /v1/agents/{uuid}/skills/sync            — Replace full skill assignment
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
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
from app.repositories.skill_repository import SkillRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.skills import (
    AgentSkillSyncRequest,
    SkillCreate,
    SkillFileResponse,
    SkillFileUpsert,
    SkillPatch,
    SkillResponse,
)

router = APIRouter(prefix="/skills", tags=["skills"])
agent_skills_router = APIRouter(prefix="/agents", tags=["skills"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


# ---------------------------------------------------------------------------
# GET /v1/skills
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[SkillResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_skills(
    request: Request,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[SkillResponse]:
    """List all skills."""
    repo = SkillRepository(db)
    skills, total = await repo.list_all(page=pagination.page, page_size=pagination.page_size)
    return PaginatedResponse(
        data=[SkillResponse.model_validate(s) for s in skills],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# POST /v1/skills
# ---------------------------------------------------------------------------


@router.post("", response_model=DataResponse[SkillResponse], status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_skill(
    request: Request,
    body: SkillCreate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SkillResponse]:
    """Create a new skill. A SKILL.md entry file is auto-created."""
    repo = SkillRepository(db)
    existing = await repo.get_by_slug(body.slug)
    if existing is not None:
        raise CalsetaException(
            code="CONFLICT",
            message=f"A skill with slug '{body.slug}' already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )
    skill = await repo.create(
        slug=body.slug,
        name=body.name,
        description=body.description,
        is_global=body.is_global,
    )
    await db.commit()
    await db.refresh(skill)
    return DataResponse(data=SkillResponse.model_validate(skill))


# ---------------------------------------------------------------------------
# GET /v1/skills/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{skill_uuid}", response_model=DataResponse[SkillResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_skill(
    request: Request,
    skill_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SkillResponse]:
    """Get a single skill by UUID."""
    repo = SkillRepository(db)
    skill = await repo.get_by_uuid(skill_uuid)
    if skill is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Skill '{skill_uuid}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=SkillResponse.model_validate(skill))


# ---------------------------------------------------------------------------
# PATCH /v1/skills/{uuid}
# ---------------------------------------------------------------------------


@router.patch("/{skill_uuid}", response_model=DataResponse[SkillResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_skill(
    request: Request,
    skill_uuid: UUID,
    body: SkillPatch,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SkillResponse]:
    """Partially update a skill."""
    repo = SkillRepository(db)
    skill = await repo.get_by_uuid(skill_uuid)
    if skill is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Skill '{skill_uuid}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    updates: dict[str, object] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.is_global is not None:
        updates["is_global"] = body.is_global

    updated = await repo.patch(skill, **updates)
    await db.commit()
    await db.refresh(updated)
    return DataResponse(data=SkillResponse.model_validate(updated))


# ---------------------------------------------------------------------------
# DELETE /v1/skills/{uuid}
# ---------------------------------------------------------------------------


@router.delete("/{skill_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_skill(
    request: Request,
    skill_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a skill. Cascades to agent assignments and skill files."""
    repo = SkillRepository(db)
    skill = await repo.get_by_uuid(skill_uuid)
    if skill is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Skill '{skill_uuid}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await repo.delete(skill)
    await db.commit()


# ---------------------------------------------------------------------------
# File management sub-routes
# ---------------------------------------------------------------------------


@router.get("/{skill_uuid}/files", response_model=DataResponse[list[SkillFileResponse]])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_skill_files(
    request: Request,
    skill_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[list[SkillFileResponse]]:
    """List all files in a skill's directory tree."""
    repo = SkillRepository(db)
    skill = await repo.get_by_uuid(skill_uuid)
    if skill is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Skill '{skill_uuid}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=[SkillFileResponse.model_validate(f) for f in skill.files])


@router.get(
    "/{skill_uuid}/files/{file_uuid}",
    response_model=DataResponse[SkillFileResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_skill_file(
    request: Request,
    skill_uuid: UUID,
    file_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SkillFileResponse]:
    """Get a single skill file by UUID."""
    repo = SkillRepository(db)
    skill = await repo.get_by_uuid(skill_uuid)
    if skill is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Skill '{skill_uuid}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    skill_file = await repo.get_file_by_uuid(file_uuid)
    if skill_file is None or skill_file.skill_id != skill.id:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"File '{file_uuid}' not found on skill '{skill_uuid}'.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=SkillFileResponse.model_validate(skill_file))


@router.put(
    "/{skill_uuid}/files",
    response_model=DataResponse[SkillFileResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def upsert_skill_file(
    request: Request,
    skill_uuid: UUID,
    body: SkillFileUpsert,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SkillFileResponse]:
    """Upsert a file in a skill's directory tree by path."""
    repo = SkillRepository(db)
    skill = await repo.get_by_uuid(skill_uuid)
    if skill is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Skill '{skill_uuid}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    skill_file = await repo.upsert_file(
        skill_id=skill.id,
        path=body.path,
        content=body.content,
    )
    await db.commit()
    await db.refresh(skill_file)
    return DataResponse(data=SkillFileResponse.model_validate(skill_file))


@router.delete(
    "/{skill_uuid}/files/{file_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_skill_file(
    request: Request,
    skill_uuid: UUID,
    file_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a skill file. Returns 403 if the file is the entry point (SKILL.md)."""
    repo = SkillRepository(db)
    skill = await repo.get_by_uuid(skill_uuid)
    if skill is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Skill '{skill_uuid}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    skill_file = await repo.get_file_by_uuid(file_uuid)
    if skill_file is None or skill_file.skill_id != skill.id:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"File '{file_uuid}' not found on skill '{skill_uuid}'.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if skill_file.is_entry:
        raise CalsetaException(
            code="FORBIDDEN",
            message="Cannot delete the entry file (SKILL.md) of a skill.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    await repo.delete_file(skill_file)
    await db.commit()


# ---------------------------------------------------------------------------
# Agent sub-routes
# ---------------------------------------------------------------------------


@agent_skills_router.get("/{agent_uuid}/skills", response_model=PaginatedResponse[SkillResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_agent_skills(
    request: Request,
    agent_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[SkillResponse]:
    """List all skills assigned to a specific agent."""
    agent_repo = AgentRepository(db)
    agent = await agent_repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Agent '{agent_uuid}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    skill_repo = SkillRepository(db)
    skills = await skill_repo.get_agent_skills(agent.id)
    return PaginatedResponse(
        data=[SkillResponse.model_validate(s) for s in skills],
        meta=PaginationMeta.from_total(
            total=len(skills), page=1, page_size=len(skills) or 1
        ),
    )


@agent_skills_router.post(
    "/{agent_uuid}/skills/sync",
    response_model=PaginatedResponse[SkillResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def sync_agent_skills(
    request: Request,
    agent_uuid: UUID,
    body: AgentSkillSyncRequest,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[SkillResponse]:
    """Replace the full set of skills assigned to an agent.

    Provide an empty list to clear all skill assignments.
    """
    agent_repo = AgentRepository(db)
    agent = await agent_repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Agent '{agent_uuid}' not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    skill_repo = SkillRepository(db)

    # Resolve UUIDs → int IDs, validate all exist
    if body.skill_uuids:
        skills = await skill_repo.get_by_uuids(body.skill_uuids)
        found_uuids = {s.uuid for s in skills}
        missing = [str(u) for u in body.skill_uuids if u not in found_uuids]
        if missing:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Skills not found: {', '.join(missing)}",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        skill_ids = [s.id for s in skills]
    else:
        skills = []
        skill_ids = []

    await skill_repo.sync_agent_skills(agent_id=agent.id, skill_ids=skill_ids)
    await db.commit()

    # Reload to return current active skills
    current_skills = await skill_repo.get_agent_skills(agent.id)
    return PaginatedResponse(
        data=[SkillResponse.model_validate(s) for s in current_skills],
        meta=PaginationMeta.from_total(
            total=len(current_skills), page=1, page_size=len(current_skills) or 1
        ),
    )
