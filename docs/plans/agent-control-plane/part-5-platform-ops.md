# Part 5: Platform Operations (Auth, Secrets, UI)

> **Split PRD navigation:**
> [Overview](_overview.md) | [Part 1: Core Runtime](part-1-core-runtime.md) | [Part 2: Actions & Orchestration](part-2-actions-orchestration.md) | [Part 3: Knowledge & Memory](part-3-knowledge-memory.md) | [Part 4: Operational](part-4-operational.md) | [Part 5: Platform Ops](part-5-platform-ops.md) | [API & MCP](appendix-api-mcp.md) | [Implementation Phases](implementation-phases.md)

# Part 5: Platform Operations (Auth, Secrets, UI)

> **Dependencies:** Part 1 (Core Runtime)
> **Implementation:** Phase 1 (Secrets, Auth), Phase 6.5 (UI)

---

### Data Model

#### `secrets` (NEW)

Instance-level encrypted secret storage with versioning.


| Column           | Type        | Notes                                                                                                 |
| ---------------- | ----------- | ----------------------------------------------------------------------------------------------------- |
| `id`             | uuid        | PK                                                                                                    |
| `name`           | text        | NOT NULL, UNIQUE — human label ("anthropic_api_key", "confluence_token", "crowdstrike_client_secret") |
| `description`    | text        | NULL                                                                                                  |
| `provider`       | enum        | `local_encrypted` (default), `env_var`, `aws_secrets_manager`, `vault`                                |
| `external_ref`   | text        | NULL — reference for external providers (env var name, ARN, Vault path)                               |
| `latest_version` | int         | NOT NULL, default 1                                                                                   |
| `created_at`     | timestamptz | NOT NULL                                                                                              |
| `updated_at`     | timestamptz | NOT NULL                                                                                              |


#### `secret_versions` (NEW)


| Column         | Type        | Notes                                                                                                       |
| -------------- | ----------- | ----------------------------------------------------------------------------------------------------------- |
| `id`           | uuid        | PK                                                                                                          |
| `secret_id`    | uuid        | FK `secrets.id`, NOT NULL                                                                                   |
| `version`      | int         | NOT NULL                                                                                                    |
| `material`     | jsonb       | NOT NULL — encrypted payload (for `local_encrypted` provider). Contains `{ ciphertext, nonce, algorithm }`. |
| `value_sha256` | text        | NOT NULL — hash of plaintext for integrity verification                                                     |
| `revoked_at`   | timestamptz | NULL — NULL = active, non-NULL = revoked                                                                    |
| `created_at`   | timestamptz | NOT NULL                                                                                                    |


---

### Auth and Permissions (Extended)

> [!note] This section extends the existing Auth and Permissions section with human login, API token self-service, run-scoped JWTs, and enhanced agent auth.
>
> **Paperclip ref:** `/server/src/auth/better-auth.ts` (human auth), `/server/src/agent-auth-jwt.ts` (agent JWTs), `/server/src/services/access.ts` (permissions), `/packages/db/src/schema/agent_api_keys.ts` (API keys)

#### Human Operator Auth (NEW)

Calseta v2 introduces a web UI that humans log into. Authentication for the operator UI uses **BetterAuth** — the same library already in Calseta's v1 architecture (BetterAuth-ready, per `CLAUDE.md`).

**Login methods:**
- Email + password (default, always available)
- OAuth providers: Google, GitHub, Microsoft (configurable via env vars)

