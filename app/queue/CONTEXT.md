# Task Queue Abstraction

## What This Component Does

The task queue abstraction provides a durable, asynchronous job execution layer backed by PostgreSQL via procrastinate. All async operations (alert enrichment, agent webhook dispatch, workflow execution, approval notifications) are enqueued before the originating HTTP request returns, ensuring the API responds within 200ms while heavy work runs in the worker process. The abstraction layer (`TaskQueueBase`) allows future backend swaps (Celery/Redis, SQS, Azure Service Bus) without changing any service or route code.

## Interfaces

### TaskQueueBase (`base.py`)

Abstract base class. The only interface imported by services and routes:

```python
class TaskQueueBase(ABC):
    async def enqueue(
        self,
        task_name: str,              # registered task name, e.g. "enrich_alert"
        payload: dict[str, object],  # kwargs passed to the task function
        *,
        queue: str,                  # "enrichment", "dispatch", "workflows", "default"
        delay_seconds: int = 0,      # deferred execution
        priority: int = 0,           # higher = run first (backend support varies)
    ) -> str:                        # returns task ID string

    async def get_task_status(self, task_id: str) -> TaskStatus: ...

    async def start_worker(self, queues: list[str]) -> None:
        # Blocks until worker exits. Called from worker.py.
```

### TaskStatus (`base.py`)

```python
class TaskStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
```

### Queue Names

| Queue | Tasks | Purpose |
|---|---|---|
| `enrichment` | `enrich_alert` | Indicator extraction + provider enrichment pipeline |
| `dispatch` | `dispatch_agent_webhooks`, `send_approval_notification_task` | Agent webhook delivery + approval notifications |
| `workflows` | `execute_workflow_run`, `execute_approved_workflow_task` | Workflow sandbox execution |

### Factory (`factory.py`)

```python
def get_queue_backend() -> TaskQueueBase
```

Reads `QUEUE_BACKEND` env var. Valid values: `postgres` (default), `celery_redis`, `sqs`, `azure_service_bus`. Non-postgres backends are stubs that raise `NotImplementedError`.

### Dependency (`dependencies.py`)

FastAPI dependency for route handlers:

```python
def get_queue() -> TaskQueueBase  # lru_cache(maxsize=1) singleton
```

Usage in routes:
```python
@router.post("/items")
async def create_item(queue: Annotated[TaskQueueBase, Depends(get_queue)]) -> ...:
    await queue.enqueue("my_task", {"id": 42}, queue="default")
```

### Task Registry (`registry.py`)

Owns the module-level `procrastinate.App` instance. All tasks are decorated with `@procrastinate_app.task(name=..., queue=...)` here. The `ProcrastinateBackend` imports and reuses this same app instance so task registrations are visible when enqueueing.

Registered tasks:

```python
@procrastinate_app.task(name="enrich_alert", queue="enrichment", retry=max_attempts=3)
async def enrich_alert_task(alert_id: int) -> None: ...

@procrastinate_app.task(name="execute_workflow_run", queue="workflows", retry=max_attempts=1)
async def execute_workflow_run_task(workflow_run_id: int) -> None: ...

@procrastinate_app.task(name="send_approval_notification_task", queue="dispatch", retry=max_attempts=3)
async def send_approval_notification_task(approval_request_id: int) -> None: ...

@procrastinate_app.task(name="execute_approved_workflow_task", queue="workflows", retry=max_attempts=1)
async def execute_approved_workflow_task(approval_request_id: int) -> None: ...

@procrastinate_app.task(name="dispatch_agent_webhooks", queue="dispatch", retry=max_attempts=3)
async def dispatch_agent_webhooks_task(alert_id: int) -> None: ...
```

### Import Topology

```
registry.py  ← owns procrastinate_app + all @task functions
    ↑
backends/postgres.py  ← imports procrastinate_app from registry
    ↑
factory.py  ← instantiates ProcrastinateBackend
    ↑
dependencies.py  ← FastAPI Depends(get_queue)
    ↑
routes / services  ← call queue.enqueue()
```

`registry.py` is imported by `app/worker.py` (startup) and `app/main.py` (startup) to ensure tasks are registered before any enqueue call.

## Key Design Decisions

1. **Procrastinate + PostgreSQL as default backend, not Celery + Redis.** Eliminates Redis as an external dependency. Procrastinate stores jobs in `procrastinate_jobs` table using PostgreSQL's `LISTEN/NOTIFY` for worker wake-up. For a single-tenant, self-hosted platform, one fewer infrastructure component (Redis) significantly simplifies deployment.

