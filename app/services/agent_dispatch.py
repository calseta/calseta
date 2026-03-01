"""
Agent dispatch service — build webhook payloads and deliver to registered agents.

Two public functions:
  build_webhook_payload(alert_id, db)  — assemble full enriched alert payload
  dispatch_to_agent(agent, alert_id, payload, db) — POST with retries; write AgentRun audit record

Design decisions:
  - Never raises — all errors are caught and returned as failed status
  - One AgentRun record per delivery attempt
  - Auth header decryption is best-effort: logs a warning and skips if no ENCRYPTION_KEY
  - Exponential backoff: 1s, 2s, 4s, ... between retries (2**attempt)
  - Enrichment results in payload strip the "raw" key per provider (token optimization)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.agent_registration import AgentRegistration
from app.db.models.alert import Alert
from app.db.models.detection_rule import DetectionRule
from app.db.models.workflow import Workflow
from app.repositories.alert_repository import AlertRepository
from app.repositories.indicator_repository import IndicatorRepository
from app.services.agent_runs import record_agent_run
from app.services.context_targeting import get_applicable_documents

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Payload builder helpers
# ---------------------------------------------------------------------------


def _build_indicator_dict(ind: object) -> dict[str, Any]:
    """Serialize an Indicator ORM object to a dict for the webhook payload."""
    from app.db.models.indicator import Indicator

    assert isinstance(ind, Indicator)

    # Build enrichment_results excluding "raw" key per provider (token optimization)
    enrichment_results: dict[str, Any] = {}
    raw_er = ind.enrichment_results or {}
    for provider_name, provider_data in raw_er.items():
        if isinstance(provider_data, dict):
            enrichment_results[provider_name] = {
                k: v for k, v in provider_data.items() if k != "raw"
            }
        else:
            enrichment_results[provider_name] = provider_data

    return {
        "uuid": str(ind.uuid),  # type: ignore[union-attr]
        "type": ind.type,  # type: ignore[union-attr]
        "value": ind.value,  # type: ignore[union-attr]
        "malice": ind.malice,  # type: ignore[union-attr]
        "first_seen": ind.first_seen.isoformat() if ind.first_seen else None,  # type: ignore[union-attr]
        "last_seen": ind.last_seen.isoformat() if ind.last_seen else None,  # type: ignore[union-attr]
        "is_enriched": ind.is_enriched,  # type: ignore[union-attr]
        "enrichment_results": enrichment_results,
    }


def _build_alert_dict(
    alert: Alert, indicator_count: int, context_doc_count: int
) -> dict[str, Any]:
    """Serialize an Alert ORM object to a dict with _metadata block."""
    metadata: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "alert_source": alert.source_name,
        "indicator_count": indicator_count,
        "enrichment": {
            "succeeded": [],
            "failed": [],
            "enriched_at": alert.enriched_at.isoformat() if alert.enriched_at else None,
        },
        "detection_rule_matched": alert.detection_rule_id is not None,
        "context_documents_applied": context_doc_count,
    }

    return {
        "uuid": str(alert.uuid),
        "title": alert.title,
        "severity": alert.severity,
        "severity_id": alert.severity_id,
        "source_name": alert.source_name,
        "status": alert.status,
        "occurred_at": alert.occurred_at.isoformat() if alert.occurred_at else None,
        "ingested_at": alert.ingested_at.isoformat() if alert.ingested_at else None,
        "enriched_at": alert.enriched_at.isoformat() if alert.enriched_at else None,
        "is_enriched": alert.is_enriched,
        "tags": list(alert.tags or []),
        "close_classification": alert.close_classification,
        "acknowledged_at": (
            alert.acknowledged_at.isoformat() if alert.acknowledged_at else None
        ),
        "triaged_at": alert.triaged_at.isoformat() if alert.triaged_at else None,
        "closed_at": alert.closed_at.isoformat() if alert.closed_at else None,
        "agent_findings": alert.agent_findings or [],
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
        "_metadata": metadata,
    }


def _build_detection_rule_dict(rule: DetectionRule | None) -> dict[str, Any] | None:
    """Serialize a DetectionRule ORM object; returns None if no rule matched."""
    if rule is None:
        return None
    return {
        "uuid": str(rule.uuid),
        "name": rule.name,
        "source_rule_id": rule.source_rule_id,
        "source_name": rule.source_name,
        "severity": rule.severity,
        "is_active": rule.is_active,
        "mitre_tactics": list(rule.mitre_tactics or []),
        "mitre_techniques": list(rule.mitre_techniques or []),
        "mitre_subtechniques": list(rule.mitre_subtechniques or []),
        "data_sources": list(rule.data_sources or []),
        "run_frequency": rule.run_frequency,
        "created_by": rule.created_by,
        "documentation": rule.documentation,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


def _build_context_doc_dict(doc: object) -> dict[str, Any]:
    """Serialize a ContextDocument ORM object."""
    from app.db.models.context_document import ContextDocument

    assert isinstance(doc, ContextDocument)
    return {
        "uuid": str(doc.uuid),
        "title": doc.title,
        "document_type": doc.document_type,
        "description": doc.description,
        "is_global": doc.is_global,
        "tags": list(doc.tags or []),
        "content": doc.content,
        "version": doc.version,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }


def _build_workflow_summary_dict(workflow: Workflow) -> dict[str, Any]:
    """Serialize a Workflow ORM object summary (no code) for webhook payload."""
    return {
        "uuid": str(workflow.uuid),
        "name": workflow.name,
        "workflow_type": workflow.workflow_type,
        "documentation": workflow.documentation,
        "risk_level": workflow.risk_level,
        "requires_approval": workflow.requires_approval,
        "indicator_types": list(workflow.indicator_types or []),
        "tags": list(workflow.tags or []),
    }


# ---------------------------------------------------------------------------
# Public: payload builder
# ---------------------------------------------------------------------------


async def build_webhook_payload(alert_id: int, db: AsyncSession) -> dict[str, Any]:
    """
    Assemble the full enriched alert webhook payload.

    Returns dict with:
      alert              — full alert dict with _metadata block
      indicators         — list of indicator dicts (enrichment_results excludes "raw" key)
      detection_rule     — full rule dict with documentation, or None
      context_documents  — applicable context docs for this alert
      workflows          — active workflow summaries (no code), limit 20
      calseta_api_base_url — from settings.CALSETA_API_BASE_URL
    """
    alert_repo = AlertRepository(db)
    indicator_repo = IndicatorRepository(db)

    alert = await alert_repo.get_by_id(alert_id)
    if alert is None:
        return {}

    # Load indicators
    indicators = await indicator_repo.list_for_alert(alert_id)
    indicator_dicts = [_build_indicator_dict(ind) for ind in indicators]

    # Load applicable context documents
    context_docs = await get_applicable_documents(alert, db)
    context_doc_dicts = [_build_context_doc_dict(doc) for doc in context_docs]

    # Build alert dict (includes _metadata with context_doc count)
    alert_dict = _build_alert_dict(alert, len(indicators), len(context_docs))

    # Load matched detection rule if present
    detection_rule: DetectionRule | None = None
    if alert.detection_rule_id is not None:
        dr_result = await db.execute(
            select(DetectionRule).where(DetectionRule.id == alert.detection_rule_id)
        )
        detection_rule = dr_result.scalar_one_or_none()
    detection_rule_dict = _build_detection_rule_dict(detection_rule)

    # Load active workflows (limit 20, no code field included)
    wf_result = await db.execute(
        select(Workflow)
        .where(Workflow.state == "active")
        .order_by(Workflow.created_at.asc())
        .limit(20)
    )
    active_workflows = list(wf_result.scalars().all())
    workflow_dicts = [_build_workflow_summary_dict(wf) for wf in active_workflows]

    return {
        "alert": alert_dict,
        "indicators": indicator_dicts,
        "detection_rule": detection_rule_dict,
        "context_documents": context_doc_dicts,
        "workflows": workflow_dicts,
        "calseta_api_base_url": settings.CALSETA_API_BASE_URL,
    }


# ---------------------------------------------------------------------------
# Public: webhook delivery with retries
# ---------------------------------------------------------------------------


async def dispatch_to_agent(
    agent: AgentRegistration,
    alert_id: int,
    payload: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    """
    POST the webhook payload to the agent endpoint with retries.

    - Decrypts auth_header_value_encrypted if present; skips on ValueError (no key)
    - Timeout = agent.timeout_seconds per request
    - Retries up to agent.retry_count times with exponential backoff (2**attempt seconds)
    - Writes one AgentRun audit record per delivery attempt regardless of outcome
    - Returns: {"status": "success"|"failed"|"timeout", "status_code": N|None,
                 "attempt_count": N, "error": str|None}

    Never raises.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}

    # Decrypt auth header if configured
    if agent.auth_header_name and agent.auth_header_value_encrypted:
        try:
            from app.auth.encryption import decrypt_value

            decrypted = decrypt_value(agent.auth_header_value_encrypted)
            headers[agent.auth_header_name] = decrypted
        except ValueError:
            logger.warning(
                "agent_auth_decrypt_skipped",
                agent_uuid=str(agent.uuid),
                reason="ENCRYPTION_KEY not set",
            )
        except Exception:
            logger.warning(
                "agent_auth_decrypt_failed",
                agent_uuid=str(agent.uuid),
            )

    max_attempts = max(1, agent.retry_count + 1)  # retry_count retries after initial attempt
    last_status_code: int | None = None
    last_error: str | None = None
    attempt_count = 0
    final_status = "failed"

    async with httpx.AsyncClient(timeout=float(agent.timeout_seconds)) as client:
        for attempt in range(max_attempts):
            attempt_count = attempt + 1
            started_at = datetime.now(UTC)
            attempt_status = "failed"
            response_body: dict[str, Any] | None = None
            current_status_code: int | None = None
            current_error: str | None = None

            try:
                response = await client.post(
                    agent.endpoint_url,
                    json=payload,
                    headers=headers,
                )
                current_status_code = response.status_code
                last_status_code = current_status_code

                # Try to parse response body as JSON
                try:
                    response_body = response.json()
                except Exception:
                    raw_text = response.text
                    response_body = {"raw": raw_text[:2000]} if raw_text else None

                if response.is_success:
                    attempt_status = "success"
                    final_status = "success"
                else:
                    current_error = f"HTTP {current_status_code}"
                    last_error = current_error
                    logger.warning(
                        "agent_webhook_non_2xx",
                        agent_uuid=str(agent.uuid),
                        status_code=current_status_code,
                        attempt=attempt_count,
                    )

            except httpx.TimeoutException as exc:
                current_error = f"Timeout: {exc}"
                last_error = current_error
                attempt_status = "timeout"
                final_status = "timeout"
                logger.warning(
                    "agent_webhook_timeout",
                    agent_uuid=str(agent.uuid),
                    attempt=attempt_count,
                )
            except httpx.RequestError as exc:
                current_error = f"Connection error: {exc}"
                last_error = current_error
                logger.warning(
                    "agent_webhook_connection_error",
                    agent_uuid=str(agent.uuid),
                    attempt=attempt_count,
                    error=str(exc),
                )

            completed_at = datetime.now(UTC)

            try:
                await record_agent_run(
                    db,
                    agent_registration_id=agent.id,
                    alert_id=alert_id,
                    status=attempt_status,
                    attempt_count=attempt_count,
                    request_payload={"endpoint_url": agent.endpoint_url},
                    response_status_code=current_status_code,
                    response_body=response_body,
                    started_at=started_at,
                    completed_at=completed_at,
                )
            except Exception:
                logger.exception(
                    "agent_run_record_failed",
                    agent_uuid=str(agent.uuid),
                    attempt=attempt_count,
                )

            if attempt_status == "success":
                logger.info(
                    "agent_webhook_delivered",
                    agent_uuid=str(agent.uuid),
                    status_code=current_status_code,
                    attempt=attempt_count,
                )
                return {
                    "status": "success",
                    "status_code": last_status_code,
                    "attempt_count": attempt_count,
                    "error": None,
                }

            # Backoff before next retry
            if attempt < max_attempts - 1:
                await asyncio.sleep(2**attempt)

    logger.error(
        "agent_webhook_all_attempts_failed",
        agent_uuid=str(agent.uuid),
        attempt_count=attempt_count,
        error=last_error,
    )
    return {
        "status": final_status,
        "status_code": last_status_code,
        "attempt_count": attempt_count,
        "error": last_error,
    }