**Session management:**
- Sessions backed by PostgreSQL session table (via BetterAuth's database adapter)
- Session cookie: `calseta_session` (HTTP-only, Secure, SameSite=Strict)
- Session TTL: 24 hours (configurable via `SESSION_TTL_HOURS` env var)
- Every API call from UI attaches session cookie; backend validates and extracts operator identity

**Operator API token self-service:**
Logged-in operators can generate their own long-lived API tokens from the UI settings page (`/control-plane/settings/api-tokens`):

```
POST   /api/v1/operator/tokens           Create operator API token (scope selection, name label)
GET    /api/v1/operator/tokens           List my tokens (names + prefixes only, no values)
DELETE /api/v1/operator/tokens/{id}      Revoke token
```

Token format: `calseta_op_{random_32_char_urlsafe_string}` (same pattern as v1 `cai_` keys but with `calseta_op_` prefix). Shown once at creation. Stored as bcrypt hash.

**Initial operator seeding:**
A `CALSETA_ADMIN_EMAIL` + `CALSETA_ADMIN_PASSWORD` env var pair seeds the first operator account at startup (or first-run setup wizard). All subsequent operators are added via the UI or `POST /api/v1/operator/users` endpoint (admin-only).

**Operator scopes (unchanged from v1, extended for control plane):**
`agents:read`, `agents:write`, `alerts:read`, `alerts:write`, `enrichments:read`, `workflows:read`, `workflows:execute`, `approvals:write`, `admin` — plus new control plane scopes: `queue:read`, `queue:write`, `costs:read`, `kb:read`, `kb:write`, `issues:read`, `issues:write`, `routines:read`, `routines:write`, `secrets:read`, `secrets:write`, `topology:read`.

#### Operator Auth

New agent-specific API keys (separate from operator API keys). Bearer token in `Authorization: Bearer calseta_agent_...` header. Scoped to one agent registration. This is the **inbound** auth (agent calling Calseta), distinct from the existing **outbound** auth (`auth_header_name` / `auth_header_value_encrypted` used when Calseta pushes TO agents).

**Permission matrix (basic):**


| Action                        | Operator | Agent                                            |
| ----------------------------- | -------- | ------------------------------------------------ |
| Create/manage agents          | Yes      | No                                               |
| Pause/resume/terminate agents | Yes      | No                                               |
| Checkout alert from queue     | Yes      | Yes (own queue only)                             |
| Release alert                 | Yes      | Yes (own assignments only)                       |
| Propose action                | Yes      | Yes                                              |
| Approve/reject action         | Yes      | No                                               |
| Report cost event             | Yes      | Yes (own agent only)                             |
| Delegate to sub-agent         | No       | Yes (orchestrators only, within `sub_agent_ids`) |
| Read sub-agent catalog        | Yes      | Yes (orchestrators only)                         |
| Set budget                    | Yes      | No                                               |
| Manage LLM integrations       | Yes      | No                                               |
| View dashboard                | Yes      | No                                               |
| View activity log             | Yes      | No                                               |
| Read alerts (enriched)        | Yes      | Yes (checked-out or matching filter)             |
| Read context documents        | Yes      | Yes                                              |
| Read workflows                | Yes      | Yes                                              |


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


| Action                        | Operator | Agent (External, API Key) | Agent (Managed, JWT)       |
| ----------------------------- | -------- | ------------------------- | -------------------------- |
| Create/manage agents          | Yes      | No                        | No                         |
| Pause/resume/terminate agents | Yes      | No                        | No                         |
| Checkout alert from queue     | Yes      | Yes (own queue)           | Yes (own queue)            |
| Release alert                 | Yes      | Yes (own assignments)     | Yes (own assignments)      |
| Propose action                | Yes      | Yes                       | Yes                        |
| Approve/reject action         | Yes      | No                        | No                         |
| Report cost event             | Yes      | Yes (own agent)           | Automatic (runtime tracks) |
| Delegate to sub-agent         | No       | Yes (orchestrators)       | Yes (orchestrators)        |
| Read sub-agent catalog        | Yes      | Yes (orchestrators)       | Yes (orchestrators)        |
| Set budget                    | Yes      | No                        | No                         |
| Manage LLM integrations       | Yes      | No                        | No                         |
| Manage secrets                | Yes      | No                        | No                         |
| View dashboard                | Yes      | No                        | No                         |
| View activity log             | Yes      | No                        | No                         |
| Read KB pages                 | Yes      | Yes                       | Yes                        |
| Write KB pages                | Yes      | Yes (if permitted)        | Yes                        |
| Write memory                  | N/A      | Yes (own memory)          | Yes (own memory)           |
| Create issues                 | Yes      | Yes                       | Yes                        |
| Manage routines               | Yes      | No                        | No                         |
| Read topology                 | Yes      | Yes                       | Yes                        |


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

### Platform Settings

All configurable platform behaviors are stored in a `platform_settings` table (key-value store with JSONB values), managed via the settings UI and API. This ensures settings are changeable at runtime without deployments.

```
GET    /api/v1/settings                    Get all settings (admin only)
PATCH  /api/v1/settings/{key}              Update a setting (admin only)
```

Settings categories: `user_validation` (campaign guardrails, template config), `agent_runtime` (default token budgets, supervision intervals), `kb_sync` (default sync interval, max page size), `approval` (default approval modes, expiry times), `cost` (budget alert thresholds).

---

### Platform Metrics (Agentic Work)

The existing metrics system (`GET /api/v1/metrics/summary` in v1) is extended with control plane metrics. These are computed from the `cost_events`, `alert_assignments`, `heartbeat_runs`, `agent_actions`, and `agent_issues` tables — no new tables needed.

#### New Metrics

| Metric | Calculation | Surface |
| --- | --- | --- |
| **Cost per alert** | `SUM(cost_cents) / COUNT(resolved assignments)` — total agent spend divided by alerts resolved | Dashboard, Cost page |
| **Auto-resolve rate** | `COUNT(assignments resolved by agent without human action) / COUNT(all resolved)` | Dashboard |
| **Agent utilization rate** | `SUM(time in running state) / SUM(total active time)` per agent | Agent detail |
| **MTTTR (agent-assisted)** | `AVG(completed_at - checked_out_at)` for agent-handled assignments | Dashboard |
| **Tool call success rate** | `COUNT(tool calls returning non-error) / COUNT(total tool calls)` per agent and tool | Agent detail, Tool registry |
| **Investigation abandonment rate** | `COUNT(assignments timed_out or force_closed) / COUNT(all assignments)` | Dashboard |
| **Escalation rate** | `COUNT(actions requiring approval) / COUNT(all proposed actions)` | Actions page |
| **Agent failure rate** | `COUNT(heartbeat_runs with status=error) / COUNT(all runs)` per agent | Agent detail |
| **Sub-agent result quality** | `COUNT(invocations returning actionable findings) / COUNT(all invocations)` per specialist | Agent detail |
| **Cost by LLM model** | `SUM(cost_cents) GROUP BY model` | Cost dashboard |
| **Approval decision time** | `AVG(responded_at - created_at)` for approved/rejected `WorkflowApprovalRequests` | Approvals page |
| **User validation response rate** | `COUNT(acknowledged + denied) / COUNT(sent)` per template | User Validation settings |

#### MCP Resource Extension

```
calseta://metrics/summary       — Extended with: cost_per_alert, auto_resolve_rate, agent_utilization, 
                                  tool_call_success_rate, investigation_abandonment_rate
calseta://metrics/agents        — Per-agent metrics: utilization, failure rate, cost, MTTTR
calseta://metrics/costs         — Cost breakdown by agent, model, alert
```

---

### Operator UI

New pages in Calseta's web UI (or new UI if Calseta doesn't have one yet — this would be the first major UI surface).

> [!important] UI is Top-Tier Priority
> The operator UI is the primary way security teams interact with the control plane. Every new feature introduced in this PRD needs a well-designed UI surface. A dedicated working session is required to spec every page, component, interaction, and data visualization in detail before implementation begins. The UI should be enterprise-grade — this is a security product used by SOC teams in high-pressure situations. Clarity, speed, and information density matter more than aesthetics.

#### Pages


