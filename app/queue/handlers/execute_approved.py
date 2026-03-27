"""Handler for the execute_approved_workflow_task task."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.workflow import Workflow as WorkflowModel
from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR
from app.queue.handlers.payloads import ExecuteApprovedWorkflowPayload
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.schemas.activity_events import ActivityEventType
from app.services.activity_event import ActivityEventService
from app.services.workflow_executor import execute_workflow
from app.workflows.context import TriggerContext
from app.workflows.notifiers.base import ApprovalRequest
from app.workflows.notifiers.factory import get_approval_notifier


class ExecuteApprovedWorkflowHandler:
    """Execute a workflow after approval.

    Creates a WorkflowRun from the approval request context and executes it.
    Updates the approval request with execution_result when done.
    """

    async def execute(
        self, payload: ExecuteApprovedWorkflowPayload, session: AsyncSession
    ) -> None:
        ar_result = await session.execute(
            select(WAR).where(WAR.id == payload.approval_request_id)
        )
        approval = ar_result.scalar_one_or_none()
        if approval is None:
            return

        wf_result = await session.execute(
            select(WorkflowModel).where(WorkflowModel.id == approval.workflow_id)
        )
        workflow = wf_result.scalar_one_or_none()
        if workflow is None:
            return

        tc = approval.trigger_context or {}
        trigger_ctx = TriggerContext(
            indicator_type=str(tc.get("indicator_type", "")),
            indicator_value=str(tc.get("indicator_value", "")),
            trigger_source=approval.trigger_type,
            alert_id=tc.get("alert_id"),
        )

        # Create WorkflowRun
        run_repo = WorkflowRunRepository(session)
        run = await run_repo.create(
            workflow_id=workflow.id,
            trigger_type=approval.trigger_type,
            trigger_context=tc,
            code_version_executed=workflow.code_version,
            status="queued",
        )
        approval.workflow_run_id = run.id
        await session.flush()

        run.started_at = datetime.now(UTC).isoformat()
        await session.flush()

        exec_result = await execute_workflow(workflow, trigger_ctx, session)

        if "timed out" in exec_result.result.message.lower():
            run_status = "timed_out"
        elif exec_result.result.success:
            run_status = "success"
        else:
            run_status = "failed"

        result_data = {
            "success": exec_result.result.success,
            "message": exec_result.result.message,
            "data": exec_result.result.data,
        }
        await run_repo.update_after_execution(
            run,
            status=run_status,
            log_output=exec_result.log_output,
            result_data=result_data,
            duration_ms=exec_result.duration_ms,
            completed_at=datetime.now(UTC).isoformat(),
        )

        approval.execution_result = result_data

        # Activity event: workflow_executed (via approval)
        try:
            activity_svc = ActivityEventService(session)
            await activity_svc.write(
                ActivityEventType.WORKFLOW_EXECUTED,
                actor_type="system",
                workflow_id=workflow.id,
                alert_id=tc.get("alert_id"),
                references={
                    "workflow_uuid": str(workflow.uuid),
                    "workflow_name": workflow.name,
                    "run_uuid": str(run.uuid),
                    "trigger_type": approval.trigger_type,
                    "status": run_status,
                    "duration_ms": exec_result.duration_ms,
                    "approval_uuid": str(approval.uuid),
                    "indicator_type": tc.get("indicator_type"),
                    "indicator_value": tc.get("indicator_value"),
                },
            )
        except Exception:
            pass

        # Commit before sending notification so DB state is persisted
        # even if notification fails. The shim's task_session() will
        # call commit again (no-op after explicit commit).
        await session.commit()

        # Send result notification (best-effort, errors logged by notifier)
        notifier = get_approval_notifier(settings)
        notif_request = ApprovalRequest(
            approval_uuid=approval.uuid,
            workflow_name=workflow.name,
            workflow_risk_level=workflow.risk_level,
            indicator_type=str(tc.get("indicator_type", "")),
            indicator_value=str(tc.get("indicator_value", "")),
            trigger_source=approval.trigger_type,
            reason=approval.reason,
            confidence=approval.confidence,
            expires_at=approval.expires_at,
            execution_result=result_data,
        )
        await notifier.send_result_notification(
            request=notif_request,
            approved=True,
            responder_id=approval.responder_id,
        )
