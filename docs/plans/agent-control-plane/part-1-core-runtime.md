# Part 1: Agent Control Plane — Core Runtime

> **Split PRD navigation:**
> [Overview](_overview.md) | [Part 1: Core Runtime](part-1-core-runtime.md) | [Part 2: Actions & Orchestration](part-2-actions-orchestration.md) | [Part 3: Knowledge & Memory](part-3-knowledge-memory.md) | [Part 4: Operational](part-4-operational.md) | [Part 5: Platform Ops](part-5-platform-ops.md) | [API & MCP](appendix-api-mcp.md) | [Implementation Phases](implementation-phases.md)

# Part 1: Agent Control Plane (Core Runtime)

> **Dependencies:** None (foundation)
> **Implementation:** Phase 1, Phase 4

---

### Data Model

Calseta is single-tenant (one deployment = one org), so no tenant scoping is needed. Extends the existing PostgreSQL schema via Alembic migrations.

> [!important] Building on Existing Models
> Calseta already has `AgentRegistration` (webhook-based agent registry with trigger filters) and `AgentRun` (dispatch audit trail). The control plane **extends** these models rather than replacing them. The existing push-based dispatch continues to work — the control plane adds pull-based queuing, lifecycle management, and orchestration on top.

#### `llm_integrations`

Instance-level LLM provider configurations. Registered once, referenced by agents.


| Column                            | Type        | Notes                                                                             |
| --------------------------------- | ----------- | --------------------------------------------------------------------------------- |
| `id`                              | uuid        | PK                                                                                |
| `name`                            | text        | NOT NULL, UNIQUE — human label ("claude-opus", "haiku-fast", "gpt-4o")            |
| `provider`                        | text        | NOT NULL — "anthropic", "openai", "google", "azure_openai", "ollama", "claude_code"  |
| `model`                           | text        | NOT NULL — "claude-opus-4-6", "claude-haiku-4-5-20251001", "gpt-4o", etc.         |
| `api_key_ref`                     | text        | NULL — reference to secret storage (e.g., env var name or secret manager key). NULL for `claude_code` provider (uses local CLI auth). |
| `base_url`                        | text        | NULL — override for self-hosted/proxy endpoints                                   |
| `config`                          | jsonb       | NULL — provider-specific settings (temperature, max_tokens defaults, etc.)        |
| `cost_per_1k_input_tokens_cents`  | int         | NOT NULL — for budget tracking/estimation                                         |
| `cost_per_1k_output_tokens_cents` | int         | NOT NULL — for budget tracking/estimation                                         |
| `is_default`                      | boolean     | NOT NULL, default false — if true, agents without explicit LLM config use this    |
| `created_at`                      | timestamptz | NOT NULL                                                                          |
| `updated_at`                      | timestamptz | NOT NULL                                                                          |


Operators register LLM integrations at the instance level. Agents reference them by `llm_integration_id`. This gives:

- **Central API key management** — keys configured once, not per-agent
- **Cost tracking per model** — know exactly which model is burning budget
- **Easy model swaps** — change an integration's model without touching agent configs
- **Multiple providers** — use Opus for orchestrators, Haiku for focused specialists, GPT for specific tasks

> Cross-ref: API key storage uses the secrets system defined in [Part 5: Platform Operations].

#### `agent_registrations` (EXTEND EXISTING)

The existing `agent_registrations` table already has: `name`, `description`, `endpoint_url`, `auth_header_name`, `auth_header_value_encrypted`, `trigger_on_sources`, `trigger_on_severities`, `trigger_filter`, `timeout_seconds`, `retry_count`, `status` (TEXT enum — `active`/`paused`/`terminated`, replaces the former boolean `is_active` which was dropped in the Phase 1 migration), `documentation`. The control plane adds these columns:


| New Column                  | Type        | Notes                                                                                                                                                                             |
| --------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `execution_mode`            | enum        | `managed`, `external` — default `external` (backwards-compatible). `managed` = Calseta runs the agent. `external` = agent runs itself.                                            |
| `agent_type`                | enum        | `orchestrator`, `specialist`, `standalone` — default `standalone` (backwards-compatible with existing agents)                                                                     |
| `role`                      | text        | NULL — functional role ("triage", "enrichment", "response", "investigation", "detection_engineering")                                                                             |
| `capabilities`              | jsonb       | NULL — structured capability declarations for specialists (see Multi-Agent Orchestration)                                                                                         |
| `status`                    | enum        | `active`, `paused`, `terminated` — replaces the dropped boolean `is_active` (Phase 1 shipped). State machine managed via lifecycle endpoints (`pause`, `resume`, `terminate`).    |
| `adapter_type`              | enum        | NULL — `http`, `mcp`, `webhook` — default `webhook` (existing behavior). NULL = legacy webhook mode. For managed agents, this is ignored (Calseta runs the agent directly).       |
| `adapter_config`            | jsonb       | NULL — adapter-specific config for http/mcp adapters. NULL = use existing endpoint_url/auth fields (webhook mode).                                                                |
| `llm_integration_id`        | uuid        | NULL — FK `llm_integrations.id`. **Required** for managed agents (Calseta uses this to make LLM API calls). NULL for external/BYO agents.                                         |
| `system_prompt`             | text        | NULL — system prompt for managed agents. **Required** when `execution_mode = 'managed'`. NULL for external agents.                                                                |
| `methodology`               | text        | NULL — step-by-step investigation methodology (markdown). Injected into system prompt at runtime. Separating this from `system_prompt` allows reuse across agents and versioning. |
| `tool_ids`                  | text[]      | NULL — which tools this managed agent can use (references `agent_tools.id`). NULL for external agents.                                                                            |
| `max_tokens`                | int         | NULL — max output tokens per LLM call. NULL = use `llm_integrations.config` default.                                                                                              |
| `enable_thinking`           | boolean     | NOT NULL, default false — enable extended thinking for this agent (Anthropic only).                                                                                               |
| `sub_agent_ids`             | uuid[]      | NULL — for orchestrators: which specialist agents this orchestrator can invoke                                                                                                    |
| `max_sub_agent_calls`       | int         | NULL — for orchestrators: max sub-agent invocations per alert (cost safety)                                                                                                       |
| `budget_monthly_cents`      | int         | NOT NULL, default 0 (0 = unlimited)                                                                                                                                               |
| `spent_monthly_cents`       | int         | NOT NULL, default 0                                                                                                                                                               |
| `budget_period_start`       | timestamptz | NULL — start of current budget window (NULL = no budget tracking)                                                                                                                 |
| `last_heartbeat_at`         | timestamptz | NULL                                                                                                                                                                              |
| `max_concurrent_alerts`     | int         | NOT NULL, default 1 — how many alerts this agent can work simultaneously                                                                                                          |
| `max_cost_per_alert_cents`  | int         | NOT NULL, default 0 (0 = unlimited) — per-alert budget cap. Investigation paused and operator notified if exceeded. Prevents runaway investigations on a single alert.            |
| `max_investigation_minutes` | int         | NOT NULL, default 0 (0 = unlimited) — time limit per investigation. Triggers escalation or forced resolution on timeout.                                                          |
| `stall_threshold`           | int         | NOT NULL, default 0 (0 = disabled) — number of consecutive sub-agent invocations returning no actionable findings before flagging investigation as stalling.                      |
| `instruction_files`         | jsonb       | NULL — array of `{ name: string, description: string, content: string }` instruction files injected into the agent's prompt after system_prompt. Agent-specific. See global instructions for instance-wide files. |