| Route                                                 | Purpose                                                                                                                                                                       | Part                         | New?     |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------- | -------- |
| `/control-plane`                                      | Dashboard — agent status, queue depth, pending approvals, costs, key metrics                                                                                                  | All                          | Original |
| `/control-plane/agents`                               | Agent registry — list orchestrators + specialists, create, configure, pause/resume                                                                                            | [Part 1]                     | Original |
| `/control-plane/agents/new`                           | Create agent — choose type (orchestrator/specialist), assign LLM, configure capabilities                                                                                      | [Part 1]                     | Original |
| `/control-plane/agents/{id}`                          | Agent detail — config, heartbeat history, cost breakdown, assigned alerts/issues, sub-agent invocations, **session state**, **memory entries**, **PM view (tasks by status)** | [Part 1], [Part 3], [Part 4] | Enhanced |
| `/control-plane/agents/{id}/investigation/{alert_id}` | Investigation view — full tree of sub-agent invocations, findings, reasoning chain                                                                                            | [Part 2]                     | Original |
| `/control-plane/topology`                             | **Agent topology** — interactive graph of agent fleet: routing paths, delegation paths, capability map, health status                                                         | [Part 4]                     | **NEW**  |
| `/control-plane/queue`                                | Alert queue — pending alerts, assignments, routing rules, status filters                                                                                                      | [Part 1]                     | Original |
| `/control-plane/issues`                               | **Issue board** — non-alert work items by status (backlog/todo/in_progress/done), filterable by category, assignee, priority, linked alert                                    | [Part 4]                     | **NEW**  |
| `/control-plane/issues/{id}`                          | **Issue detail** — description, comments, linked alerts/KB pages, history, assignee, checkout status                                                                          | [Part 4]                     | **NEW**  |
| `/control-plane/actions`                              | Action feed — proposed, pending approval, approved, executed, failed                                                                                                          | [Part 2]                     | Original |
| `/control-plane/approvals`                            | Approval inbox — extends existing `/v1/workflow-approvals` with response action context                                                                                       | [Part 2]                     | Original |
| `/kb`                                                 | **Knowledge base** — top-level SOC wiki: folder tree, page list, search (Cmd+K), sync status. Primary destination for operators AND agents. Not scoped under /control-plane. | [Part 3]                     | **NEW**  |
| `/kb/{slug}`                                          | **KB page detail** — rendered markdown, revision history, linked entities, injection scope badges, sync status, agent usage indicator (which agents inject this page)         | [Part 3]                     | **NEW**  |
| `/kb/{slug}/edit`                                     | **KB page editor** — markdown editor (Tiptap), injection scope picker, sync config, token count, @ mentions                                                                   | [Part 3]                     | **NEW**  |
| `/control-plane/routines`                             | **Routines** — scheduled/recurring agent tasks with cron config, trigger history, run status                                                                                  | [Part 4]                     | **NEW**  |
| `/control-plane/routines/{id}`                        | **Routine detail** — trigger config, run history, linked issues, concurrency policy, failure tracking                                                                         | [Part 4]                     | **NEW**  |
| `/control-plane/campaigns`                            | **Campaigns** — strategic objectives with target metrics, progress tracking, linked items                                                                                     | [Part 4]                     | **NEW**  |
| `/control-plane/campaigns/{id}`                       | **Campaign detail** — metric history chart, linked alerts/issues/routines, progress toward target                                                                             | [Part 4]                     | **NEW**  |
| `/control-plane/costs`                                | Cost dashboard — spend by agent, by LLM integration, by alert, budget utilization, **budget policy management**                                                               | [Part 1]                     | Enhanced |
| `/control-plane/activity`                             | Audit log — searchable, filterable activity stream                                                                                                                            | [Part 1]                     | Original |
| `/control-plane/settings/llm`                         | LLM integrations — register providers, manage API keys, view per-model costs                                                                                                  | [Part 1]                     | Original |
| `/control-plane/settings/integrations`                | Action integrations — per-integration approval modes, config, documentation links                                                                                             | [Part 2]                     | Original |
| `/control-plane/settings/secrets`                     | **Secrets management** — create/rotate/revoke secrets, view usage references, provider config                                                                                 | [Part 5]                     | **NEW**  |
| `/control-plane/settings/instructions`                | **Global instruction files** — instance-wide instructions applied to all agents (or role-scoped). Create, edit, reorder, activate/deactivate.                                 | [Part 1]                     | **NEW**  |
| `/control-plane/settings/user-validation`             | **User validation** — rules, templates, and campaign guardrails (all DB-driven, changeable at runtime)                                                                        | [Part 2]                     | **NEW**  |
| `/control-plane/settings/kb-sync`                     | **KB sync settings** — global sync interval, enable/disable sync globally, per-source credential references. Also accessible from within `/kb` page editor sidebar.           | [Part 3]                     | **NEW**  |
| `/control-plane/settings/api-tokens`                  | **Operator API tokens** — self-service token generation, scope selection, revocation                                                                                           | [Part 5]                     | **NEW**  |


#### Key UX Patterns

- **Approval inbox as primary surface** — the most important page for SOC operators. Show proposed action, agent's reasoning, alert context, enrichment data, and one-click approve/reject.
- **Queue visibility** — see unassigned alerts, who's working what, how long alerts have been waiting.
- **Agent health at a glance** — status indicators (running/idle/paused/error), last heartbeat, current workload, budget utilization.
- **Progressive disclosure** — top layer: human-readable summary. Middle: action details and enrichment. Bottom: raw agent logs and API calls.
- **Slack/webhook notifications** — pending approvals push to Slack so operators don't need to watch the UI.
- **Agent detail as command center** — the agent detail page is the most complex page. It needs tabs/sections for: Config, Heartbeat History (with log viewer), Assigned Work (alerts + issues by status — the PM view), Sessions, Memory, Cost Breakdown, Delegation History (orchestrators), Capability Declarations (specialists).
- **KB as top-level SOC wiki** — first-class nav destination at `/kb`, not buried in control-plane. This is the SOC's knowledge repository that *also* powers agentic context injection — operators use it to write and read runbooks daily; agents read it on every invocation. Folder tree nav on the left, rendered markdown on the right, edit button, revision history drawer. Pages show injection scope badges (global, role:X, agent:Y) and sync status indicators (local, synced from GitHub, synced from Confluence). "Agent usage" indicator on each page shows which agents currently inject it.
- **Topology as situational awareness** — interactive DAG/graph visualization. Nodes are agents with status badges. Edges show alert routing and delegation paths. Click a node to navigate to agent detail. Color-coding by status (green=idle, blue=running, yellow=paused, red=error).
- **Issue board for non-alert work** — filterable list or kanban view. Categories as swimlanes or tabs. Link to originating alert or routine. This is where remediation tasks, detection tuning, and follow-ups live.
- **Routine dashboard** — list of routines with last run status, next scheduled run, trigger type icon (clock for cron, webhook icon, hand for manual). Drill into run history with pass/fail indicators.

