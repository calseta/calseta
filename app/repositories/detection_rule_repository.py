"""DetectionRule repository — all DB operations for the detection_rules table."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.detection_rule import DetectionRule
from app.schemas.detection_rules import DetectionRuleCreate, DetectionRulePatch


class DetectionRuleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_uuid(self, rule_uuid: uuid.UUID) -> DetectionRule | None:
        result = await self._db.execute(
            select(DetectionRule).where(DetectionRule.uuid == rule_uuid)
        )
        return result.scalar_one_or_none()

    async def get_by_source_rule_id(
        self, source_name: str, source_rule_id: str
    ) -> DetectionRule | None:
        """Look up a rule by the external source's rule identifier."""
        result = await self._db.execute(
            select(DetectionRule).where(
                DetectionRule.source_name == source_name,
                DetectionRule.source_rule_id == source_rule_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, data: DetectionRuleCreate) -> DetectionRule:
        rule = DetectionRule(
            name=data.name,
            source_rule_id=data.source_rule_id,
            source_name=data.source_name,
            severity=data.severity,
            is_active=data.is_active,
            mitre_tactics=data.mitre_tactics,
            mitre_techniques=data.mitre_techniques,
            mitre_subtechniques=data.mitre_subtechniques,
            data_sources=data.data_sources,
            run_frequency=data.run_frequency,
            created_by=data.created_by,
            documentation=data.documentation,
        )
        self._db.add(rule)
        await self._db.flush()
        return rule

    async def list(
        self,
        *,
        source_name: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[DetectionRule], int]:
        """Return (rules, total_count) matching filters."""
        from sqlalchemy import func

        stmt = select(DetectionRule)
        count_stmt = select(func.count()).select_from(DetectionRule)

        if source_name:
            stmt = stmt.where(DetectionRule.source_name == source_name)
            count_stmt = count_stmt.where(DetectionRule.source_name == source_name)
        if is_active is not None:
            stmt = stmt.where(DetectionRule.is_active == is_active)
            count_stmt = count_stmt.where(DetectionRule.is_active == is_active)

        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        stmt = stmt.order_by(DetectionRule.created_at.desc()).offset(offset).limit(page_size)
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def patch(
        self,
        rule: DetectionRule,
        data: DetectionRulePatch,
    ) -> DetectionRule:
        """Apply partial updates to a detection rule."""
        updates: dict[str, Any] = data.model_dump(exclude_none=True)
        for field, value in updates.items():
            setattr(rule, field, value)
        await self._db.flush()
        return rule

    async def delete(self, rule: DetectionRule) -> None:
        await self._db.delete(rule)
        await self._db.flush()
