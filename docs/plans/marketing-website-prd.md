# Marketing Website PRD — v2 Update

## Summary

Calseta v1 was a pure data layer: ingest alerts, enrich indicators, normalize to a clean schema, deliver payloads to customer-built agents via webhook or MCP. The v2 agent control plane — which has shipped across Phases 1–6 on `feat/calseta-v2` — adds a full agent execution runtime on top of that foundation: LLM provider management, managed agent execution (Calseta runs the LLM conversation), multi-agent orchestration with delegation, response action proposals and approval gates, budget and heartbeat supervision, a knowledge base with context injection, persistent agent memory, issues/routines/campaigns for non-alert work, and a fleet topology view. The current marketing website describes only the v1 data pipeline, explicitly states "Calseta is NOT an AI SOC product — it does not build, host, or run AI agents," and has zero marketing presence for any v2 capability. That statement is now factually wrong and undersells the product by approximately an order of magnitude.

---

## Current State Audit

| Page / Section | Current Claim | Gap | Priority |
|---|---|---|---|
| Site title / meta description | "The data layer for your security agents" | Data layer framing undersells v2; needs to reflect agent platform | P0 |
| Hero headline | "The data layer for your security agents" | Misses the runtime/orchestration layer; BYO-only framing | P0 |
| Hero subtitle | "Calseta ingests security alerts, enriches indicators, and delivers normalized, context-rich payloads — so agents focus on reasoning and response, not plumbing." | Stops at delivery; v2 executes the agents too | P0 |
| Problem section | Three problems: context gap, integration burden, token waste | Missing the governance/control gap: no visibility into what agents do, no cost controls, no approval gates, no way to run agents at all | P1 |
| Solution section | Three cards: Enriched, Agent-ready, Contextualized | No mention of agent runtime, orchestration, or governance | P0 |
| Features section | 8 features, all v1 data layer | Missing: LLM provider management, managed agents, multi-agent orchestration, response actions, budget controls, heartbeat supervision, KB, memory, issues/routines | P0 |
| CLAUDE.md (brand source of truth) | "Calseta is NOT an AI SOC product. It does not build, host, or run AI agents." | This statement is now incorrect; v2 runs agents natively | P0 |
| BRAND_GUIDELINES.md | Tagline: "The data layer for your security agents." | Tagline needs updating for v2 | P0 |
| CTA section | "One alert. Zero tokens wasted. That's what your agents deserve." | Token efficiency framing still valid but too narrow; misses control plane value prop | P1 |
| Alert Journey page | 8-phase walkthrough: ingest → normalize → enrich → contextualize → dispatch → workflow → approval → resolution | Shows the v1 pipeline well. Missing the v2 path where Calseta itself runs the agent through all phases — no "managed agent" branch in the journey | P1 |
| Navigation | Alert Journey, Case Study, Cloud | No "Agents" or "Control Plane" nav item; no product page | P0 |
| Integrations section | Scrolling badge list of sources, providers, agent frameworks | Does not communicate that Calseta now runs these agents — just that they integrate | P2 |
| Benchmark section | "92% fewer tokens. Comparable quality." | Strong v1 proof point; remains valid but needs a v2 companion framing around cost control and agent governance | P2 |
| OSS section | "Apache 2.0. Your data stays yours." | Strong. Keep. | — |
| `/product` route | Redirects to `/alert-journey` | Should be a real product page | P1 |
| `/about` route | Redirects to home | No about page | P2 |

---

## Proposed Changes (by page)

### Home — `app/page.tsx`

**Keep:** OSS section (Apache 2.0 framing), benchmark stats (token reduction proof point), integrations scroll (ecosystem breadth), pipeline visualization.

**Rewrite: Site title, meta description, and page metadata**

```
title: "Calseta — The open-source AI SOC platform"
description: "Open-source, self-hostable platform for security AI agents.
  Ingest and enrich alerts, run managed agents, orchestrate multi-agent
  investigations — with approval gates, budget controls, and full audit
  trails. Self-host in under an hour."
```