#### Page Detail Specs

> [!note] Implementation Reference
> All pages extend the existing Calseta React 19 + Vite UI. Design tokens, component library, spacing, and interaction patterns are documented in `ui/DESIGN_SYSTEM.md`. Engineering patterns (routing, API hooks, types) are in `ui/UI_ENGINEERING.md`. Read both before building any page.
>
> Legend: `→ extends` = start from existing Calseta page; `→ new` = no Calseta equivalent; `⚠ open question` = Jorge decision needed before implementation (see **Open Questions** at end of this section)

---

##### `/agents` — Agent Control Plane Hub (tabbed)

**Decision: `/manage/agents` evolves into `/agents` — the Control Plane hub.** The existing `/` dashboard stays as the SOC metrics dashboard (alert throughput, enrichment coverage, workflow stats). `/agents` is the agent fleet command center.

`→ extends` existing `/manage/agents` (`pages/settings/agents/index.tsx`), promoted to a top-level tabbed hub.

**Route:** `/agents` (replaces `/manage/agents` — retire that route with a redirect)

**Tab bar** (consistent with existing Calseta tab style — `bg-surface border border-border`, active: `data-[state=active]:bg-teal/15 data-[state=active]:text-teal-light`):

| Tab | Icon | Route param | Default? |
|-----|------|-------------|---------|
| Fleet | `Bot` | `?tab=fleet` | Yes |
| Queue | `Inbox` | `?tab=queue` | |
| Issues | `LayoutList` | `?tab=issues` | |
| Topology | `Network` | `?tab=topology` | |
| Actions | `Zap` | `?tab=actions` | |
| Costs | `DollarSign` | `?tab=costs` | |
| Activity | `Clock` | `?tab=activity` | |

Tab state persisted in URL via `validateSearch` — same pattern as all existing Calseta detail pages.

**Top stat bar (above tabs, always visible):** agent fleet health (total / running / paused / error), queue depth, pending approvals count, MTD cost. These four numbers orient the operator before they drill into any tab. Use `DetailPageStatusCards` pattern — 4 cards, compact.

**Real-time (SSE — Q6 confirmed):** `EventSource('/api/v1/events/stream')` pushes `agent.status_changed`, `approval.created`, `approval.expired`, `queue.updated`. On each event, invalidate the relevant React Query key — no polling needed for these four. See Decisions Log.

**Empty state (Fleet tab, no agents):** centered — `Bot h-12 w-12 text-dim`, "No agents registered", "Register your first agent" → opens create flow.

---

###### Fleet Tab — Agent Registry

`→ extends` existing agents table, same `ResizableTable` + `useTableState` pattern.

**New columns vs. current `/manage/agents`:**

| Column | Notes |
|--------|-------|
| Type | `orchestrator` / `specialist` / `external` badge — `text-teal`, `text-amber`, `text-dim` |
| LLM Provider | `provider:model` label or "External" (dim) |
| Status | `running` / `idle` / `paused` / `error` with pulsing dot for `running` — outer `span animate-ping`, inner solid dot |
| Last Heartbeat | `relativeTime()` — `text-red-threat` if > 5 min stale |
| Budget | mini progress bar: `bg-teal` → `bg-amber` at 75% → `bg-red-threat` at 90% |

**Header:** Refresh button + agent count (left) + "+ Register Agent" button (right, `size="sm" className="bg-teal text-white hover:bg-teal-dim"`).

**Create flow:** "+ Register Agent" → always navigates to `/agents/new` full stepped page. No dialog — all agent types (external BYO and managed) use the same registration flow.

**Actions column:** Pause / Resume / Terminate lifecycle buttons + Delete (external agents only).

---

##### `/agents/new` — Create Agent

`→ new` (no Calseta equivalent — existing create flows are dialogs, this is the first stepped page)

**Pattern:** Multi-step full page. `DetailPageLayout` with sidebar showing step progress nav.

**Steps (sidebar, active step `bg-teal/15 text-teal-light`):**
1. Type & Identity — name, description, `agent_type`, `execution_mode`
2. LLM Provider — select from `GET /api/v1/llm-integrations`, optional model override
3. System Prompt & Instructions — `TiptapEditor` + instruction file selector
4. Tools & Capabilities — toggle group for tool tiers; capability declarations (specialist only)
5. Triggers & Budget — reuse `TargetingRuleBuilder`; budget limit inputs
6. Review & Save

Back / Next at page bottom. Validate before advancing. Cancel → `/agents?tab=fleet`.

---

##### `/agents/{id}` — Agent Detail

`→ extends` existing `/manage/agents/{uuid}` (`pages/settings/agents/detail.tsx`)

**Status cards (top row):** Status (inline `Select`: idle/running/paused/error), LLM Provider, Last Heartbeat (`relativeTime()`), MTD Cost / Budget.

**New tabs added to existing Config + Activity tabs:**

| Tab | Icon | Content |
|-----|------|---------|
| Config | `Settings` | Existing fields + new CP fields (system prompt, tools, LLM assignment, capabilities) |
| PM View | `LayoutList` | Assigned alerts + issues by status — agent's current workload |
| Heartbeats | `Activity` | Table: start time, duration, status, alert count, cost. Row click → `Sheet` log viewer |
| Sessions | `Terminal` | Active + recent task sessions: session_id, type, status, started/ended, token usage |
| Cost | `DollarSign` | Spend by model, `AreaChart` over time (recharts), budget policy status |
| Delegation | `GitBranch` | Orchestrators only: sub-agent invocations with per-step status + result summary |
| Capabilities | `Zap` | Specialists only: declared capability list |

