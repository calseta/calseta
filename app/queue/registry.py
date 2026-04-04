"""Task registry — procrastinate task shims delegating to handler classes.

Each task is a thin shim: parse payload, open session, delegate to handler.
Business logic lives in ``app/queue/handlers/``.
"""

from __future__ import annotations

import procrastinate

from app.config import settings


def _to_pg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


_connector = procrastinate.PsycopgConnector(conninfo=_to_pg_dsn(settings.DATABASE_URL))
procrastinate_app = procrastinate.App(connector=_connector)


@procrastinate_app.task(
    name="enrich_alert",
    queue="enrichment",
    retry=procrastinate.RetryStrategy(
        max_attempts=settings.QUEUE_MAX_RETRIES,
        wait=settings.QUEUE_RETRY_BACKOFF_SECONDS,
    ),
)
async def enrich_alert_task(alert_id: int) -> None:
    from app.queue.handlers.base import task_session
    from app.queue.handlers.enrich_alert import EnrichAlertHandler
    from app.queue.handlers.payloads import EnrichAlertPayload

    payload = EnrichAlertPayload(alert_id=alert_id)
    async with task_session() as session:
        await EnrichAlertHandler().execute(payload, session)

    # Defer dispatch (best-effort). Must use procrastinate_app directly —
    # queue.enqueue() would cause AppNotOpen inside the worker context.
    try:
        dispatch_task = procrastinate_app.tasks.get("dispatch_agent_webhooks")
        if dispatch_task is not None:
            await dispatch_task.defer_async(alert_id=alert_id)
    except Exception:
        import structlog
        structlog.get_logger().warning("dispatch_enqueue_failed", alert_id=alert_id)


@procrastinate_app.task(
    name="execute_workflow_run",
    queue="workflows",
    retry=procrastinate.RetryStrategy(max_attempts=1, wait=0),
)
async def execute_workflow_run_task(workflow_run_id: int) -> None:
    from app.queue.handlers.base import task_session
    from app.queue.handlers.execute_workflow import ExecuteWorkflowHandler
    from app.queue.handlers.payloads import ExecuteWorkflowRunPayload

    payload = ExecuteWorkflowRunPayload(workflow_run_id=workflow_run_id)
    async with task_session() as session:
        await ExecuteWorkflowHandler().execute(payload, session)


@procrastinate_app.task(
    name="send_approval_notification_task",
    queue="dispatch",
    retry=procrastinate.RetryStrategy(
        max_attempts=3,
        wait=30,
    ),
)
async def send_approval_notification_task(approval_request_id: int) -> None:
    from app.queue.handlers.approval_notification import ApprovalNotificationHandler
    from app.queue.handlers.base import task_session
    from app.queue.handlers.payloads import SendApprovalNotificationPayload

    payload = SendApprovalNotificationPayload(
        approval_request_id=approval_request_id
    )
    async with task_session() as session:
        await ApprovalNotificationHandler().execute(payload, session)


@procrastinate_app.task(
    name="execute_approved_workflow_task",
    queue="workflows",
    retry=procrastinate.RetryStrategy(
        max_attempts=1,
        wait=0,
    ),
)
async def execute_approved_workflow_task(approval_request_id: int) -> None:
    from app.queue.handlers.base import task_session
    from app.queue.handlers.execute_approved import ExecuteApprovedWorkflowHandler
    from app.queue.handlers.payloads import ExecuteApprovedWorkflowPayload

    payload = ExecuteApprovedWorkflowPayload(
        approval_request_id=approval_request_id
    )
    async with task_session() as session:
        await ExecuteApprovedWorkflowHandler().execute(payload, session)


@procrastinate_app.task(
    name="execute_response_action_task",
    queue="workflows",
    retry=procrastinate.RetryStrategy(max_attempts=1, wait=0),
)
async def execute_response_action_task(agent_action_id: int) -> None:
    from app.queue.handlers.base import task_session
    from app.queue.handlers.execute_action import ExecuteResponseActionHandler
    from app.queue.handlers.payloads import ExecuteResponseActionPayload

    payload = ExecuteResponseActionPayload(agent_action_id=agent_action_id)
    async with task_session() as session:
        await ExecuteResponseActionHandler().execute(payload, session)


@procrastinate_app.task(
    name="dispatch_agent_webhooks",
    queue="dispatch",
    retry=procrastinate.RetryStrategy(max_attempts=3, wait=30),
)
async def dispatch_agent_webhooks_task(alert_id: int) -> None:
    from app.queue.handlers.base import task_session
    from app.queue.handlers.dispatch_webhooks import DispatchWebhooksHandler
    from app.queue.handlers.payloads import DispatchAgentWebhooksPayload

    payload = DispatchAgentWebhooksPayload(alert_id=alert_id)
    async with task_session() as session:
        await DispatchWebhooksHandler().execute(payload, session)


