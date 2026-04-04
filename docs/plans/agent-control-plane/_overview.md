# Agent Control Plane — Overview

> **Split PRD navigation:**
> [Overview](_overview.md) | [Part 1: Core Runtime](part-1-core-runtime.md) | [Part 2: Actions & Orchestration](part-2-actions-orchestration.md) | [Part 3: Knowledge & Memory](part-3-knowledge-memory.md) | [Part 4: Operational](part-4-operational.md) | [Part 5: Platform Ops](part-5-platform-ops.md) | [API & MCP](appendix-api-mcp.md) | [Implementation Phases](implementation-phases.md)

---

## created: 2026-03-16

project: Calseta
status: idea
priority: high

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
- **Generic task/issue tracking** — adapted as `agent_issues` (security-domain work items: remediation, detection tuning, post-incident, compliance) — see [Part 4: Operational Management]
- **Agent instructions bundle** — named markdown instruction files per agent, version-controlled alongside config — see agent_registrations.instruction_files
- **Storage provider abstraction** — local-disk + S3/EFS providers for agent home directories

Key Paperclip concepts **not** adopted:

- Org chart / reporting hierarchy (security agents are functional, not hierarchical)
- Company-as-first-class-object (Calseta is single-tenant — one deployment per org)
- Kanban/board metaphor (security teams think in queues and incidents)

> **Note on generic task/issue tracking:** Paperclip's issue system IS adopted in Part 4 as `agent_issues`, adapted for the security domain (categories: remediation, detection_tuning, post_incident, compliance, investigation, maintenance). External sync with Jira/Linear is Phase 8+. See [Part 4: Operational Management].

### Paperclip Implementation Reference Map

> For LLM implementors: when implementing a feature in this PRD, the corresponding Paperclip implementation provides a proven reference pattern. Adapt for Python/FastAPI/SQLAlchemy — don't port TypeScript directly.

| PRD Feature | Paperclip Reference File(s) |
|---|---|
| Agent registry + config revisions | `/server/src/services/agents.ts`, `/packages/db/src/schema/agents.ts`, `agent_config_revisions.ts` |
| Agent API keys | `/packages/db/src/schema/agent_api_keys.ts`, `board_api_keys.ts` |
| Heartbeat runs + sessions | `/server/src/services/heartbeat.ts`, `/packages/db/src/schema/heartbeat_runs.ts`, `agent_task_sessions.ts`, `agent_wakeup_requests.ts` |
| Cost events + budget enforcement | `/server/src/services/costs.ts`, `budgets.ts`, `quota-windows.ts`, `/packages/db/src/schema/cost_events.ts`, `budget_policies.ts` |
| Activity log | `/server/src/services/activity.ts`, `activity-log.ts`, `/packages/db/src/schema/activity_log.ts` |
| Tool registry + dispatcher | `/server/src/services/plugin-tool-registry.ts`, `plugin-tool-dispatcher.ts` |
| Human auth (BetterAuth) | `/server/src/auth/better-auth.ts` |
| Agent JWT auth | `/server/src/agent-auth-jwt.ts` |
| Permissions/access | `/server/src/services/access.ts`, `/packages/shared/src/types/access.ts` |
| Agent home directory paths | `/server/src/home-paths.ts` |
| Storage providers (local + S3) | `/server/src/storage/local-disk-provider.ts`, `s3-provider.ts`, `provider-registry.ts` |
| Agent instructions bundle | `/server/src/services/agent-instructions.ts`, `default-agent-instructions.ts` |
| Routines / scheduled invocations | `/server/src/services/routines.ts`, `/packages/db/src/schema/routines.ts` |
| Issues + comments | `/server/src/services/issues.ts`, `/packages/db/src/schema/issues.ts`, `issue_documents.ts` |
| Context snapshot | `HeartbeatRun.contextSnapshot` field in `/packages/shared/src/types/heartbeat.ts` |
| Adapter system | `/packages/adapters/` — Claude, OpenAI, Gemini, HTTP, Process adapters |

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


