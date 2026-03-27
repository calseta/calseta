"""Handler for the execute_workflow_run task."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.workflow import Workflow as WorkflowModel
from app.queue.handlers.payloads import ExecuteWorkflowRunPayload
from app.repositories.workflow_run_repository import WorkflowRunRepository
from app.schemas.activity_events import ActivityEventType
from app.services.activity_event import ActivityEventService
from app.services.workflow_executor import execute_workflow
from app.workflows.context import TriggerContext


class ExecuteWorkflowHandler:
    """Execute a queued workflow run.

    Loads the WorkflowRun record by ID, calls execute_workflow() from the sandbox,
    and updates the run record with the result.

    Not idempotent by design — each call represents one execution attempt.
    The WorkflowRun's status is updated from 'queued' to 'success', 'failed',
    or 'timed_out' after execution completes.
    """

    async def execute(
        self, payload: ExecuteWorkflowRunPayload, session: AsyncSession
    ) -> None:
        run_repo = WorkflowRunRepository(session)
        run = await run_repo.get_by_id(payload.workflow_run_id)
        if run is None:
            return  # Run was deleted before task was processed

        wf_result = await session.execute(
            select(WorkflowModel).where(WorkflowModel.id == run.workflow_id)
        )
        workflow = wf_result.scalar_one_or_none()
        if workflow is None:
            return

        # Build TriggerContext from stored trigger_context JSON
        tc = run.trigger_context or {}
        trigger_ctx = TriggerContext(
            indicator_type=str(tc.get("indicator_type", "")),
            indicator_value=str(tc.get("indicator_value", "")),
            trigger_source=run.trigger_type,
            alert_id=tc.get("alert_id"),
        )

        run.started_at = datetime.now(UTC).isoformat()
        await session.flush()

        exec_result = await execute_workflow(workflow, trigger_ctx, session)

        # Determine status
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

        # Activity event: workflow_executed
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
                    "trigger_type": run.trigger_type,
                    "status": run_status,
                    "duration_ms": exec_result.duration_ms,
                    "indicator_type": tc.get("indicator_type"),
                    "indicator_value": tc.get("indicator_value"),
                },
            )
        except Exception:
            pass  # ActivityEventService.write already swallows errors
