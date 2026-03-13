"""
Per-detection-rule effectiveness metrics.

Pure SQL aggregation — no LLM, no new dependencies.
Follows the same query patterns as app/services/metrics.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.db.models.alert_indicator import AlertIndicator
from app.db.models.indicator import Indicator
from app.schemas.detection_rule_metrics import DetectionRuleMetricsResponse


async def compute_detection_rule_metrics(
    db: AsyncSession,
    detection_rule_id: int,
    detection_rule_uuid: UUID,
    detection_rule_name: str,
    from_time: datetime,
    to_time: datetime,
) -> DetectionRuleMetricsResponse:
    """Compute all effectiveness metrics for a single detection rule."""

    # Base filter: alerts for this rule within time window
    base_where = [
        Alert.detection_rule_id == detection_rule_id,
        Alert.created_at >= from_time,
        Alert.created_at < to_time,
    ]

    # ------------------------------------------------------------------
    # total_alerts
    # ------------------------------------------------------------------
    total_result = await db.execute(
        select(func.count(Alert.id)).where(*base_where)
    )
    total_alerts: int = total_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # active_alerts — Open/Triaging/Escalated
    # ------------------------------------------------------------------
    active_result = await db.execute(
        select(func.count(Alert.id)).where(
            *base_where,
            Alert.status.in_(["Open", "Triaging", "Escalated"]),
        )
    )
    active_alerts: int = active_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # alerts_by_status
    # ------------------------------------------------------------------
    status_result = await db.execute(
        select(Alert.status, func.count(Alert.id))
        .where(*base_where)
        .group_by(Alert.status)
    )
    alerts_by_status: dict[str, int] = {
        row[0]: row[1] for row in status_result.all()
    }

    # ------------------------------------------------------------------
    # alerts_by_severity
    # ------------------------------------------------------------------
    severity_result = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .where(*base_where)
        .group_by(Alert.severity)
    )
    alerts_by_severity: dict[str, int] = {
        row[0]: row[1] for row in severity_result.all()
    }

    # ------------------------------------------------------------------
    # false_positive_rate & true_positive_rate
    # ------------------------------------------------------------------
    closed_result = await db.execute(
        select(func.count(Alert.id)).where(
            *base_where,
            Alert.status == "Closed",
        )
    )
    closed_count: int = closed_result.scalar_one() or 0

    if closed_count > 0:
        fp_result = await db.execute(
            select(func.count(Alert.id)).where(
                *base_where,
                Alert.status == "Closed",
                Alert.close_classification.like("False Positive%"),
            )
        )
        fp_count: int = fp_result.scalar_one() or 0
        false_positive_rate = fp_count / closed_count

        tp_result = await db.execute(
            select(func.count(Alert.id)).where(
                *base_where,
                Alert.status == "Closed",
                Alert.close_classification.like("True Positive%"),
            )
        )
        tp_count: int = tp_result.scalar_one() or 0
        true_positive_rate = tp_count / closed_count
    else:
        false_positive_rate = 0.0
        true_positive_rate = 0.0

    # ------------------------------------------------------------------
    # close_classifications — breakdown of closed alerts by classification
    # ------------------------------------------------------------------
    cc_result = await db.execute(
        select(Alert.close_classification, func.count(Alert.id))
        .where(
            *base_where,
            Alert.status == "Closed",
            Alert.close_classification.is_not(None),
        )
        .group_by(Alert.close_classification)
    )
    close_classifications: dict[str, int] = {
        row[0]: row[1] for row in cc_result.all()
    }

    # ------------------------------------------------------------------
    # alerts_over_time — group by day
    # ------------------------------------------------------------------
    day_expr = func.date_trunc("day", Alert.created_at)
    time_result = await db.execute(
        select(day_expr.label("day"), func.count(Alert.id).label("count"))
        .where(*base_where)
        .group_by(day_expr)
        .order_by(day_expr)
    )
    alerts_over_time: list[dict[str, Any]] = [
        {"date": row[0].strftime("%Y-%m-%d"), "count": row[1]}
        for row in time_result.all()
    ]

    # ------------------------------------------------------------------
    # fp_over_time — false positives per day
    # ------------------------------------------------------------------
    fp_time_result = await db.execute(
        select(day_expr.label("day"), func.count(Alert.id).label("count"))
        .where(
            *base_where,
            Alert.status == "Closed",
            Alert.close_classification.like("False Positive%"),
        )
        .group_by(day_expr)
        .order_by(day_expr)
    )
    fp_over_time: list[dict[str, Any]] = [
        {"date": row[0].strftime("%Y-%m-%d"), "count": row[1]}
        for row in fp_time_result.all()
    ]

    # ------------------------------------------------------------------
    # mtta_seconds — AVG(acknowledged_at - created_at)
    # ------------------------------------------------------------------
    mtta_result = await db.execute(
        select(
            func.avg(
                extract("epoch", Alert.acknowledged_at - Alert.created_at)
            )
        ).where(
            *base_where,
            Alert.acknowledged_at.is_not(None),
        )
    )
    mtta_raw = mtta_result.scalar_one()
    mtta_seconds: float | None = float(mtta_raw) if mtta_raw is not None else None

    # ------------------------------------------------------------------
    # mttc_seconds — AVG(closed_at - created_at)
    # ------------------------------------------------------------------
    mttc_result = await db.execute(
        select(
            func.avg(
                extract("epoch", Alert.closed_at - Alert.created_at)
            )
        ).where(
            *base_where,
            Alert.closed_at.is_not(None),
        )
    )
    mttc_raw = mttc_result.scalar_one()
    mttc_seconds: float | None = float(mttc_raw) if mttc_raw is not None else None

    # ------------------------------------------------------------------
    # severity_distribution — active alerts only
    # ------------------------------------------------------------------
    active_sev_result = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .where(
            *base_where,
            Alert.status.in_(["Open", "Triaging", "Escalated"]),
        )
        .group_by(Alert.severity)
    )
    severity_distribution: dict[str, int] = {
        row[0]: row[1] for row in active_sev_result.all()
    }

    # ------------------------------------------------------------------
    # top_indicators — top 10 by association count
    # ------------------------------------------------------------------
    top_ind_result = await db.execute(
        select(
            Indicator.type,
            Indicator.value,
            func.count(AlertIndicator.id).label("count"),
            Indicator.malice,
        )
        .join(AlertIndicator, AlertIndicator.indicator_id == Indicator.id)
        .join(Alert, Alert.id == AlertIndicator.alert_id)
        .where(*base_where)
        .group_by(Indicator.type, Indicator.value, Indicator.malice)
        .order_by(func.count(AlertIndicator.id).desc())
        .limit(10)
    )
    top_indicators: list[dict[str, Any]] = [
        {
            "type": row[0],
            "value": row[1],
            "count": row[2],
            "malice": row[3],
        }
        for row in top_ind_result.all()
    ]

    # ------------------------------------------------------------------
    # alert_sources — group by source_name
    # ------------------------------------------------------------------
    source_result = await db.execute(
        select(Alert.source_name, func.count(Alert.id))
        .where(*base_where)
        .group_by(Alert.source_name)
    )
    alert_sources: dict[str, int] = {
        row[0]: row[1] for row in source_result.all()
    }

    return DetectionRuleMetricsResponse(
        detection_rule_uuid=detection_rule_uuid,
        detection_rule_name=detection_rule_name,
        period_from=from_time,
        period_to=to_time,
        total_alerts=total_alerts,
        active_alerts=active_alerts,
        alerts_by_status=alerts_by_status,
        alerts_by_severity=alerts_by_severity,
        false_positive_rate=false_positive_rate,
        true_positive_rate=true_positive_rate,
        close_classifications=close_classifications,
        alerts_over_time=alerts_over_time,
        fp_over_time=fp_over_time,
        mtta_seconds=mtta_seconds,
        mttc_seconds=mttc_seconds,
        severity_distribution=severity_distribution,
        top_indicators=top_indicators,
        alert_sources=alert_sources,
    )