|                         | Managed Agent                                             | BYO Agent                                                   |
| ----------------------- | --------------------------------------------------------- | ----------------------------------------------------------- |
| **Who makes LLM calls** | Calseta (via `llm_integrations`)                          | The agent itself                                            |
| **System prompt**       | Stored in Calseta DB, editable via API/UI                 | Agent's own                                                 |
| **Tools**               | Calseta's tool system (tiered permissions)                | Agent calls Calseta REST/MCP                                |
| **Cost tracking**       | Automatic (Calseta sees every token)                      | Agent self-reports via `POST /api/v1/cost-events`           |
| **How identified**      | `llm_integration_id` is set, `execution_mode = 'managed'` | `llm_integration_id` is NULL, `execution_mode = 'external'` |
| **Use case**            | Teams that want Calseta to handle everything              | Teams with existing agents that just need the control plane |


### Core Philosophy Alignment


| Calseta Principle                      | How the Platform Honors It                                                                                                              |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Deterministic ops stay deterministic   | Alert routing, tool permission checks, budget enforcement, approval routing — zero LLM tokens. Intelligence is only in agent execution. |
| Token optimization is first-class      | Budget tracking and hard-stops are native. Managed agents give exact cost visibility (Calseta sees every API call).                     |
| Framework-agnostic                     | BYO agents can be built with any framework. Managed agents use Calseta's runtime but the underlying LLM provider is swappable.          |
| AI-readable documentation is a feature | Agent registry includes capability descriptions, methodologies, and system prompts — all surfaced via API for agent-to-agent discovery. |
| Self-hostable without pain             | Runtime uses the same PostgreSQL + Procrastinate infrastructure. No new dependencies for managed agents beyond the LLM provider SDK.    |


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


---

## Competitive Positioning

### Before (Data Layer Only)

> "Calseta: the open-source data layer for security AI agents. Ingest, normalize, enrich, contextualize, and dispatch alerts to your agents."

### After (AI SOC Platform)

> "Calseta: the open-source AI SOC platform. Ingest alerts from any source, enrich them automatically, and orchestrate AI agents to investigate — with human approval gates, budget controls, and full audit trails. Self-host it, extend it, own your security."

> **v1 vs v2 clarity:** Calseta v1 ships the data layer (ingest, enrich, normalize, MCP server). Calseta v2 adds the agent control plane: managed agent execution, multi-agent orchestration, approval gates, KB, memory, and issues. v1 is production-ready today. v2 is this PRD.

### Competitive Matrix

> [!note] Phase caveats
> "Calseta (with CP)" reflects the full v2 roadmap across all phases. Features marked **bold** are Phase 3+ and will not ship in the Phase 1–2 MVP. Multi-agent orchestration (Phase 5), KB (Phase 6), memory (Phase 6), and full UI (Phase 6.5) are later phases. The Phase 1–4 MVP delivers: managed + external agents, pull queue, approval gates, cost controls, heartbeat monitoring, and secrets.

| Capability                                  | Calseta v1 | Calseta v2 (with CP) | Dropzone | Prophet | Simbian | Torq    | Tines   |
| ------------------------------------------- | ---------- | -------------------- | -------- | ------- | ------- | ------- | ------- |
| Open source                                 | Yes        | Yes                  | No       | No      | No      | No      | No      |
| Self-hostable                               | Yes        | Yes                  | No       | No      | No      | No      | No      |
| Data pipeline (ingest/enrich)               | Yes        | Yes                  | Partial  | Partial | Partial | Yes     | Yes     |
| Multi-agent orchestration                   | No         | Yes (Phase 5)        | No       | No      | No      | No      | No      |
| Human approval gates                        | Yes        | Yes                  | Limited  | Limited | Limited | Yes     | Yes     |
| Budget/cost controls (per-agent, per-model) | No         | Yes                  | No       | No      | No      | No      | No      |
| MCP native                                  | Yes        | Yes                  | No       | No      | No      | No      | No      |
| BYO agent + managed agents                  | No         | Yes                  | No       | No      | No      | No      | No      |
| Full audit trail (incl. delegation chains)  | Yes        | Yes                  | Partial  | Partial | Partial | Yes     | Yes     |
| Reference agents (open source)              | No         | Yes (Phase 7)        | No       | No      | No      | No      | No      |
| Agent-native schema                         | Yes        | Yes                  | No       | No      | No      | No      | No      |
| **Knowledge base with context injection**   | No         | **Yes (Phase 6)**    | No       | No      | No      | No      | No      |
| **Agent persistent memory**                 | No         | **Yes (Phase 6)**    | No       | No      | No      | No      | No      |
| **Session continuity across invocations**   | No         | **Yes (Phase 1)**    | No       | No      | No      | No      | No      |
| **Scheduled agent routines (cron)**         | No         | **Yes (Phase 5.5)**  | No       | No      | No      | Partial | Partial |
| **Non-alert work management (issues)**      | No         | **Yes (Phase 5.5)**  | No       | No      | No      | No      | No      |
| **Investigation campaigns**                 | No         | **Yes (Phase 5.5)**  | No       | No      | No      | No      | No      |
| **External KB sync (Confluence/GitHub)**    | No         | **Yes (Phase 6)**    | No       | No      | No      | No      | No      |
| **Centralized secrets with log redaction**  | No         | **Yes (Phase 1)**    | No       | No      | No      | Partial | Partial |


