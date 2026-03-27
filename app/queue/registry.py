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


if settings.SANDBOX_MODE:

    @procrastinate_app.periodic(cron="0 0 * * *")
    @procrastinate_app.task(name="sandbox_reset", queue="default")
    async def sandbox_reset_task(timestamp: int) -> None:
        from app.queue.handlers.payloads import SandboxResetPayload
        from app.queue.handlers.sandbox_reset import SandboxResetHandler

        payload = SandboxResetPayload(timestamp=timestamp)
        await SandboxResetHandler().execute(payload)
