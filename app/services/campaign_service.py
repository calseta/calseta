"""CampaignService — business logic for the Campaign system.

Campaigns are strategic objective containers that group alerts, issues, and routines.
They are optional overlays — they do not affect execution or routing.

Flow:
  1. create_campaign: validate enums, resolve owner_agent_uuid, persist.
  2. get_campaign / list_campaigns: read-only queries via repository.
  3. patch_campaign: validate enums if changed, apply partial update.
  4. add_item: validate item_type, link item UUID to campaign.
  5. remove_item: find item by UUID and unlink.
  6. get_metrics: compute metrics from linked items on-demand.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.db.models.campaign import Campaign
from app.db.models.campaign_item import CampaignItem
from app.repositories.agent_repository import AgentRepository
from app.repositories.campaign_repository import CampaignRepository
from app.schemas.campaigns import (
    CampaignCategory,
    CampaignCreate,
    CampaignItemCreate,
    CampaignItemResponse,
    CampaignItemType,
    CampaignMetrics,
    CampaignPatch,
    CampaignResponse,
    CampaignStatus,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_item_response(item: CampaignItem) -> CampaignItemResponse:
    return CampaignItemResponse(
        uuid=item.uuid,
        item_type=item.item_type,
        item_uuid=item.item_uuid,
        created_at=item.created_at,
    )


def _build_campaign_response(campaign: Campaign) -> CampaignResponse:
    return CampaignResponse(
        uuid=campaign.uuid,
        name=campaign.name,
        description=campaign.description,
        status=campaign.status,
        category=campaign.category,
        owner_operator=campaign.owner_operator,
        target_metric=campaign.target_metric,
        target_value=campaign.target_value,
        current_value=campaign.current_value,
        target_date=campaign.target_date,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        owner_agent_uuid=campaign.owner_agent.uuid if campaign.owner_agent else None,
        items=[_build_item_response(i) for i in (campaign.items or [])],
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CampaignService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = CampaignRepository(db)

    async def create_campaign(self, data: CampaignCreate) -> CampaignResponse:
        """Validate enums, resolve owner_agent_uuid, create campaign."""
        if data.status not in CampaignStatus.ALL:
            raise CalsetaException(
                status_code=422,
                code="invalid_status",
                message=f"Invalid status '{data.status}'. Must be one of: {CampaignStatus.ALL}",
            )
        if data.category not in CampaignCategory.ALL:
            raise CalsetaException(
                status_code=422,
                code="invalid_category",
                message=(
                    f"Invalid category '{data.category}'. "
                    f"Must be one of: {CampaignCategory.ALL}"
                ),
            )

        owner_agent_id: int | None = None
        if data.owner_agent_uuid is not None:
            agent_repo = AgentRepository(self._db)
            agent = await agent_repo.get_by_uuid(data.owner_agent_uuid)
            if agent is None:
                raise CalsetaException(
                    status_code=404,
                    code="agent_not_found",
                    message=f"Agent '{data.owner_agent_uuid}' not found",
                )
            owner_agent_id = agent.id

        campaign = await self._repo.create(
            name=data.name,
            description=data.description,
            status=data.status,
            category=data.category,
            owner_agent_id=owner_agent_id,
            owner_operator=data.owner_operator,
            target_metric=data.target_metric,
            target_value=data.target_value,
            target_date=data.target_date,
        )
        await self._db.refresh(campaign, ["items", "owner_agent"])
        logger.info("campaign_created", campaign_uuid=str(campaign.uuid))
        return _build_campaign_response(campaign)

    async def get_campaign(self, campaign_uuid: UUID) -> CampaignResponse:
        """Fetch a campaign by UUID, raise 404 if missing."""
        campaign = await self._repo.get_by_uuid(campaign_uuid)
        if campaign is None:
            raise CalsetaException(
                status_code=404,
                code="campaign_not_found",
                message=f"Campaign '{campaign_uuid}' not found",
            )
        return _build_campaign_response(campaign)

    async def list_campaigns(
        self,
        status: str | None = None,
        owner_agent_uuid: UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[CampaignResponse], int]:
        """List campaigns with optional filters."""
        owner_agent_id: int | None = None
        if owner_agent_uuid is not None:
            agent_repo = AgentRepository(self._db)
            agent = await agent_repo.get_by_uuid(owner_agent_uuid)
            if agent is None:
                return [], 0
            owner_agent_id = agent.id

        campaigns, total = await self._repo.list_campaigns(
            status=status,
            owner_agent_id=owner_agent_id,
            page=page,
            page_size=page_size,
        )
        return [_build_campaign_response(c) for c in campaigns], total

    async def patch_campaign(
        self, campaign_uuid: UUID, patch: CampaignPatch
    ) -> CampaignResponse:
        """Validate enums if changed, apply partial update."""
        campaign = await self._repo.get_by_uuid(campaign_uuid)
        if campaign is None:
            raise CalsetaException(
                status_code=404,
                code="campaign_not_found",
                message=f"Campaign '{campaign_uuid}' not found",
            )

        updates: dict[str, object] = {}

        if patch.name is not None:
            updates["name"] = patch.name
        if patch.description is not None:
            updates["description"] = patch.description
        if patch.status is not None:
            if patch.status not in CampaignStatus.ALL:
                raise CalsetaException(
                    status_code=422,
                    code="invalid_status",
                    message=f"Invalid status '{patch.status}'",
                )
            updates["status"] = patch.status
        if patch.category is not None:
            if patch.category not in CampaignCategory.ALL:
                raise CalsetaException(
                    status_code=422,
                    code="invalid_category",
                    message=f"Invalid category '{patch.category}'",
                )
            updates["category"] = patch.category
        if patch.owner_operator is not None:
            updates["owner_operator"] = patch.owner_operator
        if patch.target_metric is not None:
            updates["target_metric"] = patch.target_metric
        if patch.target_value is not None:
            updates["target_value"] = patch.target_value
        if patch.target_date is not None:
            updates["target_date"] = patch.target_date

        if patch.owner_agent_uuid is not None:
            agent_repo = AgentRepository(self._db)
            agent = await agent_repo.get_by_uuid(patch.owner_agent_uuid)
            if agent is None:
                raise CalsetaException(
                    status_code=404,
                    code="agent_not_found",
                    message=f"Agent '{patch.owner_agent_uuid}' not found",
                )
            updates["owner_agent_id"] = agent.id

        campaign = await self._repo.patch(campaign, **updates)
        await self._db.refresh(campaign, ["items", "owner_agent"])
        return _build_campaign_response(campaign)

    async def add_item(
        self, campaign_uuid: UUID, data: CampaignItemCreate
    ) -> CampaignItemResponse:
        """Validate item_type and link an item to a campaign."""
        if data.item_type not in CampaignItemType.ALL:
            raise CalsetaException(
                status_code=422,
                code="invalid_item_type",
                message=(
                    f"Invalid item_type '{data.item_type}'. "
                    f"Must be one of: {CampaignItemType.ALL}"
                ),
            )

        campaign = await self._repo.get_by_uuid(campaign_uuid)
        if campaign is None:
            raise CalsetaException(
                status_code=404,
                code="campaign_not_found",
                message=f"Campaign '{campaign_uuid}' not found",
            )

        item = await self._repo.add_item(
            campaign_id=campaign.id,
            item_type=data.item_type,
            item_uuid=data.item_uuid,
        )
        logger.info(
            "campaign_item_added",
            campaign_uuid=str(campaign_uuid),
            item_type=data.item_type,
            item_uuid=str(data.item_uuid),
        )
        return _build_item_response(item)

    async def remove_item(
        self, campaign_uuid: UUID, item_uuid: UUID
    ) -> None:
        """Find item by UUID and unlink from campaign."""
        campaign = await self._repo.get_by_uuid(campaign_uuid)
        if campaign is None:
            raise CalsetaException(
                status_code=404,
                code="campaign_not_found",
                message=f"Campaign '{campaign_uuid}' not found",
            )

        item = await self._repo.get_item_by_uuid(item_uuid)
        if item is None or item.campaign_id != campaign.id:
            raise CalsetaException(
                status_code=404,
                code="campaign_item_not_found",
                message=f"Campaign item '{item_uuid}' not found in campaign '{campaign_uuid}'",
            )

        await self._repo.delete_item(item)
        logger.info(
            "campaign_item_removed",
            campaign_uuid=str(campaign_uuid),
            item_uuid=str(item_uuid),
        )

    async def get_metrics(self, campaign_uuid: UUID) -> CampaignMetrics:
        """Compute metrics from linked items on-demand."""
        campaign = await self._repo.get_by_uuid(campaign_uuid)
        if campaign is None:
            raise CalsetaException(
                status_code=404,
                code="campaign_not_found",
                message=f"Campaign '{campaign_uuid}' not found",
            )

        metrics = await self._repo.compute_metrics(campaign)

        return CampaignMetrics(
            campaign_uuid=campaign.uuid,
            computed_at=datetime.now(UTC),
            total_items=metrics["total_items"],  # type: ignore[arg-type]
            alert_count=metrics["alert_count"],  # type: ignore[arg-type]
            issue_count=metrics["issue_count"],  # type: ignore[arg-type]
            routine_count=metrics["routine_count"],  # type: ignore[arg-type]
            issues_done=metrics["issues_done"],  # type: ignore[arg-type]
            issues_in_progress=metrics["issues_in_progress"],  # type: ignore[arg-type]
            issues_backlog=metrics["issues_backlog"],  # type: ignore[arg-type]
            completion_pct=metrics["completion_pct"],  # type: ignore[arg-type]
            current_value=campaign.current_value,
            target_value=campaign.target_value,
            target_metric=campaign.target_metric,
        )
