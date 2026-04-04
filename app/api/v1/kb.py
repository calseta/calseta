"""
Knowledge Base routes.

POST   /v1/kb                                  Create page
GET    /v1/kb                                  List pages (filterable)
GET    /v1/kb/folders                          List folder hierarchy
GET    /v1/kb/search                           Search pages
POST   /v1/kb/sync                             Trigger sync for all external pages
GET    /v1/kb/{slug}                           Get page by slug
PATCH  /v1/kb/{slug}                           Update page
DELETE /v1/kb/{slug}                           Delete (archive) page
GET    /v1/kb/{slug}/revisions                 List revisions
GET    /v1/kb/{slug}/revisions/{rev_number}    Get specific revision
POST   /v1/kb/{slug}/links                     Link page to entity
POST   /v1/kb/{slug}/sync                      Trigger sync for single page

IMPORTANT: literal routes (folders, search, sync) are registered BEFORE
parameterized /{slug} routes to avoid FastAPI routing conflicts.
"""

from __future__ import annotations

from typing import Annotated

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
from app.schemas.kb import (
    KBFolderNode,
    KBPageCreate,
    KBPageLinkCreate,
    KBPageLinkResponse,
    KBPagePatch,
    KBPageResponse,
    KBPageRevisionResponse,
    KBPageSummary,
    KBSearchResultItem,
    KBSyncResult,
)
from app.services.kb_service import KBService

router = APIRouter(prefix="/kb", tags=["kb"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post("", response_model=DataResponse[KBPageResponse], status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_page(
    request: Request,
    body: KBPageCreate,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[KBPageResponse]:
    """Create a new KB page."""
    svc = KBService(db)
    page = await svc.create_page(data=body, created_by_operator=auth.key_prefix)
    await db.commit()
    return DataResponse(data=page, meta={})


# ---------------------------------------------------------------------------
# Literal sub-routes — MUST be registered before /{slug}
# ---------------------------------------------------------------------------


@router.get("/folders", response_model=DataResponse[list[KBFolderNode]])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_folders(
    request: Request,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[list[KBFolderNode]]:
    """Return the folder hierarchy derived from all published KB pages."""
    svc = KBService(db)
    folders = await svc.get_folders()
    return DataResponse(data=folders, meta={})


@router.get("/search", response_model=PaginatedResponse[KBSearchResultItem])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def search_pages(
    request: Request,
    auth: _Read,
    q: str = Query(..., min_length=1, description="Search query"),
    mode: str = Query(default="keyword", description="Search mode (keyword)"),
    folder: str | None = Query(default=None, description="Restrict search to folder prefix"),
    status: str = Query(default="published", description="Filter by page status"),
    inject_scope: str | None = Query(default=None, description="Filter by inject_scope key"),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[KBSearchResultItem]:
    """Full-text search KB pages."""
    svc = KBService(db)
    results, total = await svc.search_pages(
        query=q,
        folder=folder,
        status=status,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=results,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


@router.post("/sync", response_model=DataResponse[list[KBSyncResult]])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def sync_all_pages(
    request: Request,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[list[KBSyncResult]]:
    """Trigger sync for all KB pages that have a sync_source configured."""
    svc = KBService(db)
    results = await svc.sync_all_pages()
    await db.commit()
    return DataResponse(data=results, meta={})


# ---------------------------------------------------------------------------
# List + parameterized routes
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[KBPageSummary])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_pages(
    request: Request,
    auth: _Read,
    folder: str | None = Query(default=None),
    status: str | None = Query(default=None),
    inject_scope: str | None = Query(default=None, description="Filter: global|role|agent|all"),
    has_sync_source: bool | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[KBPageSummary]:
    """List KB pages with optional filters."""
    svc = KBService(db)
    pages, total = await svc.list_pages(
        folder=folder,
        status=status,
        inject_scope_filter=inject_scope,
        has_sync_source=has_sync_source,
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


@router.get("/{slug}", response_model=DataResponse[KBPageResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_page(
    request: Request,
    slug: str,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[KBPageResponse]:
    """Get a single KB page by slug."""
    svc = KBService(db)
    page = await svc.get_page(slug)
    return DataResponse(data=page, meta={})


@router.patch("/{slug}", response_model=DataResponse[KBPageResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_page(
    request: Request,
    slug: str,
    body: KBPagePatch,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[KBPageResponse]:
    """Partially update a KB page."""
    svc = KBService(db)
    page = await svc.update_page(slug=slug, patch=body, updated_by_operator=auth.key_prefix)
    await db.commit()
    return DataResponse(data=page, meta={})


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_page(
    request: Request,
    slug: str,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Archive (soft-delete) a KB page."""
    svc = KBService(db)
    await svc.delete_page(slug)
    await db.commit()


# ---------------------------------------------------------------------------
# Revisions
# ---------------------------------------------------------------------------


@router.get("/{slug}/revisions", response_model=PaginatedResponse[KBPageRevisionResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_revisions(
    request: Request,
    slug: str,
    auth: _Read,
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[KBPageRevisionResponse]:
    """List revision history for a KB page."""
    svc = KBService(db)
    revisions, total = await svc.get_revisions(
        slug=slug,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=revisions,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


@router.get("/{slug}/revisions/{rev_number}", response_model=DataResponse[KBPageRevisionResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_revision(
    request: Request,
    slug: str,
    rev_number: int,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[KBPageRevisionResponse]:
    """Get a specific revision of a KB page."""
    svc = KBService(db)
    revision = await svc.get_revision(slug=slug, revision_number=rev_number)
    return DataResponse(data=revision, meta={})


# ---------------------------------------------------------------------------
# Links
# ---------------------------------------------------------------------------


@router.post(
    "/{slug}/links",
    response_model=DataResponse[KBPageLinkResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def link_page(
    request: Request,
    slug: str,
    body: KBPageLinkCreate,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[KBPageLinkResponse]:
    """Link a KB page to an alert, issue, agent, or other entity."""
    svc = KBService(db)
    link = await svc.link_page(slug=slug, link=body)
    await db.commit()
    return DataResponse(data=link, meta={})


# ---------------------------------------------------------------------------
# Per-page sync
# ---------------------------------------------------------------------------


@router.post("/{slug}/sync", response_model=DataResponse[KBSyncResult])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def sync_page(
    request: Request,
    slug: str,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[KBSyncResult]:
    """Trigger sync for a single KB page from its configured external source."""
    svc = KBService(db)
    result = await svc.sync_page(slug=slug)
    await db.commit()
    return DataResponse(data=result, meta={})