**Rewrite: Hero section**

Headline (option A — v2 positioning, keeps brand voice):
```
The open-source
AI SOC platform.
```

Headline (option B — action-oriented, positions against black-box vendors):
```
Run security agents
you actually control.
```

Subtitle:
```
Calseta ingests alerts, enriches indicators, and runs your security agents —
managed or BYO. Multi-agent orchestration, approval gates, budget controls,
and full audit trails. Apache 2.0. Self-host it.
```

The hero badge should change from `open source · Apache 2.0 · self-hostable` to add context:
```
v2 · agent control plane · Apache 2.0 · self-hostable
```

**Rewrite: Problem section**

Add a fourth problem card. The current three (context gap, integration burden, token waste) remain valid. Add:

```
4. No governance
Your agents run unsupervised. No visibility into cost, no approval gates
before high-impact actions, no way to know if an agent is stuck or
running up a bill. Security automation without oversight is a liability.
tag: zero visibility
```

**Rewrite: Solution section**

Current cards (Enriched, Agent-ready, Contextualized) address the data layer only. Replace or expand to reflect the full platform:

```
Card 1: Enriched (keep — still accurate)

Card 2: Executed
  "Calseta runs your agents. Register an LLM provider, define a system
  prompt and toolset, and Calseta handles the full investigation loop —
  tool calls, cost tracking, session state, and findings — without any
  agent runtime to build yourself."
  tag: managed execution

Card 3: Governed
  "Every agent action goes through the platform. Approval gates for
  high-risk responses. Budget hard-stops by agent. Heartbeat monitoring
  with automatic stuck-agent recovery. Multi-agent orchestration with
  full delegation trees."
  tag: human-in-the-loop
```

**Rewrite: Features section**

Add the following new feature cards to the existing eight. Current cards remain but need updated copy for "Executable workflows" (now also callable as agent tools):

New cards to add:
```
- LLM provider management
  "Register Anthropic, OpenAI, or any compatible provider. Track spend
  per agent, per model, per alert. Set monthly budget limits with
  auto-pause at threshold."
  tags: cost tracking, multi-provider

- Managed agent runtime
  "Define agents with a system prompt, methodology, toolset, and LLM.
  Calseta runs the full tool loop — tool calls, results, session state,
  handoff summaries. You own the prompt; Calseta handles execution."
  tags: tool loop, session state

- Multi-agent orchestration
  "Orchestrator agents delegate to specialists in parallel. Full
  delegation tree tracked with cost rollup. Specialists can be managed
  (Calseta runs them) or BYO (any HTTP-callable agent)."
  tags: parallel delegation, framework-agnostic

- Response actions
  "Agents propose block IP, disable user, isolate host actions.
  Each action routes through the approval gate before execution.
  Full rollback support. CrowdStrike, Entra, Slack integrations ship
  out of the box."
  tags: containment, approval gate

- Knowledge base
  "Store runbooks, IR playbooks, and organizational context in
  the KB. Pages auto-inject into agent prompts by role, agent,
  or global scope. Sync from GitHub, Confluence, or URL."
  tags: context injection, versioned

- Agent memory
  "Agents write observations during investigations. Relevant
  memories auto-inject into future sessions. Promote to KB for
  team-wide sharing. TTL-based staleness with approval controls."
  tags: persistent, cross-session

- Issues and routines
  "Non-alert work: remediation tasks, detection tuning, compliance.
  Scheduled routines trigger agents on cron or webhook. Campaign
  tracking with auto-computed MTTD, FP rate, and auto-resolve metrics."
  tags: scheduled, non-alert work

- Fleet visibility
  "Agent topology graph shows routing paths, delegation chains, and
  sub-agent relationships. Heartbeat monitoring detects stuck or
  stalled agents and releases assignments automatically."
  tags: topology, supervision
```

