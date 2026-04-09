# Docs v2 PRD — Agent Control Plane Documentation

**Status:** Draft  
**Date:** 2026-04-04  
**Branch:** `feat/calseta-v2`  
**Author:** Docs audit + PRD (agent-assisted)

---

## Overview

Calseta v2 shipped a full agent control plane: LLM provider management, managed agent runtime, alert queue with atomic checkout, tool system, response actions with approval gate, multi-agent orchestration, knowledge base with sync, agent memory, secrets management, issues/routines/campaigns, heartbeat monitoring, agent topology, operator dashboard, CLI, and 7 reference agent implementations.

The docs site at `docs.calseta.com` covers **none of this**. It describes Calseta v1 only. The current doc set is correct for a push-based SOC data layer with webhook agents. It is completely wrong for a managed agent platform.

This PRD defines the gap, proposes a nav restructure, inventories every new page required, estimates writing effort, and phases the rollout.

**Reading this PRD:** A writer picking up any section below should be able to write that page without asking clarifying questions. All page specs include slug, title, section, type, audience, priority, dependencies, and a 3–5 line content brief.

---

## 1. Gap Analysis

### V2 Feature → Documentation Status

| Feature | Shipped | Existing Doc | Gap |
|---|---|---|---|
| LLM Integrations | ✅ | ❌ | Full concept + API reference group |
| Managed agent execution mode | ✅ | ❌ | New concept + guide |
| Agent Registry v2 (new fields: execution_mode, system_prompt, tool_ids, budget, adapter_type, etc.) | ✅ | ⚠️ Partial — `integrations/agent-webhooks.mdx` covers v1 webhook-only registration | Major update to agent docs |
| Agent lifecycle (pause/resume/terminate) | ✅ | ❌ | Docs for new lifecycle endpoints |
| Agent API keys (`cak_*`) | ✅ | ❌ | Auth concept update + API reference |
| Agent runtime engine (tool loop, 6-layer prompt, session state) | ✅ | ❌ | Full concept page needed |
| Session compaction | ✅ | ❌ | Subsection of agent runtime concept |
| Tool system (tiers, built-in tools, workflow-as-tool) | ✅ | ❌ | Full concept + API reference group |
| Alert queue (pull model, atomic checkout) | ✅ | ❌ | Full concept + API reference group |
| Alert assignment lifecycle | ✅ | ❌ | Subsection of alert queue concept |
| Response actions (propose/approve/reject/execute) | ✅ | ❌ | Full concept + guide + API reference |
| Action integrations (CrowdStrike, Entra ID, Slack, GenericWebhook) | ✅ | ❌ | Integration guide per action type |
| Confidence-based approval mode | ✅ | ❌ | Subsection of response actions concept |
| Multi-agent orchestration (delegate, parallel, long-poll) | ✅ | ❌ | Full concept + guide |
| Invocation lifecycle | ✅ | ❌ | API reference group + concept subsection |
| Knowledge base (pages, folders, inject_scope, revision history) | ✅ | ❌ | Full concept + API reference group |
| KB sync (GitHub, Confluence, URL providers) | ✅ | ❌ | Guide + contributing page |
| KB injection into managed agent prompts | ✅ | ❌ | Subsection of agent runtime concept |
| Agent memory (save/recall/promote, staleness TTL) | ✅ | ❌ | Full concept + API reference group |
| Issues & routines (non-alert work items, cron/webhook triggers) | ✅ | ❌ | Full concept + API reference groups |
| Campaigns | ✅ | ❌ | Concept subsection + API reference group |
| Secrets management (local_encrypted, env_var, secret_ref) | ✅ | ❌ | Full concept + API reference group |
| Heartbeat system (liveness, stuck detection, supervisor) | ✅ | ❌ | Concept subsection + API reference group |
| Agent topology (fleet graph, delegation edges) | ✅ | ❌ | Concept + API reference group |
| Budget & cost tracking (per-alert cap, monthly cap, hard-stop) | ✅ | ❌ | Concept subsection + API reference |
| Operator dashboard (queue, fleet, costs, pending actions) | ✅ | ❌ | Mention in existing UI concept |
| CLI (7 MVP commands) | ✅ | ❌ | Full CLI section (overview + 4 pages) |
| `calseta investigate` command | ✅ | ❌ | Primary CLI guide |
| `calseta setup` (MCP config + CLAUDE.md generation) | ✅ | ❌ | Guide page |
| Reference agents (lead-investigator + 6 specialists) | ✅ | ❌ | Guide: building an orchestrator, building a specialist |
| Two-mode agent execution (queue / invocation) | ✅ | ❌ | Reference agent guide |
| `make dev-agents` testbed | ✅ | ❌ | Operations mention |
| Agent instruction files | ✅ | ❌ | Subsection of agent registry concept |
| `agent.methodology` field | ✅ | ❌ | Subsection of agent registry concept |
| MCP tools for KB + memory (save_memory, recall_memory, etc.) | ✅ | ❌ | MCP reference tool pages |
| `concepts/alert-schema.mdx` — assignment fields, agent_findings | ✅ | ⚠️ Missing from existing page | Update |
| `integrations/agent-webhooks.mdx` — stale, v1 only | ✅ | ⚠️ Stale — no mention of managed execution, cak_* keys, agent_type | Overhaul or replace |
| `mcp-reference/overview.mdx` — v1 only | ✅ | ⚠️ Missing all v2 tools | Update |
| `essentials/` folder | N/A | ❌ Mintlify boilerplate, not Calseta content | Remove from nav |

**Summary:** Of the 38 v2 features audited, **31 have zero docs coverage (❌)**, 4 are partially covered (⚠️), and 3 exist and are accurate (✓). The v2 agent platform is a complete blind spot in the current documentation.

---

## 2. Proposed Nav Restructuring

The current 3-tab structure was designed for a v1 SOC data platform with push-only dispatch. V2 adds enough surface area (managed agent platform, CLI, control plane APIs) to warrant a restructure.

### Recommended: 4 Tabs

**Rationale for changes:**
- "Documentation" tab is overloaded with integrations, operations, and contributing. Separate "Guides" into its own tab — it's a different audience mode (doing vs understanding).
- CLI gets its own section within Documentation (not a 4th tab) — it's a surface, not a reference system.
- MCP Reference expands but stays its own tab.
- "Integrations" vs "Guides" overlap is cleaned up: Integrations = source/enrichment/action *setup* (operator work). Guides = how to accomplish a goal (developer work).
- `essentials/` folder removed — it's Mintlify template boilerplate.

### Proposed `docs.json` Navigation

