# Calseta — MVP Launch Plan

**Version:** 1.0
**Last Updated:** 2026-03-06
**Branch:** `feat/mvp-dev` → merge to `main`
**Executor:** Jorge + Claude Code subagents

---

## Table of Contents

1. [What Calseta Is](#1-what-calseta-ai-is)
2. [Current Status](#2-current-status)
3. [Launch Phases](#3-launch-phases)
4. [Architecture Reference](#4-architecture-reference)
5. [Data Model Reference](#5-data-model-reference)
6. [API Reference](#6-api-reference)
7. [Plugin Interfaces](#7-plugin-interfaces)
8. [Integration Catalog v1](#8-integration-catalog-v1)
9. [MCP Server](#9-mcp-server)
10. [Enums & Constants](#10-enums--constants)
11. [Out of Scope v1](#11-out-of-scope-v1)
12. [Post-v1 Roadmap](#12-post-v1-roadmap)
13. [Success Criteria](#13-success-criteria)

---

## 1. What Calseta Is

Calseta is an open-source, single-tenant, self-hostable SOC data platform built for AI agent consumption. It is **not** an AI SOC product — it does not build or run AI agents.

It is the data infrastructure layer:
- **Ingest** security alerts from Sentinel, Elastic, Splunk, or any webhook
- **Normalize** to a clean agent-native schema (`CalsetaAlert`)
- **Enrich** with threat intelligence (VirusTotal, AbuseIPDB, Okta, Entra)
- **Expose** structured, context-rich data via REST API and MCP server

Agents built by customers — using any framework (LangChain, CrewAI, raw Claude/OpenAI, n8n, Slack bots) — connect to Calseta and get exactly what they need to investigate and respond. No custom integrations, no wasted tokens, no black boxes.

**Core principles:**
1. Deterministic operations stay deterministic — enrichment, normalization, workflows never consume LLM tokens
2. Token optimization is first-class — every response gives agents exactly what they need
3. AI-readable documentation is a feature — every entity has a `documentation` field surfaced through API/MCP
4. Framework agnostic — REST + MCP work with any agent framework
5. Self-hostable without pain — single `docker compose up`

**Target user:** Technical builder (CTO, Security Engineer, Cloud Engineer) at a 50-2000 employee company who can clone a repo, run Docker Compose, and write Python. Not necessarily a security expert by title, but responsible for security alert response.

---

## 2. Current Status

### What's Built

All platform application code is complete (Waves 1-7, 61/61 chunks).

| Component | Status |
|---|---|
| FastAPI server + all routes | Complete |
| PostgreSQL schema (15 tables + migrations) | Complete |
| Alert ingestion + normalization pipeline | Complete |
| Indicator extraction (3-pass) | Complete |
| Enrichment engine (database-driven) | Complete |
| 4 builtin enrichment providers (VT, AbuseIPDB, Okta, Entra) | Complete |
| Custom enrichment provider CRUD API | Complete |
| Task queue (procrastinate + Postgres) | Complete |
| Worker process | Complete |
| Workflow engine + sandbox + approval gate | Complete |
| MCP server (12 resources + 6 tools) | Complete |
| API key auth + security middleware | Complete |
| Agent registration + webhook dispatch | Complete |
| Activity events (audit log) | Complete |
| Context documents + targeting | Complete |
| Detection rules + MITRE mapping | Complete |
| Metrics endpoint | Complete |
| Seed data (sandbox + enrichment providers) | Complete |
| Frontend UI (React + Vite) | Complete |

### Open Issues

- 1 bug: AbuseIPDB DB-driven provider returning HTTP 422
- `make ci` (lint + typecheck + test) needs a clean pass
- Worker enrichment registry not loading — `enrichment_results` stays `{}`, `malice` stays `Pending` (fix applied in `app/worker.py`: added `_load_enrichment_registry()` — needs rebuild to verify)
- `agent_webhook_dispatched` activity event not being written (fix applied: added event type to schema + writes in dispatch tasks — needs rebuild to verify)
- Slack/Teams approval bot not yet tested end-to-end (Phases 12-13 in prior QA plan)
- `docs/workflows/examples/` directory never created

### What Remains

Bug fixes, rebuild verification, lab environment, case study, and launch content (Phases 1-8 below).

---

## 3. Launch Phases

### Phase 1: Fix Bugs + Run Tests

**Goal:** Green `make ci` — the gate for everything else.

#### 1.1 Fix AbuseIPDB 422

**Problem:** The database-driven AbuseIPDB provider returns HTTP 422 when called via the enrichment pipeline.

**Investigation path:**
1. Compare `app/seed/enrichment_providers.py` AbuseIPDB `http_config` against the static implementation in `app/integrations/enrichment/abuseipdb.py`
2. Check the `GenericHttpEnrichmentEngine` request construction — likely a query param vs header vs body mismatch
3. Verify the seeded `auth_config` has the right `auth_type` and template variable placement
4. Test fix by running `make dev` and hitting `POST /v1/enrichment/enrich` with a known IP

**Files to inspect:**
- `app/seed/enrichment_providers.py` — AbuseIPDB seed config
- `app/integrations/enrichment/engine.py` — `GenericHttpEnrichmentEngine`
- `app/integrations/enrichment/abuseipdb.py` — static reference implementation
- `docs/integrations/abuseipdb/api_notes.md` — API contract

#### 1.2 Run `make ci`

```bash
make lint       # ruff check app/ tests/
make typecheck  # mypy app/ tests/
make test       # pytest tests/ -v
```

Fix all failures. Common patterns: missing type annotations, unused imports, test fixtures referencing old schema.

#### 1.3 Rebuild Verification

These bugs were found during manual QA and fixes were applied but never verified after rebuild:

1. **Worker enrichment registry** — `app/worker.py` was missing `_load_enrichment_registry()` call. Without it, the worker enriches alerts but `enrichment_results` stays `{}` and `malice` stays `Pending`. Verify by ingesting an alert and confirming indicators get populated `enrichment_results` and a non-`Pending` `malice` verdict.
2. **`agent_webhook_dispatched` activity event** — Event type was missing from schema and dispatch service didn't write activity events. Fix added `AGENT_WEBHOOK_DISPATCHED` to `ActivityEventType` and activity event writes to dispatch tasks. Verify by ingesting a High/Critical alert with a registered agent and checking `GET /v1/alerts/{uuid}/activity` for the event.
3. **Slack approval bot** — Full interactive flow untested: trigger agent workflow → Slack message appears with buttons → click Approve → workflow executes. Requires ngrok tunnel + Slack app configured per `.env`.
4. **Teams approval bot** — Adaptive Card posting untested. Requires Teams incoming webhook URL configured per `.env`.

**Acceptance:** `make ci` passes. AbuseIPDB enriches an IP without error. All 4 rebuild items verified (Slack/Teams can be deferred if no test workspace available).

---

### Phase 2: Set Up the Lab

**Goal:** `make lab` gives anyone a fully seeded, enrichment-ready Calseta instance in one command.

The existing 5 case study fixtures already cover the core scenarios (brute force, malware, exfil, impossible travel, C2). That's enough for launch — additional fixtures can be added post-merge.

#### 2.1 Lab Seed Fixtures

Use the existing 5 case study fixtures (in `examples/case_study/fixtures/`):

| # | Source | Scenario |
|---|---|---|
| 01 | Sentinel | Brute force from TOR exit node |
| 02 | Elastic | Known malware (Emotet) on endpoint |
| 03 | Splunk | 2GB+ data exfiltration |
| 04 | Sentinel | Impossible travel (NY → Moscow, 32 min) |
| 05 | Elastic | Encoded PowerShell + C2 beacon |

#### 2.2 `make lab` Wiring

1. **Create** `.env.lab.example` — lab environment template with enrichment keys + mock mode option
2. **Add Makefile targets:** `lab` (starts stack, runs migrations, seeds sandbox data), `lab-reset` (down -v + lab), `lab-stop`, `case-study`
3. **Lab API key** with full scopes (not read-only like sandbox): `cai_lab_demo_full_access_key_not_for_prod`

The `make lab` target runs the existing sandbox seeder which already seeds detection rules, context documents, and the 5 case study alerts.

#### 2.3 Files to Create/Edit

| Action | File |
|---|---|
| Create | `.env.lab.example` |
| Edit | `Makefile` — add `lab`, `lab-reset`, `lab-stop`, `case-study` targets |

**Acceptance:** `make lab` starts a fully seeded instance with 5 alerts, all enriched, with detection rules and context documents. `curl -H "Authorization: Bearer cai_lab_demo_full_access_key_not_for_prod" http://localhost:8000/v1/alerts` returns 5 alerts.

---

### Phase 3: Run Case Study

**Goal:** Quantified proof that Calseta reduces token consumption by >=50%, with cost projections at scale.

#### 3.1 Multi-Model Support

Extend case study to run with Claude + OpenAI for cross-provider validation.

**Files to modify/create:**
- `examples/case_study/naive_agent.py` — add `OpenAINaiveAgent`
- `examples/case_study/calseta_agent.py` — add `OpenAICalsetaAgent`
- `examples/case_study/run_study.py` — add `--models` flag, run matrix (5 scenarios x 2 approaches x 2 models x 3 runs = 60 runs)
- `examples/case_study/openai_agent.py` — OpenAI variants

#### 3.2 Cost Projection Calculator

**Create:** `examples/case_study/cost_projections.py`

Produces tables showing cost at 1/10/100/1000 alerts/day for both models, both approaches. Includes engineering time comparison (40-80 hrs building naive pipeline vs 1-2 hrs deploying Calseta).

#### 3.3 Success Criteria & Framing

**What to measure:**
- Input token reduction (Calseta vs Naive) for both Claude and OpenAI
- Investigation quality scores (completeness, accuracy, actionability)
- Cost projections at scale (1/10/100/1000 alerts/day)
- Engineering time comparison (build-your-own vs deploy Calseta)

**How to frame results honestly:**
- Report the actual numbers — don't round up to hit a target
- The "naive" baseline must be clearly defined (raw SIEM payload + raw VT/AbuseIPDB API responses stuffed into context)
- If token reduction is 30% instead of 50%, that's still real value — lead with engineering time saved instead
- The strongest value prop may be **engineering time** ($6K-$12K building a custom pipeline vs. $150-$300 deploying Calseta) rather than per-token savings
- Frame as "here's what a typical agent workflow looks like with and without Calseta" not "guaranteed X% reduction"

**Acceptance:** Results committed to `examples/case_study/results/` with honest numbers.

---

### Phase 4: Record Demos / Videos

**Goal:** 4 launch-day videos. Agent starter kit videos (3, 4) deferred to post-launch.

| # | Title | Length | Audience | Format |
|---|---|---|---|---|
| 1 | "The Journey of a Security Alert" | 60-90 sec | Everyone, LinkedIn | Animated architecture diagram |
| 2 | "Docker Compose to SOC Investigation in 5 Minutes" | 3-5 min | Developers | Terminal recording + voiceover |
| 3 | "Zero-Code Enrichment Provider" | 3-5 min | Community | Terminal recording + voiceover |
| 4 | "The Calseta UI" | 3-5 min | Visual learners | Screen recording + voiceover |

**Video 1 — "The Journey of a Security Alert" (launch video):**

Animated flow using branded motion graphics (not terminal commands). Tells the full story visually:

```
Alert fires in Sentinel → webhook hits Calseta
  → normalize to clean schema
  → extract indicators (IPs, hashes, accounts)
  → enrich with VT + AbuseIPDB (parallel)
  → match detection rule → attach runbook
  → structured payload ready
  → agent reads via MCP → one LLM call
  → finding posted back → workflow triggered
  → human approves in Slack → account suspended
```

Voiceover: 60 seconds, tight, no filler. End card: GitHub link + "Apache 2.0 / Self-hostable / Open source."

This is the LinkedIn launch embed — visual, conceptual, memorable. Terminal demos are for builders (Video 2+).

**Tooling:** Remotion (programmatic video) or Motion Canvas for animation + ElevenLabs TTS + FFmpeg export.
**Brand:** IBM Plex Mono (terminal), Manrope (titles), `#080b0f` bg, `#4D7D71` green accent.

---

### Phase 5: LinkedIn Content Plan

4 posts over 3 weeks:
1. **Launch post** (merge day) — embed Video 1 (animated), case study stats, GitHub link
2. **Technical deep-dive** (day 3-5) — architecture, engineering time savings, cost comparison
3. **Community post** (week 2) — zero-code enrichment provider, Video 3
4. **Builder post** (week 3) — MCP server walkthrough, Video 2

---

### Phase 6: Public Docs (Mintlify)

12 pages: Quickstart, Architecture, API Reference, MCP Server, Alert Sources, Enrichment Providers, Workflows, Agent Integration, Authentication, Deployment Guide, Case Study / Benchmark, Contributing.

---

### Phase 7: Finalize and Merge

1. Create `docs/workflows/examples/` with canonical workflow examples
2. Clean up dev artifacts (`.mcp.json`, etc.)
3. Write `CHANGELOG.md` for v1.0.0
4. PR `feat/mvp-dev` → `main` with comprehensive description
5. Merge and tag `v1.0.0`

---

### Project Management — Execution Tracker

#### Dependency Graph

```
Phase 1: Fix Bugs + Tests
   │
   ├──→ Phase 2: Lab Environment
   │       │
   │       ├──→ Phase 3: Case Study ──→ Phase 7: Merge + Tag v1.0.0
   │       │
   │       └──→ Phase 4: Record Demos ──→ Phase 5: LinkedIn Content
   │
   └──→ Phase 6: Public Docs (can start from existing code + docs)
```

#### Parallelism Guide

After Phase 1 completes, two independent workstreams can run in parallel:

| Workstream | Phases | Can Start After |
|---|---|---|
| **A: Lab + Case Study** | 2 → 3 | Phase 1 |
| **B: Public Docs** | 6 | Phase 1 |

After Phase 2 completes:

| Workstream | Phases | Can Start After |
|---|---|---|
| **C: Demo Videos** | 4 | Phase 2 |
| **D: LinkedIn Content** | 5 | Phase 3 (needs stats) + Phase 4 (needs videos) |

**Merge gate:** Phases 1, 2, 3 must be complete before Phase 7.
**Post-merge:** Phases 4, 5, 6 can continue after merge.

#### Status Tracker

Update this table as work progresses. Agents: claim a phase by setting status to `in_progress` before starting.

| Phase | Description | Status | Dependencies | Notes |
|---|---|---|---|---|
| 1 | Fix bugs + tests | `complete` | — | 1075 tests pass, 0 lint/type errors. MissingGreenlet fixed. Mock enrichment working. |
| 2 | Lab environment | `complete` | Phase 1 | `make lab-reset` working. 5 alerts, 7 enrichment providers, full detection rule docs, context doc targeting, inline tag editing, Agent Payload tab. |
| 3 | Case study | `pending` | Phase 2 | Next up — needs Claude + OpenAI API keys for token comparison |
| 4 | Record demos | `pending` | Phase 2 | Can start — lab is polished |
| 5 | LinkedIn content | `pending` | Phase 3, 4 | Rolling, starts at merge |
| 6 | Public docs | `pending` | Phase 1 | Can start — parallel track |
| 7 | Merge + tag v1.0.0 | `pending` | Phase 1, 2, 3 | Merge blocker gate |

Status values: `pending` → `in_progress` → `complete` (or `blocked`)

#### Post-Launch Backlog

These are valuable but not launch blockers. Build after v1.0.0 ships:

| Item | Description |
|---|---|
| System Activity page | UI page showing a unified, filterable feed of activity events, workflow runs, and agent delivery attempts. Data already exists in `activity_events`, `workflow_runs`, and `agent_runs` tables with REST endpoints. Useful for engineers debugging agent integrations — see enrichment outcomes, webhook delivery status codes, and workflow execution logs without `docker compose logs`. |
| Agent Starter Kit | Separate `calseta-agent-starter` repo — BaseAgent ABC, LLM provider abstraction, router, SOC role-based agent catalog. Enables "Build Your Own Agent" and "SOC in a Box" demo videos. |
| Additional lab fixtures | 5 more scenarios (S3 malware, OAuth consent abuse, Global Admin assignment, AWS root login, lateral movement) for richer demos |
| "Build Your Own Agent" video | 10-15 min builder walkthrough (depends on agent starter kit) |
| "SOC in a Box" video | 15-20 min full pipeline demo (depends on agent starter kit) |

---

## 4. Architecture Reference

### Process Architecture

```
FastAPI Server (port 8000)   MCP Server (port 8001)
        │                            │
        └────────────────┬───────────┘
                         │
                    PostgreSQL (port 5432)
                    (also task queue store)
                         │
                    Worker Process
                    (enrichment, webhooks, workflows)
```

Docker Compose services: `api` (8000), `worker`, `mcp` (8001), `db` (PostgreSQL 15).

API server and worker share **no in-memory state** — only the database. All async work is enqueued to the durable task queue before the originating HTTP request returns.

### Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Web framework | FastAPI |
| Validation | Pydantic v2 |
| Database | PostgreSQL 15+ |
| ORM | SQLAlchemy 2.0 async (asyncpg driver) |
| Migrations | Alembic |
| Task queue | procrastinate + PostgreSQL |
| Caching | In-memory with TTL (v1) |
| MCP server | Anthropic `mcp` Python SDK |
| HTTP client | httpx async |
| Auth | API keys (`cai_` prefix, bcrypt hash) |
| Testing | pytest + pytest-asyncio |
| Containerization | Docker + Docker Compose |
| Linting | ruff |
| Type checking | mypy |
| Logging | structlog (JSON in prod, colored text in dev) |

### Layered Architecture

```
Route Handler     app/api/v1/          Parse/validate HTTP, call service, return envelope
     │
Service Layer     app/services/        Business logic, orchestration
     │
     ├── Repository     app/repositories/    All DB reads/writes via SQLAlchemy
     ├── Integration    app/integrations/    External APIs through ABCs only
     └── Task Queue     app/queue/           Enqueue async work
```

No layer imports from a layer below its neighbor. All dependencies injected via FastAPI DI (`Depends()`).

### Project Structure

```
app/
  config.py              # pydantic-settings, env-driven
  main.py                # FastAPI app factory
  worker.py              # Worker process entry point
  mcp_server.py          # MCP server entry point
  models/                # SQLAlchemy ORM models
  schemas/               # Pydantic request/response schemas
  api/v1/                # All routes under /v1/
  integrations/
    sources/             # AlertSourceBase subclasses
    enrichment/          # DB-driven enrichment system
    community/           # Community-contributed plugins
  workflows/             # WorkflowContext, WorkflowResult, engine
  queue/                 # TaskQueueBase + procrastinate backend
  services/              # Business logic
  auth/                  # API key auth
  seed/                  # Seed data (sandbox, enrichment providers, lab)
docs/
  integrations/          # {name}/api_notes.md
  workflows/examples/    # Canonical workflow examples
  HOW_TO_*.md            # Extension guides
examples/
  case_study/            # naive_agent.py, calseta_agent.py, fixtures/, results/
  lab/fixtures/          # Lab-only alert fixtures
alembic/                 # Database migrations
ui/                      # React + Vite frontend
```

### Task Queue Operations

| Task | Queue |
|---|---|
| Alert enrichment pipeline | `enrichment` |
| Alert trigger evaluation | `dispatch` |
| Agent webhook delivery | `dispatch` |
| Workflow execution | `workflows` |
| On-demand enrichment | `enrichment` |

All task handlers must be **idempotent**.

### Indicator Extraction Pipeline (3-Pass)

1. **Pass 1** — Source plugin `extract_indicators(raw_payload)` — source-specific, hardcoded
2. **Pass 2** — System normalized-field mappings against normalized alert columns (`is_system=True`, `extraction_target='normalized'`)
3. **Pass 3** — Custom per-source field mappings against `raw_payload` (user-defined, `extraction_target='raw_payload'`)

Results merged and deduplicated by `(type, value)` before storage.

### Security Stack

| Layer | Implementation |
|---|---|
| Rate limiting | `slowapi` — keyed by API key prefix or IP |
| Security headers | `SecurityHeadersMiddleware` |
| CORS | Disabled by default |
| Body size limits | `BodySizeLimitMiddleware` |
| Auth expiry | Checked on every request |
| Webhook signature | `AlertSourceBase.verify_webhook_signature()` |

All env-var-driven with secure defaults.

---

## 5. Data Model Reference

Every table includes: `id` (serial PK), `uuid` (UUID, external-facing), `created_at`, `updated_at`. External IDs are always UUIDs. Internal joins use integer `id`.

### Core Tables (15 + workflow_code_versions)

**alerts** — One row per security alert. Normalized fields as direct columns (`title`, `severity`, `severity_id`, `occurred_at`). `raw_payload` JSONB preserves original source data. `tags` TEXT[]. FK to `detection_rules`. `status` TEXT (investigation lifecycle: `Open`/`Triaging`/`Escalated`/`Closed`). `enrichment_status` TEXT (system-managed: `Pending`/`Enriched`/`Failed`). `acknowledged_at`, `triaged_at`, `closed_at` TIMESTAMP nullable (write-once).

**detection_rules** — Detection library with MITRE fields and `documentation` TEXT.

**indicators** — Global entity, one row per unique `(type, value)` pair. `first_seen`, `last_seen` TIMESTAMP. `malice` TEXT enum. `enrichment_results` JSONB.

**alert_indicators** — Many-to-many join. Same IOC in 50 alerts = 1 indicator row + 50 join rows.

**enrichment_providers** — Runtime-configurable enrichment configs. `provider_name` (unique), `http_config` JSONB (templated HTTP steps), `auth_config` JSONB (encrypted at rest), `malice_rules` JSONB, `cache_ttl_by_type` JSONB. 4 builtins seeded at startup.

**enrichment_field_extractions** — Configurable field extraction from enrichment provider responses. `source_path` (dot-notation into raw response) → `target_key` (key in `extracted` dict). ~64 system defaults seeded.

**context_documents** — Runbooks, IR plans, SOPs. `targeting_rules` JSONB, `content` TEXT.

**workflows** — Python automation functions. `code` TEXT, `code_version` INTEGER, `state` TEXT (`draft`/`active`/`inactive`), `documentation` TEXT, `requires_approval` BOOLEAN, `risk_level`.

**workflow_runs** — Execution audit log. `log_output` TEXT, `result` JSONB, `code_version_executed` INTEGER.

**workflow_approval_requests** — Human-in-the-loop approval lifecycle. `status` TEXT (`pending`/`approved`/`rejected`/`expired`/`cancelled`).

**workflow_code_versions** — Version history for workflow code edits.

**agent_registrations** — Registered agent webhook endpoints with trigger filters.

**agent_runs** — Webhook delivery audit log.

**activity_events** — Immutable audit log. `event_type`, `actor_type` (`system`/`api`/`mcp`), polymorphic FKs, `references` JSONB. Append-only.

**source_integrations** — Configured alert sources.

**indicator_field_mappings** — System + custom per-source IOC extraction mappings. `extraction_target`: `'normalized'` or `'raw_payload'`.

**api_keys** — `key_prefix`, `key_hash` (bcrypt), `scopes` TEXT[], `allowed_sources` TEXT[].

---

## 6. API Reference

### Conventions

- All routes: `/v1/` prefix
- All responses: JSON
- All timestamps: ISO 8601 with timezone
- All IDs in paths/responses: UUIDs
- Pagination: `page` (1-indexed), `page_size` (default 50, max 500)
- Success single: `{ "data": {...}, "meta": {} }`
- Success list: `{ "data": [...], "meta": { "total": N, "page": 1, "page_size": 50 } }`
- Error: `{ "error": { "code": "...", "message": "...", "details": {} } }`
- Ingestion returns `202 Accepted` within 200ms

### Endpoint Map

| Method | Path | Description |
|---|---|---|
| POST | `/v1/alerts/ingest/{source_name}` | Ingest alert (202 Accepted) |
| GET | `/v1/alerts` | List alerts (paginated, filterable) |
| GET | `/v1/alerts/{uuid}` | Get alert detail (with `_metadata` block) |
| PATCH | `/v1/alerts/{uuid}` | Update alert status |
| GET | `/v1/alerts/{uuid}/indicators` | List indicators for alert |
| GET | `/v1/alerts/{uuid}/activity` | Activity event timeline |
| GET | `/v1/alerts/{uuid}/context` | Matched context documents |
| GET | `/v1/detection-rules` | List detection rules |
| GET | `/v1/detection-rules/{uuid}` | Get detection rule |
| POST | `/v1/detection-rules` | Create detection rule |
| PATCH | `/v1/detection-rules/{uuid}` | Update detection rule |
| DELETE | `/v1/detection-rules/{uuid}` | Delete detection rule |
| GET | `/v1/context-documents` | List context documents |
| GET | `/v1/context-documents/{uuid}` | Get context document |
| POST | `/v1/context-documents` | Create (JSON or multipart/form-data) |
| PATCH | `/v1/context-documents/{uuid}` | Update context document |
| DELETE | `/v1/context-documents/{uuid}` | Delete context document |
| GET | `/v1/workflows` | List workflows |
| GET | `/v1/workflows/{uuid}` | Get workflow |
| POST | `/v1/workflows` | Create workflow |
| PATCH | `/v1/workflows/{uuid}` | Update workflow |
| POST | `/v1/workflows/{uuid}/execute` | Execute workflow |
| GET | `/v1/workflows/{uuid}/runs` | List workflow runs |
| GET | `/v1/workflow-runs/{uuid}` | Get workflow run |
| POST | `/v1/workflow-approvals/{uuid}/approve` | Approve workflow request |
| POST | `/v1/workflow-approvals/{uuid}/reject` | Reject workflow request |
| GET | `/v1/enrichment-providers` | List enrichment providers |
| GET | `/v1/enrichment-providers/{uuid}` | Get provider detail |
| POST | `/v1/enrichment-providers` | Create custom provider |
| PATCH | `/v1/enrichment-providers/{uuid}` | Update provider |
| DELETE | `/v1/enrichment-providers/{uuid}` | Delete provider |
| POST | `/v1/enrichment/enrich` | On-demand enrichment |
| GET | `/v1/enrichment/indicators/{type}/{value}` | Get indicator enrichment |
| GET | `/v1/agents` | List agent registrations |
| GET | `/v1/agents/{uuid}` | Get agent registration |
| POST | `/v1/agents` | Register agent webhook |
| PATCH | `/v1/agents/{uuid}` | Update agent registration |
| DELETE | `/v1/agents/{uuid}` | Delete agent registration |
| POST | `/v1/alerts/{uuid}/findings` | Post agent finding |
| GET | `/v1/source-integrations` | List source integrations |
| POST | `/v1/source-integrations` | Create source integration |
| GET | `/v1/metrics/summary` | SOC metrics summary |
| POST | `/v1/api-keys` | Create API key |
| GET | `/v1/api-keys` | List API keys |
| DELETE | `/v1/api-keys/{uuid}` | Revoke API key |

### Authentication

- Format: `cai_{random_32_char_urlsafe_string}`
- Stored as bcrypt hash; `key_prefix` (first 8 chars) for display
- Header: `Authorization: Bearer cai_xxxxx`
- Scopes: `alerts:read`, `alerts:write`, `enrichments:read`, `workflows:read`, `workflows:execute`, `approvals:write`, `agents:read`, `agents:write`, `admin`

### Alert `_metadata` Block

Computed at serialization time on `GET /v1/alerts/{uuid}` and webhook payloads:
- `generated_at` — response timestamp
- `alert_source` — source integration name
- `indicator_count` — number of linked indicators
- `enrichment` — `{ succeeded: [...], failed: [...], enriched_at: ... }`
- `detection_rule_matched` — boolean
- `context_documents_applied` — count

---

## 7. Plugin Interfaces

### Alert Source Plugin (`AlertSourceBase`)

```python
class AlertSourceBase(ABC):
    source_name: str       # "elastic", "sentinel", "splunk"
    display_name: str

    def validate_payload(self, raw: dict) -> bool: ...
    def normalize(self, raw: dict) -> CalsetaAlert: ...
    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]: ...
    def extract_detection_rule_ref(self, raw: dict) -> str | None: ...
```

`CalsetaAlert` is the Calseta agent-native schema — clean field names for AI consumption. Source-specific fields preserved in `raw_payload`.

### Enrichment Provider System (Database-Driven)

```python
class EnrichmentProviderBase(ABC):
    async def enrich(self, value, indicator_type) -> EnrichmentResult: ...
    def is_configured(self) -> bool: ...

class DatabaseDrivenProvider(EnrichmentProviderBase):
    # Wraps a DB row; delegates HTTP execution to GenericHttpEnrichmentEngine
```

All providers are database rows with templated HTTP configs. Zero code changes to add a new provider — seed as builtin or add via `POST /v1/enrichment-providers`. `enrich()` must never raise.

### Task Queue (`TaskQueueBase`)

```python
class TaskQueueBase(ABC):
    async def enqueue(self, task_name: str, payload: dict, *, queue: str, delay_seconds: int, priority: int) -> str: ...
    async def get_task_status(self, task_id: str) -> TaskStatus: ...
    async def start_worker(self, queues: list[str]) -> None: ...
```

Default backend: procrastinate + PostgreSQL.

### Workflow Interface

```python
async def run(ctx: WorkflowContext) -> WorkflowResult
```

- `WorkflowContext` provides: `indicator`, `alert`, `http` (httpx.AsyncClient), `log`, `secrets`, `integrations`
- `WorkflowResult` has `success: bool`, `message: str`, `data: dict`
- Must never raise; all errors returned as `WorkflowResult.fail(...)`
- Allowed imports validated via AST at save time

### Workflow Approval Gate

- Gate fires when `trigger_source=agent` AND `workflow.requires_approval=true`
- Human-triggered execute always bypasses gate
- `reason` + `confidence` required on agent-triggered execute requests
- `ApprovalNotifierBase` ABC → `NullApprovalNotifier`, `SlackApprovalNotifier`, `TeamsApprovalNotifier`
- Factory resolves from `APPROVAL_NOTIFIER` env var: `slack`, `teams`, `none` (default)

---

## 8. Integration Catalog v1

### Alert Sources

| Source | Plugin | Webhook Secret Env Var |
|---|---|---|
| Microsoft Sentinel | `app/integrations/sources/sentinel.py` | `SENTINEL_WEBHOOK_SECRET` |
| Elastic Security | `app/integrations/sources/elastic.py` | `ELASTIC_WEBHOOK_SECRET` |
| Splunk | `app/integrations/sources/splunk.py` | `SPLUNK_WEBHOOK_SECRET` |
| Generic webhook | `app/integrations/sources/generic.py` | — |

### Enrichment Providers (Builtin)

| Provider | Indicator Types | Auth |
|---|---|---|
| VirusTotal | IP, domain, hash | `VIRUSTOTAL_API_KEY` |
| AbuseIPDB | IP | `ABUSEIPDB_API_KEY` |
| Okta | account | `OKTA_DOMAIN`, `OKTA_API_TOKEN` |
| Microsoft Entra | account | `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET` |

**Rule:** Before writing any integration code, fetch and analyze the official API documentation. Produce `docs/integrations/{name}/api_notes.md` first.

---

## 9. MCP Server

Thin adapter over the REST API. No independent business logic.

### Resources (read)

| URI | Description |
|---|---|
| `calseta://alerts` | List alerts |
| `calseta://alerts/{uuid}` | Alert detail |
| `calseta://alerts/{uuid}/activity` | Activity timeline |
| `calseta://alerts/{uuid}/context` | Matched context documents |
| `calseta://detection-rules` | List detection rules |
| `calseta://detection-rules/{uuid}` | Detection rule detail |
| `calseta://context-documents` | List context documents |
| `calseta://context-documents/{uuid}` | Context document detail |
| `calseta://workflows` | List workflows |
| `calseta://workflows/{uuid}` | Workflow detail |
| `calseta://metrics/summary` | SOC metrics |
| `calseta://enrichments/{type}/{value}` | Indicator enrichment |

### Tools (write/execute)

| Tool | Description |
|---|---|
| `post_alert_finding` | Post investigation finding |
| `update_alert_status` | Update alert status |
| `execute_workflow` | Execute a workflow |
| `enrich_indicator` | On-demand enrichment |
| `search_alerts` | Search/filter alerts |
| `search_detection_rules` | Search detection rules |

---

## 10. Enums & Constants

### Alert Status (investigation lifecycle)
`Open` → `Triaging` / `Escalated` → `Closed`

### Enrichment Status (system-managed, separate column)
`Pending` → `Enriched` | `Failed`

### Alert Severity
`Pending`=0, `Informational`=1, `Low`=2, `Medium`=3, `High`=4, `Critical`=5

Sources map `Fatal`→`Critical`, absent/unknown→`Pending`.

### Indicator Malice
`Pending`, `Benign`, `Suspicious`, `Malicious`

Enrichment engine sets worst verdict across providers (`Malicious` > `Suspicious` > `Benign` > `Pending`).

### Indicator Types
`ip`, `domain`, `hash_md5`, `hash_sha1`, `hash_sha256`, `url`, `email`, `account`

### Close Classification
Any value starting with `"False Positive"` counts for FP rate metric.

### `acknowledged_at`
Set on first transition OUT of `Open` (to any other status).

---

## 11. Out of Scope v1

Do not implement: incidents entity, pull/polling sources, user management/RBAC, analytics dashboard, containerized agent hosting, multi-tenancy, SSO/OAuth, alternative queue backends beyond procrastinate, MITRE auto-tagging, Slack SOC bot (v2.2 — distinct from `SlackApprovalNotifier` which IS v1), execution rules engine, named secrets store, database-driven indicator types, knowledge base integrations (Confluence/GitHub/GitLab sync).

Architecture must not preclude these.

---

## 12. Post-v1 Roadmap

| Version | Feature |
|---|---|
| Post-launch | Agent starter kit repo, additional lab fixtures, builder demo videos |
| v1.1 | KB integrations (Confluence/GitHub sync), SIEM polling sources, inline field extractions on provider creation |
| v1.2 | Execution rules engine, named secrets store |
| v1.5 | Hosted sandbox (Wave 9), benchmark page |
| v2.0 | Multi-tenancy, RBAC, SSO |
| v2.2 | Slack SOC bot, agent orchestrator add-on |

### v1.1 Design Notes

**Inline field extractions on provider creation:** Currently, field extractions (`enrichment_field_extractions` table) are managed via separate CRUD endpoints. The `POST /v1/enrichment-providers` and `PATCH /v1/enrichment-providers/{uuid}` endpoints do not accept `field_extractions` in the request body. In v1.1, the provider creation/update endpoints should accept an optional `field_extractions` array in the payload and create/update them in the same database transaction. This simplifies the UX for custom providers — one API call instead of N+1. The separate CRUD endpoints should remain for granular management. Requires: schema change to `EnrichmentProviderCreate`/`EnrichmentProviderPatch`, service layer transaction logic, OpenAPI spec update.

---

## 13. Success Criteria

### Quantitative (from case study)
- Measurable input token reduction (Calseta vs Naive approach) — report actual numbers honestly
- Investigation quality scores comparable or better
- `docker compose up` to working instance in < 5 minutes
- Engineering time comparison quantified (build-your-own vs deploy Calseta)

### Qualitative
- An engineer can deploy Calseta, connect an agent via MCP, and investigate an alert without reading source code
- Adding a new enrichment provider requires zero code changes
- Every entity surfaced to agents includes documentation/context
- Activity log provides full audit trail of agent actions

### Launch Checklist
- Clean `make ci` pass
- 5 seeded lab alerts with enrichment
- Case study results committed with cost projections
- 4 demo videos recorded (animated launch video + 3 walkthroughs)
- Public docs live on Mintlify
- v1.0.0 tagged on `main`
