"""
MCP tools for alert operations.

Tools (write/execute):
  - post_alert_finding   — Post an agent analysis finding to an alert
  - update_alert_status  — Update an alert's status
  - search_alerts        — Search alerts by filter criteria
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import UTC, datetime

import structlog
from mcp.server.fastmcp import Context

from app.db.session import AsyncSessionLocal
from app.mcp.scope import _resolve_client_id, check_scope
from app.mcp.server import mcp_server
from app.repositories.alert_repository import AlertRepository
from app.repositories.indicator_repository import IndicatorRepository
from app.schemas.activity_events import ActivityEventType
from app.schemas.alert import AlertStatus
from app.schemas.alerts import FindingConfidence
from app.schemas.indicators import MaliceLevel
from app.services.activity_event import ActivityEventService

logger = structlog.get_logger(__name__)

_VALID_STATUSES = sorted(s.value for s in AlertStatus)
_VALID_CONFIDENCES = sorted(c.value for c in FindingConfidence)


def _json_serial(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@mcp_server.tool()
async def post_alert_finding(
    alert_uuid: str,
    summary: str,
    confidence: str,
    ctx: Context,
    agent_name: str = "mcp-agent",
    recommended_action: str | None = None,
) -> str:
    """Post an agent analysis finding to an alert.

    Args:
        alert_uuid: UUID of the alert to attach the finding to.
        summary: Free-text analysis summary (what was found, why it matters).
        confidence: Confidence level — one of: "low", "medium", "high".
        agent_name: Name identifying the agent posting this finding.
        recommended_action: Optional suggested next step for the SOC analyst.

    Returns:
        JSON with the created finding ID and posted_at timestamp.
    """
    try:
        parsed_uuid = _uuid.UUID(alert_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {alert_uuid}"})

    if confidence not in _VALID_CONFIDENCES:
        return json.dumps({
            "error": f"Invalid confidence '{confidence}'. Must be one of: {_VALID_CONFIDENCES}"
        })

    async with AsyncSessionLocal() as session:
        # Scope check: alerts:write
        scope_err = await check_scope(ctx, session, "alerts:write")
        if scope_err:
            return scope_err

        repo = AlertRepository(session)
        alert = await repo.get_by_uuid(parsed_uuid)
        if alert is None:
            return json.dumps({"error": f"Alert not found: {alert_uuid}"})

        now = datetime.now(UTC)
        finding_id = str(_uuid.uuid4())
        finding = {
            "id": finding_id,
            "agent_name": agent_name,
            "summary": summary,
            "confidence": confidence,
            "recommended_action": recommended_action,
            "evidence": None,
            "posted_at": now.isoformat(),
        }

        await repo.add_finding(alert, finding)

        activity_svc = ActivityEventService(session)
        await activity_svc.write(
            ActivityEventType.ALERT_FINDING_ADDED,
            actor_type="mcp",
            actor_key_prefix=_resolve_client_id(ctx),
            alert_id=alert.id,
            references={"finding_id": finding_id, "agent_name": agent_name},
        )

        await session.commit()

        return json.dumps({
            "finding_id": finding_id,
            "alert_uuid": alert_uuid,
            "posted_at": now.isoformat(),
        })


@mcp_server.tool()
async def update_alert_status(
    alert_uuid: str,
    status: str,
    ctx: Context,
    close_classification: str | None = None,
) -> str:
    """Update the status of a security alert.

    Args:
        alert_uuid: UUID of the alert to update.
        status: New status value. Valid values: "pending_enrichment", "enriched",
                "Open", "Triaging", "Escalated", "Closed".
        close_classification: Required when setting status to "Closed". Example
                values: "True Positive - Suspicious Activity",
                "False Positive - Incorrect Detection Logic".

    Returns:
        JSON with the updated alert UUID, new status, and timestamp.
    """
    try:
        parsed_uuid = _uuid.UUID(alert_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {alert_uuid}"})

    if status not in _VALID_STATUSES:
        return json.dumps({
            "error": f"Invalid status '{status}'. Must be one of: {_VALID_STATUSES}"
        })

    if status == AlertStatus.CLOSED and not close_classification:
        return json.dumps({
            "error": "close_classification is required when setting status to 'Closed'."
        })

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "alerts:write")
        if scope_err:
            return scope_err

        repo = AlertRepository(session)
        alert = await repo.get_by_uuid(parsed_uuid)
        if alert is None:
            return json.dumps({"error": f"Alert not found: {alert_uuid}"})

        prev_status = alert.status

        await repo.patch(
            alert,
            status=AlertStatus(status),
            close_classification=close_classification,
        )

        resolved_client_id = _resolve_client_id(ctx)
        activity_svc = ActivityEventService(session)
        if status == AlertStatus.CLOSED:
            await activity_svc.write(
                ActivityEventType.ALERT_CLOSED,
                actor_type="mcp",
                actor_key_prefix=resolved_client_id,
                alert_id=alert.id,
                references={
                    "from_status": prev_status,
                    "close_classification": close_classification,
                },
            )
        else:
            await activity_svc.write(
                ActivityEventType.ALERT_STATUS_UPDATED,
                actor_type="mcp",
                actor_key_prefix=resolved_client_id,
                alert_id=alert.id,
                references={"from_status": prev_status, "to_status": status},
            )

        await session.commit()

        return json.dumps({
            "alert_uuid": alert_uuid,
            "status": status,
            "previous_status": prev_status,
            "updated_at": datetime.now(UTC).isoformat(),
        })


@mcp_server.tool()
async def search_alerts(
    ctx: Context,
    status: str | None = None,
    severity: str | None = None,
    source_name: str | None = None,
    is_enriched: bool | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    tags: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """Search alerts by filter criteria.

    Args:
        status: Filter by alert status (e.g. "Open", "Closed", "enriched").
        severity: Filter by severity (e.g. "High", "Critical").
        source_name: Filter by source (e.g. "sentinel", "elastic").
        is_enriched: Filter by enrichment state (true/false).
        from_time: ISO 8601 start time for occurred_at filter.
        to_time: ISO 8601 end time for occurred_at filter.
        tags: Comma-separated list of tags to filter by.
        page: Page number (1-indexed, default 1).
        page_size: Results per page (default 20, max 100).

    Returns:
        JSON with matching alerts and pagination metadata.
    """
    parsed_from = None
    parsed_to = None
    if from_time:
        try:
            parsed_from = datetime.fromisoformat(from_time)
        except ValueError:
            return json.dumps({"error": f"Invalid from_time format: {from_time}"})
    if to_time:
        try:
            parsed_to = datetime.fromisoformat(to_time)
        except ValueError:
            return json.dumps({"error": f"Invalid to_time format: {to_time}"})

    parsed_tags = [t.strip() for t in tags.split(",")] if tags else None
    page_size = min(page_size, 100)

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "alerts:read")
        if scope_err:
            return scope_err

        repo = AlertRepository(session)
        alerts, total = await repo.list_alerts(
            status=status,
            severity=severity,
            source_name=source_name,
            is_enriched=is_enriched,
            from_time=parsed_from,
            to_time=parsed_to,
            tags=parsed_tags,
            page=page,
            page_size=page_size,
        )

        result = [
            {
                "uuid": str(a.uuid),
                "title": a.title,
                "severity": a.severity,
                "status": a.status,
                "source_name": a.source_name,
                "occurred_at": a.occurred_at.isoformat(),
                "is_enriched": a.is_enriched,
                "tags": a.tags,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]

        return json.dumps({
            "alerts": result,
            "total": total,
            "page": page,
            "page_size": page_size,
        }, default=_json_serial)


_VALID_MALICE = sorted(m.value for m in MaliceLevel)


@mcp_server.tool()
async def update_alert_malice(
    alert_uuid: str,
    ctx: Context,
    malice: str | None = None,
) -> str:
    """Set or reset the malice override on an alert.

    When malice is provided, the alert's effective malice is overridden to the
    given value (analyst verdict). When malice is null/omitted, any existing
    override is cleared and the alert returns to computing malice from its
    indicators.

    Args:
        alert_uuid: UUID of the alert to update.
        malice: Malice verdict to set. Valid values: "Pending", "Benign",
                "Suspicious", "Malicious". Pass null to reset to computed.

    Returns:
        JSON with the updated alert UUID, malice override, and timestamp.
    """
    try:
        parsed_uuid = _uuid.UUID(alert_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {alert_uuid}"})

    if malice is not None and malice not in _VALID_MALICE:
        return json.dumps({
            "error": f"Invalid malice '{malice}'. Must be one of: {_VALID_MALICE}"
        })

    reset = malice is None

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "alerts:write")
        if scope_err:
            return scope_err

        repo = AlertRepository(session)
        alert = await repo.get_by_uuid(parsed_uuid)
        if alert is None:
            return json.dumps({"error": f"Alert not found: {alert_uuid}"})

        prev_malice = alert.malice_override

        await repo.patch(
            alert,
            malice_override=malice,
            reset_malice_override=reset,
        )

        activity_svc = ActivityEventService(session)
        await activity_svc.write(
            ActivityEventType.ALERT_MALICE_UPDATED,
            actor_type="mcp",
            actor_key_prefix=_resolve_client_id(ctx),
            alert_id=alert.id,
            references={
                "from_malice": prev_malice,
                "to_malice": malice,
                "malice_source": "reset" if reset else "analyst",
            },
        )

        await session.commit()

        # Compute effective malice for the response
        effective_malice = malice
        if reset:
            indicator_repo = IndicatorRepository(session)
            indicators = await indicator_repo.list_for_alert(alert.id)
            malice_order = {"Malicious": 3, "Suspicious": 2, "Benign": 1, "Pending": 0}
            effective_malice = "Pending"
            for ind in indicators:
                if malice_order.get(ind.malice, 0) > malice_order.get(effective_malice, 0):
                    effective_malice = ind.malice

        return json.dumps({
            "alert_uuid": alert_uuid,
            "malice_override": malice,
            "effective_malice": effective_malice,
            "updated_at": datetime.now(UTC).isoformat(),
        })
