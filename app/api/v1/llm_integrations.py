"""
LLM integration management routes.

POST   /v1/llm-integrations               Register LLM provider+model combo
GET    /v1/llm-integrations               List all (paginated)
GET    /v1/llm-integrations/providers     List available providers
GET    /v1/llm-integrations/{uuid}        Get integration details
PATCH  /v1/llm-integrations/{uuid}        Update config
DELETE /v1/llm-integrations/{uuid}        Remove integration (204)
GET    /v1/llm-integrations/{uuid}/usage  Cost/token usage aggregate
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
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
from app.repositories.llm_integration_repository import LLMIntegrationRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.llm_integrations import (
    LLMIntegrationCreate,
    LLMIntegrationPatch,
    LLMIntegrationResponse,
    LLMUsageResponse,
)
from app.services.llm_integration_service import LLMIntegrationService

router = APIRouter(prefix="/llm-integrations", tags=["llm-integrations"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


# ---------------------------------------------------------------------------
# GET /v1/llm-integrations
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[LLMIntegrationResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_llm_integrations(
    request: Request,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[LLMIntegrationResponse]:
    repo = LLMIntegrationRepository(db)
    integrations, total = await repo.list_all(page=pagination.page, page_size=pagination.page_size)
    return PaginatedResponse(
        data=[LLMIntegrationResponse.from_orm(i) for i in integrations],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# POST /v1/llm-integrations
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DataResponse[LLMIntegrationResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_llm_integration(
    request: Request,
    body: LLMIntegrationCreate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[LLMIntegrationResponse]:
    svc = LLMIntegrationService(db)
    integration = await svc.create(body)
    return DataResponse(data=LLMIntegrationResponse.from_orm(integration))


# ---------------------------------------------------------------------------
# GET /v1/llm-integrations/providers
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=DataResponse[list[dict]])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_llm_providers(
    request: Request,
    auth: _Read,
) -> DataResponse[list[dict]]:
    """List all available LLM providers (built-in + external)."""
    from app.integrations.llm.adapter_registry import (
        list_external_providers,
    )
    from app.schemas.llm_integrations import LLMProvider

    builtin = [
        {
            "provider_name": p.value,
            "display_name": p.value,
            "is_external": False,
        }
        for p in LLMProvider
    ]
    external = list_external_providers()
    return DataResponse(data=builtin + external)


# ---------------------------------------------------------------------------
# GET /v1/llm-integrations/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{integration_uuid}", response_model=DataResponse[LLMIntegrationResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_llm_integration(
    request: Request,
    integration_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[LLMIntegrationResponse]:
    repo = LLMIntegrationRepository(db)
    integration = await repo.get_by_uuid(integration_uuid)
    if integration is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="LLM integration not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=LLMIntegrationResponse.from_orm(integration))


# ---------------------------------------------------------------------------
# PATCH /v1/llm-integrations/{uuid}
# ---------------------------------------------------------------------------


@router.patch("/{integration_uuid}", response_model=DataResponse[LLMIntegrationResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_llm_integration(
    request: Request,
    integration_uuid: UUID,
    body: LLMIntegrationPatch,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[LLMIntegrationResponse]:
    repo = LLMIntegrationRepository(db)
    integration = await repo.get_by_uuid(integration_uuid)
    if integration is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="LLM integration not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    svc = LLMIntegrationService(db)
    updated = await svc.update(integration, body)
    return DataResponse(data=LLMIntegrationResponse.from_orm(updated))


# ---------------------------------------------------------------------------
# DELETE /v1/llm-integrations/{uuid}
# ---------------------------------------------------------------------------


@router.delete("/{integration_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_llm_integration(
    request: Request,
    integration_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = LLMIntegrationRepository(db)
    integration = await repo.get_by_uuid(integration_uuid)
    if integration is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="LLM integration not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    svc = LLMIntegrationService(db)
    await svc.delete(integration)


# ---------------------------------------------------------------------------
# GET /v1/llm-integrations/{uuid}/usage
# ---------------------------------------------------------------------------


@router.get("/{integration_uuid}/usage", response_model=DataResponse[LLMUsageResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_llm_integration_usage(
    request: Request,
    integration_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
    from_dt: datetime = Query(
        default=None,
        description="Start of range (ISO 8601). Defaults to 30 days ago.",
    ),
    to_dt: datetime = Query(
        default=None,
        description="End of range (ISO 8601). Defaults to now.",
    ),
) -> DataResponse[LLMUsageResponse]:
    repo = LLMIntegrationRepository(db)
    integration = await repo.get_by_uuid(integration_uuid)
    if integration is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="LLM integration not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    now = datetime.now(UTC)
    if to_dt is None:
        to_dt = now
    if from_dt is None:
        from datetime import timedelta
        from_dt = now - timedelta(days=30)

    svc = LLMIntegrationService(db)
    usage = await svc.get_usage(integration.id, from_dt, to_dt)

    return DataResponse(
        data=LLMUsageResponse(
            llm_integration_uuid=integration.uuid,
            from_dt=from_dt,
            to_dt=to_dt,
            total_input_tokens=usage["total_input_tokens"],
            total_output_tokens=usage["total_output_tokens"],
            total_cost_cents=usage["total_cost_cents"],
            event_count=usage["event_count"],
            billing_types=usage["billing_types"],
        )
    )


# ---------------------------------------------------------------------------
# POST /v1/llm-integrations/{uuid}/test  — Test connectivity
# ---------------------------------------------------------------------------


@router.post("/{uuid}/test")
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def test_llm_integration(
    request: Request,
    uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[dict]:
    repo = LLMIntegrationRepository(db)
    integration = await repo.get_by_uuid(uuid)
    if integration is None:
        raise CalsetaException(
            status_code=404, code="NOT_FOUND", message="LLM integration not found",
        )

    start = time.time()
    try:
        from app.integrations.llm.factory import get_adapter

        adapter = get_adapter(integration)
        result = await adapter.test_environment()
        latency_ms = int((time.time() - start) * 1000)
        return DataResponse(data={
            "success": result.ok, "latency_ms": latency_ms, "message": result.message,
        })
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.time() - start) * 1000)
        return DataResponse(data={"success": False, "latency_ms": latency_ms, "message": str(exc)})