**Heartbeat log viewer:** right-side `Sheet`, `ScrollArea` monospace font, copy-to-clipboard `CopyableText` button.

**PM View:** for each alert: `Badge` (status color) + alert title `Link` to `/alerts/{uuid}` + severity badge + `relativeTime()`. Issues: category badge + title.

---

##### `/agents/{id}/investigation/{alert_id}` — Investigation Tree

`→ new` **Decision: @xyflow/react flow diagram** (same library as topology page — one dep, two uses)

**Purpose:** Full orchestration chain for one alert — orchestrator → specialist invocations → findings → proposed actions, with cost + timing per step.

**Node types:**
- Orchestrator run node (root): large card — agent name, alert title, total duration, total cost
- Invocation node (children): medium card — agent name, task description, status badge, duration, token count
- Finding node: small card — finding summary, confidence score, `text-teal-light`
- Action proposal node: medium card — action type badge, payload summary, approval status

**Edges:** labeled directed arrows — "invoked" (orchestrator→specialist), "produced" (invocation→finding), "proposed" (invocation→action)

**Node status colors:** same token mapping as topology page.

**Click node → right `Sheet`:** full log output in `ScrollArea` monospace, copy button, token breakdown.

**Layout algorithm:** top-down dagre layout (`@dagrejs/dagre`, commonly used with @xyflow). Root at top, children expand downward.

**Controls:** fit-to-screen, zoom in/out (React Flow built-in controls, styled `bg-surface border-border`).

> Since topology (`/control-plane/topology`) also uses `@xyflow/react`, both pages share one dependency. Build investigation tree and topology in the same sprint.

---

###### Topology Tab — Agent Fleet Graph

`→ new` — Library: `@xyflow/react` (React Flow). Add as dependency.

**Node types:**
- Orchestrator: 200×80px card, status dot, name, current alert count
- Specialist: 160×60px card, status dot, name, role label

**Status colors** (Calseta design tokens):
| Status | Classes |
|--------|---------|
| `idle` | `bg-teal/15 border-teal/30 text-teal-light` |
| `running` | `bg-teal border-teal text-white animate-pulse` |
| `paused` | `bg-amber/15 border-amber/30 text-amber` |
| `error` | `bg-red-threat/15 border-red-threat/30 text-red-threat` |
| `terminated` | `bg-dim/10 border-dim/30 text-dim` |

**Interactions:**
- Click node → navigate to `/control-plane/agents/{id}`
- Hover → tooltip: last heartbeat, workload, budget %
- Minimap: styled `bg-surface border-border`
- Fit-to-screen button: `Expand` icon, `variant="ghost" size="sm"` (top-left controls)

**Edge labels:** "dispatches alerts" (Calseta → orchestrators), "delegates" (orchestrator → specialist).

**Empty state:** "No agents registered" + create link.

---

###### Queue Tab — Alert Queue

`→ new` (pattern: extends alert list — `pages/alerts/index.tsx`)

**Same `ResizableTable` + `useTableState` pattern.** Additional columns:

| Column | Notes |
|--------|-------|
| Assigned To | Agent name badge or "Unassigned" (dim) |
| Queue Status | `pending` / `checked_out` / `pending_review` / `resolved` badge |
| Wait Time | `formatSeconds(seconds_in_queue)` — `text-red-threat` if > 30 min |
| Checkout | Agent name + `relativeTime()` of checkout, or "—" |

**Filter bar (toggle button groups):** Queue status, severity, source, "Unassigned only" switch.

**Row actions:** Manual assign (operator override), release back to queue (if checked out), link to alert detail.

---

###### Actions Tab — Action Feed

`→ new` (pattern: similar to `/approvals` — `pages/workflows/approvals.tsx`)

**Table columns:** Action Type badge, Subtype, Agent (link), Alert (link), Status badge, Confidence %, Proposed At (`relativeTime()`), Approved By.

**Status badge classes:**
| Status | Classes |
|--------|---------|
| `pending_approval` | `text-amber bg-amber/10 border-amber/30` |
| `approved` | `text-teal bg-teal/10 border-teal/30` |
| `executing` | `text-teal-light bg-teal-light/10 border-teal-light/30` + pulsing dot |
| `completed` | `text-dim bg-dim/10 border-dim/30` |
| `rejected` | `text-red-threat bg-red-threat/10 border-red-threat/30` |
| `failed` | `text-red-threat bg-red-threat/10 border-red-threat/30` |

**Row click:** opens right `Sheet` with full reasoning, payload, alert context, enrichment summary, approval timeline, execution result.

---

##### `/approvals` — Approval Inbox (standalone page)

`→ extends` existing `/approvals` (`pages/workflows/approvals.tsx`) — **priority #1 page**

**New fields vs. existing workflow approvals:**
- Action type + subtype (e.g., "containment: block_ip")
- Payload preview: specific values being acted on (IP, user, host)
- Agent reasoning (full text, expandable `Collapsible`)
- Confidence score badge: `text-teal` > 85%, `text-amber` 60–85%, `text-red-threat` < 60%
- Alert context summary: severity + status + top enrichment hits
- Approve / Reject / Defer — same 3-button pattern

**Sort:** `expires_at` ascending (soonest first). `text-red-threat` countdown badge when < 5 min remaining.

---

##### `/kb` — Knowledge Base Browser

`→ new` (reference: Cabinet `sidebar/tree-view.tsx` pattern, adapted to Calseta tokens. Note: Calseta `/manage/context-docs` is the simpler predecessor.)

**Layout:** 3-panel full-height (no `AppLayout` top padding on this page):
- Left panel (280px fixed): folder tree + search input
- Center (flex-1): page list (default) or rendered page
- Right panel (320px, conditional): injection scope editor, revision history drawer

