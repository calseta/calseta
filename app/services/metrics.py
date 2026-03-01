"""
Metrics computation service.

All functions execute raw SQLAlchemy queries — no ORM load, no heavy ORM relationships.
All MTTX values in seconds (float). Return null (None) per PRD spec when data is unavailable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import extract, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.db.models.detection_rule import DetectionRule
from app.db.models.workflow import Workflow
from app.db.models.workflow_approval_request import WorkflowApprovalRequest
from app.db.models.workflow_run import WorkflowRun
from app.schemas.metrics import (
    AlertMetricsResponse,
    MetricsSummaryAlerts,
    MetricsSummaryApprovals,
    MetricsSummaryResponse,
    MetricsSummaryWorkflows,
    WorkflowMetricsResponse,
)


async def compute_alert_metrics(
    db: AsyncSession,
    from_time: datetime,
    to_time: datetime,
) -> AlertMetricsResponse:
    """Compute all 13 alert metrics for the given time window."""

    # ------------------------------------------------------------------
    # total_alerts
    # ------------------------------------------------------------------
    total_result = await db.execute(
        select(func.count(Alert.id)).where(
            Alert.created_at >= from_time,
            Alert.created_at < to_time,
        )
    )
    total_alerts: int = total_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # alerts_by_status
    # ------------------------------------------------------------------
    status_result = await db.execute(
        select(Alert.status, func.count(Alert.id))
        .where(Alert.created_at >= from_time, Alert.created_at < to_time)
        .group_by(Alert.status)
    )
    alerts_by_status: dict[str, int] = {row[0]: row[1] for row in status_result.all()}

    # ------------------------------------------------------------------
    # alerts_by_severity
    # ------------------------------------------------------------------
    severity_result = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .where(Alert.created_at >= from_time, Alert.created_at < to_time)
        .group_by(Alert.severity)
    )
    alerts_by_severity: dict[str, int] = {
        row[0]: row[1] for row in severity_result.all()
    }

    # ------------------------------------------------------------------
    # alerts_by_source
    # ------------------------------------------------------------------
    source_result = await db.execute(
        select(Alert.source_name, func.count(Alert.id))
        .where(Alert.created_at >= from_time, Alert.created_at < to_time)
        .group_by(Alert.source_name)
    )
    alerts_by_source: dict[str, int] = {row[0]: row[1] for row in source_result.all()}

    # ------------------------------------------------------------------
    # alerts_over_time — group by day
    # ------------------------------------------------------------------
    day_expr = func.date_trunc("day", Alert.created_at)
    time_result = await db.execute(
        select(day_expr.label("day"), func.count(Alert.id).label("count"))
        .where(Alert.created_at >= from_time, Alert.created_at < to_time)
        .group_by(day_expr)
        .order_by(day_expr)
    )
    alerts_over_time: list[dict[str, Any]] = [
        {"date": row[0].strftime("%Y-%m-%d"), "count": row[1]}
        for row in time_result.all()
    ]

    # ------------------------------------------------------------------
    # false_positive_rate
    # ------------------------------------------------------------------
    closed_result = await db.execute(
        select(func.count(Alert.id)).where(
            Alert.created_at >= from_time,
            Alert.created_at < to_time,
            Alert.status == "Closed",
        )
    )
    closed_count: int = closed_result.scalar_one() or 0

    if closed_count > 0:
        fp_result = await db.execute(
            select(func.count(Alert.id)).where(
                Alert.created_at >= from_time,
                Alert.created_at < to_time,
                Alert.status == "Closed",
                Alert.close_classification.like("False Positive%"),
            )
        )
        fp_count: int = fp_result.scalar_one() or 0
        false_positive_rate = fp_count / closed_count
    else:
        false_positive_rate = 0.0

    # ------------------------------------------------------------------
    # mean_time_to_enrich — AVG(enriched_at - ingested_at) for enriched alerts
    # ------------------------------------------------------------------
    mtte_result = await db.execute(
        select(
            func.avg(
                extract("epoch", Alert.enriched_at - Alert.ingested_at)
            )
        ).where(
            Alert.created_at >= from_time,
            Alert.created_at < to_time,
            Alert.is_enriched.is_(True),
            Alert.enriched_at.is_not(None),
        )
    )
    mtte_raw = mtte_result.scalar_one()
    mean_time_to_enrich: float | None = float(mtte_raw) if mtte_raw is not None else None

    # ------------------------------------------------------------------
    # mean_time_to_detect (MTTD) — AVG(created_at - occurred_at)
    # ------------------------------------------------------------------
    mttd_result = await db.execute(
        select(
            func.avg(
                extract("epoch", Alert.created_at - Alert.occurred_at)
            )
        ).where(
            Alert.created_at >= from_time,
            Alert.created_at < to_time,
            Alert.occurred_at.is_not(None),
        )
    )
    mttd_raw = mttd_result.scalar_one()
    mean_time_to_detect: float | None = float(mttd_raw) if mttd_raw is not None else None

    # ------------------------------------------------------------------
    # mean_time_to_acknowledge (MTTA) — AVG(acknowledged_at - created_at)
    # ------------------------------------------------------------------
    mtta_result = await db.execute(
        select(
            func.avg(
                extract("epoch", Alert.acknowledged_at - Alert.created_at)
            )
        ).where(
            Alert.created_at >= from_time,
            Alert.created_at < to_time,
            Alert.acknowledged_at.is_not(None),
        )
    )
    mtta_raw = mtta_result.scalar_one()
    mean_time_to_acknowledge: float | None = (
        float(mtta_raw) if mtta_raw is not None else None
    )

    # ------------------------------------------------------------------
    # mean_time_to_triage (MTTT) — AVG(triaged_at - created_at)
    # ------------------------------------------------------------------
    mttt_result = await db.execute(
        select(
            func.avg(
                extract("epoch", Alert.triaged_at - Alert.created_at)
            )
        ).where(
            Alert.created_at >= from_time,
            Alert.created_at < to_time,
            Alert.triaged_at.is_not(None),
        )
    )
    mttt_raw = mttt_result.scalar_one()
    mean_time_to_triage: float | None = float(mttt_raw) if mttt_raw is not None else None

    # ------------------------------------------------------------------
    # mean_time_to_conclusion (MTTC) — AVG(closed_at - created_at)
    # ------------------------------------------------------------------
    mttc_result = await db.execute(
        select(
            func.avg(
                extract("epoch", Alert.closed_at - Alert.created_at)
            )
        ).where(
            Alert.created_at >= from_time,
            Alert.created_at < to_time,
            Alert.closed_at.is_not(None),
        )
    )
    mttc_raw = mttc_result.scalar_one()
    mean_time_to_conclusion: float | None = (
        float(mttc_raw) if mttc_raw is not None else None
    )

    # ------------------------------------------------------------------
    # active_alerts_by_severity — Open/Triaging/Escalated
    # ------------------------------------------------------------------
    active_sev_result = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .where(
            Alert.created_at >= from_time,
            Alert.created_at < to_time,
            Alert.status.in_(["Open", "Triaging", "Escalated"]),
        )
        .group_by(Alert.severity)
    )
    active_alerts_by_severity: dict[str, int] = {
        row[0]: row[1] for row in active_sev_result.all()
    }

    # ------------------------------------------------------------------
    # top_detection_rules — top 10 by alert count
    # ------------------------------------------------------------------
    top_rules_result = await db.execute(
        select(
            DetectionRule.uuid,
            DetectionRule.name,
            func.count(Alert.id).label("count"),
        )
        .join(DetectionRule, Alert.detection_rule_id == DetectionRule.id)
        .where(Alert.created_at >= from_time, Alert.created_at < to_time)
        .group_by(DetectionRule.uuid, DetectionRule.name)
        .order_by(func.count(Alert.id).desc())
        .limit(10)
    )
    top_detection_rules: list[dict[str, Any]] = [
        {"uuid": str(row[0]), "name": row[1], "count": row[2]}
        for row in top_rules_result.all()
    ]

    # ------------------------------------------------------------------
    # enrichment_coverage — enriched / total
    # ------------------------------------------------------------------
    if total_alerts > 0:
        enriched_count_result = await db.execute(
            select(func.count(Alert.id)).where(
                Alert.created_at >= from_time,
                Alert.created_at < to_time,
                Alert.is_enriched.is_(True),
            )
        )
        enriched_count: int = enriched_count_result.scalar_one() or 0
        enrichment_coverage = enriched_count / total_alerts
    else:
        enrichment_coverage = 0.0

    return AlertMetricsResponse(
        period_from=from_time,
        period_to=to_time,
        total_alerts=total_alerts,
        alerts_by_status=alerts_by_status,
        alerts_by_severity=alerts_by_severity,
        alerts_by_source=alerts_by_source,
        alerts_over_time=alerts_over_time,
        false_positive_rate=false_positive_rate,
        mean_time_to_enrich=mean_time_to_enrich,
        mean_time_to_detect=mean_time_to_detect,
        mean_time_to_acknowledge=mean_time_to_acknowledge,
        mean_time_to_triage=mean_time_to_triage,
        mean_time_to_conclusion=mean_time_to_conclusion,
        active_alerts_by_severity=active_alerts_by_severity,
        top_detection_rules=top_detection_rules,
        enrichment_coverage=enrichment_coverage,
    )


async def compute_workflow_metrics(
    db: AsyncSession,
    from_time: datetime,
    to_time: datetime,
) -> WorkflowMetricsResponse:
    """Compute all workflow metrics for the given time window."""

    # ------------------------------------------------------------------
    # total_configured — all workflows regardless of state
    # ------------------------------------------------------------------
    total_configured_result = await db.execute(select(func.count(Workflow.id)))
    total_configured: int = total_configured_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # workflows_by_type — grouped by workflow_type
    # ------------------------------------------------------------------
    by_type_result = await db.execute(
        select(Workflow.workflow_type, func.count(Workflow.id)).group_by(
            Workflow.workflow_type
        )
    )
    workflows_by_type: dict[str, int] = {
        (row[0] if row[0] is not None else "unset"): row[1]
        for row in by_type_result.all()
    }

    # ------------------------------------------------------------------
    # workflow_run_count — total runs in time window
    # ------------------------------------------------------------------
    run_count_result = await db.execute(
        select(func.count(WorkflowRun.id)).where(
            WorkflowRun.created_at >= from_time,
            WorkflowRun.created_at < to_time,
        )
    )
    workflow_run_count: int = run_count_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # workflow_success_rate — successful / total runs in window
    # ------------------------------------------------------------------
    if workflow_run_count > 0:
        success_count_result = await db.execute(
            select(func.count(WorkflowRun.id)).where(
                WorkflowRun.created_at >= from_time,
                WorkflowRun.created_at < to_time,
                WorkflowRun.status == "success",
            )
        )
        success_count: int = success_count_result.scalar_one() or 0
        workflow_success_rate = success_count / workflow_run_count
    else:
        workflow_success_rate = 0.0

    # ------------------------------------------------------------------
    # workflow_runs_over_time — group by day
    # ------------------------------------------------------------------
    run_day_expr = func.date_trunc("day", WorkflowRun.created_at)
    runs_time_result = await db.execute(
        select(run_day_expr.label("day"), func.count(WorkflowRun.id).label("count"))
        .where(
            WorkflowRun.created_at >= from_time,
            WorkflowRun.created_at < to_time,
        )
        .group_by(run_day_expr)
        .order_by(run_day_expr)
    )
    workflow_runs_over_time: list[dict[str, Any]] = [
        {"date": row[0].strftime("%Y-%m-%d"), "count": row[1]}
        for row in runs_time_result.all()
    ]

    # ------------------------------------------------------------------
    # time_saved_hours — sum(time_saved_minutes) for successful runs / 60
    # ------------------------------------------------------------------
    time_saved_result = await db.execute(
        select(func.sum(Workflow.time_saved_minutes))
        .join(WorkflowRun, WorkflowRun.workflow_id == Workflow.id)
        .where(
            WorkflowRun.status == "success",
            WorkflowRun.created_at >= from_time,
            WorkflowRun.created_at < to_time,
            Workflow.time_saved_minutes.is_not(None),
        )
    )
    time_saved_raw = time_saved_result.scalar_one()
    time_saved_hours: float = float(time_saved_raw) / 60.0 if time_saved_raw else 0.0

    # ------------------------------------------------------------------
    # most_executed_workflows — top 10 by run count in window
    # ------------------------------------------------------------------
    most_exec_result = await db.execute(
        select(
            Workflow.uuid,
            Workflow.name,
            func.count(WorkflowRun.id).label("run_count"),
        )
        .join(WorkflowRun, WorkflowRun.workflow_id == Workflow.id)
        .where(
            WorkflowRun.created_at >= from_time,
            WorkflowRun.created_at < to_time,
        )
        .group_by(Workflow.uuid, Workflow.name)
        .order_by(func.count(WorkflowRun.id).desc())
        .limit(10)
    )
    most_executed_workflows: list[dict[str, Any]] = [
        {"uuid": str(row[0]), "name": row[1], "run_count": row[2]}
        for row in most_exec_result.all()
    ]

    return WorkflowMetricsResponse(
        period_from=from_time,
        period_to=to_time,
        total_configured=total_configured,
        workflows_by_type=workflows_by_type,
        workflow_run_count=workflow_run_count,
        workflow_success_rate=workflow_success_rate,
        workflow_runs_over_time=workflow_runs_over_time,
        time_saved_hours=time_saved_hours,
        most_executed_workflows=most_executed_workflows,
    )


async def compute_metrics_summary(db: AsyncSession) -> MetricsSummaryResponse:
    """
    Compact SOC health snapshot — always last 30 days.
    Optimized: 8 targeted queries, no full metric computation.
    """
    from datetime import UTC, timedelta

    now = datetime.now(UTC)
    from_time = now - timedelta(days=30)

    # ------------------------------------------------------------------
    # Alert: total
    # ------------------------------------------------------------------
    total_result = await db.execute(
        select(func.count(Alert.id)).where(Alert.created_at >= from_time)
    )
    total: int = total_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # Alert: active count
    # ------------------------------------------------------------------
    active_result = await db.execute(
        select(func.count(Alert.id)).where(
            Alert.created_at >= from_time,
            Alert.status.in_(["Open", "Triaging", "Escalated"]),
        )
    )
    active: int = active_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # Alert: by_severity (active alerts only)
    # ------------------------------------------------------------------
    sev_result = await db.execute(
        select(Alert.severity, func.count(Alert.id))
        .where(
            Alert.created_at >= from_time,
            Alert.status.in_(["Open", "Triaging", "Escalated"]),
        )
        .group_by(Alert.severity)
    )
    by_severity: dict[str, int] = {row[0]: row[1] for row in sev_result.all()}

    # ------------------------------------------------------------------
    # Alert: false_positive_rate
    # ------------------------------------------------------------------
    closed_result = await db.execute(
        select(func.count(Alert.id)).where(
            Alert.created_at >= from_time,
            Alert.status == "Closed",
        )
    )
    closed_count: int = closed_result.scalar_one() or 0

    if closed_count > 0:
        fp_result = await db.execute(
            select(func.count(Alert.id)).where(
                Alert.created_at >= from_time,
                Alert.status == "Closed",
                Alert.close_classification.like("False Positive%"),
            )
        )
        fp_count: int = fp_result.scalar_one() or 0
        false_positive_rate = fp_count / closed_count
    else:
        false_positive_rate = 0.0

    # ------------------------------------------------------------------
    # Alert: MTTD — AVG(created_at - occurred_at)
    # ------------------------------------------------------------------
    mttd_result = await db.execute(
        select(
            func.avg(extract("epoch", Alert.created_at - Alert.occurred_at))
        ).where(
            Alert.created_at >= from_time,
            Alert.occurred_at.is_not(None),
        )
    )
    mttd_raw = mttd_result.scalar_one()
    mttd_seconds: float | None = float(mttd_raw) if mttd_raw is not None else None

    # ------------------------------------------------------------------
    # Alert: MTTA — AVG(acknowledged_at - created_at)
    # ------------------------------------------------------------------
    mtta_result = await db.execute(
        select(
            func.avg(extract("epoch", Alert.acknowledged_at - Alert.created_at))
        ).where(
            Alert.created_at >= from_time,
            Alert.acknowledged_at.is_not(None),
        )
    )
    mtta_raw = mtta_result.scalar_one()
    mtta_seconds: float | None = float(mtta_raw) if mtta_raw is not None else None

    # ------------------------------------------------------------------
    # Alert: MTTT — AVG(triaged_at - created_at)
    # ------------------------------------------------------------------
    mttt_result = await db.execute(
        select(
            func.avg(extract("epoch", Alert.triaged_at - Alert.created_at))
        ).where(
            Alert.created_at >= from_time,
            Alert.triaged_at.is_not(None),
        )
    )
    mttt_raw = mttt_result.scalar_one()
    mttt_seconds: float | None = float(mttt_raw) if mttt_raw is not None else None

    # ------------------------------------------------------------------
    # Alert: MTTC — AVG(closed_at - created_at)
    # ------------------------------------------------------------------
    mttc_result = await db.execute(
        select(
            func.avg(extract("epoch", Alert.closed_at - Alert.created_at))
        ).where(
            Alert.created_at >= from_time,
            Alert.closed_at.is_not(None),
        )
    )
    mttc_raw = mttc_result.scalar_one()
    mttc_seconds: float | None = float(mttc_raw) if mttc_raw is not None else None

    # ------------------------------------------------------------------
    # Workflows: total_configured (active only)
    # ------------------------------------------------------------------
    wf_total_result = await db.execute(
        select(func.count(Workflow.id)).where(Workflow.state == "active")
    )
    wf_total_configured: int = wf_total_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # Workflows: executions (last 30 days)
    # ------------------------------------------------------------------
    wf_exec_result = await db.execute(
        select(func.count(WorkflowRun.id)).where(
            WorkflowRun.created_at >= from_time
        )
    )
    wf_executions: int = wf_exec_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # Workflows: success_rate
    # ------------------------------------------------------------------
    if wf_executions > 0:
        wf_success_result = await db.execute(
            select(func.count(WorkflowRun.id)).where(
                WorkflowRun.created_at >= from_time,
                WorkflowRun.status == "success",
            )
        )
        wf_success_count: int = wf_success_result.scalar_one() or 0
        wf_success_rate = wf_success_count / wf_executions
    else:
        wf_success_rate = 0.0

    # ------------------------------------------------------------------
    # Workflows: estimated_time_saved_hours
    # ------------------------------------------------------------------
    wf_time_saved_result = await db.execute(
        select(func.sum(Workflow.time_saved_minutes))
        .join(WorkflowRun, WorkflowRun.workflow_id == Workflow.id)
        .where(
            WorkflowRun.status == "success",
            WorkflowRun.created_at >= from_time,
            Workflow.time_saved_minutes.is_not(None),
        )
    )
    wf_time_saved_raw = wf_time_saved_result.scalar_one()
    estimated_time_saved_hours: float = (
        float(wf_time_saved_raw) / 60.0 if wf_time_saved_raw else 0.0
    )

    # ------------------------------------------------------------------
    # Approvals: pending (no time filter — current pending count)
    # ------------------------------------------------------------------
    ap_pending_result = await db.execute(
        select(func.count(WorkflowApprovalRequest.id)).where(
            WorkflowApprovalRequest.status == "pending"
        )
    )
    ap_pending: int = ap_pending_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # Approvals: approved_last_30_days
    # ------------------------------------------------------------------
    ap_approved_result = await db.execute(
        select(func.count(WorkflowApprovalRequest.id)).where(
            WorkflowApprovalRequest.status == "approved",
            WorkflowApprovalRequest.created_at >= from_time,
        )
    )
    ap_approved: int = ap_approved_result.scalar_one() or 0

    # ------------------------------------------------------------------
    # Approvals: approval_rate — approved / (approved + rejected) in window
    # ------------------------------------------------------------------
    ap_rejected_result = await db.execute(
        select(func.count(WorkflowApprovalRequest.id)).where(
            WorkflowApprovalRequest.status == "rejected",
            WorkflowApprovalRequest.created_at >= from_time,
            WorkflowApprovalRequest.responded_at.is_not(None),
        )
    )
    ap_rejected: int = ap_rejected_result.scalar_one() or 0

    ap_approved_decided_result = await db.execute(
        select(func.count(WorkflowApprovalRequest.id)).where(
            WorkflowApprovalRequest.status == "approved",
            WorkflowApprovalRequest.created_at >= from_time,
            WorkflowApprovalRequest.responded_at.is_not(None),
        )
    )
    ap_approved_decided: int = ap_approved_decided_result.scalar_one() or 0

    total_decided = ap_approved_decided + ap_rejected
    approval_rate: float = ap_approved_decided / total_decided if total_decided > 0 else 0.0

    # ------------------------------------------------------------------
    # Approvals: median_response_time_minutes — PERCENTILE_CONT(0.5)
    # ------------------------------------------------------------------
    median_result = await db.execute(
        text("""
            SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY EXTRACT('epoch' FROM responded_at - created_at) / 60
            )
            FROM workflow_approval_requests
            WHERE responded_at IS NOT NULL
              AND created_at >= :from_time
        """),
        {"from_time": from_time},
    )
    median_raw = median_result.scalar_one_or_none()
    median_response_time_minutes: float | None = (
        float(median_raw) if median_raw is not None else None
    )

    return MetricsSummaryResponse(
        period="last_30_days",
        alerts=MetricsSummaryAlerts(
            total=total,
            active=active,
            by_severity=by_severity,
            false_positive_rate=false_positive_rate,
            mttd_seconds=mttd_seconds,
            mtta_seconds=mtta_seconds,
            mttt_seconds=mttt_seconds,
            mttc_seconds=mttc_seconds,
        ),
        workflows=MetricsSummaryWorkflows(
            total_configured=wf_total_configured,
            executions=wf_executions,
            success_rate=wf_success_rate,
            estimated_time_saved_hours=estimated_time_saved_hours,
        ),
        approvals=MetricsSummaryApprovals(
            pending=ap_pending,
            approved_last_30_days=ap_approved,
            approval_rate=approval_rate,
            median_response_time_minutes=median_response_time_minutes,
        ),
    )
