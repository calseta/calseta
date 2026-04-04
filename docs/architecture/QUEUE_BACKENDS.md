# Queue Backends

Calseta uses an abstract task queue interface (`TaskQueueBase`) backed by
procrastinate + PostgreSQL by default.

## Switching Backends

Set the `QUEUE_BACKEND` environment variable:

| Value | Backend | Status |
|---|---|---|
| `postgres` | procrastinate + PostgreSQL | ✅ Implemented (default) |
| `celery_redis` | Celery + Redis | 🚧 Stub — not implemented |
| `sqs` | AWS SQS | 🚧 Stub — not implemented |
| `azure_service_bus` | Azure Service Bus | 🚧 Stub — not implemented |

## Implementing an Alternative Backend

TODO: Document the steps to implement a new `TaskQueueBase` subclass
and wire it into `app/queue/factory.py`.

---

## Task Types by Queue

### `enrichment` queue
- `enrich_alert_task` — runs the full enrichment pipeline for a newly ingested alert
- `enrich_indicator_on_demand_task` — single-indicator enrichment triggered via API

### `dispatch` queue
- `evaluate_alert_triggers_task` — evaluates agent registration trigger filters after ingest
- `deliver_agent_webhook_task` — HTTP delivery of alert payload to a registered agent endpoint

### `workflows` queue
- `execute_workflow_run_task` — executes an active workflow's `run()` function in the sandbox; writes `WorkflowRun` result row
- `execute_response_action_task` — **NEW (Phase 2/3)**: executes an approved `AgentAction` via the action integration registry; calls `get_integration_for_action(action.action_subtype)` and then `integration.execute(action)`; writes result and activity events

Both `workflows` queue task types are idempotent. If `execute_response_action_task` is retried after a transient failure, the action record is checked — if status is already `executed` or `failed`, the task exits immediately without re-calling the integration.