> Cross-ref: `sub_agent_ids`, `max_sub_agent_calls`, `stall_threshold`, `capabilities`, and `agent_type` columns are used by the multi-agent orchestration system in [Part 2].

#### `agent_instruction_files` (NEW — global instructions)

> **Paperclip ref:** `/server/src/services/agent-instructions.ts`, `default-agent-instructions.ts` — Paperclip manages instruction bundles per agent with `managed` vs `external` bundle mode and an `entryFile` (AGENTS.md) pattern.

Instance-level instruction files that apply to **all** managed agents. These supplement (not replace) per-agent `instruction_files`. Useful for instance-wide policies, tool usage guides, and operational standards that every agent should know.

| Column        | Type        | Notes                                                                                                   |
| ------------- | ----------- | ------------------------------------------------------------------------------------------------------- |
| `id`          | uuid        | PK                                                                                                      |
| `name`        | text        | NOT NULL, UNIQUE — file identifier ("global-tool-usage.md", "security-policies.md")                     |
| `description` | text        | NOT NULL — one-line description shown in agent detail UI                                                |
| `content`     | text        | NOT NULL — markdown content of the instruction file                                                     |
| `scope`       | text        | NOT NULL, default 'global' — 'global' (all agents) or 'role:{role_name}' (all agents with that role)    |
| `is_active`   | boolean     | NOT NULL, default true                                                                                  |
| `inject_order`| int         | NOT NULL, default 0 — lower numbers inject first; global files inject after per-agent instruction_files |
| `created_at`  | timestamptz | NOT NULL                                                                                                |
| `updated_at`  | timestamptz | NOT NULL                                                                                                |

**Injection order in prompt construction:**
```
Layer 1: system_prompt (per-agent)
  → agent.instruction_files (per-agent, in order)
  → global agent_instruction_files scoped to this agent's role (by inject_order)
  → global agent_instruction_files scoped 'global' (by inject_order)
Layer 2: methodology (per-agent)
...
```

**API surface:**
```
POST   /api/v1/agent-instructions              Create global instruction file
GET    /api/v1/agent-instructions              List all global instruction files
GET    /api/v1/agent-instructions/{id}         Get file
PATCH  /api/v1/agent-instructions/{id}         Update file
DELETE /api/v1/agent-instructions/{id}         Delete file
GET    /api/v1/agents/{uuid}/instructions      Get all instruction files for an agent (global + per-agent, in inject order)
```

**UI:** In the agent detail page, a new "Instructions" tab shows all instruction files (global + per-agent) in injection order. Operators can add per-agent files inline or navigate to Settings > Global Instructions to manage instance-wide files.

**Managed vs External — how the columns interact:**


| Column               | Managed Agent                    | External Agent              |
| -------------------- | -------------------------------- | --------------------------- |
| `execution_mode`     | `managed`                        | `external`                  |
| `llm_integration_id` | Required                         | NULL                        |
| `system_prompt`      | Required                         | NULL                        |
| `methodology`        | Optional (recommended)           | NULL                        |
| `tool_ids`           | Required (what tools can it use) | NULL                        |
| `adapter_type`       | Ignored (Calseta runs it)        | `webhook`, `http`, or `mcp` |
| `endpoint_url`       | NULL                             | Required                    |


**Backwards compatibility:** Existing agents continue to work as-is. They get `execution_mode = 'external'`, `agent_type = 'standalone'`, `adapter_type = 'webhook'`, `status = 'active'` (migrated from the former `is_active` boolean, which was dropped in the Phase 1 Alembic migration). The existing push-based dispatch (`dispatch_to_agent()`) uses the same `endpoint_url` and trigger matching. New control plane features are opt-in via the new columns.

> **Note:** The `is_active` → `status` migration is complete. The `is_active` boolean column no longer exists on `agent_registrations`. The live column is `status` TEXT enum (`active`/`paused`/`terminated`). The migration SQL below is preserved for reference only:

```sql
-- Reference only — already executed in Phase 1 migration
UPDATE agent_registrations SET status = CASE WHEN is_active THEN 'active' ELSE 'paused' END;
-- is_active column was dropped after verification
```

**Status state machine (Phase 1 implementation):**

Phase 1 ships with three operator-managed states. The `idle`/`running`/`error` transient states below are the full design intent for future phases when the managed agent runtime tracks per-investigation execution state more granularly.

```
active  → paused     (operator pause, or budget hard-stop)
paused  → active     (operator resume)
*       → terminated (operator only, irreversible)
```

Full state machine (Phase 1 — managed agent runtime implementation):
```
idle → running (heartbeat invoked or alert checked out)
running → idle (heartbeat complete, no active work)
running → error (crash, timeout, adapter failure)
error → idle (manual recovery or heartbeat success)
idle → paused (operator or budget hard-stop)
running → paused (graceful cancel → pause)
paused → idle (operator resumes)
* → terminated (operator only, irreversible)
```

#### `agent_api_keys` (NEW)

Scoped authentication for agents to call back into Calseta (pull alerts, propose actions, report costs). Separate from the existing auth header system which is for Calseta pushing TO agents. Plaintext shown once at creation; only hash stored.


| Column                  | Type        | Notes                                                      |
| ----------------------- | ----------- | ---------------------------------------------------------- |
| `id`                    | uuid        | PK                                                         |
| `agent_registration_id` | int         | FK `agent_registrations.id`, NOT NULL                      |
| `name`                  | text        | NOT NULL — human label ("production-key-1")                |
| `key_prefix`            | text        | NOT NULL — first 8 chars for identification                |
| `key_hash`              | text        | NOT NULL — bcrypt/argon2 hash                              |
| `scopes`                | jsonb       | NOT NULL — array of allowed scopes (see Permission Matrix) |
| `last_used_at`          | timestamptz | NULL                                                       |
| `revoked_at`            | timestamptz | NULL                                                       |
| `created_at`            | timestamptz | NOT NULL                                                   |
| `updated_at`            | timestamptz | NOT NULL                                                   |


> Cross-ref: Permission matrix and run-scoped JWTs for managed agents are in [Part 5: Platform Operations].

#### `alert_assignments` (NEW)

Maps alerts to agents. This is the atomic checkout table — the bridge between Calseta's existing alert model and the agent work queue. Complements the existing `AgentRun` table (which tracks push-based dispatch attempts) by tracking pull-based agent work.


| Column                  | Type        | Notes                                                                            |
| ----------------------- | ----------- | -------------------------------------------------------------------------------- |
| `id`                    | uuid        | PK                                                                               |
| `alert_id`              | int         | FK `alerts.id`, NOT NULL                                                         |
| `agent_registration_id` | int         | FK `agent_registrations.id`, NOT NULL                                            |
| `status`                | enum        | `assigned`, `in_progress`, `pending_review`, `resolved`, `escalated`, `released` |
| `checked_out_at`        | timestamptz | NOT NULL                                                                         |
| `started_at`            | timestamptz | NULL                                                                             |
| `completed_at`          | timestamptz | NULL                                                                             |
| `resolution`            | text        | NULL — free-text resolution summary                                              |
| `resolution_type`       | enum        | NULL — `true_positive`, `false_positive`, `benign`, `inconclusive`               |
| `created_at`            | timestamptz | NOT NULL                                                                         |
| `updated_at`            | timestamptz | NOT NULL                                                                         |


**Checkout invariant:** Single-assignee atomic checkout via:

