"""
DetectionRuleService — business logic for detection rule management and association.

Key responsibility: associate_detection_rule() resolves an external rule reference
(source_name + source_rule_id) to a DetectionRule row, creating it if it doesn't exist.
This is called at alert ingest time.
"""

from __future__ import annotations

import uuid as _uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.db.models.detection_rule import DetectionRule
from app.repositories.alert_repository import AlertRepository
from app.repositories.detection_rule_repository import DetectionRuleRepository
from app.schemas.detection_rules import DetectionRuleCreate

logger = structlog.get_logger(__name__)


class DetectionRuleService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._rule_repo = DetectionRuleRepository(db)
        self._alert_repo = AlertRepository(db)

    async def associate_detection_rule(
        self,
        alert: Alert,
        source_name: str,
        source_rule_id: str,
    ) -> DetectionRule | None:
        """
        Resolve or create a DetectionRule for the given source reference,
        then link it to the alert.

        Lookup order:
          1. Existing rule matching (source_name, source_rule_id)
          2. If not found, create a stub rule with name=source_rule_id

        Returns the linked DetectionRule, or None if source_rule_id is empty.
        """
        if not source_rule_id.strip():
            return None

        rule = await self._rule_repo.get_by_source_rule_id(source_name, source_rule_id)
        if rule is None:
            rule = await self._rule_repo.create(
                DetectionRuleCreate(
                    name=source_rule_id,
                    source_rule_id=source_rule_id,
                    source_name=source_name,
                )
            )
            logger.info(
                "detection_rule_stub_created",
                source_name=source_name,
                source_rule_id=source_rule_id,
                rule_uuid=str(rule.uuid),
            )

        await self._alert_repo.set_detection_rule(alert, rule.id)
        logger.debug(
            "alert_detection_rule_linked",
            alert_uuid=str(alert.uuid),
            rule_uuid=str(rule.uuid),
        )
        return rule

    async def get_by_uuid(self, rule_uuid: _uuid.UUID) -> DetectionRule | None:
        return await self._rule_repo.get_by_uuid(rule_uuid)
