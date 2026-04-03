---
created: 2026-03-16
project: Calseta
status: idea
priority: high
---
# Agent Control Plane — Orchestrate Security AI Agents from Calseta

## Problem

Calseta today has the foundation for agent interaction but stops short of full orchestration. **What exists:**

- **Agent registration** (`AgentRegistration` model) — agents register with name, webhook endpoint URL, encrypted auth headers, and trigger filters (source, severity, JSONB targeting rules)
- **Push-based dispatch** — after enrichment, Calseta POSTs full enriched payloads (alert + indicators + detection rules + context docs + workflows) to matching agents via webhooks
- **Dispatch audit trail** (`AgentRun` model) — every dispatch attempt recorded with request payload, response status, retries, timing
- **Trigger matching** — agents matched by `trigger_on_sources`, `trigger_on_severities`, and complex `trigger_filter` JSONB rules (same targeting syntax as context documents)
- **MCP tools** — agents can post findings back (`post_alert_finding`), update alert status, search alerts, and execute workflows (with approval gates)
- **Workflow approval system** — full approval gate with Slack/Teams/browser notifications, pluggable notifiers, async execution via Procrastinate

**What's missing — the control plane gap:**

- **No pull model** — agents can only receive pushed webhooks, not pull from a queue. No atomic checkout to prevent double-handling.
- **No response action orchestration** — agents can post findings and execute workflows, but can't propose containment/remediation actions (block IP, disable user, isolate host) with structured approval flows
- **No budget/cost tracking** — no visibility into how much LLM spend each agent is consuming
- **No heartbeat/liveness** — no way to know if an agent is healthy, stuck, or crashed
- **No multi-agent orchestration** — no mechanism for an orchestrator agent to delegate to specialist sub-agents and collect results
- **No LLM management** — agents manage their own LLM connections; no central model registry or cost-per-model tracking
- **No agent lifecycle management** — no pause/resume/terminate, no status tracking beyond active/inactive

This gap means security teams get alerts to their agents but can't govern what happens next. Meanwhile, closed-source "AI SOC" vendors (Dropzone, Prophet, Simbian, Torq) ship all of this as a black box.

**The opportunity:** extend Calseta's existing agent infrastructure from push-only dispatch to a **full control plane** — alert queuing, atomic checkout, response action orchestration, multi-agent delegation, budget controls, and operator visibility — while keeping the core philosophy intact (deterministic ops stay deterministic, intelligence stays in the agent).

## Inspiration