```sql
UPDATE alert_assignments
SET agent_registration_id = :agent_reg_id, status = 'in_progress', started_at = now()
WHERE alert_id = :alert_id
  AND status IN ('assigned', 'released')
  AND (agent_registration_id IS NULL OR agent_registration_id = :agent_reg_id)
RETURNING *;
-- 0 rows = 409 Conflict (already claimed)
```

Alternatively for new assignments:

```sql
INSERT INTO alert_assignments (alert_id, agent_registration_id, status, checked_out_at)
SELECT :alert_id, :agent_reg_id, 'in_progress', now()
WHERE NOT EXISTS (
  SELECT 1 FROM alert_assignments
  WHERE alert_id = :alert_id AND status NOT IN ('released', 'resolved')
);
-- 0 rows inserted = 409 Conflict
```

#### `agent_task_sessions` (NEW)

Persists agent LLM session state across heartbeat invocations. Enables conversation continuity so managed agents don't restart from scratch on each heartbeat. Sessions are scoped per-agent per-alert (not globally per-agent), allowing an agent to maintain separate conversation contexts for different investigations.


| Column                  | Type        | Notes                                                                                                                                                                       |
| ----------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `id`                    | uuid        | PK                                                                                                                                                                          |
| `agent_registration_id` | int         | FK `agent_registrations.id`, NOT NULL                                                                                                                                       |
| `alert_id`              | uuid        | NULL — FK `alerts.id`. NULL for non-alert work (issues, scheduled tasks).                                                                                                   |
| `task_key`              | text        | NOT NULL — composite key for session lookup (e.g., `alert:{alert_id}`, `issue:{issue_id}`, `routine:{routine_id}`). UNIQUE constraint on (agent_registration_id, task_key). |
| `session_params`        | jsonb       | NOT NULL — adapter-specific session state. For managed agents: conversation history reference, tool call state. For external agents: opaque blob the agent controls.        |
| `session_display_id`    | text        | NULL — human-readable session identifier                                                                                                                                    |
| `total_input_tokens`    | int         | NOT NULL, default 0 — cumulative input tokens across all heartbeats in this session                                                                                         |
| `total_output_tokens`   | int         | NOT NULL, default 0 — cumulative output tokens                                                                                                                              |
| `total_cost_cents`      | int         | NOT NULL, default 0 — cumulative cost for this session                                                                                                                      |
| `heartbeat_count`       | int         | NOT NULL, default 0 — number of heartbeats in this session                                                                                                                  |
| `last_run_id`           | uuid        | NULL — FK `heartbeat_runs.id`                                                                                                                                               |
| `last_error`            | text        | NULL                                                                                                                                                                        |
| `compacted_at`          | timestamptz | NULL — when session was last compacted (conversation summarized)                                                                                                            |
| `created_at`            | timestamptz | NOT NULL                                                                                                                                                                    |
| `updated_at`            | timestamptz | NOT NULL                                                                                                                                                                    |


**Session lifecycle:**

```
Alert checked out → session created (or existing session resumed)
  → heartbeat 1: agent investigates, session_params updated with conversation state
  → heartbeat 2: agent resumes conversation (not from scratch), tokens are delta-computed
  → ...
  → session compaction threshold hit: conversation summarized, old context replaced with handoff summary
  → alert resolved → session archived (retained for audit, not actively loaded)
```

**Session compaction:** When cumulative tokens exceed a configurable threshold (e.g., 80% of model context window), the runtime engine triggers compaction:

1. Generate a handoff summary from the current conversation (key findings, investigation state, next steps)
2. Store the summary as `session_handoff_markdown` in `session_params`
3. On next heartbeat, inject the handoff summary as initial context instead of resuming the full conversation
4. Reset token counters, increment `heartbeat_count`, set `compacted_at`

This prevents context window overflow during long multi-wave investigations while preserving investigation continuity.

**Compaction thresholds (configurable per-agent):**


| Setting                            | Default       | Notes                                                                 |
| ---------------------------------- | ------------- | --------------------------------------------------------------------- |
| `session_compaction_threshold_pct` | 80            | Percentage of model's context window that triggers compaction         |
| `session_compaction_strategy`      | `summarize`   | `summarize` (LLM generates summary) or `truncate` (keep last N turns) |
| `session_max_heartbeats`           | 0 (unlimited) | Force compaction after N heartbeats regardless of token count         |


These are stored as optional fields in `agent_registrations.adapter_config` or a new `session_config` JSONB column.

#### `heartbeat_runs`

Track agent invocation lifecycle.


| Column                  | Type        | Notes                                                                |
| ----------------------- | ----------- | -------------------------------------------------------------------- |
| `id`                    | uuid        | PK                                                                   |
| `agent_registration_id` | int         | FK `agent_registrations.id`, NOT NULL                                |
| `source`                | enum        | `scheduler`, `manual`, `dispatch`, `callback`                        |
| `status`                | enum        | `queued`, `running`, `succeeded`, `failed`, `cancelled`, `timed_out` |
| `started_at`            | timestamptz | NULL                                                                 |
| `finished_at`           | timestamptz | NULL                                                                 |
| `error`                 | text        | NULL                                                                 |
| `alerts_processed`      | int         | NOT NULL, default 0                                                  |
| `actions_proposed`      | int         | NOT NULL, default 0                                                  |
| `context_snapshot`      | jsonb       | NULL — what context was provided to the agent                        |
| `created_at`            | timestamptz | NOT NULL                                                             |
| `updated_at`            | timestamptz | NOT NULL                                                             |


#### `cost_events`

Token and cost tracking per agent interaction.


| Column                  | Type        | Notes                                                                       |
| ----------------------- | ----------- | --------------------------------------------------------------------------- |
| `id`                    | uuid        | PK                                                                          |
| `agent_registration_id` | int         | FK `agent_registrations.id`, NOT NULL                                       |
| `llm_integration_id`    | uuid        | NULL — FK `llm_integrations.id` (auto-populated for Calseta-managed agents) |
| `alert_id`              | uuid        | NULL — FK `alerts.id`                                                       |
| `invocation_id`         | uuid        | NULL — FK `agent_invocations.id` (links cost to specific sub-agent call)    |
| `heartbeat_run_id`      | uuid        | NULL — FK `heartbeat_runs.id`                                               |
| `provider`              | text        | NOT NULL — "anthropic", "openai", "google", "claude_code", etc.             |
| `model`                 | text        | NOT NULL — "claude-opus-4-6", "claude-haiku-4-5-20251001", "gpt-4o", etc.   |
| `input_tokens`          | int         | NOT NULL, default 0                                                         |
| `output_tokens`         | int         | NOT NULL, default 0                                                         |
| `cost_cents`            | int         | NOT NULL                                                                    |
| `occurred_at`           | timestamptz | NOT NULL                                                                    |
| `created_at`            | timestamptz | NOT NULL                                                                    |


> Cross-ref: `invocation_id` links to `agent_invocations` defined in [Part 2].

#### `activity_log` (EXTENDS EXISTING `activity_events`)

> [!important] Unification with Existing Audit Trail
> Calseta v1 already has an `activity_events` table covering alert-level mutations (`alert.created`, `alert.status_changed`, `workflow.executed`, etc.). The control plane does **not** create a separate `activity_log` table. Instead, `activity_events` is extended with new event types covering the full platform. This gives operators a single audit trail across all of Calseta's operations — not two parallel tables.
>
> The existing `activity_events` schema (`event_type`, `actor_type` (system/api/mcp), `actor_key_prefix`, polymorphic FKs, `references` JSONB) already supports the control plane's needs. New control plane event types are added as values to the existing `event_type` enum.

