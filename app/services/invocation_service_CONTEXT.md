# Invocation Service — CONTEXT.md

## What this component does

`InvocationService` implements multi-agent delegation for the Calseta agent control plane. Orchestrator agents use it to delegate focused sub-tasks to specialist agents. It creates `agent_invocations` rows, enqueues execution via procrastinate, tracks cost rollup, and marks timed-out invocations.

This component is deterministic — no LLM tokens consumed. It creates records and enqueues tasks; execution happens in `ExecuteInvocationHandler`.

## Interfaces

### Inputs
- `orchestrator: AgentRegistration` — must have `agent_type == 'orchestrator'`
- `DelegateTaskRequest` — single delegation (alert_id, child_agent_id, task_description, optional input_context/output_schema/timeout_seconds/assignment_id)
- `DelegateParallelRequest` — 2–10 tasks, all validated before any row is created
- `AgentInvocation` — passed directly to `mark_timed_out()` by the supervisor

### Outputs
- `DelegateTaskResponse` — `{invocation_id, status, child_agent_id}`
- `list[DelegateTaskResponse]` — one per parallel task
- `list[AgentCatalogEntry]` — active specialists from `get_catalog()`

### Contracts callers must uphold
- Caller must commit the session after `delegate_task()` / `delegate_parallel()` — the service flushes but never commits
- `mark_timed_out()` is idempotent — safe to call multiple times on the same invocation
- `_enqueue_invocation()` failure is non-fatal; invocation stays in `queued` for retry

## Key design decisions

**All-or-nothing parallel creation**: In `delegate_parallel()`, all specialist agents are resolved and validated _before_ any rows are inserted. If any specialist is missing or inactive, the entire batch fails with no DB side effects.

**Procrastinate task ID stored on invocation**: After enqueue, the job ID is written to `task_queue_id` so operators can correlate DB records with procrastinate job history.

**Cost rollup is additive**: `add_cost()` increments both `invocation.cost_cents` and `parent.spent_monthly_cents`. Called by the execution handler when the child agent reports costs.

**Catalog returns specialist + resolver agent types**: Both `specialist` and `resolver` types are included. Orchestrators should filter by `capabilities` for more precise selection.

## Extension pattern

To add a new execution strategy for a specialist (e.g., direct SDK call instead of webhook):

1. Add a branch in `execute_invocation.py:_call_webhook_specialist` or add a new `_call_*` function
2. The dispatch is determined by `child_agent.execution_mode` and `child_agent.adapter_type`
3. Current strategies: `external + endpoint_url → webhook`, `managed → enqueue run_managed_agent_task`

To add new catalog filters (e.g., filter by capability key):
1. Extend `InvocationService.get_catalog()` — add additional WHERE clauses to the query
2. Add optional query params to `GET /v1/agents/catalog` in `agents.py`

## Common failure modes

**"No active orchestrator agent found"** — The MCP tool can't resolve an orchestrator from context. Ensure at least one `agent_type='orchestrator'` + `status='active'` agent exists.

**Invocation stuck in `queued`** — The procrastinate worker may not be running, or the `invocations` queue isn't being consumed. Check worker logs and that `QUEUE_BACKEND=postgres` is set.

**`timed_out` invocations accumulating** — The `supervise_running_agents_task` periodic cron is not running (every 1 minute). Verify the worker process is consuming the `agents` queue.

**Specialist endpoint returns non-2xx** — `ExecuteInvocationHandler` records status=`failed` with `error=HTTP {code}: ...`. Check child agent logs.

## Test coverage

- `tests/unit/services/test_invocation_service.py` — delegate_task validation, parallel 2–10 constraint, orchestrator enforcement, cost rollup
- `tests/unit/api/test_invocations.py` — REST endpoint happy paths and error cases
- `tests/integration/test_invocations_integration.py` — full create → enqueue → complete lifecycle against real DB