### Key Differentiators

1. **Open source + self-hosted** — security teams can audit, modify, and own the code. No vendor lock-in.
2. **Multi-agent orchestration** — orchestrator agents delegate to specialist sub-agents with full visibility into the investigation tree. Not just "run one agent per alert."
3. **BYO + managed agents** — bring your own agent (Option A) or use Calseta's LLM integrations and reference agents to get started fast (Option B). Both work through the same control plane.
4. **MCP native** — first AI SOC platform with native MCP support. Any MCP client is a Calseta agent. Orchestration tools available via MCP.
5. **Deterministic pipeline + AI orchestration** — the data layer never burns LLM tokens. AI costs are isolated to agent execution and fully tracked per-agent and per-LLM-integration.
6. **Approval gates with full context** — operators see the enriched alert, full sub-agent investigation chain, orchestrator reasoning, and proposed action together. Not a black box.
7. **Cost transparency** — per-agent, per-model, per-alert cost tracking with budget enforcement. Know exactly what each investigation costs and which models are burning budget.
8. **Reference agents as education** — open-source, well-documented agent implementations that teach security teams how to build AI SOC agents. Videos, docs, and working code.
9. **Knowledge base with context injection** — internal wiki where agents and operators author runbooks, investigation summaries, and institutional knowledge. Pages are automatically injected into agent prompts based on role/scope. Syncs from Confluence, GitHub, and URL endpoints; Notion sync is Phase 8+. No other AI SOC platform has this.
10. **Agent persistent memory** — agents learn once and remember forever. Entity profiles, investigation patterns, and institutional observations persist across invocations. Staleness detection prevents stale memory from misleading agents. Most platforms restart agents from scratch on every invocation.
11. **Session continuity** — multi-wave investigations don't restart from scratch. Session state persists across heartbeats with automatic compaction when context windows fill up.
12. **Full work management** — alerts for automated signals, issues for follow-up work (remediation tasks, detection tuning, compliance). Agents create issues from investigations so nothing gets buried in alert comments.
13. **Investigation campaigns** — define strategic objectives (reduce MTTD, improve auto-resolve rate) with target metrics, link alerts and issues, and track auto-computed progress. No manual metric entry.

---

## Open Questions