**Folder tree (left panel):**
- `GET /api/v1/kb/folders` → recursive `{ name, path, page_count, children }`
- Node: `ChevronRight` (rotates 90° when open) + `Folder`/`FolderOpen` icon + name + `text-xs text-dim` count
- Active folder: `bg-teal/15 text-teal-light`
- "New Page" on hover: `Plus h-3 w-3`, `variant="ghost" size="xs"`
- `⋯` context menu: Add Sub Folder, Rename, Delete (blocked if not empty)
- Depth indentation: `paddingLeft: ${depth * 16 + 12}px`

**Cmd+K search:** `Dialog`, 200ms debounce, results grouped by folder, keyboard arrow nav, Enter → navigate.

**Page list (center):** Title (`Link`), Folder path (dim), Last Updated (`relativeTime()`), Status badge, Sync source icon. Injection scope chips inline in row.

---

##### `/kb/{slug}` — KB Page Detail

`→ new` (pattern: `DetailPageLayout` — like context-doc detail, extended)

**Main area:** `MarkdownPreview` (existing `components/markdown-preview.tsx`). Edit button → `/kb/{slug}/edit`.

**Sidebar sections:**
- Details: slug (`CopyableText`), status badge, created/updated, token count estimate
- Injection Scope: global toggle + role chips + agent chips (read-only; edit via `/edit`)
- Sync Status: source badge, last synced (`relativeTime()`), "Sync Now" button
- Agent Usage: agents currently injecting this page (name + link)
- Linked Entities: alerts / issues / agents that mention this page

**Revision History `Sheet` (right side, triggered by button):** revision list → side-by-side diff view → "Restore" button creates new revision.

---

##### `/kb/{slug}/edit` — KB Page Editor

`→ new` **Decision: Tiptap WYSIWYG** (reference: Cabinet `editor.tsx`, `editor-toolbar.tsx`)

**New dependency:** `@tiptap/react` + `@tiptap/starter-kit` + `@tiptap/extension-mention` + `@tiptap/extension-table` (~50KB gzip total)