```
navigation: {
  tabs: [

    // TAB 1: Documentation
    {
      tab: "Documentation",
      groups: [

        {
          group: "Get Started",
          pages: [
            "getting-started/quickstart",           // UPDATE: add make dev-agents, CLI install
            "getting-started/introduction",
            "getting-started/how-it-works"
          ]
        },

        {
          group: "Concepts",
          pages: [
            // V1 core (existing, some need updates)
            "concepts/alert-schema",                // UPDATE: add assignment fields, agent_findings
            "concepts/authentication",             // UPDATE: add cak_* agent keys section
            "concepts/detection-rules",
            "concepts/context-documents",
            "concepts/workflows",
            "concepts/security",

            // V2 Agent Platform (all new)
            "concepts/llm-integrations",           // NEW P0
            "concepts/agent-registry",             // NEW P0 (replaces stale agent-webhooks concept)
            "concepts/agent-runtime",              // NEW P0
            "concepts/alert-queue",                // NEW P0
            "concepts/tool-system",                // NEW P0
            "concepts/response-actions",           // NEW P0
            "concepts/multi-agent-orchestration",  // NEW P0
            "concepts/knowledge-base",             // NEW P0
            "concepts/agent-memory",               // NEW P1
            "concepts/issues-and-routines",        // NEW P1
            "concepts/secrets-management",         // NEW P1
            "concepts/agent-topology",             // NEW P2
            "concepts/heartbeat",                  // NEW P2 (or merge into agent-registry)
            "concepts/campaigns"                   // NEW P2
          ]
        },

        {
          group: "CLI",                            // NEW SECTION
          pages: [
            "cli/overview",                        // NEW P0
            "cli/login-and-setup",                 // NEW P0
            "cli/investigate",                     // NEW P0
            "cli/command-reference"                // NEW P1
          ]
        },

        {
          group: "Integrations",
          pages: [
            {
              group: "Alert Sources",
              pages: [
                "integrations/alert-sources/overview",
                "integrations/alert-sources/microsoft-sentinel",
                "integrations/alert-sources/elastic",
                "integrations/alert-sources/splunk",
                "integrations/alert-sources/generic-webhook"
              ]
            },
            {
              group: "Enrichment",
              pages: [
                "integrations/enrichment/overview",
                "integrations/enrichment/virustotal",
                "integrations/enrichment/abuseipdb",
                "integrations/enrichment/okta",
                "integrations/enrichment/entra",
                "integrations/enrichment/custom-sources"
              ]
            },
            {
              group: "Response Actions",              // NEW GROUP
              pages: [
                "integrations/actions/crowdstrike",  // NEW P1
                "integrations/actions/entra-id",     // NEW P1
                "integrations/actions/slack",        // NEW P1
                "integrations/actions/generic-webhook" // NEW P1
              ]
            },
            {
              group: "KB Sync",                      // NEW GROUP
              pages: [
                "integrations/kb-sync/github",       // NEW P1
                "integrations/kb-sync/confluence",   // NEW P1
                "integrations/kb-sync/url"           // NEW P2
              ]
            }
            // NOTE: integrations/agent-webhooks — REMOVE (stale v1 only; concepts/agent-registry replaces it)
          ]
        },

        {
          group: "Operations",
          pages: [
            "operations/self-hosting",             // UPDATE: add make dev-agents
            "operations/production-deployment",
            "operations/deploy-aws",
            "operations/deploy-azure",
            "operations/roadmap"
          ]
        },

        {
          group: "Contributing",
          pages: [
            "contributing/adding-alert-sources",
            "contributing/adding-enrichment-providers",
            "contributing/adding-action-integrations", // NEW P2
            "contributing/community-integrations"
          ]
        }
      ]
    },

    // TAB 2: Guides
    {
      tab: "Guides",
      groups: [
        {
          group: "Getting Started with Agents",
          pages: [
            "guides/your-first-managed-agent",     // NEW P0
            "guides/using-calseta-with-claude-code", // NEW P0
            "guides/local-development"             // MOVE from Documentation > Development
          ]
        },
        {
          group: "Building Agents",
          pages: [
            "guides/building-an-orchestrator",     // NEW P0
            "guides/human-in-the-loop-approvals",  // NEW P1
            "guides/writing-a-custom-action-integration" // NEW P2
          ]
        },
        {
          group: "Knowledge Management",
          pages: [
            "guides/setting-up-kb-sync"            // NEW P1
          ]
        }
      ]
    },

    // TAB 3: API Reference (massively expanded)
    {
      tab: "API Reference",
      groups: [
        {
          group: "API Reference",
          pages: [
            "api-reference/overview",             // UPDATE: document cak_* keys

            // V1 groups (existing — unchanged structurally)
            { group: "Alerts", pages: [...existing...] },
            { group: "Detection Rules", pages: [...existing...] },
            { group: "Context Documents", pages: [...existing...] },
            { group: "Workflows", pages: [...existing...] },
            { group: "Workflow Runs", pages: [...existing...] },
            { group: "Workflow Approvals", pages: [...existing...] },
            { group: "Enrichment", pages: [...existing...] },
            { group: "Enrichment Providers", pages: [...existing...] },
            { group: "Field Extractions", pages: [...existing...] },
            { group: "Indicators", pages: [...existing...] },
            { group: "Indicator Mappings", pages: [...existing...] },
            { group: "Sources", pages: [...existing...] },
            { group: "Metrics", pages: [...existing...] },
            { group: "API Keys", pages: [...existing...] },

            // V1 Agents (existing but needs update for v2 fields)
            { group: "Agents", pages: [
              "api-reference/agents/list",
              "api-reference/agents/get",
              "api-reference/agents/register",    // UPDATE: all new v2 fields
              "api-reference/agents/update",
              "api-reference/agents/delete",
              "api-reference/agents/pause",       // NEW
              "api-reference/agents/resume",      // NEW
              "api-reference/agents/terminate",   // NEW
              "api-reference/agents/keys-list",   // NEW
              "api-reference/agents/keys-create", // NEW
              "api-reference/agents/keys-delete", // NEW
              "api-reference/agents/files-get",   // NEW
              "api-reference/agents/files-put",   // NEW
              "api-reference/agents/files-delete" // NEW
            ]},

            // V2 NEW GROUPS
            { group: "LLM Integrations", pages: [    // NEW
              "api-reference/llm-integrations/list",
              "api-reference/llm-integrations/get",
              "api-reference/llm-integrations/create",
              "api-reference/llm-integrations/update",
              "api-reference/llm-integrations/delete",
              "api-reference/llm-integrations/usage"
            ]},
            { group: "Alert Queue", pages: [          // NEW
              "api-reference/queue/list",
              "api-reference/queue/checkout",
              "api-reference/queue/release",
              "api-reference/queue/dashboard"
            ]},
            { group: "Assignments", pages: [          // NEW
              "api-reference/assignments/mine",
              "api-reference/assignments/list",
              "api-reference/assignments/get",
              "api-reference/assignments/update"
            ]},
            { group: "Actions", pages: [              // NEW
              "api-reference/actions/list",
              "api-reference/actions/get",
              "api-reference/actions/propose",
              "api-reference/actions/approve",
              "api-reference/actions/reject",
              "api-reference/actions/cancel"
            ]},
            { group: "Invocations", pages: [          // NEW
              "api-reference/invocations/delegate",
              "api-reference/invocations/delegate-parallel",
              "api-reference/invocations/get",
              "api-reference/invocations/poll",
              "api-reference/invocations/patch",
              "api-reference/invocations/history"
            ]},
            { group: "Agent Tools", pages: [          // NEW
              "api-reference/tools/list",
              "api-reference/tools/get",
              "api-reference/tools/register",
              "api-reference/tools/update",
              "api-reference/tools/delete"
            ]},
            { group: "Knowledge Base", pages: [       // NEW
              "api-reference/kb/list",
              "api-reference/kb/get",
              "api-reference/kb/create",
              "api-reference/kb/update",
              "api-reference/kb/delete",
              "api-reference/kb/search",
              "api-reference/kb/folders",
              "api-reference/kb/sync",
              "api-reference/kb/revisions"
            ]},
            { group: "Memory", pages: [               // NEW
              "api-reference/memory/list",
              "api-reference/memory/get",
              "api-reference/memory/create",
              "api-reference/memory/update",
              "api-reference/memory/delete",
              "api-reference/memory/promote"
            ]},
            { group: "Issues", pages: [               // NEW
              "api-reference/issues/list",
              "api-reference/issues/get",
              "api-reference/issues/create",
              "api-reference/issues/update",
              "api-reference/issues/delete",
              "api-reference/issues/checkout",
              "api-reference/issues/release",
              "api-reference/issues/comments"
            ]},
            { group: "Routines", pages: [             // NEW
              "api-reference/routines/list",
              "api-reference/routines/get",
              "api-reference/routines/create",
              "api-reference/routines/update",
              "api-reference/routines/delete",
              "api-reference/routines/pause",
              "api-reference/routines/resume",
              "api-reference/routines/trigger",
              "api-reference/routines/runs"
            ]},
            { group: "Campaigns", pages: [            // NEW
              "api-reference/campaigns/list",
              "api-reference/campaigns/get",
              "api-reference/campaigns/create",
              "api-reference/campaigns/update",
              "api-reference/campaigns/delete",
              "api-reference/campaigns/items"
            ]},
            { group: "Secrets", pages: [              // NEW
              "api-reference/secrets/list",
              "api-reference/secrets/get",
              "api-reference/secrets/create",
              "api-reference/secrets/delete",
              "api-reference/secrets/rotate",
              "api-reference/secrets/versions"
            ]},
            { group: "Heartbeat & Costs", pages: [    // NEW
              "api-reference/heartbeat/record",
              "api-reference/heartbeat/runs-list",
              "api-reference/heartbeat/runs-get",
              "api-reference/costs/summary",
              "api-reference/costs/by-agent",
              "api-reference/costs/by-alert",
              "api-reference/costs/events"
            ]},
            { group: "Topology & Sessions", pages: [  // NEW
              "api-reference/topology/get",
              "api-reference/topology/routing",
              "api-reference/sessions/list",
              "api-reference/sessions/get"
            ]}
          ]
        }
      ]
    },

    // TAB 4: MCP Reference (expanded)
    {
      tab: "MCP Reference",
      groups: [
        {
          group: "MCP Reference",
          pages: [
            "mcp-reference/overview",              // UPDATE: add v2 tools
            "mcp-reference/setup",
            {
              group: "Resources",
              pages: [
                // existing
                "mcp-reference/resources/alerts",
                "mcp-reference/resources/detection-rules",
                "mcp-reference/resources/context-documents",
                "mcp-reference/resources/workflows",
                "mcp-reference/resources/enrichments",
                "mcp-reference/resources/metrics",
                // new
                "mcp-reference/resources/kb-pages",  // NEW P1
                "mcp-reference/resources/queue"      // NEW P1
              ]
            },
            {
              group: "Tools",
              pages: [
                // existing
                "mcp-reference/tools/post-alert-finding",
                "mcp-reference/tools/update-alert-status",
                "mcp-reference/tools/execute-workflow",
                "mcp-reference/tools/search-alerts",
                "mcp-reference/tools/search-detection-rules",
                "mcp-reference/tools/enrich-indicator",
                // new v2
                "mcp-reference/tools/save-memory",    // NEW P0
                "mcp-reference/tools/recall-memory",  // NEW P0
                "mcp-reference/tools/create-kb-page", // NEW P1
                "mcp-reference/tools/search-kb",      // NEW P1
                "mcp-reference/tools/checkout-alert", // NEW P1
                "mcp-reference/tools/propose-action", // NEW P1
                "mcp-reference/tools/list-actions"    // NEW P2
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

### Pages to Remove from Nav

| Current path | Reason |
|---|---|
| `essentials/*` | Mintlify template boilerplate — not Calseta content. Remove group from nav. Files can stay in repo for Mintlify's sake but should not be navigable. |
| `integrations/agent-webhooks` | V1-only. The page describes webhook push only. The new `concepts/agent-registry` page covers both v1 webhook and v2 managed/external modes. Archive or redirect to `concepts/agent-registry`. |
| `guides/local-development` (from Documentation tab) | Move to Guides tab > Getting Started with Agents group. |

---

## 3. New Pages Inventory

### Format

```
Slug:         <path relative to docs root>
Title:        <H1 of the page>
Section:      <tab/group>
Type:         concept | guide | reference | quickstart
Audience:     Operators | Developers | Both
Priority:     P0 | P1 | P2
Dependencies: <slugs that should exist first>
Brief:        <3–5 lines: what this page covers, key sections>
Lines (est):  <rough MDX line count>
```

---

### Concepts (new)

---

**Slug:** `concepts/llm-integrations`  
**Title:** LLM Integrations  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Operators  
**Priority:** P0  
**Dependencies:** —  
**Brief:** Explains the `llm_integrations` table as the central registry for LLM providers. Covers Anthropic, OpenAI, Azure OpenAI, and `ClaudeCodeAdapter` (dev-only). Explains `is_default` flag, `api_key_ref` secret reference pattern, `cost_per_1k_*_tokens_cents` fields operators must set, and when to use `ClaudeCodeAdapter` vs API keys. Includes the `test_environment()` verification step. Warns against ClaudeCode in production.  
**Lines (est):** 140

---

**Slug:** `concepts/agent-registry`  
**Title:** Agent Registry  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Operators  
**Priority:** P0  
**Dependencies:** `concepts/llm-integrations`  
**Brief:** The complete v2 `AgentRegistration` reference. Covers `execution_mode` (managed vs external), `agent_type` (orchestrator vs specialist), `adapter_type` (http/mcp/webhook/claude_code), `role`, `status` (active/paused/terminated), `system_prompt`, `methodology`, `instruction_files`, `tool_ids`, `sub_agent_ids`, `budget_monthly_cents`, `max_cost_per_alert_cents`, `max_concurrent_alerts`, trigger config fields, and the `cak_*` agent API key system. Includes a lifecycle diagram. Replaces the stale `integrations/agent-webhooks` content.  
**Lines (est):** 180

---

**Slug:** `concepts/agent-runtime`  
**Title:** Agent Runtime Engine  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Developers  
**Priority:** P0  
**Dependencies:** `concepts/agent-registry`, `concepts/llm-integrations`, `concepts/tool-system`  
**Brief:** How Calseta executes managed agents. Covers: the tool loop (send prompt → parse → tool_use → execute → return result), the 6-layer prompt construction system (layer by layer: identity/instructions, methodology, KB context, alert context, session history, checkpoint+memory), session state persistence in `agent_task_sessions`, session compaction trigger (80% context window) and handoff mechanism, and `MAX_TOOL_ITERATIONS=50` limit. Includes a flow diagram of one tool loop iteration. Explains what triggers a heartbeat vs what a heartbeat does.  
**Lines (est):** 200

---

**Slug:** `concepts/alert-queue`  
**Title:** Alert Queue  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Developers  
**Priority:** P0  
**Dependencies:** `concepts/agent-registry`  
**Brief:** The pull model: how enriched alerts move from ingest pipeline to the agent queue. Covers `GET /v1/queue` eligibility filtering (enrichment_status=Enriched, no existing assignment, matches agent's trigger config), atomic checkout via `SELECT FOR UPDATE` preventing double-handling, assignment status machine (`in_progress` → `completed`/`released`/`budget_stopped`), and the difference between operator view (all alerts) and agent view (own-eligible only). Explains when to use queue mode vs invocation mode (queue = alert triage, invocation = delegated specialist work).  
**Lines (est):** 140

---

**Slug:** `concepts/tool-system`  
**Title:** Tool System  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Developers  
**Priority:** P0  
**Dependencies:** `concepts/agent-runtime`  
**Brief:** Four tool tiers and their enforcement: `safe` (always execute), `managed` (execute but log), `requires_approval` (route through action system), `forbidden` (blocked with error). Lists all Calseta built-in tools registered at startup. Explains workflow-as-tool registration. Covers `tool_ids` assignment to agents and how the runtime checks tier before executing. Explains why tools use Anthropic format as canonical (even for OpenAI agents).  
**Lines (est):** 130

---

**Slug:** `concepts/response-actions`  
**Title:** Response Actions  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Both  
**Priority:** P0  
**Dependencies:** `concepts/agent-registry`  
**Brief:** The propose→approve→execute flow. Covers: action types (containment, remediation, notification, escalation, investigation, user_validation, custom), `default_approval_mode` per action type, confidence-based approval threshold table (≥0.95 auto_approve, ≥0.85 quick_review, ≥0.70 human_review, <0.70 block), `bypass_confidence_override` for high-stakes actions (Entra ID), `AgentAction.payload` shape, rollback support, and the operator approval UI flow. Includes the status state machine diagram (pending → approved/rejected → executed/failed).  
**Lines (est):** 160

---

**Slug:** `concepts/multi-agent-orchestration`  
**Title:** Multi-Agent Orchestration  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Developers  
**Priority:** P0  
**Dependencies:** `concepts/agent-registry`, `concepts/alert-queue`  
**Brief:** Orchestrators, specialists, and the delegation model. Covers: `agent_type` field (orchestrator/specialist), `sub_agent_ids` and specialist selection, `POST /v1/invocations` for single delegation vs `POST /v1/invocations/parallel` for 2–10 simultaneous tasks, long-poll via `GET /v1/invocations/{uuid}/poll` (200=done, 202=pending, max 30s), invocation payload shape (task_type, payload, orchestrator_agent_uuid), result posting from specialist via `PATCH /v1/invocations/{uuid}`, and invocation status machine. Includes a sequence diagram of the lead-investigator pattern.  
**Lines (est):** 170

---

**Slug:** `concepts/knowledge-base`  
**Title:** Knowledge Base  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Operators  
**Priority:** P0  
**Dependencies:** `concepts/agent-runtime`  
**Brief:** KB pages, folders, and injection into managed agent prompts. Covers: `inject_scope` values (`global`, `role:{role}`, `agent:{uuid}`) and what each injects into, `inject_pinned` flag (always included regardless of token budget), the 15% context window budget for KB injection, token estimation from `page.token_count` or `len(body)//4`, sync_source JSONB for external sync providers (GitHub, Confluence, URL), revision history on every update, and the full-text search endpoint. Explains the distinction between KB (operator-curated knowledge) and memory (agent-written state).  
**Lines (est):** 150

---

**Slug:** `concepts/agent-memory`  
**Title:** Agent Memory  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Developers  
**Priority:** P1  
**Dependencies:** `concepts/knowledge-base`, `concepts/agent-runtime`  
**Brief:** How agents persist and recall state across investigations. Covers: private memory at `/memory/agents/{agent.id}/` (note: integer ID not UUID), `metadata_.staleness_ttl_hours` for TTL-based staleness, the `[STALE — last updated X hours ago]` prefix injected on stale pages, 5% context window memory budget, non-stale-first sort order then `updated_at DESC`, the `promote` endpoint for elevating agent memory to shared KB (operator approval optional via `memory_promotion_requires_approval` flag), and shared memory at `/memory/shared/`. Includes a save/recall/promote workflow example.  
**Lines (est):** 140

---

**Slug:** `concepts/issues-and-routines`  
**Title:** Issues and Routines  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Both  
**Priority:** P1  
**Dependencies:** `concepts/agent-registry`  
**Brief:** Non-alert work items in the agent control plane. **Issues:** security-domain work items (categories: remediation, detection_tuning, post_incident, compliance, investigation, maintenance), atomic checkout for issue work, comment threads. **Routines:** scheduled/event-driven agent invocations, cron triggers, webhook triggers (HMAC-SHA256 signed), `pause`/`resume` lifecycle, run history. Covers when to use issues vs alerts (issues are longer-running; alerts are point-in-time detections). Includes campaigns as the grouping layer across alerts, issues, and routines.  
**Lines (est):** 140

---

**Slug:** `concepts/secrets-management`  
**Title:** Secrets Management  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Operators  
**Priority:** P1  
**Dependencies:** —  
**Brief:** Two providers: `local_encrypted` (AES-256-GCM in PostgreSQL, requires `ENCRYPTION_KEY` env var) and `env_var` (reads from process environment). The `secret_ref` pattern for referencing secrets in agent configs, LLM integration configs, and KB sync configs — format: `env:VAR_NAME` or `secret:my-secret-name`. Secret rotation via `POST /v1/secrets/{name}/versions`, version history retention, and log redaction for resolved values in heartbeat run logs. Explains why agents never see raw secret values (JWT-scoped access only).  
**Lines (est):** 120

---

**Slug:** `concepts/agent-topology`  
**Title:** Agent Topology  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Operators  
**Priority:** P2  
**Dependencies:** `concepts/multi-agent-orchestration`  
**Brief:** The fleet graph: node types (orchestrator, specialist, external), delegation edges (which orchestrators have delegated to which specialists, with invocation counts), routing config. Explains `GET /v1/topology` response shape and how to read the graph. Covers `GET /v1/dashboard` for operator visibility into queue depth, active agents, pending actions, and MTD costs.  
**Lines (est):** 100

---

**Slug:** `concepts/heartbeat`  
**Title:** Heartbeat and Budget  
**Section:** Documentation > Concepts  
**Type:** Concept  
**Audience:** Operators  
**Priority:** P2  
**Dependencies:** `concepts/agent-runtime`  
**Brief:** How Calseta monitors managed agent health. Covers: `HeartbeatRun` lifecycle (running → completed/failed/budget_stopped/timed_out), `last_heartbeat_at` timestamp for liveness detection, `AgentSupervisor` checking every 30s for timeouts and monthly budget overruns, the two budget enforcement points (per-alert `max_cost_per_alert_cents` in engine loop; monthly `budget_monthly_cents` in supervisor), and `cost_events` recording per LLM API call. Explains `billing_type: "subscription"` for ClaudeCode (not counted against `budget_monthly_cents` by default).  
**Lines (est):** 120

---

**Slug:** `concepts/campaigns`  
**Title:** Campaigns  
**Section:** Documentation > Concepts (or subsection of issues-and-routines)  
**Type:** Concept  
**Audience:** Both  
**Priority:** P2  
**Dependencies:** `concepts/issues-and-routines`  
**Brief:** Campaigns group related alerts, issues, and routines for coordinated investigation. Covers: campaign creation, item linking (alerts, issues, routines), auto-computed aggregate metrics (total alerts, resolved count, open actions, total cost), and use cases (ransomware response campaign, identity compromise investigation). Can be a short subsection appended to `concepts/issues-and-routines` rather than a standalone page.  
**Lines (est):** 80

---

### CLI (new)

---

**Slug:** `cli/overview`  
**Title:** Calseta CLI  
**Section:** Documentation > CLI  
**Type:** Reference  
**Audience:** Both  
**Priority:** P0  
**Dependencies:** —  
**Brief:** What the CLI is and who it's for. Covers installation (`pip install calseta-cli`), configuration priority order (flags > env vars > `~/.calseta/config.toml` > default localhost), named profiles via `--profile`, and the full command tree. Explains the relationship to the REST API (CLI is human ergonomics; REST API is programmatic agent use). Includes a quick "first 3 commands" getting started flow: `calseta login` → `calseta status` → `calseta alerts list`.  
**Lines (est):** 100

---

**Slug:** `cli/login-and-setup`  
**Title:** Login and Setup  
**Section:** Documentation > CLI  
**Type:** Guide  
**Audience:** Both  
**Priority:** P0  
**Dependencies:** `cli/overview`  
**Brief:** Step-by-step for `calseta login` (writes `~/.calseta/config.toml`) and `calseta setup` (writes `.claude/settings.json` + `CLAUDE.md` in CWD). Shows the exact `settings.json` MCP config block that gets written. Shows the generated `CLAUDE.md` content structure (available tools, resources, alert data model, enum reference, investigation patterns). Covers merge/append behavior when files already exist.  
**Lines (est):** 100

---

**Slug:** `cli/investigate`  
**Title:** `calseta investigate`  
**Section:** Documentation > CLI  
**Type:** Guide  
**Audience:** Both  
**Priority:** P0  
**Dependencies:** `cli/login-and-setup`  
**Brief:** The anchor command — fetch alert context, format a prompt, and launch Claude with the Calseta MCP server pre-wired. Covers: what it fetches in parallel (alert detail, context docs, active workflows), the investigation prompt format, `--no-mcp` flag (clipboard fallback), `--dry-run` for debugging the prompt, `--model` override, and prerequisite checks (`claude` CLI installed and logged in, `calseta setup` run). Includes a full walkthrough: from `calseta queue list` to `calseta investigate <uuid>` to Claude posting a finding.  
**Lines (est):** 120

---

**Slug:** `cli/command-reference`  
**Title:** Command Reference  
**Section:** Documentation > CLI  
**Type:** Reference  
**Audience:** Both  
**Priority:** P1  
**Dependencies:** `cli/overview`  
**Brief:** Full reference for all 7 MVP commands plus the full command tree (Sprint 1 + Sprint 2 deferred commands marked). Each command: synopsis, flags, output format, example. Covers: `login`, `status`, `alerts list`, `alerts inspect`, `setup`, `investigate`, `enrichments lookup`. Includes global flags (`--json`, `--quiet`, `--profile`). Notes Sprint 2 commands as coming soon (queue, agents, workflows, kb, keys).  
**Lines (est):** 160

---

### Guides (new)

---

**Slug:** `guides/your-first-managed-agent`  
**Title:** Your First Managed Agent  
**Section:** Guides > Getting Started with Agents  
**Type:** Guide  
**Audience:** Developers  
**Priority:** P0  
**Dependencies:** `concepts/llm-integrations`, `concepts/agent-registry`  
**Brief:** End-to-end tutorial: register an Anthropic LLM integration → create a managed agent (triage-analyst role, system prompt, tool_ids, budget) → ingest a test alert → watch the agent check out the alert and post a finding. All steps via REST API with curl commands. Covers the 5-minute path using `make dev-agents` for a seeded testbed. Shows what a `HeartbeatRun` record looks like after the agent completes. Ends with: verify the finding in `GET /v1/alerts/{uuid}/findings`.  
**Lines (est):** 180

---

**Slug:** `guides/using-calseta-with-claude-code`  
**Title:** Using Calseta with Claude Code  
**Section:** Guides > Getting Started with Agents  
**Type:** Guide  
**Audience:** Both  
**Priority:** P0  
**Dependencies:** `cli/login-and-setup`  
**Brief:** Two modes: (1) Claude Code as a client via MCP (`calseta setup` → `calseta investigate <uuid>` → Claude uses Calseta tools), and (2) ClaudeCodeAdapter for managed agents (Calseta invokes `claude` subprocess for managed agents — dev/demo only). Covers `calseta setup` output in detail, what CLAUDE.md contains and why, and how to use `calseta investigate` interactively. Includes a full investigation walkthrough with screenshots or terminal output. Note why ClaudeCodeAdapter is not for production (subscription billing, no `budget_monthly_cents` tracking).  
**Lines (est):** 160

---

**Slug:** `guides/building-an-orchestrator`  
**Title:** Building an Orchestrator Agent  
**Section:** Guides > Building Agents  
**Type:** Guide  
**Audience:** Developers  
**Priority:** P0  
**Dependencies:** `concepts/multi-agent-orchestration`, `concepts/agent-registry`  
**Brief:** Build the lead-investigator pattern from scratch: register orchestrator + 3 specialists, configure `sub_agent_ids`, implement `select_specialists()` logic (indicator type → specialist mapping), call `POST /v1/invocations/parallel`, poll each invocation with `GET /v1/invocations/{uuid}/poll`, synthesize results, post finding. Uses the reference agent implementations in `examples/agents/` as starting points. Covers both the "managed" execution model (Calseta runs the LLM loop) and the "external" model (BYO script calling the API). Ends with testing the flow via `make dev-agents`.  
**Lines (est):** 200

---

**Slug:** `guides/human-in-the-loop-approvals`  
**Title:** Human-in-the-Loop Approval Flows  
**Section:** Guides > Building Agents  
**Type:** Guide  
**Audience:** Operators  
**Priority:** P1  
**Dependencies:** `concepts/response-actions`  
**Brief:** Configure the approval gate for agent-proposed actions. Covers three notification paths: Slack (bot token + channel config), browser approval page (`GET /v1/actions/{uuid}/decide` HTML page), and programmatic approve via API. Explains `APPROVAL_NOTIFIER` env var, how confidence thresholds affect approval mode, the `bypass_confidence_override=True` safety constraint for Entra ID actions, and rollback support. Includes a Slack approval flow screenshot/mockup and a complete curl-based test of propose → notify → approve → execute.  
**Lines (est):** 150

---

**Slug:** `guides/setting-up-kb-sync`  
**Title:** Setting Up KB Sync  
**Section:** Guides > Knowledge Management  
**Type:** Guide  
**Audience:** Operators  
**Priority:** P1  
**Dependencies:** `concepts/knowledge-base`  
**Brief:** Connect external knowledge sources to Calseta KB. Covers all three providers: GitHub (PAT via secret_ref, repo/path/branch config), Confluence (base_url + page_id + bearer token), and URL (plain HTTP, optional markitdown conversion). Step-by-step for each: create a KB page with `sync_source` JSONB, trigger first sync, verify content imported. Explains hash-based change detection (no DB writes if content unchanged), the 6-hour automatic sync schedule via procrastinate task, and how to trigger manual sync via `POST /v1/kb/{uuid}/sync`. Covers `inject_scope` assignment for synced pages.  
**Lines (est):** 160

---

**Slug:** `guides/writing-a-custom-action-integration`  
**Title:** Writing a Custom Action Integration  
**Section:** Guides > Building Agents  
**Type:** Guide  
**Audience:** Developers  
**Priority:** P2  
**Dependencies:** `concepts/response-actions`  
**Brief:** How to add a new response action integration (e.g., PagerDuty, Jira, custom webhook). Step-by-step: create `app/integrations/actions/my_tool_integration.py` subclassing `ActionIntegration`, implement `execute()` and optionally `rollback()`, set `default_approval_mode`, implement `is_configured()`, register in `registry.py`, add env var to `config.py`, write tests. Covers the never-raise contract (all errors as `ExecutionResult.fail(...)`), SSRF protection for webhook URLs, and how to document the integration for operators. Links to existing implementations as reference patterns.  
**Lines (est):** 150

---

### Integrations — Action Integrations (new)

---

**Slug:** `integrations/actions/crowdstrike`  
**Title:** CrowdStrike Falcon  
**Section:** Documentation > Integrations > Response Actions  
**Type:** Reference  
**Audience:** Operators  
**Priority:** P1  
**Dependencies:** `concepts/response-actions`  
**Brief:** Setup guide for CrowdStrike endpoint containment/lift integration. Covers required Falcon API scopes, `CROWDSTRIKE_CLIENT_ID`/`CROWDSTRIKE_CLIENT_SECRET` env vars, supported action subtypes (contain_host, lift_containment), payload shape, rollback support, and error diagnosis (OAuth2 token failure, device not found). Includes the API client permission configuration in Falcon UI.  
**Lines (est):** 100

---

**Slug:** `integrations/actions/entra-id`  
**Title:** Microsoft Entra ID (Identity Actions)  
**Section:** Documentation > Integrations > Response Actions  
**Type:** Reference  
**Audience:** Operators  
**Priority:** P1  
**Dependencies:** `concepts/response-actions`  
**Brief:** Setup for Entra ID identity response: disable_account, enable_account, revoke_sessions, force_mfa_reregistration. Covers `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, required Graph API permissions (`User.ReadWrite.All`, `UserAuthenticationMethod.ReadWrite.All`). Documents `bypass_confidence_override=True` — Entra ID always requires human approval regardless of confidence. Rollback support for disable_account (re-enables user).  
**Lines (est):** 100

---

**Slug:** `integrations/actions/slack`  
**Title:** Slack  
**Section:** Documentation > Integrations > Response Actions  
**Type:** Reference  
**Audience:** Operators  
**Priority:** P1  
**Dependencies:** `concepts/response-actions`  
**Brief:** Two Slack integrations: `SlackActionIntegration` (send_alert notifications, create_channel) and `SlackUserValidationIntegration` (DM + template rendering for user activity confirmation). Covers `SLACK_BOT_TOKEN`, bot scopes required (`chat:write`, `channels:manage`), user validation template format (DB-stored templates with `{{alert.title}}` placeholders), and common failures (channel_not_found, not_authed).  
**Lines (est):** 100

---

**Slug:** `integrations/actions/generic-webhook`  
**Title:** Generic Webhook  
**Section:** Documentation > Integrations > Response Actions  
**Type:** Reference  
**Audience:** Operators  
**Priority:** P1  
**Dependencies:** `concepts/response-actions`  
**Brief:** HTTP POST to any configurable URL. Covers action.payload shape (url, headers, body template), SSRF protection (private IPs blocked — use `SSRF_ALLOWED_HOSTS` in dev only), authentication options, and response handling. Use case: trigger n8n workflows, Logic Apps, Lambda functions, custom endpoints.  
**Lines (est):** 80

---

### KB Sync Integrations (new)

---

**Slug:** `integrations/kb-sync/github`  
**Title:** GitHub KB Sync  
**Section:** Documentation > Integrations > KB Sync  
**Type:** Reference  
**Audience:** Operators  
**Priority:** P1  
**Dependencies:** `concepts/knowledge-base`  
**Brief:** Sync KB pages from GitHub repos. Covers sync_config shape, PAT scopes needed (repo read), `secret_ref` pattern for PAT storage, GitHub Wiki support via `github_wiki` provider type, commit SHA tracking in `sync_source_ref`, and troubleshooting (401/404/rate limit).  
**Lines (est):** 80

---

**Slug:** `integrations/kb-sync/confluence`  
**Title:** Confluence KB Sync  
**Section:** Documentation > Integrations > KB Sync  
**Type:** Reference  
**Audience:** Operators  
**Priority:** P1  
**Dependencies:** `concepts/knowledge-base`  
**Brief:** Sync Confluence pages. Covers sync_config shape (base_url, page_id, auth token), best-effort Confluence storage XML → markdown conversion (headings, lists, code blocks), version number in `sync_source_ref`, and troubleshooting (401, page ID format).  
**Lines (est):** 80

---

**Slug:** `integrations/kb-sync/url`  
**Title:** URL KB Sync  
**Section:** Documentation > Integrations > KB Sync  
**Type:** Reference  
**Audience:** Operators  
**Priority:** P2  
**Dependencies:** `concepts/knowledge-base`  
**Brief:** Sync from any public URL. Covers HTML→markdown conversion via markitdown (optional, falls back to raw text), use cases (runbook on internal wiki, public threat feeds), and caveats (no auth support — use GitHub or Confluence providers for private content).  
**Lines (est):** 60

---

### MCP New Tools (new)

---

**Slug:** `mcp-reference/tools/save-memory`  
**Title:** save_memory  
**Section:** MCP Reference > Tools  
**Type:** Reference  
**Audience:** Developers  
**Priority:** P0  
**Dependencies:** `concepts/agent-memory`  
**Brief:** Tool for managed agents to persist state to agent memory. Parameters: title, slug, body, staleness_ttl_hours (optional). Writes to `/memory/agents/{agent.id}/`. Returns created page UUID and slug. Shows cURL and Python examples. Notes that memory is automatically injected into future prompts (5% context budget).  
**Lines (est):** 70

---

**Slug:** `mcp-reference/tools/recall-memory`  
**Title:** recall_memory  
**Section:** MCP Reference > Tools  
**Type:** Reference  
**Audience:** Developers  
**Priority:** P0  
**Dependencies:** `concepts/agent-memory`  
**Brief:** Tool for agents to search and retrieve specific memory pages. Parameters: query (full-text search), slug (exact lookup). Returns matching pages with stale indicator. Explains why agents should use this for targeted lookups while automatic injection handles ambient context.  
**Lines (est):** 60

---

**Slug:** `mcp-reference/tools/create-kb-page`  
**Title:** create_kb_page  
**Section:** MCP Reference > Tools  
**Type:** Reference  
**Audience:** Developers  
**Priority:** P1  
**Dependencies:** `concepts/knowledge-base`  
**Brief:** Create a KB page programmatically. Parameters: title, slug, body, folder, inject_scope, inject_pinned. Returns page UUID. Notes scope options and budget implications of inject_pinned.  
**Lines (est):** 60

---

**Slug:** `mcp-reference/tools/search-kb`  
**Title:** search_kb  
**Section:** MCP Reference > Tools  
**Type:** Reference  
**Audience:** Developers  
**Priority:** P1  
**Dependencies:** `concepts/knowledge-base`  
**Brief:** Full-text search across KB pages. Parameters: query, folder (optional filter), inject_scope (optional filter). Returns matching pages with snippet. Notes that automatic KB injection already occurs — use this tool only for targeted lookups beyond what's automatically injected.  
**Lines (est):** 60

---

**Slug:** `mcp-reference/tools/checkout-alert`  
**Title:** checkout_alert  
**Section:** MCP Reference > Tools  
**Type:** Reference  
**Audience:** Developers  
**Priority:** P1  
**Dependencies:** `concepts/alert-queue`  
**Brief:** Atomically check out an alert from the queue. Requires `cak_*` agent key. Parameters: alert_uuid. Returns assignment_id, status. Explains that only `cak_*` keys can checkout (operators cannot). Notes that the alert is now locked to this agent — release via `release_alert` or post a finding to complete.  
**Lines (est):** 60

---

**Slug:** `mcp-reference/tools/propose-action`  
**Title:** propose_action  
**Section:** MCP Reference > Tools  
**Type:** Reference  
**Audience:** Developers  
**Priority:** P1  
**Dependencies:** `concepts/response-actions`  
**Brief:** Propose a response action for human review. Requires `cak_*` agent key. Parameters: action_type, action_subtype, payload (integration-specific), confidence (0.0–1.0), reason. Returns action UUID and resolved approval mode. Explains how confidence affects what happens next (auto-approve / quick_review / human_review / block).  
**Lines (est):** 70

---

**Slug:** `mcp-reference/tools/list-actions`  
**Title:** list_actions  
**Section:** MCP Reference > Tools  
**Type:** Reference  
**Audience:** Developers  
**Priority:** P2  
**Dependencies:** `concepts/response-actions`  
**Brief:** List pending/recent actions. Agents use this to check if their proposed actions have been approved or rejected. Parameters: status filter, alert_uuid filter. Returns action list with current status and any rejection reason.  
**Lines (est):** 60

---

### Contributing (new page)

---

**Slug:** `contributing/adding-action-integrations`  
**Title:** Adding Action Integrations  
**Section:** Documentation > Contributing  
**Type:** Guide  
**Audience:** Developers  
**Priority:** P2  
**Dependencies:** `guides/writing-a-custom-action-integration`  
**Brief:** Community contributor guide for submitting a new action integration to the Calseta repo. Covers the 5-step pattern (create file, add env var, register in registry, write tests, add docs), required test coverage (never-raise, rollback support, `is_configured()` false path), and the PR checklist. Points to existing integrations as style references. Explains the difference between a community action integration and a generic webhook workflow.  
**Lines (est):** 100

---

### Existing Page Updates

| Page | What to add/change | Priority |
|---|---|---|
| `concepts/alert-schema` | Add `agent_findings[]` field, `assignment` object (assignment_id, agent, status, investigation_state), note `malice` field (worst across indicators) | P0 |
| `concepts/authentication` | Add v2 agent key section (`cak_*` prefix, created via `POST /v1/agents/{uuid}/keys`, used for queue/checkout/invocation endpoints, returns 403 with wrong key type) | P0 |
| `getting-started/quickstart` | Add `make dev-agents` step, add CLI install (`pip install calseta-cli`) | P0 |
| `mcp-reference/overview` | Add v2 tools table (save_memory, recall_memory, create_kb_page, search_kb, checkout_alert, propose_action, list_actions); add v2 resources (kb-pages, queue); add note that MCP tool scope differs from v2 agent tools | P0 |
| `integrations/agent-webhooks` | Replace with redirect to `concepts/agent-registry`, or overhaul to be the external/BYO agent setup guide (keep webhook content, add managed agent setup) | P1 |
| `operations/self-hosting` | Add `make dev-agents` one-command testbed section; mention `ENRICHMENT_STUB=true` for testing without real provider API keys | P1 |
| `api-reference/overview` | Add cak_* agent key documentation, explain 403 behavior when using wrong key type | P1 |
| `api-reference/agents/register` | All new v2 fields | P1 |

---

## 4. openapi.json Update Requirements

The `openapi.json` currently covers v1 endpoints only. Every v2 API Reference page requires the endpoint to be defined in the spec.

| Route Group | Prefix | New endpoints (count) | Est. API Reference pages |
|---|---|---|---|
| LLM Integrations | `/v1/llm-integrations` | CRUD + usage = 6 | 6 |
| Alert Queue | `/v1/queue`, `/v1/assignments`, `/v1/dashboard` | checkout, release, mine, list-q, dashboard + assignments CRUD = 9 | 8 |
| Actions | `/v1/actions` | propose, list, get, approve, reject, cancel = 6 | 6 |
| Invocations | `/v1/invocations` | delegate, parallel, get, poll, patch, history = 6 | 6 |
| Agent Tools | `/v1/tools` | list, get, register, update, delete = 5 | 5 |
| Knowledge Base | `/v1/kb` | CRUD + search + folders + sync + revisions = 9 | 9 |
| Memory | `/v1/memory`, `/v1/agents/{uuid}/memory` | CRUD + promote = 6 | 6 |
| Issues | `/v1/issues` | CRUD + checkout + release + comments = 8 | 8 |
| Routines | `/v1/routines` | CRUD + pause + resume + trigger + runs = 9 | 9 |
| Campaigns | `/v1/campaigns` | CRUD + items = 6 | 6 |
| Secrets | `/v1/secrets` | CRUD + rotate + versions = 6 | 6 |
| Heartbeat & Costs | `/v1/heartbeat`, `/v1/heartbeat-runs`, `/v1/cost-events`, `/v1/costs` | record + runs-list + runs-get + cost-events + summaries = 7 | 7 |
| Topology & Sessions | `/v1/topology`, `/v1/sessions` | topology + routing + sessions = 4 | 4 |
| Agents v2 additions | `/v1/agents` extensions | pause + resume + terminate + key CRUD + file CRUD = 8 | 8 |
| **Total** | | **~95 new endpoints** | **~94 new API ref pages** |

**openapi.json work estimate:** The existing spec is ~307KB covering ~60 endpoints. Adding 95 new endpoints with full request/response schemas is a significant expansion — estimated ~180KB additional spec content. This should be auto-generated from FastAPI's `/openapi.json` endpoint on a running v2 server, then committed to the docs repo.

**Recommended approach:** Run `docker compose up`, hit `GET /openapi.json`, copy to docs repo. Do not hand-write the spec.

---

## 5. Writing Effort Estimate

### Line Counts by Page Type

| Type | Typical lines | Count in this PRD |
|---|---|---|
| Deep-dive concept | 150–200 | 10 |
| Standard concept | 100–150 | 5 |
| Full guide | 150–200 | 6 |
| Short guide | 80–120 | 4 |
| Integration setup | 80–100 | 7 |
| MCP tool reference | 60–70 | 7 |
| CLI reference | 100–160 | 4 |
| Contributing guide | 80–100 | 1 |
| Existing page updates | 30–50 per update | 8 updates |

### Totals

| Category | Page count | Estimated lines |
|---|---|---|
| New concept pages | 14 | ~1,900 |
| New guide pages | 6 | ~1,020 |
| New CLI pages | 4 | ~480 |
| New action integration pages | 4 | ~380 |
| New KB sync integration pages | 3 | ~220 |
| New MCP tool pages | 7 | ~440 |
| New contributing page | 1 | ~100 |
| Updates to existing pages | 8 | ~320 |
| **Primary content total** | **47 pages** | **~4,860 lines** |
| API Reference pages (openapi-driven) | ~94 | ~100–150 lines each = ~12,000 lines |
| **Grand total** | **~141 pages** | **~17,000 lines** |

The API Reference pages are largely auto-generated from the openapi.json spec by Mintlify — the manual writing effort is the 47 primary content pages (~4,860 lines). At 150 lines/hour for a writer familiar with the codebase, that's approximately **32 hours of writing effort** for primary content, plus ~8 hours for openapi.json generation and verification.

---

## 6. Phased Rollout Recommendation

### Phase 1 — P0: Launch Blockers

These pages are completely absent for shipped features. Any operator trying to use v2 will immediately hit a dead end without them.

**Must ship before publicizing v2:**

| Page | Why it's blocking |
|---|---|
| `concepts/llm-integrations` | Can't create a managed agent without understanding this |
| `concepts/agent-registry` | The registration step has ~15 new fields with no docs |
| `concepts/agent-runtime` | Operators need to understand what Calseta does during execution |
| `concepts/alert-queue` | The pull model is a fundamental behavior change from v1 push |
| `concepts/tool-system` | Tier system blocks tool calls silently if misconfigured |
| `concepts/response-actions` | Actions stuck in pending with no docs = support tickets |
| `concepts/multi-agent-orchestration` | Delegation is the primary v2 use case |
| `concepts/knowledge-base` | KB injection is in every managed agent run |
| `guides/your-first-managed-agent` | Without this, there's no path to first success |
| `guides/using-calseta-with-claude-code` | Highest-value integration; `calseta setup` output is unexplained |
| `guides/building-an-orchestrator` | The lead-investigator pattern is the anchor demo |
| `cli/overview` | CLI ships with v2; zero docs |
| `cli/login-and-setup` | Prerequisite for all CLI use |
| `cli/investigate` | The anchor CLI command |
| `mcp-reference/overview` (update) | Current page is missing all v2 tools |
| `concepts/authentication` (update) | `cak_*` keys appear in every v2 code sample |
| `concepts/alert-schema` (update) | `agent_findings` and `assignment` fields appear in API responses |
| `getting-started/quickstart` (update) | `make dev-agents` is the fastest v2 on-ramp |

**Phase 1 total:** 15 new pages + 4 updates

---

### Phase 2 — P1: Important Gaps

Core features covered, but significant gaps remain for production deployments.

| Page | Why it's important |
|---|---|
| `concepts/agent-memory` | Memory injection is in every managed agent run |
| `concepts/issues-and-routines` | Routines are a key automation pattern |
| `concepts/secrets-management` | Required for production API key storage |
| `guides/human-in-the-loop-approvals` | CrowdStrike/Entra actions stuck in pending without this |
| `guides/setting-up-kb-sync` | Operators need to populate KB from existing runbooks |
| `cli/command-reference` | Full CLI reference for power users |
| `integrations/actions/crowdstrike` | First production response action integration |
| `integrations/actions/entra-id` | Identity response is the #1 use case |
| `integrations/actions/slack` | Notification actions + user validation |
| `integrations/actions/generic-webhook` | Custom integration path for everything else |
| `integrations/kb-sync/github` | Primary KB sync source for runbooks |
| `integrations/kb-sync/confluence` | Enterprise knowledge base sync |
| `mcp-reference/tools/save-memory` | Memory tools are in the generated CLAUDE.md |
| `mcp-reference/tools/recall-memory` | Paired with save-memory |
| `mcp-reference/tools/checkout-alert` | Queue tools needed for external agents using MCP |
| `mcp-reference/tools/propose-action` | Action proposal via MCP |
| `integrations/agent-webhooks` (overhaul) | V1 page is actively misleading for v2 users |
| `api-reference/overview` (update) | `cak_*` key type needs documentation in the API tab |
| openapi.json v2 endpoints | All API Reference pages are blocked until spec is updated |

**Phase 2 total:** 16 new pages + 3 updates + openapi.json generation

---

### Phase 3 — P2: Polish

Nice-to-have for completeness and developer experience.

| Page | Description |
|---|---|
| `concepts/agent-topology` | Fleet graph visualization docs |
| `concepts/heartbeat` | Budget and liveness monitoring details |
| `concepts/campaigns` | Grouping patterns for complex investigations |
| `guides/writing-a-custom-action-integration` | Developer guide for custom integrations |
| `integrations/kb-sync/url` | URL sync for simple cases |
| `mcp-reference/tools/create-kb-page` | MCP tool for KB page creation |
| `mcp-reference/tools/search-kb` | MCP tool for KB search |
| `mcp-reference/tools/list-actions` | MCP tool for action status |
| `contributing/adding-action-integrations` | Community contribution guide |
| Remove `essentials/` from nav | Clean up Mintlify boilerplate |
| `mcp-reference/resources/kb-pages` | New MCP resource |
| `mcp-reference/resources/queue` | New MCP resource |

**Phase 3 total:** 12 new pages + 1 nav cleanup

---

## Summary

| Metric | Count |
|---|---|
| **Total new pages proposed** | **47** (primary content) + ~94 (API reference) = ~141 |
| **P0 pages (launch blockers)** | **15 new + 4 updates** |
| **P1 pages** | **16 new + 3 updates** |
| **P2 pages** | **12 new + 1 cleanup** |
| **Pages to remove from nav** | 2 (`essentials/*`, `integrations/agent-webhooks`) |
| **Existing pages updated** | 8 |
| **Estimated writing effort (primary content)** | ~32 hours |
| **openapi.json new endpoints** | ~95 |

**Biggest structural change:** Separating "Guides" into its own tab (currently it's a single page in the Documentation tab). This reflects the audience split — operators reading concepts vs developers following step-by-step guides. The Agent Platform grows large enough that burying it inside "Concepts" would make the Documentation tab overwhelming.

**Biggest surprise — the confuser:** The `integrations/agent-webhooks.mdx` page is actively misleading for v2 users. It describes only push-based webhook dispatch, which is the v1 model. A developer reading it will try to build a webhook receiver when they should be building a managed agent with `execution_mode=managed` or an external agent using `cak_*` keys. This page should either be archived immediately or prominently flagged as "V1 Push Model Only" with a banner pointing to `concepts/agent-registry`.

A close second: `concepts/authentication` makes no mention of `cak_*` agent keys — but every v2 code sample uses them, and using the wrong key type returns a 403 with no explanation. New developers will be confused by this until they read the error carefully.

**Recommendation:** Phase 1 can be split into two mini-sprints:
- Sprint 1a (blocking concepts, ~2 days): The 8 concept pages + 3 page updates
- Sprint 1b (guides + CLI, ~2 days): The 7 guide/CLI pages

The openapi.json update (Phase 2) is the fastest leverage: one `curl http://localhost:8000/openapi.json` generates ~94 API Reference pages automatically via Mintlify.
