# Part 4: Operational Management

> **Split PRD navigation:**
> [Overview](_overview.md) | [Part 1: Core Runtime](part-1-core-runtime.md) | [Part 2: Actions & Orchestration](part-2-actions-orchestration.md) | [Part 3: Knowledge & Memory](part-3-knowledge-memory.md) | [Part 4: Operational](part-4-operational.md) | [Part 5: Platform Ops](part-5-platform-ops.md) | [API & MCP](appendix-api-mcp.md) | [Implementation Phases](implementation-phases.md)

# Part 4: Operational Management

> **Dependencies:** Part 1 (Core Runtime), Part 2 (Actions & Orchestration) for issue creation from investigations
> **Implementation:** Phase 5.5 (issues, routines, campaigns, topology)

---

### Data Model

#### `agent_issues` (NEW)


| Column                | Type        | Notes                                                                                                      |
| --------------------- | ----------- | ---------------------------------------------------------------------------------------------------------- |
| `id`                  | uuid        | PK                                                                                                         |
| `identifier`          | text        | NOT NULL, UNIQUE — auto-generated (e.g., "CAL-001"). Uses instance-level counter.                          |
| `parent_id`           | uuid        | NULL — FK self-reference for subtasks                                                                      |
| `alert_id`            | uuid        | NULL — FK `alerts.id`, if this issue originated from an alert investigation                                |
| `title`               | text        | NOT NULL                                                                                                   |
| `description`         | text        | NULL — markdown                                                                                            |
| `status`              | enum        | `backlog`, `todo`, `in_progress`, `in_review`, `done`, `blocked`, `cancelled`                              |
| `priority`            | enum        | `critical`, `high`, `medium`, `low` — default `medium`                                                     |
| `category`            | enum        | `remediation`, `detection_tuning`, `investigation`, `compliance`, `post_incident`, `maintenance`, `custom` |
| `assignee_agent_id`   | int         | NULL — FK `agent_registrations.id`                                                                         |
| `assignee_operator`   | text        | NULL — operator email (for human-assigned tasks)                                                           |
| `created_by_agent_id` | int         | NULL — FK `agent_registrations.id`                                                                         |
| `created_by_operator` | text        | NULL — operator email                                                                                      |
| `checkout_run_id`     | uuid        | NULL — FK `heartbeat_runs.id`, atomic checkout (same pattern as alert assignments)                         |
| `execution_locked_at` | timestamptz | NULL                                                                                                       |
| `routine_id`          | uuid        | NULL — FK `agent_routines.id`, if created by a routine                                                     |
| `due_at`              | timestamptz | NULL                                                                                                       |
| `started_at`          | timestamptz | NULL — set when status transitions to `in_progress`                                                        |
| `completed_at`        | timestamptz | NULL — set when status transitions to `done`                                                               |
| `cancelled_at`        | timestamptz | NULL                                                                                                       |
| `resolution`          | text        | NULL — free-text resolution summary                                                                        |
| `metadata`            | jsonb       | NULL — extensible metadata                                                                                 |
| `created_at`          | timestamptz | NOT NULL                                                                                                   |
| `updated_at`          | timestamptz | NOT NULL                                                                                                   |


#### `agent_issue_comments` (NEW)


| Column            | Type        | Notes                              |
| ----------------- | ----------- | ---------------------------------- |
| `id`              | uuid        | PK                                 |
| `issue_id`        | uuid        | FK `agent_issues.id`, NOT NULL     |
| `author_agent_id` | int         | NULL — FK `agent_registrations.id` |
| `author_operator` | text        | NULL — operator email              |
| `body`            | text        | NOT NULL — markdown                |
| `created_at`      | timestamptz | NOT NULL                           |
| `updated_at`      | timestamptz | NOT NULL                           |


#### `agent_routines` (NEW)

Defines recurring work patterns for agents.