**Editor features:**
- Toolbar: H1/H2/H3, bold, italic, inline code, code block, bulleted list, numbered list, table insert, undo/redo (reference: Cabinet `editor-toolbar.tsx`)
- Slash commands: `/heading`, `/code`, `/callout`, `/table`, `/divider`
- Inline markdown shortcuts: `## ` → H2, ` ``` ` → code block, `- ` → list
- `@` mention typeahead → `@page:`, `@agent:`, `@alert:`, `@issue:` entity search dropdown, resolves to chips on save
- Auto-save: 500ms debounce on keystroke → save state indicator in toolbar: `"Saving…"` → `"Saved"` (relativeTime) → `"Error — retry"` with retry button
- Markdown raw toggle: WYSIWYG ↔ raw markdown (same Write/Preview tab pattern as existing `DocumentationEditor`)

**Right sidebar panel (320px):**
- `inject_scope` picker: global toggle + role multiselect chips + agent multiselect chips
- `inject_priority` number input (1–10)
- `inject_pinned` switch
- Sync source config: source type select + URL/path input + `secret_ref` picker
- Token count estimate: `text-xs text-dim` — live, updates as content changes

**Header:** Breadcrumb `KB > {folder} > {title}` + Save button + Cancel → `/kb/{slug}`. `ConfirmDialog` on discard if unsaved changes.

> **Tiptap migration scope** — see "Tiptap Migration Audit" section below for where `DocumentationEditor` should be upgraded across the existing app.

---

###### Routines Tab — Routine List

`→ new` (pattern: nearly identical to `/workflows` list — `pages/workflows/index.tsx`)

**Columns:** Name, Type badge, Schedule (cron expression or "On webhook"), Last Run (`relativeTime()` + status dot), Next Run, Status badge, Actions.

**Trigger type display:**
- `cron` → `Clock h-3.5 w-3.5 text-teal` + human-readable cron (e.g., "Daily at 08:00 UTC")
- `webhook` → `Webhook h-3.5 w-3.5 text-amber`
- `manual` → `Play h-3.5 w-3.5 text-dim`

---

##### `/agents/routines/{id}` — Routine Detail

`→ new` (pattern: workflow detail — `pages/workflows/detail.tsx`)

**Tabs:** Config (cron expression + human-readable translation, trigger config, agent assignment, timeout), Run History (table: start, duration, status, issues created, error message), Linked Issues.

---

###### Issues Tab — Kanban Board

`→ new` **Decision: Kanban board** (reference: Paperclip `KanbanBoard.tsx`)

**New dependencies:** `@dnd-kit/core` + `@dnd-kit/sortable`

**Columns:** `backlog / todo / in_progress / in_review / blocked / done` — fixed order, horizontal scroll.

**Card anatomy:**
- Issue ID (`CAL-042`) — `text-[11px] text-dim`
- Title — 2-line clamp, `text-sm text-foreground`
- Priority icon: `AlertTriangle` (critical, `text-red-threat`), `ArrowUp` (high, `text-amber`), `Minus` (medium, `text-teal`), `ArrowDown` (low, `text-dim`)
- Category badge: `variant="outline"`, appropriate color
- Assigned agent chip: `text-[11px] bg-teal/10 border-teal/30 text-teal-light`
- Linked alert title: `text-[11px] text-dim` (if present)
- Active run indicator: pulsing `animate-ping` dot when agent is actively working this issue

**Column header:** status label + `text-xs text-dim` item count.

**Drag behavior (Paperclip `PointerSensor`, 5px activation distance):**
- `useSortable` per card — within-column reorder
- `useDroppable` per column — cross-column drag changes `status` on drop
- Dragging card: `opacity-50 cursor-grabbing`, target column: `bg-accent/40`
- On drop: optimistic update → `PATCH /api/v1/issues/{id}` → rollback on error + `toast.error()`

**Filter bar (above board):** Category (toggle group), Assigned Agent (select), Active only toggle.

**"New Issue" button:** `size="sm" className="bg-teal text-white hover:bg-teal-dim"` — create dialog.

**Empty column:** `text-center text-xs text-dim py-8` "No issues".

---

##### `/agents/issues/{id}` — Issue Detail

`→ new` (pattern: `DetailPageLayout`)

**Status cards:** Status (inline Select), Priority (inline Select), Category badge, Linked Alert link.

**Tabs:**
- Description: `DocumentationEditor` markdown edit/preview
- Comments: chronological list with `ActorBadge`, timestamp, content. Operator comment textarea at bottom.
- Activity: timeline (`activity_events` pattern)
- Linked Entities: alerts, KB pages, routines, campaigns

**Sidebar:** Issue ID (`CopyableText`), status, priority, category, assigned agent (link), created by, dates, checkout status.

---

###### Costs Tab — Cost Dashboard

`→ new` (reference: Paperclip `Costs.tsx` for structure; use Calseta recharts + design tokens)

**Layout:** `AppLayout` + `space-y-4`

**Top stat cards (4, `DetailPageStatusCards` pattern):**
- MTD Spend ($X.XX), Budget ($Y.YY), Utilization % (color: teal <75%, amber 75–90%, red-threat >90%), Runs This Month

**Date range selector (top-right):** "7 days" / "30 days" / "90 days" toggle button group.

**Charts:**
- Spend over time: recharts `AreaChart`, one line per LLM provider
- By agent: recharts `BarChart`, agent names X, cost $ Y

**Spend table columns:** Agent (link), LLM Provider, Model, Input Tokens, Output Tokens, Cost, % of Total, Budget Status badge.

**Budget incidents callout:** if any agent paused by budget, show `Alert` callout at top with links.

---

###### Activity Tab — Audit Log

`→ new` (pattern: alert activity tab promoted to full list page)

**Columns:** Event Type, Actor Type (`ActorBadge`), Actor Key Prefix (dim), Entity Type, Entity link, Timestamp (`relativeTime()` + full date tooltip).

**Filters:** actor_type, event_type (multiselect), entity_type, date range. Sort: newest first, fixed.

---

##### `/settings/llm` — LLM Integrations

`→ new` (pattern: enrichment providers list + detail — `pages/settings/enrichment-providers/`)

**List:** Provider badge (Anthropic/OpenAI/Google/Ollama), Model name, `is_default` indicator (`Star h-3.5 w-3.5 text-teal`), cost per 1K tokens (input / output), configured badge.

**Create/detail:** Provider select → model → API key ref → base_url (optional) → cost fields → default toggle. "Validate" button → `POST /api/v1/llm-integrations/{id}/test`.

**Default:** only one can be default; switching updates old default via PATCH.

---

##### `/settings/secrets` — Secrets Management

`→ new` (pattern: api-keys list — `pages/settings/api-keys/index.tsx`)

**List:** Secret name, Provider type badge (`local_encrypted` / `env_var` / `aws_sm` / `azure_kv`), Usage count, Created, Last Rotated (`relativeTime()`). **Never show secret value.**

**Create:** Name, provider type select, value input (`type="password"`). Same "shown once" pattern as API key creation.

**Actions:** Rotate (prompts new value), Revoke, Delete (blocked if referenced).

**Usage references:** `Sheet` showing which agents / integrations reference this secret.

---

##### `/settings/instructions` — Global Instruction Files

`→ new` (pattern: context-docs list + detail — `pages/settings/context-docs/`)

**List:** Name, Scope badge, active `Switch`, order (`GripVertical` drag handle — up/down arrow buttons, no drag lib needed).

**Detail/Edit:** name, scope config, content (`DocumentationEditor`), active toggle.

---

##### `/settings/api-tokens` — Operator API Tokens

`→ extends` existing `/settings/api-keys` — nearly identical. Add `key_type = "operator"` filter. Otherwise same page.

---

##### `/agents/campaigns` — Campaign Dashboard

`→ new` (pattern: list page)

**Columns:** Name, Target metric, Current vs. Target, Progress bar (`bg-teal` on track / `bg-amber` at risk / `bg-red-threat` overdue), Status badge, Deadline, Linked items count.

---

##### `/agents/campaigns/{id}` — Campaign Detail

`→ new` (pattern: `DetailPageLayout`)

**Tabs:**
- Progress: recharts `LineChart` of metric over time + dashed target threshold line (`stroke-dasharray`)
- Linked Items: alerts / issues / routines
- Activity: timeline

**Sidebar:** current value, target, deadline, owner, status (inline Select), description.

---

##### Sidebar Navigation Restructure

**Decision: `/agents` as tabbed hub — minimal sidebar footprint.**

`/manage/agents` is retired and replaced by a single `/agents` top-level sidebar entry. All control plane sub-sections live as tabs within that page, not as separate sidebar entries. KB gets its own top-level entry. New settings entries appended to the Settings section.

```
Dashboard               (/)           ← existing
Alerts                  (/alerts)     ← existing
Workflows               (/workflows)  ← existing
Approvals               (/approvals)  ← existing
────────────────
KNOWLEDGE BASE                        ← NEW — top-level per PRD intent
  KB                    (/kb)
────────────────
MANAGE
  Agents                (/agents)     ← replaces /manage/agents; hub for entire control plane
  Enrichments           (/manage/enrichment-providers)       ← existing
  Detection Rules       (/manage/detection-rules)            ← existing
  Context Docs          (/manage/context-docs)               ← existing
────────────────
SETTINGS
  API Keys              (/settings/api-keys)                 ← existing
  Alert Sources         (/settings/alert-sources)            ← existing
  Indicator Mappings    (/settings/indicator-mappings)       ← existing
  LLM Providers         (/settings/llm)                      ← NEW
  Secrets               (/settings/secrets)                  ← NEW
  Instructions          (/settings/instructions)             ← NEW
  Integrations          (/settings/integrations)             ← NEW
  API Tokens            (/settings/api-tokens)               ← NEW
