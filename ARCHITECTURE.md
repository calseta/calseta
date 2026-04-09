# Calseta Architecture

Calseta is an open-source, self-hostable SOC data platform that ingests security alerts, normalizes them, enriches with threat intelligence, and exposes context-rich data via REST API and MCP server for AI agent consumption. It is **not** an AI SOC product — it is the data infrastructure layer.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12+ |
| Web Framework | FastAPI + Pydantic v2 |
| Database | PostgreSQL 15+ (asyncpg driver) |
| ORM / Migrations | SQLAlchemy 2.0 async / Alembic |
| Task Queue | procrastinate (PostgreSQL-backed) |
| MCP Server | Anthropic `mcp` Python SDK |
| HTTP Client | httpx async |
| Auth | API keys (bcrypt-hashed, `cai_` prefix) |
| Frontend | React 19, Vite, Tailwind CSS, TypeScript |
| Testing | pytest + pytest-asyncio |
| Linting / Types | ruff / mypy |
| Containerization | Docker + Docker Compose |

---

## Process Architecture

```
FastAPI Server (port 8000)       MCP Server (port 8001)
  REST API + Admin UI              Agent-facing resources/tools
        │                                   │
        └──────────────┬────────────────────┘
                       │
                  PostgreSQL (port 5432)
                  (data + task queue store)
                       │
                  Worker Process
                  (enrichment, webhooks, workflows)
```

Four services in `docker-compose.yml`: `api`, `worker`, `mcp`, `db`. API and worker share **no in-memory state** — only the database.

---

## Data Flow: Alert Pipeline

```
1. INGEST         Webhook → /v1/ingest/{source_name}
2. NORMALIZE      Source plugin → CalsetaAlert schema
3. EXTRACT        3-pass indicator extraction (source → system → custom mappings)
4. DEDUPLICATE    Fingerprint match within dedup window → increment or persist
5. ENRICH (async) Queued task → parallel provider lookups → cached results
6. CONTEXTUALIZE  Targeting rules → attach context docs + workflows
7. DISPATCH       REST API / MCP resource / webhook to agents
```

All deterministic work (steps 1-4) completes synchronously. Enrichment (step 5) runs async via task queue. Agents receive fully enriched, contextualized alerts — no LLM tokens spent on plumbing.

---

## Key Modules

```
app/
├── api/v1/              Route handlers (HTTP layer)
├── services/            Business logic (no HTTP, no raw SQL)
├── repositories/        Data access (SQLAlchemy queries)
├── db/models/           ORM models (18 tables)
├── schemas/             Pydantic request/response models
├── integrations/
│   ├── sources/         Alert source plugins (Sentinel, Elastic, Splunk, Generic)
│   └── enrichment/      DB-driven enrichment providers (VT, AbuseIPDB, Okta, Entra)
├── workflows/           Sandboxed Python workflow execution
├── queue/               Task queue abstraction (procrastinate default)
├── mcp/                 MCP server resources and tools
├── auth/                API key authentication
├── middleware/          Security headers, rate limiting, body size limits
├── cache/               In-memory TTL cache
├── seed/                Database seeding (builtins)
├── tasks/               Async task definitions
├── cli/                 CLI utilities
├── config.py            Env-driven settings (pydantic-settings)
├── main.py              FastAPI app factory
├── worker.py            Worker process entry point
└── mcp_server.py        MCP server entry point

ui/src/                  React frontend (TanStack Query/Router)
docs/                    Guides, integration API notes, architecture docs
examples/                Case study comparing naive vs Calseta-powered agents
alembic/                 Database migrations
```

---

## Layered Architecture

```
Route Handler  →  Service Layer  →  Repository / Integration / Queue
(app/api/v1/)     (app/services/)   (app/repositories/, app/integrations/, app/queue/)
```

Strict import boundaries: no layer imports from below its neighbor. All dependencies injected via FastAPI DI — no globals, no singletons.

---

## Plugin Interfaces

**Alert Sources** (`AlertSourceBase`): `validate_payload()`, `normalize()`, `extract_indicators()`. Each source maps raw SIEM payloads to the `CalsetaAlert` schema.

**Enrichment Providers** (database-driven): Each provider is a DB row with templated HTTP configs. `DatabaseDrivenProvider` adapter wraps all providers — adding a new one requires zero code changes.

**Task Queue** (`TaskQueueBase`): `enqueue()`, `get_task_status()`, `start_worker()`. Default: procrastinate + PostgreSQL.

**Workflows**: User-defined `async def run(ctx) -> WorkflowResult` functions. Sandboxed execution with timeout, memory limits, SSRF prevention, and AST-validated imports.

---

## Key Data Models

| Table | Purpose |
|-------|---------|
| `alerts` | Security alerts with normalized fields + raw payload |
| `indicators` | Global IOCs — one row per unique (type, value) |
| `alert_indicators` | Many-to-many join |
| `enrichment_providers` | Runtime-configurable enrichment configs |
| `enrichment_field_extractions` | Field extraction schemas per provider |
| `detection_rules` | Detection library with MITRE mappings |
| `context_documents` | Runbooks, IR plans, SOPs with targeting rules |
| `workflows` | Python automation with versioning + approval gates |
| `workflow_runs` | Execution audit log |
| `activity_events` | Immutable audit trail |
| `source_integrations` | SIEM source configs |
| `api_keys` | Auth tokens (bcrypt-hashed) |

All tables use integer PKs internally, UUIDs externally. Timestamps are ISO 8601 with timezone.

---

## Deployment

Single `docker compose up` starts all services. Configuration is environment-driven:

```
Priority: Azure Key Vault → AWS Secrets Manager → env vars → .env → defaults
```

CI runs: ruff → mypy → pytest (real Postgres) → Docker build. Images published to GHCR on tagged releases.

---

## Recommended CLAUDE.md / CONTEXT.md Additions

Existing CONTEXT.md files cover 7 key components. Additional directories that would benefit:

| Directory | Why |
|-----------|-----|
| `app/api/v1/` | 18 route modules — endpoint conventions, error handling, pagination patterns |
| `app/repositories/` | 14 repos — base patterns, async query conventions, join strategies |
| `app/db/models/` | 18 models — naming conventions, JSONB patterns, FK relationships |
| `app/middleware/` | Security stack — rate limiting, headers, body limits, ordering |
| `app/schemas/` | Pydantic models — validation patterns, envelope conventions |
| `app/seed/` | Seeding strategy — builtins vs user-created, idempotency |
| `ui/src/` | Frontend — component patterns, hooks, TanStack conventions |
| `docs/` | Documentation structure — guides vs API notes vs architecture |
