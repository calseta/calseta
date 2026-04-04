# Appendix: API Contract, MCP Extensions & User Stories

> **Split PRD navigation:**
> [Overview](_overview.md) | [Part 1: Core Runtime](part-1-core-runtime.md) | [Part 2: Actions & Orchestration](part-2-actions-orchestration.md) | [Part 3: Knowledge & Memory](part-3-knowledge-memory.md) | [Part 4: Operational](part-4-operational.md) | [Part 5: Platform Ops](part-5-platform-ops.md) | [API & MCP](appendix-api-mcp.md) | [Implementation Phases](implementation-phases.md)

# Shared Appendices

---

## API Contract

All endpoints under `/api/v1`. Extends Calseta's existing FastAPI router. Existing agent endpoints (`GET/POST/PATCH/DELETE /v1/agents`, `POST /v1/agents/{uuid}/test`) continue to work for webhook-based agent management. The control plane adds new endpoints for the pull model, orchestration, and lifecycle management.

### Pagination Convention

All list endpoints (`GET /api/v1/agents`, `GET /api/v1/issues`, `GET /api/v1/kb`, etc.) follow Calseta's standard pagination contract:

```
Query params: page=1 (1-indexed), page_size=50 (default), page_size max=500

Response envelope:
{
  "data": [...],
  "meta": {
    "total": 142,
    "page": 1,
    "page_size": 50
  }
}
```

List endpoints that support filtering accept filter params as query strings (e.g., `?status=running&agent_type=orchestrator`). All filter params are optional — omitting returns all records.

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

### Cost Event Reporting Contract `[Part 1]`

```
POST /api/v1/cost-events

Request:
{
  "provider": "anthropic",
  "model": "claude-opus-4-6",
  "input_tokens": 12400,
  "output_tokens": 1850,
  "cost_cents": 42,
  "alert_id": "uuid",            // optional
  "heartbeat_run_id": "uuid",    // optional — links cost to specific run
  "invocation_id": "uuid"        // optional — links cost to sub-agent call
}

Response (201):
{
  "cost_event_id": "uuid",
  "agent_budget": {
    "monthly_cents": 50000,
    "spent_cents": 17242,
    "remaining_cents": 32758,
    "hard_stop_triggered": false
  }
}
```

> `hard_stop_triggered: true` signals the agent to stop immediately. Managed agents handle this automatically; external agents must check this field after every `report_cost` call.

### Heartbeat and Monitoring `[Part 1]`

```
POST   /api/v1/heartbeat                       Agent reports heartbeat (auto from adapters)
GET    /api/v1/heartbeat-runs                   List heartbeat runs (paginated)
GET    /api/v1/heartbeat-runs/{run_id}          Get run details with logs
```

**Heartbeat request/response contract:**

```
POST /api/v1/heartbeat

Request:
{
  "assignment_id": "uuid",       // optional — heartbeat is scoped to this assignment
  "status": "running",           // running | idle | completed | error
  "progress_note": "...",        // optional, human-readable progress update
  "findings_count": 3,           // optional, findings logged this heartbeat
  "actions_proposed": 1          // optional
}

Response (200):
{
  "heartbeat_run_id": "uuid",
  "acknowledged_at": "2026-04-03T10:22:00Z",
  "agent_status": "running",
  "supervisor_directive": null   // null | "pause" | "terminate" — operator override
}
```

> `supervisor_directive` is non-null when an operator has issued a pause or terminate command. External agents must poll heartbeat responses and respect directives. Managed agents handle directives automatically via the runtime engine.

**Invocation polling response contract:**

```
GET /api/v1/invocations/{invocation_id}/poll?timeout_ms=30000

Response (200 — completed):
{
  "invocation_id": "uuid",
  "status": "completed",
  "child_agent_name": "identity-agent",
  "result": {
    "success": true,
    "summary": "jsmith@corp.com: low-risk. Last login normal location. No lateral movement.",
    "findings": [...],
    "actions_proposed": 0,
    "tokens_used": 4200,
    "cost_cents": 12
  }
}

Response (202 — still running, long-poll timed out):
{
  "invocation_id": "uuid",
  "status": "running",
  "started_at": "2026-04-03T10:21:00Z"
}

Response (200 — failed):
{
  "invocation_id": "uuid",
  "status": "failed",
  "error": "specialist timed out after 300s",
  "child_agent_name": "identity-agent"
}
```