```

**`/agents` tabs (all control plane surface lives here):**
```
Fleet | Queue | Issues | Topology | Actions | Costs | Activity | Routines | Campaigns
```

> The sidebar stays compact. The entire control plane is one nav entry — "Agents" — that expands into a tabbed hub. This is consistent with how existing Calseta detail pages work (one URL, multiple tabs), just applied at the feature-hub level.

**Implementation:** Update `ui/src/components/layout/sidebar.tsx` — add `knowledgeBaseNav` array (one entry), update `manageNav` to replace `/manage/agents` with `/agents`, extend `settingsNav` with new entries. Add `/agents` route (with `validateSearch` for tab param) to `router.tsx`. Redirect `/manage/agents` → `/agents?tab=fleet`.

---

#### Tiptap Migration Audit

**Decision: Add Tiptap.** The KB editor introduces it as a dependency. Below is where `DocumentationEditor` (current: textarea + markdown preview tab) exists today and the recommended migration approach for each.

| Location | File | Content type | Migrate to Tiptap? | Notes |
|---|---|---|---|---|
| **KB page editor** | `pages/kb/edit.tsx` (new) | Long-form runbooks, SOPs, KB articles | **Yes — primary use case** | Full feature set: slash commands, @mentions, tables, auto-save |
| **Context Docs** | `pages/settings/context-docs/detail.tsx` | Structured markdown docs, IR templates | **Yes** | Context docs are the v1 predecessor to KB pages — same content type. Migrate `DocumentationEditor` → `TiptapEditor` here |
| **Issue descriptions** | `pages/control-plane/issues/detail.tsx` (new) | Structured text, links | **Yes** | Issues have rich descriptions; @mentions needed for linking alerts/pages |
| **Issue comments** | `pages/control-plane/issues/detail.tsx` (new) | Short comments | **Lightweight only** | Use Tiptap with just `StarterKit` + `Mention` — no slash commands or tables |
| **Workflow documentation** | `pages/workflows/detail.tsx` | Short technical notes | **No** | Content is short (1–3 sentences), textarea is fine |
| **Detection rule documentation** | `pages/settings/detection-rules/detail.tsx` | Short notes, links | **No** | Same — short content, textarea sufficient |
| **Agent documentation** | `pages/settings/agents/detail.tsx` | Short description | **No** | Single paragraph max |
| **Enrichment provider documentation** | `pages/settings/enrichment-providers/detail.tsx` | Short notes | **No** | Rarely used |

**Migration plan:**
1. Build `TiptapEditor` component at `ui/src/components/tiptap-editor.tsx` — wraps Tiptap with Calseta styling (dark theme, border-border, font-sans, toolbar buttons using lucide icons)
2. Build `TiptapEditorLite` variant — `StarterKit` + `Mention` only (for comments)
3. Replace `DocumentationEditor` in Context Docs detail page
4. Use `TiptapEditor` in new KB editor and Issue description
5. Use `TiptapEditorLite` in Issue comments and Alert activity comment input (future)
6. Leave `DocumentationEditor` in place for Workflow, Detection Rule, Agent, Enrichment Provider docs — these are short fields where textarea is appropriate

**`TiptapEditor` component contract:**
```tsx
interface TiptapEditorProps {
  content: string;               // markdown string in, markdown string out
  onChange?: (markdown: string) => void;   // live changes (for auto-save)
  onSave?: (markdown: string) => void;     // explicit save (for Save button)
  isSaving?: boolean;
  readOnly?: boolean;
  placeholder?: string;
  enableMentions?: boolean;      // enables @ mention extension
  enableTables?: boolean;        // enables table extension
  autoSave?: boolean;            // enables 500ms debounce auto-save
  className?: string;
}
```

---

#### Decisions Log

All questions resolved.

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| Q1 | Issue board layout | **Kanban** (@dnd-kit/core + @dnd-kit/sortable) | Visual status management; Paperclip proved the pattern |
| Q2 | KB / rich text editor | **Tiptap** — full editor for KB + Issues; migrate Context Docs | @mention support and table editing needed; migrate where content is long-form |
| Q3 | Investigation tree | **@xyflow/react** flow diagram (same dep as topology) | One dep, two uses; build both in same sprint |
| Q4 | Nav structure | **`/agents` as tabbed hub** — single sidebar entry, all CP tabs inside | Consistent with existing Calseta tab pattern; keeps sidebar compact |
| Q5 | Dashboard split | **`/` stays as SOC metrics, `/agents` is the agent fleet hub** | Clean separation — `/` = alert throughput, `/agents` = agent command center |
| Q6 | Real-time updates | **SSE** — `GET /api/v1/events/stream` pushes 4 event types | Approval inbox is time-critical; FastAPI supports SSE natively; zero new infra |

**SSE event stream spec (`GET /api/v1/events/stream`):**

Server-Sent Events, `text/event-stream`, authenticated via API key. Frontend subscribes with `EventSource`. On each event, invalidate the matching React Query key — no polling needed for these data types.

| Event type | Payload | React Query key invalidated |
|---|---|---|
| `agent.status_changed` | `{ agent_uuid, status, previous_status }` | `["agents"]`, `["agent", uuid]` |
| `approval.created` | `{ approval_uuid, workflow_name, expires_at }` | `["approvals"]` |
| `approval.expired` | `{ approval_uuid }` | `["approvals"]` |
| `queue.updated` | `{ alert_uuid, event: "added" \| "checked_out" \| "released" }` | `["queue"]` |

**Frontend connection pattern:**
```ts
// hooks/use-sse.ts
export function useSSE() {
  const qc = useQueryClient();
  useEffect(() => {
    const es = new EventSource("/api/v1/events/stream", {
      headers: { Authorization: `Bearer ${getApiKey()}` },
    });
    es.onmessage = (e) => {
      const event = JSON.parse(e.data);
      if (event.type === "agent.status_changed") {
        qc.invalidateQueries({ queryKey: ["agents"] });
        qc.invalidateQueries({ queryKey: ["agent", event.agent_uuid] });
      } else if (event.type.startsWith("approval.")) {
        qc.invalidateQueries({ queryKey: ["approvals"] });
      } else if (event.type === "queue.updated") {
        qc.invalidateQueries({ queryKey: ["queue"] });
      }
    };
    es.onerror = () => es.close(); // reconnect handled by browser
    return () => es.close();
  }, [qc]);
}
```

Mount `useSSE()` once at the `AppLayout` level so the connection is shared across all pages.

---

---