This PRD adapts concepts from [Paperclip](https://github.com/paperclipai/paperclip), an open-source control plane for AI-agent companies. Paperclip provides agent registry, task assignment, approval gates, budget controls, heartbeat monitoring, and audit logging for autonomous AI workforces. We adapt these patterns for the security domain while preserving Calseta's identity as an open, framework-agnostic platform.

Key Paperclip concepts adopted:
- **Agent registry with API key auth** — agents authenticate and pull work
- **Atomic task checkout** — single-assignee model prevents double-handling
- **Approval gates** — human-in-the-loop before high-impact actions
- **Budget hard-stops** — auto-pause agents when token/cost limits hit
- **Heartbeat system** — monitor agent liveness and execution status
- **Adapter-agnostic design** — any agent runtime (Claude, GPT, custom scripts) can plug in
- **Activity logging** — every mutation auditable

Key Paperclip concepts **not** adopted:
- Org chart / reporting hierarchy (security agents are functional, not hierarchical)
- Company-as-first-class-object (Calseta is single-tenant — one deployment per org)
- Generic task/issue tracking (alerts and incidents are the work units)
- Kanban/board metaphor (security teams think in queues and incidents)

## Proposed Solution

Extend Calseta from a data layer with push-only dispatch into a **full agent platform**: control plane + built-in runtime. Calseta both **executes** managed agents (making LLM API calls via registered providers) and **orchestrates** external BYO agents (via HTTP/MCP). The existing push model continues to work — everything new is additive.

```
Existing Pipeline (unchanged):
  Ingest → Normalize → Enrich → Contextualize → Dispatch
                                                    │
                                    ┌───────────────┤
                                    ▼               ▼
                              EXISTING:          NEW:
                              Push (webhook)     Alert Queue (pull)
                              AgentRun audit     Atomic Checkout
                                                    │
                              Agent Platform:       ▼
                                LLM Providers  ← Register Anthropic, OpenAI, etc. with API keys
                                Agent Registry ← Agent definitions: prompt, tools, methodology, LLM provider
                                Agent Runtime  ← Calseta makes LLM API calls, executes tool loops
                                Alert Queue    ← Enriched alert becomes assignable task
                                Checkout       ← Agent atomically claims an alert (no double-handling)
                                Tool System    ← Tiered tools: safe / managed / requires_approval / forbidden
                                Action Engine  ← Agent proposes response action → Approval Gate → Execute
                                Budget Tracker ← Token/cost tracking per agent + per LLM, hard-stop limits
                                Orchestration  ← Orchestrator delegates to specialist sub-agents
                                Heartbeat      ← Monitor agent liveness, detect stuck/crashed agents
                                Audit Log      ← Extends existing ActivityEvent system
                                Operator UI    ← Dashboard: agents, approvals, costs, queue, investigations
                                                    │
                                              ┌─────┴─────┐
                                              ▼           ▼
                                        MANAGED       BYO (EXTERNAL)
                                        Calseta runs  Agent runs itself
                                        the LLM       calls back via
                                        conversation   HTTP/MCP
```

### Two Agent Modes

| | Managed Agent | BYO Agent |
|---|---|---|
| **Who makes LLM calls** | Calseta (via `llm_integrations`) | The agent itself |
| **System prompt** | Stored in Calseta DB, editable via API/UI | Agent's own |
| **Tools** | Calseta's tool system (tiered permissions) | Agent calls Calseta REST/MCP |
| **Cost tracking** | Automatic (Calseta sees every token) | Agent self-reports via `POST /api/v1/cost-events` |
| **How identified** | `llm_integration_id` is set, `execution_mode = 'managed'` | `llm_integration_id` is NULL, `execution_mode = 'external'` |
| **Use case** | Teams that want Calseta to handle everything | Teams with existing agents that just need the control plane |

### Core Philosophy Alignment

| Calseta Principle | How the Platform Honors It |
|---|---|
| Deterministic ops stay deterministic | Alert routing, tool permission checks, budget enforcement, approval routing — zero LLM tokens. Intelligence is only in agent execution. |
| Token optimization is first-class | Budget tracking and hard-stops are native. Managed agents give exact cost visibility (Calseta sees every API call). |
| Framework-agnostic | BYO agents can be built with any framework. Managed agents use Calseta's runtime but the underlying LLM provider is swappable. |
| AI-readable documentation is a feature | Agent registry includes capability descriptions, methodologies, and system prompts — all surfaced via API for agent-to-agent discovery. |
| Self-hostable without pain | Runtime uses the same PostgreSQL + Procrastinate infrastructure. No new dependencies for managed agents beyond the LLM provider SDK. |

---

## Architecture

> **This PRD is organized into 5 Parts, each functioning as a self-contained section. Cross-references link between parts where dependencies exist.**
>
> - **Part 1:** Agent Control Plane (Core Runtime) — foundation
> - **Part 2:** Actions & Multi-Agent Orchestration — response + delegation
> - **Part 3:** Knowledge & Memory — organizational knowledge management
> - **Part 4:** Operational Management — non-alert work, scheduling, campaigns, topology
> - **Part 5:** Platform Operations (Auth, Secrets, UI) — auth, secrets, operator interface

---
---

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

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `name` | text | NOT NULL, UNIQUE — human label ("claude-opus", "haiku-fast", "gpt-4o") |
| `provider` | text | NOT NULL — "anthropic", "openai", "google", "azure_openai", "ollama" |
| `model` | text | NOT NULL — "claude-opus-4-6", "claude-haiku-4-5-20251001", "gpt-4o", etc. |
| `api_key_ref` | text | NOT NULL — reference to secret storage (e.g., env var name or secret manager key) |
| `base_url` | text | NULL — override for self-hosted/proxy endpoints |
| `config` | jsonb | NULL — provider-specific settings (temperature, max_tokens defaults, etc.) |
| `cost_per_1k_input_tokens_cents` | int | NOT NULL — for budget tracking/estimation |
| `cost_per_1k_output_tokens_cents` | int | NOT NULL — for budget tracking/estimation |
| `is_default` | boolean | NOT NULL, default false — if true, agents without explicit LLM config use this |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

Operators register LLM integrations at the instance level. Agents reference them by `llm_integration_id`. This gives:
- **Central API key management** — keys configured once, not per-agent
- **Cost tracking per model** — know exactly which model is burning budget
- **Easy model swaps** — change an integration's model without touching agent configs
- **Multiple providers** — use Opus for orchestrators, Haiku for focused specialists, GPT for specific tasks

> Cross-ref: API key storage uses the secrets system defined in [Part 5: Platform Operations].

#### `agent_registrations` (EXTEND EXISTING)

The existing `agent_registrations` table already has: `name`, `description`, `endpoint_url`, `auth_header_name`, `auth_header_value_encrypted`, `trigger_on_sources`, `trigger_on_severities`, `trigger_filter`, `timeout_seconds`, `retry_count`, `is_active`, `documentation`. The control plane adds these columns:

| New Column | Type | Notes |
|---|---|---|
| `execution_mode` | enum | `managed`, `external` — default `external` (backwards-compatible). `managed` = Calseta runs the agent. `external` = agent runs itself. |
| `agent_type` | enum | `orchestrator`, `specialist`, `standalone` — default `standalone` (backwards-compatible with existing agents) |
| `role` | text | NULL — functional role ("triage", "enrichment", "response", "investigation", "detection_engineering") |
| `capabilities` | jsonb | NULL — structured capability declarations for specialists (see Multi-Agent Orchestration) |
| `status` | enum | `active`, `paused`, `idle`, `running`, `error`, `terminated` — replaces boolean `is_active` |
| `adapter_type` | enum | NULL — `http`, `mcp`, `webhook` — default `webhook` (existing behavior). NULL = legacy webhook mode. For managed agents, this is ignored (Calseta runs the agent directly). |
| `adapter_config` | jsonb | NULL — adapter-specific config for http/mcp adapters. NULL = use existing endpoint_url/auth fields (webhook mode). |
| `llm_integration_id` | uuid | NULL — FK `llm_integrations.id`. **Required** for managed agents (Calseta uses this to make LLM API calls). NULL for external/BYO agents. |
| `system_prompt` | text | NULL — system prompt for managed agents. **Required** when `execution_mode = 'managed'`. NULL for external agents. |
| `methodology` | text | NULL — step-by-step investigation methodology (markdown). Injected into system prompt at runtime. Separating this from `system_prompt` allows reuse across agents and versioning. |
| `tool_ids` | text[] | NULL — which tools this managed agent can use (references `agent_tools.id`). NULL for external agents. |
| `max_tokens` | int | NULL — max output tokens per LLM call. NULL = use `llm_integrations.config` default. |
| `enable_thinking` | boolean | NOT NULL, default false — enable extended thinking for this agent (Anthropic only). |
| `sub_agent_ids` | uuid[] | NULL — for orchestrators: which specialist agents this orchestrator can invoke |
| `max_sub_agent_calls` | int | NULL — for orchestrators: max sub-agent invocations per alert (cost safety) |
| `budget_monthly_cents` | int | NOT NULL, default 0 (0 = unlimited) |
| `spent_monthly_cents` | int | NOT NULL, default 0 |
| `budget_period_start` | timestamptz | NULL — start of current budget window (NULL = no budget tracking) |
| `last_heartbeat_at` | timestamptz | NULL |
| `max_concurrent_alerts` | int | NOT NULL, default 1 — how many alerts this agent can work simultaneously |
| `max_cost_per_alert_cents` | int | NOT NULL, default 0 (0 = unlimited) — per-alert budget cap. Investigation paused and operator notified if exceeded. Prevents runaway investigations on a single alert. |
| `max_investigation_minutes` | int | NOT NULL, default 0 (0 = unlimited) — time limit per investigation. Triggers escalation or forced resolution on timeout. |
| `stall_threshold` | int | NOT NULL, default 0 (0 = disabled) — number of consecutive sub-agent invocations returning no actionable findings before flagging investigation as stalling. |

> Cross-ref: `sub_agent_ids`, `max_sub_agent_calls`, `stall_threshold`, `capabilities`, and `agent_type` columns are used by the multi-agent orchestration system in [Part 2].

**Managed vs External — how the columns interact:**

| Column | Managed Agent | External Agent |
|---|---|---|
| `execution_mode` | `managed` | `external` |
| `llm_integration_id` | Required | NULL |
| `system_prompt` | Required | NULL |
| `methodology` | Optional (recommended) | NULL |
| `tool_ids` | Required (what tools can it use) | NULL |
| `adapter_type` | Ignored (Calseta runs it) | `webhook`, `http`, or `mcp` |
| `endpoint_url` | NULL | Required |

**Backwards compatibility:** Existing agents continue to work as-is. They get `execution_mode = 'external'`, `agent_type = 'standalone'`, `adapter_type = 'webhook'`, `status = 'active'` (migrated from `is_active`). The existing push-based dispatch (`dispatch_to_agent()`) uses the same `endpoint_url` and trigger matching. New control plane features are opt-in via the new columns.

**Migration path for `is_active` → `status`:**
```sql
-- Migrate existing boolean to enum
UPDATE agent_registrations SET status = CASE WHEN is_active THEN 'active' ELSE 'paused' END;
-- Then drop is_active column after verifying
```

**Status state machine:**
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

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `agent_registration_id` | int | FK `agent_registrations.id`, NOT NULL |
| `name` | text | NOT NULL — human label ("production-key-1") |
| `key_prefix` | text | NOT NULL — first 8 chars for identification |
| `key_hash` | text | NOT NULL — bcrypt/argon2 hash |
| `scopes` | jsonb | NOT NULL — array of allowed scopes (see Permission Matrix) |
| `last_used_at` | timestamptz | NULL |
| `revoked_at` | timestamptz | NULL |
| `created_at` | timestamptz | NOT NULL |

> Cross-ref: Permission matrix and run-scoped JWTs for managed agents are in [Part 5: Platform Operations].

#### `alert_assignments` (NEW)

Maps alerts to agents. This is the atomic checkout table — the bridge between Calseta's existing alert model and the agent work queue. Complements the existing `AgentRun` table (which tracks push-based dispatch attempts) by tracking pull-based agent work.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `alert_id` | int | FK `alerts.id`, NOT NULL |
| `agent_registration_id` | int | FK `agent_registrations.id`, NOT NULL |
| `status` | enum | `assigned`, `in_progress`, `pending_review`, `resolved`, `escalated`, `released` |
| `checked_out_at` | timestamptz | NOT NULL |
| `started_at` | timestamptz | NULL |
| `completed_at` | timestamptz | NULL |
| `resolution` | text | NULL — free-text resolution summary |
| `resolution_type` | enum | NULL — `true_positive`, `false_positive`, `benign`, `inconclusive` |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

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

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `agent_registration_id` | int | FK `agent_registrations.id`, NOT NULL |
| `alert_id` | uuid | NULL — FK `alerts.id`. NULL for non-alert work (issues, scheduled tasks). |
| `task_key` | text | NOT NULL — composite key for session lookup (e.g., `alert:{alert_id}`, `issue:{issue_id}`, `routine:{routine_id}`). UNIQUE constraint on (agent_registration_id, task_key). |
| `session_params` | jsonb | NOT NULL — adapter-specific session state. For managed agents: conversation history reference, tool call state. For external agents: opaque blob the agent controls. |
| `session_display_id` | text | NULL — human-readable session identifier |
| `total_input_tokens` | int | NOT NULL, default 0 — cumulative input tokens across all heartbeats in this session |
| `total_output_tokens` | int | NOT NULL, default 0 — cumulative output tokens |
| `total_cost_cents` | int | NOT NULL, default 0 — cumulative cost for this session |
| `heartbeat_count` | int | NOT NULL, default 0 — number of heartbeats in this session |
| `last_run_id` | uuid | NULL — FK `heartbeat_runs.id` |
| `last_error` | text | NULL |
| `compacted_at` | timestamptz | NULL — when session was last compacted (conversation summarized) |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

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

| Setting | Default | Notes |
|---|---|---|
| `session_compaction_threshold_pct` | 80 | Percentage of model's context window that triggers compaction |
| `session_compaction_strategy` | `summarize` | `summarize` (LLM generates summary) or `truncate` (keep last N turns) |
| `session_max_heartbeats` | 0 (unlimited) | Force compaction after N heartbeats regardless of token count |

These are stored as optional fields in `agent_registrations.adapter_config` or a new `session_config` JSONB column.

#### `heartbeat_runs`

Track agent invocation lifecycle.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `agent_registration_id` | int | FK `agent_registrations.id`, NOT NULL |
| `source` | enum | `scheduler`, `manual`, `dispatch`, `callback` |
| `status` | enum | `queued`, `running`, `succeeded`, `failed`, `cancelled`, `timed_out` |
| `started_at` | timestamptz | NULL |
| `finished_at` | timestamptz | NULL |
| `error` | text | NULL |
| `alerts_processed` | int | NOT NULL, default 0 |
| `actions_proposed` | int | NOT NULL, default 0 |
| `context_snapshot` | jsonb | NULL — what context was provided to the agent |
| `created_at` | timestamptz | NOT NULL |

#### `cost_events`

Token and cost tracking per agent interaction.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `agent_registration_id` | int | FK `agent_registrations.id`, NOT NULL |
| `llm_integration_id` | uuid | NULL — FK `llm_integrations.id` (auto-populated for Calseta-managed agents) |
| `alert_id` | uuid | NULL — FK `alerts.id` |
| `invocation_id` | uuid | NULL — FK `agent_invocations.id` (links cost to specific sub-agent call) |
| `heartbeat_run_id` | uuid | NULL — FK `heartbeat_runs.id` |
| `provider` | text | NOT NULL — "anthropic", "openai", "google", etc. |
| `model` | text | NOT NULL — "claude-opus-4-6", "claude-haiku-4-5-20251001", "gpt-4o", etc. |
| `input_tokens` | int | NOT NULL, default 0 |
| `output_tokens` | int | NOT NULL, default 0 |
| `cost_cents` | int | NOT NULL |
| `occurred_at` | timestamptz | NOT NULL |
| `created_at` | timestamptz | NOT NULL |

> Cross-ref: `invocation_id` links to `agent_invocations` defined in [Part 2].

#### `activity_log`

Audit trail for every mutation in the control plane.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `actor_type` | enum | `agent`, `user`, `system` |
| `actor_id` | text | NOT NULL — agent UUID or user email |
| `action` | text | NOT NULL — "alert.checkout", "action.proposed", "action.approved", "agent.paused", etc. |
| `entity_type` | text | NOT NULL — "alert", "agent", "action", "assignment" |
| `entity_id` | uuid | NOT NULL |
| `details` | jsonb | NULL — additional context |
| `created_at` | timestamptz | NOT NULL, default now() |

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

| Layer | Typical allocation | Notes |
|---|---|---|
| System prompt | 5-10% | Static, well-optimized |
| Methodology | 5-10% | Structured playbook |
| KB context | 10-20% | Dynamic, prioritized |
| Alert/task context | 20-40% | Scales with enrichment depth |
| Session state | 10-30% | Grows across heartbeats, compacted when large |
| Runtime checkpoint | 1-2% | Small, injected at boundaries |
| **Remaining for agent reasoning + tool calls** | **20-40%** | Must be sufficient for useful work |

The runtime engine monitors total prompt size and warns (or auto-compacts) if the remaining space for agent reasoning drops below a configurable minimum (default: 20% of context window).

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
- `AnthropicAdapter` — Claude models via `anthropic` SDK (supports extended thinking)
- `OpenAIAdapter` — GPT models via `openai` SDK (compatible with Azure OpenAI via `base_url`)

> [!note] Why not use Agent SDK / framework X?
> The runtime is intentionally thin — construct prompt, call API, handle tool calls, record cost. This is ~200 lines of code per provider adapter, not a framework. Using the raw SDKs means: no framework lock-in, full control over the conversation loop, exact token tracking, and the ability to add new providers without adopting their agent framework. The patterns are well-documented by both Anthropic and OpenAI.

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

| Tier | Permission | Examples | Approval Required |
|---|---|---|---|
| `safe` | Read-only, no side effects | `get_alert`, `search_alerts`, `get_detection_rule`, `get_enrichment`, `list_context_documents` | No |
| `managed` | Creates/updates Calseta records | `post_finding`, `update_alert_status`, `create_case`, `add_timeline_entry` | No |
| `requires_approval` | External side effects or destructive | `execute_workflow`, `block_ip`, `disable_user`, `isolate_host` | Yes (via existing approval gate) |
| `forbidden` | Never allowed for autonomous agents | `delete_alert`, `delete_agent`, `modify_agent_config` | Blocked |

When a managed agent makes a tool call:
1. Runtime checks the tool's tier against the agent's `tool_ids` (allowed list)
2. If `requires_approval` → creates `agent_action` + `WorkflowApprovalRequest` → pauses agent until decision
3. If `forbidden` → returns error to agent, logged as security event
4. If `safe` or `managed` → executes immediately, returns result

> Cross-ref: `agent_action` creation and the approval flow are defined in [Part 2: Actions & Multi-Agent Orchestration].

#### Tool Registry

Tools are registered in a new `agent_tools` table:

| Column | Type | Notes |
|---|---|---|
| `id` | text | PK — tool identifier ("get_alert", "block_ip", "search_siem") |
| `display_name` | text | NOT NULL — human label |
| `description` | text | NOT NULL — description passed to LLM in tool schema |
| `tier` | enum | `safe`, `managed`, `requires_approval`, `forbidden` |
| `category` | text | NOT NULL — "calseta_api", "mcp", "workflow", "integration" |
| `input_schema` | jsonb | NOT NULL — JSON Schema for tool parameters |
| `output_schema` | jsonb | NULL — JSON Schema for tool output (for agent context) |
| `handler_ref` | text | NOT NULL — how to execute: "calseta:get_alert", "mcp:splunk:search", "workflow:{uuid}" |
| `is_active` | boolean | NOT NULL, default true |
| `created_at` | timestamptz | NOT NULL |

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

# Part 2: Actions & Multi-Agent Orchestration

> **Dependencies:** Part 1 (Core Runtime)
> **Implementation:** Phase 2, Phase 3, Phase 5

---

### Data Model

#### `agent_actions`

Actions proposed or executed by agents. Leverages Calseta's **existing approval system** (`WorkflowApprovalRequest`, pluggable notifiers, Procrastinate task queue) rather than building a parallel approval flow.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `alert_id` | uuid | FK `alerts.id`, NOT NULL |
| `agent_registration_id` | int | FK `agent_registrations.id`, NOT NULL |
| `assignment_id` | uuid | FK `alert_assignments.id`, NOT NULL |
| `action_type` | enum | `containment`, `remediation`, `notification`, `escalation`, `enrichment`, `investigation`, `user_validation`, `custom` |
| `action_subtype` | text | NOT NULL — specific action ("block_ip", "disable_user", "isolate_host", "send_slack", "create_ticket") |
| `status` | enum | `proposed`, `approved`, `rejected`, `executing`, `completed`, `failed`, `cancelled` |
| `payload` | jsonb | NOT NULL — action parameters (IP to block, user to disable, message to send, etc.) |
| `approval_request_id` | int | NULL — FK `workflow_approval_requests.id`, set when approval is required |
| `execution_result` | jsonb | NULL — result from integration execution |
| `executed_at` | timestamptz | NULL |
| `created_at` | timestamptz | NOT NULL |

> Cross-ref: `assignment_id` references `alert_assignments` from [Part 1].

**How this integrates with the existing approval system:**

Calseta already has a production-ready approval gate with:
- `WorkflowApprovalRequest` model (status lifecycle: `pending → approved/rejected/expired`)
- Pluggable notifier system (`SlackApprovalNotifier` with interactive buttons, `TeamsApprovalNotifier`, `NullApprovalNotifier`)
- Browser-based approval page (token-authenticated, no API key needed)
- Async execution via Procrastinate task queue (returns 202, executes in background)
- Confidence scores, risk levels, responder tracking, activity audit trail
- Per-workflow approval modes: `always`, `agent_only`, `never`

**Rather than duplicating this, the control plane extends it:**

1. When an agent proposes an action, the system creates an `agent_actions` row AND a `WorkflowApprovalRequest` (if approval is needed based on the workflow's `approval_mode`)
2. The existing notifier system (Slack buttons, Teams cards, browser page) handles the human review UX — no new notification code needed
3. The existing `process_approval_decision()` function handles approve/reject, then triggers execution of the response action via a new Procrastinate task (`execute_response_action_task`)
4. The existing activity event system logs all decisions automatically

**Changes needed to the existing approval system:**

- Extend `WorkflowApprovalRequest.trigger_context` to store response action metadata (action_type, action_subtype, payload, agent_id, assignment_id)
- Add a new `trigger_type` value: `"agent_action"` (alongside existing `"agent"`, `"human"`)
- Add a new Procrastinate task `execute_response_action_task` that runs the `ActionIntegration` after approval (parallel to existing `execute_approved_workflow_task`)
- Extend notifier message templates to show response action details (what action, against what target, agent confidence/reasoning)
- Add `action_type`-based approval mode logic: containment/remediation default to `always`, notification/escalation/enrichment/investigation default to `never`

**Status state machine:**
```
proposed → pending_approval (approval required, WorkflowApprovalRequest created)
proposed → executing (no approval required, auto-execute)
pending_approval → approved → executing (human approves via existing Slack/Teams/browser flow)
pending_approval → rejected (human rejects)
pending_approval → expired (approval timeout, existing expiry-on-read logic)
executing → completed (integration returns success)
executing → failed (integration returns error)
proposed → cancelled (agent or operator cancels)
```

#### Approval Policy Defaults by Action Type

The existing per-workflow `approval_mode` field (`always`/`agent_only`/`never`) handles most cases. For finer-grained control over response actions, we extend the workflow model or add a lightweight config:

| Action Type | Default Approval Mode | Rationale |
|---|---|---|
| `containment` | `always` | Blocking IPs, isolating hosts = high-impact |
| `remediation` | `always` | Disabling users, revoking sessions = high-impact |
| `notification` | `never` | Sending Slack messages, creating tickets = low-risk |
| `escalation` | `never` | Routing to human = inherently safe |
| `enrichment` | `never` | Additional lookups = low-risk |
| `investigation` | `never` | Reading logs, querying SIEMs = low-risk |
| `user_validation` | `never` | Outbound Slack DM to user for activity confirmation = low-risk, automated |

#### Confidence-Scored Auto-Approval (Override Layer)

When `approval_mode` resolves to `always` or `agent_only`, the agent's `confidence` score on the proposed action can further refine the approval routing. This is an **override layer on top of action-type defaults** — it only applies when approval would otherwise be required.

| Confidence Range | Approval Behavior | Rationale |
|---|---|---|
| `0.95–1.00` | **Auto-approve** — execute immediately, log as auto-approved | Critical threat confirmed (ransomware, active C2). Speed matters more than review. |
| `0.85–0.94` | **Quick review** — notify operator, 15-minute approval window, auto-approve on expiry | High confidence (confirmed malware, impossible travel). Operator can override within window. |
| `0.70–0.84` | **Human approval required** — standard approval flow via Slack/Teams/browser | Moderate confidence (suspicious but not confirmed). Human judgment needed. |
| `< 0.70` | **Block auto-execution** — action stays `proposed`, agent instructed to gather more evidence | Insufficient evidence. Forcing the agent to investigate further prevents false positives from triggering containment. |

> [!note] Confidence thresholds are configurable
> The thresholds above are defaults. Operators can adjust per-action-type or per-integration via config (e.g., "never auto-approve `disable_user` regardless of confidence" or "lower the quick-review threshold to 0.80 for `block_ip`"). This is stored as optional `confidence_thresholds` JSONB on `ActionIntegration` config — not a separate table.

> [!note] Implementation Note
> The simplest approach: each `ActionIntegration` declares its default `approval_mode` and optional `confidence_thresholds`. Operators can override per-integration via config. This avoids a separate `approval_policies` table — the existing workflow approval infrastructure handles everything. The confidence override is evaluated in the action proposal handler before creating a `WorkflowApprovalRequest`.

#### `agent_invocations`

Tracks parent→child agent delegation. When an orchestrator invokes a specialist sub-agent, this records the full lifecycle.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `parent_agent_id` | int | FK `agent_registrations.id`, NOT NULL — the orchestrator |
| `child_agent_id` | int | FK `agent_registrations.id`, NOT NULL — the specialist |
| `alert_id` | uuid | FK `alerts.id`, NOT NULL |
| `assignment_id` | uuid | FK `alert_assignments.id`, NOT NULL |
| `task_description` | text | NOT NULL — what the orchestrator asked for |
| `input_context` | jsonb | NOT NULL — structured input passed to sub-agent |
| `output_result` | jsonb | NULL — sub-agent's findings (populated on completion) |
| `status` | enum | `queued`, `running`, `completed`, `failed`, `timed_out`, `cancelled` |
| `cost_cents` | int | NOT NULL, default 0 — rolled up from sub-agent's cost_events |
| `started_at` | timestamptz | NULL |
| `completed_at` | timestamptz | NULL |
| `created_at` | timestamptz | NOT NULL |

**Constraints:**
- `parent_agent_id` must be an `orchestrator` type agent
- `child_agent_id` must be in the parent's `sub_agent_ids` array
- Depth is limited to 1 level in initial implementation (orchestrator → specialist only, no sub-sub-agents)

#### Required Indexes (Part 2)

```sql
CREATE INDEX idx_agent_actions_status ON agent_actions(status);
CREATE INDEX idx_agent_actions_assignment ON agent_actions(assignment_id);
CREATE INDEX idx_agent_actions_approval ON agent_actions(approval_request_id) WHERE approval_request_id IS NOT NULL;
CREATE INDEX idx_agent_invocations_parent ON agent_invocations(parent_agent_id, alert_id);
CREATE INDEX idx_agent_invocations_child ON agent_invocations(child_agent_id, status);
CREATE INDEX idx_agent_invocations_assignment ON agent_invocations(assignment_id);
CREATE INDEX idx_cost_events_invocation ON cost_events(invocation_id) WHERE invocation_id IS NOT NULL;
```

---

### Integration Execution Engine

When an approved action needs to execute (block IP, disable user, etc.), Calseta needs an execution layer. This builds on the existing plugin-based enrichment pattern.

#### Integration Interface

```python
class ActionIntegration(ABC):
    """Base class for action execution integrations."""

    @abstractmethod
    async def execute(self, action: AgentAction) -> ExecutionResult:
        """Execute the approved action."""
        ...

    @abstractmethod
    async def rollback(self, action: AgentAction) -> ExecutionResult:
        """Reverse the action if possible."""
        ...

    @abstractmethod
    def supported_actions(self) -> list[str]:
        """Return list of action_subtypes this integration handles."""
        ...
```

#### Initial Integrations (Phase 3)

| Integration | Actions | Target |
|---|---|---|
| CrowdStrike Falcon | `isolate_host`, `lift_containment` | Endpoint isolation |
| Microsoft Entra ID | `disable_user`, `revoke_sessions`, `force_mfa` | Identity response |
| Palo Alto Networks | `block_ip`, `block_domain`, `block_url` | Network containment |
| Slack | `send_alert`, `create_channel`, `notify_oncall`, `validate_user_activity` | Notification + User Validation |
| Jira / ServiceNow | `create_ticket`, `update_ticket` | Ticketing |
| Generic Webhook | `webhook_post` | Custom integrations |

> Cross-ref: Integration credentials use the secrets system in [Part 5: Platform Operations].

#### User Validation via Slack DM (Decentralized Alert Triage)

A key action type for reducing alert fatigue: **automated user validation**. When an alert involves user activity that may be legitimate (password change, new device login, MFA reset, OAuth app consent), an agent can propose a `user_validation` action that triggers a Slack DM to the affected user asking them to confirm or deny the activity.

**Flow:**
```
Alert: "Password changed for jsmith@corp.com"
  │
  ├─ Agent (or automation rule): proposes action:
  │   action_type: "user_validation"
  │   action_subtype: "validate_user_activity"
  │   payload: {
  │     "user_email": "jsmith@corp.com",
  │     "slack_user_id": "U12345",  (resolved via Slack directory lookup)
  │     "activity_description": "Your password was changed at 2:47 PM CT",
  │     "template": "activity_confirmation",
  │     "timeout_hours": 4
  │   }
  │
  ├─ SlackUserValidationIntegration executes:
  │   → DM sent to user with "Was this you?" + Yes/No buttons
  │   → Per-recipient tracking (sent/failed/acknowledged/denied)
  │
  ├─ User responds:
  │   ├─ "Yes, that was me" → auto-close alert, attach user response as finding
  │   └─ "No, that wasn't me" → escalate alert to team, attach response, bump severity
  │
  └─ No response within timeout → escalate for human review
```

**Implementation:** Extends the existing `SlackApprovalNotifier` pattern — same Slack app, same interactive button handling, different message template and callback behavior. The `SlackUserValidationIntegration` is an `ActionIntegration` that handles the `validate_user_activity` action subtype.

**Approval mode:** `user_validation` defaults to `never` (no operator approval needed to send a DM asking a user about their own activity). Operators can override to `always` if they want to review before outbound DMs are sent.

**Campaign System (Future — Phase 8+):**

For batch user validation (e.g., after a credential stuffing attack affecting 50 users), extend the `user_validation` action into a **campaign system**:

1. Slash command or API endpoint → select pre-approved template, audience (list of users), schedule
2. Approval gate → campaign posts to ops channel for review before sending
3. Batched delivery → DMs queued to Procrastinate task queue and sent in rate-limited batches; each recipient tracked individually with Slack message timestamp
4. Tracking → per-recipient status (sent/failed/acknowledged/denied), aggregate dashboard (X% confirmed, Y% denied, Z% no response)
5. Auto-triage → confirmed responses auto-close associated alerts; denied responses auto-escalate

This treats user validation like a mini email campaign system but native to Slack. Built on the same `ActionIntegration` infrastructure — the campaign is just N parallel `validate_user_activity` actions with shared tracking metadata.

> Cross-ref: Investigation campaigns (strategic objectives) are in [Part 4: Operational Management].

---

### Multi-Agent Orchestration

The core pattern: **Calseta routes alerts to orchestrators deterministically, then orchestrators drive specialist sub-agents dynamically.**

#### Agent Types

| Type | Purpose | Examples |
|---|---|---|
| **Orchestrator** | Receives alerts, decides investigation strategy, delegates to specialists, synthesizes findings, proposes response actions | Lead Investigator, Credential Theft Investigator, Malware Investigator |
| **Specialist** | Performs focused investigation tasks on demand from orchestrators, returns structured findings | SIEM Query Agent, Identity Agent, Endpoint Agent, Threat Intel Agent |

#### Alert Routing (Deterministic)

Calseta matches incoming alerts to orchestrators based on `alert_filter` rules — the same targeting rule syntax used by context documents. No LLM tokens burned on routing.

```
Alert arrives (enriched) → match against orchestrator alert_filters (by priority)
  → First match wins → alert queued for that orchestrator
  → No match → alert goes to default orchestrator (if configured) or manual queue
```

Multiple orchestrators can exist for different alert types:
- "Credential Theft Investigator" handles `credential_access`, `initial_access` alerts
- "Malware Investigator" handles `execution`, `persistence`, `defense_evasion` alerts
- "General Investigator" handles everything else (low priority, catches unmatched)

#### Investigation Flow (Dynamic, Wave-Structured)

Once an orchestrator checks out an alert, it drives the investigation using LLM reasoning. Investigations follow a **wave structure** — parallel specialist execution within each wave, with deterministic checkpoint evaluation between waves. The wave convention is expressed in the orchestrator's `methodology` field (markdown), not as rigid schema. The runtime engine enforces checkpoint rules at wave boundaries.

```
Wave 1 — Context Gathering (parallel):
  ├─ Identity Agent: user profile + recent activity
  ├─ SIEM Agent: related events in time window
  └─ Threat Intel Agent: deep IOC analysis
  └── CHECKPOINT: At least 2/3 specialists must return findings.
      If all return empty, flag as potential false positive.

Wave 2 — Scope Assessment (parallel, conditional):
  ├─ Endpoint Agent: process trees on affected hosts (if Wave 1 found lateral movement)
  ├─ SIEM Agent (follow-up): expanded entity search based on Wave 1 findings
  └─ Historical Context Agent: prior investigations involving same entities
  └── CHECKPOINT: If scope is expanding (new hosts/users discovered),
      inject escalation context before Wave 3.

Wave 3 — Response:
  ├─ Orchestrator synthesizes all findings → confidence + verdict
  ├─ Orchestrator proposes response actions
  └── CHECKPOINT: Approval gate (existing system) for containment/remediation.
```

**How waves work in practice:**

The orchestrator LLM decides the investigation flow — waves are a **methodology convention**, not a rigid execution engine. The `methodology` field on `agent_registrations` documents the expected wave structure in markdown. The runtime engine adds two deterministic behaviors:

1. **Wait-for-parallel**: When an orchestrator issues `delegate_parallel`, the runtime waits for all invocations to complete (or timeout) before returning results to the orchestrator. This is already the natural behavior of `delegate_parallel`.
2. **Checkpoint injection**: At configurable points (after parallel results return), the runtime can inject checkpoint context into the orchestrator's next prompt: "Budget status: $0.23 of $1.00 spent. Stall status: 0 empty results. Time: 2m of 10m elapsed." This gives the orchestrator situational awareness without requiring a separate governance agent.

The full step-by-step flow:

```
1. Orchestrator receives: enriched alert + sub-agent catalog (capabilities + descriptions)
2. Orchestrator reasons (LLM): "Based on this alert, I need to check X, Y, Z"
3. Orchestrator delegates: invoke specialists in parallel via MCP tools / REST API (Wave 1)
4. Specialists execute: each runs its focused task, returns structured JSON findings
5. Runtime injects checkpoint context: budget/stall/time status + severity flags
6. Orchestrator collects results, may delegate follow-up tasks based on findings (Wave 2)
7. Orchestrator synthesizes: produce overall finding + confidence + recommended actions
8. Orchestrator proposes response actions → existing approval system (Wave 3)
```

The orchestrator can adapt mid-investigation. If the SIEM agent finds lateral movement, the orchestrator can invoke the endpoint agent for additional hosts that weren't in the original alert. This is where LLM intelligence adds value — rigid workflows can't do this.

#### Investigation Checkpoints (Deterministic Guardrails)

While the orchestrator drives investigation dynamically via LLM reasoning, **deterministic checkpoints** prevent drift, runaway costs, and stuck investigations. These are enforced by the runtime engine — no LLM tokens burned on checkpoint evaluation.

| Checkpoint | Trigger | Action |
|---|---|---|
| **Budget** | Investigation cost exceeds `max_cost_per_alert_cents` | Pause investigation, notify operator, surface cost breakdown. Operator can raise limit and resume or force-close. |
| **Depth** | Sub-agent invocation count exceeds `max_sub_agent_calls` | Pause investigation, force orchestrator to synthesize with available findings or escalate. |
| **Stalling** | `stall_threshold` consecutive sub-agent invocations return no actionable findings | Flag investigation as stalling, notify operator. Orchestrator receives "investigation stalling — synthesize or escalate" injection before next LLM call. |
| **Time** | Investigation duration exceeds `max_investigation_minutes` | Force resolution or escalation. Same cancel flow as agent timeout. |
| **Severity Escalation** | Any specialist returns finding with `malice: Malicious` or detects lateral movement indicators | Runtime injects "re-evaluate priority and consider immediate escalation" prompt into orchestrator context before continuing. Does not pause — adds urgency context. |

> [!important] Checkpoints are deterministic, not governance agents
> These guardrails are platform-level controls evaluated by the runtime engine — not separate "governance agents" that burn tokens re-reading investigation context. This honors Calseta's core principle: deterministic operations stay deterministic. The orchestrator IS the governance layer for investigation quality; the platform provides the safety rails.

#### Capability Declarations

Specialists declare structured capabilities so orchestrators know what's available:

```json
{
  "capabilities": [
    {
      "name": "search_events",
      "description": "Run queries against SIEM to find related events within a time window",
      "input_schema": {
        "query": {"type": "string", "description": "KQL or SPL query"},
        "timerange_hours": {"type": "integer", "default": 24}
      },
      "output_schema": {
        "events": {"type": "array"},
        "count": {"type": "integer"},
        "query_executed": {"type": "string"}
      }
    },
    {
      "name": "build_timeline",
      "description": "Build chronological timeline of all activity for an entity",
      "input_schema": {
        "entity": {"type": "string"},
        "entity_type": {"type": "string", "enum": ["user", "host", "ip", "domain"]}
      },
      "output_schema": {
        "timeline": {"type": "array"},
        "earliest": {"type": "string"},
        "latest": {"type": "string"}
      }
    }
  ]
}
```

The orchestrator's system prompt includes the full sub-agent catalog. This is how it knows who to call and what to ask for.

#### Cost Rollup

Sub-agent costs roll up through the invocation chain:

```
Alert Investigation #ALT-2026-0847: Total cost $0.47
├─ Lead Investigator (claude-opus): $0.12 (reasoning + synthesis)
├─ Identity Agent (claude-haiku): $0.04
├─ SIEM Query Agent (claude-haiku): $0.08
│   └─ Follow-up SIEM query: $0.03
├─ Threat Intel Agent (claude-sonnet): $0.11
└─ Response recommendation: $0.09
```

This visibility is critical — operators can see exactly where investigation budget goes and optimize (e.g., "the threat intel agent is expensive, can we use a cheaper model?").

#### Example: Full Investigation Trace

```
Alert: "Suspicious login from TOR exit node for jsmith@corp.com"
  │
  ├─ Calseta pipeline: ingest → normalize → enrich (VT, AbuseIPDB) → contextualize
  │
  ├─ Routing: matches "credential_access" + severity "high"
  │  → routed to "Credential Theft Investigator" orchestrator
  │
  ├─ Orchestrator checks out alert, receives:
  │   - Full enriched alert payload
  │   - Sub-agent catalog: [identity, siem, endpoint, threat-intel, historical]
  │
  ├─ Orchestrator delegates (parallel):
  │   ├─ Identity Agent: "Full user profile + recent activity for jsmith@corp.com"
  │   ├─ SIEM Agent: "Auth events for jsmith last 48h + any TOR-related events"
  │   └─ Threat Intel Agent: "Deep dive on 185.220.101.42 beyond basic enrichment"
  │
  ├─ Results return:
  │   ├─ Identity: "IT admin, MFA enabled, last normal login Chicago 3h ago"
  │   ├─ SIEM: "2 failed logins from TOR, 1 success. 3 new OAuth app consents post-auth."
  │   └─ Threat Intel: "Known TOR exit, linked to credential stuffing campaigns"
  │
  ├─ Orchestrator adapts — OAuth consents are suspicious, needs more info:
  │   └─ SIEM Agent (follow-up): "List all OAuth app consents by jsmith last 24h"
  │      └─ Result: 3 unfamiliar apps consented in 10-minute window
  │
  ├─ Orchestrator synthesizes:
  │   "Confirmed compromise. Impossible travel (Chicago → TOR). Post-auth OAuth
  │    consents = persistence attempt. High confidence true positive."
  │
  ├─ Orchestrator proposes response actions:
  │   ├─ disable_user (jsmith@corp.com)        → requires approval
  │   ├─ revoke_sessions (jsmith@corp.com)     → requires approval
  │   ├─ revoke_oauth_apps ([3 apps])          → requires approval
  │   ├─ create_ticket (P1 incident)           → auto-approved
  │   └─ notify_oncall (#security-incidents)   → auto-approved
  │
  ├─ Slack notification fires with full context
  │   Operator sees: alert details + all sub-agent findings + reasoning + proposed actions
  │
  └─ Operator approves containment → actions execute via integrations
```

---
---

# Part 3: Knowledge & Memory

> **Dependencies:** Part 1 (Core Runtime)
> **Implementation:** Phase 6.5

---

### Data Model

#### `knowledge_base_pages` (NEW)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `slug` | text | NOT NULL, UNIQUE — URL-friendly identifier ("credential-theft-runbook", "siem-query-syntax") |
| `title` | text | NOT NULL |
| `body` | text | NOT NULL — markdown content |
| `folder` | text | NOT NULL, default '/' — hierarchical path ("/runbooks", "/policies", "/integrations") |
| `format` | text | NOT NULL, default 'markdown' |
| `status` | enum | `published`, `draft`, `archived` |
| `inject_scope` | jsonb | NULL — injection targeting rules. NULL = not injectable. Examples: `{"global": true}`, `{"roles": ["triage", "investigation"]}`, `{"agent_ids": ["uuid-1", "uuid-2"]}` |
| `inject_priority` | int | NOT NULL, default 0 — higher = injected first when token budget is tight |
| `inject_pinned` | boolean | NOT NULL, default false — pinned pages are always injected regardless of token budget |
| `sync_source` | jsonb | NULL — external sync config. NULL = locally authored. See External Sync below. |
| `sync_last_hash` | text | NULL — hash of last synced content (for change detection) |
| `synced_at` | timestamptz | NULL — last successful sync |
| `created_by_agent_id` | int | NULL — FK `agent_registrations.id` |
| `created_by_operator` | text | NULL |
| `updated_by_agent_id` | int | NULL |
| `updated_by_operator` | text | NULL |
| `latest_revision_id` | uuid | NULL — FK `kb_page_revisions.id` |
| `latest_revision_number` | int | NOT NULL, default 1 |
| `token_count` | int | NULL — estimated token count for budget planning |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

#### `kb_page_revisions` (NEW)

Revision history for every page edit.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `page_id` | uuid | FK `knowledge_base_pages.id`, NOT NULL |
| `revision_number` | int | NOT NULL |
| `body` | text | NOT NULL — full content at this revision |
| `change_summary` | text | NULL — what changed |
| `author_agent_id` | int | NULL |
| `author_operator` | text | NULL |
| `sync_source_ref` | text | NULL — external commit SHA or revision ID |
| `created_at` | timestamptz | NOT NULL |

#### `kb_page_links` (NEW)

Links KB pages to alerts, issues, investigations, and other pages for cross-referencing.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `page_id` | uuid | FK `knowledge_base_pages.id`, NOT NULL |
| `linked_entity_type` | enum | `alert`, `issue`, `page`, `agent`, `campaign` |
| `linked_entity_id` | uuid | NOT NULL |
| `link_type` | enum | `reference`, `source`, `generated_from`, `related` |
| `created_at` | timestamptz | NOT NULL |

> Cross-ref: `linked_entity_type = 'issue'` references issues from [Part 4]. `linked_entity_type = 'campaign'` references campaigns from [Part 4].

---

### Knowledge Base System

Calseta needs a structured knowledge base where agents and operators store, discover, and inject organizational knowledge. This unifies several needs: durable work products, injectable agent context, external knowledge sync, and cross-investigation learning.

#### Design Principles

1. **Markdown-native** — pages are markdown. Agents write markdown naturally. Operators read markdown easily.
2. **Context-injectable** — pages can be tagged for automatic injection into agent prompts (Layer 3 of prompt construction).
3. **Externally syncable** — pages can be read-only mirrors of GitHub wikis, Confluence spaces, or Notion databases.
4. **Agent-writable** — agents can create and update pages via tools, building organizational knowledge over time.
5. **Searchable** — full-text and semantic search across all pages.

> Cross-ref: Layer 3 of the 6-layer prompt construction system is in [Part 1: Agent Control Plane (Core Runtime)].

#### Context Injection Flow

When the runtime engine constructs an agent's prompt (Layer 3), it resolves injectable KB pages:

```python
def resolve_kb_context(agent: AgentRegistration) -> list[KBPage]:
    """Resolve KB pages to inject into this agent's prompt."""
    pages = []

    # 1. Global pages (inject_scope.global = true)
    pages += get_pages_where(inject_scope__global=True, status='published')

    # 2. Role-scoped pages (inject_scope.roles contains agent.role)
    pages += get_pages_where(inject_scope__roles__contains=agent.role, status='published')

    # 3. Agent-specific pages (inject_scope.agent_ids contains agent.id)
    pages += get_pages_where(inject_scope__agent_ids__contains=str(agent.id), status='published')

    # 4. Deduplicate, sort by: pinned first, then inject_priority DESC, then updated_at DESC
    pages = deduplicate_and_sort(pages)

    # 5. Token budget enforcement
    budget = agent.context_window_size * KB_CONTEXT_BUDGET_PCT  # e.g., 20%
    selected = []
    total_tokens = 0
    for page in pages:
        if page.inject_pinned or total_tokens + page.token_count <= budget:
            selected.append(page)
            total_tokens += page.token_count
    return selected
```

Each selected page is injected as:
```xml
<context_document title="Credential Theft Runbook" slug="credential-theft-runbook" updated="2026-03-15">
[page body in markdown]
</context_document>
```

#### External Sync

Pages can be read-only mirrors of external knowledge bases. Sync is pull-based (Calseta fetches from source on schedule).

##### Supported Sync Sources (Phase 1)

| Source | `sync_source` config | Sync mechanism |
|---|---|---|
| **GitHub** | `{ "type": "github", "repo": "org/repo", "path": "docs/runbooks/credential-theft.md", "branch": "main" }` | GitHub API (`GET /repos/{owner}/{repo}/contents/{path}`). Polls on schedule or webhook. |
| **GitHub Wiki** | `{ "type": "github_wiki", "repo": "org/repo", "page": "Credential-Theft-Runbook" }` | Clone wiki repo, read page. |
| **Confluence** | `{ "type": "confluence", "space_key": "SEC", "page_id": "12345", "base_url": "https://company.atlassian.net" }` | Confluence REST API (`GET /wiki/rest/api/content/{id}?expand=body.storage`). Convert storage format to markdown. |
| **Notion** | `{ "type": "notion", "page_id": "abc123", "database_id": null }` | Notion API. Convert blocks to markdown. |
| **URL** | `{ "type": "url", "url": "https://example.com/docs/runbook.md" }` | HTTP GET. Assumes markdown response. |

##### Sync Scheduler

A Procrastinate periodic task (`sync_kb_pages_task`) runs on a configurable interval (default: every 6 hours):

1. Scan all pages where `sync_source IS NOT NULL` and `status = 'published'`
2. For each page: fetch from source, compute content hash
3. If hash differs from `sync_last_hash`: update body, create revision, update hash and timestamp
4. If fetch fails: log error, skip (don't overwrite local content)
5. Activity log entry for every sync (success or failure)

Sync can also be triggered manually: `POST /api/v1/kb/sync` (all pages) or `POST /api/v1/kb/{id}/sync` (single page).

##### Sync Credentials

External sync sources that require authentication (GitHub private repos, Confluence, Notion) reference credentials via the secrets system. The `sync_source` config includes a `secret_ref` for the API key/token:

> Cross-ref: See [Part 5: Platform Operations] for the secrets system and `secret_ref` pattern.

```json
{
  "type": "confluence",
  "space_key": "SEC",
  "page_id": "12345",
  "base_url": "https://company.atlassian.net",
  "auth": { "type": "secret_ref", "secret_name": "confluence_api_token" }
}
```

#### Agent-Writable Pages

Agents create and update KB pages via tools:

```
create_kb_page     — Create a new KB page (managed tier)
update_kb_page     — Update an existing KB page (managed tier)
search_kb          — Search KB pages by keyword or semantic query (safe tier)
get_kb_page        — Read a KB page by slug (safe tier)
link_kb_page       — Link a KB page to an alert, issue, or other entity (managed tier)
```

**Common agent-authored pages:**
- Investigation summaries that become reusable knowledge ("TOR Exit Node Investigation Playbook" generated from a real investigation)
- Entity profiles built over time ("jsmith@corp.com Risk Profile" updated across multiple investigations)
- Detection rule documentation ("Rule XYZ: Purpose, Logic, Known FPs")
- Integration-specific query templates ("Splunk Queries for Credential Theft")

#### Search

Two search modes:

1. **Full-text search** — PostgreSQL `tsvector` index on `body` column. Fast, keyword-based.
2. **Semantic search** (Phase 8+) — Vector embeddings stored in `pgvector` column. Finds conceptually similar pages even when wording differs. Uses the same embedding model as Calseta's existing enrichment pipeline (if available).

```
GET /api/v1/kb/search?q=credential+theft+runbook          # full-text
GET /api/v1/kb/search?q=how+to+investigate+stolen+creds&mode=semantic  # semantic (Phase 8+)
```

#### KB API Surface

```
POST   /api/v1/kb                                  Create page
GET    /api/v1/kb                                  List pages (filterable by folder, status, inject_scope, sync_source)
GET    /api/v1/kb/{slug}                           Get page by slug
PATCH  /api/v1/kb/{slug}                           Update page
DELETE /api/v1/kb/{slug}                           Delete page (or archive)
GET    /api/v1/kb/{slug}/revisions                 List revisions
GET    /api/v1/kb/{slug}/revisions/{rev}           Get specific revision
POST   /api/v1/kb/{slug}/links                     Link page to entity
GET    /api/v1/kb/search                           Search pages
POST   /api/v1/kb/sync                             Trigger sync for all external pages
POST   /api/v1/kb/{slug}/sync                      Trigger sync for single page
GET    /api/v1/kb/folders                           List folder hierarchy
```

---

### Agent Persistent Memory

Agents build knowledge over time. A security agent that scans a codebase, maps a network topology, or profiles user behavior shouldn't re-learn this on every invocation. The persistent memory system lets agents store and retrieve durable facts.

#### Design

Memory is a specialized subset of the Knowledge Base — agent-writable, agent-readable, with automatic injection into prompt context. The key difference from general KB pages: memory is **private by default** and **agent-managed** (agents decide what to remember, the platform manages injection and staleness).

#### Memory Storage

Memory entries are stored in the existing `knowledge_base_pages` table with special conventions:

- `folder`: `/memory/agents/{agent_id}/` (agent-private) or `/memory/shared/` (promoted to shared)
- `inject_scope`: auto-set to target the owning agent. Shared memory auto-scoped to relevant roles.
- `status`: `published` (active memory) or `archived` (superseded/stale)
- `metadata`: includes `memory_type` (entity_profile, codebase_map, investigation_summary, pattern, preference), `staleness_ttl_hours`, `source_hash` (for invalidation)

#### Memory Tools (Agent-Facing)

```
save_memory        — Store a memory entry (managed tier). Params: title, body, memory_type, ttl_hours, source_context.
recall_memory      — Search agent's memory entries (safe tier). Params: query (keyword or semantic).
update_memory      — Update an existing memory entry (managed tier). Supersedes previous version.
promote_memory     — Promote private memory to shared (managed tier, requires operator approval if configured).
list_memories      — List agent's memory entries by type/recency (safe tier).
```

#### Memory Lifecycle

```
Agent creates memory ("save_memory")
  → stored in KB with agent-private scope
  → injected into Layer 6 of prompt construction on future heartbeats
  → ...
  → TTL expires or source changes
  → runtime marks as stale (not deleted, just deprioritized in injection)
  → agent can refresh (re-scan, update) or archive
```

> Cross-ref: Memory entries are injected into Layer 6 (Runtime Checkpoint) of the prompt construction system defined in [Part 1].

**Staleness detection:**
- **TTL-based**: each memory entry has a `staleness_ttl_hours`. After TTL, the entry is flagged as potentially stale. It's still available but injected with a `[STALE — last updated X hours ago]` prefix so the agent knows to verify before trusting.
- **Hash-based**: for codebase scans and file-based knowledge, the `source_hash` (e.g., git commit hash, file SHA) is compared at invocation time. If the source changed, the memory is flagged stale.

**Injection budget:** Memory entries compete for token budget within Layer 6 of prompt construction. Priority: non-stale > stale, recent > old, relevant (keyword match on current alert/issue) > general. The runtime caps memory injection at a configurable percentage of the context window (default: 5%).

#### Memory vs. Knowledge Base

| Aspect | Knowledge Base | Agent Memory |
|---|---|---|
| Primary author | Operators, external sync | Agents |
| Default visibility | Published (all can read) | Private (owning agent only) |
| Injection | Explicit (inject_scope tags) | Automatic (injected into owning agent) |
| Staleness | Manual (operator manages) | Automatic (TTL + hash-based) |
| Use case | Runbooks, policies, references | Learned facts, entity profiles, patterns |

Both use the same underlying storage (`knowledge_base_pages`) and revision system. Memory is a convention on top of KB, not a separate system.

---
---

# Part 4: Operational Management

> **Dependencies:** Part 1 (Core Runtime), Part 2 (Actions & Orchestration) for issue creation from investigations
> **Implementation:** Phase 5.5, Phase 8 (Campaigns)

---

### Data Model

#### `agent_issues` (NEW)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `identifier` | text | NOT NULL, UNIQUE — auto-generated (e.g., "CAL-001"). Uses instance-level counter. |
| `parent_id` | uuid | NULL — FK self-reference for subtasks |
| `alert_id` | uuid | NULL — FK `alerts.id`, if this issue originated from an alert investigation |
| `title` | text | NOT NULL |
| `description` | text | NULL — markdown |
| `status` | enum | `backlog`, `todo`, `in_progress`, `in_review`, `done`, `blocked`, `cancelled` |
| `priority` | enum | `critical`, `high`, `medium`, `low` — default `medium` |
| `category` | enum | `remediation`, `detection_tuning`, `investigation`, `compliance`, `post_incident`, `maintenance`, `custom` |
| `assignee_agent_id` | int | NULL — FK `agent_registrations.id` |
| `assignee_operator` | text | NULL — operator email (for human-assigned tasks) |
| `created_by_agent_id` | int | NULL — FK `agent_registrations.id` |
| `created_by_operator` | text | NULL — operator email |
| `checkout_run_id` | uuid | NULL — FK `heartbeat_runs.id`, atomic checkout (same pattern as alert assignments) |
| `execution_locked_at` | timestamptz | NULL |
| `routine_id` | uuid | NULL — FK `agent_routines.id`, if created by a routine |
| `due_at` | timestamptz | NULL |
| `started_at` | timestamptz | NULL — set when status transitions to `in_progress` |
| `completed_at` | timestamptz | NULL — set when status transitions to `done` |
| `cancelled_at` | timestamptz | NULL |
| `resolution` | text | NULL — free-text resolution summary |
| `metadata` | jsonb | NULL — extensible metadata |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

#### `agent_issue_comments` (NEW)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `issue_id` | uuid | FK `agent_issues.id`, NOT NULL |
| `author_agent_id` | int | NULL — FK `agent_registrations.id` |
| `author_operator` | text | NULL — operator email |
| `body` | text | NOT NULL — markdown |
| `created_at` | timestamptz | NOT NULL |

#### `agent_routines` (NEW)

Defines recurring work patterns for agents.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `name` | text | NOT NULL — human label ("Daily Threat Intel Triage", "Weekly FP Rate Review") |
| `description` | text | NULL — what this routine does |
| `agent_registration_id` | int | FK `agent_registrations.id`, NOT NULL — which agent runs this |
| `status` | enum | `active`, `paused`, `completed` |
| `concurrency_policy` | enum | `skip_if_active` (default), `coalesce_if_active`, `always_run` |
| `catch_up_policy` | enum | `skip_missed` (default), `catch_up` |
| `task_template` | jsonb | NOT NULL — template for the work item created per run: `{ title_template, description_template, priority }`. Mustache-style rendering with `{{routine.name}}`, `{{trigger.fired_at}}`, `{{trigger.payload}}`. |
| `max_consecutive_failures` | int | NOT NULL, default 3 — pause routine after N consecutive failures |
| `consecutive_failures` | int | NOT NULL, default 0 |
| `last_run_at` | timestamptz | NULL |
| `next_run_at` | timestamptz | NULL — computed from trigger schedule |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

#### `routine_triggers` (NEW)

Each routine can have one or more triggers (cron, webhook, manual).

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `routine_id` | uuid | FK `agent_routines.id`, NOT NULL |
| `kind` | enum | `cron`, `webhook`, `manual` |
| `cron_expression` | text | NULL — 5-field cron expression (required when kind=cron). Examples: `0 8 * * *` (daily 8am), `*/30 * * * *` (every 30 min). |
| `timezone` | text | NULL — IANA timezone for cron evaluation (default UTC) |
| `webhook_public_id` | text | NULL — public identifier for webhook URL (kind=webhook) |
| `webhook_secret_hash` | text | NULL — HMAC signing secret hash for webhook verification |
| `webhook_replay_window_sec` | int | NULL — reject webhooks older than this (default 300) |
| `next_run_at` | timestamptz | NULL — next scheduled fire time (cron only) |
| `last_fired_at` | timestamptz | NULL |
| `is_active` | boolean | NOT NULL, default true |
| `created_at` | timestamptz | NOT NULL |

#### `routine_runs` (NEW)

Tracks each execution instance of a routine.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `routine_id` | uuid | FK `agent_routines.id`, NOT NULL |
| `trigger_id` | uuid | FK `routine_triggers.id`, NOT NULL |
| `source` | enum | `cron`, `webhook`, `manual` |
| `status` | enum | `received`, `enqueued`, `running`, `completed`, `skipped`, `failed` |
| `trigger_payload` | jsonb | NULL — webhook payload or manual invocation context |
| `linked_alert_id` | uuid | NULL — if routine creates/processes an alert |
| `linked_issue_id` | uuid | NULL — if routine creates an issue (see Issue/Task System) |
| `heartbeat_run_id` | uuid | NULL — FK `heartbeat_runs.id`, the actual execution |
| `coalesced_into_run_id` | uuid | NULL — if skipped due to coalesce policy |
| `error` | text | NULL |
| `created_at` | timestamptz | NOT NULL |
| `completed_at` | timestamptz | NOT NULL |

#### `campaigns` (NEW)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `name` | text | NOT NULL — "Credential Theft MTTD Reduction", "Q2 Vulnerability Remediation" |
| `description` | text | NULL — markdown, strategic context and success criteria |
| `status` | enum | `planned`, `active`, `completed`, `cancelled` |
| `category` | enum | `detection_improvement`, `response_optimization`, `vulnerability_management`, `compliance`, `threat_hunting`, `custom` |
| `owner_agent_id` | int | NULL — FK `agent_registrations.id`, agent leading this campaign |
| `owner_operator` | text | NULL — operator email |
| `target_metric` | text | NULL — what metric this campaign targets (e.g., "mttd_credential_theft_min", "fp_rate_pct", "auto_resolve_pct") |
| `target_value` | numeric | NULL — target value for the metric |
| `current_value` | numeric | NULL — current measured value |
| `target_date` | timestamptz | NULL |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

#### `campaign_items` (NEW)

Links alerts, issues, and routines to campaigns for traceability.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `campaign_id` | uuid | FK `campaigns.id`, NOT NULL |
| `item_type` | enum | `alert`, `issue`, `routine` |
| `item_id` | uuid | NOT NULL — polymorphic FK (alert_id, issue_id, or routine_id) |
| `created_at` | timestamptz | NOT NULL |

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

| Routine | Schedule | Agent | Purpose |
|---|---|---|---|
| Daily Threat Intel Triage | `0 8 * * *` | Threat Intel Agent | Process overnight intel submissions |
| FP Rate Review | `0 9 * * 1` (Mon 9am) | Detection Eng Agent | Review detection rules with >20% FP rate |
| Posture Assessment | `0 6 1 * *` (1st of month) | Compliance Agent | Monthly security posture scan |
| SIEM Health Check | `*/30 * * * *` (every 30m) | SIEM Agent | Verify log sources are healthy |
| On-demand Sweep | webhook | Endpoint Agent | Triggered by external threat intel feed |

---

### Investigation Campaigns (Strategic Objectives)

While individual alerts are tactical, security teams also pursue strategic objectives: "Reduce credential theft MTTD to under 5 minutes", "Eliminate all critical vulnerability findings by Q2", "Achieve 95% auto-resolution rate for low-severity alerts." Investigation campaigns provide this strategic layer.

#### How It Works

Campaigns are lightweight containers that give strategic context to operational work:

1. Operator creates a campaign with a target metric and goal
2. Alerts, issues, and routines can be linked to campaigns
3. The campaign dashboard shows progress toward the target (metric value over time)
4. Agents can query campaign context to understand why they're doing work (e.g., "This detection tuning issue is part of the 'Reduce FP Rate' campaign targeting <10% FP rate by Q2")

Campaigns are optional. They don't affect execution — they add strategic visibility. This is a Phase 8+ feature but the data model is lightweight enough to include early.

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

# Part 5: Platform Operations (Auth, Secrets, UI)

> **Dependencies:** Part 1 (Core Runtime)
> **Implementation:** Phase 1 (Secrets, Auth), Phase 6 (UI)

---

### Data Model

#### `secrets` (NEW)

Instance-level encrypted secret storage with versioning.

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `name` | text | NOT NULL, UNIQUE — human label ("anthropic_api_key", "confluence_token", "crowdstrike_client_secret") |
| `description` | text | NULL |
| `provider` | enum | `local_encrypted` (default), `env_var`, `aws_secrets_manager`, `vault` |
| `external_ref` | text | NULL — reference for external providers (env var name, ARN, Vault path) |
| `latest_version` | int | NOT NULL, default 1 |
| `created_at` | timestamptz | NOT NULL |
| `updated_at` | timestamptz | NOT NULL |

#### `secret_versions` (NEW)

| Column | Type | Notes |
|---|---|---|
| `id` | uuid | PK |
| `secret_id` | uuid | FK `secrets.id`, NOT NULL |
| `version` | int | NOT NULL |
| `material` | jsonb | NOT NULL — encrypted payload (for `local_encrypted` provider). Contains `{ ciphertext, nonce, algorithm }`. |
| `value_sha256` | text | NOT NULL — hash of plaintext for integrity verification |
| `revoked_at` | timestamptz | NULL — NULL = active, non-NULL = revoked |
| `created_at` | timestamptz | NOT NULL |

---

### Auth and Permissions (Extended)

> [!note] This section extends the existing Auth and Permissions section with run-scoped JWTs and enhanced agent auth.

#### Operator Auth

Existing Calseta auth (API keys with scopes like `agents:read`, `agents:write`, `approvals:write`). Full read/write across all control plane resources. Every operator mutation writes to `activity_log` (extends existing `ActivityEvent` system).

#### Agent Auth

New agent-specific API keys (separate from operator API keys). Bearer token in `Authorization: Bearer calseta_agent_...` header. Scoped to one agent registration. This is the **inbound** auth (agent calling Calseta), distinct from the existing **outbound** auth (`auth_header_name` / `auth_header_value_encrypted` used when Calseta pushes TO agents).

**Permission matrix (basic):**

| Action | Operator | Agent |
|---|---|---|
| Create/manage agents | Yes | No |
| Pause/resume/terminate agents | Yes | No |
| Checkout alert from queue | Yes | Yes (own queue only) |
| Release alert | Yes | Yes (own assignments only) |
| Propose action | Yes | Yes |
| Approve/reject action | Yes | No |
| Report cost event | Yes | Yes (own agent only) |
| Delegate to sub-agent | No | Yes (orchestrators only, within `sub_agent_ids`) |
| Read sub-agent catalog | Yes | Yes (orchestrators only) |
| Set budget | Yes | No |
| Manage LLM integrations | Yes | No |
| View dashboard | Yes | No |
| View activity log | Yes | No |
| Read alerts (enriched) | Yes | Yes (checked-out or matching filter) |
| Read context documents | Yes | Yes |
| Read workflows | Yes | Yes |

#### Run-Scoped JWTs for Managed Agents

When the runtime engine invokes a managed agent, it creates a short-lived JWT scoped to that specific run. This provides per-invocation attribution without long-lived credentials.

**JWT Claims:**
```json
{
  "sub": "agent:<agent_registration_id>",
  "company_id": null,
  "agent_id": "<agent_registration_id>",
  "run_id": "<heartbeat_run_id>",
  "alert_id": "<alert_id or null>",
  "issue_id": "<issue_id or null>",
  "adapter_type": "managed",
  "scopes": ["queue:read", "queue:checkout", "actions:propose", "costs:report", "kb:read", "kb:write", "issues:read", "issues:write", "memory:read", "memory:write"],
  "iat": 1711756800,
  "exp": 1711929600
}
```

**Properties:**
- **Algorithm:** HMAC-SHA256 (symmetric, no external PKI needed)
- **Secret:** from `CALSETA_AGENT_JWT_SECRET` env var (generated at install time)
- **TTL:** 48 hours (configurable). Generous to cover long-running multi-wave investigations.
- **Scopes:** derived from agent's permissions. Orchestrators get additional scopes (`invocations:create`, `agents:catalog:read`).
- **Run attribution:** every API call from the agent is tied to a specific `run_id`, which ties to a specific alert/issue. Full audit chain.

**Why not use persistent API keys for managed agents?**
Managed agents run inside Calseta — they don't need long-lived keys. Run-scoped JWTs mean:
1. Credential exposure is time-limited (48h vs. permanent)
2. Every API call is attributed to a specific run (not just an agent)
3. No key management overhead for managed agents
4. If an agent is terminated, its JWT expires naturally

**Persistent API keys** (from existing PRD) remain for **external agents** — they need long-lived credentials to authenticate callbacks.

**Updated Auth Resolution Order:**
1. No auth header + local development mode → implicit operator
2. No auth header + production mode → try session cookie (existing Calseta auth)
3. `Authorization: Bearer calseta_agent_...` → agent API key lookup (external agents)
4. `Authorization: Bearer eyJ...` (JWT format) → verify JWT, extract agent context + run context
5. `Authorization: Bearer calseta_op_...` → operator API key (existing)

**Updated Permission Matrix (with JWT distinction):**

| Action | Operator | Agent (External, API Key) | Agent (Managed, JWT) |
|---|---|---|---|
| Create/manage agents | Yes | No | No |
| Pause/resume/terminate agents | Yes | No | No |
| Checkout alert from queue | Yes | Yes (own queue) | Yes (own queue) |
| Release alert | Yes | Yes (own assignments) | Yes (own assignments) |
| Propose action | Yes | Yes | Yes |
| Approve/reject action | Yes | No | No |
| Report cost event | Yes | Yes (own agent) | Automatic (runtime tracks) |
| Delegate to sub-agent | No | Yes (orchestrators) | Yes (orchestrators) |
| Read sub-agent catalog | Yes | Yes (orchestrators) | Yes (orchestrators) |
| Set budget | Yes | No | No |
| Manage LLM integrations | Yes | No | No |
| Manage secrets | Yes | No | No |
| View dashboard | Yes | No | No |
| View activity log | Yes | No | No |
| Read KB pages | Yes | Yes | Yes |
| Write KB pages | Yes | Yes (if permitted) | Yes |
| Write memory | N/A | Yes (own memory) | Yes (own memory) |
| Create issues | Yes | Yes | Yes |
| Manage routines | Yes | No | No |
| Read topology | Yes | Yes | Yes |

---

### Secrets Management (Extended)

The PRD's existing approach (LLM API keys stored as env var references) needs extension to cover all credential scenarios: agent env vars, integration credentials, KB sync tokens, webhook signing secrets, and routine webhook auth.

#### Secret References

Any configuration field that holds a credential can use a `secret_ref` instead of a plaintext value:

```json
// Plaintext (rejected for sensitive keys in strict mode)
{ "type": "plain", "value": "sk-ant-..." }

// Secret reference (preferred)
{ "type": "secret_ref", "secret_name": "anthropic_api_key", "version": "latest" }

// Environment variable reference
{ "type": "env_ref", "env_var": "ANTHROPIC_API_KEY" }
```

**Where secret_refs are used:**
- `llm_integrations.api_key_ref` — LLM provider API keys
- `agent_registrations.adapter_config.env` — agent environment variables
- `knowledge_base_pages.sync_source.auth` — KB sync credentials
- `routine_triggers.webhook_secret` — webhook signing secrets
- ActionIntegration configs — CrowdStrike, Entra ID, Palo Alto, Slack credentials

> Cross-ref: LLM integrations are in [Part 1]. KB sync credentials are in [Part 3]. Routine webhook secrets are in [Part 4]. ActionIntegration configs are in [Part 2].

#### Resolution at Runtime

```python
def resolve_secret(ref: dict) -> str:
    """Resolve a secret reference to its plaintext value."""
    if ref["type"] == "plain":
        return ref["value"]
    elif ref["type"] == "env_ref":
        return os.environ[ref["env_var"]]
    elif ref["type"] == "secret_ref":
        secret = get_secret(ref["secret_name"])
        version = secret.latest_version if ref.get("version") == "latest" else ref["version"]
        return decrypt(get_secret_version(secret.id, version).material)
```

Resolution happens at the last possible moment (just before invocation, not at config load time). Resolved values are never logged — the runtime tracks which keys were resolved and redacts them from heartbeat run logs.

#### Sensitive Key Detection

A regex pattern identifies keys that should never be stored as plaintext:

```python
SENSITIVE_KEY_PATTERN = re.compile(
    r'(api[-_]?key|access[-_]?token|auth[-_]?token|secret|password|credential|'
    r'jwt|private[-_]?key|client[-_]?secret|signing[-_]?key|bearer)',
    re.IGNORECASE
)
```

In strict mode (configurable, default off): any `adapterConfig.env` key matching this pattern that uses `{ "type": "plain" }` is rejected at creation time with an error directing the operator to use `secret_ref` instead.

#### Log Redaction

After secret resolution, the runtime maintains a set of resolved plaintext values. All heartbeat run logs (stdout, stderr, error messages) are scanned for these values and redacted with `[REDACTED:secret_name]` before storage.

#### Secrets API Surface

```
POST   /api/v1/secrets                             Create secret (returns plaintext once if local_encrypted)
GET    /api/v1/secrets                             List secrets (names only, no values)
GET    /api/v1/secrets/{name}                      Get secret metadata (no value)
POST   /api/v1/secrets/{name}/versions             Add new version (rotates secret)
DELETE /api/v1/secrets/{name}/versions/{version}   Revoke a version
DELETE /api/v1/secrets/{name}                      Delete secret (fails if referenced)
POST   /api/v1/secrets/{name}/verify               Verify secret is resolvable (returns hash, not value)
```

#### Provider Extensibility

Secret providers are pluggable via a provider interface:

```python
class SecretProvider(ABC):
    @abstractmethod
    async def store(self, name: str, value: str) -> StorageResult: ...

    @abstractmethod
    async def retrieve(self, name: str, version: int) -> str: ...

    @abstractmethod
    async def revoke(self, name: str, version: int) -> None: ...
```

Initial providers:
- `local_encrypted` — AES-256-GCM encrypted in PostgreSQL. Zero external dependencies. Good for self-hosted single-node.
- `env_var` — reads from environment variable. Good for container deployments with injected secrets.
- `aws_secrets_manager` (Phase 8+) — delegates to AWS Secrets Manager. Good for AWS-hosted deployments.
- `vault` (Phase 8+) — delegates to HashiCorp Vault. Good for enterprise deployments.

---

### Operator UI

New pages in Calseta's web UI (or new UI if Calseta doesn't have one yet — this would be the first major UI surface).

> [!important] UI is Top-Tier Priority
> The operator UI is the primary way security teams interact with the control plane. Every new feature introduced in this PRD needs a well-designed UI surface. A dedicated working session is required to spec every page, component, interaction, and data visualization in detail before implementation begins. The UI should be enterprise-grade — this is a security product used by SOC teams in high-pressure situations. Clarity, speed, and information density matter more than aesthetics.

#### Pages

| Route | Purpose | Part | New? |
|---|---|---|---|
| `/control-plane` | Dashboard — agent status, queue depth, pending approvals, costs, key metrics | All | Original |
| `/control-plane/agents` | Agent registry — list orchestrators + specialists, create, configure, pause/resume | [Part 1] | Original |
| `/control-plane/agents/new` | Create agent — choose type (orchestrator/specialist), assign LLM, configure capabilities | [Part 1] | Original |
| `/control-plane/agents/{id}` | Agent detail — config, heartbeat history, cost breakdown, assigned alerts/issues, sub-agent invocations, **session state**, **memory entries**, **PM view (tasks by status)** | [Part 1], [Part 3], [Part 4] | Enhanced |
| `/control-plane/agents/{id}/investigation/{alert_id}` | Investigation view — full tree of sub-agent invocations, findings, reasoning chain | [Part 2] | Original |
| `/control-plane/topology` | **Agent topology** — interactive graph of agent fleet: routing paths, delegation paths, capability map, health status | [Part 4] | **NEW** |
| `/control-plane/queue` | Alert queue — pending alerts, assignments, routing rules, status filters | [Part 1] | Original |
| `/control-plane/issues` | **Issue board** — non-alert work items by status (backlog/todo/in_progress/done), filterable by category, assignee, priority, linked alert | [Part 4] | **NEW** |
| `/control-plane/issues/{id}` | **Issue detail** — description, comments, linked alerts/KB pages, history, assignee, checkout status | [Part 4] | **NEW** |
| `/control-plane/actions` | Action feed — proposed, pending approval, approved, executed, failed | [Part 2] | Original |
| `/control-plane/approvals` | Approval inbox — extends existing `/v1/workflow-approvals` with response action context | [Part 2] | Original |
| `/control-plane/kb` | **Knowledge base** — browsable wiki with folder hierarchy, search, page list, external sync status | [Part 3] | **NEW** |
| `/control-plane/kb/{slug}` | **KB page detail** — rendered markdown, revision history, linked entities, injection scope config, sync status | [Part 3] | **NEW** |
| `/control-plane/kb/{slug}/edit` | **KB page editor** — markdown editor with preview, injection scope picker, external sync config | [Part 3] | **NEW** |
| `/control-plane/routines` | **Routines** — scheduled/recurring agent tasks with cron config, trigger history, run status | [Part 4] | **NEW** |
| `/control-plane/routines/{id}` | **Routine detail** — trigger config, run history, linked issues, concurrency policy, failure tracking | [Part 4] | **NEW** |
| `/control-plane/campaigns` | **Campaigns** — strategic objectives with target metrics, progress tracking, linked items | [Part 4] | **NEW** |
| `/control-plane/campaigns/{id}` | **Campaign detail** — metric history chart, linked alerts/issues/routines, progress toward target | [Part 4] | **NEW** |
| `/control-plane/costs` | Cost dashboard — spend by agent, by LLM integration, by alert, budget utilization, **budget policy management** | [Part 1] | Enhanced |
| `/control-plane/activity` | Audit log — searchable, filterable activity stream | [Part 1] | Original |
| `/control-plane/settings/llm` | LLM integrations — register providers, manage API keys, view per-model costs | [Part 1] | Original |
| `/control-plane/settings/integrations` | Action integrations — per-integration approval modes and config | [Part 2] | Original |
| `/control-plane/settings/secrets` | **Secrets management** — create/rotate/revoke secrets, view usage references, provider config | [Part 5] | **NEW** |

#### Key UX Patterns

- **Approval inbox as primary surface** — the most important page for SOC operators. Show proposed action, agent's reasoning, alert context, enrichment data, and one-click approve/reject.
- **Queue visibility** — see unassigned alerts, who's working what, how long alerts have been waiting.
- **Agent health at a glance** — status indicators (running/idle/paused/error), last heartbeat, current workload, budget utilization.
- **Progressive disclosure** — top layer: human-readable summary. Middle: action details and enrichment. Bottom: raw agent logs and API calls.
- **Slack/webhook notifications** — pending approvals push to Slack so operators don't need to watch the UI.
- **Agent detail as command center** — the agent detail page is the most complex page. It needs tabs/sections for: Config, Heartbeat History (with log viewer), Assigned Work (alerts + issues by status — the PM view), Sessions, Memory, Cost Breakdown, Delegation History (orchestrators), Capability Declarations (specialists).
- **KB as internal wiki** — folder tree nav on the left, rendered markdown on the right, edit button, revision history dropdown. Pages show injection scope badges (global, role:X, agent:Y) and sync status indicators (local, synced from GitHub, synced from Confluence).
- **Topology as situational awareness** — interactive DAG/graph visualization. Nodes are agents with status badges. Edges show alert routing and delegation paths. Click a node to navigate to agent detail. Color-coding by status (green=idle, blue=running, yellow=paused, red=error).
- **Issue board for non-alert work** — filterable list or kanban view. Categories as swimlanes or tabs. Link to originating alert or routine. This is where remediation tasks, detection tuning, and follow-ups live.
- **Routine dashboard** — list of routines with last run status, next scheduled run, trigger type icon (clock for cron, webhook icon, hand for manual). Drill into run history with pass/fail indicators.

#### Page Detail Specs (Working Session Required)

> [!warning] Working Session Needed
> Each page listed above requires a dedicated design pass covering: layout, components, data requirements, API calls, real-time update strategy, error states, empty states, loading states, and responsive behavior. This section will be populated during the UI working session. Prioritize in this order:
>
> 1. **Approval inbox** — highest operational impact, operators live here
> 2. **Agent detail** — most complex page, command center for agent management
> 3. **Dashboard** — first thing operators see, sets situational awareness
> 4. **Alert queue** — core workflow surface
> 5. **Knowledge base** — wiki browsing and editing
> 6. **Topology** — fleet situational awareness
> 7. **Issue board** — non-alert work management
> 8. **Cost dashboard** — budget visibility
> 9. **Routines** — scheduling management
> 10. **Campaigns** — strategic tracking (can ship later)
> 11. **Settings pages** — LLM, integrations, secrets (admin surfaces, lower frequency)

---
---

# Shared Appendices

---

## API Contract

All endpoints under `/api/v1`. Extends Calseta's existing FastAPI router. Existing agent endpoints (`GET/POST/PATCH/DELETE /v1/agents`, `POST /v1/agents/{uuid}/test`) continue to work for webhook-based agent management. The control plane adds new endpoints for the pull model, orchestration, and lifecycle management.

### LLM Integrations (Operator) `[Part 1]`

```
POST   /api/v1/llm-integrations               Register LLM provider+model combo
GET    /api/v1/llm-integrations               List all registered LLM integrations
GET    /api/v1/llm-integrations/{id}           Get integration details (API key redacted)
PATCH  /api/v1/llm-integrations/{id}           Update integration config
DELETE /api/v1/llm-integrations/{id}           Remove integration (fails if agents reference it)
GET    /api/v1/llm-integrations/{id}/usage     Cost/token usage for this LLM integration
```

### Agent Management (Operator) `[Part 1]`

Existing endpoints (`GET/POST/PATCH/DELETE /v1/agents`, `POST /v1/agents/{uuid}/test`) are extended with new fields. New endpoints added for lifecycle management and control plane features:

```
— EXISTING (extended with new fields: agent_type, role, status, llm_integration_id, etc.) —
POST   /api/v1/agents                         Create agent (now supports orchestrator/specialist type)
GET    /api/v1/agents                         List agents (new filters: status, role, agent_type)
GET    /api/v1/agents/{uuid}                  Get agent details (includes new control plane fields)
PATCH  /api/v1/agents/{uuid}                  Update agent config (accepts new fields)
DELETE /api/v1/agents/{uuid}                  Delete agent
POST   /api/v1/agents/{uuid}/test             Test webhook delivery (existing)

— NEW —
POST   /api/v1/agents/{uuid}/pause            Pause agent (graceful cancel if running)
POST   /api/v1/agents/{uuid}/resume           Resume paused agent
POST   /api/v1/agents/{uuid}/terminate        Terminate agent (irreversible)
POST   /api/v1/agents/{uuid}/keys             Create agent API key (returns plaintext once)
DELETE /api/v1/agents/{uuid}/keys/{key_id}    Revoke agent API key
POST   /api/v1/agents/{uuid}/invoke           Manually trigger agent execution (managed) or heartbeat (external)
GET    /api/v1/agents/{uuid}/capabilities     Get declared capabilities (specialist only)
GET    /api/v1/agents/{uuid}/invocations      Get sub-agent invocation history (orchestrator only)
```

### Tool Management (Operator) `[Part 1]`

```
GET    /api/v1/tools                           List all registered tools (filterable by tier, category)
GET    /api/v1/tools/{id}                      Get tool details (schema, tier, handler)
POST   /api/v1/tools                           Register a custom tool
PATCH  /api/v1/tools/{id}                      Update tool config (tier, schema, active)
DELETE /api/v1/tools/{id}                      Remove custom tool (fails if agents reference it)
POST   /api/v1/tools/sync                      Re-sync MCP tools from connected MCP servers
```

Built-in Calseta tools (category `calseta_api`) are auto-registered at startup. MCP tools are discovered from connected MCP servers. Custom tools are added by operators for internal APIs, scripts, etc.

### Alert Queue (Agent-facing) `[Part 1]`

```
GET    /api/v1/queue                          Get available alerts (matching agent's filter)
POST   /api/v1/queue/{alert_id}/checkout      Atomic checkout (agent claims alert)
POST   /api/v1/queue/{alert_id}/release       Release alert back to queue
GET    /api/v1/assignments/mine               Get agent's current assignments
PATCH  /api/v1/assignments/{assignment_id}     Update assignment status/resolution
```

### Actions and Approvals (Agent + Operator) `[Part 2]`

```
POST   /api/v1/actions                        Propose an action
GET    /api/v1/actions                         List actions (filterable by status, type)
GET    /api/v1/actions/{action_id}             Get action details
POST   /api/v1/actions/{action_id}/cancel      Cancel action
```

Approve/reject flows through the **existing approval endpoints** (`/v1/workflow-approvals/{uuid}/approve`, `/v1/workflow-approvals/{uuid}/reject`) and existing Slack/Teams/browser callbacks. No new approval endpoints needed.

**Propose action contract:**
```
POST /api/v1/actions

Request:
{
  "alert_id": "uuid",
  "assignment_id": "uuid",
  "action_type": "containment",
  "action_subtype": "block_ip",
  "payload": {
    "ip": "198.51.100.42",
    "firewall": "palo_alto_prod",
    "duration_hours": 24,
    "reason": "C2 callback detected from alert ALT-2026-0847"
  },
  "confidence": 0.92,
  "reasoning": "IP matched known C2 infrastructure via VT enrichment. 3 beacons in 15 min window."
}

Response (201) — when approval required:
{
  "action_id": "uuid",
  "status": "pending_approval",
  "approval_request_uuid": "uuid",
  "expires_at": "2026-03-16T15:00:00Z"
}

Response (201) — when auto-approved:
{
  "action_id": "uuid",
  "status": "executing"
}
```

### Sub-Agent Delegation (Orchestrator Agents) `[Part 2]`

```
POST   /api/v1/invocations                    Delegate task to a sub-agent
POST   /api/v1/invocations/parallel            Delegate to multiple sub-agents simultaneously
GET    /api/v1/invocations/{invocation_id}     Get invocation status + result
GET    /api/v1/invocations/{invocation_id}/poll Poll until complete (long-poll with timeout)
GET    /api/v1/agents/catalog                  Get available sub-agents with capabilities (for orchestrator context)
```

**Delegate task contract:**
```
POST /api/v1/invocations

Request:
{
  "child_agent_id": "uuid",
  "alert_id": "uuid",
  "assignment_id": "uuid",
  "task_description": "Full user profile + recent activity for jsmith@corp.com",
  "input_context": {
    "entity": "jsmith@corp.com",
    "entity_type": "user",
    "timerange_hours": 48
  }
}

Response (201):
{
  "invocation_id": "uuid",
  "status": "queued",
  "child_agent": "identity-agent"
}
```

**Parallel delegation contract:**
```
POST /api/v1/invocations/parallel

Request:
{
  "alert_id": "uuid",
  "assignment_id": "uuid",
  "tasks": [
    {"child_agent_id": "uuid-1", "task_description": "...", "input_context": {...}},
    {"child_agent_id": "uuid-2", "task_description": "...", "input_context": {...}},
    {"child_agent_id": "uuid-3", "task_description": "...", "input_context": {...}}
  ]
}

Response (201):
{
  "invocations": [
    {"invocation_id": "uuid-a", "child_agent": "identity-agent", "status": "queued"},
    {"invocation_id": "uuid-b", "child_agent": "siem-agent", "status": "queued"},
    {"invocation_id": "uuid-c", "child_agent": "threat-intel-agent", "status": "queued"}
  ]
}
```

### Cost and Budget (Agent + Operator) `[Part 1]`

```
POST   /api/v1/cost-events                    Report token/cost usage
GET    /api/v1/costs/summary                   Instance-wide cost summary
GET    /api/v1/costs/by-agent                  Cost breakdown by agent
GET    /api/v1/costs/by-alert                  Cost breakdown by alert
PATCH  /api/v1/agents/{agent_id}/budget        Update agent budget
```

### Heartbeat and Monitoring `[Part 1]`

```
POST   /api/v1/heartbeat                       Agent reports heartbeat (auto from adapters)
GET    /api/v1/heartbeat-runs                   List heartbeat runs
GET    /api/v1/heartbeat-runs/{run_id}          Get run details with logs
```

### Activity and Dashboard `[Part 1]`

```
GET    /api/v1/activity                         Audit log (filterable, paginated)
GET    /api/v1/dashboard                        Control plane dashboard data
```

**Dashboard payload:**
```json
{
  "agents": {
    "total": 5,
    "active": 3,
    "running": 2,
    "paused": 1,
    "error": 0
  },
  "queue": {
    "pending": 12,
    "in_progress": 4,
    "pending_review": 2,
    "resolved_today": 47
  },
  "actions": {
    "pending_approval": 3,
    "approved_today": 15,
    "rejected_today": 1
  },
  "costs": {
    "mtd_cents": 4520,
    "budget_utilization_pct": 34.2,
    "top_agent": {"name": "Triage Agent", "spent_cents": 2100}
  },
  "metrics": {
    "mean_time_to_triage_min": 2.3,
    "mean_time_to_resolve_min": 18.7,
    "auto_resolved_pct": 62.0
  }
}
```

### Approval Policies `[Part 2]`

No new endpoints needed — the existing per-workflow `approval_mode` field and the per-`ActionIntegration` default approval mode handle policy. Operators configure approval behavior through workflow settings and integration config.

### Issues `[Part 4]`

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

### Routines `[Part 4]`

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

### Campaigns `[Part 4]`

```
POST   /api/v1/campaigns                           Create campaign
GET    /api/v1/campaigns                           List campaigns
GET    /api/v1/campaigns/{id}                      Get campaign details with linked items
PATCH  /api/v1/campaigns/{id}                      Update campaign
POST   /api/v1/campaigns/{id}/items                Link item to campaign
DELETE /api/v1/campaigns/{id}/items/{item_id}      Unlink item
GET    /api/v1/campaigns/{id}/metrics              Get metric history for campaign
```

### Topology `[Part 4]`

```
GET    /api/v1/topology                            Get full agent topology graph
GET    /api/v1/topology/routing                    Get alert routing paths only
GET    /api/v1/topology/delegation                 Get delegation paths only
```

### Knowledge Base `[Part 3]`

```
POST   /api/v1/kb                                  Create page
GET    /api/v1/kb                                  List pages (filterable by folder, status, inject_scope, sync_source)
GET    /api/v1/kb/{slug}                           Get page by slug
PATCH  /api/v1/kb/{slug}                           Update page
DELETE /api/v1/kb/{slug}                           Delete page (or archive)
GET    /api/v1/kb/{slug}/revisions                 List revisions
GET    /api/v1/kb/{slug}/revisions/{rev}           Get specific revision
POST   /api/v1/kb/{slug}/links                     Link page to entity
GET    /api/v1/kb/search                           Search pages
POST   /api/v1/kb/sync                             Trigger sync for all external pages
POST   /api/v1/kb/{slug}/sync                      Trigger sync for single page
GET    /api/v1/kb/folders                           List folder hierarchy
```

### Secrets `[Part 5]`

```
POST   /api/v1/secrets                             Create secret (returns plaintext once if local_encrypted)
GET    /api/v1/secrets                             List secrets (names only, no values)
GET    /api/v1/secrets/{name}                      Get secret metadata (no value)
POST   /api/v1/secrets/{name}/versions             Add new version (rotates secret)
DELETE /api/v1/secrets/{name}/versions/{version}   Revoke a version
DELETE /api/v1/secrets/{name}                      Delete secret (fails if referenced)
POST   /api/v1/secrets/{name}/verify               Verify secret is resolvable (returns hash, not value)
```

---

## MCP Server Extensions

Extend Calseta's existing MCP server (port 8001). The MCP server already has tools for agents: `post_alert_finding`, `update_alert_status`, `search_alerts`, `update_alert_malice`, and `execute_workflow` (with approval gate integration). The control plane adds:

**New core tools (all agents):** `[Part 1]`
```
get_pending_alerts     — Get alerts available for checkout (pull model — complements existing push dispatch)
checkout_alert         — Atomically claim an alert
release_alert          — Release an alert back to the queue
get_assignment         — Get current assignment details with full enriched context
propose_action         — Propose a response action (containment, remediation, etc.)
get_action_status      — Check if a proposed action was approved/rejected
complete_assignment    — Mark assignment as resolved with resolution type
report_cost            — Report token/cost usage for current session
get_agent_context      — Get agent's config, budget status, and capabilities
```

**Orchestration tools (orchestrator agents):** `[Part 2]`
```
list_available_agents  — Get catalog of sub-agents with declared capabilities
delegate_task          — Invoke a specialist sub-agent with context
delegate_parallel      — Invoke multiple sub-agents simultaneously
get_task_result        — Get a sub-agent invocation's result (polls until complete)
get_all_results        — Get results from all sub-agent invocations for current alert
```

**Issue tools:** `[Part 4]`
```
create_issue           — Create a new issue (managed tier)
get_my_issues          — Get issues assigned to this agent (safe tier)
update_issue_status    — Update issue status (managed tier)
add_issue_comment      — Add a comment to an issue (managed tier)
checkout_issue         — Atomic checkout of an issue (managed tier)
```

**Knowledge base tools:** `[Part 3]`
```
create_kb_page         — Create a new KB page (managed tier)
update_kb_page         — Update an existing KB page (managed tier)
search_kb              — Search KB pages by keyword or semantic query (safe tier)
get_kb_page            — Read a KB page by slug (safe tier)
link_kb_page           — Link a KB page to an alert, issue, or other entity (managed tier)
```

**Memory tools:** `[Part 3]`
```
save_memory            — Store a memory entry (managed tier)
recall_memory          — Search agent's memory entries (safe tier)
update_memory          — Update an existing memory entry (managed tier)
promote_memory         — Promote private memory to shared (managed tier)
list_memories          — List agent's memory entries by type/recency (safe tier)
```

This means any MCP-compatible agent (Claude Desktop, Claude Code, custom MCP clients) can orchestrate security workflows — including multi-agent investigations — through Calseta's MCP server without building REST API integrations.

---

## User Stories

### Operator Stories

- As a security engineer, I want to register AI agents in Calseta so that I can manage which agents handle which types of alerts.
- As a security engineer, I want to register LLM providers once and assign them to agents so that I don't manage API keys per-agent.
- As a security engineer, I want to create an orchestrator agent that delegates investigation to specialist sub-agents so that complex alerts get thorough, multi-faceted analysis.
- As a SOC lead, I want to see a dashboard of all agent activity — including sub-agent invocation trees — so that I can understand what my AI agents are doing at any moment.
- As a security engineer, I want to configure approval policies so that high-impact actions (block IP, disable user) require my approval while low-risk actions (enrichment, notifications) auto-execute.
- As a SOC operator, I want an approval inbox where I can review agent-proposed actions with full context and one-click approve or reject.
- As a security manager, I want to set per-agent token budgets with model-level visibility so that I know exactly which LLM is burning budget.
- As a security manager, I want to see full investigation cost rollups (orchestrator + all sub-agents) per alert so I can assess ROI.
- As a compliance officer, I want a full audit trail of every agent action — including the full delegation chain — so that I can demonstrate due diligence in incident response.
- As a security engineer, I want to start with Calseta's reference agents and customize them for my environment so that I'm not building from scratch.
- As a SOC lead, I want to manage non-alert work (remediation tasks, detection tuning, post-incident follow-ups) alongside alert investigations so that nothing falls through the cracks.
- As a security engineer, I want to schedule agents on cron triggers (daily threat intel triage, weekly FP rate review) so that recurring work happens automatically without manual invocation.
- As a SOC operator, I want an internal knowledge base where investigation findings, runbooks, and institutional knowledge are searchable and browsable so that agents and humans can reference the same source of truth.
- As a security engineer, I want to inject KB pages as context into specific agents or roles so that agents always have the latest runbooks without manual prompt editing.
- As a security engineer, I want to sync KB pages from our existing Confluence/GitHub docs so that Calseta is a read-only mirror of our canonical knowledge.
- As a SOC lead, I want to see an agent topology view (routing paths, delegation map, capability overview) so that I understand how my agent fleet is wired together at a glance.
- As a security manager, I want to define investigation campaigns with target metrics (MTTD, FP rate, auto-resolve rate) so that operational work ties back to strategic objectives.
- As a security engineer, I want agents to build persistent memory from their work (codebase maps, entity profiles, investigation patterns) so that we pay tokens once and reuse learned context forever.
- As a SOC operator, I want an agent detail page with a PM view showing all tasks by status (todo/in_progress/done) so that I can see what an agent has been doing without filtering the global board.
- As a security engineer, I want centralized secret management with versioning, rotation, and automatic log redaction so that credentials are never exposed in agent logs or configs.

### Agent Developer Stories

- As an agent developer, I want to authenticate my agent with an API key so that it can pull alerts and propose actions through Calseta's API.
- As an agent developer, I want atomic alert checkout so that my agent never works an alert that another agent is already handling.
- As an agent developer, I want MCP tools for the control plane — including sub-agent delegation — so that I can build orchestrator agents using Claude Desktop or any MCP client without custom API code.
- As an agent developer, I want to propose actions with structured payloads so that Calseta can route them through approval gates and execute them via integrations.
- As an agent developer, I want to report token usage so that cost tracking happens automatically without building my own telemetry.
- As an agent developer building a specialist, I want to declare structured capabilities so that orchestrators can discover what I can do and invoke me correctly.
- As an agent developer, I want to study Calseta's reference agents as working examples of how to build orchestrators and specialists.
- As an agent developer, I want session continuity across heartbeats so that my agent can resume multi-wave investigations without starting from scratch.
- As an agent developer, I want to save and recall persistent memory (entity profiles, codebase maps) via tools so that my agent learns once and remembers forever.
- As an agent developer, I want to create follow-up issues from investigations (remediation tasks, detection tuning) so that work doesn't get lost in alert comments.
- As an agent developer, I want to create and search KB pages via tools so that my agent can contribute to organizational knowledge.
- As an agent developer, I want a persistent home directory (`AGENT_HOME`) for storing working files, memory, and artifacts across heartbeats.

### Platform Stories

- As a Calseta contributor, I want the control plane to use the same plugin pattern as enrichment providers so that adding new action integrations follows a familiar pattern.
- As a Calseta user, I want the control plane to be optional so that I can still use Calseta as a pure data layer if I don't need orchestration.
- As a Calseta user, I want to choose between BYO agents (Option A) and Calseta-managed agents (Option B) depending on my needs.

---

## Implementation Phases

> [!important] Enterprise-First Phasing
> LLM provider registration, the agent runtime engine, and the tool system are foundational. The `process` adapter (subprocess spawning) is deferred to Phase 7+ as a dev/demo convenience. Managed agents run inside Calseta; external agents communicate via HTTP.

### Phase 1 — LLM Providers + Agent Registry + Agent Runtime + Tool System (Foundation) `[Part 1]` `[Part 5: Secrets, Auth]`

**Goal:** Operators register LLM providers, define managed agents (prompt + tools + LLM), and Calseta executes them. Also supports external agents via pull-based queue. This is the biggest phase — it ships the core platform.

**LLM Provider Management:** `[Part 1]`
- [ ] `llm_integrations` table + Alembic migration
- [ ] LLM integration CRUD endpoints (`POST/GET/PATCH/DELETE /api/v1/llm-integrations`)
- [ ] LLM usage endpoint (`GET /api/v1/llm-integrations/{id}/usage`)
- [ ] API key storage: reference to env var or secret manager key (never plaintext in DB)
- [ ] `is_default` flag — agents without explicit LLM config use the default
- [ ] `LLMProviderAdapter` ABC + `AnthropicAdapter` + `OpenAIAdapter`

**Agent Registry Extension:** `[Part 1]`
- [ ] Alembic migration: add new columns to `agent_registrations` (`execution_mode`, `agent_type`, `role`, `status`, `adapter_type`, `adapter_config`, `capabilities`, `llm_integration_id`, `system_prompt`, `methodology`, `tool_ids`, `max_tokens`, `enable_thinking`, `sub_agent_ids`, `max_sub_agent_calls`, `budget_monthly_cents`, `spent_monthly_cents`, `budget_period_start`, `last_heartbeat_at`, `max_concurrent_alerts`)
- [ ] Migrate `is_active` boolean → `status` enum (backwards-compatible default: `active`/`paused`)
- [ ] `agent_api_keys` table + key generation/hashing (for external agents calling back into Calseta)
- [ ] Agent API key auth middleware (Bearer token → agent context for inbound calls)
- [ ] Extend existing agent CRUD endpoints with new fields (including `execution_mode`, `llm_integration_id`, `system_prompt`, `tool_ids`)
- [ ] New lifecycle endpoints: `pause`, `resume`, `terminate`

**Tool System:** `[Part 1]`
- [ ] `agent_tools` table + migration
- [ ] Tool CRUD endpoints (`GET/POST/PATCH/DELETE /api/v1/tools`)
- [ ] Auto-register Calseta built-in tools at startup (get_alert, search_alerts, post_finding, update_alert_status, get_enrichment, get_detection_rule, list_context_documents, etc.)
- [ ] MCP tool sync endpoint (`POST /api/v1/tools/sync`) — discovers tools from connected MCP servers
- [ ] Tool tier enforcement in runtime (safe/managed/requires_approval/forbidden)
- [ ] Workflow-as-tool registration — expose existing workflows as callable tools

**Agent Runtime Engine:** `[Part 1]`
- [ ] `AgentRuntimeEngine` — main execution loop for managed agents
- [ ] Prompt construction: system_prompt + methodology + alert context + tool schemas
- [ ] Tool call routing: intercept LLM tool calls → check tier → execute → return result
- [ ] `cost_events` recording on every LLM API call (exact token counts from provider response)
- [ ] Investigation state tracking on `alert_assignments.investigation_state` (JSONB)
- [ ] Timeout and cancellation support
- [ ] Procrastinate task: `run_managed_agent_task` — executes managed agent in worker process

**Adapter System (External Agents):** `[Part 1]`
- [ ] `AgentAdapter` ABC
- [ ] `http` adapter implementation (for external agents)
- [ ] `mcp` adapter implementation (heartbeat inferred from MCP tool activity)
- [ ] `webhook` adapter continues working as-is (existing behavior, no changes)

**Session State + Agent Home:** `[Part 1]`
- [ ] `agent_task_sessions` table + migration
- [ ] Session resolution in runtime: lookup by agent_id + task_key, resume or create fresh
- [ ] Session compaction logic: detect threshold, generate handoff summary, inject into next heartbeat
- [ ] Session compaction config on `agent_registrations` (threshold_pct, strategy, max_heartbeats)
- [ ] Agent home directory creation at agent registration (`$CALSETA_DATA_DIR/agents/{id}/`)
- [ ] `AGENT_HOME` environment variable set during invocation
- [ ] Agent file API endpoints (`GET/PUT/DELETE /api/v1/agents/{uuid}/files/{path}`)

**Secrets Foundation:** `[Part 5]`
- [ ] `secrets` table + `secret_versions` table + migrations
- [ ] Secret CRUD endpoints (`POST/GET/DELETE /api/v1/secrets`)
- [ ] Secret version rotation endpoint (`POST /api/v1/secrets/{name}/versions`)
- [ ] `local_encrypted` provider (AES-256-GCM in PostgreSQL)
- [ ] `env_var` provider (reads from environment)
- [ ] `secret_ref` resolution in adapter config, LLM integration config, and KB sync config
- [ ] Sensitive key detection regex + strict mode option
- [ ] Log redaction for resolved secret values in heartbeat run logs
- [ ] Run-scoped JWT generation for managed agents (`CALSETA_AGENT_JWT_SECRET`)
- [ ] JWT verification middleware in auth resolution chain

**Alert Queue + Checkout:** `[Part 1]`
- [ ] `alert_assignments` table + migration
- [ ] Alert queue endpoint (`GET /api/v1/queue`) — returns enriched alerts matching agent's trigger filters
- [ ] Atomic checkout endpoint (`POST /api/v1/queue/{alert_id}/checkout`)
- [ ] Release endpoint (`POST /api/v1/queue/{alert_id}/release`)
- [ ] Bridge: after enrichment, route to managed agent (auto-checkout + execute) or create queue entry for external agents
- [ ] MCP tools: `get_pending_alerts`, `checkout_alert`, `release_alert`, `get_assignment`
- [ ] Activity logging for all new mutations (extends existing `ActivityEvent` system)

**Exit criteria:** Operator registers "claude-opus" as an LLM provider. Creates a managed Triage Agent with system prompt, methodology, tool set (get_alert, search_alerts, post_finding), linked to claude-opus. Alert arrives → matches agent trigger → Calseta auto-checks out alert → runtime engine constructs prompt (6-layer system) → calls Anthropic API → agent uses tools → findings posted → cost recorded → session state persisted for next heartbeat. External agents authenticate with agent API key, managed agents get run-scoped JWTs. Secrets resolved securely with log redaction. Both managed and external agents coexist.

### Phase 2 — Actions + Approval Gates (Human-in-the-Loop) `[Part 2]`

**Goal:** Agents can propose actions, humans approve via existing Slack/Teams/browser flows, Calseta tracks everything.

- [ ] `agent_actions` table + migration (with `approval_request_id` FK to existing `workflow_approval_requests`)
- [ ] Extend `WorkflowApprovalRequest.trigger_context` schema for response action metadata
- [ ] Add `"agent_action"` trigger_type to existing approval system
- [ ] Propose action endpoint (`POST /api/v1/actions`) — creates `agent_actions` row + `WorkflowApprovalRequest` when approval needed
- [ ] New Procrastinate task: `execute_response_action_task` (runs `ActionIntegration` after approval, parallel to existing `execute_approved_workflow_task`)
- [ ] Extend existing notifier message templates to show response action details (target, action type, agent reasoning)
- [ ] Assignment completion flow (agent marks alert resolved with resolution type)
- [ ] MCP tools: `propose_action`, `get_action_status`, `complete_assignment`
- [ ] Activity logging via existing activity event system

**Exit criteria:** Agent proposes "block IP" action → existing approval system creates `WorkflowApprovalRequest` → operator approves via Slack button → `execute_response_action_task` fires → action status transitions to completed. Auto-execute works for notification/enrichment actions.

### Phase 3 — Integration Execution Engine (Close the Loop) `[Part 2]`

**Goal:** Approved actions actually execute against security tools.

- [ ] `ActionIntegration` base class (same pattern as `EnrichmentProviderBase`)
- [ ] Execution engine: approved action → find integration → execute → record result
- [ ] Rollback support for reversible actions
- [ ] Initial integrations: Generic Webhook, Slack, CrowdStrike, Entra ID
- [ ] `SlackUserValidationIntegration` — DM users for activity confirmation, button callbacks, auto-close/escalate based on response
- [ ] Execution result stored on `agent_actions.execution_result`
- [ ] Failed execution → retry logic or manual intervention flag

**Exit criteria:** Agent proposes "isolate host" → operator approves → CrowdStrike integration isolates the host → result recorded → alert marked resolved. User validation flow: agent proposes `validate_user_activity` → Slack DM sent → user confirms → alert auto-closed with response attached.

### Phase 4 — Heartbeat + Budget Controls + Supervision (Operational Maturity) `[Part 1]`

**Goal:** Monitor agent health, enforce cost limits per-agent and per-LLM-provider, detect stuck/stalling investigations.

- [ ] `heartbeat_runs` table + migration
- [ ] Heartbeat reporting endpoint
- [ ] Scheduler: periodic heartbeat checks, stuck detection
- [ ] `cost_events` table + migration (links to both `agent_registration_id` AND `llm_integration_id`)
- [ ] Cost reporting endpoint (`POST /api/v1/cost-events`)
- [ ] Cost summary endpoints: by-agent, by-alert, by-LLM-provider, instance-wide
- [ ] Budget enforcement: soft alert at 80%, hard-stop at 100% (auto-pause agent)
- [ ] Per-alert budget enforcement: `max_cost_per_alert_cents` checked after each LLM call in runtime engine
- [ ] `AgentSupervisor` — periodic Procrastinate task (`supervise_running_agents_task`, every 30s):
  - [ ] Stuck agent detection: no heartbeat or tool activity beyond `timeout_seconds`
  - [ ] Stall detection: `stall_threshold` consecutive empty sub-agent results
  - [ ] Time enforcement: investigation duration vs `max_investigation_minutes`
  - [ ] Concurrency enforcement: no agent exceeds `max_concurrent_alerts`
- [ ] Investigation checkpoint context injection: budget/stall/time status injected into orchestrator prompts at wave boundaries
- [ ] MCP tools: `report_cost`, `get_agent_context` (includes budget status + checkpoint status)
- [ ] Monthly budget reset logic

**Exit criteria:** Agent reports cost with LLM integration reference → costs tracked per-agent AND per-LLM-provider → budget approaches limit → soft alert fires → budget exceeded → agent auto-paused → operator raises budget and resumes. Per-alert budget: investigation exceeds per-alert cap → paused → operator notified. Supervision: stuck agent killed after timeout → alert released back to queue. Stalling investigation flagged after N empty results → operator notified.

### Phase 5 — Multi-Agent Orchestration `[Part 2]`

**Goal:** Orchestrator agents delegate to specialist sub-agents, full investigation trees are tracked.

- [ ] `agent_invocations` table + migration
- [ ] Sub-agent delegation endpoints (`POST /api/v1/invocations`, `POST /api/v1/invocations/parallel`)
- [ ] Invocation result polling endpoint (`GET /api/v1/invocations/{id}/poll`)
- [ ] Agent catalog endpoint (`GET /api/v1/agents/catalog`) — specialists with capability declarations
- [ ] MCP orchestration tools: `list_available_agents`, `delegate_task`, `delegate_parallel`, `get_task_result`, `get_all_results`
- [ ] Alert routing engine: deterministic rules match alerts to orchestrators based on `alert_filter`
- [ ] Cost rollup: sub-agent costs aggregate to parent invocation → parent agent → alert → LLM provider
- [ ] Invocation depth limit enforcement (1 level: orchestrator → specialist only)

**Exit criteria:** An orchestrator agent receives an alert, invokes 3 specialist sub-agents in parallel via MCP tools or REST API, collects structured results, synthesizes findings, and proposes a response action. Full invocation tree visible via API with cost rollups per sub-agent and per LLM provider.

### Phase 5.5 — Issue/Task System + Routine Scheduler + Agent Topology `[Part 4]`

**Goal:** Non-alert work management, scheduled agent invocations, and fleet visibility.

**Issue/Task System:** `[Part 4]`
- [ ] `agent_issues` table + `agent_issue_comments` table + migrations
- [ ] Issue CRUD endpoints (`POST/GET/PATCH /api/v1/issues`)
- [ ] Atomic checkout for issues (same pattern as alert assignments)
- [ ] Issue comment endpoints
- [ ] MCP tools: `create_issue`, `get_my_issues`, `update_issue_status`, `add_issue_comment`, `checkout_issue`
- [ ] Agent detail: issues assigned to agent endpoint (`GET /api/v1/agents/{uuid}/issues`)
- [ ] Activity logging for issue mutations

**Routine Scheduler:** `[Part 4]`
- [ ] `agent_routines` + `routine_triggers` + `routine_runs` tables + migrations
- [ ] Routine CRUD endpoints
- [ ] Cron expression parser (5-field)
- [ ] Procrastinate periodic task: `evaluate_routine_triggers_task` (runs every 30s)
- [ ] Concurrency policy enforcement (skip_if_active, coalesce_if_active, always_run)
- [ ] Webhook trigger endpoint with HMAC verification + replay window
- [ ] Manual trigger endpoint
- [ ] Routine failure tracking + auto-pause after N consecutive failures

**Agent Topology:** `[Part 4]`
- [ ] Topology computation from existing agent config (types, sub_agent_ids, trigger_filters, capabilities)
- [ ] Topology API endpoint (`GET /api/v1/topology`)
- [ ] Routing path computation, delegation path computation

**Exit criteria:** Agent creates a remediation issue during an investigation → issue tracked with subtasks → assignee agent picks it up on next heartbeat. Scheduled routine fires daily → creates issue → agent wakes and processes. Topology API returns agent fleet graph with routing + delegation paths.

### Phase 6 — Operator UI (Visibility) `[Part 5]`

> [!important] UI Working Session Required Before Implementation
> Every page below requires a dedicated design working session to spec layout, components, interactions, data requirements, error/empty/loading states, and real-time update strategy. The UI must be enterprise-grade — SOC operators use this in high-pressure situations. See the "Page Detail Specs" note in the Operator UI architecture section.

**Goal:** Full operator dashboard for the control plane, including all new feature surfaces.

**Core Pages (MVP):** `[Part 1]` `[Part 2]`
- [ ] Tech decision: extend existing Calseta UI or build new React app
- [ ] Approval inbox page — **build first**, highest operational impact
- [ ] Dashboard page (agent status, queue depth, pending approvals, costs by LLM provider)
- [ ] Agent registry page (list, create with LLM provider selection, configure)
- [ ] Agent detail page — **command center**: config, heartbeats, cost breakdown, **PM view (assigned work by status)**, sessions, delegation history
- [ ] Investigation tree view (orchestrator → sub-agent invocations → findings → cost per step)
- [ ] Alert queue page (pending, assigned, resolved)

**New Feature Pages:** `[Part 3]` `[Part 4]` `[Part 5]`
- [ ] Agent topology page — interactive DAG/graph visualization of agent fleet `[Part 4]`
- [ ] Issue board page — non-alert work items by status, category tabs, linked alert references `[Part 4]`
- [ ] Issue detail page — description, comments, linked entities, history `[Part 4]`
- [ ] Knowledge base browser — folder tree nav, rendered markdown, search, injection scope badges `[Part 3]`
- [ ] KB page detail — rendered markdown, revision history, linked entities, sync status `[Part 3]`
- [ ] KB page editor — markdown editor with preview, injection scope picker, sync config `[Part 3]`
- [ ] Routine dashboard — routine list with status, next run, trigger type, run history `[Part 4]`
- [ ] Routine detail — trigger config, run history, linked issues, failure tracking `[Part 4]`
- [ ] Campaign dashboard — strategic objectives, metric progress charts, linked items `[Part 4]`
- [ ] Campaign detail — metric history, linked alerts/issues/routines `[Part 4]`
- [ ] Secrets management page — create/rotate/revoke, view references, provider config `[Part 5]`

**Settings & Admin Pages:** `[Part 1]` `[Part 2]`
- [ ] LLM integrations page (register providers, manage API key refs, view per-model costs)
- [ ] Cost dashboard page (spend by agent, by LLM provider, by time, budget policy management)
- [ ] Activity log page (searchable audit stream)
- [ ] Action integration settings page (per-integration approval mode config)

**Real-time:**
- [ ] SSE/WebSocket event stream for live updates (agent status changes, new approvals, run completions)
- [ ] Real-time log streaming for active heartbeat runs

**Exit criteria:** Operator can manage the full control plane through the web UI: agents, alerts, issues, KB, routines, campaigns, secrets, topology, costs, approvals, and activity. All new features have dedicated, well-designed UI surfaces. Agent detail page includes PM view showing tasks by status.

### Phase 6.5 — Knowledge Base + Agent Memory (Organizational Knowledge) `[Part 3]`

**Goal:** Ship the knowledge base system and agent persistent memory. Agents and operators can create, search, and inject knowledge into agent prompts.

**Knowledge Base:** `[Part 3]`
- [ ] `knowledge_base_pages` table + `kb_page_revisions` table + `kb_page_links` table + migrations
- [ ] KB CRUD endpoints (`POST/GET/PATCH/DELETE /api/v1/kb`)
- [ ] KB search endpoint (full-text via PostgreSQL `tsvector`)
- [ ] Folder hierarchy endpoint
- [ ] Revision history endpoints
- [ ] Context injection resolver: `resolve_kb_context(agent)` — global + role-scoped + agent-specific pages
- [ ] Token budget enforcement for KB injection (configurable % of context window)
- [ ] Injection into Layer 3 of prompt construction system
- [ ] MCP tools: `create_kb_page`, `update_kb_page`, `search_kb`, `get_kb_page`, `link_kb_page`
- [ ] KB page linking to alerts, issues, agents, campaigns

**External Sync (Phase 1 sources):** `[Part 3]`
- [ ] GitHub sync provider (public + private repos via secret_ref)
- [ ] Confluence sync provider (REST API, storage format → markdown conversion)
- [ ] URL sync provider (HTTP GET, assumes markdown)
- [ ] Procrastinate periodic task: `sync_kb_pages_task` (configurable interval, default 6h)
- [ ] Manual sync trigger endpoint
- [ ] Content hash change detection

**Agent Persistent Memory:** `[Part 3]`
- [ ] Memory conventions on KB pages (folder: `/memory/agents/{id}/`, auto-scoped injection)
- [ ] Memory tools: `save_memory`, `recall_memory`, `update_memory`, `promote_memory`, `list_memories`
- [ ] Staleness detection: TTL-based expiry + hash-based invalidation
- [ ] Memory injection into Layer 6 of prompt construction (budget-capped, prioritized)
- [ ] Stale memory prefix injection (`[STALE — last updated X hours ago]`)

**Exit criteria:** Operator creates a KB page "Credential Theft Runbook", tags it with `inject_scope: { roles: ["investigation"] }`. All investigation agents automatically receive this page in their prompt. Agent creates a memory entry after scanning a codebase; on next heartbeat, the memory is injected. KB page synced from GitHub wiki updates automatically every 6 hours.

### Phase 7 — Reference Agents + Dev Tooling (Option B) `[Part 1]`

**Goal:** Ship reference agent implementations and dev convenience tooling. Users fork and customize for their environment.

**What "reference agents" means:**
Reference agents are **working examples**, not plug-and-play templates. They ship in an `examples/agents/` directory with full source code, system prompts, capability declarations, and documentation explaining the design decisions. They demonstrate how to build Calseta-native agents — not a production deployment you use as-is. Every organization has different tools, SIEMs, identity providers, and processes, so the examples are meant to be forked and adapted.

**`process` adapter (dev/demo convenience):** `[Part 1]`
- [ ] `process` adapter implementation — spawns local child processes for running reference agents locally
- [ ] Only intended for local development and demos, not production

**Reference orchestrator:**
- [ ] `examples/agents/lead-investigator/` — orchestrator that receives enriched alerts, decides which specialists to invoke based on alert type/indicators, synthesizes findings, and proposes response actions

**Reference specialists:**
- [ ] `examples/agents/siem-query-agent/` — runs KQL/SPL queries to find related events, build timelines. Shows how to integrate with Sentinel/Splunk/Elastic APIs.
- [ ] `examples/agents/threat-intel-agent/` — deep-dives IOCs beyond Calseta's built-in enrichment. Queries VirusTotal, GreyNoise, Shodan, OTX, correlates across sources.
- [ ] `examples/agents/identity-agent/` — investigates user context: recent logins, MFA status, impossible travel, group memberships, OAuth app consents. Shows Entra/Okta integration patterns.
- [ ] `examples/agents/endpoint-agent/` — pulls process trees, persistence mechanisms, lateral movement artifacts from CrowdStrike/Defender/SentinelOne.
- [ ] `examples/agents/historical-context-agent/` — searches Calseta's own alert/assignment history for prior investigations involving the same entities.
- [ ] `examples/agents/response-agent/` — given investigation findings, recommends specific containment/remediation actions with confidence scores and reasoning.

**Each reference agent includes:**
```
examples/agents/<name>/
├── README.md              # What this agent does, how to customize, design decisions
├── agent.py               # Main entry point (Python)
├── system_prompt.md       # The system prompt (editable, well-commented)
├── capabilities.json      # Structured capability declarations
├── config.example.json    # Example adapter_config for Calseta registration
└── requirements.txt       # Python dependencies
```

**Agent builder UI (stretch goal):**
- [ ] In-UI agent creation with system prompt editor
- [ ] Capability declaration builder (structured form → JSON)
- [ ] "Fork from reference" flow: pick a reference agent, customize in-browser
- [ ] Test invocation: send a sample alert to the agent and see the response
- [ ] Prompt versioning: track system prompt changes over time

### Phase 8 — Advanced Features (Differentiation) `[All Parts]`

**Goal:** Features that make Calseta's control plane uniquely valuable for security.

- [ ] Incident grouping (multiple related alerts → single incident → single orchestrator assignment) `[Part 2]`
- [ ] Feedback loop integration with [[evaluation-agent]] feature request `[Part 2]`
- [ ] Gap detection integration with [[self-improving-agent]] feature request `[Part 2]`
- [ ] Embedded LLM integration with [[embedded-llm-functionality]] feature request for operator-side AI assistance `[Part 5]`
- [ ] Export/import agent configurations (portable agent configs, not full templates) `[Part 1]`
- [ ] Calseta Agent SDK (Python package for building Calseta-native agents — formalizes patterns from reference agents) `[Part 1]`
- [ ] Multi-level delegation (sub-agents can invoke sub-sub-agents with configurable depth limit) `[Part 2]`
- [ ] Agent-to-agent knowledge sharing (now partially addressed by KB + memory system — extend with automatic cross-agent knowledge promotion) `[Part 3]`
- [ ] User validation campaign system — batch DM outreach for credential stuffing / mass compromise scenarios with per-recipient tracking, rate-limited delivery, and aggregate dashboards `[Part 2]`
- [ ] Semantic search for KB (pgvector embeddings, conceptual similarity search) `[Part 3]`
- [ ] Notion sync provider for KB `[Part 3]`
- [ ] AWS Secrets Manager provider + HashiCorp Vault provider for secrets `[Part 5]`
- [ ] Investigation campaign metric auto-computation (e.g., auto-calculate MTTD from alert/assignment timestamps) `[Part 4]`
- [ ] Mid-execution agent interruption — operator injects context into a running managed agent (extends checkpoint injection to support human-initiated injection) `[Part 1]`
- [ ] Notion/Jira/Linear sync for issues (bidirectional sync with external project management) `[Part 4]`
- [ ] Agent memory semantic search (vector-based recall in addition to keyword) `[Part 3]`

---

## Competitive Positioning

### Before (Data Layer Only)

> "Calseta: the open-source data layer for security AI agents. Ingest, normalize, enrich, contextualize, and dispatch alerts to your agents."

### After (AI SOC Platform)

> "Calseta: the open-source AI SOC platform. Ingest alerts from any source, enrich them automatically, and orchestrate AI agents to investigate and respond — with human approval gates, budget controls, and full audit trails. Self-host it, extend it, own your security."

### Competitive Matrix

| Capability | Calseta (with CP) | Dropzone | Prophet | Simbian | Torq | Tines |
|---|---|---|---|---|---|---|
| Open source | Yes | No | No | No | No | No |
| Self-hostable | Yes | No | No | No | No | No |
| Data pipeline (ingest/enrich) | Yes | Partial | Partial | Partial | Yes | Yes |
| Multi-agent orchestration | Yes | No | No | No | No | No |
| Human approval gates | Yes | Limited | Limited | Limited | Yes | Yes |
| Budget/cost controls (per-agent, per-model) | Yes | No | No | No | No | No |
| MCP native | Yes | No | No | No | No | No |
| BYO agent + managed agents | Yes | No | No | No | No | No |
| Full audit trail (incl. delegation chains) | Yes | Partial | Partial | Partial | Yes | Yes |
| Reference agents (open source) | Yes | No | No | No | No | No |
| Agent-native schema | Yes | No | No | No | No | No |
| **Knowledge base with context injection** | **Yes** | No | No | No | No | No |
| **Agent persistent memory** | **Yes** | No | No | No | No | No |
| **Session continuity across invocations** | **Yes** | No | No | No | No | No |
| **Scheduled agent routines (cron)** | **Yes** | No | No | No | Partial | Partial |
| **Non-alert work management (issues)** | **Yes** | No | No | No | No | No |
| **External KB sync (Confluence/GitHub)** | **Yes** | No | No | No | No | No |
| **Centralized secrets with log redaction** | **Yes** | No | No | No | Partial | Partial |

### Key Differentiators

1. **Open source + self-hosted** — security teams can audit, modify, and own the code. No vendor lock-in.
2. **Multi-agent orchestration** — orchestrator agents delegate to specialist sub-agents with full visibility into the investigation tree. Not just "run one agent per alert."
3. **BYO + managed agents** — bring your own agent (Option A) or use Calseta's LLM integrations and reference agents to get started fast (Option B). Both work through the same control plane.
4. **MCP native** — first AI SOC platform with native MCP support. Any MCP client is a Calseta agent. Orchestration tools available via MCP.
5. **Deterministic pipeline + AI orchestration** — the data layer never burns LLM tokens. AI costs are isolated to agent execution and fully tracked per-agent and per-LLM-integration.
6. **Approval gates with full context** — operators see the enriched alert, full sub-agent investigation chain, orchestrator reasoning, and proposed action together. Not a black box.
7. **Cost transparency** — per-agent, per-model, per-alert cost tracking with budget enforcement. Know exactly what each investigation costs and which models are burning budget.
8. **Reference agents as education** — open-source, well-documented agent implementations that teach security teams how to build AI SOC agents. Videos, docs, and working code.
9. **Knowledge base with context injection** — internal wiki where agents and operators author runbooks, investigation summaries, and institutional knowledge. Pages are automatically injected into agent prompts based on role/scope. Syncs from Confluence, GitHub, Notion. No other AI SOC platform has this.
10. **Agent persistent memory** — agents learn once and remember forever. Codebase maps, entity profiles, investigation patterns persist across invocations. Staleness detection prevents stale memory from misleading agents. This is a moat — most platforms restart agents from scratch every time.
11. **Session continuity** — multi-wave investigations don't restart from scratch. Session state persists across heartbeats with automatic compaction when context windows fill up.
12. **Full work management** — alerts for automated signals, issues for everything else (remediation, detection tuning, compliance, post-incident). Agents create follow-up work that doesn't get lost in comments.

---

## Open Questions

- [ ] Should the control plane be a separate Python package/module or integrated into the core Calseta codebase?
- [ ] UI tech stack — does Calseta have an existing UI to extend, or is this the first UI? React + Vite is the obvious choice if starting fresh.
- [ ] How does this interact with the existing dispatch webhook system? Should dispatch become "queue + webhook" (both) or should users choose one mode?
- [x] ~~Secret management for LLM API keys — store encrypted in DB, env vars, or defer to external secret managers?~~ **Resolved:** Full secrets system specced with `local_encrypted` (AES-256-GCM in DB) and `env_var` providers for Phase 1, external providers (AWS SM, Vault) in Phase 8+. Secret_ref pattern for all credential fields.
- [ ] Incident vs. alert — should the control plane introduce an "incident" entity that groups related alerts, or keep alerts as the atomic unit? (Now more nuanced: alerts + issues + incidents form a work hierarchy.)
- [ ] Notification integrations — Slack first, but what about Teams, PagerDuty, Opsgenie?
- [ ] How does this affect Calseta's v1.0 milestone? Is the control plane part of v1.0 or a v2.0 feature?
- [ ] Sub-agent timeout behavior — what happens when a specialist takes too long? Orchestrator retries? Skips and reasons with partial data?
- [ ] Should orchestrators be able to invoke the same specialist multiple times in one investigation (e.g., SIEM agent called twice with different queries)?
- [x] ~~How do reference agents handle credentials for external tools?~~ **Resolved:** Via the secrets system. Reference agents use `secret_ref` bindings in adapter config. Operators register credentials once in secrets, agents reference by name.
- [ ] Should the agent builder UI support prompt versioning / A/B testing (e.g., compare two system prompts for the same agent)?

**New open questions (from Paperclip evaluation and PRD enhancements):**

- [ ] Session compaction strategy — should compaction use an LLM call to summarize (higher quality, costs tokens) or a truncation strategy (keep last N turns, zero cost)? Default to LLM summary with truncation as fallback?
- [ ] KB page injection token budget — what's the right default percentage of context window to allocate to KB context? 20% seems reasonable but may need tuning per-model.
- [ ] Agent memory promotion flow — when an agent promotes private memory to shared, does it require operator approval? Configurable per-instance?
- [ ] Issue/task system and alert assignments — should there be a unified "work item" abstraction, or keep alerts and issues as separate entity types with separate checkout mechanics? Separate is simpler now; unified is cleaner long-term.
- [ ] KB external sync conflict resolution — if an operator edits a synced page locally between syncs, what happens? Options: (a) external source always wins (overwrite), (b) conflict detected and flagged for operator, (c) local edits fork into a new non-synced page.
- [ ] Routine concurrency and the issue system — when a routine fires and creates an issue, should the issue be auto-assigned to the routine's agent, or go through normal routing?
- [ ] Campaign metric auto-computation — should Calseta auto-compute metrics (MTTD, FP rate, auto-resolve rate) from alert/assignment data, or require manual metric entry?
- [ ] UI working session scope — should we spec all pages at once (comprehensive but slow) or spec in priority order (approval inbox first, then agent detail, etc.) and iterate?
- [ ] Agent topology rendering — client-side JavaScript graph library (D3, cytoscape.js, react-flow) or server-side SVG (like Paperclip's org chart)?

---

## Rough Scope

**Extra Large** — this is a multi-phase effort that transforms Calseta from a data layer into a full platform.

- Phase 1: ~6-8 weeks (LLM providers, agent runtime, tool system, agent registry, adapters, queue, **session state, secrets, agent home, run-scoped JWTs** — the core platform) `[Part 1]` `[Part 5]`
- Phase 2: ~2 weeks (actions, approval gate integration) `[Part 2]`
- Phase 3: ~2-3 weeks (action execution integrations) `[Part 2]`
- Phase 4: ~1-2 weeks (heartbeat, budget enforcement, per-model cost tracking) `[Part 1]`
- Phase 5: ~3-4 weeks (multi-agent orchestration) `[Part 2]`
- Phase 5.5: ~3-4 weeks (**issue/task system, routine scheduler, agent topology**) `[Part 4]`
- Phase 6: ~4-6 weeks (operator UI — **expanded scope: KB browser, issue board, topology, routines, campaigns, secrets, PM view in agent detail**) `[Part 5]`
- Phase 6.5: ~3-4 weeks (**knowledge base + external sync + agent persistent memory**) `[Part 3]`
- Phase 7: ~3-4 weeks (reference agents, process adapter, agent builder UI) `[Part 1]`
- Phase 8: Ongoing (advanced features) `[All Parts]`

Total MVP (Phases 1-4, managed + external agents, API-only): ~12-15 weeks
Multi-agent orchestration (Phases 1-5): ~15-19 weeks
Full operational platform (Phases 1-5.5): ~18-23 weeks
Full platform with UI + KB + memory (Phases 1-6.5): ~25-33 weeks
Reference agents + agent builder (Phases 1-7): ~28-37 weeks

## Future Agent Types (Beyond Alert Triage)

The runtime engine is generic — it executes any managed agent, not just alert triage agents. The alert triage orchestrator is the first use case, but the same infrastructure supports:

### Detection Engineering Agents (Future)
- **Trigger**: on-demand or scheduled (cron via Procrastinate)
- **Input**: detection rule UUID or "all rules above X% FP rate"
- **Flow**: Agent loads detection rule from Calseta → queries FP rate metrics → analyzes `close_classification` data on related alerts → pivots to SIEM (via MCP tool) to investigate root cause → proposes detection rule fix as structured output → submits PR to detection-as-code repo (via workflow tool that calls GitHub API)
- **Tools needed**: `get_detection_rule`, `search_alerts` (filtered by rule), `get_metrics`, MCP SIEM query tool, workflow for GitHub PR submission
- **Why it works**: Same runtime, same tool system, same cost tracking. Just a different system prompt, methodology, and trigger (scheduled vs. alert-driven).

### Threat Intel Triage Agents (Future)
- **Trigger**: scheduled (daily) or on new intel submission
- **Input**: raw threat intel submitted to a Calseta endpoint (`POST /api/v1/threat-intel/ingest`)
- **Flow**: Agent loads unprocessed intel → categorizes (APT report, IOC list, vulnerability advisory, etc.) → extracts IOCs → cross-references against Calseta's indicator DB → prioritizes by relevance to existing detections → produces structured summary
- **Tools needed**: `search_indicators`, `search_alerts`, `search_detection_rules`, MCP threat intel tools (VirusTotal, OTX, etc.)
- **Why it works**: Same runtime. The scheduled trigger is just a Procrastinate periodic task that invokes `run_managed_agent_task`.

### What This Means Architecturally
All of these are just **different agent configs** — different system prompts, different tool sets, different triggers. The runtime engine, tool system, cost tracking, and approval gates are shared infrastructure. Adding a new agent type is:
1. Register LLM provider (if not already done)
2. Create agent definition (prompt, methodology, tools, trigger rules)
3. Done — Calseta runs it

---

## Notes

- This PRD intentionally excludes time estimates for Jorge's review — the scope sizes above are rough and depend on team capacity
- The adapter pattern aligns with Calseta's existing plugin architecture (`AlertSourceBase`, `EnrichmentProviderBase`) — `AgentAdapter`, `ActionIntegration`, and `LLMProviderAdapter` follow the same pattern
- Existing feature requests ([[evaluation-agent]], [[self-improving-agent]], [[embedded-llm-functionality]]) become Phase 8 integrations with the control plane
- Paperclip's full SPEC is ~5000 words of detailed design — referenced where applicable but adapted heavily for security domain
- Vigil SOC, Claude Agent SDK, LangChain deepagents, and Matousek's three-tier orchestration pattern were all analyzed in detail — see "Research & Validation (March 2026)" section for full findings, what was adopted, and what was skipped.
- The MCP-native approach is a significant differentiator. No other AI SOC platform supports MCP. Any MCP client is a Calseta agent. Orchestration tools available via MCP.
- **Calseta is both runtime AND control plane** — managed agents run inside Calseta (Calseta makes LLM API calls). External agents run independently and call back via HTTP/MCP. Both modes use the same queue, checkout, approval, cost tracking, and audit infrastructure.
- **LLM integrations are foundational, not an add-on** — registering LLM providers at the instance level enables: central API key management, per-model cost tracking, model swaps without touching agents, AND the runtime engine (which uses providers to make API calls).
- **Managed vs External is per-agent** — same deployment can have managed triage agents (Calseta runs them) alongside an external BYO orchestrator (team's custom agent that calls Calseta API). The `execution_mode` column on `agent_registrations` determines which path.
- **Reference agents are educational, not production-ready** — they ship as `examples/` with full source code and docs. Users fork and customize. This aligns with Calseta's open-source philosophy.
- The multi-agent orchestration pattern (hybrid: deterministic routing + LLM-driven investigation) keeps orchestration costs predictable while letting AI add value where it matters most

---

## Research & Validation (March 2026)

External systems and patterns were analyzed to validate and refine this PRD. This section documents what was evaluated, what was adopted, and what was deliberately skipped.

### Vigil SOC (github.com/Vigil-SOC/vigil) — Deep Codebase Analysis

Vigil is an open-source AI SOC platform with 12 specialized agents, Claude Agent SDK integration, and an autonomous daemon mode. Full codebase was cloned and analyzed.

**Adopted from Vigil:**
- **Tool tier safety model** (`safe`/`managed`/`requires_approval`/`forbidden`) — validates our identical tiering design. Vigil enforces these in daemon mode only; Calseta enforces them for all managed agents.
- **Confidence-scored approval thresholds** — Vigil uses 0.95+ auto-approve, 0.85-0.94 quick review, 0.70-0.84 human review, <0.70 investigate further. Adopted as the confidence override layer on top of action-type-based approval defaults.
- **Supervision loop pattern** — Vigil's daemon runs three concurrent async loops: Intake (poll for new findings), Supervision (stuck detection + timeout kills), Review (approve/rework completed investigations). Adapted into Calseta's `AgentSupervisor` as a periodic Procrastinate task rather than long-running loops.
- **Methodology-in-prompt pattern** — methodologies are pure text injected into system prompts via `<methodology>` sections. Validates our `methodology` field on `agent_registrations`.
- **Investigation state as JSONB** — Vigil uses filesystem-based `plan.md` + `state.json` per investigation. Calseta adapts this to `alert_assignments.investigation_state` JSONB for PostgreSQL-native persistence (cloud-scalable, queryable, crash-recoverable).

**Skipped from Vigil:**
- **Filesystem-based investigation state** — pragmatic for single-machine but not cloud-native. Calseta uses DB-backed JSONB instead.
- **Claude-only lock-in** — Vigil is tightly coupled to Anthropic SDK + Claude Agent SDK. Calseta's thin-adapter approach supports multiple LLM providers.
- **Code-configured agents** — Vigil defines agents as Python dataclasses in source code. Calseta uses DB-backed agent definitions editable via API/UI.
- **Single-machine daemon** — Vigil's orchestrator can't distribute across nodes. Calseta uses Procrastinate + PostgreSQL for distributed task execution.
- **Web UI role-playing** — Vigil's web mode has Claude role-play multiple agents sequentially in one conversation. Calseta uses real multi-agent delegation with separate LLM calls per specialist.

### Claude Agent SDK — Evaluated and Rejected for Runtime

The Claude Agent SDK was evaluated as a potential runtime for Calseta's managed agents.

**Why it was rejected:**
- **~12-second subprocess startup overhead per invocation** — disqualifying for a platform that needs to process 100+ alerts/hour across 50 concurrent agents. Each query spawns a fresh CLI subprocess.
- **Claude-only lock-in** — no pluggable LLM provider system. Violates Calseta's framework-agnostic principle.
- **No native cost tracking** — token counts require instrumenting hooks + OpenTelemetry integration with external observability (Langfuse, SigNoz). Calseta needs exact per-agent, per-alert cost data in the same database transaction as results.
- **Session model mismatch** — designed for interactive resume/fork semantics, not atomic alert checkout from a work queue.
- **Overkill** — provides a full CLI simulation (file editing, bash execution, etc.) when Calseta only needs a thin tool-calling loop.

**What was validated:**
- The PRD's thin-adapter approach (~200 lines per LLM provider) is confirmed as the right architecture. Direct SDK calls give: zero startup overhead, exact token tracking, multi-provider support, and full control over the conversation loop.
- The Agent SDK's `PreToolUse`/`PostToolUse` hooks pattern validates the concept of tool interception callbacks — implemented in Calseta as tool tier enforcement in the runtime engine.

### LangChain deepagents — Patterns Noted, Framework Not Adopted

deepagents is a LangGraph-based agent harness with model-agnostic design and LangSmith observability.

**Patterns worth studying (not adopting the framework):**
- **Context compression** — automatic conversation summarization for long-running investigations. Could be valuable for multi-wave investigations that accumulate large specialist result sets.
- **Task decomposition via `write_todos`** — orchestrators proposing explicit sub-investigation plans before delegating. Could inform the wave structure methodology convention.
- **Structured output enforcement at framework level** — deepagents enforces output schemas. Validates Calseta's specialist `output_schema` in capability declarations.

**Why the framework was not adopted:**
- **LangChain lock-in** — adds a framework dependency layer between Calseta and the LLM APIs, complicating cost tracking and provider management.
- **Single-agent design** — deepagents orchestrates one agent's execution, not a fleet of agents in a control plane.
- **Startup latency** — likely similar subprocess/process overhead to the Agent SDK.

### Matousek's Three-Tier Orchestration Pattern — Checkpoint Discipline Adopted, Governance Tier Skipped

David Matousek's "Anatomy of an Orchestration" proposes three tiers: Human Strategy (decides), Agent Governance (persistent, carries context across lifecycle), Agent Execution (ephemeral specialists). Wave coordination with checkpoint gates between phases.

**Adopted:**
- **Deterministic investigation checkpoints** — budget, depth, stalling, time, severity escalation. Enforced by the runtime engine between investigation waves. No LLM tokens burned on checkpoint evaluation.
- **Explicit wave structure** — Wave 1 (context gathering, parallel) → checkpoint → Wave 2 (scope assessment) → checkpoint → Wave 3 (response + approval gate). Expressed as a methodology convention, not rigid schema.
- **Per-work-unit budget caps** — `max_cost_per_alert_cents` prevents runaway investigations on a single alert (Matousek's insight: governance at the work-unit level, not just the agent level).
- **"Investigation stalling" detection** — N consecutive empty sub-agent results → flag for operator review.

**Skipped:**
- **Persistent governance agents** (PM Agent, Architect Agent, Team Lead Agent) — security investigations run in minutes, not days. The orchestrator IS the governance layer for investigation quality. Adding LLM agents to validate other LLM agents' work doubles cost with minimal benefit. Governance in SOC is a platform concern (permissions, budgets, approval gates), not an agent concern.
- **Separate "quality review" agent** — the orchestrator's synthesis step IS the review. A separate Investigation Reviewer Agent is redundant.
- **Cross-lifecycle persistent agent memory** — cross-investigation learning should be deterministic (database queries, indicator correlation, metrics), not stored in an agent's context window.

### Key Conclusion

The thin-adapter, deterministic-guardrails approach in this PRD is validated by all three external analyses. The runtime should be simple (~200 lines per LLM provider), governance should be platform-level deterministic controls (not governance agents), and investigation structure should be convention-based (methodology field) with runtime-enforced checkpoints at wave boundaries.
