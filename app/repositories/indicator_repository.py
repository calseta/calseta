"""Indicator repository — global entity, one row per unique (type, value) pair."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert_indicator import AlertIndicator
from app.db.models.indicator import Indicator


class IndicatorRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert(self, itype: str, value: str, now: datetime) -> Indicator:
        """
        Insert or update indicator by (type, value).

        On insert: sets first_seen and last_seen to now.
        On conflict: updates last_seen only (preserves first_seen).
        Returns the upserted ORM object.
        """
        stmt = (
            pg_insert(Indicator)
            .values(
                type=itype,
                value=value,
                first_seen=now,
                last_seen=now,
                is_enriched=False,
                malice="Pending",
            )
            .on_conflict_do_update(
                constraint="uq_indicator_type_value",
                set_={"last_seen": now},
            )
        )
        await self._db.execute(stmt)
        await self._db.flush()
        result = await self._db.execute(
            select(Indicator).where(
                Indicator.type == itype, Indicator.value == value
            )
        )
        return result.scalar_one()

    async def get_by_uuid(self, indicator_uuid: str) -> Indicator | None:
        result = await self._db.execute(
            select(Indicator).where(Indicator.uuid == indicator_uuid)  # type: ignore[arg-type]
        )
        return result.scalar_one_or_none()

    async def link_to_alert(self, indicator_id: int, alert_id: int) -> None:
        """Link indicator to alert. No-op if already linked (ON CONFLICT DO NOTHING)."""
        stmt = (
            pg_insert(AlertIndicator)
            .values(alert_id=alert_id, indicator_id=indicator_id)
            .on_conflict_do_nothing(constraint="uq_alert_indicator")
        )
        await self._db.execute(stmt)

    async def list_for_alert(self, alert_id: int) -> list[Indicator]:
        """Return all indicators linked to the given alert."""
        result = await self._db.execute(
            select(Indicator)
            .join(AlertIndicator, AlertIndicator.indicator_id == Indicator.id)
            .where(AlertIndicator.alert_id == alert_id)
        )
        return list(result.scalars().all())

    async def update_enrichment(
        self,
        indicator: Indicator,
        malice: str,
        enrichment_results: dict[str, Any],
    ) -> None:
        """Update enrichment results and set is_enriched=True."""
        existing = indicator.enrichment_results or {}
        indicator.enrichment_results = {**existing, **enrichment_results}
        indicator.malice = malice
        indicator.is_enriched = True
        await self._db.flush()

    async def count_for_alert(self, alert_id: int) -> int:
        """Return count of indicators linked to the given alert."""
        from sqlalchemy import func

        result = await self._db.execute(
            select(func.count())
            .select_from(AlertIndicator)
            .where(AlertIndicator.alert_id == alert_id)
        )
        return result.scalar_one()
