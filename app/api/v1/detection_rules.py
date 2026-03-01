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


@router.get("", response_model=PaginatedResponse[DetectionRuleResponse])
async def list_detection_rules(
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    source_name: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> PaginatedResponse[DetectionRuleResponse]:
    repo = DetectionRuleRepository(db)
    rules, total = await repo.list(
        source_name=source_name,
        is_active=is_active,
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