**New control plane event types added to `activity_events`:**

```
agent.created              agent.paused               agent.resumed
agent.terminated           agent.status_changed       agent.budget_exceeded
alert.checked_out          alert.released             alert.assignment_resolved
action.proposed            action.approved            action.rejected
action.executed            action.failed              action.cancelled
invocation.created         invocation.completed       invocation.failed
heartbeat.started          heartbeat.completed        heartbeat.timed_out
cost.budget_alert          cost.hard_stop             routine.fired
routine.completed          routine.failed             issue.created
issue.status_changed       issue.assigned             kb.page_created
kb.page_updated            kb.page_synced             secret.created
secret.rotated             secret.revoked             operator.login
operator.token_created     operator.token_revoked
```

> **Paperclip ref:** `/server/src/services/activity.ts`, `activity-log.ts`, `/packages/db/src/schema/activity_log.ts` — Paperclip's activity log uses the same `actorType` (agent/user/system), `entityType`, `entityId`, `details` JSONB pattern.

The audit trail now covers the **entire platform** — every entity mutation, every auth event, every agent action, and every cost event is auditable through a single `GET /api/v1/activity` endpoint with filtering by entity type, actor, date range, and event type.


#### Required Indexes (Part 1)

```sql
CREATE INDEX idx_llm_integrations_name ON llm_integrations(name);
CREATE INDEX idx_agent_reg_status ON agent_registrations(status);
CREATE INDEX idx_agent_reg_type ON agent_registrations(agent_type);
CREATE INDEX idx_agent_reg_llm ON agent_registrations(llm_integration_id);
CREATE INDEX idx_alert_assignments_status ON alert_assignments(status);
CREATE INDEX idx_alert_assignments_alert ON alert_assignments(alert_id, status);
CREATE INDEX idx_alert_assignments_agent ON alert_assignments(agent_id, status);
CREATE INDEX idx_heartbeat_runs_agent ON heartbeat_runs(agent_id, started_at DESC);
CREATE INDEX idx_cost_events_agent ON cost_events(agent_id, occurred_at);
CREATE INDEX idx_cost_events_llm ON cost_events(llm_integration_id, occurred_at);
CREATE INDEX idx_cost_events_occurred ON cost_events(occurred_at);
CREATE INDEX idx_activity_log_created ON activity_log(created_at DESC);
```

> Cross-ref: Indexes for Part 2 tables (`agent_actions`, `agent_invocations`) are in [Part 2]. Indexes for `cost_events.invocation_id` are also in [Part 2].

**`activity_events` enum migration:** The existing `event_type` TEXT column requires no schema change — new event types are application-level values, not a PostgreSQL ENUM. All new control plane event types (`agent.created`, `alert.checked_out`, `action.proposed`, etc.) are added as valid values in the application's event type registry without an ALTER TYPE migration.

#### Required Indexes (Part 3)

```sql
CREATE INDEX idx_kb_pages_status ON knowledge_base_pages(status) WHERE status = 'published';
CREATE INDEX idx_kb_pages_inject ON knowledge_base_pages(inject_scope) WHERE inject_scope IS NOT NULL;
CREATE INDEX idx_kb_pages_folder ON knowledge_base_pages(folder);
CREATE INDEX idx_kb_page_revisions_page ON kb_page_revisions(page_id, revision_number DESC);
CREATE INDEX idx_kb_page_links_entity ON kb_page_links(linked_entity_type, linked_entity_id);
```

#### Required Indexes (Part 4)

```sql
CREATE INDEX idx_agent_issues_status ON agent_issues(status);
CREATE INDEX idx_agent_issues_assignee ON agent_issues(assignee_agent_id) WHERE assignee_agent_id IS NOT NULL;
CREATE INDEX idx_agent_issues_alert ON agent_issues(alert_id) WHERE alert_id IS NOT NULL;
CREATE INDEX idx_routine_triggers_next_run ON routine_triggers(next_run_at) WHERE kind = 'cron' AND is_active = true;
CREATE INDEX idx_routine_runs_routine ON routine_runs(routine_id, created_at DESC);
CREATE INDEX idx_campaign_items_campaign ON campaign_items(campaign_id);
CREATE INDEX idx_campaign_items_item ON campaign_items(item_type, item_id);
```

---

### Adapter System

> [!important] Two agent modes
> **Managed agents** run inside Calseta — Calseta makes the LLM API calls, controls the tool loop, and tracks every token. **External (BYO) agents** are independent HTTP services that communicate with Calseta via REST API and API keys. The adapter system below applies only to external agents — managed agents don't need adapters because Calseta IS the runtime.

**For external agents, two communication directions, both HTTP:**

1. **Calseta → Agent** (push): HTTP POST to agent's webhook URL or invoke endpoint
2. **Agent → Calseta** (pull): Agent authenticates with agent API key, calls Calseta REST API to pull alerts, propose actions, report costs

Adapters define how Calseta invokes **external** agents on the push side. The pull side is always the same: agent calls Calseta's REST API with a Bearer token. Managed agents don't use adapters — Calseta runs them directly via the Agent Runtime Engine.

#### `webhook` Adapter (EXISTING — Phase 1)

The current system. Calseta pushes enriched alert payloads to agent webhook URLs. Uses existing `endpoint_url`, `auth_header_name`, `auth_header_value_encrypted`, `timeout_seconds`, `retry_count` fields on `AgentRegistration`. Dispatch tracked via `AgentRun` records. No changes needed — this continues to work as-is for agents with `adapter_type = 'webhook'`.

#### `http` Adapter (PRIMARY — Phase 1)

The enterprise-grade adapter. Fire-and-forget invocation of externally hosted agents — serverless functions, containers, third-party agent platforms.

```json
{
  "adapter_type": "http",
  "adapter_config": {
    "url": "https://my-agent.example.com/invoke",
    "method": "POST",
    "headers": {
      "Authorization": "Bearer {{secret:agent_webhook_token}}"
    },
    "timeout_ms": 15000,
    "payload_template": {
      "agent_id": "{{agent.id}}",
      "run_id": "{{run.id}}",
      "callback_url": "{{calseta.callback_url}}"
    }
  }
}
```

Behavior:

- Send HTTP request with templated payload
- 2xx = invocation accepted (agent is running)
- non-2xx = invocation failed
- Agent reports completion via callback URL or Calseta REST API
- Cancel sends DELETE to callback URL

**Why this is the primary adapter:** Enterprise agents run as independent services with their own infrastructure, scaling, and deployment pipelines. The `http` adapter treats them as black boxes — Calseta invokes them, they call back. No process management, no shared runtime, no coupling.

#### `mcp` Adapter (Phase 1)

Leverages Calseta's existing MCP server. Agent connects as an MCP client and pulls work through MCP tools.

```json
{
  "adapter_type": "mcp",
  "adapter_config": {
    "mode": "pull",
    "poll_interval_sec": 30,
    "tools_enabled": [
      "get_pending_alerts",
      "checkout_alert",
      "propose_action",
      "report_cost",
      "complete_alert"
    ]
  }
}
```

Behavior:

- Agent connects to Calseta's MCP server (port 8001)
- Agent uses MCP tools to pull alerts, propose actions, report results
- Heartbeat inferred from tool call activity (last MCP call = last heartbeat)
- No explicit invoke/cancel — agent manages its own lifecycle

