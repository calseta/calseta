"""
Workflow management routes.

GET    /v1/workflows            — Paginated list (no code field)
POST   /v1/workflows            — Create workflow
GET    /v1/workflows/{uuid}     — Full workflow with code
PATCH  /v1/workflows/{uuid}     — Partial update
DELETE /v1/workflows/{uuid}     — Delete (403 if is_system=True)

On create and on any PATCH that includes a new `code` value, the code is
AST-validated before storage. Invalid code returns 400 with the error list.
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
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.workflows import (
    WorkflowCreate,
    WorkflowPatch,
    WorkflowResponse,
    WorkflowSummary,
)
from app.services.workflow_ast import validate_workflow_code

router = APIRouter(prefix="/workflows", tags=["workflows"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.WORKFLOWS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.WORKFLOWS_WRITE))]


def _to_summary(w: object) -> WorkflowSummary:
    return WorkflowSummary.model_validate(w)


def _to_response(w: object) -> WorkflowResponse:
    return WorkflowResponse.model_validate(w)


def _assert_valid_code(code: str) -> None:
    """Run AST validation and raise 400 if any errors are found."""
    errors = validate_workflow_code(code)
    if errors:
        raise CalsetaException(
            code="WORKFLOW_CODE_INVALID",
            message="Workflow code failed validation",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"errors": errors},
        )


# ---------------------------------------------------------------------------
# GET /v1/workflows
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[WorkflowSummary])
async def list_workflows(
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    workflow_type: str | None = Query(None),
    state: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> PaginatedResponse[WorkflowSummary]:
    repo = WorkflowRepository(db)
    workflows, total = await repo.list_workflows(
        workflow_type=workflow_type,
        state=state,
        is_active=is_active,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[_to_summary(w) for w in workflows],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# POST /v1/workflows
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DataResponse[WorkflowResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow(
    body: WorkflowCreate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[WorkflowResponse]:
    _assert_valid_code(body.code)

    repo = WorkflowRepository(db)
    workflow = await repo.create(
        name=body.name,
        workflow_type=body.workflow_type,
        indicator_types=body.indicator_types,
        code=body.code,
        state=body.state,
        timeout_seconds=body.timeout_seconds,
        retry_count=body.retry_count,
        is_active=body.is_active,
        tags=body.tags,
        time_saved_minutes=body.time_saved_minutes,
        requires_approval=body.requires_approval,
        approval_channel=body.approval_channel,
        approval_timeout_seconds=body.approval_timeout_seconds,
        risk_level=body.risk_level,
        documentation=body.documentation,
    )
    return DataResponse(data=_to_response(workflow))


# ---------------------------------------------------------------------------
# GET /v1/workflows/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{workflow_uuid}", response_model=DataResponse[WorkflowResponse])
async def get_workflow(
    workflow_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[WorkflowResponse]:
    repo = WorkflowRepository(db)
    workflow = await repo.get_by_uuid(workflow_uuid)
    if workflow is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Workflow {workflow_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=_to_response(workflow))


# ---------------------------------------------------------------------------
# PATCH /v1/workflows/{uuid}
# ---------------------------------------------------------------------------


@router.patch("/{workflow_uuid}", response_model=DataResponse[WorkflowResponse])
async def patch_workflow(
    workflow_uuid: UUID,
    body: WorkflowPatch,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[WorkflowResponse]:
    repo = WorkflowRepository(db)
    workflow = await repo.get_by_uuid(workflow_uuid)
    if workflow is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Workflow {workflow_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if body.code is not None:
        _assert_valid_code(body.code)

    workflow = await repo.patch(
        workflow,
        name=body.name,
        workflow_type=body.workflow_type,
        indicator_types=body.indicator_types,
        code=body.code,
        state=body.state,
        timeout_seconds=body.timeout_seconds,
        retry_count=body.retry_count,
        is_active=body.is_active,
        tags=body.tags,
        time_saved_minutes=body.time_saved_minutes,
        requires_approval=body.requires_approval,
        approval_channel=body.approval_channel,
        approval_timeout_seconds=body.approval_timeout_seconds,
        risk_level=body.risk_level,
        documentation=body.documentation,
    )
    return DataResponse(data=_to_response(workflow))


# ---------------------------------------------------------------------------
# DELETE /v1/workflows/{uuid}
# ---------------------------------------------------------------------------


@router.delete("/{workflow_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = WorkflowRepository(db)
    workflow = await repo.get_by_uuid(workflow_uuid)
    if workflow is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Workflow {workflow_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if workflow.is_system:
        raise CalsetaException(
            code="FORBIDDEN",
            message="System workflows cannot be deleted",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    await repo.delete(workflow)
