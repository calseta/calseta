"""
Campaign routes.

POST   /v1/campaigns                                       Create campaign
GET    /v1/campaigns                                       List campaigns (filterable)
GET    /v1/campaigns/{campaign_uuid}                       Get campaign with items
PATCH  /v1/campaigns/{campaign_uuid}                       Update campaign
POST   /v1/campaigns/{campaign_uuid}/items                 Link item
DELETE /v1/campaigns/{campaign_uuid}/items/{item_uuid}     Unlink item
GET    /v1/campaigns/{campaign_uuid}/metrics               Get metrics
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
from app.schemas.campaigns import (
    CampaignCreate,
    CampaignItemCreate,
    CampaignItemResponse,
    CampaignMetrics,
    CampaignPatch,
    CampaignResponse,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.services.campaign_service import CampaignService

router = APIRouter(prefix="/campaigns", tags=["campaigns"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


# ---------------------------------------------------------------------------
# Campaign CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=DataResponse[CampaignResponse], status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_campaign(
    request: Request,
    body: CampaignCreate,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[CampaignResponse]:
    """Create a new campaign."""
    svc = CampaignService(db)
    campaign = await svc.create_campaign(body)
    await db.commit()
    return DataResponse(data=campaign, meta={})


@router.get("", response_model=PaginatedResponse[CampaignResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_campaigns(
    request: Request,
    auth: _Read,
    status: str | None = Query(default=None),
    owner_agent_uuid: UUID | None = Query(default=None),
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[CampaignResponse]:
    """List campaigns with optional filters."""
    svc = CampaignService(db)
    campaigns, total = await svc.list_campaigns(
        status=status,
        owner_agent_uuid=owner_agent_uuid,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=campaigns,
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


@router.get("/{campaign_uuid}", response_model=DataResponse[CampaignResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_campaign(
    request: Request,
    campaign_uuid: UUID,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[CampaignResponse]:
    """Get a single campaign with its linked items."""
    svc = CampaignService(db)
    campaign = await svc.get_campaign(campaign_uuid)
    return DataResponse(data=campaign, meta={})


@router.patch("/{campaign_uuid}", response_model=DataResponse[CampaignResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_campaign(
    request: Request,
    campaign_uuid: UUID,
    body: CampaignPatch,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[CampaignResponse]:
    """Partially update a campaign."""
    svc = CampaignService(db)
    campaign = await svc.patch_campaign(campaign_uuid, body)
    await db.commit()
    return DataResponse(data=campaign, meta={})


# ---------------------------------------------------------------------------
# Campaign items
# ---------------------------------------------------------------------------


@router.post(
    "/{campaign_uuid}/items",
    response_model=DataResponse[CampaignItemResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def add_campaign_item(
    request: Request,
    campaign_uuid: UUID,
    body: CampaignItemCreate,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[CampaignItemResponse]:
    """Link an alert, issue, or routine to a campaign."""
    svc = CampaignService(db)
    item = await svc.add_item(campaign_uuid, body)
    await db.commit()
    return DataResponse(data=item, meta={})


@router.delete(
    "/{campaign_uuid}/items/{item_uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def remove_campaign_item(
    request: Request,
    campaign_uuid: UUID,
    item_uuid: UUID,
    auth: _Write,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Unlink an item from a campaign."""
    svc = CampaignService(db)
    await svc.remove_item(campaign_uuid, item_uuid)
    await db.commit()


# ---------------------------------------------------------------------------
# Campaign metrics
# ---------------------------------------------------------------------------


@router.get("/{campaign_uuid}/metrics", response_model=DataResponse[CampaignMetrics])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_campaign_metrics(
    request: Request,
    campaign_uuid: UUID,
    auth: _Read,
    db: AsyncSession = Depends(get_db),
) -> DataResponse[CampaignMetrics]:
    """Get computed metrics for a campaign."""
    svc = CampaignService(db)
    metrics = await svc.get_metrics(campaign_uuid)
    return DataResponse(data=metrics, meta={})