#### Adapter Interface

```python
class AgentAdapter(ABC):
    """Base class for agent execution adapters."""

    @abstractmethod
    async def invoke(self, agent: Agent, context: InvocationContext) -> InvokeResult:
        """Start the agent's execution cycle."""
        ...

    @abstractmethod
    async def status(self, run: HeartbeatRun) -> RunStatus:
        """Check if the agent is still running."""
        ...

    @abstractmethod
    async def cancel(self, run: HeartbeatRun) -> None:
        """Send graceful termination signal."""
        ...
```

#### `process` Adapter (Dev/Demo Only — Phase 7+)

> [!warning] Not for production
> The `process` adapter spawns local child processes. This is useful for local development, demos, and reference agent examples. Enterprise deployments should use the `http` or `mcp` adapters. No enterprise SOC team should run agents as subprocesses co-located with their data platform.

Spawns a local child process. Useful for running reference agents locally during development.

```json
{
  "adapter_type": "process",
  "adapter_config": {
    "command": "python",
    "args": ["agent.py", "--agent-id", "{{agent.id}}"],
    "cwd": "/opt/agents/triage",
    "env": {
      "CALSETA_API_URL": "http://localhost:8000",
      "CALSETA_API_KEY": "{{agent.api_key}}",
      "ANTHROPIC_API_KEY": "{{secret:anthropic_key}}"
    },
    "timeout_sec": 900,
    "grace_sec": 15
  }
}
```

Behavior:

- Spawn child process with configured command/args/env
- Stream stdout/stderr to heartbeat run logs
- Mark run status based on exit code (0 = succeeded, non-zero = failed)
- On cancel: SIGTERM → wait `grace_sec` → SIGKILL
- On timeout: same cancel flow

---

### Agent Runtime Engine

The runtime engine is how Calseta **executes** managed agents. When a managed agent is triggered (alert arrives, orchestrator delegates, operator invokes manually), the runtime:

1. Loads agent config from DB (system prompt, methodology, tool set, LLM provider)
2. Resolves the LLM provider from `llm_integrations` (gets API key, model, config)
3. Resolves session state from `agent_task_sessions` (resume conversation or start fresh)
4. Constructs the full prompt via the **6-layer prompt construction system** (see below)
5. Initializes the LLM client (Anthropic SDK, OpenAI SDK, etc. based on provider)
6. Runs the agent loop: send prompt → receive response → if tool call, execute tool → feed result back → repeat until agent signals completion
7. Records all token usage as `cost_events` (exact, not estimated — Calseta sees every API response)
8. Persists findings, proposed actions, investigation state, and session state to `agent_task_sessions`

#### Prompt Construction (6-Layer System)

The runtime engine assembles agent context from six layers, each serving a distinct purpose. Layers are concatenated in order; earlier layers set identity and rules, later layers provide dynamic context.

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: System Prompt (per-agent, static)              │
│   Who you are, your role, behavioral rules, constraints │
├─────────────────────────────────────────────────────────┤
│ Layer 2: Methodology (per-agent, reusable)              │
│   Step-by-step investigation playbook (markdown)        │
├─────────────────────────────────────────────────────────┤
│ Layer 3: Knowledge Base Context (dynamic, scoped)       │
│   KB pages tagged for injection into this agent/role    │
│   Global pages + role-scoped pages + agent-specific     │
├─────────────────────────────────────────────────────────┤
│ Layer 4: Alert/Task Context (per-invocation)            │
│   Enriched alert payload, assignment details,           │
│   prior findings, linked context documents              │
├─────────────────────────────────────────────────────────┤
│ Layer 5: Session State (cross-heartbeat)                │
│   Session handoff summary (if compacted),               │
│   investigation plan progress, prior tool call results  │
├─────────────────────────────────────────────────────────┤
│ Layer 6: Runtime Checkpoint (system-injected)           │
│   Budget status, stall status, time elapsed,            │
│   severity flags, agent memory entries                  │
└─────────────────────────────────────────────────────────┘

```

**Layer 1 — System Prompt** (from `agent_registrations.system_prompt`):

- Static per-agent. Defines identity, role, constraints, output format expectations.
- Example: "You are a Triage Agent. Your job is to classify alerts as true positive, false positive, or benign. You must provide a confidence score (0.0-1.0) and reasoning for every classification."
- Editable via API/UI. Changes take effect on next heartbeat.

**Layer 2 — Methodology** (from `agent_registrations.methodology`):

- Step-by-step investigation playbook in markdown. Injected into a `<methodology>` section in the prompt.
- Separating methodology from system prompt allows: (a) reuse across agents with the same role, (b) independent versioning, (c) operator can swap methodologies without touching the base prompt.
- Example: A credential theft methodology specifying Wave 1 (identity + SIEM + threat intel), Wave 2 (endpoint + historical), Wave 3 (response).

**Layer 3 — Knowledge Base Context** (from `knowledge_base_pages` with `inject_scope`):

- Dynamic context pages managed via the Knowledge Base system.
- Pages tagged with injection scope: `global` (all agents), `role:<role_name>` (all agents with that role), `agent:<agent_id>` (specific agent).
- Runtime resolves applicable pages at invocation time, injects as `<context_document title="...">` sections.
- Examples: company security policies (global), SIEM query syntax reference (role:siem_specialist), specific runbook for a particular agent.
- Token-budget-aware: if total KB context exceeds a configurable limit (e.g., 20% of context window), pages are prioritized by: pinned > agent-specific > role-scoped > global, then by last-modified date.

> Cross-ref: See [Part 3: Knowledge & Memory] for the KB system, data model, context injection flow, and external sync.

**Layer 4 — Alert/Task Context** (assembled at invocation time):

- For alert-driven invocations: full enriched alert payload (indicators, detection rules, enrichment results, context documents from Calseta's existing targeting system).
- For issue-driven invocations: issue description, parent context, linked alerts, comments.
- For routine-driven invocations: routine description, trigger payload, any linked entities.
- Prior findings from this investigation (from `alert_assignments.investigation_state` or issue comments).

> Cross-ref: Issues and routines are defined in [Part 4: Operational Management].

**Layer 5 — Session State** (from `agent_task_sessions`):

- On session resume: the LLM conversation continues from where it left off (no re-injection needed — the session itself carries context).
- On session compaction: a `session_handoff_markdown` summary is injected as the first user message, providing continuity without the full conversation history.
- Investigation plan progress: if the agent has a structured investigation plan, the current step and completed steps are summarized.

**Layer 6 — Runtime Checkpoint** (system-generated, injected at wave boundaries):

- Budget status: "$0.23 of $1.00 spent. 77% remaining."
- Stall status: "0 empty results. Investigation progressing."
- Time status: "2m of 10m elapsed."
- Severity flags: "SIEM agent returned finding with malice: Malicious. Re-evaluate priority."
- Agent memory entries: relevant persistent memory items (if agent memory system is active).
- This layer is injected by the runtime engine, not authored by humans. It gives the agent situational awareness without requiring a separate governance agent.

> Cross-ref: Agent persistent memory injected into Layer 6 is defined in [Part 3: Knowledge & Memory].

**Token budget allocation across layers:**

> [!note] These are **targets/guidelines for tuning**, not hard limits enforced by the runtime. The runtime enforces only one hard constraint: total prompt size must leave a configurable minimum headroom for agent reasoning (default: 20% of context window). The allocations below are defaults that operators use as a starting point when configuring agents. Per-agent overrides are stored in `agent_registrations.adapter_config` under a `context_budget` key.

| Layer                                          | Default target | Notes                                         |
| ---------------------------------------------- | -------------- | --------------------------------------------- |
| System prompt + instruction files              | 5-15%          | Static, well-optimized; grows with instruction files |
| Methodology                                    | 5-10%          | Structured playbook                           |
| KB context                                     | 10-20%         | Dynamic, prioritized; configurable per-agent  |
| Alert/task context                             | 20-40%         | Scales with enrichment depth                  |
| Session state                                  | 10-30%         | Grows across heartbeats, compacted when large |
| Runtime checkpoint                             | 1-2%           | Small, injected at boundaries                 |
| **Minimum reserved for agent reasoning**       | **20%**        | Hard floor — runtime warns/compacts if breached |

The runtime engine monitors total prompt size and warns (or auto-compacts) if the remaining space for agent reasoning drops below the configurable minimum (default: 20% of context window).

#### Context Preview API

Operators can inspect the exact context an agent would receive for a given alert — the assembled output of the 6-layer system — without actually invoking the agent. Critical for debugging prompt construction, verifying KB injection, and understanding why an agent behaved a certain way.

```
GET /api/v1/agents/{uuid}/context-preview?alert_id={alert_uuid}

