"""
Alert management routes.

POST   /v1/alerts                            — Programmatic alert ingest (no sig verification)
GET    /v1/alerts                            — List alerts with filters
GET    /v1/alerts/{uuid}                     — Get alert detail (includes indicators + _metadata)
PATCH  /v1/alerts/{uuid}                     — Update alert (status, severity, tags, classification)
DELETE /v1/alerts/{uuid}                     — Delete alert
POST   /v1/alerts/{uuid}/findings           — Add an agent finding to an alert
GET    /v1/alerts/{uuid}/indicators         — List indicators for an alert
POST   /v1/alerts/{uuid}/indicators         — Add indicators to an alert
GET    /v1/alerts/{uuid}/activity           — List activity events for an alert
GET    /v1/alerts/{uuid}/relationship-graph — Alert-indicator-sibling relationship graph

Note on ingest paths:
  POST /v1/ingest/{source_name}  — Webhook ingest with signature verification (external systems)
  POST /v1/alerts                — Programmatic ingest, skips signature check (trusted API callers)
"""

from __future__ import annotations

import uuid as _uuid
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.queue.base import TaskQueueBase
from app.queue.dependencies import get_queue
from app.queue.handlers.dispatch_webhooks import get_matching_agents
from app.repositories.activity_event_repository import ActivityEventRepository
from app.repositories.agent_repository import AgentRepository
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
from app.schemas.detection_rules import DetectionRuleResponse
from app.schemas.indicators import (
    EnrichedIndicator,
    IndicatorAddRequest,
    IndicatorAddResponse,
    IndicatorResponse,
)
from app.schemas.relationship_graph import (
    AlertRelationshipGraph,
    GraphAlertNode,
    GraphIndicatorNode,
)
from app.services.activity_event import ActivityEventService
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
        malice_source=ind.malice_source,
        malice_overridden_at=ind.malice_overridden_at,
        enrichment_results=_filter_enrichment_results(ind.enrichment_results),
        created_at=ind.created_at,
        updated_at=ind.updated_at,
    )


def _compute_dominant_malice(indicators: list[EnrichedIndicator]) -> str:
    """Compute worst-case malice across indicators."""
    malice_order = ["Malicious", "Suspicious", "Benign", "Pending"]
    worst = "Pending"
    for ind in indicators:
        wi = malice_order.index(worst) if worst in malice_order else len(malice_order)
        ci = malice_order.index(ind.malice) if ind.malice in malice_order else len(malice_order)
        if ci < wi:
            worst = ind.malice
    return worst


def _build_metadata(
    alert: object,
    indicators: list[EnrichedIndicator],
    context_docs_count: int = 0,
) -> AlertMetadata:
    from app.db.models.alert import Alert

    assert isinstance(alert, Alert)

    # Collect succeeded/failed provider names from indicator enrichment results
    succeeded: set[str] = set()
    failed: set[str] = set()
    for ind in indicators:
        if not ind.enrichment_results:
            continue
        for provider, data in ind.enrichment_results.items():
            if not isinstance(data, dict):
                continue
            if data.get("success") is True:
                succeeded.add(provider)
            elif data.get("success") is False:
                failed.add(provider)

    enrichment: dict[str, object] = {
        "succeeded": sorted(succeeded),
        "failed": sorted(failed),
        "enriched_at": alert.enriched_at.isoformat() if alert.enriched_at else None,
    }
    return AlertMetadata(
        generated_at=datetime.now(UTC),
        alert_source=alert.source_name,
        indicator_count=len(indicators),
        enrichment=enrichment,
        detection_rule_matched=alert.detection_rule_id is not None,
        context_documents_applied=context_docs_count,
    )


def _alert_response_from_orm(alert: object) -> AlertResponse:
    """Build AlertResponse without triggering SQLAlchemy relationship lazy-loads."""
    from app.db.models.alert import Alert

    assert isinstance(alert, Alert)
    # Use __dict__ to avoid hitting relationship descriptors
    attrs = {k: v for k, v in alert.__dict__.items() if not k.startswith("_")}
    attrs.pop("detection_rule", None)
    return AlertResponse.model_validate(attrs)


# ---------------------------------------------------------------------------
# POST /v1/alerts — programmatic ingest (no webhook signature check)
# ---------------------------------------------------------------------------


