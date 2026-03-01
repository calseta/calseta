"""
Alert management routes.

GET    /v1/alerts                            — List alerts with filters
GET    /v1/alerts/{uuid}                     — Get alert detail (includes indicators + _metadata)
PATCH  /v1/alerts/{uuid}                     — Update alert (status, severity, tags, classification)
DELETE /v1/alerts/{uuid}                     — Delete alert
POST   /v1/alerts/{uuid}/findings           — Add an agent finding to an alert
GET    /v1/alerts/{uuid}/activity           — List activity events for an alert
"""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.db.session import get_db
from app.queue.base import TaskQueueBase
from app.queue.dependencies import get_queue
from app.repositories.activity_event_repository import ActivityEventRepository
from app.repositories.alert_repository import AlertRepository
from app.repositories.indicator_repository import IndicatorRepository
from app.schemas.activity_events import ActivityEventResponse, ActivityEventType
from app.schemas.alert import AlertStatus
from app.schemas.alerts import (
    AlertMetadata,
    AlertPatch,
    AlertResponse,
    AlertSummary,
    FindingConfidence,
    FindingCreate,
    FindingResponse,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.context_documents import ContextDocumentResponse
from app.schemas.indicators import EnrichedIndicator, IndicatorResponse
from app.services.activity_event import ActivityEventService
from app.services.agent_trigger import get_matching_agents
from app.services.context_targeting import get_applicable_documents

router = APIRouter(prefix="/alerts", tags=["alerts"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_WRITE))]


def _filter_enrichment_results(raw_results: dict | None) -> dict | None:  # type: ignore[type-arg]
    """Strip the `raw` key from each provider's enrichment data before returning to callers."""
    if not raw_results:
        return raw_results
    filtered = {}
    for provider, data in raw_results.items():
        filtered[provider] = {k: v for k, v in data.items() if k != "raw"}
    return filtered


def _build_indicator(ind: object) -> EnrichedIndicator:
    from app.db.models.indicator import Indicator

    assert isinstance(ind, Indicator)
    return EnrichedIndicator(
        uuid=str(ind.uuid),
        type=ind.type,  # type: ignore[arg-type]
        value=ind.value,
        first_seen=ind.first_seen,
        last_seen=ind.last_seen,
        is_enriched=ind.is_enriched,
        malice=ind.malice,
        enrichment_results=ind.enrichment_results,
        created_at=ind.created_at,
        updated_at=ind.updated_at,
    )


def _build_metadata(alert: object, indicator_count: int) -> AlertMetadata:
    from app.db.models.alert import Alert

    assert isinstance(alert, Alert)
    enrichment: dict[str, object] = {
        "succeeded": [],
        "failed": [],
        "enriched_at": alert.enriched_at.isoformat() if alert.enriched_at else None,
    }
    return AlertMetadata(
        generated_at=datetime.now(UTC),
        alert_source=alert.source_name,
        indicator_count=indicator_count,
        enrichment=enrichment,
        detection_rule_matched=alert.detection_rule_id is not None,
        context_documents_applied=0,
    )


