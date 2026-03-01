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
from app.repositories.indicator_mapping_repository import IndicatorMappingRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.indicator_mappings import (
    IndicatorFieldMappingCreate,
    IndicatorFieldMappingPatch,
    IndicatorFieldMappingResponse,
)

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