2. **Dual PostgreSQL drivers by design.** SQLAlchemy uses `asyncpg` (`postgresql+asyncpg://`). Procrastinate v3 uses `psycopg` (`PsycopgConnector`). Both connect to the same PostgreSQL instance via different drivers. The `_to_pg_dsn()` helper strips `+asyncpg` from the DATABASE_URL for procrastinate. This is intentional, not a bug.

3. **Shared `procrastinate.App` instance.** `registry.py` creates the single `procrastinate_app`. `ProcrastinateBackend` imports and reuses it rather than creating its own `App`. This ensures tasks registered with `@procrastinate_app.task` are visible when `backend.enqueue()` looks them up via `app.tasks.get(name)`.

4. **Task names are explicit strings, not derived from function paths.** Every `@procrastinate_app.task` passes `name=` explicitly (e.g. `name="enrich_alert"`). This decouples the task lookup key from the Python module path, making refactors safe and task routing predictable.

5. **Workflow tasks have max_attempts=1 (no auto-retry).** Workflow execution failures are recorded in `workflow_runs` as `failed` or `timed_out`. Auto-retrying could cause unintended side effects (e.g. suspending a user twice). The enrichment and dispatch tasks retry up to 3 times because they are idempotent.

6. **Each `enqueue()` call opens/closes a procrastinate pool.** The `async with self.app.open_async()` context manager in `ProcrastinateBackend.enqueue()` opens a fresh connection pool per call. This is simple but suboptimal for high-volume. For production, wire `open_async()` into FastAPI lifespan to reuse the pool (deferred optimization).

## Extension Pattern: Implementing a New Backend (e.g. Celery + Redis)

1. **Implement in `app/queue/backends/celery_redis.py`** (currently a stub):
   ```python
   class CeleryRedisBackend(TaskQueueBase):
       def __init__(self):
           from celery import Celery
           self.celery_app = Celery(broker="redis://...")

       async def enqueue(self, task_name, payload, *, queue, delay_seconds=0, priority=0) -> str:
           result = self.celery_app.send_task(task_name, kwargs=payload, queue=queue)
           return result.id

       async def get_task_status(self, task_id) -> TaskStatus:
           result = AsyncResult(task_id)
           # Map Celery states to TaskStatus
           ...

       async def start_worker(self, queues) -> None:
           # Start Celery worker consuming from queues
           ...
   ```

2. **Set env var**: `QUEUE_BACKEND=celery_redis`

3. **Register task handlers** in a Celery-compatible format (the `registry.py` tasks are procrastinate-specific; a Celery backend would need its own task registration or an adapter layer).

## Idempotency Requirements

All task handlers must be idempotent -- safe to execute more than once:

- **`enrich_alert`**: Re-running updates `last_seen` on indicators and refreshes enrichment results; no duplicate indicator records (upsert by `(type, value)`).
- **`dispatch_agent_webhooks`**: Re-dispatching sends the webhook again. Agents must handle duplicate deliveries.
- **`execute_workflow_run`**: NOT idempotent by design. Each call represents one execution attempt. The `workflow_runs` status guards against re-execution.
- **`execute_approved_workflow_task`**: Creates a new `WorkflowRun` on each invocation. The approval request's `status` field prevents re-processing an already-decided request.

## Common Failure Modes

| Symptom | Cause | Diagnosis |
|---|---|---|
| "Task 'xxx' is not registered" | `registry.py` not imported at startup | Ensure `import app.queue.registry` in `app/main.py` and `app/worker.py` |
| `AppNotOpen` error in worker | Calling `queue.enqueue()` inside a task handler | Inside worker tasks, use `procrastinate_app.tasks.get(name).defer_async()` directly instead of `queue.enqueue()` (see `enrich_alert_task` for the pattern) |
| Tasks enqueued but never executed | Worker not running or not listening on correct queues | Check worker process is started with correct queue list; check `procrastinate_jobs` table for `todo` status rows |
| DSN format error | `DATABASE_URL` has `+asyncpg` prefix that procrastinate cannot parse | `_to_pg_dsn()` should strip it; check if DATABASE_URL format changed |
| Unknown `QUEUE_BACKEND` value | Typo in env var | Factory raises `ValueError` with the list of valid values |

## Test Coverage

| Test file | Scenarios |
|---|---|
| `tests/integration/test_ingest.py` | Verifies enrichment task is enqueued after alert ingestion (mock queue) |
| `tests/integration/test_workflows.py` | Verifies workflow execution task is enqueued on execute endpoint |
| `tests/integration/test_workflow_approvals.py` | Verifies approval notification task is enqueued; approved workflow task is enqueued after decision |
| `tests/integration/test_agents.py` | Agent webhook dispatch task enqueuing |
| `tests/conftest.py` | Provides mock `TaskQueueBase` implementation (`MockQueue`) for all integration tests |
