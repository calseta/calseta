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
  Wave 5: dispatch_agent_webhooks         (queue: dispatch)        ← added in Wave 5
  dispatch_single_agent_webhook            (queue: dispatch)        ← manual single-agent dispatch
  Wave 9: sandbox_reset                   (queue: default, periodic) ← conditional on SANDBOX_MODE
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
    Run indicator extraction + enrichment pipeline for an alert.

    Steps:
      1. Load the alert and its source plugin
      2. Extract indicators via 3-pass pipeline (IndicatorExtractionService)
      3. Enrich all extracted indicators via configured providers
      4. Defer agent dispatch task (best-effort)

    Idempotent: re-running after success updates last_seen on indicators and
    refreshes enrichment results; no duplicate records are created.
    """
    import structlog as _structlog

    from app.cache.factory import get_cache_backend
    from app.db.session import AsyncSessionLocal
    from app.integrations.sources.registry import source_registry
    from app.repositories.alert_repository import AlertRepository
    from app.services.enrichment import EnrichmentService
    from app.services.indicator_extraction import IndicatorExtractionService

    _logger = _structlog.get_logger()
    cache = get_cache_backend()

    async with AsyncSessionLocal() as session:
        try:
            alert_repo = AlertRepository(session)
            alert = await alert_repo.get_by_id(alert_id)
            if alert is None:
                _logger.error("enrich_alert_not_found", alert_id=alert_id)
                return

            # Step 1: Extract indicators (3-pass pipeline)
            source = source_registry.get(alert.source_name)
            if source is not None and alert.raw_payload:
                try:
                    normalized = source.normalize(alert.raw_payload)
                    extraction_svc = IndicatorExtractionService(session)
                    count = await extraction_svc.extract_and_persist(
                        alert, normalized, alert.raw_payload, source
                    )
                    _logger.info(
                        "indicators_extracted",
                        alert_id=alert_id,
                        indicator_count=count,
                    )
                except Exception:
                    _logger.exception(
                        "indicator_extraction_failed", alert_id=alert_id
                    )
                await session.flush()

            # Step 2: Enrich all indicators
            enrichment_svc = EnrichmentService(session, cache)
            await enrichment_svc.enrich_alert(alert_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    # Defer agent dispatch after successful enrichment (best-effort).
    # Use the procrastinate task's configure().defer_async() directly — we're already
    # inside the worker's open_async() context, so calling queue.enqueue() (which
    # opens a new context) would cause AppNotOpen.
    try:
        dispatch_task = procrastinate_app.tasks.get("dispatch_agent_webhooks")
        if dispatch_task is not None:
            await dispatch_task.defer_async(alert_id=alert_id)
    except Exception:
        _structlog.get_logger().warning(
            "dispatch_enqueue_failed", alert_id=alert_id
        )


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


# ---------------------------------------------------------------------------
# Wave 5: Agent webhook dispatch task (dispatch queue)
# ---------------------------------------------------------------------------


@procrastinate_app.task(
    name="dispatch_agent_webhooks",
    queue="dispatch",
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=30),
)
async def dispatch_agent_webhooks_task(alert_id: int) -> None:
    """
    Evaluate trigger criteria and dispatch alert to all matching agents.

    Enqueued after enrichment completes for each alert.
    Idempotent: re-dispatching sends the webhook again (operators can
    use POST /v1/alerts/{uuid}/trigger-agents to re-trigger manually).
    """
    import structlog as _structlog

    from app.db.session import AsyncSessionLocal
    from app.repositories.alert_repository import AlertRepository
    from app.services.agent_dispatch import build_webhook_payload, dispatch_to_agent
    from app.services.agent_trigger import get_matching_agents

    _logger = _structlog.get_logger()

    async with AsyncSessionLocal() as session:
        try:
            alert_repo = AlertRepository(session)
            alert = await alert_repo.get_by_id(alert_id)
            if alert is None:
                return  # Alert deleted before task ran

            agents = await get_matching_agents(alert, session)
            if not agents:
                return

            payload = await build_webhook_payload(alert_id, session)

            for agent in agents:
                try:
                    await dispatch_to_agent(agent, alert_id, payload, session)
                    await session.commit()
                except Exception:
                    await session.rollback()
                    _logger.exception(
                        "agent_dispatch_failed",
                        agent_uuid=str(agent.uuid),
                        alert_id=alert_id,
                    )

        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Dispatch single agent webhook (dispatch queue)
# ---------------------------------------------------------------------------


@procrastinate_app.task(
    name="dispatch_single_agent_webhook",
    queue="dispatch",
    retry=procrastinate.RetryStrategy(max_attempts=1, wait=0),
)
async def dispatch_single_agent_webhook_task(alert_id: int, agent_id: int) -> None:
    """
    Dispatch an alert to a single specific agent (bypasses trigger matching).

    Enqueued by POST /v1/alerts/{uuid}/dispatch-agent for manual agent runs.
    """
    import structlog as _structlog

    from app.db.session import AsyncSessionLocal
    from app.services.agent_dispatch import build_webhook_payload, dispatch_to_agent

    _logger = _structlog.get_logger()

    async with AsyncSessionLocal() as session:
        try:
            from app.db.models.agent_registration import AgentRegistration
            from sqlalchemy import select

            agent_result = await session.execute(
                select(AgentRegistration).where(AgentRegistration.id == agent_id)
            )
            agent = agent_result.scalar_one_or_none()
            if agent is None:
                _logger.warning("dispatch_single_agent_not_found", agent_id=agent_id)
                return

            payload = await build_webhook_payload(alert_id, session)
            if not payload:
                _logger.warning("dispatch_single_alert_not_found", alert_id=alert_id)
                return

            await dispatch_to_agent(agent, alert_id, payload, session)
            await session.commit()
        except Exception:
            await session.rollback()
            _logger.exception(
                "dispatch_single_agent_failed",
                agent_id=agent_id,
                alert_id=alert_id,
            )
            raise


# ---------------------------------------------------------------------------
# Wave 9: Sandbox auto-reset (periodic, only when SANDBOX_MODE=true)
# ---------------------------------------------------------------------------

if settings.SANDBOX_MODE:

    @procrastinate_app.periodic(cron="0 0 * * *")
    @procrastinate_app.task(name="sandbox_reset", queue="default")
    async def sandbox_reset_task(timestamp: int) -> None:
        """
        Reset the sandbox database daily at midnight UTC.

        Deletes transient data, user-created config, and re-seeds fixtures.
        Only registered when SANDBOX_MODE=true.
        """
        import structlog as _structlog

        from app.tasks.sandbox_reset import reset_sandbox

        _logger = _structlog.get_logger()
        _logger.info("sandbox_reset_task_triggered", timestamp=timestamp)
        counts = await reset_sandbox()
        _logger.info("sandbox_reset_task_complete", deleted_counts=counts)