Response:
{
  "layers": {
    "system_prompt": "...",
    "instruction_files": [...],
    "methodology": "...",
    "kb_context": [
      {"slug": "credential-theft-runbook", "tokens": 1240, "inject_scope": "role:investigation"},
      ...
    ],
    "alert_context": { ...full enriched alert... },
    "session_state": null,
    "runtime_checkpoint": null
  },
  "total_tokens_estimated": 8420,
  "context_window": 200000,
  "headroom_pct": 95.8,
  "kb_pages_excluded_by_budget": [...],
  "assembled_prompt": "...(full text)..."
}
```

> Cross-ref: The `heartbeat_runs.context_snapshot` field captures the actual context used in the last real invocation. The preview endpoint is pre-invocation; `context_snapshot` is post-invocation.

**MCP tool:** `get_context_preview` — returns the same data for use in agent-to-agent debugging.

**UI:** In agent detail page, a "Context Preview" button opens a modal with the assembled prompt, token counts per layer, and a list of KB pages included vs. excluded by token budget. This is the primary tool for understanding the 6-layer system in practice.

```python
class AgentRuntimeEngine:
    """Executes managed agents by making LLM API calls."""

    async def run(self, agent: AgentRegistration, context: RuntimeContext) -> RuntimeResult:
        """
        Main execution loop for a managed agent.

        1. Build prompt from agent config + context
        2. Initialize LLM client from llm_integration
        3. Loop: prompt → response → tool calls → results → repeat
        4. Record cost_events for every LLM call
        5. Return structured result (findings, actions, cost)
        """
        ...

    async def _execute_tool_call(self, tool_call: ToolCall, agent: AgentRegistration) -> ToolResult:
        """
        Execute a tool call, respecting tool tier permissions.
        Routes to: Calseta API (internal), MCP server, or workflow execution.
        """
        ...
```

#### Agent Home Directory

> **Paperclip ref:** `/server/src/home-paths.ts` (path resolution), `/server/src/storage/local-disk-provider.ts`, `s3-provider.ts`, `provider-registry.ts` (pluggable storage backends). Paperclip uses `resolvePaperclipHomeDir()` → `resolveDefaultAgentWorkspaceDir(agentId)`. Calseta adapts this to `$CALSETA_DATA_DIR/agents/<agent_registration_id>/`.

> [!important] Cloud Deployment: Persistent Storage Required
> The agent home directory must survive container restarts. For local/single-node deployments, local disk is fine. For AWS ECS (Fargate), the directory must be backed by **EFS** (Amazon Elastic File System) mounted at `CALSETA_DATA_DIR`. For Azure Container Apps, use an Azure Files share. For GCP Cloud Run, use Filestore. Self-hosted Docker with bind mounts also works.
>
> The storage backend is abstracted via a `StorageProvider` ABC (same pattern as Paperclip's `/server/src/storage/provider-registry.ts`):
> - `LocalDiskProvider` — default, for single-node / docker-compose deployments
> - `S3Provider` — for artifact storage (artifacts/ subdirectory only) on AWS. Works with any S3-compatible object store (MinIO, Cloudflare R2).
> - `EFSProvider` — EFS mount for full directory persistence on ECS (configured via CALSETA_DATA_DIR pointing to EFS mount point)
>
> Cross-ref: cloud deployment architecture is in the Cloud Deployment PRD (`docs/plans/cloud-native-deployment.md`). EFS mount configuration is in that PRD's ECS task definition specs.

Each managed agent gets a persistent home directory (`AGENT_HOME`) for file-based storage that survives across heartbeats. This is where agents store working files, investigation notes, memory, and intermediate artifacts.

```
$CALSETA_DATA_DIR/agents/<agent_registration_id>/
├── memory/              # Agent-writable persistent memory (see Agent Persistent Memory)
│   ├── YYYY-MM-DD.md    # Daily investigation notes
│   └── entities/        # Learned facts about recurring entities (IPs, users, hosts)
├── workspace/           # Temporary working files (cleared per investigation)
├── config/              # Agent-specific config files (operator-managed)
└── artifacts/           # Investigation artifacts (exported reports, timelines)
```

> Cross-ref: The `memory/` subdirectory is used by the Agent Persistent Memory system in [Part 3: Knowledge & Memory].

**How it works:**

- `AGENT_HOME` is set as an environment variable for both managed and external agents
- For managed agents: Calseta creates the directory structure at agent creation time. The runtime engine sets `AGENT_HOME` before each invocation.
- For external agents: `AGENT_HOME` is communicated via the agent API key metadata. The agent is responsible for managing its own directory.
- The `memory/` subdirectory is special: its contents can be injected into Layer 6 (Runtime Checkpoint) of the prompt construction system. The runtime reads memory files and includes relevant entries.
- The `workspace/` subdirectory is ephemeral per-investigation. When a new alert is checked out, the workspace is cleared (previous investigation's temp files don't leak).
- The `artifacts/` subdirectory persists across investigations. Agents can store generated reports, timelines, and analysis outputs here for later retrieval via the operator UI or API.

**API surface:**

```
GET    /api/v1/agents/{uuid}/files/{path}       Read agent file (operator only)
PUT    /api/v1/agents/{uuid}/files/{path}       Write agent file (agent or operator)
DELETE /api/v1/agents/{uuid}/files/{path}       Delete agent file (operator only)
GET    /api/v1/agents/{uuid}/files              List agent files (operator only)
```

Agents write files via the existing filesystem (managed agents have direct access) or via the REST API (external agents). The API endpoints give operators visibility into what agents are storing.

**Supervision Loop:**

The runtime engine includes a supervision system that runs as a periodic Procrastinate task (`supervise_running_agents_task`), monitoring all active investigations:

```python
class AgentSupervisor:
    """Monitors running agents and enforces investigation guardrails."""

    async def supervise(self) -> SupervisionReport:
        """
        Periodic supervision loop (runs every 30s via Procrastinate scheduler).

        1. Stuck detection — agents with no heartbeat or tool call activity
           beyond their timeout_seconds. Kill agent, mark investigation
           as stuck, notify operator.
        2. Budget enforcement — check spent_monthly_cents against
           budget_monthly_cents AND per-alert cost against
           max_cost_per_alert_cents. Auto-pause on breach.
        3. Stall detection — check sub-agent invocation results against
           stall_threshold. Flag investigations producing no findings.
        4. Time enforcement — check investigation duration against
           max_investigation_minutes. Force escalation on timeout.
        5. Concurrency enforcement — verify no agent exceeds
           max_concurrent_alerts active assignments.
        """
        ...

    async def _handle_stuck_agent(self, agent: AgentRegistration, run: HeartbeatRun) -> None:
        """Cancel stuck agent, release alert back to queue or escalate."""
        ...

    async def _handle_budget_breach(self, agent: AgentRegistration) -> None:
        """Pause agent, notify operator with cost breakdown."""
        ...
