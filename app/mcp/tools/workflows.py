"""
MCP tool for workflow execution.

Tool:
  - execute_workflow — Run a registered workflow with trigger context
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime

import structlog
from mcp.server.fastmcp import Context

from app.db.session import AsyncSessionLocal
from app.mcp.scope import _resolve_client_id, check_scope
from app.mcp.server import mcp_server
from app.repositories.workflow_repository import WorkflowRepository
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.schemas.indicators import IndicatorType

logger = structlog.get_logger(__name__)

_VALID_INDICATOR_TYPES = sorted(t.value for t in IndicatorType)


def _json_serial(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@mcp_server.tool()
async def execute_workflow(
    workflow_uuid: str,
    indicator_type: str,
    indicator_value: str,
    ctx: Context,
    alert_uuid: str | None = None,
    reason: str | None = None,
    confidence: float | None = None,
) -> str:
    """Execute a registered workflow with the given trigger context.

    The workflow is enqueued for asynchronous execution and a run UUID is
    returned immediately. Use the run UUID to check execution status.

    If the workflow requires approval, the execution is gated behind an
    approval request — the response will indicate "pending_approval" status.

    Args:
        workflow_uuid: UUID of the workflow to execute.
        indicator_type: Type of indicator triggering the workflow. Valid values:
                       "ip", "domain", "hash_md5", "hash_sha1", "hash_sha256",
                       "url", "email", "account".
        indicator_value: The indicator value (e.g. an IP address, domain name).
        alert_uuid: Optional UUID of the related alert.
        reason: Why this workflow should be executed (required for approval gate).
        confidence: Confidence score 0.0-1.0 (required for approval gate).

    Returns:
        JSON with run_uuid and status ("queued" or "pending_approval").
    """
    try:
        parsed_wf_uuid = _uuid.UUID(workflow_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid workflow UUID: {workflow_uuid}"})

    if indicator_type not in _VALID_INDICATOR_TYPES:
        return json.dumps({
            "error": f"Invalid indicator_type '{indicator_type}'. "
            f"Must be one of: {_VALID_INDICATOR_TYPES}"
        })

    parsed_alert_uuid: _uuid.UUID | None = None
    if alert_uuid:
        try:
            parsed_alert_uuid = _uuid.UUID(alert_uuid)
        except ValueError:
            return json.dumps({"error": f"Invalid alert UUID: {alert_uuid}"})

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "workflows:execute")
        if scope_err:
            return scope_err

        wf_repo = WorkflowRepository(session)
        workflow = await wf_repo.get_by_uuid(parsed_wf_uuid)
        if workflow is None:
            return json.dumps({"error": f"Workflow not found: {workflow_uuid}"})

        if not workflow.is_active or workflow.state == "draft":
            return json.dumps({
                "error": "Workflow cannot be executed: inactive or in draft state."
            })

        # Resolve alert if provided
        alert_id: int | None = None
        if parsed_alert_uuid:
            from app.repositories.alert_repository import AlertRepository

            alert_repo = AlertRepository(session)
            alert = await alert_repo.get_by_uuid(parsed_alert_uuid)
            if alert is None:
                return json.dumps({"error": f"Alert not found: {alert_uuid}"})
            alert_id = alert.id

        trigger_context = {
            "indicator_type": indicator_type,
            "indicator_value": indicator_value,
            "alert_id": alert_id,
            "alert_uuid": alert_uuid,
        }

        # Approval gate (MCP calls are always agent-triggered)
        if workflow.requires_approval:
            if not reason:
                return json.dumps({
                    "error": "reason is required for workflows that require approval."
                })
            if confidence is None:
                return json.dumps({
                    "error": "confidence is required for workflows that require approval."
                })

            from app.config import settings
            from app.workflows.approval import create_approval_request
            from app.workflows.notifiers.factory import get_approval_notifier

            notifier = get_approval_notifier(settings)
            approval_req = await create_approval_request(
                workflow=workflow,
                trigger_type="agent",
                trigger_agent_key_prefix=_resolve_client_id(ctx),
                trigger_context=trigger_context,
                reason=reason,
                confidence=confidence,
                notifier_type=notifier.notifier_name,
                db=session,
                cfg=settings,
            )

            from app.queue.factory import get_queue_backend

            queue = get_queue_backend()
            await queue.enqueue(
                "send_approval_notification_task",
                {"approval_request_id": approval_req.id},
                queue="dispatch",
                delay_seconds=0,
                priority=0,
            )

            await session.commit()

            return json.dumps({
                "status": "pending_approval",
                "approval_request_uuid": str(approval_req.uuid),
                "workflow_uuid": workflow_uuid,
                "expires_at": approval_req.expires_at.isoformat(),
            }, default=_json_serial)

        # Immediate execution path
        run_repo = WorkflowRunRepository(session)
        run = await run_repo.create(
            workflow_id=workflow.id,
            trigger_type="agent",
            trigger_context=trigger_context,
            code_version_executed=workflow.code_version,
            status="queued",
        )
        await session.flush()

        from app.queue.factory import get_queue_backend

        queue = get_queue_backend()
        await queue.enqueue(
            "execute_workflow_run",
            {"workflow_run_id": run.id},
            queue="workflows",
            delay_seconds=0,
            priority=0,
        )

        await session.commit()

        return json.dumps({
            "status": "queued",
            "run_uuid": str(run.uuid),
            "workflow_uuid": workflow_uuid,
        }, default=_json_serial)