class _GenericIngestBody(BaseModel):
    source_name: str
    payload: dict[str, Any]

    @field_validator("payload")
    @classmethod
    def _validate_payload_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        from app.schemas.common import JSONB_SIZE_LARGE, validate_jsonb_size

        return validate_jsonb_size(v, JSONB_SIZE_LARGE, "payload")  # type: ignore[return-value]


class _IngestResponse(BaseModel):
    alert_uuid: _uuid.UUID
    status: str = "queued"
    is_duplicate: bool = False
    duplicate_count: int | None = None


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DataResponse[_IngestResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_INGEST_PER_MINUTE}/minute")
async def programmatic_ingest(
    request: Request,
    body: _GenericIngestBody,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[TaskQueueBase, Depends(get_queue)],
) -> DataResponse[_IngestResponse]:
    """
    Programmatic alert ingest — skips webhook signature verification.

    Accepts {"source_name": "sentinel", "payload": {...}}.
    The payload must pass the source plugin's validate_payload() check.

    Use this path for trusted API callers (internal pipelines, tests, scripts)
    that do not go through an external webhook. For external webhook ingest with
    signature verification, use POST /v1/ingest/{source_name} instead.
    """
    from app.integrations.sources.registry import source_registry
    from app.services.alert_ingestion import AlertIngestionService

    source = source_registry.get(body.source_name)
    if source is None:
        raise CalsetaException(
            code="UNKNOWN_SOURCE",
            message=f"Alert source '{body.source_name}' is not registered.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if auth.allowed_sources is not None and body.source_name not in auth.allowed_sources:
        raise CalsetaException(
            code="SOURCE_NOT_ALLOWED",
            message=f"API key is not authorized to ingest from source '{body.source_name}'.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if not source.validate_payload(body.payload):
        raise CalsetaException(
            code="INVALID_PAYLOAD",
            message=f"Payload does not match expected structure for source '{body.source_name}'.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    svc = AlertIngestionService(db, queue)
    result = await svc.ingest(
        source,
        body.payload,
        actor_type="api",
        actor_key_prefix=auth.key_prefix,
    )

    return DataResponse(
        data=_IngestResponse(
            alert_uuid=result.alert.uuid,
            status="deduplicated" if result.is_duplicate else "queued",
            is_duplicate=result.is_duplicate,
            duplicate_count=result.alert.duplicate_count if result.is_duplicate else None,
        ),
    )


_ALLOWED_SORT_BY = {"title", "status", "severity", "source_name", "occurred_at", "created_at"}
_ALLOWED_SORT_ORDER = {"asc", "desc"}


@router.get("", response_model=PaginatedResponse[AlertSummary])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_alerts(
    request: Request,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: str | None = Query(None),
    severity: str | None = Query(None),
    source_name: str | None = Query(None),
    is_enriched: bool | None = Query(None),
    enrichment_status: str | None = Query(None),
    detection_rule_uuid: UUID | None = Query(None),
    from_time: datetime | None = Query(None),
    to_time: datetime | None = Query(None),
    tags: list[str] | None = Query(None),
    sort_by: str | None = Query(None),
    sort_order: str | None = Query(None),
) -> PaginatedResponse[AlertSummary]:
    # Validate sort params
    if sort_by and sort_by not in _ALLOWED_SORT_BY:
        raise CalsetaException(
            code="VALIDATION_ERROR",
            message=f"Invalid sort_by '{sort_by}'. Must be one of: {sorted(_ALLOWED_SORT_BY)}",
            status_code=400,
        )
    if sort_order and sort_order not in _ALLOWED_SORT_ORDER:
        raise CalsetaException(
            code="VALIDATION_ERROR",
            message=f"Invalid sort_order '{sort_order}'. Must be 'asc' or 'desc'.",
            status_code=400,
        )

    # Parse comma-separated multi-value filters into lists
    status_list = [s.strip() for s in status.split(",") if s.strip()] if status else None
    severity_list = [s.strip() for s in severity.split(",") if s.strip()] if severity else None
    source_list = [s.strip() for s in source_name.split(",") if s.strip()] if source_name else None
    enrichment_status_list = (
        [s.strip() for s in enrichment_status.split(",") if s.strip()]
        if enrichment_status
        else None
    )

    repo = AlertRepository(db)
    alerts, total = await repo.list_alerts(
        status=status_list,
        severity=severity_list,
        source_name=source_list,
        is_enriched=is_enriched,
        enrichment_status=enrichment_status_list,
        detection_rule_uuid=detection_rule_uuid,
        from_time=from_time,
        to_time=to_time,
        tags=tags,
        sort_by=sort_by,
        sort_order=sort_order,
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
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_alert(
    request: Request,
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

    # Load applicable context documents
    context_docs = await get_applicable_documents(alert, db)

    # Load detection rule if linked
    detection_rule_resp = None
    if alert.detection_rule_id is not None:
        from app.db.models.detection_rule import DetectionRule

        dr_result = await db.execute(
            select(DetectionRule).where(DetectionRule.id == alert.detection_rule_id)
        )
        dr = dr_result.scalar_one_or_none()
        if dr is not None:
            detection_rule_resp = DetectionRuleResponse.model_validate(dr)

    metadata = _build_metadata(alert, enriched_indicators, len(context_docs))

    response = _alert_response_from_orm(alert)
    response.indicators = enriched_indicators
    response.detection_rule = detection_rule_resp
    response.context_documents = [
        ContextDocumentResponse.model_validate(d) for d in context_docs
    ]
    # Compute effective malice: override > worst-of-indicators > "Pending"
    response.malice = (
        alert.malice_override
        if alert.malice_override
        else _compute_dominant_malice(enriched_indicators)
    )

    return DataResponse(data=response, meta=metadata.model_dump())


@router.patch("/{alert_uuid}", response_model=DataResponse[AlertResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_alert(
    request: Request,
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
    prev_malice_override = alert.malice_override

    updated = await alert_repo.patch(
        alert,
        status=body.status,
        severity=body.severity,
        tags=body.tags,
        close_classification=body.close_classification.value
        if body.close_classification
        else None,
        malice_override=body.malice_override.value if body.malice_override else None,
        reset_malice_override=body.reset_malice_override,
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

    # Malice override activity event
    new_malice_override = updated.malice_override
    if body.reset_malice_override and prev_malice_override is not None:
        await activity_svc.write(
            ActivityEventType.ALERT_MALICE_UPDATED,
            actor_type="api",
            actor_key_prefix=auth.key_prefix,
            alert_id=alert.id,
            references={
                "from_malice": prev_malice_override,
                "to_malice": None,
                "malice_source": "reset",
            },
        )
    elif body.malice_override is not None and body.malice_override.value != prev_malice_override:
        await activity_svc.write(
            ActivityEventType.ALERT_MALICE_UPDATED,
            actor_type="api",
            actor_key_prefix=auth.key_prefix,
            alert_id=alert.id,
            references={
                "from_malice": prev_malice_override,
                "to_malice": new_malice_override,
                "malice_source": "analyst",
            },
        )

    indicators = await indicator_repo.list_for_alert(updated.id)
    enriched_indicators = [_build_indicator(i) for i in indicators]
    metadata = _build_metadata(updated, enriched_indicators)

    response = _alert_response_from_orm(updated)
    response.indicators = enriched_indicators
    response.malice = (
        updated.malice_override
        if updated.malice_override
        else _compute_dominant_malice(enriched_indicators)
    )

    return DataResponse(data=response, meta=metadata.model_dump())


@router.delete("/{alert_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_alert(
    request: Request,
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
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def add_finding(
    request: Request,
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
        references={
            "finding_id": finding_id,
            "agent_name": body.agent_name,
            "summary": (body.summary[:120] + "...") if len(body.summary) > 120 else body.summary,
            "confidence": body.confidence.value if body.confidence else None,
        },
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


@router.post(
    "/{alert_uuid}/enrich",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(f"{settings.RATE_LIMIT_ENRICHMENT_PER_MINUTE}/minute")
async def enrich_alert(
    request: Request,
    alert_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[TaskQueueBase, Depends(get_queue)],
) -> DataResponse[dict]:  # type: ignore[type-arg]
    """
    Re-trigger the enrichment pipeline for an alert.

    Queues the enrich_alert task which re-runs the full 3-pass indicator
    extraction + enrichment pipeline. Safe to call multiple times (idempotent).
    """
    alert_repo = AlertRepository(db)
    alert = await alert_repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    await queue.enqueue(
        "enrich_alert",
        {"alert_id": alert.id},
        queue="enrichment",
        delay_seconds=0,
        priority=0,
    )

    return DataResponse(data={"message": "Enrichment queued"})


@router.get(
    "/{alert_uuid}/findings",
    response_model=DataResponse[list[FindingResponse]],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_findings(
    request: Request,
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
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_alert_context(
    request: Request,
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
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_alert_indicators(
    request: Request,
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
            malice_source=ind.malice_source,
            malice_overridden_at=ind.malice_overridden_at,
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
# POST /v1/alerts/{uuid}/indicators
# ---------------------------------------------------------------------------


@router.post(
    "/{alert_uuid}/indicators",
    response_model=DataResponse[IndicatorAddResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def add_indicators(
    request: Request,
    alert_uuid: UUID,
    body: IndicatorAddRequest,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[TaskQueueBase, Depends(get_queue)],
    enrich: bool = Query(default=True),
) -> DataResponse[IndicatorAddResponse]:
    """
    Add one or more indicators to an alert.

    Each indicator is upserted globally (idempotent on type+value) and linked
    to the alert. If ``enrich=true`` (default), an enrichment task is queued.
    """
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

    now = datetime.now(UTC)
    added_indicators = []
    for item in body.indicators:
        indicator = await indicator_repo.upsert(item.type.value, item.value.strip(), now)
        await indicator_repo.link_to_alert(indicator.id, alert.id)
        added_indicators.append(indicator)

    enrich_requested = False
    if enrich:
        await queue.enqueue(
            "enrich_alert",
            {"alert_id": alert.id},
            queue="enrichment",
            delay_seconds=0,
            priority=0,
        )
        enrich_requested = True

    await activity_svc.write(
        ActivityEventType.ALERT_INDICATORS_ADDED,
        actor_type="api",
        actor_key_prefix=auth.key_prefix,
        alert_id=alert.id,
        references={
            "indicator_count": len(added_indicators),
            "indicators": [
                {"type": ind.type, "value": ind.value} for ind in added_indicators
            ],
            "enrich_requested": enrich_requested,
        },
    )

    result_indicators = [
        IndicatorResponse(
            uuid=str(ind.uuid),
            type=ind.type,  # type: ignore[arg-type]
            value=ind.value,
            malice=ind.malice,
            malice_source=ind.malice_source,
            malice_overridden_at=ind.malice_overridden_at,
            first_seen=ind.first_seen,
            last_seen=ind.last_seen,
            is_enriched=ind.is_enriched,
            enrichment_results=_filter_enrichment_results(ind.enrichment_results),
            created_at=ind.created_at,
            updated_at=ind.updated_at,
        )
        for ind in added_indicators
    ]

    return DataResponse(
        data=IndicatorAddResponse(
            added_count=len(result_indicators),
            indicators=result_indicators,
            enrich_requested=enrich_requested,
        )
    )


# ---------------------------------------------------------------------------
# GET /v1/alerts/{uuid}/activity
# ---------------------------------------------------------------------------


@router.get(
    "/{alert_uuid}/activity",
    response_model=PaginatedResponse[ActivityEventResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_alert_activity(
    request: Request,
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
# GET /v1/alerts/{uuid}/relationship-graph
# ---------------------------------------------------------------------------


def _build_enrichment_summary(enrichment_results: dict | None) -> dict[str, str]:  # type: ignore[type-arg]
    """Extract a one-line verdict summary per provider from enrichment_results."""
    if not enrichment_results:
        return {}
    summary: dict[str, str] = {}
    for provider, data in enrichment_results.items():
        if not isinstance(data, dict):
            continue
        extracted = data.get("extracted", {})
        if isinstance(extracted, dict):
            verdict = (
                extracted.get("verdict")
                or extracted.get("malice")
                or extracted.get("risk_score")
            )
            if verdict is not None:
                summary[provider] = str(verdict)
                continue
        if data.get("success") is True:
            summary[provider] = "enriched"
        elif data.get("success") is False:
            summary[provider] = "failed"
    return summary


@router.get(
    "/{alert_uuid}/relationship-graph",
    response_model=DataResponse[AlertRelationshipGraph],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_relationship_graph(
    request: Request,
    alert_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
    sibling_limit: int = Query(default=10, ge=1, le=50),
) -> DataResponse[AlertRelationshipGraph]:
    """
    Return the alert-indicator relationship graph.

    Includes the current alert, its indicators, and for each indicator
    the other alerts it appears in (capped by sibling_limit).
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
    indicator_ids = [ind.id for ind in indicators]

    related = await indicator_repo.get_related_alerts_for_indicators(
        indicator_ids, exclude_alert_id=alert.id, limit_per_indicator=sibling_limit
    )

    alert_node = GraphAlertNode(
        uuid=str(alert.uuid),
        title=alert.title,
        severity=alert.severity,
        status=alert.status,
        source_name=alert.source_name,
        occurred_at=alert.occurred_at,
        tags=alert.tags or [],
    )

    indicator_nodes = []
    for ind in indicators:
        sibling_alerts, total_count = related.get(ind.id, ([], 0))
        sibling_nodes = [
            GraphAlertNode(
                uuid=str(a.uuid),
                title=a.title,
                severity=a.severity,
                status=a.status,
                source_name=a.source_name,
                occurred_at=a.occurred_at,
                tags=a.tags or [],
            )
            for a in sibling_alerts
        ]
        indicator_nodes.append(
            GraphIndicatorNode(
                uuid=str(ind.uuid),
                type=ind.type,
                value=ind.value,
                malice=ind.malice,
                first_seen=ind.first_seen,
                last_seen=ind.last_seen,
                is_enriched=ind.is_enriched,
                enrichment_summary=_build_enrichment_summary(ind.enrichment_results),
                total_alert_count=total_count,
                sibling_alerts=sibling_nodes,
            )
        )

    graph = AlertRelationshipGraph(alert=alert_node, indicators=indicator_nodes)
    return DataResponse(data=graph)


# ---------------------------------------------------------------------------
# POST /v1/alerts/{uuid}/trigger-agents
# ---------------------------------------------------------------------------
# Distinct from /v1/alerts/{uuid}/dispatch-agent:
#   trigger-agents: broadcast — evaluate trigger rules and fan-out to ALL
#                   matching agents (same logic as post-enrichment auto-dispatch)
#   dispatch-agent: targeted — send to ONE specific agent (query param),
#                   bypasses trigger rules (used for manual re-runs / testing)
# ---------------------------------------------------------------------------


@router.post(
    "/{alert_uuid}/trigger-agents",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def trigger_agents(
    request: Request,
    alert_uuid: UUID,
    auth: Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))],
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[TaskQueueBase, Depends(get_queue)],
) -> DataResponse[dict]:  # type: ignore[type-arg]
    """
    Broadcast re-dispatch: evaluate trigger criteria and fan-out to all matching agents.

    Runs the same trigger-rule matching as the post-enrichment auto-dispatch.
    Enqueues dispatch_agent_webhooks and returns 202 with the count and names
    of agents that will receive the webhook.

    Use dispatch-agent instead when you want to target a single specific agent
    regardless of its trigger criteria.
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


# ---------------------------------------------------------------------------
# POST /v1/alerts/{uuid}/dispatch-agent
# ---------------------------------------------------------------------------


@router.post(
    "/{alert_uuid}/dispatch-agent",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def dispatch_agent(
    request: Request,
    alert_uuid: UUID,
    agent_uuid: Annotated[UUID, Query(description="UUID of the agent to dispatch to")],
    auth: Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))],
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[TaskQueueBase, Depends(get_queue)],
) -> DataResponse[dict]:  # type: ignore[type-arg]
    """
    Targeted dispatch: send this alert to one specific agent, bypassing trigger rules.

    Enqueues dispatch_single_agent_webhook for the named agent regardless of
    whether its trigger criteria match the alert. The agent must be active.
    Useful for manual investigation, regression testing, or forcing a specific
    agent to re-run against an alert.

    Use trigger-agents instead when you want broadcast dispatch to all agents
    whose trigger rules match the alert.
    """
    alert_repo = AlertRepository(db)
    alert = await alert_repo.get_by_uuid(alert_uuid)
    if alert is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Alert not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    agent_repo = AgentRepository(db)
    agent = await agent_repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if agent.status != "active":
        raise CalsetaException(
            code="AGENT_INACTIVE",
            message=f"Agent '{agent.name}' is not active (current status: {agent.status}).",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    await queue.enqueue(
        "dispatch_single_agent_webhook",
        {"alert_id": alert.id, "agent_id": agent.id},
        queue="dispatch",
        delay_seconds=0,
        priority=0,
    )

    return DataResponse(
        data={
            "agent_uuid": str(agent.uuid),
            "agent_name": agent.name,
            "alert_uuid": str(alert.uuid),
        }
    )