### Session Management `[Part 1]`

```
GET    /api/v1/sessions                              List agent task sessions (filterable by agent, status)
GET    /api/v1/sessions/{task_key}                   Get session details (token usage, heartbeat count, compaction status)
DELETE /api/v1/sessions/{task_key}                   Archive/reset session (operator override — clears conversation state)
GET    /api/v1/agents/{uuid}/sessions                List all sessions for an agent
```

> Sessions are read-only via REST; agents manage session state via the heartbeat and checkout flows. Operators can force-reset sessions (DELETE) if an agent is stuck in an inconsistent state. All session data is retained for audit purposes — DELETE archives, not hard-deletes.

### Memory `[Part 3]`

Memory entries are primarily managed via MCP tools (`save_memory`, `recall_memory`, `promote_memory`, etc.). The REST API exposes read + operator management:

```
GET    /api/v1/agents/{uuid}/memory              List memory entries for an agent
GET    /api/v1/memory/shared                     List shared memory entries (visible to all agents)
GET    /api/v1/memory/{memory_id}               Get memory entry details
PATCH  /api/v1/memory/{memory_id}               Update memory entry (operator edit, inject_scope change)
DELETE /api/v1/memory/{memory_id}               Delete memory entry
POST   /api/v1/memory/{memory_id}/promote       Promote private memory to shared (operator-initiated)
```

> Agents create memory exclusively via MCP tools. The REST API is for operator review, management, and debugging. Bulk memory export and import are Phase 8+.

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

**KB search modes (`GET /api/v1/kb/search`):**

```
Query params:
  q:            string — required, search query
  mode:         "keyword" | "semantic" — default "keyword"
  folder:       string — optional, restrict to folder path prefix
  inject_scope: "global" | "role" | "agent" | "all" — optional filter
  status:       "published" | "draft" | "archived" — optional, default "published"
  page, page_size: standard pagination

Keyword mode: PostgreSQL full-text search on title + content (tsvector index).
Semantic mode: Vector embedding similarity search. Phase 8+ only; returns 400 if
               semantic backend not configured, with error.code="semantic_unavailable".

Response:
{
  "data": [
    {
      "slug": "runbooks/identity/okta-lockout",
      "title": "Okta Account Lockout Response",
      "folder": "runbooks/identity",
      "summary": "First 200 chars of content...",
      "inject_scope": "role:soc_analyst",
      "sync_source": "github",
      "relevance_score": 0.87
    }
  ],
  "meta": {"total": 4, "page": 1, "page_size": 10, "mode": "keyword"}
}
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
get_agent_context      — Get agent's config, budget status, capabilities, and active instruction files
get_context_preview    — Returns the assembled 6-layer prompt context for the current agent + alert,
                         including token counts per layer and KB pages included/excluded by budget.
                         Primary debugging tool for understanding what context the agent receives.
report_heartbeat       — Explicit heartbeat for external agents (managed agents heartbeat automatically)
get_session_state      — Get current session state (token counts, heartbeat count, compaction status)
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

### New MCP Resources `[Part 1+]`

New resources added to the MCP server alongside existing v1 resources (`calseta://alerts`, `calseta://metrics/summary`, etc.).

```
calseta://agents                — List all registered agents with status + health
calseta://agents/{uuid}         — Agent detail: config, budget, capabilities, session state, recent runs
calseta://agents/topology       — Full fleet topology: nodes (agents), edges (routing + delegation paths)
calseta://queue                 — Current alert queue state: pending, in-progress, pending-review counts + items
calseta://issues/{uuid}         — Issue detail: description, status, comments, linked alert/KB pages
calseta://kb                    — KB page index: folder tree, page list, inject_scope badges, sync status
calseta://routines              — Routine list with last-run status, next scheduled time, trigger type
```

**`calseta://agents` response shape:**
```json
{
  "agents": [
    {
      "uuid": "...",
      "name": "Triage Orchestrator",
      "agent_type": "orchestrator",
      "role": "triage",
      "status": "running",
      "last_heartbeat_at": "2026-04-03T10:22:00Z",
      "budget_monthly_cents": 50000,
      "spent_monthly_cents": 17200,
      "current_assignments": 2
    }
  ]
}
```

