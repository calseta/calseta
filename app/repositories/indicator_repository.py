"""Indicator repository — global entity, one row per unique (type, value) pair."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
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

    async def get_by_type_and_value(self, itype: str, value: str) -> Indicator | None:
        result = await self._db.execute(
            select(Indicator).where(
                Indicator.type == itype, Indicator.value == value
            )
        )
        return result.scalar_one_or_none()

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
        """Update enrichment results and set is_enriched=True.

        Skips malice update when malice_source is 'analyst' (sticky override).
        """
        existing = indicator.enrichment_results or {}
        indicator.enrichment_results = {**existing, **enrichment_results}
        if indicator.malice_source != "analyst":
            indicator.malice = malice
        indicator.is_enriched = True
        await self._db.flush()

    async def patch_malice(
        self,
        indicator: Indicator,
        malice: str | None,
        now: datetime,
    ) -> None:
        """Set analyst malice override or reset to enrichment-computed value.

        Args:
            indicator: The indicator ORM object.
            malice: New malice value, or None to reset to enrichment.
            now: Current timestamp.
        """
        if malice is not None:
            indicator.malice = malice
            indicator.malice_source = "analyst"
            indicator.malice_overridden_at = now
        else:
            # Reset to enrichment-computed value
            indicator.malice = self._compute_malice_from_enrichment(indicator)
            indicator.malice_source = "enrichment"
            indicator.malice_overridden_at = None
        await self._db.flush()

    @staticmethod
    def _compute_malice_from_enrichment(indicator: Indicator) -> str:
        """Recompute malice from stored enrichment_results JSONB.

        Applies worst-case aggregation: Malicious > Suspicious > Benign > Pending.
        """
        malice_order = {"Malicious": 3, "Suspicious": 2, "Benign": 1, "Pending": 0}
        worst = "Pending"
        results = indicator.enrichment_results or {}
        for _provider, data in results.items():
            if not isinstance(data, dict):
                continue
            extracted = data.get("extracted", {})
            if isinstance(extracted, dict):
                verdict = extracted.get("verdict") or extracted.get("malice")
                if isinstance(verdict, str) and verdict in malice_order:
                    if malice_order[verdict] > malice_order[worst]:
                        worst = verdict
        return worst

    async def count_for_alert(self, alert_id: int) -> int:
        """Return count of indicators linked to the given alert."""
        result = await self._db.execute(
            select(func.count())
            .select_from(AlertIndicator)
            .where(AlertIndicator.alert_id == alert_id)
        )
        return result.scalar_one()

    async def get_related_alerts_for_indicators(
        self,
        indicator_ids: list[int],
        exclude_alert_id: int,
        limit_per_indicator: int = 10,
    ) -> dict[int, tuple[list[Alert], int]]:
        """
        For each indicator ID, return sibling alerts (excluding the given alert)
        and the total count of linked alerts.

        Returns a dict mapping indicator_id -> (list[Alert], total_count).
        """
        result: dict[int, tuple[list[Alert], int]] = {}

        if not indicator_ids:
            return result

        # Get total counts per indicator (excluding the current alert)
        count_stmt = (
            select(
                AlertIndicator.indicator_id,
                func.count(AlertIndicator.alert_id).label("cnt"),
            )
            .where(
                AlertIndicator.indicator_id.in_(indicator_ids),
                AlertIndicator.alert_id != exclude_alert_id,
            )
            .group_by(AlertIndicator.indicator_id)
        )
        count_rows = await self._db.execute(count_stmt)
        counts = {row.indicator_id: row.cnt for row in count_rows}

        # For each indicator, fetch top-N sibling alerts ordered by occurred_at desc
        for ind_id in indicator_ids:
            total = counts.get(ind_id, 0)
            if total == 0:
                result[ind_id] = ([], 0)
                continue

            sibling_stmt = (
                select(Alert)
                .join(AlertIndicator, AlertIndicator.alert_id == Alert.id)
                .where(
                    AlertIndicator.indicator_id == ind_id,
                    Alert.id != exclude_alert_id,
                )
                .order_by(Alert.occurred_at.desc())
                .limit(limit_per_indicator)
            )
            sibling_rows = await self._db.execute(sibling_stmt)
            result[ind_id] = (list(sibling_rows.scalars().all()), total)

        return result
