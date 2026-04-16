"""
Issue/Task System routes.

POST   /v1/issues                              — Create issue
GET    /v1/issues                              — List issues (filterable)
GET    /v1/issues/{issue_uuid}                 — Get issue details
PATCH  /v1/issues/{issue_uuid}                 — Update issue
DELETE /v1/issues/{issue_uuid}                 — Delete issue (204)
POST   /v1/issues/{issue_uuid}/checkout        — Atomic checkout
POST   /v1/issues/{issue_uuid}/release         — Release checkout
GET    /v1/issues/{issue_uuid}/comments        — List comments
POST   /v1/issues/{issue_uuid}/comments        — Add comment

GET    /v1/labels                              — List all labels
POST   /v1/labels                              — Create label
DELETE /v1/labels/{label_uuid}                 — Delete label (204)

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
    IssueCategoryDefCreate,
    IssueCategoryDefPatch,
    IssueCategoryDefResponse,
    IssueCheckoutRequest,
    IssueCommentCreate,
    IssueCommentResponse,
    IssueCreate,
    IssueLabelCreate,
    IssueLabelResponse,
    IssuePatch,
    IssueResponse,
)
from app.services.issue_service import IssueService

router = APIRouter(prefix="/issues", tags=["issues"])
labels_router = APIRouter(prefix="/labels", tags=["issues"])
categories_router = APIRouter(prefix="/issue-categories", tags=["issues"])
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
    label_uuid: UUID | None = Query(default=None),
    q: str | None = Query(default=None, description="Search title and description (ILIKE)"),
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
        label_uuid=label_uuid,
        q=q,
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


@router.delete("/{issue_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_issue(
    request: Request,
    issue_uuid: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an issue by UUID. Cascades to comments and label assignments."""
    svc = IssueService(db)
    await svc.delete_issue(issue_uuid)
    await db.commit()


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
# Labels routes
# ---------------------------------------------------------------------------


@labels_router.get("", response_model=PaginatedResponse[IssueLabelResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_labels(
    request: Request,
    auth: _Read,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[IssueLabelResponse]:
    """List all issue labels."""
    svc = IssueService(db)
    labels, total = await svc.list_labels(
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=labels,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


@labels_router.post(
    "",
    response_model=DataResponse[IssueLabelResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_label(
    request: Request,
    body: IssueLabelCreate,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[IssueLabelResponse]:
    """Create a new issue label."""
    svc = IssueService(db)
    label = await svc.create_label(body)
    await db.commit()
    return DataResponse(data=label, meta={})


@labels_router.delete("/{label_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_label(
    request: Request,
    label_uuid: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a label. Cascades to all issue assignments."""
    svc = IssueService(db)
    await svc.delete_label(label_uuid)
    await db.commit()


# ---------------------------------------------------------------------------
# Categories routes
# ---------------------------------------------------------------------------


@categories_router.get("", response_model=PaginatedResponse[IssueCategoryDefResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_categories(
    request: Request,
    auth: _Read,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[IssueCategoryDefResponse]:
    """List all issue categories."""
    svc = IssueService(db)
    categories, total = await svc.list_categories(
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=categories,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


@categories_router.post(
    "",
    response_model=DataResponse[IssueCategoryDefResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_category(
    request: Request,
    body: IssueCategoryDefCreate,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[IssueCategoryDefResponse]:
    """Create a new issue category."""
    svc = IssueService(db)
    category = await svc.create_category(body)
    await db.commit()
    return DataResponse(data=category, meta={})


@categories_router.patch("/{category_uuid}", response_model=DataResponse[IssueCategoryDefResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_category(
    request: Request,
    category_uuid: UUID,
    body: IssueCategoryDefPatch,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[IssueCategoryDefResponse]:
    """Update a category label."""
    svc = IssueService(db)
    category = await svc.patch_category(category_uuid, body.label)
    await db.commit()
    return DataResponse(data=category, meta={})


@categories_router.delete("/{category_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_category(
    request: Request,
    category_uuid: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a category. Blocked if is_system=True."""
    svc = IssueService(db)
    await svc.delete_category(category_uuid)
    await db.commit()


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
