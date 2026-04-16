# Agent Runtime Hardening

**Date**: 2026-04-15
**Author**: Jorge Castro
**Status**: Draft

## Problem Statement

Calseta's agent control plane (Phases 1-6) shipped a functional runtime: managed agents investigate alerts via a tool loop, sessions persist across heartbeats, orchestrators delegate to specialists, and a supervisor enforces timeout/budget/stall rules. But the runtime lacks the operational maturity needed for production SOC work:

1. **Agents are black boxes.** No real-time output streaming. An analyst dispatches an agent to a critical alert and waits — no visibility into what it's doing, which tools it's calling, what data it's accessing. The only feedback is "succeeded" or "failed" after the run ends.

2. **Agents can't be stopped.** No cancellation mechanism. If an agent is misconfigured or taking wrong actions on a live incident, the only recourse is waiting for timeout (default 30s, but could be minutes for complex investigations).

3. **Agent output isn't auditable.** No persistent run logs with integrity guarantees. SOC compliance (SOC2, ISO 27001) requires immutable records of every automated action on security data. Today, agent output exists only in-memory during execution and is discarded.

4. **Failed agents leave orphans.** If the worker process crashes mid-investigation, the alert assignment stays `in_progress` forever until timeout. No PID tracking, no orphan detection, no auto-retry.

5. **Agents can't be woken by analyst input.** An analyst adds context to an alert ("this IP is our VPN egress, re-investigate") but the agent doesn't know. No comment-driven re-triggering.

6. **The adapter layer is closed.** Only in-tree LLM adapters. Organizations with custom LLM gateways, fine-tuned models, or proprietary agent frameworks can't plug into Calseta without forking.

This PRD addresses all six problems. The reference implementation is Paperclip's agent runtime (audited 2026-04-14), adapted for security operations.

## Solution

When this ships, a SOC analyst will be able to:

- **Watch an investigation unfold in real-time** — a streaming transcript view shows every LLM turn, tool call, finding, and action proposal as the agent works. SSE-backed, with HTTP polling fallback.
- **Cancel a running agent immediately** — one click sends SIGTERM, waits 15s for graceful shutdown, then SIGKILL. The alert assignment is released and the next queued agent starts.
- **Audit every agent action** — every run produces a tamper-evident NDJSON log (SHA256 hash + byte count). Structured run events are queryable in the DB. Log retention is configurable.
- **Trust auto-recovery** — if a worker dies, the supervisor detects orphaned runs via PID health check and auto-retries once. Alert assignments don't get stuck.
- **Re-trigger investigations via comments** — an analyst posts a note on an alert, and the assigned agent wakes up to incorporate the new context.
- **Plug in any LLM backend** — external adapters loaded from Python packages at startup. A company can write a 50-line adapter for their internal LLM gateway and register it without forking Calseta.

## User Stories

### Real-Time Streaming

1. As a SOC analyst, I want to see an agent's investigation in real-time so that I can intervene if it's going down the wrong path on a critical alert.
2. As a SOC analyst, I want to see exactly which tools an agent called and what data it accessed so that I can trust its findings.
3. As a SOC manager, I want to review a complete transcript of any past agent run so that I can audit agent behavior during incident post-mortems.
4. As a SOC analyst, I want the transcript to distinguish between stdout, stderr, tool calls, tool results, LLM thinking, and agent findings so that I can quickly scan for relevant information.
5. As a SOC analyst, I want run output to continue streaming even if I navigate away and come back so that I don't miss context.

### Agent Lifecycle

6. As a SOC analyst, I want to cancel a running agent immediately so that I can stop a misconfigured agent from taking wrong actions during a live incident.
7. As a SOC manager, I want agents to auto-recover from worker crashes so that alert investigations don't silently stall.
8. As a SOC manager, I want structured error codes on failed runs (not just free-text errors) so that I can build dashboards and alerts on agent failure patterns.
9. As a SOC manager, I want per-agent concurrency enforcement (FIFO queue) so that alert storms don't overload a single agent.
10. As a SOC analyst, I want to see `cancelled` and `timed_out` as distinct run statuses (not just `failed`) so that I can distinguish between agent bugs and infrastructure issues.

### Audit & Compliance

11. As a compliance officer, I want every agent run to produce a tamper-evident log file (NDJSON + SHA256) so that we can prove the integrity of automated investigation records.
12. As a compliance officer, I want structured run events stored in the database so that I can query agent actions across runs for audit reports.
13. As a SOC manager, I want log retention to be configurable so that we can comply with data retention policies.

### Comment-Driven Re-Investigation

14. As a SOC analyst, I want to add a note to an alert and have the assigned agent automatically re-investigate with the new context so that I don't have to manually re-trigger agents.
15. As a SOC analyst, I want the agent to see my comment in its wake context so that it understands what changed and why it was re-triggered.

### External Adapters

16. As a platform engineer, I want to write a custom LLM adapter as a Python package so that I can connect Calseta agents to our internal LLM gateway without forking.
17. As a platform engineer, I want to register external adapters via configuration (not code changes) so that upgrades don't break my custom adapters.
18. As a platform engineer, I want external adapters to participate in the same streaming, session, and cost-tracking infrastructure as built-in adapters so that they are first-class citizens.

### Session & Context Optimization

19. As a SOC manager, I want agents to skip redundant prompt layers on session resume so that we save 5-10K tokens per heartbeat across hundreds of daily runs.
20. As a SOC manager, I want session compaction to actually execute (not just flag) so that long-running multi-day investigations don't hit context limits.
21. As an agent (via Claude Code adapter), I want `CALSETA_*` environment variables injected into my subprocess so that I can call Calseta APIs directly from skills.

### Workspace & Skill Management

22. As a detection engineer, I want the schema to support workspace tracking so that future detection-as-code agents can manage git worktrees.
23. As a platform engineer, I want skill files to be ephemeral per run (created in temp dir, cleaned up after) so that stale skills from previous runs don't contaminate future investigations.
24. As a SOC manager, I want the wake context to include why the agent was triggered and what changed since its last run so that agents make better decisions.

### Dashboard Configurability

25. As a SOC manager, I want to add and remove dashboard cards so that I can build a view focused on the metrics I care about without scrolling past 30+ cards I don't need.
26. As a SOC manager, I want to browse a catalog of available cards organized by category (Alerts, Agents, Workflows, Platform) so that I can discover useful cards quickly.
27. As a platform engineer, I want to add agent health cards (error rates, stall detection, budget burn) to my dashboard without affecting the SOC manager's view.
28. As a SOC manager, I want my dashboard layout to persist across sessions so that I don't have to reconfigure it every time I log in.
29. As a SOC analyst, I want dashboard presets (e.g., "SOC Overview", "Agent Operations", "Minimal") so that I can switch between views without manual card-by-card configuration.

## Implementation Decisions

### Streaming Architecture: SSE over WebSocket

SSE (Server-Sent Events) is chosen over WebSocket because:
- FastAPI has native SSE support via `StreamingResponse` + `asyncio.Queue` — zero additional dependencies
- SSE works through HTTP proxies and load balancers without special configuration (critical for enterprise SOC deployments behind reverse proxies)
- The data flow is unidirectional (server → client) — agents produce output, the frontend consumes it. No bidirectional communication needed.
- HTTP polling fallback is trivial to implement alongside SSE (same data source, different transport)

The streaming pipeline:

```
LLM Adapter (on_log callback)
    │
    ├──→ Run Log Store (NDJSON to disk, append-only)
    │
    ├──→ agent_run_events table (structured events, append-only)
    │
    └──→ In-process asyncio.Queue → SSE endpoint
              │
              └──→ Browser (EventSource API)
                     │
                     └──→ HTTP polling fallback (GET /v1/runs/{uuid}/log)
```

PostgreSQL LISTEN/NOTIFY (already available via procrastinate) bridges the worker→API process boundary: the worker emits events via `NOTIFY`, the API server's SSE handler listens via `LISTEN`. This avoids shared-memory coupling between the API and worker processes.

### Adapter Streaming Interface

Add an `on_log` callback to the adapter execution contract. Every adapter — not just Claude Code — must support streaming output via this callback. The callback receives `(stream: str, chunk: str)` where stream is `"stdout"`, `"stderr"`, `"tool_call"`, `"tool_result"`, `"thinking"`, or `"finding"`.

For API-based adapters (Anthropic, OpenAI), "streaming" means emitting events at each tool loop iteration — one event per LLM response, one per tool call, one per tool result. For subprocess-based adapters (Claude Code), streaming means piping stdout/stderr line by line.

The engine's tool loop becomes the universal event emitter: regardless of adapter type, the engine emits structured events at each step.

### Run Event Schema

New `agent_run_events` table:

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL PK | — |
| heartbeat_run_id | BIGINT FK | Parent run |
| seq | INTEGER | Sequence within run (monotonic) |
| event_type | TEXT | `llm_response`, `tool_call`, `tool_result`, `finding`, `action`, `error`, `status_change`, `budget_check` |
| stream | TEXT | `system`, `stdout`, `stderr`, `assistant`, `tool` |
| level | TEXT | `info`, `warn`, `error` |
| content | TEXT | Human-readable content (truncated for large payloads) |
| payload | JSONB | Full structured data |
| created_at | TIMESTAMPTZ | — |

### NDJSON Log Store

Each run produces `{CALSETA_DATA_DIR}/logs/{agent_uuid}/{run_uuid}.ndjson`. Each line:

```json
{"ts":"2026-04-15T10:30:00.123Z","seq":1,"stream":"assistant","event_type":"llm_response","content":"...","payload":{}}
```

On run completion:
- SHA256 hash computed and stored on HeartbeatRun (`log_sha256`)
- Byte count stored on HeartbeatRun (`log_bytes`)
- Final stdout/stderr excerpt (last 50KB) stored on HeartbeatRun (`stdout_excerpt`, `stderr_excerpt`)

### HeartbeatRun State Machine (6 states)

```
queued ──────────────────→ running
  │                          │
  │ (cancelled before start) ├→ succeeded  (all tools completed, no errors)
  │                          ├→ failed     (LLM error, tool error, or exception)
  ▼                          ├→ timed_out  (supervisor timeout or per-alert budget)
cancelled                    └→ cancelled  (manual cancel via API)
```

New fields on HeartbeatRun:
- `process_pid` (INTEGER, nullable) — OS process ID for subprocess adapters
- `process_started_at` (TIMESTAMPTZ, nullable) — when the subprocess was spawned
- `error_code` (TEXT, nullable) — structured error code
- `log_store` (TEXT, default `"local_file"`) — log storage backend
- `log_ref` (TEXT, nullable) — path to NDJSON file
- `log_sha256` (TEXT, nullable) — integrity hash
- `log_bytes` (BIGINT, nullable) — log file size
- `stdout_excerpt` (TEXT, nullable) — last 50KB of stdout
- `stderr_excerpt` (TEXT, nullable) — last 50KB of stderr

### Error Codes

| Code | Meaning |
|------|---------|
| `process_lost` | Worker crashed, PID no longer alive |
| `timeout` | Exceeded agent.timeout_seconds |
| `budget_exceeded` | Per-alert or monthly budget limit hit |
| `adapter_failed` | LLM adapter threw an unrecoverable error |
| `cancelled` | Manually cancelled via API |