@router.get("", response_model=PaginatedResponse[AlertSummary])
async def list_alerts(
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(None),
    severity: str | None = Query(None),
    source_name: str | None = Query(None),
    is_enriched: bool | None = Query(None),
    detection_rule_uuid: UUID | None = Query(None),
    from_time: datetime | None = Query(None),
    to_time: datetime | None = Query(None),
    tags: list[str] | None = Query(None),
) -> PaginatedResponse[AlertSummary]:
    repo = AlertRepository(db)
    alerts, total = await repo.list_alerts(
        status=status,
        severity=severity,
        source_name=source_name,
        is_enriched=is_enriched,
        detection_rule_uuid=detection_rule_uuid,
        from_time=from_time,
        to_time=to_time,
        tags=tags,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[AlertSummary.model_validate(a) for a in alerts],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


@router.get("/{alert_uuid}", response_model=DataResponse[AlertResponse])
async def get_alert(
    alert_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AlertResponse]:
    alert_repo = AlertRepository(db)
    indicator_repo = IndicatorRepository(db)

    alert = await alert_repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    indicators = await indicator_repo.list_for_alert(alert.id)
    enriched_indicators = [_build_indicator(i) for i in indicators]
    metadata = _build_metadata(alert, len(enriched_indicators))

    response = AlertResponse.model_validate(alert)
    response.indicators = enriched_indicators

    return DataResponse(data=response, meta={"_metadata": metadata.model_dump()})


@router.patch("/{alert_uuid}", response_model=DataResponse[AlertResponse])
async def patch_alert(
    alert_uuid: UUID,
    body: AlertPatch,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AlertResponse]:
    alert_repo = AlertRepository(db)
    indicator_repo = IndicatorRepository(db)
    activity_svc = ActivityEventService(db)

    alert = await alert_repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Validate: close_classification required when closing
    if body.status == AlertStatus.CLOSED and body.close_classification is None:
        raise CalsetaException(
            code="VALIDATION_ERROR",
            message="close_classification is required when setting status to Closed.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    prev_status = alert.status
    prev_severity = alert.severity

    updated = await alert_repo.patch(
        alert,
        status=body.status,
        severity=body.severity,
        tags=body.tags,
        close_classification=body.close_classification.value
        if body.close_classification
        else None,
    )

    # Activity events for significant transitions
    if body.status is not None and body.status.value != prev_status:
        if body.status == AlertStatus.CLOSED:
            await activity_svc.write(
                ActivityEventType.ALERT_CLOSED,
                actor_type="api",
                actor_key_prefix=auth.key_prefix,
                alert_id=alert.id,
                references={
                    "from_status": prev_status,
                    "close_classification": body.close_classification.value
                    if body.close_classification
                    else None,
                },
            )
        else:
            await activity_svc.write(
                ActivityEventType.ALERT_STATUS_UPDATED,
                actor_type="api",
                actor_key_prefix=auth.key_prefix,
                alert_id=alert.id,
                references={"from_status": prev_status, "to_status": body.status.value},
            )

    if body.severity is not None and body.severity.value != prev_severity:
        await activity_svc.write(
            ActivityEventType.ALERT_SEVERITY_UPDATED,
            actor_type="api",
            actor_key_prefix=auth.key_prefix,
            alert_id=alert.id,
            references={
                "from_severity": prev_severity,
                "to_severity": body.severity.value,
            },
        )

    indicators = await indicator_repo.list_for_alert(updated.id)
    enriched_indicators = [_build_indicator(i) for i in indicators]
    metadata = _build_metadata(updated, len(enriched_indicators))

    response = AlertResponse.model_validate(updated)
    response.indicators = enriched_indicators

    return DataResponse(data=response, meta={"_metadata": metadata.model_dump()})


@router.delete("/{alert_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = AlertRepository(db)
    alert = await repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await repo.delete(alert)


@router.post(
    "/{alert_uuid}/findings",
    response_model=DataResponse[FindingResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_finding(
    alert_uuid: UUID,
    body: FindingCreate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[FindingResponse]:
    alert_repo = AlertRepository(db)
    activity_svc = ActivityEventService(db)

    alert = await alert_repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    now = datetime.now(UTC)
    finding_id = str(_uuid.uuid4())
    finding = {
        "id": finding_id,
        "agent_name": body.agent_name,
        "summary": body.summary,
        "confidence": body.confidence.value if body.confidence else None,
        "recommended_action": body.recommended_action,
        "evidence": body.evidence,
        "posted_at": now.isoformat(),
    }

    await alert_repo.add_finding(alert, finding)

    await activity_svc.write(
        ActivityEventType.ALERT_FINDING_ADDED,
        actor_type="api",
        actor_key_prefix=auth.key_prefix,
        alert_id=alert.id,
        references={"finding_id": finding_id, "agent_name": body.agent_name},
    )

    return DataResponse(
        data=FindingResponse(
            id=finding_id,
            agent_name=body.agent_name,
            summary=body.summary,
            confidence=body.confidence,
            recommended_action=body.recommended_action,
            evidence=body.evidence,
            posted_at=now,
        )
    )


@router.get(
    "/{alert_uuid}/findings",
    response_model=DataResponse[list[FindingResponse]],
)
async def list_findings(
    alert_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[list[FindingResponse]]:
    """Return all agent findings for an alert, ordered by posted_at."""
    alert_repo = AlertRepository(db)
    alert = await alert_repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    raw_findings = alert.agent_findings or []
    findings = sorted(raw_findings, key=lambda f: f.get("posted_at", ""))
    result = [
        FindingResponse(
            id=f["id"],
            agent_name=f["agent_name"],
            summary=f["summary"],
            confidence=FindingConfidence(f["confidence"]) if f.get("confidence") else None,
            recommended_action=f.get("recommended_action"),
            evidence=f.get("evidence"),
            posted_at=datetime.fromisoformat(f["posted_at"]),
        )
        for f in findings
    ]
    return DataResponse(data=result)


# ---------------------------------------------------------------------------
# GET /v1/alerts/{uuid}/context
# ---------------------------------------------------------------------------


@router.get(
    "/{alert_uuid}/context",
    response_model=DataResponse[list[ContextDocumentResponse]],
)
async def get_alert_context(
    alert_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[list[ContextDocumentResponse]]:
    """
    Return all applicable context documents for an alert.

    Global documents appear first (sorted by document_type), followed by
    targeted documents that match the alert's fields (also sorted by document_type).
    """
    alert_repo = AlertRepository(db)
    alert = await alert_repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    docs = await get_applicable_documents(alert, db)
    return DataResponse(data=[ContextDocumentResponse.model_validate(d) for d in docs])


# ---------------------------------------------------------------------------
# GET /v1/alerts/{uuid}/indicators
# ---------------------------------------------------------------------------


@router.get(
    "/{alert_uuid}/indicators",
    response_model=DataResponse[list[IndicatorResponse]],
)
async def list_alert_indicators(
    alert_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[list[IndicatorResponse]]:
    """
    Return all indicators linked to an alert.

    Each indicator includes enrichment results keyed by provider with the raw
    response excluded — only the extracted sub-object, success flag, and
    enriched_at timestamp are returned.
    """
    alert_repo = AlertRepository(db)
    indicator_repo = IndicatorRepository(db)

    alert = await alert_repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    indicators = await indicator_repo.list_for_alert(alert.id)
    result = [
        IndicatorResponse(
            uuid=str(ind.uuid),
            type=ind.type,  # type: ignore[arg-type]
            value=ind.value,
            malice=ind.malice,
            first_seen=ind.first_seen,
            last_seen=ind.last_seen,
            is_enriched=ind.is_enriched,
            enrichment_results=_filter_enrichment_results(ind.enrichment_results),
            created_at=ind.created_at,
            updated_at=ind.updated_at,
        )
        for ind in indicators
    ]
    return DataResponse(data=result)


# ---------------------------------------------------------------------------
# GET /v1/alerts/{uuid}/activity
# ---------------------------------------------------------------------------


@router.get(
    "/{alert_uuid}/activity",
    response_model=PaginatedResponse[ActivityEventResponse],
)
async def list_alert_activity(
    alert_uuid: UUID,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[ActivityEventResponse]:
    alert_repo = AlertRepository(db)
    activity_repo = ActivityEventRepository(db)

    alert = await alert_repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    events, total = await activity_repo.list_for_alert(
        alert.id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[ActivityEventResponse.model_validate(e) for e in events],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# POST /v1/alerts/{uuid}/trigger-agents
# ---------------------------------------------------------------------------


@router.post(
    "/{alert_uuid}/trigger-agents",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_agents(
    alert_uuid: UUID,
    auth: Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))],
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[TaskQueueBase, Depends(get_queue)],
) -> DataResponse[dict]:  # type: ignore[type-arg]
    """
    Manually re-dispatch an alert to all matching registered agents.

    Evaluates trigger criteria against the alert (same logic as post-enrichment
    dispatch) and enqueues a dispatch_agent_webhooks task. Returns 202 with the
    count and names of agents that will receive the webhook.
    """
    alert_repo = AlertRepository(db)
    alert = await alert_repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    matching_agents = await get_matching_agents(alert, db)

    await queue.enqueue(
        "dispatch_agent_webhooks",
        {"alert_id": alert.id},
        queue="dispatch",
        delay_seconds=0,
        priority=0,
    )

    return DataResponse(
        data={
            "queued_agent_count": len(matching_agents),
            "agent_names": [a.name for a in matching_agents],
        }
    )
