"""
Workflow management routes.

GET    /v1/workflows                  — Paginated list (no code field)
POST   /v1/workflows                  — Create workflow
POST   /v1/workflows/generate         — Generate workflow code via LLM
GET    /v1/workflows/{uuid}           — Full workflow with code
PATCH  /v1/workflows/{uuid}           — Partial update
DELETE /v1/workflows/{uuid}           — Delete (403 if is_system=True)
POST   /v1/workflows/{uuid}/execute   — Enqueue a workflow run (202 Accepted)
GET    /v1/workflows/{uuid}/runs      — Paginated run history
POST   /v1/workflows/{uuid}/test      — Sandbox test run (mock HTTP)
GET    /v1/workflows/{uuid}/versions  — Code version history

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
from app.config import settings
from app.db.session import get_db
from app.repositories.workflow_code_version_repository import WorkflowCodeVersionRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.workflow_approvals import WorkflowExecuteAgentRequest
from app.schemas.workflows import (
    WorkflowCreate,
    WorkflowExecuteResponse,
    WorkflowGenerateRequest,
    WorkflowGenerateResponse,
    WorkflowPatch,
    WorkflowResponse,
    WorkflowRunResponse,
    WorkflowSummary,
    WorkflowTestRequest,
    WorkflowTestResponse,
    WorkflowVersionResponse,
)
from app.services.workflow_ast import validate_workflow_code

router = APIRouter(prefix="/workflows", tags=["workflows"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.WORKFLOWS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.WORKFLOWS_WRITE))]
_Execute = Annotated[AuthContext, Depends(require_scope(Scope.WORKFLOWS_EXECUTE))]


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

    # Keep is_active in sync with state transitions when not explicitly set
    is_active = body.is_active
    if body.state is not None and is_active is None:
        if body.state == "active":
            is_active = True
        elif body.state in ("inactive", "draft"):
            is_active = False

    workflow = await repo.patch(
        workflow,
        name=body.name,
        workflow_type=body.workflow_type,
        indicator_types=body.indicator_types,
        code=body.code,
        state=body.state,
        timeout_seconds=body.timeout_seconds,
        retry_count=body.retry_count,
        is_active=is_active,
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


# ---------------------------------------------------------------------------
# POST /v1/workflows/{uuid}/execute  (Chunk 4.8)
# ---------------------------------------------------------------------------


@router.post(
    "/{workflow_uuid}/execute",
    status_code=status.HTTP_202_ACCEPTED,
)
async def execute_workflow(
    workflow_uuid: UUID,
    body: WorkflowExecuteAgentRequest,
    auth: _Execute,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[WorkflowExecuteResponse]:
    """
    Enqueue a workflow for execution. Returns 202 Accepted immediately.

    Approval gate:
    - If trigger_source="agent" AND workflow.requires_approval=True:
      creates an approval request, enqueues a notification, returns
      {"status": "pending_approval", "approval_request_uuid": "...", "expires_at": "..."}
    - Otherwise: immediately enqueues execution (existing behavior).

    When trigger_source="agent", both `reason` and `confidence` are required.
    """
    from app.queue.factory import get_queue_backend
    from app.repositories.alert_repository import AlertRepository

    # Agent-specific field validation
    agent_errors = body.validate_agent_fields()
    if agent_errors:
        raise CalsetaException(
            code="VALIDATION_ERROR",
            message="Missing required fields for agent-triggered execution",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"errors": agent_errors},
        )

    repo = WorkflowRepository(db)
    workflow = await repo.get_by_uuid(workflow_uuid)
    if workflow is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Workflow {workflow_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if workflow.state != "active":
        raise CalsetaException(
            code="WORKFLOW_NOT_EXECUTABLE",
            message=(
                "Workflow cannot be executed: state is "
                f"'{workflow.state}'. Set state to 'active' before executing."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Resolve optional alert_uuid → alert_id
    alert_id: int | None = None
    if body.alert_uuid is not None:
        alert_repo = AlertRepository(db)
        alert = await alert_repo.get_by_uuid(body.alert_uuid)
        if alert is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Alert {body.alert_uuid} not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        alert_id = alert.id

    trigger_context = {
        "indicator_type": body.indicator_type,
        "indicator_value": body.indicator_value,
        "alert_id": alert_id,
        "alert_uuid": str(body.alert_uuid) if body.alert_uuid else None,
    }

    # ---------------------------------------------------------------------------
    # Approval gate: agent trigger + requires_approval
    # ---------------------------------------------------------------------------
    if body.trigger_source == "agent" and workflow.requires_approval:
        from app.workflows.approval import create_approval_request
        from app.workflows.notifiers.factory import get_approval_notifier

        notifier = get_approval_notifier(settings)
        approval_req = await create_approval_request(
            workflow=workflow,
            trigger_type=body.trigger_source,
            trigger_agent_key_prefix=auth.key_prefix,
            trigger_context=trigger_context,
            reason=body.reason or "",
            confidence=body.confidence or 0.0,
            notifier_type=notifier.notifier_name,
            db=db,
            cfg=settings,
        )

        # Enqueue notification task
        queue = get_queue_backend()
        await queue.enqueue(
            "send_approval_notification_task",
            {"approval_request_id": approval_req.id},
            queue="dispatch",
            delay_seconds=0,
            priority=0,
        )

        await db.commit()

        from fastapi.responses import JSONResponse

        return JSONResponse(  # type: ignore[return-value]
            status_code=status.HTTP_202_ACCEPTED,
            content={
                "data": {
                    "status": "pending_approval",
                    "approval_request_uuid": str(approval_req.uuid),
                    "expires_at": approval_req.expires_at.isoformat(),
                }
            },
        )

    # ---------------------------------------------------------------------------
    # Immediate execution path (human trigger, or requires_approval=False)
    # ---------------------------------------------------------------------------
    run_repo = WorkflowRunRepository(db)
    run = await run_repo.create(
        workflow_id=workflow.id,
        trigger_type=body.trigger_source,
        trigger_context=trigger_context,
        code_version_executed=workflow.code_version,
        status="queued",
    )

    # Flush to get run.id, then enqueue
    await db.flush()

    queue = get_queue_backend()
    await queue.enqueue(
        "execute_workflow_run",
        {"workflow_run_id": run.id},
        queue="workflows",
        delay_seconds=0,
        priority=0,
    )

    return DataResponse(
        data=WorkflowExecuteResponse(run_uuid=run.uuid, status="queued")
    )


# ---------------------------------------------------------------------------
# GET /v1/workflows/{uuid}/runs  (Chunk 4.9)
# ---------------------------------------------------------------------------


@router.get(
    "/{workflow_uuid}/runs",
    response_model=PaginatedResponse[WorkflowRunResponse],
)
async def list_workflow_runs(
    workflow_uuid: UUID,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[WorkflowRunResponse]:
    repo = WorkflowRepository(db)
    workflow = await repo.get_by_uuid(workflow_uuid)
    if workflow is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Workflow {workflow_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    run_repo = WorkflowRunRepository(db)
    runs, total = await run_repo.list_for_workflow(
        workflow.id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[WorkflowRunResponse.model_validate(r) for r in runs],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# GET /v1/workflow-runs  (Chunk 4.10 — global run history)
# ---------------------------------------------------------------------------

workflow_runs_router = APIRouter(prefix="/workflow-runs", tags=["workflow-runs"])


@workflow_runs_router.get("", response_model=PaginatedResponse[WorkflowRunResponse])
async def list_all_workflow_runs(
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    run_status: str | None = Query(None, alias="status"),
    workflow_uuid: UUID | None = Query(None),
) -> PaginatedResponse[WorkflowRunResponse]:
    """List workflow runs across all workflows. Filterable by status and workflow_uuid."""
    # Resolve optional workflow_uuid → workflow_id
    wf_id: int | None = None
    if workflow_uuid is not None:
        wf_repo = WorkflowRepository(db)
        wf = await wf_repo.get_by_uuid(workflow_uuid)
        if wf is None:
            raise CalsetaException(
                code="NOT_FOUND",
                message=f"Workflow {workflow_uuid} not found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        wf_id = wf.id

    run_repo = WorkflowRunRepository(db)
    runs, total = await run_repo.list_all(
        status=run_status,
        workflow_id=wf_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[WorkflowRunResponse.model_validate(r) for r in runs],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# POST /v1/workflows/generate  (Chunk 4.7)
# ---------------------------------------------------------------------------


@router.post(
    "/generate",
    response_model=DataResponse[WorkflowGenerateResponse],
    status_code=status.HTTP_200_OK,
)
async def generate_workflow(
    body: WorkflowGenerateRequest,
    auth: _Write,
) -> DataResponse[WorkflowGenerateResponse]:
    """
    Generate workflow Python code from a natural language description.

    Uses the configured LLM (Anthropic Claude) to produce a runnable
    workflow. Returns the generated code for review; does not save automatically.
    Requires ANTHROPIC_API_KEY to be configured.
    """
    from app.services.workflow_generator import generate_workflow_code

    try:
        result = await generate_workflow_code(
            description=body.description,
            workflow_type=body.workflow_type,
            indicator_types=body.indicator_types,
            cfg=settings,
        )
    except ValueError as exc:
        raise CalsetaException(
            code="WORKFLOW_GENERATION_FAILED",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    return DataResponse(data=result)


# ---------------------------------------------------------------------------
# POST /v1/workflows/{uuid}/test  (Chunk 4.7)
# ---------------------------------------------------------------------------


@router.post(
    "/{workflow_uuid}/test",
    response_model=DataResponse[WorkflowTestResponse],
    status_code=status.HTTP_200_OK,
)
async def test_workflow(
    workflow_uuid: UUID,
    body: WorkflowTestRequest,
    auth: _Execute,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[WorkflowTestResponse]:
    """
    Execute a workflow in a sandboxed test environment.

    All outbound HTTP from ctx.http is intercepted — no real external calls.
    Integration clients (Okta, Entra) are replaced with mock versions that
    record calls without executing them. Returns the WorkflowResult and
    captured log output.
    """
    import httpx

    from app.workflows.context import (
        EntraClient,
        IndicatorContext,
        IntegrationClients,
        OktaClient,
        SecretsAccessor,
        WorkflowContext,
        WorkflowLogger,
    )
    from app.workflows.sandbox import run_workflow_code

    repo = WorkflowRepository(db)
    workflow = await repo.get_by_uuid(workflow_uuid)
    if workflow is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Workflow {workflow_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if workflow.state != "active":
        raise CalsetaException(
            code="WORKFLOW_NOT_EXECUTABLE",
            message=f"Workflow is in '{workflow.state}' state — set state to 'active' before testing",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Build mock HTTP transport that returns 200 for all requests
    mock_transport = httpx.MockTransport(
        handler=lambda request: httpx.Response(
            200,
            json=body.mock_http_responses or {"status": "ok"},
        )
    )

    # Build mock integration clients (record calls, no real API)
    class _MockOkta(OktaClient):
        def __init__(self) -> None:
            super().__init__(domain="mock.okta.com", api_token="mock")

        async def revoke_sessions(self, user_id: str) -> None:
            pass

        async def suspend_user(self, user_id: str) -> None:
            pass

        async def unsuspend_user(self, user_id: str) -> None:
            pass

        async def reset_password(self, user_id: str) -> str | None:
            return None

        async def expire_password(self, user_id: str) -> None:
            pass

    class _MockEntra(EntraClient):
        def __init__(self) -> None:
            super().__init__(tenant_id="mock", client_id="mock", client_secret="mock")

        async def revoke_sessions(self, user_id: str) -> None:
            pass

        async def disable_account(self, user_id: str) -> None:
            pass

        async def enable_account(self, user_id: str) -> None:
            pass

        async def reset_mfa(self, user_id: str) -> None:
            pass

    from datetime import UTC, datetime
    from uuid import uuid4

    _now = datetime.now(UTC)
    ctx = WorkflowContext(
        indicator=IndicatorContext(
            uuid=uuid4(),
            type=body.indicator_type,
            value=body.indicator_value,
            malice="Pending",
            is_enriched=False,
            enrichment_results={},
            first_seen=_now,
            last_seen=_now,
            created_at=_now,
            updated_at=_now,
        ),
        alert=None,
        http=httpx.AsyncClient(transport=mock_transport),
        log=WorkflowLogger(),
        secrets=SecretsAccessor(),
        integrations=IntegrationClients(
            okta=_MockOkta(),
            entra=_MockEntra(),
        ),
    )

    result = await run_workflow_code(
        code=workflow.code,
        ctx=ctx,
        timeout=min(workflow.timeout_seconds, 30),
    )

    return DataResponse(
        data=WorkflowTestResponse(
            success=result.success,
            message=result.message,
            log_output=ctx.log.render(),
            duration_ms=0,
            result_data=result.data or {},
        )
    )


# ---------------------------------------------------------------------------
# GET /v1/workflows/{uuid}/versions  (Chunk 4.7)
# ---------------------------------------------------------------------------


@router.get(
    "/{workflow_uuid}/versions",
    response_model=DataResponse[list[WorkflowVersionResponse]],
)
async def list_workflow_versions(
    workflow_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[list[WorkflowVersionResponse]]:
    """List saved code versions for a workflow, newest first."""
    repo = WorkflowRepository(db)
    workflow = await repo.get_by_uuid(workflow_uuid)
    if workflow is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Workflow {workflow_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    ver_repo = WorkflowCodeVersionRepository(db)
    versions = await ver_repo.list_for_workflow(workflow.id)

    return DataResponse(
        data=[
            WorkflowVersionResponse(
                version=v.version,
                code_preview=v.code[:120],
                saved_at=v.saved_at,
            )
            for v in versions
        ]
    )
