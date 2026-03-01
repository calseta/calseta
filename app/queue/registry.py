"""
Task registry — all procrastinate @procrastinate_app.task decorated functions.

This module owns the single module-level procrastinate.App instance
(`procrastinate_app`). The ProcrastinateBackend in app/queue/backends/postgres.py
imports and reuses this instance so that task registrations made here are
visible when tasks are enqueued.

This module is imported by:
  - app/worker.py            → ensures tasks are registered before worker starts
  - app/main.py (startup)    → ensures tasks are registered before API accepts requests
  - app/queue/backends/postgres.py → ProcrastinateBackend uses the shared app

Task naming:
  Always pass `name=` explicitly so the task lookup key is stable and does not
  depend on the Python function's qualified name.

Registered tasks:
  Wave 3: enrich_alert                    (queue: enrichment)
  Wave 4: execute_workflow_run            (queue: workflows)       ← added in Wave 4
  Wave 4: deliver_agent_webhook           (queue: dispatch)        ← added in Wave 4
  Wave 4: send_approval_notification_task (queue: dispatch)        ← added in Wave 4
  Wave 4: execute_approved_workflow_task  (queue: workflows)       ← added in Wave 4
"""

from __future__ import annotations

import procrastinate

from app.config import settings


def _to_pg_dsn(url: str) -> str:
    """Convert SQLAlchemy DSN to plain libpq DSN for procrastinate."""
    return url.replace("postgresql+asyncpg://", "postgresql://")


# ---------------------------------------------------------------------------
# Module-level procrastinate App — shared by all task registrations and
# ProcrastinateBackend. Tasks registered here are visible to the backend.
# ---------------------------------------------------------------------------
_connector = procrastinate.PsycopgConnector(conninfo=_to_pg_dsn(settings.DATABASE_URL))
procrastinate_app = procrastinate.App(connector=_connector)


# ---------------------------------------------------------------------------
# Wave 3: Alert enrichment task
# ---------------------------------------------------------------------------

@procrastinate_app.task(
    name="enrich_alert",
    queue="enrichment",
    retry=procrastinate.RetryStrategy(
        max_attempts=settings.QUEUE_MAX_RETRIES,
        wait=settings.QUEUE_RETRY_BACKOFF_SECONDS,
    ),
)
async def enrich_alert_task(alert_id: int) -> None:
    """
    Run the enrichment pipeline for all indicators of an alert.

    Idempotent: re-running after success updates last_seen on indicators and
    refreshes enrichment results; no duplicate records are created.
    """
    from app.cache.factory import get_cache_backend
    from app.db.session import AsyncSessionLocal
    from app.services.enrichment import EnrichmentService

    cache = get_cache_backend()
    async with AsyncSessionLocal() as session:
        try:
            service = EnrichmentService(session, cache)
            await service.enrich_alert(alert_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Wave 4: Workflow execution task
# ---------------------------------------------------------------------------


@procrastinate_app.task(
    name="execute_workflow_run",
    queue="workflows",
    retry=procrastinate.RetryStrategy(
        max_attempts=1,  # Workflow runs are not auto-retried — failures are recorded
        wait=0,
    ),
)
async def execute_workflow_run_task(workflow_run_id: int) -> None:
    """
    Execute a queued workflow run.

    Loads the WorkflowRun record by ID, calls execute_workflow() from the sandbox,
    and updates the run record with the result.

    Not idempotent by design — each call represents one execution attempt.
    The WorkflowRun's status is updated from 'queued' to 'success', 'failed',
    or 'timed_out' after execution completes.
    """
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.db.models.workflow import Workflow as WorkflowModel
    from app.db.session import AsyncSessionLocal
    from app.repositories.workflow_run_repository import WorkflowRunRepository
    from app.services.workflow_executor import execute_workflow
    from app.workflows.context import TriggerContext

    async with AsyncSessionLocal() as session:
        try:
            run_repo = WorkflowRunRepository(session)
            run = await run_repo.get_by_id(workflow_run_id)
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

            await run_repo.update_after_execution(
                run,
                status=run_status,
                log_output=exec_result.log_output,
                result_data={
                    "success": exec_result.result.success,
                    "message": exec_result.result.message,
                    "data": exec_result.result.data,
                },
                duration_ms=exec_result.duration_ms,
                completed_at=datetime.now(UTC).isoformat(),
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Wave 4: Approval notification task (dispatch queue)
# ---------------------------------------------------------------------------


@procrastinate_app.task(
    name="send_approval_notification_task",
    queue="dispatch",
    retry=procrastinate.RetryStrategy(
        max_attempts=3,
        wait=30,
    ),
)
async def send_approval_notification_task(approval_request_id: int) -> None:
    """
    Send the approval request notification via the configured notifier.

    Loads the WorkflowApprovalRequest by ID, builds ApprovalRequest, calls
    the configured notifier, and stores the external_message_id for thread replies.
    """
    from sqlalchemy import select

    from app.config import settings
    from app.db.models.workflow import Workflow as WorkflowModel
    from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR
    from app.db.session import AsyncSessionLocal
    from app.workflows.notifiers.base import ApprovalRequest
    from app.workflows.notifiers.factory import get_approval_notifier

    async with AsyncSessionLocal() as session:
        try:
            ar_result = await session.execute(
                select(WAR).where(WAR.id == approval_request_id)
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
            request = ApprovalRequest(
                approval_uuid=approval.uuid,
                workflow_name=workflow.name,
                workflow_risk_level=workflow.risk_level,
                indicator_type=str(tc.get("indicator_type", "")),
                indicator_value=str(tc.get("indicator_value", "")),
                trigger_source=approval.trigger_type,
                reason=approval.reason,
                confidence=approval.confidence,
                expires_at=approval.expires_at,
                approval_channel=approval.notifier_channel,
            )

            notifier = get_approval_notifier(settings)
            external_id = await notifier.send_approval_request(request)
            if external_id:
                approval.external_message_id = external_id
                await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Wave 4: Execute approved workflow task (workflows queue)
# ---------------------------------------------------------------------------


@procrastinate_app.task(
    name="execute_approved_workflow_task",
    queue="workflows",
    retry=procrastinate.RetryStrategy(
        max_attempts=1,
        wait=0,
    ),
)
async def execute_approved_workflow_task(approval_request_id: int) -> None:
    """
    Execute a workflow after approval.

    Creates a WorkflowRun from the approval request context and executes it.
    Updates the approval request with execution_result when done.
    """
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.config import settings
    from app.db.models.workflow import Workflow as WorkflowModel
    from app.db.models.workflow_approval_request import WorkflowApprovalRequest as WAR
    from app.db.session import AsyncSessionLocal
    from app.repositories.workflow_run_repository import WorkflowRunRepository
    from app.services.workflow_executor import execute_workflow
    from app.workflows.context import TriggerContext
    from app.workflows.notifiers.base import ApprovalRequest
    from app.workflows.notifiers.factory import get_approval_notifier

    async with AsyncSessionLocal() as session:
        try:
            ar_result = await session.execute(
                select(WAR).where(WAR.id == approval_request_id)
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

        except Exception:
            await session.rollback()
            raise