**`calseta://agents/{uuid}` response shape:**
```json
{
  "uuid": "...",
  "name": "...",
  "agent_type": "orchestrator",
  "role": "triage",
  "status": "running",
  "llm_integration": {"provider": "anthropic", "model": "claude-opus-4-6"},
  "capabilities": [],
  "budget": {"monthly_cents": 50000, "spent_cents": 17200, "period_start": "2026-04-01"},
  "active_sessions": 2,
  "last_heartbeat_at": "2026-04-03T10:22:00Z",
  "session_state": {"task_key": "alert:uuid", "heartbeat_count": 4, "total_tokens": 22400}
}
```

**`calseta://agents/topology` response shape:**
```json
{
  "nodes": [
    {"uuid": "...", "name": "Triage Orchestrator", "role": "triage", "status": "running", "type": "orchestrator"},
    {"uuid": "...", "name": "Identity Specialist", "role": "identity", "status": "idle", "type": "specialist"}
  ],
  "edges": [
    {"from": "orchestrator-uuid", "to": "specialist-uuid", "type": "delegation", "invocations_30d": 142},
    {"from": "routing-rule", "to": "orchestrator-uuid", "type": "routing", "label": "severity:high"}
  ]
}
```

**`calseta://queue` response shape:**
```json
{
  "summary": {"pending": 12, "in_progress": 4, "pending_review": 2},
  "items": [
    {"alert_uuid": "...", "title": "...", "severity": "High", "queued_at": "...", "assigned_agent": null}
  ]
}
```

**`calseta://metrics/summary` extended fields (types + formulas):**

| Field | Type | Calculation |
| --- | --- | --- |
| `cost_per_alert` | `float` (cents) | `SUM(cost_cents) / COUNT(DISTINCT alert_id)` over resolved assignments in period |
| `auto_resolve_rate` | `float` (0.0–1.0) | `COUNT(assignments resolved by agent, no human action) / COUNT(all resolved)` |
| `agent_utilization` | `dict[agent_uuid, float]` | `SUM(time in running status) / SUM(total active period)` per agent |
| `tool_call_success_rate` | `float` (0.0–1.0) | `COUNT(agent_actions where status != error) / COUNT(all agent_actions)` |
| `investigation_abandonment_rate` | `float` (0.0–1.0) | `COUNT(assignments with status timed_out or force_closed) / COUNT(all assignments)` |

### Key Tool Parameter Specs `[Part 1+]`

**`checkout_alert`** — Atomically claim an alert from the queue.
```
Input:
  alert_id: string (UUID) — required
  assignment_note: string — optional, stored in assignment
Output:
  assignment_id: string (UUID)
  alert: {uuid, title, severity, occurred_at, status, indicators, enrichments, detection_rule}
  session: {task_key, heartbeat_count, session_exists: bool}
Errors:
  409 — alert already claimed by another agent
  404 — alert not found or not in queue
```

**`propose_action`** — Propose a response action requiring approval or auto-execution.
```
Input:
  assignment_id: string (UUID) — required
  action_type: enum (containment|remediation|notification|enrichment|escalation) — required
  action_subtype: string — required (e.g., "block_ip", "disable_user", "send_slack")
  payload: object — required, action-type-specific fields
  confidence: float (0.0–1.0) — required, drives approval threshold override
  reasoning: string — required, human-readable explanation shown in approval inbox
Output (approval required):
  action_id: string (UUID)
  status: "pending_approval"
  approval_request_uuid: string (UUID)
  expires_at: datetime
Output (auto-approved):
  action_id: string (UUID)
  status: "executing"
```

**`delegate_task`** — Invoke a specialist sub-agent (orchestrators only).
```
Input:
  child_agent_id: string (UUID) — required
  alert_id: string (UUID) — required
  assignment_id: string (UUID) — required
  task_description: string — required, plain-language task for the specialist
  input_context: object — optional, structured data passed to specialist
Output:
  invocation_id: string (UUID)
  status: "queued"
  child_agent_name: string
  estimated_wait_ms: int — queue depth estimate
```