| Column                     | Type        | Notes                                                                                                                                                                                                         |
| -------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                       | uuid        | PK                                                                                                                                                                                                            |
| `name`                     | text        | NOT NULL — human label ("Daily Threat Intel Triage", "Weekly FP Rate Review")                                                                                                                                 |
| `description`              | text        | NULL — what this routine does                                                                                                                                                                                 |
| `agent_registration_id`    | int         | FK `agent_registrations.id`, NOT NULL — which agent runs this                                                                                                                                                 |
| `status`                   | enum        | `active`, `paused`, `completed`                                                                                                                                                                               |
| `concurrency_policy`       | enum        | `skip_if_active` (default), `coalesce_if_active`, `always_run`                                                                                                                                                |
| `catch_up_policy`          | enum        | `skip_missed` (default), `catch_up`                                                                                                                                                                           |
| `task_template`            | jsonb       | NOT NULL — template for the work item created per run: `{ title_template, description_template, priority }`. Mustache-style rendering with `{{routine.name}}`, `{{trigger.fired_at}}`, `{{trigger.payload}}`. |
| `max_consecutive_failures` | int         | NOT NULL, default 3 — pause routine after N consecutive failures                                                                                                                                              |
| `consecutive_failures`     | int         | NOT NULL, default 0                                                                                                                                                                                           |
| `last_run_at`              | timestamptz | NULL                                                                                                                                                                                                          |
| `next_run_at`              | timestamptz | NULL — computed from trigger schedule                                                                                                                                                                         |
| `created_at`               | timestamptz | NOT NULL                                                                                                                                                                                                      |
| `updated_at`               | timestamptz | NOT NULL                                                                                                                                                                                                      |


#### `routine_triggers` (NEW)

Each routine can have one or more triggers (cron, webhook, manual).


| Column                      | Type        | Notes                                                                                                                       |
| --------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------- |
| `id`                        | uuid        | PK                                                                                                                          |
| `routine_id`                | uuid        | FK `agent_routines.id`, NOT NULL                                                                                            |
| `kind`                      | enum        | `cron`, `webhook`, `manual`                                                                                                 |
| `cron_expression`           | text        | NULL — 5-field cron expression (required when kind=cron). Examples: `0 8 `* * * (daily 8am), `*/30 * * `* * (every 30 min). |
| `timezone`                  | text        | NULL — IANA timezone for cron evaluation (default UTC)                                                                      |
| `webhook_public_id`         | text        | NULL — public identifier for webhook URL (kind=webhook)                                                                     |
| `webhook_secret_hash`       | text        | NULL — HMAC signing secret hash for webhook verification                                                                    |
| `webhook_replay_window_sec` | int         | NULL — reject webhooks older than this (default 300)                                                                        |
| `next_run_at`               | timestamptz | NULL — next scheduled fire time (cron only)                                                                                 |
| `last_fired_at`             | timestamptz | NULL                                                                                                                        |
| `is_active`                 | boolean     | NOT NULL, default true                                                                                                      |
| `created_at`                | timestamptz | NOT NULL                                                                                                                    |


#### `routine_runs` (NEW)

Tracks each execution instance of a routine.


| Column                  | Type        | Notes                                                               |
| ----------------------- | ----------- | ------------------------------------------------------------------- |
| `id`                    | uuid        | PK                                                                  |
| `routine_id`            | uuid        | FK `agent_routines.id`, NOT NULL                                    |
| `trigger_id`            | uuid        | FK `routine_triggers.id`, NOT NULL                                  |
| `source`                | enum        | `cron`, `webhook`, `manual`                                         |
| `status`                | enum        | `received`, `enqueued`, `running`, `completed`, `skipped`, `failed` |
| `trigger_payload`       | jsonb       | NULL — webhook payload or manual invocation context                 |
| `linked_alert_id`       | uuid        | NULL — if routine creates/processes an alert                        |
| `linked_issue_id`       | uuid        | NULL — if routine creates an issue (see Issue/Task System)          |
| `heartbeat_run_id`      | uuid        | NULL — FK `heartbeat_runs.id`, the actual execution                 |
| `coalesced_into_run_id` | uuid        | NULL — if skipped due to coalesce policy                            |
| `error`                 | text        | NULL                                                                |
| `created_at`            | timestamptz | NOT NULL                                                            |
| `completed_at`          | timestamptz | NULL — null while running; set on terminal status (completed/skipped/failed) |


