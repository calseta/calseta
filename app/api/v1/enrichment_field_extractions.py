"""
CRUD API for enrichment field extraction configuration.

Routes:
  GET    /v1/enrichment-field-extractions              — List extractions (filterable)
  POST   /v1/enrichment-field-extractions              — Create single extraction
  POST   /v1/enrichment-field-extractions/bulk          — Bulk create extractions
  GET    /v1/enrichment-field-extractions/{uuid}        — Get extraction by UUID
  PATCH  /v1/enrichment-field-extractions/{uuid}        — Update extraction
  DELETE /v1/enrichment-field-extractions/{uuid}        — Delete extraction
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.integrations.enrichment.registry import enrichment_registry
from app.middleware.rate_limit import limiter
from app.repositories.enrichment_field_extraction_repository import (
    EnrichmentFieldExtractionRepository,
)
from app.repositories.enrichment_provider_repository import (
    EnrichmentProviderRepository,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.enrichment_field_extractions import (
    EnrichmentFieldExtractionBulkCreate,
    EnrichmentFieldExtractionCreate,
    EnrichmentFieldExtractionPatch,
    EnrichmentFieldExtractionResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/enrichment-field-extractions", tags=["enrichment-field-extractions"]
)

_Read = Annotated[AuthContext, Depends(require_scope(Scope.ENRICHMENTS_READ))]
_Admin = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]


def _to_response(
    extraction: object,
) -> EnrichmentFieldExtractionResponse:
    return EnrichmentFieldExtractionResponse.model_validate(extraction)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[EnrichmentFieldExtractionResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_enrichment_field_extractions(
    request: Request,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    provider_name: str | None = Query(None),
    indicator_type: str | None = Query(None),
    is_system: bool | None = Query(None),
    is_active: bool | None = Query(None),
) -> PaginatedResponse[EnrichmentFieldExtractionResponse]:
    repo = EnrichmentFieldExtractionRepository(db)
    extractions, total = await repo.list_extractions(
        provider_name=provider_name,
        indicator_type=indicator_type,
        is_system=is_system,
        is_active=is_active,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[_to_response(e) for e in extractions],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def _validate_provider_exists(
    db: AsyncSession, provider_name: str
) -> None:
    """Verify the provider_name references an existing enrichment provider."""
    provider_repo = EnrichmentProviderRepository(db)
    provider = await provider_repo.get_by_name(provider_name)
    if provider is None:
        raise CalsetaException(
            code="PROVIDER_NOT_FOUND",
            message=f"Enrichment provider '{provider_name}' does not exist.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


@router.post(
    "",
    response_model=DataResponse[EnrichmentFieldExtractionResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_enrichment_field_extraction(
    request: Request,
    body: EnrichmentFieldExtractionCreate,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[EnrichmentFieldExtractionResponse]:
    await _validate_provider_exists(db, body.provider_name)

    repo = EnrichmentFieldExtractionRepository(db)
    try:
        extraction = await repo.create(
            provider_name=body.provider_name,
            indicator_type=body.indicator_type,
            source_path=body.source_path,
            target_key=body.target_key,
            value_type=body.value_type,
            description=body.description,
        )
    except IntegrityError as exc:
        await db.rollback()
        raise CalsetaException(
            code="DUPLICATE_EXTRACTION",
            message=(
                f"Extraction for provider '{body.provider_name}', "
                f"indicator type '{body.indicator_type}', "
                f"source path '{body.source_path}' already exists."
            ),
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    # Reload registry to pick up new field extraction
    await enrichment_registry.load_from_database(db)

    return DataResponse(data=_to_response(extraction))


# ---------------------------------------------------------------------------
# Bulk create
# ---------------------------------------------------------------------------


@router.post(
    "/bulk",
    response_model=DataResponse[list[EnrichmentFieldExtractionResponse]],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def bulk_create_enrichment_field_extractions(
    request: Request,
    body: EnrichmentFieldExtractionBulkCreate,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[list[EnrichmentFieldExtractionResponse]]:
    # Validate all provider names upfront
    unique_providers = {e.provider_name for e in body.extractions}
    for pn in unique_providers:
        await _validate_provider_exists(db, pn)

    repo = EnrichmentFieldExtractionRepository(db)
    created: list[object] = []
    try:
        for item in body.extractions:
            extraction = await repo.create(
                provider_name=item.provider_name,
                indicator_type=item.indicator_type,
                source_path=item.source_path,
                target_key=item.target_key,
                value_type=item.value_type,
                description=item.description,
            )
            created.append(extraction)
    except IntegrityError as exc:
        await db.rollback()
        raise CalsetaException(
            code="DUPLICATE_EXTRACTION",
            message=(
                "Bulk create failed due to a duplicate extraction. "
                "Ensure all (provider_name, indicator_type, source_path) "
                "combinations are unique."
            ),
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    # Reload registry
    await enrichment_registry.load_from_database(db)

    return DataResponse(data=[_to_response(e) for e in created])


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


@router.get(
    "/{extraction_uuid}",
    response_model=DataResponse[EnrichmentFieldExtractionResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_enrichment_field_extraction(
    request: Request,
    extraction_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[EnrichmentFieldExtractionResponse]:
    repo = EnrichmentFieldExtractionRepository(db)
    extraction = await repo.get_by_uuid(extraction_uuid)
    if extraction is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Enrichment field extraction not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=_to_response(extraction))


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------


@router.patch(
    "/{extraction_uuid}",
    response_model=DataResponse[EnrichmentFieldExtractionResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_enrichment_field_extraction(
    request: Request,
    extraction_uuid: UUID,
    body: EnrichmentFieldExtractionPatch,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[EnrichmentFieldExtractionResponse]:
    repo = EnrichmentFieldExtractionRepository(db)
    extraction = await repo.get_by_uuid(extraction_uuid)
    if extraction is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Enrichment field extraction not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    updates = body.model_dump(exclude_none=True)

    # System extractions: only is_active can be toggled
    if extraction.is_system:
        allowed_system_fields = {"is_active"}
        disallowed = set(updates.keys()) - allowed_system_fields
        if disallowed:
            raise CalsetaException(
                code="SYSTEM_EXTRACTION_RESTRICTED",
                message=(
                    "System extractions can only have is_active toggled. "
                    f"Cannot modify: {sorted(disallowed)}"
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

    updated = await repo.patch(extraction, updates)

    # Reload registry
    await enrichment_registry.load_from_database(db)

    return DataResponse(data=_to_response(updated))


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/{extraction_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_enrichment_field_extraction(
    request: Request,
    extraction_uuid: UUID,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = EnrichmentFieldExtractionRepository(db)
    extraction = await repo.get_by_uuid(extraction_uuid)
    if extraction is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Enrichment field extraction not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if extraction.is_system:
        raise CalsetaException(
            code="SYSTEM_EXTRACTION_RESTRICTED",
            message=(
                "System extractions cannot be deleted. "
                "Set is_active=false to disable."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    await repo.delete(extraction)

    # Reload registry
    await enrichment_registry.load_from_database(db)
