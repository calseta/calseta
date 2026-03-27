# Task Queue -- Agent Navigation

## Architecture

- ABC: `base.py:TaskQueueBase` (enqueue, get_task_status, get_queue_metrics, start_worker)
- Default backend: `backends/postgres.py:ProcrastinateBackend` (reuses shared `procrastinate_app` from registry.py)
- Stub backends: `backends/celery_redis.py`, `backends/sqs.py`, `backends/azure_sb.py`
- Backend selection: `factory.py:get_queue_backend()` reads `QUEUE_BACKEND` env var
- DI: `dependencies.py:get_queue()` provides `TaskQueueBase` to route handlers via `Depends()`
- Worker entry: `app/worker.py` imports registry, loads enrichment providers, calls `backend.start_worker()`
- Session helper: `handlers/base.py:task_session()` async context manager (commit/rollback)

## All 7 Tasks

| Task Name | Queue | Payload | Retry | Idempotent | Chains To |
|-----------|-------|---------|-------|------------|-----------|
| enrich_alert | enrichment | `{alert_id: int}` | max_attempts from settings, backoff from settings | Yes | dispatch_agent_webhooks |
| execute_workflow_run | workflows | `{workflow_run_id: int}` | 1 attempt, no retry | No | -- |
| send_approval_notification_task | dispatch | `{approval_request_id: int}` | 3 attempts, 30s wait | Yes | -- |
| execute_approved_workflow_task | workflows | `{approval_request_id: int}` | 1 attempt, no retry | No | -- |
| dispatch_agent_webhooks | dispatch | `{alert_id: int}` | 3 attempts, 30s wait | Yes | -- |
| dispatch_single_agent_webhook | dispatch | `{alert_id: int, agent_id: int}` | 1 attempt, no retry | Yes | -- |
| sandbox_reset | default | `{timestamp: int}` | none (periodic) | Yes | -- |

## Pipelines

### Alert Enrichment Chain
- Entry: `enrich_alert` task enqueued by `AlertIngestionService.ingest()` (API process)
- Flow: enrich_alert -> IndicatorExtractionService.extract_and_persist() -> EnrichmentService.enrich_alert() -> defers `dispatch_agent_webhooks` via `procrastinate_app.tasks.get()`
- Session pattern: `AsyncSessionLocal()` opened in task body, manual commit/rollback
- Key seam: dispatch deferral uses `procrastinate_app.tasks.get("dispatch_agent_webhooks")` directly (not `queue.enqueue()`) because worker is already inside procrastinate's `open_async()` context
- To debug: If enrichment runs but agents are not notified, check the dispatch deferral try/except at the end of `enrich_alert_task`

### Workflow Execution (direct + approved)
- Direct: `execute_workflow_run` loaded from WorkflowRun record, calls `execute_workflow()`, updates run status
- Approved: `execute_approved_workflow_task` creates a WorkflowRun from approval context, executes, updates both run and approval records, sends result notification via notifier
- Both write `workflow_executed` activity event after execution

### Agent Dispatch
- Batch: `dispatch_agent_webhooks` evaluates trigger criteria via `get_matching_agents()`, builds webhook payload, dispatches to each matching agent with per-agent error isolation
- Single: `dispatch_single_agent_webhook` bypasses trigger matching, dispatches to one specific agent

## Session Management Pattern
Every task opens its own `AsyncSessionLocal()` and wraps in try/commit/except/rollback. The `handlers/base.py:task_session()` context manager extracts this pattern but registry.py tasks still use inline sessions. All imports are deferred (inside function body) to avoid procrastinate serialization issues.

## How to Add a Task
1. Define the task function in `registry.py` with `@procrastinate_app.task(name=..., queue=..., retry=...)`
2. Use `AsyncSessionLocal()` for DB access (deferred import inside function body)
3. Payload is passed as keyword arguments to the task function
4. Register the task name in the docstring at the top of `registry.py`
5. Enqueue from services/routes via `queue.enqueue("task_name", payload, queue="...")`
6. Four named queues: `enrichment`, `dispatch`, `workflows`, `default`