- ~~Should the control plane be a separate Python package/module or integrated into the core Calseta codebase?~~ **Resolved:** Integrated into the core Calseta codebase — no separate package.
- ~~UI tech stack — does Calseta have an existing UI to extend, or is this the first UI?~~ **Resolved:** Existing React 19 + Vite UI with Tailwind CSS v4, shadcn/ui (New York style), TanStack Router/Query, and a comprehensive `DESIGN_SYSTEM.md` (572 lines). All new control plane pages extend the existing UI — list/detail page patterns, color semantics, and component library are already established. Component cleanup and brand guideline hardening are tracked as a Phase 6 UI work item: audit existing components for consistency gaps, extract any remaining one-off patterns into shared components, and update `DESIGN_SYSTEM.md` with agent control plane additions (agent status colors, topology graph conventions, KB page card patterns).
- ~~How does this interact with the existing dispatch webhook system?~~ **Resolved:** Both coexist. Push webhook (existing, `adapter_type = 'webhook'`) and pull queue (new) are both supported. External agents choose their model. Existing registrations continue unchanged — see Backwards Compatibility note in the Agent Registry section.
- ~~Secret management for LLM API keys — store encrypted in DB, env vars, or defer to external secret managers?~~ **Resolved:** Full secrets system specced with `local_encrypted` (AES-256-GCM in DB) and `env_var` providers for Phase 1, external providers (AWS SM, Vault) in Phase 8+. Secret_ref pattern for all credential fields. All LLM API keys use the new secrets management system.
- ~~Incident vs. alert — should the control plane introduce an "incident" entity that groups related alerts, or keep alerts as the atomic unit?~~ **Resolved:** No incident entity in v2 control plane. A separate PRD will cover incidents. Alerts remain the atomic unit; `agent_issues` (security-domain follow-up work items) handle everything else.
- ~~Notification integrations — Slack first, but what about Teams, PagerDuty, Opsgenie?~~ **Resolved:** Scope is approval gate + action request notifications. Slack first, Teams second. PagerDuty/Opsgenie deferred to Phase 8+.
- ~~How does this affect Calseta's v1.0 milestone?~~ **Resolved:** v2 feature. No impact on v1.0.
- ~~Sub-agent timeout behavior — what happens when a specialist takes too long?~~ **Resolved:** Handled by `AgentSupervisor` periodic task (`supervise_running_agents_task`, runs every 30s). Stuck agents are detected via heartbeat timeout, killed, and their alert is released back to the queue or escalated. See Supervision Loop section.
- ~~Should orchestrators be able to invoke the same specialist multiple times in one investigation (e.g., SIEM agent called twice with different queries)?~~ **Resolved:** Yes.
- ~~How do reference agents handle credentials for external tools?~~ **Resolved:** Via the secrets system. Reference agents use `secret_ref` bindings in adapter config. Operators register credentials once in secrets, agents reference by name.
- ~~Should the agent builder UI support prompt versioning / A/B testing?~~ **Resolved:** Agent instruction files are KB pages — they inherit the KB revision system. Version history is automatic. A/B testing (comparing two system prompts) is deferred to Phase 8+.

**New open questions (from Paperclip evaluation and PRD enhancements):**

- ~~Session compaction strategy — LLM summary vs truncation?~~ **Resolved:** LLM-based summarization as default (higher quality, ~500–1K tokens per compaction event). Truncation (keep last N turns) as automatic fallback when LLM provider is unavailable or cost budget is exhausted. Both strategies are operator-configurable via `session_compaction_strategy` enum on `agent_registrations`.
- ~~KB page injection token budget — what's the right default percentage?~~ **Resolved:** Covered by the existing token budget allocation table in the Prompt Construction section. KB context target: 10–20%. Full breakdown: system prompt + instruction files (5–15%), methodology (5–10%), KB context (10–20%), alert/task context (20–40%), session state (10–30%), runtime checkpoint (1–2%), with 20% minimum hard-floor reserved for agent reasoning.
- ~~Agent memory promotion flow — when an agent promotes private memory to shared, does it require operator approval?~~ **Resolved:** No operator approval required by default (memory entries are metadata-level observations, not code). Configurable per-instance via `agent_registrations.memory_promotion_requires_approval` (bool, default `false`). Use case: an agent investigating multiple alerts identifies a cross-alert pattern (e.g., "all lateral movement from this subnet follows the same staging hostname pattern") and promotes the insight to shared memory so other agents benefit. Operators managing high-assurance deployments can enable approval gating.
- ~~Issue/task system and alert assignments — unified work item or separate entity types?~~ **Resolved (previous session):** Separate entity types — alerts and `agent_issues` have separate checkout mechanics. Unified abstraction is explicitly deferred.
- ~~KB external sync conflict resolution — what happens when an operator edits a synced page locally?~~ **Resolved (previous session):** Pull-only is the default sync model. When a hash change is detected, the local page is overwritten with the external source. Operators who need to annotate synced pages should create a linked (non-synced) companion page instead of editing the synced page directly. Bidirectional sync (Phase 8+) will introduce proper conflict detection.
- ~~Routine concurrency and the issue system — auto-assign or normal routing?~~ **Resolved:** Normal routing. Auto-assigning issues to the originating routine's agent would tightly couple routine definitions to agent availability. Optional: add `preferred_agent_id` on routines as a routing hint (not a hard assignment), allowing operators to express intent without breaking the routing contract.
- ~~Campaign metric auto-computation — auto or manual?~~ **Resolved:** Calseta auto-computes all metrics from alert and assignment data. No manual metric entry. Metrics include MTTD, FP rate, auto-resolve rate, and any other platform-level statistics derivable from existing data.
- **UI working session scope** — spec all pages at once or iterate in priority order? **Deferred:** Will begin once PRD cleanup is complete. Priority order approach preferred (approval inbox first, then agent detail, etc.).
- ~~Agent topology rendering — D3, cytoscape.js, react-flow, or server-side SVG?~~ **Resolved:** Use `@xyflow/react` (react-flow) — already a dependency in the Calseta UI (used for `AlertGraph`). Client-side rendering supports interactive panning, zooming, and node selection without server roundtrips. No new dependency needed.