**Update: CTA section**

Keep the token efficiency framing but add a second line that addresses governance:

```
headline: "One platform. Every alert investigated."
subheadline: "Your agents run it. You control it."
body: "Ingest, enrich, execute, govern — from raw webhook to closed investigation.
Open source. Self-hostable. Apache 2.0."
```

---

### Alert Journey page — `/alert-journey`

**Keep:** The existing 8-phase linear walkthrough describes the v1 pipeline accurately and is well-executed.

**Add:** A new "Managed Agent" callout/branch at the Dispatch phase (Phase 5), explaining that in v2, Calseta doesn't just deliver the payload — it can execute the entire investigation loop natively. Consider a mode toggle: "BYO Agent" (current journey) vs "Managed Agent" (v2 path).

**Update meta description:** Reference that Calseta can now run the investigation, not just dispatch to it.

---

### Product page — `/product`

Currently redirects to `/alert-journey`. This should become a real product page.

**Convert to:** Full product feature page. See "New Pages to Create" section below.

---

### Navigation

Current nav: `Alert Journey | Case Study | Cloud`

**Proposed nav:**
```
Agents | Alert Journey | Case Study | Cloud
```

Where "Agents" links to the new `/agents` product page. Consider also adding a "Docs" external link or a "GitHub" ghost button in the nav bar (these currently appear in hero CTAs but not in the persistent nav).

---

## New Pages to Create

### 1. Agent Control Plane — `/agents`

**Purpose:** Primary product page for v2. Explains the full platform: managed execution, orchestration, approval gates, budget controls, KB, memory.

**Target audience:** Security engineers evaluating whether to build their own agent infrastructure vs. use Calseta.

**Key sections:**
1. Hero — "Run security agents you control." — one sentence positioning, CTA to docs/GitHub
2. Two modes — Managed vs. BYO comparison table (mirrors `_overview.md` competitive table)
3. Feature breakdown — LLM providers, runtime engine, orchestration, response actions, KB+memory
4. Governance section — budget controls, approval gates, heartbeat supervision
5. Architecture diagram — the control plane layer over the v1 pipeline
6. Competitive matrix — vs. Dropzone, Prophet, Simbian (open source advantage)
7. Reference agents — link to `examples/agents/AGENTS.md` pattern
8. CTA — `docker compose up` + docs link

**URL slug:** `/agents`

---

### 2. Comparison / vs. Closed-Source AI SOC — `/vs-black-box`

**Purpose:** Targeted landing page for security engineers who have evaluated or are evaluating Dropzone, Prophet, Simbian, or similar products.

**Target audience:** Security engineers and CISOs making a buy/build decision.

**Key sections:**
1. "You shouldn't have to trust a black box with your security data."
2. Feature comparison table (mirrors the competitive matrix in `_overview.md`)
3. Three differentiators: open source, self-hostable, you own the agent logic
4. CTA to docs + GitHub

**URL slug:** `/vs-black-box` (also consider `/open-source-ai-soc`)

---

### 3. Docs redirect / getting started — `/docs` (optional)

A simple redirect to `docs.calseta.com`. Currently docs links go directly to the external URL. A canonical `/docs` route improves SEO and link consistency.

---

## Positioning Recommendations

### Primary message — what Calseta v2 is in one sentence

**Current:** "The data layer for your security agents."

**Proposed:** "The open-source platform for running and governing security AI agents."

**Rationale:** v2 ships a full agent runtime and control plane. "Data layer" is accurate for v1 but no longer captures what the product does — it now executes agents, not just feeds them. "Platform" was previously avoided (brand guidelines flagged it as implying a walled garden), but the v2 reality is a platform: it has a runtime, a registry, a governance layer, and an operator UI. The brand guideline concern was about vendor lock-in, not about the word itself — the Apache 2.0 and self-hostable qualifiers defuse that.

**Alternative if "platform" stays off the table:**
"The open-source agent control plane for security operations."

