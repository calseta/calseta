"""
Alert ingest routes.

POST /v1/ingest/{source_name}
    Webhook endpoint. Verifies signature, validates payload, enqueues enrichment.
    Returns 202 Accepted.

POST /v1/alerts
    Generic programmatic ingest. Accepts {"source_name": "...", "payload": {...}}.
    No webhook signature verification (trusted caller, key-auth only).
    Returns 202 Accepted.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.db.session import get_db
from app.integrations.sources.registry import source_registry
from app.queue.base import TaskQueueBase
from app.queue.dependencies import get_queue
from app.schemas.common import DataResponse
from app.services.alert_ingestion import AlertIngestionService

router = APIRouter(tags=["ingest"])

_AlertsWrite = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_WRITE))]


class IngestResponse(BaseModel):
    alert_uuid: uuid.UUID
    status: str = "queued"
    is_duplicate: bool = False
    duplicate_count: int | None = None


class GenericIngestBody(BaseModel):
    source_name: str
    payload: dict[str, Any]


@router.post(
    "/ingest/{source_name}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DataResponse[IngestResponse],
)
async def webhook_ingest(
    source_name: str,
    request: Request,
    auth: _AlertsWrite,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[TaskQueueBase, Depends(get_queue)],
) -> DataResponse[IngestResponse]:
    """
    Receive a webhook from a configured alert source.

    Verifies the webhook signature, validates the payload structure,
    and enqueues the enrichment pipeline. Returns 202 immediately.

    Allowed sources check: if the API key has `allowed_sources` set,
    the requested source_name must be in that list.
    """
    source = source_registry.get(source_name)
    if source is None:
        raise CalsetaException(
            code="UNKNOWN_SOURCE",
            message=f"Alert source '{source_name}' is not registered.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Allowed sources enforcement
    if auth.allowed_sources is not None and source_name not in auth.allowed_sources:
        raise CalsetaException(
            code="SOURCE_NOT_ALLOWED",
            message=(
                f"API key is not authorized to ingest from source '{source_name}'."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    raw_body = await request.body()
    headers = dict(request.headers)

    # Verify webhook signature
    if not source.verify_webhook_signature(headers, raw_body):
        raise CalsetaException(
            code="INVALID_SIGNATURE",
            message="Webhook signature verification failed.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        raw_payload = await request.json()
    except Exception:
        raise CalsetaException(
            code="INVALID_JSON",
            message="Request body is not valid JSON.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from None
    if not isinstance(raw_payload, dict):
        raise CalsetaException(
            code="INVALID_PAYLOAD",
            message="Request body must be a JSON object.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    if not source.validate_payload(raw_payload):
        raise CalsetaException(
            code="INVALID_PAYLOAD",
            message=f"Payload does not match expected structure for source '{source_name}'.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    svc = AlertIngestionService(db, queue)
    result = await svc.ingest(
        source,
        raw_payload,
        actor_type="api",
        actor_key_prefix=auth.key_prefix,
    )

    return DataResponse(
        data=IngestResponse(
            alert_uuid=result.alert.uuid,
            status="deduplicated" if result.is_duplicate else "queued",
            is_duplicate=result.is_duplicate,
            duplicate_count=result.alert.duplicate_count if result.is_duplicate else None,
        ),
    )


@router.post(
    "/alerts",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DataResponse[IngestResponse],
)
async def generic_ingest(
    body: GenericIngestBody,
    auth: _AlertsWrite,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[TaskQueueBase, Depends(get_queue)],
) -> DataResponse[IngestResponse]:
    """
    Programmatic alert ingest — skips webhook signature verification.

    Accepts {"source_name": "sentinel", "payload": {...}}.
    The payload must pass the source plugin's validate_payload() check.
    """
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
            message=(
                f"API key is not authorized to ingest from source '{body.source_name}'."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    if not source.validate_payload(body.payload):
        raise CalsetaException(
            code="INVALID_PAYLOAD",
            message=(
                f"Payload does not match expected structure "
                f"for source '{body.source_name}'."
            ),
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
        data=IngestResponse(
            alert_uuid=result.alert.uuid,
            status="deduplicated" if result.is_duplicate else "queued",
            is_duplicate=result.is_duplicate,
            duplicate_count=result.alert.duplicate_count if result.is_duplicate else None,
        ),
    )
