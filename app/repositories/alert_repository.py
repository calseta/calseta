"""Alert repository — all DB reads/writes for the alerts table."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.schemas.alert import AlertSeverity, AlertStatus, CalsetaAlert

# Whitelist of columns that can be used for sorting
_SORT_COLUMNS: dict[str, Any] = {
    "title": "title",
    "status": "status",
    "source_name": "source_name",
    "occurred_at": "occurred_at",
    "created_at": "created_at",
}

# CASE expression for severity ordering (no severity_id column in DB)
_SEVERITY_ORDER = case(
    (Alert.severity == "Critical", 5),
    (Alert.severity == "High", 4),
    (Alert.severity == "Medium", 3),
    (Alert.severity == "Low", 2),
    (Alert.severity == "Informational", 1),
    else_=0,
)


def generate_fingerprint(
    title: str, source_name: str, indicators: list[tuple[str, str]]
) -> str:
    """Generate a stable fingerprint based on alert title, source, and indicators.

    Uses MD5 hash of title + source_name + sorted indicator pairs.
    Indicators are sorted and joined as 'type:value' with '|' separator.
    """
    sorted_indicators = sorted(indicators)
    indicator_str = "|".join(f"{t}:{v}" for t, v in sorted_indicators)
    hash_input = f"{title}\x00{source_name}\x00{indicator_str}"
    return hashlib.md5(hash_input.encode()).hexdigest()


class AlertRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        normalized: CalsetaAlert,
        raw_payload: dict[str, Any],
        *,
        fingerprint: str,
    ) -> Alert:
        """Persist a new alert. Returns the created ORM object with id populated."""
        alert = Alert(
            uuid=uuid.uuid4(),
            title=normalized.title,
            severity=normalized.severity.value,
            source_name=normalized.source_name,
            occurred_at=normalized.occurred_at,
            raw_payload=raw_payload,
            tags=normalized.tags,
            status=AlertStatus.PENDING_ENRICHMENT.value,
            is_enriched=False,
            fingerprint=fingerprint,
        )
        self._db.add(alert)
        await self._db.flush()
        await self._db.refresh(alert)
        return alert

    async def find_duplicate(
        self, fingerprint: str, window_start: datetime
    ) -> Alert | None:
        """Find the most recent alert with the same fingerprint within the time window."""
        result = await self._db.execute(
            select(Alert)
            .where(
                Alert.fingerprint == fingerprint,
                Alert.created_at >= window_start,
            )
            .order_by(Alert.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def increment_duplicate(self, alert: Alert) -> Alert:
        """Bump duplicate_count and set last_seen_at on an existing alert."""
        alert.duplicate_count += 1
        alert.last_seen_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(alert)
        return alert

    async def get_by_id(self, alert_id: int) -> Alert | None:
        result = await self._db.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def get_by_uuid(self, alert_uuid: uuid.UUID) -> Alert | None:
        result = await self._db.execute(
            select(Alert).where(Alert.uuid == alert_uuid)
        )
        return result.scalar_one_or_none()

    async def list_alerts(
        self,
        *,
        status: list[str] | str | None = None,
        severity: list[str] | str | None = None,
        source_name: list[str] | str | None = None,
        is_enriched: bool | None = None,
        detection_rule_uuid: uuid.UUID | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        tags: list[str] | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Alert], int]:
        """Return (alerts, total_count) matching filters."""
        from sqlalchemy import func

        stmt = select(Alert)
        count_stmt = select(func.count()).select_from(Alert)

        # Multi-value filters: accept both str and list[str]
        if status:
            vals = status if isinstance(status, list) else [status]
            stmt = stmt.where(Alert.status.in_(vals))
            count_stmt = count_stmt.where(Alert.status.in_(vals))
        if severity:
            vals = severity if isinstance(severity, list) else [severity]
            stmt = stmt.where(Alert.severity.in_(vals))
            count_stmt = count_stmt.where(Alert.severity.in_(vals))
        if source_name:
            vals = source_name if isinstance(source_name, list) else [source_name]
            stmt = stmt.where(Alert.source_name.in_(vals))
            count_stmt = count_stmt.where(Alert.source_name.in_(vals))
        if is_enriched is not None:
            stmt = stmt.where(Alert.is_enriched == is_enriched)
            count_stmt = count_stmt.where(Alert.is_enriched == is_enriched)
        if from_time:
            stmt = stmt.where(Alert.occurred_at >= from_time)
            count_stmt = count_stmt.where(Alert.occurred_at >= from_time)
        if to_time:
            stmt = stmt.where(Alert.occurred_at <= to_time)
            count_stmt = count_stmt.where(Alert.occurred_at <= to_time)
        if tags:
            from sqlalchemy.dialects.postgresql import array
            stmt = stmt.where(Alert.tags.contains(array(tags)))
            count_stmt = count_stmt.where(Alert.tags.contains(array(tags)))
        if detection_rule_uuid:
            from app.db.models.detection_rule import DetectionRule
            subq = select(DetectionRule.id).where(
                DetectionRule.uuid == detection_rule_uuid
            ).scalar_subquery()
            stmt = stmt.where(Alert.detection_rule_id == subq)
            count_stmt = count_stmt.where(Alert.detection_rule_id == subq)

        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        # Dynamic sort
        order_clause = None
        if sort_by and sort_by in _SORT_COLUMNS:
            col = getattr(Alert, _SORT_COLUMNS[sort_by])
            order_clause = col.asc() if sort_order == "asc" else col.desc()
        elif sort_by == "severity":
            order_clause = (
                _SEVERITY_ORDER.asc() if sort_order == "asc" else _SEVERITY_ORDER.desc()
            )

        if order_clause is None:
            order_clause = Alert.occurred_at.desc()

        offset = (page - 1) * page_size
        stmt = stmt.order_by(order_clause).offset(offset).limit(page_size)
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def patch(
        self,
        alert: Alert,
        *,
        status: AlertStatus | None = None,
        severity: AlertSeverity | None = None,
        tags: list[str] | None = None,
        close_classification: str | None = None,
        malice_override: str | None = None,
        reset_malice_override: bool = False,
    ) -> Alert:
        """Apply partial updates to an alert."""
        now = datetime.now(UTC)

        if status is not None:
            prev_status = alert.status
            alert.status = status.value
            # Set lifecycle timestamps on first transition
            if (
                status in (AlertStatus.OPEN, AlertStatus.TRIAGING, AlertStatus.ESCALATED)
                and alert.acknowledged_at is None
                and prev_status in (AlertStatus.ENRICHED.value, AlertStatus.OPEN.value)
            ):
                alert.acknowledged_at = now
            if status == AlertStatus.TRIAGING and alert.triaged_at is None:
                alert.triaged_at = now
            if status == AlertStatus.CLOSED and alert.closed_at is None:
                alert.closed_at = now
                if alert.acknowledged_at is None:
                    alert.acknowledged_at = now
        if severity is not None:
            alert.severity = severity.value
        if tags is not None:
            alert.tags = tags
        if close_classification is not None:
            alert.close_classification = close_classification
        if reset_malice_override:
            alert.malice_override = None
            alert.malice_override_source = None
            alert.malice_override_at = None
        elif malice_override is not None:
            alert.malice_override = malice_override
            alert.malice_override_source = "analyst"
            alert.malice_override_at = now

        await self._db.flush()
        await self._db.refresh(alert)
        return alert

    async def delete(self, alert: Alert) -> None:
        await self._db.delete(alert)
        await self._db.flush()

    async def set_detection_rule(self, alert: Alert, rule_id: int) -> None:
        alert.detection_rule_id = rule_id
        await self._db.flush()

    async def add_finding(self, alert: Alert, finding: dict[str, Any]) -> Alert:
        """Append a finding to agent_findings JSONB array."""
        current = alert.agent_findings or []
        alert.agent_findings = [*current, finding]
        await self._db.flush()
        await self._db.refresh(alert)
        return alert

    async def mark_enriched(self, alert: Alert) -> None:
        alert.is_enriched = True
        alert.enriched_at = datetime.now(UTC)
        alert.status = AlertStatus.ENRICHED.value
        await self._db.flush()