Free-text `error` field preserved for details.

### Cancellation Mechanism

`POST /v1/runs/{uuid}/cancel` → sets `status=cancelled`, sends SIGTERM to `process_pid` (if subprocess adapter), waits 15s grace period, then SIGKILL if still alive. Releases alert assignment, starts next queued run for that agent.

For API-based adapters (Anthropic, OpenAI), cancellation sets a flag that the engine checks between tool loop iterations. The current LLM call completes, but no further tools are dispatched.

### Orphan Detection

The existing supervisor (1-minute periodic task) is extended:
1. For each running HeartbeatRun with a `process_pid`, check if the PID is alive (`os.kill(pid, 0)`)
2. If PID is dead → mark as `failed` with `error_code='process_lost'`
3. If `process_loss_retry_count < 1` → auto-retry (enqueue new run with same context)
4. Release alert assignment

New field on HeartbeatRun: `process_loss_retry_count` (INTEGER, default 0), `retry_of_run_id` (BIGINT FK, nullable).

### Concurrency Queue Enforcement

Before starting a managed agent run in `execute_invocation`, check:
```python
running_count = count assignments with status='in_progress' for this agent
if running_count >= agent.max_concurrent_alerts:
    # Leave in queue — will be picked up when a slot opens
    return
```

On assignment release, the engine checks if there are queued runs for the same agent and starts the next one (FIFO by `created_at`).

### Invocation Sources

New enum on HeartbeatRun replacing the current free-text `source`:

| Source | Description |
|--------|-------------|
| `alert` | New alert triggered the agent via dispatch rules |
| `routine` | Cron-based routine schedule fired |
| `on_demand` | Manual trigger via API or UI |
| `issue` | Issue assigned or commented on |
| `delegation` | Orchestrator delegated a task to this specialist |
| `comment` | Analyst added a comment/note that re-triggered investigation |

### Comment-Driven Wakeups

When a user posts a finding or note on an alert via `POST /v1/alerts/{uuid}/findings` or a new API endpoint `POST /v1/alerts/{uuid}/comments`:
1. Check if there's an active or recent assignment for this alert
2. If yes, enqueue a new heartbeat run with `source='comment'` and the comment text in `context_snapshot.wake_comments`
3. The prompt builder includes new comments in the alert context (Layer 4) with a directive: "New analyst input since your last run — address this first"

### Wake Context Enhancement

Extend `RuntimeContext` with:
- `wake_reason` — why the agent was triggered (maps to invocation source)
- `wake_comments` — new analyst notes since last run (list of `{author, content, posted_at}`)
- `execution_stage` — current investigation phase

The prompt builder renders this as a `<wake_context>` XML block in Layer 4, similar to Paperclip's wake payload but alert-centric:

```markdown
## Calseta Wake Context

- reason: comment
- alert: {uuid} — {title}
- severity: High
- new analyst input: 1 comment since last run
- last run: 2026-04-15T10:30:00Z (succeeded, 3 findings)

### New Analyst Input
1. comment from analyst jorge at 2026-04-15T11:00:00Z
   "The source IP 10.0.0.5 is our VPN egress — re-check the lateral movement hypothesis."
```

### Session Resume Optimization

On session resume (session has existing messages), the prompt builder skips:
- Layer 1 (system prompt + instruction files) — already in context from first run
- Layer 2 (methodology) — already in context
- Layer 3 (KB context) — already in context

Only Layer 4 (fresh alert context with any new data), Layer 5 (session history), and Layer 6 (runtime checkpoint + memory) are sent. Saves 5-10K tokens per heartbeat.

Exception: if KB pages have been updated since the session was last run (`page.updated_at > session.updated_at`), Layer 3 is included with only the updated pages.

### Session Compaction