```

The supervisor never makes LLM calls — it reads database state and enforces rules deterministically. All supervision actions are logged to `activity_log`.

**LLM Provider Abstraction:**

The runtime needs a thin adapter per LLM provider to normalize the conversation loop:

```python
class LLMProviderAdapter(ABC):
    """Adapts different LLM provider APIs to a common interface."""

    @abstractmethod
    async def create_message(self, messages: list, tools: list, **kwargs) -> LLMResponse:
        """Send messages + tools, get response (may include tool_use blocks)."""
        ...

    @abstractmethod
    def extract_cost(self, response: LLMResponse) -> CostInfo:
        """Extract input/output token counts from provider response."""
        ...
```

Initial adapters:

- `AnthropicAdapter` — Claude models via `anthropic` SDK. Supports extended thinking (`enable_thinking` flag). Provider value: `"anthropic"`.
- `OpenAIAdapter` — GPT models via `openai` SDK. Provider value: `"openai"`. 
- `AzureOpenAIAdapter` — Azure OpenAI via the same `openai` SDK with `base_url` pointing to the Azure endpoint. Azure AI Foundry models also use this adapter (they expose an OpenAI-compatible API). Provider value: `"azure_openai"`. Required config: `base_url` (Azure OpenAI endpoint), `api_version` in `config` JSONB.
- `AwsBedrockAdapter` — Claude models (and other models) on AWS Bedrock via `boto3` and the Bedrock Runtime API (`bedrock-runtime:InvokeModel`). Provider value: `"aws_bedrock"`. Uses standard AWS credential chain (IAM role, instance profile, env vars). Required config: `aws_region` in `config` JSONB. Model IDs use Bedrock format (e.g., `anthropic.claude-opus-4-5:0`). Install with `pip install calseta[aws]`.
- `ClaudeCodeAdapter` — Claude models via the local `claude` CLI subprocess. **No API key required** — uses the developer's Claude.ai subscription (`~/.claude/.credentials.json` OAuth auth). Provider value: `"claude_code"`. Intended for local development and testing; not recommended for production deployments where cost accountability matters. See full spec below.

> [!note] Azure AI Foundry vs. Azure OpenAI
> Azure AI Foundry (formerly Azure ML) and Azure OpenAI both expose OpenAI-compatible APIs. Use `AzureOpenAIAdapter` for both — the only difference is the `base_url`. Azure OpenAI: `https://{resource}.openai.azure.com/`. Azure AI Foundry: deployment-specific URL from the Foundry portal.

> [!note] Why not use Agent SDK / framework X?
> The runtime is intentionally thin — construct prompt, call API, handle tool calls, record cost. This is ~200 lines of code per provider adapter, not a framework. Using the raw SDKs means: no framework lock-in, full control over the conversation loop, exact token tracking, and the ability to add new providers without adopting their agent framework. The patterns are well-documented by both Anthropic and OpenAI.

#### `ClaudeCodeAdapter` — Local CLI Provider

> **Paperclip ref:** `/packages/adapters/claude-local/src/server/execute.ts` — Paperclip's `claude-local` adapter uses this exact pattern. The implementation below adapts it for Python.

The `ClaudeCodeAdapter` lets developers run the full agent stack against their personal Claude.ai subscription during local development and testing — no API key, no spend. The `claude` CLI handles auth transparently via `~/.claude/.credentials.json`.

**How it works:**

```python
class ClaudeCodeAdapter(LLMProviderAdapter):
    """
    Invokes the local `claude` CLI as a subprocess.
    Uses the developer's Claude.ai subscription — no API key needed.

    Paperclip ref: /packages/adapters/claude-local/src/server/execute.ts
    
    CLI invocation:
        claude --print - --output-format stream-json --verbose
               --model {model}
               --max-turns {max_turns}
               [--resume {session_id}]   # for session continuity across heartbeats

    The full prompt is passed via stdin. Claude emits newline-delimited JSON:
        system event  → session_id
        assistant event → tool_use / text blocks
        result event  → session_id, model, usage (input/output tokens), total_cost_usd
    """

    async def create_message(
        self,
        messages: list,
        tools: list,
        session_id: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        prompt = self._serialize_messages_to_prompt(messages, tools)
        args = [
            "--print", "-",
            "--output-format", "stream-json",
            "--verbose",
            "--model", self.model,
        ]
        if session_id:
            args += ["--resume", session_id]
        if self.max_turns:
            args += ["--max-turns", str(self.max_turns)]

        proc = await asyncio.create_subprocess_exec(
            "claude", *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(
            proc.communicate(input=prompt.encode()),
            timeout=self.timeout_seconds,
        )
        return self._parse_stream_json(stdout.decode())

    def extract_cost(self, response: LLMResponse) -> CostInfo:
        # `result` event contains total_cost_usd from the CLI
        # billing_type = "subscription" — logged in cost_events but NOT counted
        # against budget_monthly_cents by default (separate from paid API spend).
        # Override: set count_subscription_toward_budget = true in llm_integrations.config
        # to count it (useful for teams sharing a Max subscription budget).
        return CostInfo(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_cents=round(response.total_cost_usd * 100),
            billing_type="subscription",
        )

    async def test_environment(self) -> EnvironmentTestResult:
        """Verify claude CLI is installed and the user is logged in."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "claude", "auth", "status", "--output-format", "json",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            status = json.loads(stdout)
            if not status.get("loggedIn"):
                return EnvironmentTestResult(ok=False, message="claude CLI not logged in. Run: claude auth login")
            return EnvironmentTestResult(ok=True, message=f"Logged in as {status.get('email')} ({status.get('subscriptionType')})")
        except FileNotFoundError:
            return EnvironmentTestResult(ok=False, message="claude CLI not found. Install: https://claude.ai/code")
```

**`llm_integrations` registration for local dev:**

```json
{
  "name": "claude-local-dev",
  "provider": "claude_code",
  "model": "claude-sonnet-4-6",
  "api_key_ref": null,
  "base_url": null,
  "config": {
    "timeout_seconds": 300,
    "max_turns": 10,
    "count_subscription_toward_budget": false
  },
  "cost_per_1k_input_tokens_cents": 0,
  "cost_per_1k_output_tokens_cents": 0,
  "is_default": false
}
```

**Session continuity:** The `result` event from the CLI includes a `session_id`. This is stored in `agent_task_sessions.session_params` and passed as `--resume {session_id}` on subsequent heartbeats, enabling multi-turn conversation continuity across heartbeat runs — identical to how `AnthropicAdapter` resumes conversations via the Messages API.

**`billing_type` behavior in `cost_events`:**
- `billing_type = "subscription"` — tokens tracked for observability; cost in cents stored from `total_cost_usd`
- NOT counted toward `budget_monthly_cents` by default (subscription spend is separate from API spend)
- Set `count_subscription_toward_budget: true` in `llm_integrations.config` to opt in (useful for shared Max subscriptions with a team budget)