---

## Rough Scope

**Extra Large** — this is a multi-phase effort that transforms Calseta from a data layer into a full platform.

- Phase 1: ~6-8 weeks (LLM providers, agent runtime, tool system, agent registry, adapters, queue, **session state, secrets, heartbeat_runs + cost_events tables, agent home, run-scoped JWTs** — the core platform) `[Part 1]` `[Part 5]`
- Phase 2: ~2 weeks (actions, approval gate integration) `[Part 2]`
- Phase 3: ~2-3 weeks (action execution integrations) `[Part 2]`
- Phase 4: ~1-2 weeks (heartbeat reporting + supervision layer, budget enforcement, per-model cost tracking) `[Part 1]`
- Phase 5: ~3-4 weeks (multi-agent orchestration) `[Part 2]`
- Phase 5.5: ~4-5 weeks (**issue/task system, routine scheduler, campaigns + auto-computed metrics, agent topology**) `[Part 4]`
- Phase 6: ~3-4 weeks (**knowledge base + external sync + agent persistent memory**) `[Part 3]`
- Phase 6.5: ~5-7 weeks (full operator UI — approval inbox, agent detail, queue, topology `@xyflow/react`, issue board, KB browser, campaigns, secrets, cost dashboard) `[Part 5]`
- Phase 7: ~3-4 weeks (reference agents, process adapter, agent builder UI) `[Part 1]`
- Phase 8: Ongoing (advanced features) `[All Parts]`

Total MVP (Phases 1-4, managed + external agents, API-only): ~12-15 weeks
Multi-agent orchestration (Phases 1-5): ~15-19 weeks
Full operational platform (Phases 1-5.5): ~19-24 weeks
Full platform with KB + memory (Phases 1-6): ~22-28 weeks
Full platform with UI (Phases 1-6.5): ~27-35 weeks
Reference agents + agent builder (Phases 1-7): ~30-39 weeks

## Agent-to-Agent (A2A) Protocol — Future Interoperability

Google's [A2A (Agent-to-Agent) protocol](https://google.github.io/A2A/) is an open standard for agent interoperability: standardized agent capability cards, task lifecycle management (submit/poll/cancel), and push/pull communication. Calseta's internal multi-agent orchestration (Part 2: `agent_invocations`, `delegate_task`) is purpose-built for the security domain and does not need to change. A2A is relevant at the **external boundary** — enabling third-party agent frameworks (LangGraph, CrewAI, AutoGen) to discover and invoke Calseta agents without custom integration code.

**Phase 8+ items:**
- `GET /api/v1/agents/{uuid}/agent-card` — serve A2A-compatible capability JSON for each registered agent (maps `capabilities` + `system_prompt` + `tool_ids` to A2A format)
- `GET /.well-known/agent.json` — instance-level A2A discovery endpoint
- Accept A2A-format task submissions as an alternative inbound path alongside existing webhook push
- External specialist discovery — if a BYO specialist exposes an A2A card, the orchestrator can discover its capabilities without manual `capabilities.json` registration

**Why deferred:** Internal orchestration design already covers all current requirements. A2A adds value at the ecosystem boundary, not the core. The existing REST API contract does not preclude adding A2A-compatible endpoints later.

---

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

