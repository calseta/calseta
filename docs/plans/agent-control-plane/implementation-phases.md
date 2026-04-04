# Testing & Validation + Implementation Phases

> **Split PRD navigation:**
> [Overview](_overview.md) | [Part 1: Core Runtime](part-1-core-runtime.md) | [Part 2: Actions & Orchestration](part-2-actions-orchestration.md) | [Part 3: Knowledge & Memory](part-3-knowledge-memory.md) | [Part 4: Operational](part-4-operational.md) | [Part 5: Platform Ops](part-5-platform-ops.md) | [API & MCP](appendix-api-mcp.md) | [Implementation Phases](implementation-phases.md)

## Testing & Validation

> [!important] Test Before You Ship
> The agent control plane introduces the first LLM-in-the-loop behavior in Calseta. Every phase must be exercisable end-to-end before it is considered complete. This section defines the test infrastructure, mock data set, and integration test suite that must exist by the time Phase 1 ships.

### Quick-Standup Test Stack

A `make dev-agents` Makefile target provides a one-command testbed:

```
make dev-agents
  → docker compose up (existing Calseta stack)
  → python scripts/seed_agent_testbed.py
      → seeds: 1 ClaudeCode LLM integration (local, no API key)
      → seeds: 1 orchestrator agent (process adapter → examples/agents/lead-investigator)
      → seeds: 3 specialist agents (siem-query, identity, threat-intel)
      → seeds: mock alert dataset (see below)
      → seeds: global instruction files + KB pages + tool registrations
  → prints: agent API keys, Calseta UI URL, queue depth
```

The `process` adapter (Phase 7) is used here for local dev only — it spawns reference agent subprocesses for end-to-end testing without a separate hosted agent service. Production uses `http` or `mcp` adapters.

**Prerequisites for `make dev-agents`:**
- `docker compose up` running
- `claude` CLI installed and logged in (`claude auth login`)
- Python env with `httpx` installed

### Mock Alert Dataset

`scripts/fixtures/mock_alerts.json` contains 20 alerts across 5 realistic scenarios. Each fixture includes the raw source payload (Sentinel format to exercise the existing normalizer), pre-computed expected indicator extractions, and expected enrichment verdicts (mocked — no live VirusTotal calls needed in tests).

| Scenario | Count | Indicators | Tests |
|---|---|---|---|
| **Credential stuffing** | 5 alerts | Shared IPs hitting multiple accounts | Indicator deduplication, alert correlation, user validation rule trigger |
| **Impossible travel** | 2 alerts | User login NYC + Amsterdam, 20min apart | Identity agent, user validation flow, severity bump on deny |
| **Ransomware beachhead** | 1 alert (Critical) | 3 malicious IPs, 2 hashes, 1 domain | Full orchestrator → multi-specialist delegation, action proposal |
| **Lateral movement** | 3 alerts | Shared host + internal IPs across alerts | Alert queue checkout dedup, assignment state machine |
| **Coinminer on EC2** | 2 alerts | Outbound C2 IPs, known mining domains | Enrichment → response action (block_ip proposal), approval gate |
| **Benign noise** | 7 alerts | Mix of low-severity, FP-likely | False positive classification, auto-close on user confirm |

Seed script injects these alerts via `POST /v1/ingest/{source}` — the full ingest pipeline runs (normalization, enrichment via mocked providers, indicator extraction, dispatch). Enrichment providers are stubbed in test mode via `ENRICHMENT_STUB=true` env var that returns pre-seeded verdicts from fixture files.

### Integration Test Suite

```
tests/integration/agent_control_plane/
├── test_phase1_llm_providers.py        # Register provider, test_environment(), adapter routing
├── test_phase1_checkout.py             # Atomic checkout invariant — concurrent requests → exactly 1 winner
├── test_phase1_heartbeat.py            # Heartbeat lifecycle, stuck detection (time-travel via freeze_time)
├── test_phase1_managed_agent.py        # Full run: checkout → LLM call (mocked) → tool loop → finding → close
├── test_phase1_claude_code_adapter.py  # ClaudeCodeAdapter subprocess invocation, session resume, cost extraction
├── test_phase2_actions.py              # Propose action → approval gate → execute → rollback
├── test_phase2_user_validation.py      # Validation rule matching, DM mock, confirm/deny/timeout flows
├── test_phase4_budget.py               # Soft alert, hard stop, per-alert cap, subscription vs API billing_type
├── test_phase5_orchestration.py        # Orchestrator → 2 specialists in parallel → synthesize findings
└── fixtures/
    ├── mock_alerts.json                # Canonical 20-alert dataset (symlink from scripts/fixtures/)
    ├── mock_llm_responses.py           # Canned LLM response sequences for managed agent tests
    └── mock_enrichment.py              # Stubbed enrichment verdicts
```

