"""
Detection rule management routes.

GET    /v1/detection-rules              — List rules (filterable by source, is_active)
POST   /v1/detection-rules             — Create a rule
GET    /v1/detection-rules/{uuid}      — Get rule by UUID
PATCH  /v1/detection-rules/{uuid}      — Update a rule
DELETE /v1/detection-rules/{uuid}      — Delete a rule
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
from app.repositories.detection_rule_repository import DetectionRuleRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.detection_rules import (
    DetectionRuleCreate,
    DetectionRulePatch,
    DetectionRuleResponse,
)

router = APIRouter(prefix="/detection-rules", tags=["detection-rules"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]


def _to_response(rule: object) -> DetectionRuleResponse:
    return DetectionRuleResponse.model_validate(rule)


_DR_SORT_FIELDS = {"name", "source_name", "severity", "created_at"}


@router.get("", response_model=PaginatedResponse[DetectionRuleResponse])
async def list_detection_rules(
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_name: str | None = Query(None),
    severity: str | None = Query(None),
    is_active: bool | None = Query(None),
    sort_by: str | None = Query(None),
    sort_order: str | None = Query(None),
) -> PaginatedResponse[DetectionRuleResponse]:
    if sort_by and sort_by not in _DR_SORT_FIELDS:
        raise CalsetaException(
            code="VALIDATION_ERROR",
            message=f"sort_by must be one of: {sorted(_DR_SORT_FIELDS)}",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    if sort_order and sort_order not in ("asc", "desc"):
        raise CalsetaException(
            code="VALIDATION_ERROR",
            message="sort_order must be 'asc' or 'desc'",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Parse comma-separated multi-value filters
    source_list = [s.strip() for s in source_name.split(",") if s.strip()] if source_name else None
    severity_list = [s.strip() for s in severity.split(",") if s.strip()] if severity else None

    repo = DetectionRuleRepository(db)
    rules, total = await repo.list(
        source_name=source_list,
        severity=severity_list,
        is_active=is_active,
        sort_by=sort_by,
        sort_order=sort_order,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[_to_response(r) for r in rules],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


@router.post(
    "",
    response_model=DataResponse[DetectionRuleResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_detection_rule(
    body: DetectionRuleCreate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[DetectionRuleResponse]:
    # Auto-populate created_by from the API key prefix if not set
    if not body.created_by:
        body.created_by = auth.key_prefix
    repo = DetectionRuleRepository(db)
    rule = await repo.create(body)
    return DataResponse(data=_to_response(rule))


@router.get("/{rule_uuid}", response_model=DataResponse[DetectionRuleResponse])
async def get_detection_rule(
    rule_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[DetectionRuleResponse]:
    repo = DetectionRuleRepository(db)
    rule = await repo.get_by_uuid(rule_uuid)
    if rule is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Detection rule not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=_to_response(rule))


@router.patch("/{rule_uuid}", response_model=DataResponse[DetectionRuleResponse])
async def patch_detection_rule(
    rule_uuid: UUID,
    body: DetectionRulePatch,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[DetectionRuleResponse]:
    repo = DetectionRuleRepository(db)
    rule = await repo.get_by_uuid(rule_uuid)
    if rule is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Detection rule not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    updated = await repo.patch(rule, body)
    return DataResponse(data=_to_response(updated))


@router.delete("/{rule_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_detection_rule(
    rule_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = DetectionRuleRepository(db)
    rule = await repo.get_by_uuid(rule_uuid)
    if rule is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Detection rule not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await repo.delete(rule)
