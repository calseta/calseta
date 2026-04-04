"""CampaignRepository — CRUD and metrics for campaigns and campaign_items."""

from __future__ import annotations

import uuid as uuid_module
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models.campaign import Campaign
from app.db.models.campaign_item import CampaignItem
from app.repositories.base import BaseRepository


class CampaignRepository(BaseRepository[Campaign]):
    model = Campaign

    async def create(
        self,
        name: str,
        description: str | None,
        status: str,
        category: str,
        owner_agent_id: int | None,
        owner_operator: str | None,
        target_metric: str | None,
        target_value: object | None,
        target_date: datetime | None,
    ) -> Campaign:
        """Create a new campaign."""
        campaign = Campaign(
            uuid=uuid_module.uuid4(),
            name=name,
            description=description,
            status=status,
            category=category,
            owner_agent_id=owner_agent_id,
            owner_operator=owner_operator,
            target_metric=target_metric,
            target_value=target_value,
            target_date=target_date,
        )
        self._db.add(campaign)
        await self._db.flush()
        await self._db.refresh(campaign)
        return campaign

    async def get_by_uuid(self, uuid: UUID) -> Campaign | None:  # type: ignore[override]
        """Fetch a campaign by UUID, eager-loading items and owner_agent."""
        result = await self._db.execute(
            select(Campaign)
            .where(Campaign.uuid == uuid)
            .options(
                selectinload(Campaign.items),
                selectinload(Campaign.owner_agent),
            )
        )
        return result.scalar_one_or_none()  # type: ignore[return-value]

    async def list_campaigns(
        self,
        status: str | None = None,
        owner_agent_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Campaign], int]:
        """Return (campaigns, total) with optional filters."""
        filters = []
        if status is not None:
            filters.append(Campaign.status == status)
        if owner_agent_id is not None:
            filters.append(Campaign.owner_agent_id == owner_agent_id)

        count_stmt = select(func.count()).select_from(Campaign)
        for f in filters:
            count_stmt = count_stmt.where(f)
        total_result = await self._db.execute(count_stmt)
        total: int = total_result.scalar_one()

        stmt = (
            select(Campaign)
            .options(selectinload(Campaign.items), selectinload(Campaign.owner_agent))
            .order_by(Campaign.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        for f in filters:
            stmt = stmt.where(f)
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def patch(self, campaign: Campaign, **kwargs: object) -> Campaign:
        """Apply partial updates to a campaign."""
        _UPDATABLE = frozenset({
            "name", "description", "status", "category",
            "owner_agent_id", "owner_operator", "target_metric",
            "target_value", "current_value", "target_date",
        })
        for key, value in kwargs.items():
            if key not in _UPDATABLE:
                raise ValueError(f"Field '{key}' is not updatable via patch")
            setattr(campaign, key, value)
        await self._db.flush()
        await self._db.refresh(campaign)
        return campaign

    async def add_item(
        self,
        campaign_id: int,
        item_type: str,
        item_uuid: UUID,
    ) -> CampaignItem:
        """Link an item to a campaign."""
        item = CampaignItem(
            uuid=uuid_module.uuid4(),
            campaign_id=campaign_id,
            item_type=item_type,
            item_uuid=str(item_uuid),
        )
        self._db.add(item)
        await self._db.flush()
        await self._db.refresh(item)
        return item

    async def get_item_by_uuid(self, item_uuid: UUID) -> CampaignItem | None:
        """Fetch a single campaign item by its UUID."""
        result = await self._db.execute(
            select(CampaignItem).where(CampaignItem.uuid == item_uuid)
        )
        return result.scalar_one_or_none()  # type: ignore[return-value]

    async def delete_item(self, item: CampaignItem) -> None:
        """Delete a campaign item."""
        await self._db.delete(item)
        await self._db.flush()

    async def compute_metrics(self, campaign: Campaign) -> dict[str, object]:
        """Count items by type and issue status for a campaign.

        Returns a dict with counts for metrics aggregation.
        Issue statuses are fetched from agent_issues via UUID lookup.
        """
        from app.db.models.agent_issue import AgentIssue

        # Refresh items
        await self._db.refresh(campaign, ["items"])
        items = campaign.items

        alert_count = sum(1 for i in items if i.item_type == "alert")
        issue_count = sum(1 for i in items if i.item_type == "issue")
        routine_count = sum(1 for i in items if i.item_type == "routine")
        total_items = len(items)

        # For issue status breakdown, query agent_issues by UUID
        issue_uuids = [
            uuid_module.UUID(i.item_uuid) for i in items if i.item_type == "issue"
        ]

        issues_done = 0
        issues_in_progress = 0
        issues_backlog = 0

        if issue_uuids:
            stmt = select(AgentIssue.status).where(AgentIssue.uuid.in_(issue_uuids))
            result = await self._db.execute(stmt)
            statuses = [row[0] for row in result.all()]
            issues_done = sum(1 for s in statuses if s == "done")
            issues_in_progress = sum(1 for s in statuses if s == "in_progress")
            issues_backlog = sum(
                1 for s in statuses if s not in ("done", "in_progress", "cancelled")
            )

        completion_pct = 0.0
        if issue_count > 0:
            completion_pct = round((issues_done / issue_count) * 100, 1)

        return {
            "total_items": total_items,
            "alert_count": alert_count,
            "issue_count": issue_count,
            "routine_count": routine_count,
            "issues_done": issues_done,
            "issues_in_progress": issues_in_progress,
            "issues_backlog": issues_backlog,
            "completion_pct": completion_pct,
        }