**LLM mocking strategy:** Mock `LLMProviderAdapter.create_message()` at the interface boundary — never call real LLM APIs in CI. `mock_llm_responses.py` contains canned response sequences that exercise: tool call → result → tool call → result → text completion, tool permission denial, session compaction trigger, and budget exceeded mid-loop.

**`ClaudeCodeAdapter` tests** use a mock `claude` subprocess (via `unittest.mock.patch("asyncio.create_subprocess_exec")`) that returns valid stream-json NDJSON — exercises the parsing logic without requiring a real `claude` CLI install.

**Real DB, no mocks for data layer:** All integration tests use a real PostgreSQL test instance (same pattern as existing Calseta tests). No SQLAlchemy mocking. The atomic checkout invariant test (`test_phase1_checkout.py`) runs 10 concurrent checkout requests against the same alert and asserts exactly 1 succeeds.

### End-to-End Smoke Test

`scripts/e2e_smoke_test.py` — a single script that validates a full investigation cycle against a live local stack:

```
1. Register ClaudeCode LLM integration (POST /api/v1/llm-integrations)
2. Register a triage agent (managed, process adapter, sonnet-4-6)
3. Ingest the ransomware beachhead fixture alert
4. Wait for enrichment to complete (poll /api/v1/alerts/{uuid})
5. Manually trigger agent heartbeat (POST /api/v1/agents/{uuid}/heartbeat)
6. Assert: alert assigned, agent status → running
7. Wait for heartbeat completion (poll /api/v1/agents/{uuid}/heartbeat-runs)
8. Assert: finding posted, action proposed, alert status updated
9. Print: cost_events summary, session_id, token counts
```

Run time target: under 2 minutes for the smoke test with `ClaudeCodeAdapter` + claude-haiku-4-5.

### CI Strategy

| Test type | When | LLM | DB |
|---|---|---|---|
| Unit tests | Every push | Mocked | In-memory / mocked |
| Integration tests | Every push | Mocked | Real PostgreSQL container |
| E2E smoke test | Manual / pre-release | `ClaudeCodeAdapter` (local only) | Real PostgreSQL |
| Load/chaos tests | Phase 8+ | N/A | Real PostgreSQL |

The E2E smoke test is intentionally excluded from automated CI — it requires a real `claude` CLI session and is meant for developer validation before shipping a phase. It is documented in `docs/guides/HOW_TO_TEST_AGENTS.md` and run manually.

---

## Implementation Phases

> [!important] Enterprise-First Phasing
> LLM provider registration, the agent runtime engine, and the tool system are foundational. The `process` adapter (subprocess spawning) is deferred to Phase 7+ as a dev/demo convenience. Managed agents run inside Calseta; external agents communicate via HTTP.

### Phase 1 — LLM Providers + Agent Registry + Agent Runtime + Tool System (Foundation) `[Part 1]` `[Part 5: Secrets, Auth]`

**Goal:** Operators register LLM providers, define managed agents (prompt + tools + LLM), and Calseta executes them. Also supports external agents via pull-based queue. This is the biggest phase — it ships the core platform.

**LLM Provider Management:** `[Part 1]`

- `llm_integrations` table + Alembic migration
- LLM integration CRUD endpoints (`POST/GET/PATCH/DELETE /api/v1/llm-integrations`)
- LLM usage endpoint (`GET /api/v1/llm-integrations/{id}/usage`)
- API key storage: reference to env var or secret manager key (never plaintext in DB)
- `is_default` flag — agents without explicit LLM config use the default
- `LLMProviderAdapter` ABC + `AnthropicAdapter` + `OpenAIAdapter` + `ClaudeCodeAdapter` (local dev provider)

**Agent Registry Extension:** `[Part 1]`

