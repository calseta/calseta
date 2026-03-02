"""
Workflow approval management endpoints (Chunk 4.11).

GET    /v1/workflow-approvals           — Paginated list with status/workflow filters
GET    /v1/workflow-approvals/{uuid}    — Full approval request state
POST   /v1/workflow-approvals/{uuid}/approve  — Approve (human REST)
POST   /v1/workflow-approvals/{uuid}/reject   — Reject (human REST)
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
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.workflow_approvals import (
    WorkflowApprovalRequestResponse,
    WorkflowApproveRequest,
    WorkflowRejectRequest,
)

router = APIRouter(prefix="/workflow-approvals", tags=["workflow-approvals"])

_Execute = Annotated[AuthContext, Depends(require_scope(Scope.WORKFLOWS_EXECUTE))]


# ---------------------------------------------------------------------------
# GET /v1/workflow-approvals
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[WorkflowApprovalRequestResponse])
async def list_approval_requests(
    auth: _Execute,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    approval_status: str | None = Query(None, alias="status"),
    workflow_uuid: UUID | None = Query(None),
) -> PaginatedResponse[WorkflowApprovalRequestResponse]:
    """List workflow approval requests. Filterable by status and workflow_uuid."""
    from sqlalchemy import func, select

    from app.db.models.workflow import Workflow
    from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR

    stmt = select(WAR)
    count_stmt = select(func.count()).select_from(WAR)

    if approval_status is not None:
        stmt = stmt.where(WAR.status == approval_status)
        count_stmt = count_stmt.where(WAR.status == approval_status)

    if workflow_uuid is not None:
        wf_result = await db.execute(select(Workflow).where(Workflow.uuid == workflow_uuid))
        wf = wf_result.scalar_one_or_none()
        if wf is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Workflow {workflow_uuid} not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        stmt = stmt.where(WAR.workflow_id == wf.id)
        count_stmt = count_stmt.where(WAR.workflow_id == wf.id)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    offset = (pagination.page - 1) * pagination.page_size
    stmt = stmt.order_by(WAR.created_at.desc()).offset(offset).limit(pagination.page_size)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    return PaginatedResponse(
        data=[WorkflowApprovalRequestResponse.model_validate(r) for r in rows],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# GET /v1/workflow-approvals/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{approval_uuid}", response_model=DataResponse[WorkflowApprovalRequestResponse])
async def get_approval_request(
    approval_uuid: UUID,
    auth: _Execute,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[WorkflowApprovalRequestResponse]:
    from sqlalchemy import select

    from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR

    result = await db.execute(select(WAR).where(WAR.uuid == approval_uuid))
    request = result.scalar_one_or_none()
    if request is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Approval request {approval_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=WorkflowApprovalRequestResponse.model_validate(request))


# ---------------------------------------------------------------------------
# POST /v1/workflow-approvals/{uuid}/approve
# ---------------------------------------------------------------------------


@router.post(
    "/{approval_uuid}/approve",
    response_model=DataResponse[WorkflowApprovalRequestResponse],
)
async def approve_workflow(
    approval_uuid: UUID,
    body: WorkflowApproveRequest,
    auth: _Execute,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[WorkflowApprovalRequestResponse]:
    """
    Approve a pending workflow approval request.

    Enqueues execute_approved_workflow_task so the workflow runs asynchronously.
    Returns 409 if the request has expired or is already in a terminal state.
    """
    from app.workflows.approval import process_approval_decision

    try:
        request = await process_approval_decision(
            approval_uuid=approval_uuid,
            approved=True,
            responder_id=body.responder_id or str(auth.key_prefix),
            db=db,
        )
        await db.commit()
        await db.refresh(request)
    except ValueError as exc:
        err_msg = str(exc)
        if "expired" in err_msg.lower():
            raise CalsetaException(
                code="APPROVAL_EXPIRED",
                message=err_msg,
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        if "terminal" in err_msg.lower():
            raise CalsetaException(
                code="APPROVAL_ALREADY_DECIDED",
                message=err_msg,
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        raise CalsetaException(
            code="NOT_FOUND",
            message=err_msg,
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc

    return DataResponse(data=WorkflowApprovalRequestResponse.model_validate(request))


# ---------------------------------------------------------------------------
# POST /v1/workflow-approvals/{uuid}/reject
# ---------------------------------------------------------------------------


@router.post(
    "/{approval_uuid}/reject",
    response_model=DataResponse[WorkflowApprovalRequestResponse],
)
async def reject_workflow(
    approval_uuid: UUID,
    body: WorkflowRejectRequest,
    auth: _Execute,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[WorkflowApprovalRequestResponse]:
    """
    Reject a pending workflow approval request.

    No execution is enqueued. Returns 409 if the request has expired or is
    already in a terminal state.
    """
    from app.workflows.approval import process_approval_decision

    try:
        request = await process_approval_decision(
            approval_uuid=approval_uuid,
            approved=False,
            responder_id=body.responder_id or str(auth.key_prefix),
            db=db,
        )
        await db.commit()
        await db.refresh(request)
    except ValueError as exc:
        err_msg = str(exc)
        if "expired" in err_msg.lower():
            raise CalsetaException(
                code="APPROVAL_EXPIRED",
                message=err_msg,
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        if "terminal" in err_msg.lower():
            raise CalsetaException(
                code="APPROVAL_ALREADY_DECIDED",
                message=err_msg,
                status_code=status.HTTP_409_CONFLICT,
            ) from exc
        raise CalsetaException(
            code="NOT_FOUND",
            message=err_msg,
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc

    return DataResponse(data=WorkflowApprovalRequestResponse.model_validate(request))