#### `campaigns` (NEW)


| Column           | Type        | Notes                                                                                                                  |
| ---------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------- |
| `id`             | uuid        | PK                                                                                                                     |
| `name`           | text        | NOT NULL — "Credential Theft MTTD Reduction", "Q2 Vulnerability Remediation"                                           |
| `description`    | text        | NULL — markdown, strategic context and success criteria                                                                |
| `status`         | enum        | `planned`, `active`, `completed`, `cancelled`                                                                          |
| `category`       | enum        | `detection_improvement`, `response_optimization`, `vulnerability_management`, `compliance`, `threat_hunting`, `custom` |
| `owner_agent_id` | int         | NULL — FK `agent_registrations.id`, agent leading this campaign                                                        |
| `owner_operator` | text        | NULL — operator email                                                                                                  |
| `target_metric`  | text        | NULL — what metric this campaign targets (e.g., "mttd_credential_theft_min", "fp_rate_pct", "auto_resolve_pct")        |
| `target_value`   | numeric     | NULL — target value for the metric                                                                                     |
| `current_value`  | numeric     | NULL — current measured value                                                                                          |
| `target_date`    | timestamptz | NULL                                                                                                                   |
| `created_at`     | timestamptz | NOT NULL                                                                                                               |
| `updated_at`     | timestamptz | NOT NULL                                                                                                               |


#### `campaign_items` (NEW)

Links alerts, issues, and routines to campaigns for traceability.


| Column        | Type        | Notes                                                         |
| ------------- | ----------- | ------------------------------------------------------------- |
| `id`          | uuid        | PK                                                            |
| `campaign_id` | uuid        | FK `campaigns.id`, NOT NULL                                   |
| `item_type`   | enum        | `alert`, `issue`, `routine`                                   |
| `item_id`     | uuid        | NOT NULL — polymorphic FK (alert_id, issue_id, or routine_id) |
| `created_at`  | timestamptz | NOT NULL                                                      |


---

### Issue/Task System (Non-Alert Work)

Alerts are inbound signals from the detection pipeline. But security teams also need to track work that isn't alert-driven: remediation tasks, detection tuning tickets, post-incident follow-ups, manual investigation requests, compliance action items. The issue system provides this.

**Relationship to alerts:**

```
Alerts = automated inbound signals (from detection pipeline)
Issues = human or agent-created work items (remediation, tuning, follow-ups)
Incidents (future) = groups of related alerts + issues
```

Issues complement alerts. An agent investigating an alert may create issues as follow-up work. A routine may create issues for periodic maintenance. Operators may create issues for manual investigation requests.

#### Status Lifecycle

```
backlog → todo → in_progress → in_review → done
                     ↓
                   blocked → in_progress (when unblocked)
any → cancelled
```

Side effects:

- `in_progress`: sets `started_at`, creates `checkout_run_id` lock
- `done`: sets `completed_at`, releases lock
- `cancelled`: sets `cancelled_at`, releases lock

#### Checkout Mechanics

Same atomic checkout pattern as alert assignments:

```sql
UPDATE agent_issues
SET checkout_run_id = :run_id, execution_locked_at = now(), status = 'in_progress'
WHERE id = :issue_id
  AND (checkout_run_id IS NULL OR status NOT IN ('in_progress'))
RETURNING *;
-- 0 rows = 409 Conflict
```

> Cross-ref: Alert assignment checkout uses the same pattern in [Part 1].

#### How Agents Create Issues

Managed agents create issues via a new `managed` tier tool:

```
create_issue — Create a follow-up issue (category, title, description, priority, optional parent, optional assignee)
```

External agents create issues via REST API:

```
POST /api/v1/issues
```

**Common patterns:**

- Alert investigation reveals a vulnerable dependency → agent creates `remediation` issue
- Detection rule has high FP rate → agent creates `detection_tuning` issue
- Incident resolved but needs post-mortem → agent creates `post_incident` issue
- Routine scan finds configuration drift → agent creates `compliance` issue

#### Issue API Surface