- Alembic migration: add new columns to `agent_registrations` (`execution_mode`, `agent_type`, `role`, `status`, `adapter_type`, `adapter_config`, `capabilities`, `llm_integration_id`, `system_prompt`, `methodology`, `tool_ids`, `max_tokens`, `enable_thinking`, `sub_agent_ids`, `max_sub_agent_calls`, `budget_monthly_cents`, `spent_monthly_cents`, `budget_period_start`, `last_heartbeat_at`, `max_concurrent_alerts`, `memory_promotion_requires_approval` BOOL default `false`)
- ~~Migrate `is_active` boolean → `status` enum~~ **Done in Phase 1** (`active`/`paused`/`terminated`; `is_active` column dropped)
- `agent_api_keys` table + key generation/hashing (for external agents calling back into Calseta)
- Agent API key auth middleware (Bearer token → agent context for inbound calls)
- Extend existing agent CRUD endpoints with new fields (including `execution_mode`, `llm_integration_id`, `system_prompt`, `tool_ids`)
- New lifecycle endpoints: `pause`, `resume`, `terminate`

**Tool System:** `[Part 1]`

- `agent_tools` table + migration
- Tool CRUD endpoints (`GET/POST/PATCH/DELETE /api/v1/tools`)
- Auto-register Calseta built-in tools at startup (get_alert, search_alerts, post_finding, update_alert_status, get_enrichment, get_detection_rule, list_context_documents, etc.)
- MCP tool sync endpoint (`POST /api/v1/tools/sync`) — discovers tools from connected MCP servers
- Tool tier enforcement in runtime (safe/managed/requires_approval/forbidden)
- Workflow-as-tool registration — expose existing workflows as callable tools

**Agent Runtime Engine:** `[Part 1]`

- `AgentRuntimeEngine` — main execution loop for managed agents
- Prompt construction: system_prompt + methodology + alert context + tool schemas
- Tool call routing: intercept LLM tool calls → check tier → execute → return result
- `cost_events` recording on every LLM API call (exact token counts from provider response)
- Investigation state tracking on `alert_assignments.investigation_state` (JSONB)
- Timeout and cancellation support
- Procrastinate task: `run_managed_agent_task` — executes managed agent in worker process

**Adapter System (External Agents):** `[Part 1]`

- `AgentAdapter` ABC
- `http` adapter implementation (for external agents)
- `mcp` adapter implementation (heartbeat inferred from MCP tool activity)
- `webhook` adapter continues working as-is (existing behavior, no changes)

**Session State + Agent Home:** `[Part 1]`

