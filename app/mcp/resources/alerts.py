"""
MCP resources for alerts.

Exposes alert data as MCP resources for AI agent consumption:
  - calseta://alerts              — Recent alerts (last 50)
  - calseta://alerts/{uuid}       — Full alert with indicators, detection rule, context docs
  - calseta://alerts/{uuid}/context  — Applicable context documents
  - calseta://alerts/{uuid}/activity — Activity log (newest-first, max 100)
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime
from typing import Any

import structlog

from app.db.session import AsyncSessionLocal
from app.mcp.server import mcp_server
from app.repositories.activity_event_repository import ActivityEventRepository
from app.repositories.alert_repository import AlertRepository
from app.repositories.indicator_repository import IndicatorRepository
from app.services.context_targeting import get_applicable_documents

logger = structlog.get_logger(__name__)


def _json_serial(obj: object) -> str:
    """JSON serializer for objects not handled by default json encoder."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _filter_enrichment_results(raw_results: dict[str, Any] | None) -> dict[str, Any] | None:
    """Strip the `raw` key from each provider's enrichment data."""
    if not raw_results:
        return raw_results
    filtered: dict[str, Any] = {}
    for provider, data in raw_results.items():
        if isinstance(data, dict):
            filtered[provider] = {k: v for k, v in data.items() if k != "raw"}
        else:
            filtered[provider] = data
    return filtered


@mcp_server.resource("calseta://alerts")
async def list_alerts() -> str:
    """Recent alerts (last 50) with status, severity, source, and enrichment state."""
    async with AsyncSessionLocal() as session:
        repo = AlertRepository(session)
        alerts, _total = await repo.list_alerts(page=1, page_size=50)

        result = [
            {
                "uuid": str(a.uuid),
                "title": a.title,
                "severity": a.severity,
                "severity_id": a.severity_id,
                "status": a.status,
                "source_name": a.source_name,
                "occurred_at": a.occurred_at.isoformat(),
                "is_enriched": a.is_enriched,
                "tags": a.tags,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ]

        return json.dumps(
            {"alerts": result, "count": len(result)},
            default=_json_serial,
        )


@mcp_server.resource("calseta://alerts/{uuid}")
async def get_alert(uuid: str) -> str:
    """Full alert with indicators, detection rule documentation, and applicable context docs."""
    try:
        alert_uuid = _uuid.UUID(uuid)
    except ValueError:
        raise ValueError(f"Invalid UUID: {uuid}")

    async with AsyncSessionLocal() as session:
        alert_repo = AlertRepository(session)
        indicator_repo = IndicatorRepository(session)

        alert = await alert_repo.get_by_uuid(alert_uuid)
        if alert is None:
            raise ValueError(f"Alert not found: {uuid}")

        # Build indicators
        indicators = await indicator_repo.list_for_alert(alert.id)
        indicator_data = [
            {
                "uuid": str(ind.uuid),
                "type": ind.type,
                "value": ind.value,
                "malice": ind.malice,
                "is_enriched": ind.is_enriched,
                "first_seen": ind.first_seen.isoformat() if ind.first_seen else None,
                "last_seen": ind.last_seen.isoformat() if ind.last_seen else None,
                "enrichment_results": _filter_enrichment_results(ind.enrichment_results),
            }
            for ind in indicators
        ]

        # Build detection rule (if linked) — use repository to avoid lazy load
        detection_rule_data = None
        if alert.detection_rule_id is not None:
            from sqlalchemy import select

            from app.db.models.detection_rule import DetectionRule

            rule_result = await session.execute(
                select(DetectionRule).where(DetectionRule.id == alert.detection_rule_id)
            )
            rule = rule_result.scalar_one_or_none()
            if rule is not None:
                detection_rule_data = {
                    "uuid": str(rule.uuid),
                    "name": rule.name,
                    "severity": rule.severity,
                    "mitre_tactics": rule.mitre_tactics,
                    "mitre_techniques": rule.mitre_techniques,
                    "mitre_subtechniques": rule.mitre_subtechniques,
                    "documentation": rule.documentation,
                }

        # Applicable context documents
        context_docs = await get_applicable_documents(alert, session)
        context_data = [
            {
                "uuid": str(doc.uuid),
                "title": doc.title,
                "document_type": doc.document_type,
                "content": doc.content,
            }
            for doc in context_docs
        ]

        result = {
            "uuid": str(alert.uuid),
            "title": alert.title,
            "severity": alert.severity,
            "severity_id": alert.severity_id,
            "status": alert.status,
            "source_name": alert.source_name,
            "occurred_at": alert.occurred_at.isoformat(),
            "ingested_at": alert.ingested_at.isoformat(),
            "enriched_at": alert.enriched_at.isoformat() if alert.enriched_at else None,
            "is_enriched": alert.is_enriched,
            "close_classification": alert.close_classification,
            "acknowledged_at": alert.acknowledged_at.isoformat()
            if alert.acknowledged_at
            else None,
            "triaged_at": alert.triaged_at.isoformat() if alert.triaged_at else None,
            "closed_at": alert.closed_at.isoformat() if alert.closed_at else None,
            "tags": alert.tags,
            "indicators": indicator_data,
            "detection_rule": detection_rule_data,
            "context_documents": context_data,
            "agent_findings": alert.agent_findings,
        }

        return json.dumps(result, default=_json_serial)


@mcp_server.resource("calseta://alerts/{uuid}/context")
async def get_alert_context(uuid: str) -> str:
    """Applicable context documents for an alert, ordered by global-first then targeted."""
    try:
        alert_uuid = _uuid.UUID(uuid)
    except ValueError:
        raise ValueError(f"Invalid UUID: {uuid}")

    async with AsyncSessionLocal() as session:
        alert_repo = AlertRepository(session)
        alert = await alert_repo.get_by_uuid(alert_uuid)
        if alert is None:
            raise ValueError(f"Alert not found: {uuid}")

        docs = await get_applicable_documents(alert, session)
        result = [
            {
                "uuid": str(doc.uuid),
                "title": doc.title,
                "document_type": doc.document_type,
                "is_global": doc.is_global,
                "description": doc.description,
                "content": doc.content,
                "tags": doc.tags,
            }
            for doc in docs
        ]

        return json.dumps({"context_documents": result, "count": len(result)})


@mcp_server.resource("calseta://alerts/{uuid}/activity")
async def get_alert_activity(uuid: str) -> str:
    """Activity log for an alert, newest-first, max 100 events."""
    try:
        alert_uuid = _uuid.UUID(uuid)
    except ValueError:
        raise ValueError(f"Invalid UUID: {uuid}")

    async with AsyncSessionLocal() as session:
        alert_repo = AlertRepository(session)
        activity_repo = ActivityEventRepository(session)

        alert = await alert_repo.get_by_uuid(alert_uuid)
        if alert is None:
            raise ValueError(f"Alert not found: {uuid}")

        events, _total = await activity_repo.list_for_alert(
            alert.id, page=1, page_size=100
        )

        result = []
        for event in events:
            # Flatten references as key-value pairs alongside core fields
            entry: dict[str, Any] = {
                "event_type": event.event_type,
                "actor_type": event.actor_type,
                "actor_key_prefix": event.actor_key_prefix,
                "created_at": event.created_at.isoformat(),
            }
            if event.references:
                for key, value in event.references.items():
                    entry[key] = value
            result.append(entry)

        return json.dumps({"activity": result, "count": len(result)})