```
POST   /api/v1/issues                              Create issue
GET    /api/v1/issues                              List issues (filterable by status, priority, category, assignee, alert_id)
GET    /api/v1/issues/{id}                         Get issue details
PATCH  /api/v1/issues/{id}                         Update issue
POST   /api/v1/issues/{id}/checkout                Atomic checkout
POST   /api/v1/issues/{id}/release                 Release checkout
GET    /api/v1/issues/{id}/comments                List comments
POST   /api/v1/issues/{id}/comments                Add comment
GET    /api/v1/agents/{uuid}/issues                List issues assigned to an agent
```

#### Issue MCP Tools

```
create_issue           — Create a new issue (managed tier)
get_my_issues          — Get issues assigned to this agent (safe tier)
update_issue_status    — Update issue status (managed tier)
add_issue_comment      — Add a comment to an issue (managed tier)
checkout_issue         — Atomic checkout of an issue (managed tier)
```

---

### Routine & Scheduled Invocation System

Beyond alert-driven execution, agents need to run on schedules: periodic threat intel triage, daily detection rule tuning, weekly posture assessments, compliance scans. The routine system provides cron-based and event-based scheduling with concurrency control.

#### How It Works

> [!note] Why Procrastinate for cron scheduling?
> Procrastinate's periodic task system runs entirely within PostgreSQL — no external scheduler, no EventBridge, no cron daemon. The `evaluate_routine_triggers_task` is a Procrastinate periodic task that runs every 30 seconds, evaluates due cron triggers, and enqueues work. This is intentional: keeping scheduling inside the DB means one less moving part in the deployment, and the `TaskQueueBase` abstraction already handles task dispatch. Operators who use the SQS task queue backend can still use Procrastinate periodic tasks for scheduling — they're independent systems. No need to introduce EventBridge.

**Cron-based scheduling:**