- `agent_task_sessions` table + migration
- `heartbeat_runs` table + migration (tracks each agent invocation lifecycle; required by Phase 1 runtime)
- `cost_events` table + migration (token + cost tracking per LLM call; required by Phase 1 runtime's `cost_events` recording)
- Session resolution in runtime: lookup by agent_id + task_key, resume or create fresh
- Session compaction logic: detect threshold, generate handoff summary, inject into next heartbeat
- Session compaction config on `agent_registrations` (threshold_pct, strategy enum: `summarize`/`truncate`, max_heartbeats)
- Agent home directory creation at agent registration (`$CALSETA_DATA_DIR/agents/{id}/`)
- `AGENT_HOME` environment variable set during invocation
- Agent file API endpoints (`GET/PUT/DELETE /api/v1/agents/{uuid}/files/{path}`)

**Secrets Foundation:** `[Part 5]`

- `secrets` table + `secret_versions` table + migrations
- Secret CRUD endpoints (`POST/GET/DELETE /api/v1/secrets`)
- Secret version rotation endpoint (`POST /api/v1/secrets/{name}/versions`)
- `local_encrypted` provider (AES-256-GCM in PostgreSQL)
- `env_var` provider (reads from environment)
- `secret_ref` resolution in adapter config, LLM integration config, and KB sync config
- Sensitive key detection regex + strict mode option
- Log redaction for resolved secret values in heartbeat run logs
- Run-scoped JWT generation for managed agents (`CALSETA_AGENT_JWT_SECRET`)
- JWT verification middleware in auth resolution chain

**Alert Queue + Checkout:** `[Part 1]`

- `alert_assignments` table + migration
- Alert queue endpoint (`GET /api/v1/queue`) — returns enriched alerts matching agent's trigger filters
- Atomic checkout endpoint (`POST /api/v1/queue/{alert_id}/checkout`)
- Release endpoint (`POST /api/v1/queue/{alert_id}/release`)
- Bridge: after enrichment, route to managed agent (auto-checkout + execute) or create queue entry for external agents
- MCP tools: `get_pending_alerts`, `checkout_alert`, `release_alert`, `get_assignment`
- Activity logging for all new mutations (extends existing `ActivityEvent` system)

**Exit criteria:** Operator registers "claude-opus" as an LLM provider. Creates a managed Triage Agent with system prompt, methodology, tool set (get_alert, search_alerts, post_finding), linked to claude-opus. Alert arrives → matches agent trigger → Calseta auto-checks out alert → runtime engine constructs prompt (6-layer system) → calls Anthropic API → agent uses tools → findings posted → cost recorded → session state persisted for next heartbeat. External agents authenticate with agent API key, managed agents get run-scoped JWTs. Secrets resolved securely with log redaction. Both managed and external agents coexist.

**Phase 1 Alembic migration summary (for implementation reference):**

New tables: `llm_integrations`, `agent_api_keys`, `agent_tools`, `alert_assignments`, `agent_task_sessions`, `heartbeat_runs`, `cost_events`, `secrets`, `secret_versions`

Key constraints:
- `llm_integrations.name` UNIQUE
- `agent_tools.name` UNIQUE
- `alert_assignments(alert_id, agent_registration_id)` UNIQUE — single-assignee invariant
- `agent_task_sessions(agent_registration_id, task_key)` UNIQUE — session resumption key
- `secret_versions(secret_id, version)` UNIQUE — version uniqueness per secret

`agent_registrations` ALTER TABLE: adds `execution_mode`, `agent_type`, `role`, `status`, `adapter_type`, `adapter_config`, `capabilities`, `llm_integration_id`, `system_prompt`, `methodology`, `tool_ids`, `max_tokens`, `enable_thinking`, `sub_agent_ids`, `max_sub_agent_calls`, `budget_monthly_cents`, `spent_monthly_cents`, `budget_period_start`, `last_heartbeat_at`, `max_concurrent_alerts`, `max_cost_per_alert_cents`, `max_investigation_minutes`, `stall_threshold`, `instruction_files`, `memory_promotion_requires_approval`.

~~Data migration: `UPDATE agent_registrations SET status = CASE WHEN is_active THEN 'active' ELSE 'paused' END` before dropping `is_active`.~~ **Completed in Phase 1.** The `is_active` column has been dropped; `status` enum is the live column.

All indexes from the "Required Indexes (Part 1)" section above apply to this migration.

### Phase 2 — Actions + Approval Gates (Human-in-the-Loop) `[Part 2]`

**Goal:** Agents can propose actions, humans approve via existing Slack/Teams/browser flows, Calseta tracks everything.

- `agent_actions` table + migration (with `approval_request_id` FK to existing `workflow_approval_requests`)
- Extend `WorkflowApprovalRequest.trigger_context` schema for response action metadata
- Add `"agent_action"` trigger_type to existing approval system
- Propose action endpoint (`POST /api/v1/actions`) — creates `agent_actions` row + `WorkflowApprovalRequest` when approval needed
- New Procrastinate task: `execute_response_action_task` (runs `ActionIntegration` after approval, parallel to existing `execute_approved_workflow_task`)
- Extend existing notifier message templates to show response action details (target, action type, agent reasoning)
- Assignment completion flow (agent marks alert resolved with resolution type)
- MCP tools: `propose_action`, `get_action_status`, `complete_assignment`
- Activity logging via existing activity event system

**Exit criteria:** Agent proposes "block IP" action → existing approval system creates `WorkflowApprovalRequest` → operator approves via Slack button → `execute_response_action_task` fires → action status transitions to completed. Auto-execute works for notification/enrichment actions.

### Phase 3 — Integration Execution Engine (Close the Loop) `[Part 2]`

**Goal:** Approved actions actually execute against security tools. Integration = workflow (same pattern operators already know).

- `ActionIntegration` base class (same pattern as `EnrichmentProviderBase`) — implement as Procrastinate-executed workflow
- Generic Webhook integration — first integration: POST to configurable URL with payload template. This IS a workflow. Ships as the reference implementation for "how to add a new integration."
- `app/integrations/actions/CONTEXT.md` — LLM context file documenting extension pattern: subclass `ActionIntegration`, implement `execute()` + `rollback()` + `supported_actions()`, register in tool registry, write `documentation` field, add `docs/integrations/{name}/SETUP.md`
- Execution engine: approved action → find integration → execute → record result
- Rollback support for reversible actions
- Additional integrations: Slack (`send_alert`, `notify_oncall`), CrowdStrike (`isolate_host`, `lift_containment`), Entra ID (`disable_user`, `revoke_sessions`)
- `SlackUserValidationIntegration` — DM users using configured template + response handling (see User Validation Rules system)
- `user_validation_rules` + `user_validation_templates` tables + migrations
- User Validation Rule evaluation added to enrichment completion pipeline
- Execution result stored on `agent_actions.execution_result`
- Failed execution → retry logic or manual intervention flag
- **Integration documentation requirement:** Every integration ships with `docs/integrations/{name}/SETUP.md` covering: required API permissions (least-privilege list with specific scope names), API key/credential creation steps, authentication setup walkthrough, what Calseta does with each permission, rate limits, and common failure modes. This is a mandatory shipping requirement — no integration merges without it.

**Exit criteria:** Agent proposes "isolate host" → operator approves → CrowdStrike integration isolates the host → result recorded → alert marked resolved. User validation flow: alert matches `user_validation_rule` → DM sent via configured template → user confirms → `on_confirm` action executes (alert auto-closed with response attached).

### Phase 4 — Heartbeat + Budget Controls + Supervision (Operational Maturity) `[Part 1]`

**Goal:** Monitor agent health, enforce cost limits per-agent and per-LLM-provider, detect stuck/stalling investigations.

> Note: `heartbeat_runs` and `cost_events` tables are created in Phase 1 (required by the runtime engine). Phase 4 adds the supervision layer, reporting endpoints, and budget enforcement logic on top of those tables.

- Heartbeat reporting endpoint (external agents POST to signal liveness; managed agents auto-record via runtime)
- Scheduler: periodic heartbeat checks, stuck detection
- Cost reporting endpoint (`POST /api/v1/cost-events`) — external agents report their own costs; managed agents auto-record
- Cost summary endpoints: by-agent, by-alert, by-LLM-provider, instance-wide
- Budget enforcement: soft alert at 80%, hard-stop at 100% (auto-pause agent)
- Per-alert budget enforcement: `max_cost_per_alert_cents` checked after each LLM call in runtime engine
- `AgentSupervisor` — periodic Procrastinate task (`supervise_running_agents_task`, every 30s):
  - Stuck agent detection: no heartbeat or tool activity beyond `timeout_seconds`
  - Stall detection: `stall_threshold` consecutive empty sub-agent results
  - Time enforcement: investigation duration vs `max_investigation_minutes`
  - Concurrency enforcement: no agent exceeds `max_concurrent_alerts`
- Investigation checkpoint context injection: budget/stall/time status injected into orchestrator prompts at wave boundaries
- MCP tools: `report_cost`, `get_agent_context` (includes budget status + checkpoint status)
- Monthly budget reset logic

**Exit criteria:** Agent reports cost with LLM integration reference → costs tracked per-agent AND per-LLM-provider → budget approaches limit → soft alert fires → budget exceeded → agent auto-paused → operator raises budget and resumes. Per-alert budget: investigation exceeds per-alert cap → paused → operator notified. Supervision: stuck agent killed after timeout → alert released back to queue. Stalling investigation flagged after N empty results → operator notified.

### Phase 5 — Multi-Agent Orchestration `[Part 2]`

**Goal:** Orchestrator agents delegate to specialist sub-agents, full investigation trees are tracked.

- `agent_invocations` table + migration
- Sub-agent delegation endpoints (`POST /api/v1/invocations`, `POST /api/v1/invocations/parallel`)
- Invocation result polling endpoint (`GET /api/v1/invocations/{id}/poll`)
- Agent catalog endpoint (`GET /api/v1/agents/catalog`) — specialists with capability declarations
- MCP orchestration tools: `list_available_agents`, `delegate_task`, `delegate_parallel`, `get_task_result`, `get_all_results`
- Alert routing engine: deterministic rules match alerts to orchestrators based on `alert_filter`
- Cost rollup: sub-agent costs aggregate to parent invocation → parent agent → alert → LLM provider
- Invocation depth limit enforcement (1 level: orchestrator → specialist only)

**Exit criteria:** An orchestrator agent receives an alert, invokes 3 specialist sub-agents in parallel via MCP tools or REST API, collects structured results, synthesizes findings, and proposes a response action. Full invocation tree visible via API with cost rollups per sub-agent and per LLM provider.

### Phase 5.5 — Issue/Task System + Routine Scheduler + Agent Topology `[Part 4]`

**Goal:** Non-alert work management, scheduled agent invocations, and fleet visibility.

**Issue/Task System:** `[Part 4]`

- `agent_issues` table + `agent_issue_comments` table + migrations
- Issue CRUD endpoints (`POST/GET/PATCH /api/v1/issues`)
- Atomic checkout for issues (same pattern as alert assignments)
- Issue comment endpoints
- MCP tools: `create_issue`, `get_my_issues`, `update_issue_status`, `add_issue_comment`, `checkout_issue`
- Agent detail: issues assigned to agent endpoint (`GET /api/v1/agents/{uuid}/issues`)
- Activity logging for issue mutations

**Routine Scheduler:** `[Part 4]`

- `agent_routines` (includes `preferred_agent_id` nullable FK — routing hint, not hard assignment) + `routine_triggers` + `routine_runs` tables + migrations
- Routine CRUD endpoints
- Cron expression parser (5-field)
- Procrastinate periodic task: `evaluate_routine_triggers_task` (runs every 30s)
- Concurrency policy enforcement (skip_if_active, coalesce_if_active, always_run)
- Webhook trigger endpoint with HMAC verification + replay window
- Manual trigger endpoint
- Routine failure tracking + auto-pause after N consecutive failures
- Issues created by routines go through normal agent routing. `preferred_agent_id` is surfaced as a routing hint (not a hard assignment) — the routing engine respects it when the preferred agent is available and has capacity.

**Campaigns (moved from Phase 8):** `[Part 4]`

- `campaigns` + `campaign_items` tables + migrations
- Campaign CRUD endpoints (`POST/GET/PATCH /api/v1/campaigns`, `POST/DELETE /api/v1/campaigns/{id}/items`)
- Metric auto-computation: Procrastinate periodic task computes `current_value` from alert/assignment data for all active campaigns (MTTD, FP rate, auto-resolve rate, and other metrics derivable from existing data). **No manual metric entry — metrics are always system-computed.** Operators set `target_metric` + `target_value`; Calseta fills in `current_value` automatically.
- Campaign metrics endpoint (`GET /api/v1/campaigns/{id}/metrics`)

**Agent Topology:** `[Part 4]`

- Topology computation from existing agent config (types, sub_agent_ids, trigger_filters, capabilities)
- Topology API endpoint (`GET /api/v1/topology`)
- Routing path computation, delegation path computation

**Exit criteria:** Agent creates a remediation issue during an investigation → issue tracked with subtasks → assignee agent picks it up on next heartbeat. Scheduled routine fires daily → creates issue via normal routing → agent processes. Campaign created with MTTD target → Calseta auto-computes current MTTD from alert/assignment timestamps and updates `current_value`. Topology API returns agent fleet graph with routing + delegation paths.

### Phase 6 — Knowledge Base + Agent Memory (Organizational Knowledge) `[Part 3]`

**Goal:** Ship the knowledge base system and agent persistent memory. Agents and operators can create, search, and inject knowledge into agent prompts.

> **Note:** Phase 6 ships before the full Operator UI (Phase 6.5) so that Phase 6.5 can build the KB browser, KB editor, and memory-related UI against a live backend. The Phase 1 runtime stubs KB injection (Layer 3) with an empty list until this phase ships.

**Knowledge Base:** `[Part 3]`

- `knowledge_base_pages` table + `kb_page_revisions` table + `kb_page_links` table + migrations
- KB CRUD endpoints (`POST/GET/PATCH/DELETE /api/v1/kb`)
- KB search endpoint (full-text via PostgreSQL `tsvector`)
- Folder hierarchy endpoint
- Revision history endpoints
- Context injection resolver: `resolve_kb_context(agent)` — global + role-scoped + agent-specific pages
- Token budget enforcement for KB injection (configurable % of context window); default target 10–20% per token budget table
- Injection into Layer 3 of prompt construction system (replaces stub from Phase 1)
- Sync default: pull-only (external source always wins on hash change). Local edits to synced pages are overwritten on next sync — operators who need annotations should use a linked non-synced companion page.
- MCP tools: `create_kb_page`, `update_kb_page`, `search_kb`, `get_kb_page`, `link_kb_page`
- KB page linking to alerts, issues, agents, campaigns

**External Sync (Phase 1 sources):** `[Part 3]`

- GitHub sync provider (public + private repos via secret_ref)
- Confluence sync provider (REST API, storage format → markdown conversion)
- URL sync provider (HTTP GET, assumes markdown)
- Procrastinate periodic task: `sync_kb_pages_task` (configurable interval, default 6h)
- Manual sync trigger endpoint
- Content hash change detection

**Agent Persistent Memory:** `[Part 3]`

- Memory conventions on KB pages (folder: `/memory/agents/{id}/`, auto-scoped injection)
- Memory tools: `save_memory`, `recall_memory`, `update_memory`, `promote_memory`, `list_memories`
- `promote_memory` promotion flow: no operator approval required by default (`memory_promotion_requires_approval = false` on `agent_registrations`). Configurable per-instance for high-assurance deployments.
- Staleness detection: TTL-based expiry + hash-based invalidation
- Memory injection into Layer 6 of prompt construction (budget-capped, prioritized)
- Stale memory prefix injection (`[STALE — last updated X hours ago]`)

**Exit criteria:** Operator creates a KB page "Credential Theft Runbook", tags it with `inject_scope: { roles: ["investigation"] }`. All investigation agents automatically receive this page in their prompt. Agent creates a memory entry after scanning a codebase; on next heartbeat, the memory is injected. KB page synced from GitHub wiki updates automatically every 6 hours.

### Phase 6.5 — Full Operator UI (Visibility) `[Part 5]`

> [!important] UI Working Session Required Before Implementation
> Every page below requires a dedicated design working session to spec layout, components, interactions, data requirements, error/empty/loading states, and real-time update strategy. The UI must be enterprise-grade — SOC operators use this in high-pressure situations. See the "Page Detail Specs" note in the Operator UI architecture section.

**Goal:** Full operator dashboard for the control plane, including all new feature surfaces. Phase 6 (KB + Memory) must be complete before KB-related UI pages can be built.

**Stack:** Extends existing React 19 + Vite UI. All pages follow the design patterns and token conventions documented in `ui/DESIGN_SYSTEM.md`. No new framework or app — extend the existing one.

**Core Pages (MVP):** `[Part 1]` `[Part 2]`

- Approval inbox page — **build first**, highest operational impact
- Dashboard page (agent status, queue depth, pending approvals, costs by LLM provider)
- Agent registry page (list, create with LLM provider selection, configure)
- Agent detail page — **command center**: config, heartbeats, cost breakdown, **PM view (assigned work by status)**, sessions, delegation history
- Investigation tree view (orchestrator → sub-agent invocations → findings → cost per step)
- Alert queue page (pending, assigned, resolved)

**New Feature Pages:** `[Part 3]` `[Part 4]` `[Part 5]`

- Agent topology page — interactive DAG/graph visualization of agent fleet using `@xyflow/react` (already a project dependency) `[Part 4]`
- Issue board page — non-alert work items by status, category tabs, linked alert references `[Part 4]`
- Issue detail page — description, comments, linked entities, history `[Part 4]`
- Knowledge base browser — folder tree nav, rendered markdown, search, injection scope badges (requires Phase 6) `[Part 3]`
- KB page detail — rendered markdown, revision history, linked entities, sync status (requires Phase 6) `[Part 3]`
- KB page editor — markdown editor with preview, injection scope picker, sync config (requires Phase 6) `[Part 3]`
- Routine dashboard — routine list with status, next run, trigger type, run history `[Part 4]`
- Routine detail — trigger config, run history, linked issues, failure tracking `[Part 4]`
- Campaign dashboard — strategic objectives, auto-computed metric progress charts, linked items `[Part 4]`
- Campaign detail — metric history, linked alerts/issues/routines `[Part 4]`
- Secrets management page — create/rotate/revoke, view references, provider config `[Part 5]`

**Settings & Admin Pages:** `[Part 1]` `[Part 2]`

- LLM integrations page (register providers, manage API key refs, view per-model costs)
- Cost dashboard page (spend by agent, by LLM provider, by time, budget policy management)
- Activity log page (searchable audit stream)
- Action integration settings page (per-integration approval mode config)

**Real-time:**

- SSE/WebSocket event stream for live updates (agent status changes, new approvals, run completions)
- Real-time log streaming for active heartbeat runs

**Exit criteria:** Operator can manage the full control plane through the web UI: agents, alerts, issues, KB, routines, campaigns, secrets, topology, costs, approvals, and activity. All new features have dedicated, well-designed UI surfaces. Agent detail page includes PM view showing tasks by status.

### Phase 7 — Reference Agents + Dev Tooling (Option B) `[Part 1]`

**Goal:** Ship reference agent implementations and dev convenience tooling. Users fork and customize for their environment.

**What "reference agents" means:**
Reference agents are **working examples**, not plug-and-play templates. They ship in an `examples/agents/` directory with full source code, system prompts, capability declarations, and documentation explaining the design decisions. They demonstrate how to build Calseta-native agents — not a production deployment you use as-is. Every organization has different tools, SIEMs, identity providers, and processes, so the examples are meant to be forked and adapted.

**`process` adapter (dev/demo convenience):** `[Part 1]`

- `process` adapter implementation — spawns local child processes for running reference agents locally
- Only intended for local development and demos, not production

**Reference orchestrator:**

- `examples/agents/lead-investigator/` — orchestrator that receives enriched alerts, decides which specialists to invoke based on alert type/indicators, synthesizes findings, and proposes response actions

**Reference specialists:**

- `examples/agents/siem-query-agent/` — runs KQL/SPL queries to find related events, build timelines. Shows how to integrate with Sentinel/Splunk/Elastic APIs.
- `examples/agents/threat-intel-agent/` — deep-dives IOCs beyond Calseta's built-in enrichment. Queries VirusTotal, GreyNoise, Shodan, OTX, correlates across sources.
- `examples/agents/identity-agent/` — investigates user context: recent logins, MFA status, impossible travel, group memberships, OAuth app consents. Shows Entra/Okta integration patterns.
- `examples/agents/endpoint-agent/` — pulls process trees, persistence mechanisms, lateral movement artifacts from CrowdStrike/Defender/SentinelOne.
- `examples/agents/historical-context-agent/` — searches Calseta's own alert/assignment history for prior investigations involving the same entities.
- `examples/agents/response-agent/` — given investigation findings, recommends specific containment/remediation actions with confidence scores and reasoning.

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

- In-UI agent creation with system prompt editor
- Capability declaration builder (structured form → JSON)
- "Fork from reference" flow: pick a reference agent, customize in-browser
- Test invocation: send a sample alert to the agent and see the response
- Prompt versioning: inherited from KB revision system (agent instruction files are KB pages; revision history is automatic). A/B testing (comparing two system prompts side-by-side) is Phase 8+.

### Phase 8 — Advanced Features (Differentiation) `[All Parts]`

**Goal:** Features that make Calseta's control plane uniquely valuable for security.

- ~~Incident grouping~~ — **Scoped to a separate PRD** (not part of this project)
- Feedback loop integration with [[evaluation-agent]] feature request `[Part 2]`
- Gap detection integration with [[self-improving-agent]] feature request `[Part 2]`
- Embedded LLM integration with [[embedded-llm-functionality]] feature request for operator-side AI assistance `[Part 5]`
- Export/import agent configurations (portable agent configs, not full templates) `[Part 1]`
- Calseta Agent SDK (Python package for building Calseta-native agents — formalizes patterns from reference agents) `[Part 1]`
- Multi-level delegation (sub-agents can invoke sub-sub-agents with configurable depth limit) `[Part 2]`
- Agent-to-agent knowledge sharing (now partially addressed by KB + memory system — extend with automatic cross-agent knowledge promotion) `[Part 3]`
- User validation campaign system — batch DM outreach for credential stuffing / mass compromise scenarios with per-recipient tracking, rate-limited delivery, and aggregate dashboards `[Part 2]`
- Semantic search for KB (pgvector embeddings, conceptual similarity search) `[Part 3]`
- Notion sync provider for KB `[Part 3]`
- AWS Secrets Manager provider + HashiCorp Vault provider for secrets `[Part 5]`
- ~~Investigation campaign metric auto-computation~~ — **Moved to Phase 5.5** (metrics are always auto-computed; no manual entry)
- Mid-execution agent interruption — operator injects context into a running managed agent (extends checkpoint injection to support human-initiated injection) `[Part 1]`
- Notion/Jira/Linear sync for issues (bidirectional sync with external project management) `[Part 4]`
- Agent memory semantic search (vector-based recall in addition to keyword) `[Part 3]`

---