@procrastinate_app.task(
    name="dispatch_single_agent_webhook",
    queue="dispatch",
    retry=procrastinate.RetryStrategy(max_attempts=1, wait=0),
)
async def dispatch_single_agent_webhook_task(
    alert_id: int, agent_id: int
) -> None:
    from app.queue.handlers.base import task_session
    from app.queue.handlers.dispatch_webhooks import DispatchSingleWebhookHandler
    from app.queue.handlers.payloads import DispatchSingleAgentWebhookPayload

    payload = DispatchSingleAgentWebhookPayload(
        alert_id=alert_id, agent_id=agent_id
    )
    async with task_session() as session:
        await DispatchSingleWebhookHandler().execute(payload, session)


@procrastinate_app.task(
    name="run_managed_agent_task",
    queue="agents",
    retry=procrastinate.RetryStrategy(max_attempts=1),
)
async def run_managed_agent_task(
    agent_registration_id: int,
    assignment_id: int,
    heartbeat_run_id: int,
) -> None:
    """Execute a managed agent for a single alert assignment."""
    from datetime import UTC, datetime

    import structlog

    from app.queue.handlers.base import task_session
    from app.repositories.agent_repository import AgentRepository
    from app.repositories.alert_assignment_repository import AlertAssignmentRepository
    from app.repositories.heartbeat_run_repository import HeartbeatRunRepository
    from app.runtime.engine import AgentRuntimeEngine
    from app.runtime.models import RuntimeContext

    log = structlog.get_logger()
    log.info(
        "run_managed_agent_task.started",
        agent_registration_id=agent_registration_id,
        assignment_id=assignment_id,
        heartbeat_run_id=heartbeat_run_id,
    )

    async with task_session() as db:
        # Load agent
        agent_repo = AgentRepository(db)
        agent = await agent_repo.get_by_id(agent_registration_id)
        if agent is None or agent.execution_mode != "managed":
            log.warning(
                "run_managed_agent_task.agent_not_found_or_not_managed",
                agent_registration_id=agent_registration_id,
            )
            return

        # Load assignment
        assignment_repo = AlertAssignmentRepository(db)
        assignment = await assignment_repo.get_by_id(assignment_id)
        if assignment is None:
            log.warning(
                "run_managed_agent_task.assignment_not_found",
                assignment_id=assignment_id,
            )
            return

        context = RuntimeContext(
            agent_id=agent.id,
            task_key=f"alert:{assignment.alert_id}",
            heartbeat_run_id=heartbeat_run_id,
            alert_id=assignment.alert_id,
            assignment_id=assignment.id,
        )

        engine = AgentRuntimeEngine(db=db)
        result = await engine.run(agent=agent, context=context)

        # Update heartbeat run status
        hr_repo = HeartbeatRunRepository(db)
        run = await hr_repo.get_by_id(heartbeat_run_id)
        if run is not None:
            run_status = "succeeded" if result.success else "failed"
            await hr_repo.update_status(
                run,
                run_status,
                finished_at=datetime.now(UTC),
                error=result.error,
                alerts_processed=1 if result.success else 0,
                actions_proposed=len(result.actions_proposed),
            )

        log.info(
            "run_managed_agent_task.completed",
            success=result.success,
            total_cost_cents=result.total_cost_cents,
            agent_registration_id=agent_registration_id,
        )


@procrastinate_app.periodic(cron="*/1 * * * *")
@procrastinate_app.task(name="supervise_running_agents_task", queue="agents")
async def supervise_running_agents_task(timestamp: int) -> None:
    """Periodic supervision — runs every minute to detect stuck/timed-out agents."""
    from app.queue.handlers.base import task_session
    from app.runtime.supervisor import AgentSupervisor

    async with task_session() as db:
        supervisor = AgentSupervisor(db)
        await supervisor.supervise()


if settings.SANDBOX_MODE:

    @procrastinate_app.periodic(cron="0 0 * * *")
    @procrastinate_app.task(name="sandbox_reset", queue="default")
    async def sandbox_reset_task(timestamp: int) -> None:
        from app.queue.handlers.payloads import SandboxResetPayload
        from app.queue.handlers.sandbox_reset import SandboxResetHandler

        payload = SandboxResetPayload(timestamp=timestamp)
        await SandboxResetHandler().execute(payload)
