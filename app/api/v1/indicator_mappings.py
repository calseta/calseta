"""
Indicator field mapping management routes.

GET    /v1/indicator-mappings              — List mappings (filterable)
POST   /v1/indicator-mappings             — Create a custom mapping
GET    /v1/indicator-mappings/{uuid}      — Get mapping by UUID
PATCH  /v1/indicator-mappings/{uuid}      — Update a mapping
DELETE /v1/indicator-mappings/{uuid}      — Delete a mapping
"""

from __future__ import annotations

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
from app.integrations.sources.registry import source_registry
from app.repositories.indicator_mapping_repository import IndicatorMappingRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.indicator_mappings import (
    IndicatorFieldMappingCreate,
    IndicatorFieldMappingPatch,
    IndicatorFieldMappingResponse,
    TestExtractionRequest,
    TestExtractionResponse,
)
from app.services.indicator_extraction import test_extraction

router = APIRouter(prefix="/indicator-mappings", tags=["indicator-mappings"])

_AdminOrWrite = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]


def _to_response(mapping: object) -> IndicatorFieldMappingResponse:
    return IndicatorFieldMappingResponse.model_validate(mapping)


@router.get("", response_model=PaginatedResponse[IndicatorFieldMappingResponse])
async def list_indicator_mappings(
    auth: _AdminOrWrite,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_name: str | None = Query(None),
    is_system: bool | None = Query(None),
    is_active: bool | None = Query(None),
    extraction_target: str | None = Query(None),
) -> PaginatedResponse[IndicatorFieldMappingResponse]:
    repo = IndicatorMappingRepository(db)
    mappings, total = await repo.list_mappings(
        source_name=source_name,
        is_system=is_system,
        is_active=is_active,
        extraction_target=extraction_target,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[_to_response(m) for m in mappings],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


@router.post(
    "",
    response_model=DataResponse[IndicatorFieldMappingResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_indicator_mapping(
    auth: _AdminOrWrite,
    body: IndicatorFieldMappingCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[IndicatorFieldMappingResponse]:
    repo = IndicatorMappingRepository(db)
    mapping = await repo.create(body)
    return DataResponse(data=_to_response(mapping))


@router.get(
    "/source-plugin-fields",
    response_model=DataResponse[list[IndicatorFieldMappingResponse]],
)
async def list_source_plugin_fields(
    auth: _AdminOrWrite,
) -> DataResponse[list[IndicatorFieldMappingResponse]]:
    """Return hardcoded Pass 1 extraction fields from all registered sources."""
    from datetime import UTC, datetime

    results: list[IndicatorFieldMappingResponse] = []
    epoch = datetime(2000, 1, 1, tzinfo=UTC)
    for src in source_registry.list_all():
        for ext in src.documented_extractions():
            results.append(
                IndicatorFieldMappingResponse(
                    uuid="00000000-0000-0000-0000-000000000000",
                    source_name=src.source_name,
                    field_path=ext.field_path,
                    indicator_type=ext.indicator_type,
                    extraction_target="source_plugin",
                    is_system=True,
                    is_active=True,
                    description=ext.description,
                    created_at=epoch,
                    updated_at=epoch,
                )
            )
    return DataResponse(data=results)


@router.post(
    "/test-extraction",
    response_model=DataResponse[TestExtractionResponse],
)
async def test_extraction_endpoint(
    body: TestExtractionRequest,
    auth: _AdminOrWrite,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[TestExtractionResponse]:
    source = source_registry.get(body.source_name)
    if source is None:
        raise CalsetaException(
            code="UNKNOWN_SOURCE",
            message=f"Unknown alert source: {body.source_name}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if not source.validate_payload(body.raw_payload):
        raise CalsetaException(
            code="INVALID_PAYLOAD",
            message=(
                "Payload failed source validation. "
                "Check the JSON structure matches the selected source format."
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    repo = IndicatorMappingRepository(db)
    norm_mappings = await repo.get_active_for_extraction(
        source_name=body.source_name, extraction_target="normalized"
    )
    raw_mappings = await repo.get_active_for_extraction(
        source_name=body.source_name, extraction_target="raw_payload"
    )
    result = test_extraction(source, body.raw_payload, norm_mappings, raw_mappings)
    return DataResponse(data=result)


@router.get("/{mapping_uuid}", response_model=DataResponse[IndicatorFieldMappingResponse])
async def get_indicator_mapping(
    mapping_uuid: UUID,
    auth: _AdminOrWrite,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[IndicatorFieldMappingResponse]:
    repo = IndicatorMappingRepository(db)
    mapping = await repo.get_by_uuid(mapping_uuid)
    if mapping is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Indicator field mapping not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=_to_response(mapping))


@router.patch("/{mapping_uuid}", response_model=DataResponse[IndicatorFieldMappingResponse])
async def patch_indicator_mapping(
    mapping_uuid: UUID,
    body: IndicatorFieldMappingPatch,
    auth: _AdminOrWrite,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[IndicatorFieldMappingResponse]:
    repo = IndicatorMappingRepository(db)
    mapping = await repo.get_by_uuid(mapping_uuid)
    if mapping is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Indicator field mapping not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if mapping.is_system and body.field_path is not None:
        raise CalsetaException(
            code="SYSTEM_MAPPING_READONLY",
            message="System mappings are read-only. Only is_active can be toggled.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    updated = await repo.patch(mapping, body)
    return DataResponse(data=_to_response(updated))


@router.delete("/{mapping_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_indicator_mapping(
    mapping_uuid: UUID,
    auth: _AdminOrWrite,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = IndicatorMappingRepository(db)
    mapping = await repo.get_by_uuid(mapping_uuid)
    if mapping is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Indicator field mapping not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if mapping.is_system:
        raise CalsetaException(
            code="SYSTEM_MAPPING_READONLY",
            message="System mappings cannot be deleted. Set is_active=false to disable.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    await repo.delete(mapping)