**When NOT to use:** Production deployments should use `AnthropicAdapter` (direct API) or `AwsBedrockAdapter`. `ClaudeCodeAdapter` is intended for local development and end-to-end testing only. The `test_environment()` check warns if `ANTHROPIC_API_KEY` is set (it overrides subscription auth).

**Investigation State:**

For multi-step investigations, the runtime tracks progress via an investigation plan (inspired by Vigil's `plan.md` pattern, but stored in DB):

```python
class InvestigationPlan:
    """Tracks agent progress through an investigation."""
    steps: list[InvestigationStep]  # Each step: description, status, result
    current_step: int
    started_at: datetime
    findings: list[Finding]
    proposed_actions: list[ProposedAction]
```

This is stored on `alert_assignments.investigation_state` (JSONB) and updated after each tool call loop iteration. If the agent crashes or times out, the orchestrator can see exactly where it stopped.

---

### Tool System

Tools are what agents can *do*. For managed agents, Calseta controls which tools are available and enforces permission tiers. For external agents, tools are accessed via Calseta's REST API and MCP server (already defined in existing Calseta).

#### Tool Tiers (Managed Agents)

Borrowed from Vigil's safety model, adapted for Calseta:


| Tier                | Permission                           | Examples                                                                                       | Approval Required                |
| ------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------- | -------------------------------- |
| `safe`              | Read-only, no side effects           | `get_alert`, `search_alerts`, `get_detection_rule`, `get_enrichment`, `list_context_documents` | No                               |
| `managed`           | Creates/updates Calseta records      | `post_finding`, `update_alert_status`, `create_case`, `add_timeline_entry`                     | No                               |
| `requires_approval` | External side effects or destructive | `execute_workflow`, `block_ip`, `disable_user`, `isolate_host`                                 | Yes (via existing approval gate) |
| `forbidden`         | Never allowed for autonomous agents  | `delete_alert`, `delete_agent`, `modify_agent_config`                                          | Blocked                          |


When a managed agent makes a tool call:

1. Runtime checks the tool's tier against the agent's `tool_ids` (allowed list)
2. If `requires_approval` → creates `agent_action` + `WorkflowApprovalRequest` → pauses agent until decision
3. If `forbidden` → returns error to agent, logged as security event
4. If `safe` or `managed` → executes immediately, returns result

> Cross-ref: `agent_action` creation and the approval flow are defined in [Part 2: Actions & Multi-Agent Orchestration].

#### Tool Registry

> **Paperclip ref:** `/server/src/services/plugin-tool-registry.ts`, `plugin-tool-dispatcher.ts`. Paperclip uses `RegisteredTool` with `name`, `namespacedName` (plugin:tool format), `displayName`, `description`, `parametersSchema`. Tool dispatch routes via `executeTool()` to the correct plugin worker.

Tools are registered in a new `agent_tools` table:

| Column          | Type        | Notes                                                                                                                  |
| --------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------- |
| `id`            | text        | PK — tool identifier ("get_alert", "block_ip", "search_siem")                                                          |
| `display_name`  | text        | NOT NULL — human label shown in UI                                                                                     |
| `description`   | text        | NOT NULL — **LLM-facing invocation instructions**. This IS the tool description passed in the tools array to the LLM. Write it as clear invocation guidance: what the tool does, when to use it, and what it returns. |
| `documentation` | text        | NULL — operator-facing markdown documentation: setup requirements, required API permissions (least privilege), configuration guide, examples. Separate from `description` which is LLM-facing. |
| `tier`          | enum        | `safe`, `managed`, `requires_approval`, `forbidden`                                                                    |
| `category`      | text        | NOT NULL — "calseta_api", "mcp", "workflow", "integration"                                                             |
| `input_schema`  | jsonb       | NOT NULL — JSON Schema for tool parameters (same format as Anthropic/OpenAI tool definitions)                          |
| `output_schema` | jsonb       | NULL — JSON Schema for tool output (for agent context)                                                                 |
| `handler_ref`   | text        | NOT NULL — how to execute: "calseta:get_alert", "mcp:splunk:search", "workflow:{uuid}", "integration:{integration_id}" |
| `is_active`     | boolean     | NOT NULL, default true                                                                                                 |
| `created_at`    | timestamptz | NOT NULL                                                                                                               |

> **Note on tool invocation instructions:** The `description` field is the primary mechanism for teaching the LLM how to use the tool. Write it as if you're explaining the tool to a smart analyst who has never used it: purpose, when to call it vs. similar tools, what the parameters mean, and what the response looks like. This is the same pattern as Anthropic's tool use documentation.

> **Note on integration documentation:** Every `ActionIntegration` tool must populate the `documentation` field with: required API permissions (least-privilege list), API key setup steps, what Calseta does with each permission, rate limits, and common failure modes. See `docs/integrations/{name}/SETUP.md` for the documentation template.


**Tool sources:**

1. **Calseta built-in** — Calseta's own API operations exposed as tools (get_alert, search_alerts, post_finding, update_status, etc.). These are auto-registered from existing API routes.
2. **MCP tools** — Tools from connected MCP servers (Splunk, CrowdStrike, VirusTotal, etc.). Auto-discovered from MCP server tool listings.
3. **Workflows as tools** — Existing Calseta workflows can be exposed as tools. Agent calls "run_ip_blocklist_workflow" → workflow executes via existing workflow engine.
4. **Custom tools** — Operator-defined tools (HTTP calls to internal APIs, custom scripts). Same pattern as Calseta's existing database-driven enrichment providers.

#### Agent ↔ Tool Assignment

When creating a managed agent, the operator selects which tools the agent can use from the tool registry. This is stored as `tool_ids` on `agent_registrations`. The runtime only presents these tools in the LLM prompt.

Example: A Triage Agent might get `[get_alert, search_alerts, get_enrichment, get_detection_rule, list_context_documents, post_finding, update_alert_status]` — all `safe` or `managed` tier. No `requires_approval` tools because triage shouldn't take containment actions.

An Orchestrator Agent gets additional tools: `[delegate_task, delegate_parallel, get_task_result, list_available_agents]` — the orchestration tools.

> Cross-ref: Orchestration tools are defined in [Part 2: Actions & Multi-Agent Orchestration].

---

### Alert Queue + Checkout

> Cross-ref: Full API contract for alert queue endpoints is in [Appendix: API Contract].

The alert queue bridges Calseta's enrichment pipeline with agent work. After enrichment, alerts are either pushed (existing webhook dispatch) or queued for pull-based checkout.

**Atomic checkout contract:**

```
POST /api/v1/queue/{alert_id}/checkout

Request:
{
  "expected_statuses": ["pending", "released"]
}

Success (200):
{
  "assignment_id": "uuid",
  "alert_id": "uuid",
  "agent_id": "uuid",
  "status": "in_progress",
  "alert": { ...full enriched alert payload... }
}

Conflict (409):
{
  "error": "alert_already_assigned",
  "current_assignee": "uuid",
  "current_status": "in_progress"
}
```

---

### Heartbeat and Monitoring

Heartbeat tracking is used to monitor agent liveness and detect stuck/crashed agents. The `heartbeat_runs` table (defined above) tracks each invocation lifecycle.

> Cross-ref: Full API contract for heartbeat endpoints is in [Appendix: API Contract]. Budget enforcement and supervision are part of the Agent Runtime Engine's supervision loop (above).

---

---