When `needs_compaction=True` on session resume:
1. Load the full message history from `session_params.messages`
2. Send to a cheap model (Haiku via the instance's configured LLM) with: "Summarize this security investigation so far. Include: alerts investigated, indicators found, enrichment results, findings posted, actions proposed, current status. Max 2000 tokens."
3. Save the summary as `session_handoff_markdown`
4. Clear `messages` from session_params
5. Set `compacted_at` timestamp, clear `needs_compaction`

The prompt builder already handles compacted sessions (Layer 5 uses `session_handoff_markdown` when present).

### External Adapter System

External adapters are Python packages that implement `LLMProviderAdapter`. Registration is via configuration, not code changes.

**Registration**: `CALSETA_EXTERNAL_ADAPTERS` env var or `external_adapters` in settings:
```
CALSETA_EXTERNAL_ADAPTERS=mycompany.llm_gateway:GatewayAdapter,acme.bedrock:BedrockAdapter
```

Format: `module_path:ClassName` — each entry is a `LLMProviderAdapter` subclass. At startup, the factory imports each module and registers the adapter under a provider name derived from the class (or a `provider_name` class attribute).

**Contract**: External adapters must implement:
- `create_message()` — same interface as built-in adapters
- `extract_cost()` — token/cost computation
- `test_environment()` — optional pre-flight check
- Class attribute `provider_name: str` — unique identifier (e.g., `"custom_gateway"`)
- Class attribute `display_name: str` — human-readable name for UI

**What they get for free**: streaming via on_log callback (engine handles it), session persistence, cost tracking, tool dispatching, prompt assembly. External adapters only need to implement the LLM call itself.

**LLMIntegration row**: create an LLMIntegration with `provider="custom_gateway"` and the factory routes to the external adapter. `adapter_config` JSONB on the integration carries provider-specific settings.

### CALSETA_* Environment Variables

For subprocess-based adapters (Claude Code), inject these env vars:

| Variable | Value |
|----------|-------|
| `CALSETA_AGENT_ID` | Agent UUID |
| `CALSETA_AGENT_NAME` | Agent name |
| `CALSETA_RUN_ID` | HeartbeatRun UUID |
| `CALSETA_TASK_KEY` | Task key (e.g., `alert:123`) |
| `CALSETA_WAKE_REASON` | Invocation source |
| `CALSETA_API_URL` | `http://localhost:8000` (or configured) |
| `CALSETA_API_KEY` | Short-lived agent API key |
| `CALSETA_ALERT_UUID` | Alert UUID (if alert-scoped) |
| `CALSETA_WORKSPACE_DIR` | Agent working directory |

### Ephemeral Skill Injection

Switch from persistent write to Paperclip's temp-dir pattern:
1. Create temp dir: `tempfile.mkdtemp(prefix="calseta-skills-")`
2. Write skill files to `{tmpdir}/skills/{slug}/SKILL.md`
3. For Claude Code adapter: pass `--add-dir {tmpdir}` (skills dir is discovered automatically)
4. For API adapters: skill content is already in the system prompt (Layer 1), no file needed
5. Cleanup: `shutil.rmtree(tmpdir)` in `finally` block

### Workspace Schema (Plan Only — No Implementation)

Add `workspace_mode` to AgentRegistration: `none` (default), `git_worktree` (future).

New `agent_workspaces` table (schema only, no service logic):

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL PK | — |
| uuid | UUID | External ID |
| agent_registration_id | BIGINT FK | Agent |
| heartbeat_run_id | BIGINT FK | Run that created it |
| mode | TEXT | `shared`, `isolated`, `operator_branch` |
| strategy_type | TEXT | `git_worktree`, `project_primary` |
| status | TEXT | `active`, `idle`, `archived` |
| cwd | TEXT | Absolute working directory path |
| repo_url | TEXT | Git remote URL |
| base_ref | TEXT | Base branch |
| branch_name | TEXT | Working branch |
| created_at | TIMESTAMPTZ | — |
| last_used_at | TIMESTAMPTZ | — |

This is a schema-only placeholder for the detection-as-code agent use case. No workspace provisioning logic ships in this PRD.

## Reference Implementation: Paperclip Prompts & Context Injection

The Paperclip agent runtime uses a specific prompt assembly pattern that is documented in full at `tmp/paperclip-prompts-and-context-reference.md`. Key patterns adopted or adapted for Calseta:

### Adopted Patterns

1. **Wake payload as markdown** — Calseta renders `<wake_context>` XML (consistent with our existing `<alert_context>`, `<methodology>`, `<memory>` XML blocks) instead of Paperclip's bare markdown, but the content structure is equivalent: reason, alert summary, new input, last run status.

2. **Session resume optimization** — Skip redundant prompt sections on resume. Paperclip skips instructions, bootstrap, and main prompt. Calseta skips Layers 1-3 (system prompt, methodology, KB context).

3. **Ephemeral skill injection** — Temp dir per run, cleanup in finally. Calseta adopts this exactly.

4. **Environment variables** — `CALSETA_*` vars mirror `PAPERCLIP_*` vars. Core set: agent ID, run ID, API URL, API key, task key, wake reason.

5. **Structured run events** — Calseta's `agent_run_events` table mirrors Paperclip's `heartbeat_run_events` (seq, event_type, stream, level, content, payload).

6. **Heartbeat state machine** — 6 states matching Paperclip: queued, running, succeeded, failed, cancelled, timed_out.

### Adapted for SOC

1. **Alert-centric wake payload** — Paperclip's wake is issue-centric (title, status, comments). Calseta's is alert-centric (severity, indicators, enrichment status, detection rule, existing findings).

2. **6-layer prompt vs. 5-section prompt** — Calseta's KB context (Layer 3) and agent memory (Layer 6) have no Paperclip equivalent. These are SOC-specific: KB pages contain IR runbooks, threat intel reports, and organizational context that guide investigation.

3. **Tool tier enforcement** — Paperclip agents can call any tool. Calseta has a tier system (`allowed`, `requires_approval`, `forbidden`) because SOC response actions have different risk profiles.

4. **Evidence chain** — Paperclip's NDJSON logs capture raw stdout. Calseta's run events capture structured tool calls with the full input/output, creating a queryable evidence chain for compliance.

### Not Adopted

1. **Mustache template engine** — Calseta's code-assembled prompts are more type-safe.
2. **Git worktree workspace** — SOC investigation agents don't write code. Schema is planned but not implemented.
3. **In-memory EventEmitter** — PostgreSQL LISTEN/NOTIFY is more robust for SOC's multi-process architecture.

## Testing Strategy

### Unit Tests

- **Run log store**: write events, finalize with SHA256, verify integrity, test rotation
- **Streaming callback**: mock adapter produces events, verify engine emits correct structured events
- **Cancellation logic**: test SIGTERM/SIGKILL sequence, grace period, lock release
- **Orphan detection**: mock dead PIDs, verify auto-retry behavior
- **Concurrency queue**: concurrent checkout attempts, verify FIFO ordering and slot enforcement
- **Session compaction**: mock LLM summarization, verify handoff markdown generation
- **External adapter loading**: mock package imports, verify factory registration
- **Wake context rendering**: verify markdown output for different wake reasons

### Integration Tests

- **End-to-end streaming**: dispatch agent → connect SSE → verify events arrive in real-time → verify NDJSON matches DB events
- **Cancel mid-run**: start long-running agent → cancel → verify assignment released → verify next queued run starts
- **Orphan recovery**: start agent → kill worker PID → wait for supervisor → verify auto-retry
- **Comment wakeup**: post finding on alert → verify new heartbeat enqueued with comment context

### Test Patterns

Follow existing patterns in `tests/integration/agent_control_plane/`:
- Use `freeze_time` for timeout testing
- Mock LLM responses via the adapter layer (not httpx)
- Use real PostgreSQL for queue/session/event persistence

## Out of Scope

- **Workspace provisioning (git worktree, clone)** — Schema planned, implementation deferred to detection-as-code agent PRD
- **External issue tracker sync (Jira/ServiceNow)** — Separate PRD
- **SOAR integration** — Separate PRD
- **Log export API for compliance** — Deferred; logs are on disk and queryable via DB
- **Multi-node streaming** — SSE works within a single API process. Redis pub/sub for multi-node is a future enhancement.
- **Frontend transcript renderer** — UI components are in this PRD but the rich renderer (thinking blocks, diff display, streaming animation) is scoped to basic stdout/tool/finding display. Full renderer is iterative.

## Open Questions

1. **Log retention policy** — How long to keep NDJSON files on disk? Should there be automatic rotation? Propose: configurable via `AGENT_LOG_RETENTION_DAYS` env var, default 90 days, cleanup via periodic task.
2. **Compaction model** — Should compaction always use Haiku, or should it use the agent's configured LLM? Haiku is cheaper but might miss domain-specific nuance.
3. **SSE reconnection** — Should the SSE endpoint support `Last-Event-ID` for reconnection, or is the HTTP polling fallback sufficient?
4. **External adapter versioning** — Should external adapters declare a compatibility version? What happens on Calseta upgrade if the adapter interface changes?

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| SSE connection drops behind corporate proxies | HTTP polling fallback with 2s interval covers this. Both paths read from the same data source. |
| NDJSON logs consume excessive disk space | Configurable retention + periodic cleanup task. Gzip compression for archived logs. |
| External adapters crash the worker | External adapters run in-process but are wrapped in try/except. Adapter errors produce `error_code='adapter_failed'`, never crash the worker. |
| Session compaction loses critical context | Compaction prompt explicitly requests: indicators, findings, actions, current status. Post-compaction, the full NDJSON log is still available for manual review. |
| LISTEN/NOTIFY message loss under load | NDJSON file is the source of truth. SSE is best-effort. The polling fallback reads from the NDJSON file directly. |

## UI/UX Design

### Design System Reference

All new UI follows Calseta's existing design system:
- **Component library**: shadcn/ui + Radix UI primitives + Tailwind CSS v4
- **Typography**: Manrope (headings), IBM Plex Mono (body/code) — monospace-first aesthetic
- **Color palette**: Teal (#4D7D71) = success/active, Amber (#FFBB1A) = warning/in-progress, Red (#EA591B) = error/critical, Dim (#57635F) = muted/inactive
- **Status badges**: `text-{color} bg-{color}/10 border-{color}/30` pattern
- **Detail pages**: `DetailPageLayout` (two-column: main + sticky sidebar at lg breakpoint)
- **Tables**: `ResizableTable` with `ColumnDef[]`, pagination, loading skeletons
- **Forms**: Dialog-based, sections separated by `border-t border-border`
- **Feedback**: Sonner toasts (`toast.success()`, `toast.error()`)
- **Data**: TanStack React Query with `useQuery`/`useMutation`, invalidation chains

### New UI Components

#### 1. Run Transcript Panel (Agent Detail → Heartbeat Runs Tab)

**Layout**: Right-edge sheet (slide-out), consistent with `IndicatorDetailSheet` pattern. Sheet chosen over inline expand for guaranteed vertical space and future extensibility (mid-session chat input at bottom).

**Visual reference**: `tmp/transcript-option-b-cards.html` — approved card-per-type rendering with message input.

**Header**:
- Title: "Run Transcript"
- Three-dot menu (DropdownMenu) with: "Copy run ID", "View raw log", separator, red "Cancel Run" (only when status is `running`)
- Close button (X)
- Meta row: status badge (pulsing amber for running), run UUID (truncated), elapsed time, token count, cost

**Event stream** (card-per-type rendering — each event type gets distinct visual treatment):
- `llm_response` → **Assistant bubble**: teal-tinted background (`rgba(77,125,113,0.06)`), 3px teal left-accent bar, teal icon square, "ASSISTANT" label in Manrope, message in IBM Plex Mono
- `tool_call` + `tool_result` → **Collapsible tool card**: dark surface background (`#0f161d`), amber tool name, inline args preview, chevron toggle to expand/collapse result body
- `finding` → **Finding card**: red-tinted background (`rgba(234,89,27,0.06)`), 3px red left-accent bar, classification badge (e.g., "True Positive" in red), evidence metadata row (confidence, indicators, action)
- `analyst_message` → **Analyst bubble**: blue-tinted background (`rgba(99,139,224,0.06)`), 3px blue left-accent bar (#638BE0), "ANALYST" label with author name, "context injected" badge
- `status_change` → **Inline status**: minimal row with dot, "queued → running" text
- `budget_check` → **Inline budget**: dollar sign, budget text, 3px progress bar
- `error` → Red-tinted block (same pattern as finding but with error icon)

**Live streaming**: pulsing amber dot on "running" badge. SSE status bar at bottom: "SSE connected — streaming live" with green dot.

**Auto-scroll**: locks to bottom while streaming, unlocks on user scroll-up.

**Message input** (pinned at bottom, only visible when run is `running`):
- Auto-expanding textarea: "Drop context for the agent..."
- Teal "Send" button
- Hint: "Injected as analyst context into the live investigation. Enter to send, Shift+Enter for newline."
- Sent messages appear in the transcript as analyst bubbles (blue accent)

Data source: SSE for live runs, `GET /v1/runs/{uuid}/events` for completed runs. Message input not shown for completed runs.

#### 2. Cancel Run (via Dropdown)

Cancel lives in the transcript panel's three-dot dropdown menu — not as a standalone header button. Cleaner header, cancel is still two clicks (open menu → click cancel).

- Red text "Cancel Run" item in dropdown, separated by divider
- Confirmation dialog (ConfirmDialog pattern): "Cancel this agent run? The agent will be stopped and the alert assignment released."
- Calls `POST /v1/runs/{uuid}/cancel`
- Optimistic UI: immediately shows "Cancelling..." badge, transitions to "Cancelled" on confirmation
- Also available in the heartbeat runs table row dropdown (same pattern as existing action menus)

#### 3. Enhanced Status Badges

Extend the existing badge system with two new states:
- `cancelled` → Dim (#57635F) background, "Cancelled" text
- `timed_out` → Amber (#FFBB1A) background, "Timed Out" text

These are consistent with the existing badge convention (4 alert statuses already use this palette).

#### 4. Alert Comment Input (Alert Detail → Activity Tab)

**Visual reference**: `tmp/q1-alert-comment-option-a.html` — approved two-button layout.

New input at the bottom of the activity timeline:
- Container: `--surface-2` background, rounded border, 16px padding
- Agent indicator: pulsing teal dot + "lead-investigator recently investigated this alert" (only shown when an agent has a recent assignment)
- Textarea: "Add context for the investigating agent..."
- Two buttons, right-aligned:
  - "Post Only" (outline button) — posts the note without triggering
  - "Post & Re-trigger" (teal primary button, play icon) — posts the note AND enqueues a new heartbeat
- Hint text below: `"Post & Re-trigger" posts your note and re-triggers the agent to incorporate it.`
- "Post & Re-trigger" disabled with tooltip when no agent has recently investigated this alert

#### 5. Agent Adapter Configuration (Agent Detail → Configuration Tab)

**Visual reference**: `tmp/q2-adapter-badge-option-b.html` — approved badge + metadata section.

For built-in adapters: standard config rows with a teal "Built-in" badge next to the provider name.

For external/custom adapters:
- Purple "Custom" badge next to the provider name in the config section
- Distinct adapter metadata section below the main config, with purple tint (`rgba(155,127,212,0.08)` background):
  - Header: gear icon + "EXTERNAL ADAPTER" label
  - Rows: Package (module path), Class (class name), Provider Name, Streaming support, Session Resume support
  - Each capability shows teal "Supported" or dim "Not supported"

#### 6. Completed Run Summary Bar

**Visual reference**: `tmp/q3-summary-bar-option-a.html` — approved compact bar.

When viewing a completed run (succeeded/failed/cancelled/timed_out), the message input area is replaced by a compact single-row summary bar:
- Background: `--surface-2`
- Horizontal layout with vertical dividers between stats
- Stats shown: Duration, Tokens, Cost, Findings (red if > 0), Tools Called, Result (teal for escalated/closed, red for failed)
- Each stat: 9px uppercase label + 13px bold value
- Same height as the message input was (~56px) to maintain consistent sheet proportions

#### 7. Configurable Dashboard Cards

The existing dashboard has 32 fixed cards. With agent runtime data adding more, the dashboard needs card management.

**Add Card flow:**
- "+" button in the top-right of the dashboard (next to existing reset layout button)
- Opens a **card catalog sheet** (right-edge slide-out, same pattern as transcript panel)
- Cards organized by category tabs: **All**, **Alerts**, **Agents**, **Workflows**, **Platform**, **Costs**
- Each card in the catalog shows: title, one-line description, size preview badge (small/wide/large)
- Search input at top of catalog for type-ahead filtering across all categories
- Click a card → it's added to the dashboard grid at the next available position
- Cards already on the dashboard show a checkmark and "Added" state (dimmed, not clickable)

**Remove Card flow:**
- Hover any dashboard card → "X" button appears in top-right corner (same position as existing drag handle, replaces it on hover)
- Click X → card removed immediately (no confirmation — undo via "+" to re-add)
- Minimum 1 card must remain on the dashboard

**Presets:**
- Dropdown next to the "+" button: "SOC Overview" (default — alerts, workflows, key metrics), "Agent Operations" (agent fleet, costs, runs, errors), "Minimal" (5 core metrics only)
- Selecting a preset replaces all current cards with the preset's card set
- Confirmation dialog: "Switch to Agent Operations preset? Your current layout will be replaced."
- "Save as preset" option for custom layouts (stored in localStorage, named by user)

**Layout persistence:**
- Card selection and positions saved to localStorage keyed by user (API key prefix)
- On page load: if saved layout exists, restore it. Otherwise, use "SOC Overview" preset as default.
- Reset button clears saved layout and restores default preset

**Card catalog** (initial set — more added as agent data surfaces):

| Category | Card Title | Type | Description |
|----------|-----------|------|-------------|
| Agents | Agent Fleet Status | StatCard | Active/paused/terminated count |
| Agents | Agent Success Rate | KpiCard | % of runs succeeded (7d rolling) |
| Agents | Spend MTD | KpiCard | Monthly agent LLM spend |
| Agents | Last Heartbeat | StatCard | Most recent agent heartbeat timestamp |
| Agents | Runs by Status | ChartCard | Bar chart: succeeded/failed/timed_out/cancelled (7d) |
| Agents | Active Investigations | StatCard | Currently running agent assignments |
| Agents | Stall Detections | KpiCard | Stalls detected by supervisor (7d) |
| Agents | Orphan Recoveries | KpiCard | Process-lost auto-retries (7d) |
| Costs | Cost by Agent | ChartCard | Bar chart: spend per agent (30d) |
| Costs | Cost by Model | ChartCard | Bar chart: spend per LLM model (30d) |
| Costs | Token Usage | KpiCard | Total input/output tokens (30d) |
| Platform | Queue Depth | StatCard | Pending tasks by queue |
| Platform | Supervisor Health | KpiCard | Last run, checks performed, errors |
| Platform | Error Rate | KpiCard | Agent error rate (7d) with trend |
| Platform | Avg Investigation Time | KpiCard | Mean time from checkout to release |

## Project Management

### Overview

| Chunk | Wave | Status | Dependencies |
|-------|------|--------|-------------|
| Z1: Design system refinement | 0 | pending | — |
| A1: Streaming adapter interface | 1 | **complete** | — |
| A2: Run event log table + NDJSON store | 1 | **complete** | — |
| A3: HeartbeatRun state machine expansion | 1 | **complete** | — |
| A4: External adapter loading system | 1 | **complete** | — |
| B1: Engine streaming integration | 2 | **complete** | A1, A2, A3 |
| B2: SSE endpoint + HTTP polling | 2 | **complete** | A2 |
| B3: Cancellation mechanism | 2 | **complete** | A3 |
| B4: Orphan detection + auto-retry | 2 | **complete** | A3 |
| B5: Concurrency queue enforcement | 2 | **complete** | A3 |
| C1: Comment-driven wakeups | 3 | **complete** | A3 |
| C2: Wake context enhancement | 3 | **complete** | A3 |
| C3: Session resume optimization | 3 | **complete** | — |
| C4: Session compaction handler | 3 | **complete** | C3 |
| C5: CALSETA_* environment variables | 3 | **complete** | — |
| C6: Ephemeral skill injection | 3 | **complete** | — |
| C7: Persistent data volume | 3 | **complete** | — |
| D1: Run transcript panel (UI) | 4 | pending | B1, B2 |
| D2: Cancel button + status badges (UI) | 4 | pending | B3 |
| D3: Alert comment re-trigger (UI) | 4 | pending | C1 |
| D4: Workspace schema (plan only) | 4 | pending | — |
| D5: Configurable dashboard cards (UI) | 4 | pending | — |

### Wave 1 — Foundation (Schema + Interfaces)

All chunks in Wave 1 are independent — they define schemas, interfaces, and infrastructure that Wave 2 builds on. No file contention between chunks.

#### Chunk A1: Streaming Adapter Interface

- **What**: Add `on_log` callback to the LLM adapter contract. Update ALL adapters (Anthropic, OpenAI, Claude Code, Ollama) to call the callback at appropriate points. For API adapters, emit events per tool-loop iteration. For Claude Code, stream stdout/stderr line by line.
- **Why this wave**: Defines the interface that the engine (Wave 2) will consume
- **Modules touched**: `app/integrations/llm/base.py`, `app/integrations/llm/anthropic_adapter.py`, `app/integrations/llm/openai_adapter.py`, `app/integrations/llm/claude_code_adapter.py`, `app/integrations/llm/factory.py`
- **Depends on**: None
- **Produces**: `on_log` callback type signature, updated adapter implementations
- **Acceptance criteria**:
  - [ ] `LLMProviderAdapter.create_message()` accepts optional `on_log: Callable[[str, str], Awaitable[None]]` parameter
  - [ ] Claude Code adapter streams stdout/stderr via `proc.stdout.readline()` instead of `proc.communicate()`
  - [ ] Anthropic adapter calls `on_log("assistant", content)` after each LLM response
  - [ ] OpenAI adapter calls `on_log("assistant", content)` after each LLM response
  - [ ] All adapters continue to work correctly when `on_log` is None (backward compatible)
  - [ ] Existing adapter tests pass
- **Verification**: `pytest tests/ -k "adapter" --no-header -q`

**Implementation notes (A1):**
- `OnLogCallback = Callable[[str, str], Awaitable[None]]` type alias added to `app/integrations/llm/base.py`
- `on_log` parameter added to `create_message()` on all adapters (Anthropic, OpenAI, Claude Code) — ignored when `None`
- Claude Code adapter (`app/integrations/llm/claude_code_adapter.py`) rewritten: `proc.communicate()` replaced with line-by-line `proc.stdout.readline()` loop; new static `_classify_line()` method parses NDJSON events into `(stream, chunk)` tuples
- Anthropic adapter emits `assistant` + `tool_call` + `thinking` events; OpenAI adapter emits `assistant` + `tool_call`
- `provider_name` and `display_name` class attributes added to `LLMProviderAdapter` base
- `env: dict[str, str] | None = None` parameter also added (C5) — passed through to subprocess in Claude Code adapter
- Stream names: `stdout`, `stderr`, `assistant`, `tool_call`, `tool_result`, `thinking`, `finding`, `budget_check`

#### Chunk A2: Run Event Log Table + NDJSON Store

- **What**: Create `agent_run_events` table (migration), `RunEvent` ORM model, and `RunLogStore` service (NDJSON file writer with SHA256 finalization). No integration with the engine yet — just the storage layer.
- **Why this wave**: Storage infrastructure that Wave 2 writes to
- **Modules touched**: New migration, new `app/db/models/agent_run_event.py`, new `app/services/run_log_store.py`, `app/db/models/__init__.py` (import)
- **Depends on**: None
- **Produces**: `RunLogStore` with `open(run_uuid)`, `append(event)`, `finalize() → (sha256, bytes)` interface. `AgentRunEvent` model.
- **Acceptance criteria**:
  - [ ] Migration creates `agent_run_events` table with columns: id, heartbeat_run_id, seq, event_type, stream, level, content (TEXT), payload (JSONB), created_at
  - [ ] `RunLogStore.open(agent_uuid, run_uuid)` creates directory and returns a handle
  - [ ] `RunLogStore.append(handle, event)` writes NDJSON line
  - [ ] `RunLogStore.finalize(handle)` computes SHA256, returns `(hash, byte_count)`
  - [ ] `RunLogStore.read(agent_uuid, run_uuid, after_seq=0)` returns events from NDJSON file
  - [ ] Unit tests for write + read + finalize + integrity verification
- **Verification**: `pytest tests/ -k "run_log" --no-header -q`

**Implementation notes (A2):**
- Migration: `alembic/versions/0014_agent_run_events.py` — creates `agent_run_events` table (bigserial PK, FK to heartbeat_runs, seq, event_type, stream, level, content TEXT, payload JSONB, created_at; composite index on `(heartbeat_run_id, seq)`)
- ORM model: `app/db/models/agent_run_event.py` — `AgentRunEvent`, append-only (no UUID/TimestampMixin)
- NDJSON store: `app/services/run_log_store.py` — `RunLogStore` with `RunLogHandle` dataclass; methods: `open(agent_uuid, run_uuid)`, `append(handle, event_data)` (auto-seq + UTC timestamp), `finalize(handle) → (sha256, byte_count)`, `read(agent_uuid, run_uuid, after_seq)`, `close(handle)`
- File path pattern: `{CALSETA_DATA_DIR}/logs/{agent_uuid}/{run_uuid}.ndjson`
- Repository: `app/repositories/run_event_repository.py` — `list_for_run(heartbeat_run_id, after_seq, limit)`, `create_event()`
- Tests: `tests/unit/test_run_log_store.py` (7 tests)

#### Chunk A3: HeartbeatRun State Machine Expansion

- **What**: Add new columns to HeartbeatRun model (`process_pid`, `process_started_at`, `error_code`, `log_store`, `log_ref`, `log_sha256`, `log_bytes`, `stdout_excerpt`, `stderr_excerpt`, `process_loss_retry_count`, `retry_of_run_id`, `invocation_source`). Add `cancelled` and `timed_out` to status values. Create migration. Update HeartbeatRunRepository with new query methods. Define error code constants.
- **Why this wave**: Schema changes must land before any service logic uses them
- **Modules touched**: `app/db/models/heartbeat_run.py`, `app/repositories/heartbeat_run_repository.py`, new migration, `app/schemas/heartbeat_runs.py` (response schema)
- **Depends on**: None
- **Produces**: Extended HeartbeatRun model, `InvocationSource` enum, `RunErrorCode` enum, repository methods for status transitions
- **Acceptance criteria**:
  - [ ] Migration adds all new columns with appropriate defaults and nullability
  - [ ] HeartbeatRun model has all new fields with correct types
  - [ ] `InvocationSource` enum: `alert`, `routine`, `on_demand`, `issue`, `delegation`, `comment`
  - [ ] `RunErrorCode` enum: `process_lost`, `timeout`, `budget_exceeded`, `adapter_failed`, `cancelled`
  - [ ] Repository has `cancel(run)`, `mark_timed_out(run)`, `mark_orphaned(run)` transition methods
  - [ ] Response schema updated to include new fields
  - [ ] Migration is reversible
- **Verification**: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`

**Implementation notes (A3):**
- Migration: `alembic/versions/0015_heartbeat_run_hardening.py` — adds 12 columns to `heartbeat_runs` + self-FK `retry_of_run_id`
- Columns added to `app/db/models/heartbeat_run.py`: `process_pid`, `process_started_at`, `error_code`, `log_store` (default `"local_file"`), `log_ref`, `log_sha256`, `log_bytes`, `stdout_excerpt`, `stderr_excerpt`, `process_loss_retry_count` (default 0), `retry_of_run_id` (self-FK), `invocation_source`
- Enums: `app/schemas/run_enums.py` — `RunStatus` (6 values: queued, running, succeeded, failed, cancelled, timed_out), `InvocationSource` (6 values), `RunErrorCode` (5 values) as StrEnums
- Repository: `app/repositories/heartbeat_run_repository.py` — extended `_UPDATABLE_FIELDS` with all new columns; added `cancel()`, `mark_timed_out()`, `mark_orphaned()`, `list_running_with_pid()`
- Schema: `app/schemas/heartbeat.py` — 7 new fields added to `HeartbeatRunResponse`

#### Chunk A4: External Adapter Loading System

- **What**: Build the external adapter registration and loading system. Parse `CALSETA_EXTERNAL_ADAPTERS` env var, import adapter classes at startup, register in the factory. Add `provider_name` and `display_name` class attributes to `LLMProviderAdapter` base. Update factory to route to external adapters.
- **Why this wave**: Independent of other chunks, defines a new extension point
- **Modules touched**: `app/integrations/llm/base.py` (class attributes), `app/integrations/llm/factory.py` (registry + loading), `app/config.py` (new setting), new `app/integrations/llm/adapter_registry.py`
- **Depends on**: None
- **Produces**: Working external adapter loading, factory routing for custom providers
- **Acceptance criteria**:
  - [ ] `LLMProviderAdapter` has optional class attributes `provider_name: str` and `display_name: str`
  - [ ] `CALSETA_EXTERNAL_ADAPTERS` env var parsed as comma-separated `module:ClassName` entries
  - [ ] External adapters imported and registered at startup (during app factory)
  - [ ] `get_adapter()` routes to external adapters when `integration.provider` matches `provider_name`
  - [ ] Graceful failure: if an external adapter fails to import, log error and continue (don't crash startup)
  - [ ] `GET /v1/llm-integrations/providers` returns both built-in and external providers
  - [ ] Unit test: mock external adapter package, verify registration and routing
- **Verification**: `pytest tests/ -k "external_adapter or adapter_registry" --no-header -q`

**Implementation notes (A4):**
- Registry: `app/integrations/llm/adapter_registry.py` — global `_external_adapters` dict; functions: `load_external_adapters()`, `get_external_adapter(provider_name)`, `list_external_providers()`, `clear_registry()`
- Config: `app/config.py` — `CALSETA_EXTERNAL_ADAPTERS: str = ""` (comma-separated `module:ClassName`)
- Factory: `app/integrations/llm/factory.py` — added external adapter fallback after built-in provider checks
- Startup: `app/main.py` — `load_external_adapters()` called in `_on_startup()`
- API: `app/api/v1/llm_integrations.py` — `GET /v1/llm-integrations/providers` endpoint returns both built-in and external providers (placed before `/{uuid}` routes to avoid path conflict)
- Graceful failure: import errors logged and swallowed, startup continues
- Tests: `tests/unit/test_adapter_registry.py` (9 tests)

### Wave 2 — Core Mechanics

Depends on Wave 1 outputs. Some chunks within Wave 2 are independent of each other.

#### Chunk B1: Engine Streaming Integration

- **What**: Wire the streaming adapter interface (A1) into the engine's tool loop. The engine becomes the universal event emitter: on each LLM response, tool call, tool result, finding, and budget check, it calls `on_log` AND writes to the run event log (A2) AND writes to the NDJSON store (A2). Update HeartbeatRun with log metadata on completion (A3).
- **Why this wave**: Needs adapter interface (A1), storage (A2), and schema (A3)
- **Modules touched**: `app/runtime/engine.py`, `app/queue/registry.py` (pass log store to engine)
- **Depends on**: A1, A2, A3
- **Produces**: Full streaming pipeline from adapter → engine → storage
- **Acceptance criteria**:
  - [ ] Engine creates RunLogStore handle at start of run, finalizes on completion
  - [ ] Every tool loop iteration emits events: `llm_response`, `tool_call`, `tool_result`
  - [ ] Findings and action proposals emit `finding` and `action` events
  - [ ] Budget checks emit `budget_check` events
  - [ ] Events written to both `agent_run_events` table and NDJSON file
  - [ ] HeartbeatRun updated with `log_ref`, `log_sha256`, `log_bytes`, `stdout_excerpt` on completion
  - [ ] Streaming is non-blocking — a slow NDJSON write doesn't delay the tool loop
  - [ ] Engine works correctly when streaming is disabled (no on_log, no log store)
- **Verification**: `pytest tests/integration/agent_control_plane/ -k "streaming or run_event" --no-header -q`

**Implementation notes (B1):**
- `app/runtime/engine.py` `run()` method: opens `RunLogStore` handle at start using `agent.uuid` + `context.run_uuid`; defines `_on_log` closure that writes to NDJSON file + DB (`RunEventRepository.create_event`) + NOTIFY; passes `on_log` through `_run_tool_loop` to `adapter.create_message()`
- Events emitted: `tool_call`, `tool_result`, `finding`, `budget_check`, `llm_response` (from `assistant` stream)
- Log finalization: SHA256 + byte count written to HeartbeatRun (`log_ref`, `log_sha256`, `log_bytes`) on completion
- Cancellation flag cleared on completion via `clear_cancellation()`
- All event emission wrapped in `contextlib.suppress(Exception)` — non-blocking, never fails the run
- `app/runtime/models.py` — `run_uuid: UUID | None = None` added to `RuntimeContext`
- `app/queue/registry.py` — loads HeartbeatRun to pass `run.uuid` into `RuntimeContext`
- Tests: `tests/unit/test_engine_streaming.py` (6 tests)

#### Chunk B2: SSE Endpoint + HTTP Polling

- **What**: Create SSE endpoint `GET /v1/runs/{uuid}/stream` and polling endpoint `GET /v1/runs/{uuid}/events`. The SSE endpoint uses PostgreSQL LISTEN/NOTIFY to receive events from the worker process and streams them to the client. The polling endpoint reads from the `agent_run_events` table with `after_seq` pagination.
- **Why this wave**: Needs run events in DB (A2) to read from
- **Modules touched**: New `app/api/v1/runs.py`, `app/api/v1/router.py` (include new router), new `app/services/run_event_stream.py` (LISTEN/NOTIFY handler)
- **Depends on**: A2
- **Produces**: SSE and HTTP endpoints for run event consumption
- **Acceptance criteria**:
  - [ ] `GET /v1/runs/{uuid}/stream` returns `text/event-stream` content type
  - [ ] SSE events are formatted as `data: {json}\n\n` with `id: {seq}`
  - [ ] SSE endpoint supports `Last-Event-ID` header for reconnection
  - [ ] `GET /v1/runs/{uuid}/events?after_seq=0&limit=100` returns paginated events
  - [ ] Worker process emits `NOTIFY calseta_run_events, '{run_id}:{seq}'` after each event insert
  - [ ] SSE handler `LISTEN`s on `calseta_run_events` channel, filters by run_id
  - [ ] SSE connection closes automatically when run reaches terminal state
  - [ ] Auth required (same scopes as agent endpoints)
- **Verification**: `curl -N -H "Authorization: Bearer $KEY" http://localhost:8000/v1/runs/$UUID/stream`

**Implementation notes (B2):**
- `app/api/v1/runs.py` — three endpoints on `APIRouter(prefix="/runs")`:
  - `GET /{run_uuid}/events` — HTTP polling with `after_seq` + `limit` query params, returns `DataResponse[list[dict]]`
  - `GET /{run_uuid}/stream` — SSE; replays stored events for terminal runs, uses LISTEN/NOTIFY for active runs
  - `POST /{run_uuid}/cancel` — wired to `cancel_run()` service; returns 409 for terminal runs
- `app/services/run_event_stream.py` — `listen_for_run_events(database_url, run_id)` async generator (asyncpg LISTEN on `calseta_run_events` channel); `notify_run_event(db, run_id, seq, event_data)` sends pg_notify
- `app/api/v1/router.py` — `runs.router` registered
- SSE format: `id: {seq}\ndata: {json}\n\n`; terminal runs get full replay then close

#### Chunk B3: Cancellation Mechanism

- **What**: Implement `POST /v1/runs/{uuid}/cancel`. For subprocess adapters: send SIGTERM, wait 15s, SIGKILL. For API adapters: set a cancellation flag checked between tool loop iterations. Release alert assignment, mark run as `cancelled`, start next queued run.
- **Why this wave**: Needs HeartbeatRun schema (A3) for `process_pid` and `cancelled` status
- **Modules touched**: New `app/services/run_cancellation.py`, `app/api/v1/runs.py` (add cancel route), `app/runtime/engine.py` (check cancellation flag between iterations)
- **Depends on**: A3
- **Produces**: Working cancellation for both subprocess and API adapters
- **Acceptance criteria**:
  - [ ] `POST /v1/runs/{uuid}/cancel` returns 200 with updated run status
  - [ ] Returns 409 if run is already in terminal state
  - [ ] For subprocess runs: SIGTERM sent, 15s grace, then SIGKILL
  - [ ] For API runs: cancellation flag checked between tool loop iterations
  - [ ] Alert assignment released on cancel
  - [ ] Next queued run for the same agent started after cancel
  - [ ] Activity event emitted: `heartbeat.cancelled`
  - [ ] Cancelled run still has its NDJSON log finalized
- **Verification**: `pytest tests/ -k "cancel" --no-header -q`

**Implementation notes (B3):**
- `app/services/run_cancellation.py` — in-process `_cancellation_flags: dict[int, bool]` for API adapters; functions: `request_cancellation(run_id)`, `is_cancelled(run_id)`, `clear_cancellation(run_id)`, `cancel_run(run, db)` (orchestrates: kill subprocess OR set flag, mark cancelled, release assignment, emit activity event), `_kill_subprocess(pid)` (SIGTERM → 15s asyncio.sleep → SIGKILL)
- Engine integration: cancellation check at top of `_run_tool_loop` for-loop — `if is_cancelled(context.heartbeat_run_id): return` with partial result
- Tests: `tests/unit/test_run_cancellation.py` (13 tests)

#### Chunk B4: Orphan Detection + Auto-Retry

- **What**: Extend the supervisor to check PID health for running HeartbeatRuns. Dead PID → mark failed with `error_code='process_lost'`, auto-retry once (enqueue new run with same context). Track retry count.
- **Why this wave**: Needs HeartbeatRun schema (A3) for `process_pid`, `process_loss_retry_count`, `retry_of_run_id`
- **Modules touched**: `app/runtime/supervisor.py` (new `_check_orphans()` method)
- **Depends on**: A3
- **Produces**: Automatic recovery from worker crashes
- **Acceptance criteria**:
  - [ ] Supervisor checks `os.kill(pid, 0)` for all running HeartbeatRuns with non-null `process_pid`
  - [ ] Dead PID → `status='failed'`, `error_code='process_lost'`
  - [ ] If `process_loss_retry_count < 1`: new HeartbeatRun enqueued with same context, `retry_of_run_id` set
  - [ ] If `process_loss_retry_count >= 1`: no retry, alert assignment released
  - [ ] Activity event emitted: `heartbeat.process_lost`
  - [ ] Existing supervisor tests still pass
- **Verification**: `pytest tests/ -k "supervisor or orphan" --no-header -q`

**Implementation notes (B4):**
- `app/runtime/supervisor.py` — added `_check_orphans()` (called before assignment checks in `supervise()`); uses `os.kill(pid, 0)` — `ProcessLookupError` = dead, `PermissionError` = alive
- Auto-retry: if `process_loss_retry_count < 1`, creates new HeartbeatRun with same `context_snapshot`, incremented `process_loss_retry_count`, `retry_of_run_id` set to original; enqueues via queue backend
- Added `_log_orphan_event()` and `_retry_orphaned_run()` helper methods
- Tests: `tests/unit/test_orphan_detection.py` (6 tests)

#### Chunk B5: Concurrency Queue Enforcement

- **What**: Enforce `max_concurrent_alerts` as a FIFO queue. Before starting a run, check running assignment count. If at limit, leave in queue. On assignment release, check for and start next queued run.
- **Why this wave**: Needs HeartbeatRun schema (A3) for proper status tracking
- **Modules touched**: `app/queue/handlers/execute_invocation.py` (pre-start check), `app/runtime/engine.py` (`_release_assignment` triggers next-run start), `app/services/agent_dispatch.py`
- **Depends on**: A3
- **Produces**: FIFO concurrency enforcement per agent
- **Acceptance criteria**:
  - [ ] Agent with `max_concurrent_alerts=1` and 1 running assignment → new run stays queued
  - [ ] When running assignment completes → oldest queued run starts automatically
  - [ ] FIFO ordering: runs started in `created_at` ASC order
  - [ ] `max_concurrent_alerts=0` means unlimited (no enforcement)
  - [ ] Concurrent checkout attempts for the same agent are serialized
- **Verification**: `pytest tests/ -k "concurrency or fifo" --no-header -q`

**Implementation notes (B5):**
- `app/services/concurrency_guard.py` — `can_start_run(agent_id, max_concurrent, db)` counts `in_progress` assignments vs limit (0 = unlimited); `start_next_queued_run(agent_id, db)` finds oldest queued HeartbeatRun by `created_at ASC` and enqueues `run_managed_agent_task`
- Tests: `tests/unit/test_concurrency_guard.py` (7 tests)

### Wave 3 — Context & Session Intelligence

Chunks in Wave 3 are mostly independent of each other. They enhance the prompt assembly and session management without touching streaming or lifecycle code.

#### Chunk C1: Comment-Driven Wakeups

- **What**: When a user posts a note on an alert (new endpoint `POST /v1/alerts/{uuid}/notes`), check for active/recent agent assignment. If found, enqueue a new heartbeat run with `invocation_source='comment'` and the note content in `context_snapshot`.
- **Why this wave**: Needs HeartbeatRun schema (A3) for `invocation_source`
- **Modules touched**: New `app/api/v1/alert_notes.py` (or extend alerts.py), `app/services/alert_service.py`, `app/services/agent_dispatch.py`
- **Depends on**: A3
- **Produces**: Analyst-to-agent communication channel
- **Acceptance criteria**:
  - [ ] `POST /v1/alerts/{uuid}/notes` accepts `{ "content": "...", "trigger_agent": true }`
  - [ ] When `trigger_agent=true` and an agent has an active/recent assignment (last 1 hour), a new heartbeat is enqueued
  - [ ] HeartbeatRun has `invocation_source='comment'` and `context_snapshot.wake_comments` populated
  - [ ] When `trigger_agent=false`, note is stored but no agent triggered
  - [ ] Activity event emitted: `alert.note_added` with actor info
  - [ ] Rate limiting: max 1 re-trigger per alert per 5 minutes
- **Verification**: `pytest tests/ -k "comment_wakeup or alert_note" --no-header -q`

**Implementation notes (C1):**
- `app/schemas/activity_events.py` — added `ALERT_NOTE_ADDED = "alert_note_added"` to `ActivityEventType` (now 28 values)
- `app/services/alert_note_service.py` (new) — `AlertNoteService(db)` with `add_note(alert_id, content, trigger_agent, actor_type, actor_key_prefix, queue)`: stores note as `alert_note_added` activity event; if `trigger_agent=True`, checks rate limit (5-min cooldown via recent activity query), finds active or recent assignment (within 1 hour), creates HeartbeatRun with `invocation_source='comment'` + `context_snapshot.wake_comments`, enqueues `run_managed_agent_task`
- `app/api/v1/alerts.py` — `POST /{alert_uuid}/notes` endpoint; request body: `AlertNoteCreate(content: str, trigger_agent: bool = False)`; response: `_AlertNoteResponse(note_id, agent_triggered)`; 201 Created; `_Write` auth scope
- Notes stored as activity events — no new DB columns or tables needed
- Tests: `tests/unit/test_alert_note_service.py` (10 tests)

#### Chunk C2: Wake Context Enhancement

- **What**: Extend `RuntimeContext` with `wake_reason`, `wake_comments`, and `execution_stage`. Update the prompt builder to render a `<wake_context>` XML block in Layer 4 when wake context is present. Include previous run summary when re-triggered.
- **Why this wave**: Enhances prompt assembly, depends on A3 for invocation_source
- **Modules touched**: `app/runtime/models.py` (RuntimeContext), `app/runtime/prompt_builder.py` (Layer 4)
- **Depends on**: A3
- **Produces**: Rich wake context in agent prompts
- **Acceptance criteria**:
  - [ ] `RuntimeContext` has `wake_reason: str | None`, `wake_comments: list[dict] | None`
  - [ ] Prompt builder renders `<wake_context>` XML block when `wake_reason` is set
  - [ ] Wake context includes: reason, alert summary, new analyst input with timestamps, last run summary
  - [ ] For `wake_reason='comment'`, wake context includes directive: "New analyst input — address this first"
  - [ ] Token estimate includes wake context in layer_tokens
- **Verification**: `pytest tests/ -k "wake_context or prompt_builder" --no-header -q`

**Implementation notes (C2):**
- `app/runtime/models.py` — `RuntimeContext` extended with `wake_reason: str | None = None`, `wake_comments: list[dict] | None = None`, `execution_stage: str | None = None`
- `app/runtime/prompt_builder.py` — new `_build_wake_context(context)` method returns `<wake_context reason="...">` XML block with `<directive>` (reason-specific: "comment" → "New analyst input — address this first", "retry" → "review earlier findings", other → generic) and `<comments>` block with author/timestamp/content per entry; all values XML-escaped
- Wake context prepended to Layer 4 alert context in `_build_layer4_alert_context()`; for non-alert tasks, wake context returned alone
- Token accounting: `layer_tokens["wake_context"]` included when wake context is present
- Tests: `tests/unit/test_wake_context.py` (16 tests)

#### Chunk C3: Session Resume Optimization

- **What**: When resuming a session (session has existing messages), skip Layers 1-3 of the prompt. Only send Layer 4 (fresh alert context), Layer 5 (session history), and Layer 6 (runtime checkpoint). Exception: include Layer 3 KB pages that were updated since the session's last run.
- **Why this wave**: Independent optimization, no cross-chunk dependencies
- **Modules touched**: `app/runtime/prompt_builder.py` (build method, add `is_resume` flag)
- **Depends on**: None
- **Produces**: 5-10K token savings per resumed heartbeat
- **Acceptance criteria**:
  - [ ] On resume, system_prompt contains only Layer 6 (checkpoint + memory)
  - [ ] Layer 1 (system prompt, instructions), Layer 2 (methodology) are skipped
  - [ ] Layer 3 (KB) is skipped unless pages updated since `session.updated_at`
  - [ ] Fresh sessions still get all 6 layers
  - [ ] `layer_tokens` dict accurately reflects which layers were included
  - [ ] Token savings measurable: log the delta in structlog
- **Verification**: `pytest tests/ -k "session_resume or prompt_builder" --no-header -q`

**Implementation notes (C3):**
- `app/runtime/prompt_builder.py` `build()` — detects resume via `session.session_params` having `messages` or `session_handoff_markdown`; on resume: `layer1=""`, `layer2=""`, Layer 3 KB called with `updated_since=session.updated_at` (only includes pages updated after that timestamp); Layer 6 always included
- `_build_layer3_kb()` extended with `updated_since: datetime | None` parameter — filters pages where `updated_at > cutoff` (timezone-aware comparison)
- Token savings logged via `structlog.info("prompt_builder.resume_token_savings", saved_tokens=N)` on resume
- `layer_tokens` dict accurately reflects 0/minimal values for skipped layers
- Tests: `tests/unit/test_session_resume.py` (9 tests)

#### Chunk C4: Session Compaction Handler

- **What**: Implement actual compaction when `needs_compaction=True`. On session resume, if flagged: send message history to a cheap LLM (Haiku or agent's configured model) for summarization, save as `session_handoff_markdown`, clear `messages`, reset flag.
- **Why this wave**: Depends on C3 (resume optimization) for the session flow
- **Modules touched**: `app/runtime/engine.py` (compaction step before prompt build), new `app/services/session_compaction.py`
- **Depends on**: C3
- **Produces**: Working compaction for long-running investigations
- **Acceptance criteria**:
  - [ ] When `session.session_params.needs_compaction=True`, compaction runs before prompt assembly
  - [ ] Compaction sends full message history to LLM with SOC-specific summarization prompt
  - [ ] Summary saved as `session_handoff_markdown` (max 2000 tokens)
  - [ ] `messages` cleared from session_params after compaction
  - [ ] `compacted_at` timestamp set, `needs_compaction` cleared
  - [ ] If compaction LLM call fails, proceed with full messages (don't block the run)
  - [ ] Cost of compaction LLM call recorded as a cost event
- **Verification**: `pytest tests/ -k "compaction" --no-header -q`

**Implementation notes (C4):**
- `app/services/session_compaction.py` (new) — `compact_session(session, adapter, max_tokens=2048)` sends message history to LLM with SOC-specific summarization prompt; returns `{session_params, cost, compacted}`; summary truncated to 8000 chars (~2000 tokens); updates `session_handoff_markdown`, clears `messages`, sets `compacted_at` ISO timestamp, resets `needs_compaction=False`
- Helper: `_serialize_messages_for_summary()` converts message list to readable text (handles text, tool_use, tool_result blocks with truncation); `_extract_text()` handles both string and content-block response formats
- Engine integration: `app/runtime/engine.py` `_maybe_compact_session()` method called before prompt build; if `needs_compaction=True`, runs compaction, persists via `AgentTaskSessionRepository.update()`, records compaction cost
- Best-effort: LLM call failure → proceeds with full messages, logged as warning
- Tests: `tests/unit/test_session_compaction.py` (18 tests)

#### Chunk C5: CALSETA_* Environment Variables

- **What**: Inject `CALSETA_*` env vars into subprocess-based adapter environments. Update the Claude Code adapter to pass env vars to the subprocess. Define the env var set.
- **Why this wave**: Independent of other chunks
- **Modules touched**: `app/integrations/llm/claude_code_adapter.py` (env dict in subprocess), new `app/runtime/env_builder.py` (build env dict from context)
- **Depends on**: None
- **Produces**: Env vars available to Claude Code skills
- **Acceptance criteria**:
  - [ ] Claude Code subprocess receives all `CALSETA_*` env vars
  - [ ] Env vars set: `CALSETA_AGENT_ID`, `CALSETA_AGENT_NAME`, `CALSETA_RUN_ID`, `CALSETA_TASK_KEY`, `CALSETA_WAKE_REASON`, `CALSETA_API_URL`, `CALSETA_API_KEY`, `CALSETA_ALERT_UUID`, `CALSETA_WORKSPACE_DIR`
  - [ ] `CALSETA_API_KEY` is a short-lived agent API key (created per run, scoped to the agent)
  - [ ] Env vars are documented in a constant/enum for discoverability
  - [ ] Existing Claude Code adapter tests pass
- **Verification**: `pytest tests/ -k "claude_code" --no-header -q`

**Implementation notes (C5):**
- `app/runtime/env_builder.py` (new) — `CalsetaEnvVar(StrEnum)` with 9 members: `CALSETA_AGENT_ID`, `CALSETA_AGENT_NAME`, `CALSETA_RUN_ID`, `CALSETA_TASK_KEY`, `CALSETA_WAKE_REASON`, `CALSETA_API_URL`, `CALSETA_API_KEY`, `CALSETA_ALERT_UUID`, `CALSETA_WORKSPACE_DIR`
- `build_agent_env(agent, context, api_key=None) → dict[str, str]` inherits `os.environ`, overlays all CALSETA_* vars; uses `settings.CALSETA_API_BASE_URL` for API URL, `settings.AGENT_FILES_DIR / agent.uuid` for workspace; conditionally includes API_KEY, ALERT_UUID, RUN_ID, WAKE_REASON only when values are present
- Adapter changes: `env: dict[str, str] | None = None` parameter added to `create_message()` on all adapters (base ABC, Anthropic, OpenAI, Claude Code); Claude Code adapter passes `env=env` to `asyncio.create_subprocess_exec()`; API adapters ignore it
- Engine wiring deferred — engine calls `build_agent_env()` and passes to adapter (can be wired when env injection is needed)
- Tests: `tests/unit/test_env_builder.py` (16 tests)

#### Chunk C6: Ephemeral Skill Injection

- **What**: Switch skill injection from persistent write to temp-dir-per-run pattern. Create temp dir, write skills, pass to adapter, cleanup in finally. For Claude Code: pass `--add-dir {tmpdir}`.
- **Why this wave**: Independent of other chunks
- **Modules touched**: `app/runtime/engine.py` (`_inject_skills` method rewrite)
- **Depends on**: None
- **Produces**: Clean skill lifecycle, no stale files
- **Acceptance criteria**:
  - [ ] Skills written to `tempfile.mkdtemp(prefix="calseta-skills-")` per run
  - [ ] Temp dir cleaned up in `finally` block (even on failure)
  - [ ] Claude Code adapter receives `--add-dir {tmpdir}` argument
  - [ ] API adapters: skill content still injected into system prompt (no file needed)
  - [ ] No skill files left in `AGENT_FILES_DIR` after run completion
  - [ ] Existing skill injection tests updated
- **Verification**: `pytest tests/ -k "skill" --no-header -q && ls $AGENT_FILES_DIR/*/skills/ 2>/dev/null | wc -l` (should be 0 after run)

**Implementation notes (C6):**
- `app/runtime/engine.py` — `_inject_skills()` replaced with `_inject_skills_ephemeral(agent) → str | None` that uses `tempfile.mkdtemp(prefix="calseta-skills-")`, writes skill files to `{tmpdir}/{skill.slug}/{file.path}`, returns tmpdir path (or None if no skills)
- Engine `run()` method wrapped in `try/finally` — `shutil.rmtree(skills_tmpdir, ignore_errors=True)` in `finally` ensures cleanup even on failure
- For Claude Code adapter: tmpdir path available for `--add-dir {tmpdir}` argument (wiring to CLI args is a future step when skills are actively used)
- API adapters: skill content would be injected into system prompt (no file needed)
- Tests: `tests/unit/test_ephemeral_skills.py` (9 tests)

#### Chunk C7: Persistent Data Volume

- **What**: Fix the agent data persistence gap. `CALSETA_DATA_DIR` defaults to `/tmp/calseta` (wiped on container restart) and `AGENT_FILES_DIR` to `./data/agents` (not volume-mounted). Add a named Docker volume, update defaults, and update deployment docs. This is a prerequisite for the detection-as-code agent (git worktrees live here) and for NDJSON run logs (chunk A2).
- **Why this wave**: Independent, small change. Must land before Wave 4 workspace schema (D4) and before run logs write to `CALSETA_DATA_DIR/logs/`.
- **Modules touched**: `docker-compose.yml` (new `calseta_data` volume), `app/config.py` (update defaults), `.env.local.example`, `.env.prod.example`, `docs/guides/HOW_TO_DEPLOY.md`
- **Depends on**: None
- **Produces**: Persistent agent data directory that survives container restarts
- **Acceptance criteria**:
  - [ ] `docker-compose.yml` adds named volume `calseta_data` mounted at `/data/calseta` on api, worker, and mcp services
  - [ ] `CALSETA_DATA_DIR` default changed from `/tmp/calseta` to `/data/calseta`
  - [ ] `AGENT_FILES_DIR` default changed to `{CALSETA_DATA_DIR}/agents` (derived, not independent)
  - [ ] `.env.local.example` and `.env.prod.example` document both vars with notes about volume mounting
  - [ ] `docs/guides/HOW_TO_DEPLOY.md` updated: EFS for AWS ECS, Azure Files for ACA, local named volume for Docker Compose
  - [ ] `make dev`, `make lab`, `make dev-up` work correctly with the new volume (no Make changes needed — they inherit from docker-compose.yml)
  - [ ] `make lab-reset` (`docker compose down -v`) correctly wipes the data volume alongside postgres — expected behavior for a full reset
  - [ ] Existing agent file paths (`{AGENT_FILES_DIR}/{uuid}/`) still resolve correctly
- **Verification**: `docker compose down && docker compose up -d && docker compose exec worker ls /data/calseta` (directory exists and is writable)

**Implementation notes (C7):**
- `app/config.py` — `CALSETA_DATA_DIR` default changed from `/tmp/calseta` to `/data/calseta`; `AGENT_FILES_DIR` default changed to `""` with `@model_validator(mode="after")` `_derive_agent_files_dir()` that sets it to `{CALSETA_DATA_DIR}/agents` when empty; uses `object.__setattr__` for pydantic-settings compatibility
- `docker-compose.yml` — added `calseta_data:` named volume in `volumes:` section; mounted at `/data/calseta` on `api`, `worker`, and `mcp` services (alongside existing `.:/app` dev mount)
- `.env.local.example` — added commented documentation for `CALSETA_DATA_DIR` and `AGENT_FILES_DIR` with defaults and notes
- `.env.prod.example` — added "Persistent Data Volume" section with both vars, cloud storage notes (EFS, Azure Files)
- `docs/guides/HOW_TO_DEPLOY.md` — added "Persistent Data Volume" env var table; updated production compose example with `calseta_data` volume on all services; added platform-specific storage guide (Docker Compose / AWS ECS + EFS / Azure ACA + Azure Files / Kubernetes + PVC); added production checklist items for data volume
- `make lab-reset` (`docker compose down -v`) correctly wipes both `postgres_data` and `calseta_data` — expected for full reset

### Wave 0 — Design System Refinement (Can Run Anytime)

This chunk is independent of all runtime work. It can start immediately and run in parallel with any wave. It applies the three design improvements identified in the mockup process (semantic color layering, surface depth hierarchy, tighter typographic scale) to all existing pages.

#### Chunk Z1: Design System Refinement

- **What**: Apply semantic color layering, surface depth hierarchy, and tightened typography across all existing UI pages. Define reusable CSS utility patterns and apply them systematically.
- **Why this wave**: Independent of all backend work. Improves the entire UI before new components land.
- **Modules touched**: `ui/src/index.css` (new CSS variables + utility classes), individual page files listed in punch list below
- **Depends on**: None
- **Produces**: Consistent visual language across all pages, ready for new Wave 4 components to inherit

**Design changes to apply:**

1. **Semantic color layering** — Define card-level tinted backgrounds for each entity type. Every card/section gets a coordinated set: `bg` (rgba at 0.04-0.06), `border` (rgba at 0.12-0.15), `accent` (3px left bar), `icon-fill`, `label-color`. New CSS classes: `.card-agent`, `.card-finding`, `.card-alert`, `.card-tool`, `.card-analyst`, `.card-custom`.

2. **Surface depth tokens** — Enforce 4 surface levels: `--surface-base` (0a0e13), `--surface-1` (0d1117), `--surface-2` (131920), `--surface-3` (0f161d). Nested elements must step up one level. Currently most things sit at `--surface-1`.

3. **Typographic scale** — Tighten to 6 deliberate sizes with named roles:
   - `--text-micro`: 9px (uppercase category labels, metadata labels)
   - `--text-caption`: 10px (timestamps, hints, secondary metadata)
   - `--text-label`: 11px (badge text, form labels, section headers)
   - `--text-body`: 12px (primary content, table cells)
   - `--text-default`: 13px (default body text)
   - `--text-title`: 15px (sheet/section titles)
   Add `.micro-label` utility: `font-size: 9px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600; color: var(--text-muted);`

**Page-by-page punch list:**

**Dashboard (`/`)**
- [ ] StatCards: apply surface depth (cards should be `--surface-2` on `--surface-1` background)
- [ ] KpiCards: add semantic tint for each metric category (alerts=red, agents=teal, workflows=amber)
- [ ] Chart tooltips: verify dark background uses `--surface-2`
- [ ] Section headings: switch to `.micro-label` pattern for card category labels
- [ ] Drag handles: verify hover state uses teal tint

**Alerts list (`/alerts`)**
- [ ] Table header labels: switch to `.micro-label` (9px uppercase)
- [ ] Row hover: verify uses `--surface-2` not generic accent
- [ ] Severity/status/enrichment badges: already correct pattern, no change
- [ ] Filter popover backgrounds: use `--surface-2`

**Alert detail (`/alerts/$uuid`)**
- [ ] Status cards row: apply surface depth (`--surface-2` cards)
- [ ] Sidebar fields: switch labels to `.micro-label`
- [ ] Indicators tab — indicator rows: add subtle tint by malice (malicious=red tint, suspicious=amber tint, benign=teal tint, pending=neutral)
- [ ] Findings tab — finding cards: apply `.card-finding` (red-tinted background, 3px left accent)
- [ ] Activity tab — timeline dots: already color-coded, verify consistency
- [ ] Activity tab — event cards: apply semantic tint by actor type (system=dim, agent=teal, api=blue)
- [ ] Agent Payload tab — JsonViewer: verify uses `--surface-2` background
- [ ] Raw Data tab — JsonViewer: same
- [ ] KB tab — page cards: apply `.card-kb` with subtle teal tint
- [ ] RunAgentButton: verify teal styling

**Workflows list (`/workflows`)**
- [ ] Table header labels: `.micro-label`
- [ ] State badges: already correct
- [ ] Risk badges: already correct
- [ ] Indicator type badges: verify purple tint consistency

**Workflow detail (`/workflows/$uuid`)**
- [ ] Code editor background: verify `--surface-2`
- [ ] Sidebar field labels: `.micro-label`
- [ ] Version history cards: apply surface depth
- [ ] Run history cards: apply semantic tint by status (succeeded=teal, failed=red)

**Approvals (`/approvals`)**
- [ ] Pending items: verify amber border tint (`border-amber/20`)
- [ ] Approve/Reject buttons: verify green/red are clear
- [ ] Target badges (indicator/alert): verify purple/blue tints
- [ ] Confidence percentage: verify consistent sizing
- [ ] Non-pending items: verify reduced opacity treatment

**Detection rules list (`/detection-rules`)**
- [ ] Table header labels: `.micro-label`
- [ ] MITRE technique badges: verify consistent sizing and color

**Detection rule detail (`/detection-rules/$uuid`)**
- [ ] Rule query display: verify code block uses `--surface-2`
- [ ] Sidebar field labels: `.micro-label`
- [ ] Documentation: verify MarkdownPreview styling

**Agents list (`/agents`)**
- [ ] Table header labels: `.micro-label`
- [ ] Status badges: already correct
- [ ] Bot icon: verify teal tint

**Agent detail (`/agents/$uuid`)**
- [ ] Configuration tab — LLM config section: apply surface depth
- [ ] Configuration tab — field labels: `.micro-label`
- [ ] Heartbeat runs tab — run rows: apply semantic tint by status (succeeded=teal, failed=red, running=amber)
- [ ] Costs tab — cost event rows: apply surface depth
- [ ] Invocations tab — invocation rows: apply semantic tint by status
- [ ] Skills tab — skill cards: apply surface depth
- [ ] Files/instructions tab — file cards: apply surface depth
- [ ] Budget display: verify progress bar uses teal fill

**Enrichment providers list (`/enrichments`)**
- [ ] Table header labels: `.micro-label`
- [ ] Configured checkmark/X: verify teal/red colors
- [ ] Indicator type badges: verify consistent purple

**Enrichment provider detail (`/enrichments/$uuid`)**
- [ ] HTTP config builder: apply surface depth to step cards
- [ ] Field extraction table: `.micro-label` headers
- [ ] Malice rules builder: apply surface depth
- [ ] Test result display: apply semantic tint (success=teal, error=red)

**LLM integrations list (`/llm-integrations`)**
- [ ] Table header labels: `.micro-label`
- [ ] Provider name display: verify consistent styling

**LLM integration detail (`/llm-integrations/$uuid`)**
- [ ] Config field labels: `.micro-label`
- [ ] Test connection result: apply semantic tint
- [ ] Secret reference display: verify muted styling

**Issues / Kanban (`/issues`)**
- [ ] Kanban column headers: verify color-coded borders
- [ ] Issue cards: apply surface depth (`--surface-2` cards on `--surface-1` column)
- [ ] Priority dots: already correct, verify sizes
- [ ] Drag state: verify card elevation change

**Issue detail (`/issues/$uuid`)**
- [ ] Status badge: verify correct color
- [ ] Priority badge: verify correct color
- [ ] Assignment section: apply surface depth
- [ ] Activity timeline: apply semantic tint by actor

**Routines list (`/routines`)**
- [ ] Table header labels: `.micro-label`
- [ ] Cron expression display: verify mono styling
- [ ] Status badges: verify correct colors

**Routine detail (`/routines/$uuid`)**
- [ ] Schedule display: apply surface depth
- [ ] Run history: apply semantic tint by status
- [ ] Config sections: `.micro-label` headers

**Knowledge Base (`/kb`)**
- [ ] Sidebar folder tree: verify depth hierarchy
- [ ] Page list items: apply surface depth on hover
- [ ] Editor toolbar: verify consistent styling
- [ ] Preview mode: verify MarkdownPreview colors

**API Keys (`/settings/api-keys`)**
- [ ] Table header labels: `.micro-label`
- [ ] Key prefix: verify mono styling
- [ ] Scope badges: verify consistent sizing
- [ ] Key reveal modal: apply surface depth

**Secrets (`/settings/secrets`)**
- [ ] Field labels: `.micro-label`
- [ ] Secret value masking: verify consistent styling

**Queue (`/queue`)**
- [ ] Table header labels: `.micro-label`
- [ ] Auto-refresh indicator: verify styling
- [ ] Severity/enrichment badges: already correct

**Alert Sources (`/settings/alert-sources`)**
- [ ] Table header labels: `.micro-label`
- [ ] Expandable row detail: apply surface depth
- [ ] Webhook URL display: verify mono styling

**Indicator Mappings (`/settings/indicator-mappings`)**
- [ ] Table header labels: `.micro-label`
- [ ] Extraction target badges: verify consistent styling

**Global components**
- [ ] Sidebar navigation: verify active item uses teal tint
- [ ] TopBar: verify title typography
- [ ] ClockDisplay: verify dim color
- [ ] Toast notifications: verify teal (success) and red (error) styling
- [ ] Loading skeletons: verify use `--surface-2` shimmer
- [ ] Empty states: verify consistent styling
- [ ] Pagination: verify button styling consistency
- [ ] ConfirmDialog: verify surface depth on modal

- **Acceptance criteria**:
  - [ ] New CSS variables defined in `index.css`: surface depth tokens, typographic scale, semantic card classes
  - [ ] `.micro-label` utility class used for all table headers, sidebar labels, form field labels
  - [ ] Cards/sections across all pages use correct surface depth level
  - [ ] At least 3 pages have semantic color tinting applied (alert detail findings, agent detail runs, approvals)
  - [ ] No visual regressions — existing badge colors, status indicators, and interactive elements unchanged
  - [ ] All changes are CSS/class-level — no component API changes, no prop changes
- **Verification**: Manual review of every page in the punch list. Screenshot comparison before/after for alert detail + agent detail + dashboard.

### Wave 4 — UI + Schema-Only Planning

Depends on Waves 2-3 for backend endpoints. UI chunks can run in parallel.

#### Chunk D1: Run Transcript Panel (UI)

- **What**: Build the run transcript view in the agent detail page. Sheet/panel that opens on heartbeat run row click. Shows chronological event stream with SSE for live runs and HTTP polling for completed runs. Type-specific rendering for each event type.
- **Why this wave**: Needs SSE endpoint (B2) and engine streaming (B1)
- **Modules touched**: `ui/src/pages/settings/agents/detail.tsx` (heartbeat runs tab), new `ui/src/components/run-transcript/` directory, `ui/src/hooks/use-api.ts` (new hooks), `ui/src/lib/types.ts` (new types)
- **Depends on**: B1, B2
- **Produces**: Live and historical run transcript viewing
- **Acceptance criteria**:
  - [ ] Clicking a heartbeat run row opens a transcript panel
  - [ ] Live runs: SSE connection streams events in real-time with pulsing indicator
  - [ ] Completed runs: events loaded via `GET /v1/runs/{uuid}/events`
  - [ ] Events rendered by type: assistant messages, tool calls (collapsible), findings (highlighted), errors (red)
  - [ ] Auto-scroll to bottom during streaming, manual scroll override
  - [ ] Follows existing design system: Manrope headings, IBM Plex Mono body, teal/amber/red badges
  - [ ] Responsive: works on both desktop and tablet layouts
  - [ ] Max 200 events rendered in DOM (virtualized or paginated for long runs)
- **Verification**: Manual — start a dev agent run, verify transcript streams in real-time

#### Chunk D2: Cancel Button + Status Badges (UI)

- **What**: Add cancel button to running heartbeat rows and transcript panel. Add `cancelled` and `timed_out` status badges. Update all status rendering throughout agent pages.
- **Why this wave**: Needs cancellation endpoint (B3)
- **Modules touched**: `ui/src/pages/settings/agents/detail.tsx`, `ui/src/hooks/use-api.ts` (new `useCancelRun` mutation), `ui/src/lib/types.ts`
- **Depends on**: B3
- **Produces**: Cancel UX and comprehensive status display
- **Acceptance criteria**:
  - [ ] "Cancel Run" appears in row dropdown for `running` heartbeat runs
  - [ ] Prominent cancel button in transcript panel header for running runs
  - [ ] Confirmation dialog before cancellation
  - [ ] `cancelled` badge: Dim color (#57635F), consistent with existing badge pattern
  - [ ] `timed_out` badge: Amber color (#FFBB1A)
  - [ ] All heartbeat run status rendering updated across agent detail page
- **Verification**: Manual — cancel a running agent, verify badge transitions

#### Chunk D3: Alert Comment Re-Trigger (UI)

- **What**: Add comment input to the alert detail activity timeline. "Post & Re-trigger" and "Post Only" buttons. Shows a toast when an agent is re-triggered.
- **Why this wave**: Needs comment wakeup endpoint (C1)
- **Modules touched**: `ui/src/pages/alerts/detail.tsx`, `ui/src/hooks/use-api.ts` (new `usePostAlertNote` mutation)
- **Depends on**: C1
- **Produces**: Analyst-to-agent communication in the UI
- **Acceptance criteria**:
  - [ ] Textarea at bottom of alert activity timeline
  - [ ] "Post & Re-trigger" button (teal) posts note with `trigger_agent=true`
  - [ ] "Post Only" button (outline) posts note with `trigger_agent=false`
  - [ ] Success toast: "Note posted. Agent re-triggered." or "Note posted."
  - [ ] Textarea clears after successful post
  - [ ] Activity timeline refreshes to show the new note
  - [ ] "Post & Re-trigger" disabled with tooltip when no agent has recently investigated this alert
- **Verification**: Manual — post a note on an alert, verify agent re-triggers

#### Chunk D4: Workspace Schema (Plan Only)

- **What**: Create the `agent_workspaces` migration (table creation only). Add `workspace_mode` field to AgentRegistration. No service logic, no API endpoints — schema reservation only.
- **Why this wave**: Independent, purely additive schema
- **Modules touched**: New migration, `app/db/models/agent_registration.py` (new field), new `app/db/models/agent_workspace.py` (model only)
- **Depends on**: None
- **Produces**: Schema ready for future detection-as-code agent work
- **Acceptance criteria**:
  - [ ] Migration creates `agent_workspaces` table with all columns from the design
  - [ ] `workspace_mode` added to AgentRegistration with default `'none'`
  - [ ] ORM model exists but no repository, service, or API routes
  - [ ] Migration is reversible
- **Verification**: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`

#### Chunk D5: Configurable Dashboard Cards (UI)

- **What**: Add card management to the home dashboard — "+" button to open a card catalog, "X" to remove cards, preset switcher, localStorage persistence. Refactor the existing 32 fixed cards into a registry that the catalog reads from.
- **Why this wave**: Independent of backend runtime work. Purely frontend.
- **Modules touched**: `ui/src/pages/dashboard/index.tsx` (card registry, add/remove logic, preset system), new `ui/src/components/dashboard/card-catalog.tsx` (catalog sheet), new `ui/src/components/dashboard/card-registry.ts` (card definitions with metadata), `ui/src/lib/types.ts` (card config types)
- **Depends on**: None
- **Produces**: Configurable dashboard ready for new agent cards as backend endpoints ship
- **Acceptance criteria**:
  - [ ] "+" button in dashboard header opens a card catalog sheet (right-edge slide-out)
  - [ ] Catalog shows cards organized by category tabs: All, Alerts, Agents, Workflows, Platform, Costs
  - [ ] Each catalog entry shows: title, one-line description, size badge (small/wide/large)
  - [ ] Search input at top of catalog filters cards across all categories (type-ahead)
  - [ ] Clicking a card adds it to the dashboard grid. Already-added cards show checkmark + "Added" (dimmed)
  - [ ] Hovering a dashboard card shows "X" button in top-right. Clicking removes the card.
  - [ ] Preset dropdown next to "+" button: "SOC Overview" (default), "Agent Operations", "Minimal"
  - [ ] Selecting a preset replaces all cards (with confirmation dialog)
  - [ ] Layout (card selection + positions) persisted to localStorage
  - [ ] Reset button restores default preset
  - [ ] All 32 existing cards refactored into a card registry with category/description metadata
  - [ ] New agent-category cards added to registry (even if their data endpoints don't exist yet — show "Coming soon" placeholder)
  - [ ] Follows design system: Manrope headings, IBM Plex Mono body, teal/amber/red badges, surface depth
- **Verification**: Manual — add a card, remove a card, switch presets, refresh page (verify persistence), reset layout