1. Periodic Procrastinate task (`evaluate_routine_triggers_task`, runs every 30s) scans active cron triggers where `next_run_at <= now()`
2. For each due trigger: evaluate concurrency policy
  - `skip_if_active`: if agent has an active run for this routine, skip and log
  - `coalesce_if_active`: merge into the existing active run (increment `coalesced_count`)
  - `always_run`: always create a new run (up to agent's `max_concurrent_alerts`)
3. Create `routine_runs` row, then create a work item (alert assignment or issue depending on `task_template`)
4. Enqueue agent wakeup with `invocation_source = 'automation'`, `trigger_detail = 'routine'`
5. Compute and store `next_run_at` for the trigger

**Webhook-based triggers:**

```
POST /api/v1/routines/{routine_id}/triggers/{trigger_id}/webhook

Headers:
  X-Webhook-Signature: sha256=<HMAC of body with signing secret>
  X-Webhook-Timestamp: <unix timestamp>

Body: (arbitrary JSON payload, passed to agent as trigger_payload)
```

- Verify HMAC signature, reject if timestamp exceeds `replay_window_sec`
- Create `routine_runs` row with `trigger_payload`, enqueue agent wakeup
- Use case: external systems triggering Calseta agents (SIEM alert forwarding, CI/CD pipeline events, ticketing system webhooks)

**Manual triggers:**

```
POST /api/v1/routines/{routine_id}/invoke
Body: { "payload": { ... } }  // optional context
```

#### Routine API Surface

```
POST   /api/v1/routines                              Create routine
GET    /api/v1/routines                              List routines (filterable by agent, status)
GET    /api/v1/routines/{id}                         Get routine details
PATCH  /api/v1/routines/{id}                         Update routine
DELETE /api/v1/routines/{id}                         Delete routine
POST   /api/v1/routines/{id}/pause                   Pause routine
POST   /api/v1/routines/{id}/resume                  Resume routine
POST   /api/v1/routines/{id}/invoke                  Manual trigger
POST   /api/v1/routines/{id}/triggers                Add trigger
PATCH  /api/v1/routines/{id}/triggers/{tid}          Update trigger
DELETE /api/v1/routines/{id}/triggers/{tid}          Delete trigger
POST   /api/v1/routines/{id}/triggers/{tid}/webhook  Webhook invocation
GET    /api/v1/routines/{id}/runs                    List routine runs
```

#### Example Routines


| Routine                   | Schedule                   | Agent               | Purpose                                  |
| ------------------------- | -------------------------- | ------------------- | ---------------------------------------- |
| Daily Threat Intel Triage | `0 8 * * *`                | Threat Intel Agent  | Process overnight intel submissions      |
| FP Rate Review            | `0 9 * * 1` (Mon 9am)      | Detection Eng Agent | Review detection rules with >20% FP rate |
| Posture Assessment        | `0 6 1 * *` (1st of month) | Compliance Agent    | Monthly security posture scan            |
| SIEM Health Check         | `*/30 * * * *` (every 30m) | SIEM Agent          | Verify log sources are healthy           |
| On-demand Sweep           | webhook                    | Endpoint Agent      | Triggered by external threat intel feed  |


---

### Investigation Campaigns (Strategic Objectives)

While individual alerts are tactical, security teams also pursue strategic objectives: "Reduce credential theft MTTD to under 5 minutes", "Eliminate all critical vulnerability findings by Q2", "Achieve 95% auto-resolution rate for low-severity alerts." Investigation campaigns provide this strategic layer.

#### How It Works

Campaigns are lightweight containers that give strategic context to operational work:

1. Operator creates a campaign with a target metric and goal
2. Alerts, issues, and routines can be linked to campaigns
3. The campaign dashboard shows progress toward the target (metric value over time)
4. Agents can query campaign context to understand why they're doing work (e.g., "This detection tuning issue is part of the 'Reduce FP Rate' campaign targeting <10% FP rate by Q2")

Campaigns are optional. They don't affect execution — they add strategic visibility. The data model ships in Phase 5.5 alongside the campaign CRUD API and auto-computed metrics.

#### Campaign API Surface

```
POST   /api/v1/campaigns                           Create campaign
GET    /api/v1/campaigns                           List campaigns
GET    /api/v1/campaigns/{id}                      Get campaign details with linked items
PATCH  /api/v1/campaigns/{id}                      Update campaign
POST   /api/v1/campaigns/{id}/items                Link item to campaign
DELETE /api/v1/campaigns/{id}/items/{item_id}      Unlink item
GET    /api/v1/campaigns/{id}/metrics              Get metric history for campaign
```

---

### Agent Topology (Capability & Delegation Map)

Security agents don't have a traditional reporting hierarchy (CEO → CTO → engineers). Instead, they have a **functional topology**: orchestrators delegate to specialists based on capability, not org chart position. The agent topology provides operators with a visual understanding of their agent fleet.

#### Topology Model

The topology is derived from existing data — no new tables needed:

1. **Agent types** (from `agent_registrations.agent_type`): orchestrator, specialist, standalone
2. **Delegation paths** (from `agent_registrations.sub_agent_ids`): which orchestrators can invoke which specialists
3. **Capabilities** (from `agent_registrations.capabilities`): what each specialist can do
4. **Alert routing** (from `agent_registrations.trigger_filter`): which alert types route to which orchestrators
5. **Role grouping** (from `agent_registrations.role`): functional clusters (triage, enrichment, response, investigation, detection_engineering)

#### Topology View

The topology view is a directed graph:

```
[Alert Sources] → [Routing Rules] → [Orchestrators] → [Specialists]
                                          ↓
                                    [Action Integrations]
```

Each node shows:

- Agent name, role, status (idle/running/paused/error)
- LLM provider and model
- Current workload (active assignments / max_concurrent_alerts)
- Budget utilization (spent / budget)
- Last heartbeat

Edges show:

- Alert routing paths (which alert types flow to which orchestrators)
- Delegation paths (which orchestrators invoke which specialists)
- Action integration paths (which agents can propose which action types)

#### Topology API Surface

```
GET    /api/v1/topology                            Get full agent topology graph
GET    /api/v1/topology/routing                    Get alert routing paths only
GET    /api/v1/topology/delegation                 Get delegation paths only
```

The topology endpoint returns a graph structure (nodes + edges) that the UI renders as an interactive diagram. No new data is stored — it's a computed view over existing agent configuration.

---

---

