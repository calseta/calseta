"""
Workflow approval management endpoints.

REST API (API-key authenticated):
  GET    /v1/workflow-approvals                     — Paginated list with filters
  GET    /v1/workflow-approvals/{uuid}              — Full approval request state
  POST   /v1/workflow-approvals/{uuid}/approve      — Approve (human REST)
  POST   /v1/workflow-approvals/{uuid}/reject       — Reject (human REST)

Browser / callback (token or platform-signed):
  GET    /v1/workflow-approvals/{uuid}/decide       — Browser approval page
  POST   /v1/workflow-approvals/{uuid}/decide       — Browser form submission
  POST   /v1/workflow-approvals/callback/slack      — Slack interactive button callback
  POST   /v1/workflow-approvals/callback/teams      — Teams stub
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Header, Query, Request, Response, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.models.api_key import APIKey as ApiKeyModel
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.workflow_approvals import (
    WorkflowApprovalRequestResponse,
    WorkflowApproveRequest,
    WorkflowRejectRequest,
)

router = APIRouter(prefix="/workflow-approvals", tags=["workflow-approvals"])

_Approve = Annotated[AuthContext, Depends(require_scope(Scope.APPROVALS_WRITE))]


async def _materialize_expired(rows: list, db: AsyncSession) -> None:
    """Check-on-access materialization: any pending row whose expires_at has
    passed is updated to 'expired' in-place.  This ensures API consumers
    always see the correct status without relying on a background sweep."""
    now = datetime.now(UTC)
    dirty = False
    for r in rows:
        if r.status != "pending":
            continue
        # expires_at may be timezone-naive depending on DB driver; normalize
        expires_at = r.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if now > expires_at:
            r.status = "expired"
            dirty = True
    if dirty:
        await db.flush()
        await db.commit()


# ---------------------------------------------------------------------------
# GET /v1/workflow-approvals
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[WorkflowApprovalRequestResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_approval_requests(
    request: Request,
    auth: _Approve,
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

    await _materialize_expired(rows, db)

    # Batch-load workflow names for all rows
    wf_ids = {r.workflow_id for r in rows}
    wf_map: dict[int, tuple[str, str]] = {}
    if wf_ids:
        wf_result = await db.execute(
            select(Workflow.id, Workflow.name, Workflow.uuid).where(Workflow.id.in_(wf_ids))
        )
        for wf_id, wf_name, wf_uuid in wf_result.all():
            wf_map[wf_id] = (wf_name, str(wf_uuid))

    data = []
    for r in rows:
        resp = WorkflowApprovalRequestResponse.model_validate(r)
        if r.workflow_id in wf_map:
            resp.workflow_name = wf_map[r.workflow_id][0]
            resp.workflow_uuid = UUID(wf_map[r.workflow_id][1])
        data.append(resp)

    return PaginatedResponse(
        data=data,
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# GET /v1/workflow-approvals/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{approval_uuid}", response_model=DataResponse[WorkflowApprovalRequestResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_approval_request(
    request: Request,
    approval_uuid: UUID,
    auth: _Approve,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[WorkflowApprovalRequestResponse]:
    from sqlalchemy import select

    from app.db.models.workflow import Workflow
    from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR

    result = await db.execute(select(WAR).where(WAR.uuid == approval_uuid))
    approval = result.scalar_one_or_none()
    if approval is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Approval request {approval_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await _materialize_expired([approval], db)
    resp = WorkflowApprovalRequestResponse.model_validate(approval)
    wf_result = await db.execute(
        select(Workflow.name, Workflow.uuid).where(Workflow.id == approval.workflow_id)
    )
    wf_row = wf_result.one_or_none()
    if wf_row:
        resp.workflow_name = wf_row[0]
        resp.workflow_uuid = wf_row[1]
    return DataResponse(data=resp)


# ---------------------------------------------------------------------------
# POST /v1/workflow-approvals/{uuid}/approve
# ---------------------------------------------------------------------------


@router.post(
    "/{approval_uuid}/approve",
    response_model=DataResponse[WorkflowApprovalRequestResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def approve_workflow(
    request: Request,
    approval_uuid: UUID,
    auth: _Approve,
    db: Annotated[AsyncSession, Depends(get_db)],
    body: WorkflowApproveRequest | None = None,
) -> DataResponse[WorkflowApprovalRequestResponse]:
    """
    Approve a pending workflow approval request.

    Enqueues execute_approved_workflow_task so the workflow runs asynchronously.
    Returns 409 if the request has expired or is already in a terminal state.
    """
    from app.workflows.approval import process_approval_decision

    try:
        # Resolve API key name for audit display
        key_name: str | None = None
        key_row = (await db.execute(
            select(ApiKeyModel.name).where(ApiKeyModel.id == auth.key_id)
        )).scalar_one_or_none()
        if key_row:
            key_name = key_row

        responder = (body.responder_id if body else None) or str(auth.key_prefix)
        approval = await process_approval_decision(
            approval_uuid=approval_uuid,
            approved=True,
            responder_id=responder,
            db=db,
            actor_key_prefix=auth.key_prefix,
            actor_key_name=key_name,
        )
        await db.commit()
        await db.refresh(approval)
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

    return DataResponse(data=WorkflowApprovalRequestResponse.model_validate(approval))


# ---------------------------------------------------------------------------
# POST /v1/workflow-approvals/{uuid}/reject
# ---------------------------------------------------------------------------


@router.post(
    "/{approval_uuid}/reject",
    response_model=DataResponse[WorkflowApprovalRequestResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def reject_workflow(
    request: Request,
    approval_uuid: UUID,
    auth: _Approve,
    db: Annotated[AsyncSession, Depends(get_db)],
    body: WorkflowRejectRequest | None = None,
) -> DataResponse[WorkflowApprovalRequestResponse]:
    """
    Reject a pending workflow approval request.

    No execution is enqueued. Returns 409 if the request has expired or is
    already in a terminal state.
    """
    from app.workflows.approval import process_approval_decision

    try:
        key_name: str | None = None
        key_row = (await db.execute(
            select(ApiKeyModel.name).where(ApiKeyModel.id == auth.key_id)
        )).scalar_one_or_none()
        if key_row:
            key_name = key_row

        responder = (body.responder_id if body else None) or str(auth.key_prefix)
        approval = await process_approval_decision(
            approval_uuid=approval_uuid,
            approved=False,
            responder_id=responder,
            db=db,
            actor_key_prefix=auth.key_prefix,
            actor_key_name=key_name,
        )
        await db.commit()
        await db.refresh(approval)
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

    return DataResponse(data=WorkflowApprovalRequestResponse.model_validate(approval))


# ===========================================================================
# Browser approval page + platform callbacks
# (formerly in approvals.py — consolidated here per Phase 6 cleanup)
# ===========================================================================

_FAVICON = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 288 288'%3E"
    "%3Cpath fill='%234D7D71' d='m144,155.04c-45.72,0-82.91,37.19"
    "-82.91,82.91h30.25c0-29.04,23.62-52.66,52.66-52.66s52.66,"
    "23.62,52.66,52.66h30.25c0-45.72-37.2-82.91-82.91-82.91Z'/%3E"
    "%3Cpath fill='%234D7D71' d='m144,102.24c17.37,27.47,48,45.76,"
    "82.83,45.76v-30.25c-37.33,0-67.7-30.37-67.7-67.7h-30.25c0,"
    "37.33-30.37,67.7-67.7,67.7v30.25c34.83,0,65.46-18.29,82.83"
    "-45.76Z'/%3E%3Cpath fill='%234D7D71' d='m253.39,279.16H34.61"
    "c-14.21,0-25.77-11.56-25.77-25.77V34.61c0-14.21,11.56-25.77,"
    "25.77-25.77h218.78c14.21,0,25.77,11.56,25.77,25.77v218.78c0,"
    "14.21-11.56,25.77-25.77,25.77ZM34.61,18.79c-8.72,0-15.82,"
    "7.1-15.82,15.82v218.78c0,8.72,7.1,15.82,15.82,15.82h218.78"
    "c8.72,0,15.82-7.1,15.82-15.82V34.61c0-8.72-7.1-15.82-15.82"
    "-15.82H34.61Z'/%3E%3C/svg%3E"
)

_HEAD = (
    '<meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    f'<link rel="icon" type="image/svg+xml" href="{_FAVICON}">'
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Manrope:wght@400;600;800&family=IBM+Plex+Mono:wght@400;500&display=swap\">"
    "<style>"
    "*{box-sizing:border-box;margin:0;padding:0}"
    "html,body{height:100%}"
    "body{font-family:'IBM Plex Mono',ui-monospace,monospace;background:#080b0f;color:#CCD0CF;"
    "min-height:100vh;padding:0;-webkit-font-smoothing:antialiased;}"
    ".topbar{position:fixed;top:0;left:0;right:0;height:56px;display:flex;align-items:center;"
    "padding:0 24px;background:#0d1117;border-bottom:1px solid #1e2a25;z-index:10;}"
    ".topbar img{height:28px;width:auto}"
    ".topbar svg{width:28px;height:28px;flex-shrink:0;display:none}"
    ".main{display:flex;align-items:center;justify-content:center;"
    "min-height:100vh;padding:80px 24px 24px;}"
    ".w{width:100%;max-width:480px}"
    ".c{background:#0d1117;border:1px solid #1e2a25;border-radius:16px;padding:28px;}"
    "h1{font-family:'Manrope',system-ui,sans-serif;font-weight:800;font-size:1.15rem;"
    "letter-spacing:-0.02em;color:#CCD0CF;display:flex;align-items:center;"
    "gap:8px;margin-bottom:2px;}"
    ".sub{color:#57635F;font-size:0.8rem;margin:2px 0 20px}"
    ".pill{display:inline-block;padding:3px 10px;border-radius:9999px;"
    "font-family:'IBM Plex Mono',monospace;font-size:0.65rem;"
    "font-weight:500;text-transform:uppercase;letter-spacing:0.04em;}"
    ".r-high,.r-critical{background:rgba(234,89,27,.15);color:#EA591B}"
    ".r-medium{background:rgba(255,187,26,.15);color:#FFBB1A}"
    ".r-low,.r-informational{background:rgba(77,125,113,.15);color:#7FCAB8}"
    ".g{display:grid;grid-template-columns:1fr 1fr;gap:16px 24px;"
    "margin:20px 0;padding:16px;background:#111820;border-radius:10px;}"
    ".gl{font-size:0.7rem;color:#57635F;text-transform:uppercase;"
    "letter-spacing:0.05em;margin-bottom:3px;}"
    ".gv{font-size:0.85rem;font-weight:500;color:#CCD0CF;word-break:break-all}"
    ".gv code{color:#7FCAB8;font-size:0.8rem;background:none}"
    ".ioc{display:inline-block;margin-top:4px;padding:4px 10px;"
    "background:rgba(77,125,113,.1);border:1px solid #1e2a25;border-radius:6px;"
    "font-family:'IBM Plex Mono',monospace;font-size:0.8rem;color:#7FCAB8;"
    "word-break:break-all;}"
    ".reason{background:#111820;border-radius:10px;padding:14px 16px;"
    "margin:16px 0 0;font-size:0.8rem;line-height:1.5;color:#CCD0CF;}"
    ".reason strong{color:#57635F;font-weight:500}"
    ".acts{display:flex;gap:10px;margin-top:24px}"
    ".btn{flex:1;padding:11px 16px;border:none;border-radius:8px;"
    "font-family:'IBM Plex Mono',monospace;font-size:0.85rem;"
    "font-weight:500;cursor:pointer;transition:all .15s ease;}"
    ".ba{background:#4D7D71;color:#fff}"
    ".ba:hover{background:#3a5f56}"
    ".br{background:transparent;color:#EA591B;border:1px solid #EA591B}"
    ".br:hover{background:rgba(234,89,27,.1)}"
    ".sb{text-align:center;padding:28px 20px;border-radius:10px;"
    "font-family:'IBM Plex Mono',monospace;font-size:0.9rem;font-weight:500;}"
    ".s-ok{background:rgba(77,125,113,.12);color:#7FCAB8;"
    "border:1px solid rgba(77,125,113,.25)}"
    ".s-no{background:rgba(234,89,27,.1);color:#EA591B;"
    "border:1px solid rgba(234,89,27,.2)}"
    ".s-ex{background:rgba(255,187,26,.1);color:#FFBB1A;"
    "border:1px solid rgba(255,187,26,.2)}"
    ".s-na{background:rgba(87,99,95,.15);color:#57635F;"
    "border:1px solid rgba(87,99,95,.25)}"
    "</style>"
)

_LOGO = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 288 288"'
    ' width="24" height="24">'
    '<path fill="#4D7D71" d="m144,155.04c-45.72,0-82.91,37.19-82.91,'
    "82.91h30.25c0-29.04,23.62-52.66,52.66-52.66s52.66,23.62,52.66,"
    '52.66h30.25c0-45.72-37.2-82.91-82.91-82.91Z"/>'
    '<path fill="#4D7D71" d="m144,102.24c17.37,27.47,48,45.76,82.83,'
    "45.76v-30.25c-37.33,0-67.7-30.37-67.7-67.7h-30.25c0,37.33-30.37,"
    '67.7-67.7,67.7v30.25c34.83,0,65.46-18.29,82.83-45.76Z"/>'
    '<path fill="#4D7D71" d="m253.39,279.16H34.61c-14.21,0-25.77-11.56'
    "-25.77-25.77V34.61c0-14.21,11.56-25.77,25.77-25.77h218.78c14.21,"
    "0,25.77,11.56,25.77,25.77v218.78c0,14.21-11.56,25.77-25.77,"
    "25.77ZM34.61,18.79c-8.72,0-15.82,7.1-15.82,15.82v218.78c0,"
    "8.72,7.1,15.82,15.82,15.82h218.78c8.72,0,15.82-7.1,15.82-15.82"
    'V34.61c0-8.72-7.1-15.82-15.82-15.82H34.61Z"/></svg>'
)

_STATUS_CSS = {
    "approved": "s-ok",
    "rejected": "s-no",
    "expired": "s-ex",
}


def _esc(val: str) -> str:
    """HTML-escape a string to prevent XSS."""
    return (
        str(val)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def _approval_page_html(
    workflow_name: str,
    risk_level: str,
    indicator_type: str,
    indicator_value: str,
    reason: str,
    confidence: float,
    expires_at: datetime,
    approval_uuid: str,
    token: str,
) -> str:
    pct = f"{confidence * 100:.0f}%"
    rl = risk_level.lower() if risk_level else "medium"
    exp = expires_at.strftime("%Y-%m-%d %H:%M UTC")

    return (
        "<!DOCTYPE html><html lang=en><head>"
        "<title>Calseta</title>"
        f"{_HEAD}</head><body>"
        f'<div class="topbar"><img src="/logo.png" alt="Calseta"'
        f' onerror="this.style.display=\'none\';'
        f'this.nextElementSibling.style.display=\'block\'">'
        f"{_LOGO}</div>"
        '<div class="main"><div class="w">'
        '<div class="c">'
        f'<h1><span class="pill r-{_esc(rl)}">'
        f"{_esc(risk_level)}</span> Workflow Approval</h1>"
        f'<div class="sub">{_esc(workflow_name)}</div>'
        '<div class="g">'
        f'<div><div class="gl">Indicator Type</div>'
        f'<div class="gv">{_esc(indicator_type)}</div></div>'
        f'<div><div class="gl">Confidence</div>'
        f'<div class="gv">{pct}</div></div>'
        f'<div><div class="gl">Risk Level</div>'
        f'<div class="gv">{_esc(risk_level)}</div></div>'
        f'<div><div class="gl">Expires</div>'
        f'<div class="gv">{exp}</div></div>'
        f'<div style="grid-column:1/-1"><div class="gl">Indicator</div>'
        f'<span class="ioc">'
        f"{_esc(indicator_value)}</span></div>"
        "</div>"
        f'<div class="reason"><strong>Agent reason</strong>'
        f"<br>{_esc(reason)}</div>"
        '<form method="post">'
        f'<input type="hidden" name="token" value="{_esc(token)}">'
        '<div class="acts">'
        '<button type="submit" name="decision" value="approve"'
        ' class="btn ba">Approve</button>'
        '<button type="submit" name="decision" value="reject"'
        ' class="btn br">Reject</button>'
        "</div></form>"
        "</div>"
        "</div></div></body></html>"
    )


def _status_page_html(
    title: str, message: str, css_class: str
) -> str:
    return (
        "<!DOCTYPE html><html lang=en><head>"
        "<title>Calseta</title>"
        f"{_HEAD}</head><body>"
        f'<div class="topbar"><img src="/logo.png" alt="Calseta"'
        f' onerror="this.style.display=\'none\';'
        f'this.nextElementSibling.style.display=\'block\'">'
        f"{_LOGO}</div>"
        '<div class="main"><div class="w">'
        '<div class="c">'
        f'<div class="sb {css_class}">{_esc(message)}</div>'
        "</div>"
        "</div></div></body></html>"
    )


# ---------------------------------------------------------------------------
# GET /v1/workflow-approvals/{uuid}/decide — browser approval page
# ---------------------------------------------------------------------------


@router.get("/{approval_uuid}/decide")
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_approval_decide_page(
    request: Request,
    approval_uuid: UUID,
    token: Annotated[str, Query()],
) -> HTMLResponse:
    """
    Render a browser-based approval page for the given approval request.

    Auth: the `token` query parameter is the decide_token generated at approval
    creation time. No API key required.
    """
    from app.db.models.workflow import Workflow as WorkflowModel
    from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WAR).where(WAR.uuid == approval_uuid)
        )
        approval = result.scalar_one_or_none()

        if approval is None:
            return HTMLResponse(
                _status_page_html("Not Found", "Approval request not found.", "s-na"),
                status_code=404,
            )

        # Constant-time token comparison
        if not approval.decide_token or not hmac.compare_digest(
            approval.decide_token, token
        ):
            return HTMLResponse(
                _status_page_html("Forbidden", "Invalid approval token.", "s-na"),
                status_code=403,
            )

        # Already decided?
        if approval.status != "pending":
            status_css = _STATUS_CSS.get(approval.status, "s-na")
            return HTMLResponse(
                _status_page_html(
                    "Already Decided",
                    f"This approval request has already been {approval.status}.",
                    status_css,
                ),
            )

        # Expired?
        expires_at = approval.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if datetime.now(UTC) > expires_at:
            approval.status = "expired"
            await session.commit()
            return HTMLResponse(
                _status_page_html(
                    "Expired",
                    "This approval request has expired.",
                    "s-ex",
                ),
            )

        # Load workflow for display
        wf_result = await session.execute(
            select(WorkflowModel).where(WorkflowModel.id == approval.workflow_id)
        )
        workflow = wf_result.scalar_one_or_none()
        tc = approval.trigger_context or {}

        return HTMLResponse(
            _approval_page_html(
                workflow_name=workflow.name if workflow else "Unknown Workflow",
                risk_level=workflow.risk_level if workflow else "medium",
                indicator_type=str(tc.get("indicator_type", "")),
                indicator_value=str(tc.get("indicator_value", "")),
                reason=approval.reason,
                confidence=approval.confidence,
                expires_at=expires_at,
                approval_uuid=str(approval_uuid),
                token=token,
            )
        )


# ---------------------------------------------------------------------------
# POST /v1/workflow-approvals/{uuid}/decide — browser form submission
# ---------------------------------------------------------------------------


@router.post("/{approval_uuid}/decide")
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def post_approval_decide(
    request: Request,
    approval_uuid: UUID,
    token: Annotated[str, Form()],
    decision: Annotated[str, Form()],
) -> HTMLResponse:
    """
    Process an approval decision submitted from the browser approval page.

    Auth: the `token` form field is the decide_token. No API key required.
    """
    from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR
    from app.db.session import AsyncSessionLocal
    from app.workflows.approval import process_approval_decision

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(WAR).where(WAR.uuid == approval_uuid)
        )
        approval = result.scalar_one_or_none()

        if approval is None:
            return HTMLResponse(
                _status_page_html("Not Found", "Approval request not found.", "s-na"),
                status_code=404,
            )

        # Constant-time token comparison
        if not approval.decide_token or not hmac.compare_digest(
            approval.decide_token, token
        ):
            return HTMLResponse(
                _status_page_html("Forbidden", "Invalid approval token.", "s-na"),
                status_code=403,
            )

        if decision not in ("approve", "reject"):
            return HTMLResponse(
                _status_page_html(
                    "Bad Request",
                    "Invalid decision. Must be 'approve' or 'reject'.",
                    "s-na",
                ),
                status_code=400,
            )

        approved = decision == "approve"

        try:
            await process_approval_decision(
                approval_uuid=approval_uuid,
                approved=approved,
                responder_id="browser",
                db=session,
            )
            await session.commit()
        except ValueError as exc:
            error_msg = str(exc)
            if "expired" in error_msg.lower():
                await session.commit()  # flush the expired status change
                return HTMLResponse(
                    _status_page_html(
                        "Expired",
                        "This approval request has expired.",
                        "s-ex",
                    ),
                )
            if "terminal status" in error_msg.lower():
                return HTMLResponse(
                    _status_page_html(
                        "Already Decided",
                        "This approval request has already been decided.",
                        "s-na",
                    ),
                )
            return HTMLResponse(
                _status_page_html(
                    "Error",
                    f"Could not process decision: {_esc(error_msg)}",
                    "s-na",
                ),
                status_code=400,
            )

        if approved:
            return HTMLResponse(
                _status_page_html(
                    "Approved",
                    "Workflow approved. Execution has been queued.",
                    "s-ok",
                ),
            )
        return HTMLResponse(
            _status_page_html(
                "Rejected",
                "Workflow rejected. No execution will occur.",
                "s-no",
            ),
        )


# ---------------------------------------------------------------------------
# POST /v1/workflow-approvals/callback/slack
# ---------------------------------------------------------------------------


@router.post("/callback/slack", status_code=status.HTTP_200_OK)
async def slack_callback(
    request: Request,
    x_slack_signature: Annotated[str | None, Header()] = None,
    x_slack_request_timestamp: Annotated[str | None, Header()] = None,
) -> Response:
    """
    Receive Slack interactive button payloads.

    Validates the Slack signature, extracts the approval decision from the
    action_id, and calls process_approval_decision(). Returns 200 immediately
    (Slack requires < 3 seconds).

    Note: raw body is read first so that body bytes are cached before form
    parsing — this is required for correct HMAC signature validation against
    the raw request body.
    """
    import structlog

    from app.db.session import AsyncSessionLocal
    from app.workflows.approval import process_approval_decision

    log = structlog.get_logger(__name__)

    # Read and cache raw body before any form parsing (required for sig validation)
    raw_body = await request.body()

    # -- Signature validation --
    signing_secret = settings.SLACK_SIGNING_SECRET
    if signing_secret:
        ts = x_slack_request_timestamp or ""
        sig = x_slack_signature or ""

        # Reject stale requests (> 5 min old)
        try:
            if abs(time.time() - float(ts)) > 300:
                return Response(status_code=status.HTTP_403_FORBIDDEN, content="Request too old")
        except (ValueError, TypeError):
            return Response(status_code=status.HTTP_403_FORBIDDEN, content="Invalid timestamp")

        sig_base = f"v0:{ts}:{raw_body.decode()}"
        expected = "v0=" + hmac.new(
            signing_secret.encode(),
            sig_base.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return Response(status_code=status.HTTP_403_FORBIDDEN, content="Invalid signature")

    # Parse payload from form data (body is already cached, so stream() yields _body)
    form_data = await request.form()
    payload: str | None = form_data.get("payload")  # type: ignore[assignment]

    if not payload:
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Missing payload")

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid JSON payload")

    # Extract action from Block Kit interactive payload
    actions = data.get("actions", [])
    if not actions:
        return Response(content="ok")

    action = actions[0]
    action_id: str = action.get("action_id", "")
    slack_user_id: str = data.get("user", {}).get("id", "")

    # action_id format: "approve:{uuid}" or "reject:{uuid}"
    if not action_id or ":" not in action_id:
        return Response(content="ok")

    decision_str, uuid_str = action_id.split(":", 1)
    approved = decision_str == "approve"

    try:
        approval_uuid_val = UUID(uuid_str)
    except ValueError:
        log.warning("slack_callback_invalid_uuid", action_id=action_id)
        return Response(content="ok")

    try:
        async with AsyncSessionLocal() as db:
            await process_approval_decision(
                approval_uuid=approval_uuid_val,
                approved=approved,
                responder_id=slack_user_id or None,
                db=db,
            )
            await db.commit()
    except ValueError as exc:
        log.warning("slack_callback_decision_failed", error=str(exc))

    # Fire-and-forget: update the original Slack message to replace buttons
    # with the decision text (prevents double-clicks and shows outcome inline)
    channel_id = data.get("channel", {}).get("id", "")
    message_ts = data.get("message", {}).get("ts", "")
    original_blocks = data.get("message", {}).get("blocks", [])
    bot_token = settings.SLACK_BOT_TOKEN

    if bot_token and channel_id and message_ts:
        try:
            import httpx

            outcome_icon = "\u2705" if approved else "\u274c"
            by_text = f" by <@{slack_user_id}>" if slack_user_id else ""
            decision_text = (
                f"{outcome_icon} *{'Approved' if approved else 'Rejected'}*{by_text}"
            )

            # Keep original blocks (header, fields, reason) but replace the actions block
            updated_blocks = [b for b in original_blocks if b.get("type") != "actions"]
            updated_blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": decision_text},
            })

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    "https://slack.com/api/chat.update",
                    headers={
                        "Authorization": f"Bearer {bot_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "channel": channel_id,
                        "ts": message_ts,
                        "blocks": updated_blocks,
                    },
                )
        except Exception as exc:
            log.warning("slack_message_update_failed", error=str(exc))

    return Response(content="ok")


# ---------------------------------------------------------------------------
# POST /v1/workflow-approvals/callback/teams
# ---------------------------------------------------------------------------


@router.post("/callback/teams", status_code=status.HTTP_200_OK)
async def teams_callback() -> dict:  # type: ignore[type-arg]
    """
    Teams interactive callback stub.

    Teams incoming webhooks do not support interactive button callbacks
    (that requires Azure Bot Framework, which is out of scope for v1).

    Approvers should use the REST API endpoints or the browser approval page:
      POST /v1/workflow-approvals/{uuid}/approve or /reject
      GET  /v1/workflow-approvals/{uuid}/decide?token=...
    """
    return {
        "message": (
            "Teams interactive callbacks are not supported via incoming webhooks in v1. "
            "Use the Calseta REST API to approve or reject: "
            "POST /v1/workflow-approvals/{uuid}/approve or /reject, "
            "or use the browser approval link in the Teams card."
        )
    }
