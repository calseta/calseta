"""
Issue/Task System routes.

POST   /v1/issues                              — Create issue
GET    /v1/issues                              — List issues (filterable)
GET    /v1/issues/{issue_uuid}                 — Get issue details
PATCH  /v1/issues/{issue_uuid}                 — Update issue
POST   /v1/issues/{issue_uuid}/checkout        — Atomic checkout
POST   /v1/issues/{issue_uuid}/release         — Release checkout
GET    /v1/issues/{issue_uuid}/comments        — List comments
POST   /v1/issues/{issue_uuid}/comments        — Add comment

GET    /v1/agents/{agent_uuid}/issues          — List issues assigned to agent
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.issues import (
    IssueCheckoutRequest,
    IssueCommentCreate,
    IssueCommentResponse,
    IssueCreate,
    IssuePatch,
    IssueResponse,
)
from app.services.issue_service import IssueService

router = APIRouter(prefix="/issues", tags=["issues"])
agents_issues_router = APIRouter(prefix="/agents", tags=["agents"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


# ---------------------------------------------------------------------------
# Issue CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=DataResponse[IssueResponse], status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_issue(
    request: Request,
    body: IssueCreate,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[IssueResponse]:
    """Create a new issue/task."""
    svc = IssueService(db)
    issue = await svc.create_issue(
        data=body,
        created_by_operator=auth.key_prefix,
    )
    await db.commit()
    return DataResponse(data=issue, meta={})


@router.get("", response_model=PaginatedResponse[IssueResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_issues(
    request: Request,
    auth: _Read,
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    assignee_agent_uuid: UUID | None = Query(default=None),
    alert_uuid: UUID | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[IssueResponse]:
    """List issues with optional filters."""
    svc = IssueService(db)
    issues, total = await svc.list_issues(
        status=status,
        priority=priority,
        category=category,
        assignee_agent_uuid=assignee_agent_uuid,
        alert_uuid=alert_uuid,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=issues,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


@router.get("/{issue_uuid}", response_model=DataResponse[IssueResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_issue(
    request: Request,
    issue_uuid: UUID,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[IssueResponse]:
    """Get a single issue by UUID."""
    svc = IssueService(db)
    issue = await svc.get_issue(issue_uuid)
    return DataResponse(data=issue, meta={})


@router.patch("/{issue_uuid}", response_model=DataResponse[IssueResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_issue(
    request: Request,
    issue_uuid: UUID,
    body: IssuePatch,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[IssueResponse]:
    """Partially update an issue."""
    svc = IssueService(db)
    issue = await svc.patch_issue(issue_uuid, body)
    await db.commit()
    return DataResponse(data=issue, meta={})


# ---------------------------------------------------------------------------
# Checkout / release
# ---------------------------------------------------------------------------


@router.post("/{issue_uuid}/checkout", response_model=DataResponse[IssueResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def checkout_issue(
    request: Request,
    issue_uuid: UUID,
    body: IssueCheckoutRequest,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[IssueResponse]:
    """Atomically lock an issue for a heartbeat run. Returns 409 on conflict."""
    svc = IssueService(db)
    issue = await svc.checkout_issue(issue_uuid, body.heartbeat_run_uuid)
    await db.commit()
    return DataResponse(data=issue, meta={})


@router.post("/{issue_uuid}/release", response_model=DataResponse[IssueResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def release_issue_checkout(
    request: Request,
    issue_uuid: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[IssueResponse]:
    """Release the checkout lock on an issue."""
    svc = IssueService(db)
    issue = await svc.release_checkout(issue_uuid)
    await db.commit()
    return DataResponse(data=issue, meta={})


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


@router.get("/{issue_uuid}/comments", response_model=PaginatedResponse[IssueCommentResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_comments(
    request: Request,
    issue_uuid: UUID,
    auth: _Read,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[IssueCommentResponse]:
    """List comments for an issue."""
    svc = IssueService(db)
    comments, total = await svc.list_comments(
        issue_uuid=issue_uuid,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=comments,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


@router.post(
    "/{issue_uuid}/comments",
    response_model=DataResponse[IssueCommentResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def add_comment(
    request: Request,
    issue_uuid: UUID,
    body: IssueCommentCreate,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[IssueCommentResponse]:
    """Add a comment to an issue."""
    svc = IssueService(db)
    comment = await svc.add_comment(issue_uuid=issue_uuid, data=body)
    await db.commit()
    return DataResponse(data=comment, meta={})


# ---------------------------------------------------------------------------
# Agent sub-route: GET /v1/agents/{agent_uuid}/issues
# ---------------------------------------------------------------------------


@agents_issues_router.get("/{agent_uuid}/issues", response_model=PaginatedResponse[IssueResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_agent_issues(
    request: Request,
    agent_uuid: UUID,
    auth: _Read,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[IssueResponse]:
    """List issues assigned to a specific agent."""
    svc = IssueService(db)
    issues, total = await svc.list_agent_issues(
        agent_uuid=agent_uuid,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=issues,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )
