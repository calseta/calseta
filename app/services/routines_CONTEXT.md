# Routines Service — CONTEXT.md

## What this component does
Manages `agent_routines` lifecycle: creation, trigger management (cron/webhook/manual), invocation, and run tracking. Routines are recurring work patterns — agents run on schedules, webhook events, or manual invocation. Each execution produces a `RoutineRun` audit record.

## Interfaces
- REST: `POST/GET/PATCH/DELETE /v1/routines` + sub-routes for triggers, runs
- Webhook: `POST /v1/routines/{id}/triggers/{tid}/webhook` — HMAC-verified external trigger, no API key required
- Queue: `routine_runs` are created and advanced to `enqueued` status; actual agent wakeup is Phase 6+

## Key design decisions
- Cron trigger scheduling is evaluated by the procrastinate periodic task `evaluate_routine_triggers_task` (in registry.py) every 30 seconds — not implemented in this component
- `webhook_secret_hash` stores the raw signing secret (not a bcrypt hash) — the field name is legacy. HMAC verification uses `sha256=<hex>` format with message `"{timestamp}." + body`
- Concurrency policies (`skip_if_active`, `coalesce_if_active`, `always_run`) are enforced during cron evaluation, not at trigger creation time
- `routine_runs` uses `AppendOnlyTimestampMixin` — no `updated_at` since runs are write-once status records
- Manual invocation finds or creates a single manual trigger per routine — no duplicate manual triggers are created
- Webhook endpoints have no auth scope guard; HMAC signature is the only authentication. If no secret is configured, the signature check is skipped entirely

## Extension pattern
To add a new trigger kind:
1. Add the constant to `TriggerKind` in `app/schemas/routines.py`
2. Add validation in `RoutineService._create_trigger_for_routine()` in `app/services/routine_service.py`
3. Handle the new kind in the periodic task evaluator (registry.py)

## Common failure modes
- **HMAC verification failure**: wrong secret, wrong timestamp format, or replay attack exceeding `webhook_replay_window_sec`
- **Consecutive failure threshold**: routine auto-pauses after `max_consecutive_failures` — enforced by the evaluator in Phase 6+
- **Missing `cron_expression` on cron trigger**: validated at creation time, raises 422
- **`agent_registration_uuid` not found**: raises 404 at create time
- **Stale `next_run_at`**: if the evaluator misses a window, `catch_up_policy` determines whether missed runs are created or skipped

## Test coverage
- `tests/unit/services/test_routine_service.py`
- `tests/integration/test_routines_api.py`