**`delegate_parallel`** — Invoke multiple specialists simultaneously (orchestrators only).
```
Input:
  alert_id: string (UUID) — required
  assignment_id: string (UUID) — required
  tasks: array of {child_agent_id, task_description, input_context} — required, 2–10 items
Output:
  invocations: array of {invocation_id, child_agent_name, status}
  fan_out_count: int
```

**`search_kb`** — Search KB pages by keyword or semantic query.
```
Input:
  query: string — required, keyword or natural language search query
  mode: enum (keyword|semantic) — optional, default "keyword"
  folder: string — optional, restrict to folder path prefix (e.g., "runbooks/identity")
  inject_scope: enum (global|role|agent|all) — optional, filter by injection scope
  limit: int — optional, default 10, max 50
Output:
  pages: array of {slug, title, folder, summary, inject_scope, relevance_score}
  total_matched: int
Note: semantic mode requires a vector embedding backend (Phase 8+). In Phases 3–7, mode is
      silently normalized to "keyword" if semantic is unavailable.
```

**`create_issue`** — Create a follow-up work item from an investigation.
```
Input:
  title: string — required
  description: string — required
  category: enum (remediation|detection_tuning|post_incident|compliance|investigation|maintenance) — required
  priority: enum (low|medium|high|critical) — required
  alert_id: string (UUID) — optional, link to source alert
  assignment_id: string (UUID) — optional, link to source assignment
Output:
  issue_id: string (UUID)
  issue_number: int — human-readable display number (e.g., ISS-0042)
  status: "backlog"
```

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
- As a compliance officer, I want a full audit trail of every agent action — including the full delegation chain — so that I can demonstrate due diligence in alert investigations and response actions.
- As a security engineer, I want to start with Calseta's reference agents and customize them for my environment so that I'm not building from scratch.
- As a SOC lead, I want to manage non-alert work (remediation tasks, detection tuning, post-investigation follow-ups) alongside alert investigations so that nothing falls through the cracks.
- As a security engineer, I want to schedule agents on cron triggers (daily threat intel triage, weekly FP rate review) so that recurring work happens automatically without manual invocation.
- As a SOC operator, I want an internal knowledge base where investigation findings, runbooks, and institutional knowledge are searchable and browsable so that agents and humans can reference the same source of truth.
- As a security engineer, I want to inject KB pages as context into specific agents or roles so that agents always have the latest runbooks without manual prompt editing.
- As a security engineer, I want to sync KB pages from our existing Confluence/GitHub docs so that Calseta is a read-only mirror of our canonical knowledge.
- As a SOC lead, I want to see an agent topology view (routing paths, delegation map, capability overview) so that I understand how my agent fleet is wired together at a glance.
- As a security manager, I want to define investigation campaigns with target metrics (MTTD, FP rate, auto-resolve rate) and monitor auto-computed progress so that operational work ties back to strategic objectives without manual data entry.
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

- As a security manager, I want Calseta to automatically compute campaign metrics from alert and assignment data so that I never manually enter metric values and always have accurate, up-to-date progress.
- As a security engineer, I want to sync KB pages from external sources (GitHub, Confluence, URL) on a configurable schedule so that agent runbooks stay synchronized with our canonical documentation automatically.
- As an agent developer, I want to promote persistent memory insights to shared memory so that other agents can benefit from cross-alert patterns and institutional knowledge I've discovered.
- As a SOC lead, I want to visualize my agent fleet topology (orchestrators, specialists, routing paths, delegation chains) so that I understand how my agents are wired together and where bottlenecks might occur.
- As an agent developer, I want memory entries to be automatically marked stale after a TTL or when their source data changes so that my agent doesn't act on outdated learned context.
- As an agent developer, I want to choose whether my agent uses push webhooks or pulls from Calseta's alert queue so that I can integrate using the model that best fits my architecture.

### Platform Stories

- As a Calseta contributor, I want the control plane to use the same plugin pattern as enrichment providers so that adding new action integrations follows a familiar pattern.
- As a Calseta user, I want the control plane to be optional so that I can still use Calseta as a pure data layer if I don't need orchestration.
- As a Calseta user, I want to choose between BYO agents (Option A) and Calseta-managed agents (Option B) depending on my needs.

---

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