---

### What to stop saying

1. **"Calseta is NOT an AI SOC product — it does not build, host, or run AI agents."** This is in the marketing CLAUDE.md and the product description. It is now factually incorrect. v2 runs managed agents natively. Remove or replace everywhere.

2. **"The data layer for your security agents."** As a primary positioning statement, this undersells v2. Acceptable as a secondary description of the v1 pipeline component, but should not be the lead.

3. **"So your agents spend tokens on reasoning, not plumbing."** This framing positions Calseta purely as a cost-reduction tool for agents the customer already has. v2 is also the runtime for agents the customer doesn't have yet. Supplement with execution-centric copy.

4. **"Prefer 'layer', 'infrastructure', 'engine' over 'platform'."** This brand guideline made sense for v1. v2's scope — agent runtime, registry, governance, UI — justifies "platform." Revisit this constraint.

---

### The core comparison

v2's competitive set has expanded. v1 competed with "building your own enrichment pipeline." v2 competes with:

- **Closed-source AI SOC vendors** (Dropzone, Prophet, Simbian) — the differentiator is open source, self-hostable, and BYO agent logic
- **SOAR platforms** (Tines, Torq) — the differentiator is agent-native architecture, multi-agent orchestration, and token-efficient data delivery
- **Building it yourself** — the differentiator is the time cost of building agent runtime, approval gates, budget controls, KB injection, and memory from scratch

The marketing site should address all three comparisons. Currently it addresses none.

---

### Developer vs. operator audience split

The current site speaks exclusively to the **builder persona**: clone a repo, run Docker Compose, write a Python class. This remains the right primary audience.

v2 adds a second distinct audience: the **security operator** who uses the Calseta UI to manage agents, review approval requests, monitor budgets, and interpret investigation findings — without writing code. The operator UI ships in Phase 6.5.

Recommended approach:
- Keep the developer/builder framing as the primary voice on the home page and docs
- Add a secondary "For operators" section or callout that speaks to the governance and visibility capabilities
- The `/agents` product page should address both audiences explicitly

---

## Implementation Notes

### Brand / design changes needed

1. **Update CLAUDE.md in the marketing repo** — remove the "Calseta is NOT an AI agent product" statement; update the tagline and one-liner to reflect v2
2. **Update BRAND_GUIDELINES.md** — revise tagline, one-liner, and the "what we avoid saying" section to permit "platform" with the self-hostable qualifier
3. **New section design pattern needed:** The v2 feature additions (managed agents, orchestration, governance) are more complex than the current card-based feature sections. Consider a tabbed feature section or a two-column feature breakdown with code/diagram examples alongside copy
4. **Architecture diagram:** The `_overview.md` ASCII architecture diagram (showing Managed vs BYO paths) should be visualized as a designed SVG/component for use on the `/agents` page and potentially the home page

### Copy assets needed before implementation

1. Hero headline A/B test variants (2–3 options)
2. Full `/agents` page copy — all sections
3. Updated problem section — fourth problem card (governance gap)
4. Updated solution section — three new cards
5. Eight new feature card blurbs (listed above)
6. Competitive comparison table copy
7. New CTA section variants
8. `/vs-black-box` page copy

### SEO / metadata updates needed

Current keywords are all v1 data layer terms. Add:
- "AI SOC platform", "agent control plane", "security agent orchestration"
- "managed security agents", "open source SOAR alternative"
- "multi-agent security", "LLM cost controls security"
- Remove or de-prioritize: "security data layer" (too narrow)

### What does NOT need to change immediately

- Color palette, typography, animation patterns — all remain appropriate
- OSS section (Apache 2.0 messaging is strong)
- Benchmark section (token reduction proof point remains accurate and compelling)
- Alert Journey page structure (accurate for v1 pipeline; only needs a v2 branch added)
- Integrations scroll (ecosystem breadth messaging is still accurate)
- The overall dark, terminal-aesthetic design system
