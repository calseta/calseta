# Calseta — CLAUDE.md

This file is the primary reference for any AI agent or developer working in this repository. Read it fully before writing code.

---

## What This Project Is

Calseta is an open-source, single-tenant, self-hostable SOC data platform built for AI agent consumption. It is **not** an AI SOC product — it does not build or run AI agents. It is the data infrastructure layer: ingest security alerts, normalize to a clean agent-readable schema, enrich with threat intelligence, and expose context-rich data via REST API and MCP server so that customer-built agents can investigate and respond effectively.

Full requirements are in `PRD.md`. Full execution plan is in `PROJECT_PLAN.md`.

---

## Core Principles (Read These Before Every Implementation Decision)

1. **Deterministic operations stay deterministic.** Enrichment, normalization, workflow execution, and metric calculation never consume LLM tokens. These run in the platform, not in the agent.
2. **Token optimization is first-class.** Every API response and MCP resource is designed to give agents exactly what they need — structured, concise, well-labeled data. Not raw API dumps.
3. **AI-readable documentation is a feature.** Every entity (detection rules, workflows, context docs, enrichment providers) has a `documentation` field surfaced through the API and MCP server.
4. **Framework agnosticism.** REST API and MCP server must work equally with LangChain, raw Claude API, CrewAI, n8n, or a Slack slash command. No framework is privileged.
5. **Open by default.** Designed to be understood, extended, and contributed to. Every extension point has a worked example in `docs/`.
6. **Self-hostable without pain.** Single `docker compose up`. Minimal external dependencies. Deploy in under an hour.
7. **Component-level LLM context documentation ships with the code.** Every major component has a `CONTEXT.md` alongside its source — a precise, LLM-optimized guide covering responsibilities, interfaces, design decisions, extension patterns, and failure modes. This is not optional documentation; it is a shipping requirement for every Wave 8 component. See the "Component Context Documentation" section below.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Web framework | FastAPI |
| Validation | Pydantic v2 |
| Database | PostgreSQL 15+ |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| Task queue | procrastinate + PostgreSQL (default); abstracted via `TaskQueueBase` |
| Caching | In-memory with TTL (v1); Redis-ready interface |
| MCP server | Anthropic `mcp` Python SDK |
| HTTP client | httpx async |
| Auth | API keys (`cai_` prefix, bcrypt hash); BetterAuth-ready architecture |
| Testing | pytest + pytest-asyncio |
| Containerization | Docker + Docker Compose |
| Linting | ruff |
| Type checking | mypy |

---

## Process Architecture

Three long-running processes, all started via Docker Compose:

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

Services in `docker-compose.yml`:
- `api` — FastAPI app, port 8000
- `worker` — procrastinate worker, consumes from Postgres task queue
- `mcp` — MCP server, port 8001
- `db` — PostgreSQL 15

The API server and worker share **no in-memory state** — only the database. All async work is enqueued to the durable task queue before the originating HTTP request returns.

---

## Project Structure

```
app/
  config.py              # Settings (pydantic-settings, env-driven)
  main.py                # FastAPI app factory
  worker.py              # Worker process entry point
  mcp_server.py          # MCP server entry point
  models/                # SQLAlchemy ORM models
  schemas/               # Pydantic request/response schemas
  api/
    v1/                  # All routes under /v1/
  integrations/
    sources/             # Alert source plugins (AlertSourceBase subclasses)
    enrichment/          # Enrichment provider system (DB-driven via DatabaseDrivenProvider adapter)
    community/           # Community-contributed plugins
  workflows/             # WorkflowContext, WorkflowResult, execution engine
  queue/                 # TaskQueueBase + backends (procrastinate, celery, sqs, azure)
  services/              # Business logic (enrichment engine, indicator extraction, etc.)
  auth/                  # API key auth (BetterAuth-ready interface)
docs/
  integrations/          # {integration_name}/api_notes.md — API research artifacts
  workflows/examples/    # Canonical workflow examples (primary LLM training material)
  HOW_TO_ADD_ALERT_SOURCE.md
  HOW_TO_ADD_ENRICHMENT_PROVIDER.md
  HOW_TO_DEPLOY.md
  VALIDATION_CASE_STUDY.md
examples/
  case_study/            # naive_agent.py, calseta_agent.py, fixtures/, results/
alembic/                 # Database migrations
```

---

## Data Model — Key Tables

Every table includes: `id` (serial PK), `uuid` (UUID, external-facing), `created_at`, `updated_at`. External-facing IDs are always UUIDs. Internal joins use integer `id` for performance.

- **alerts** — one row per security alert; normalized fields as direct columns (`title TEXT`, `severity TEXT`, `severity_id INTEGER`, `occurred_at TIMESTAMPTZ`); `raw_payload` JSONB (original source payload); `tags` TEXT[]; FK to `detection_rules`; no `indicators` JSONB — indicators are relational; `status` TEXT (investigation lifecycle: `Open`/`Triaging`/`Escalated`/`Closed`); `enrichment_status` TEXT (system-managed: `Pending`/`Enriched`/`Failed`); `acknowledged_at`, `triaged_at`, `closed_at` TIMESTAMP nullable (write-once, set by service layer on status transitions). Normalization happens synchronously at ingest time — source-specific fields that don't map are preserved in `raw_payload`.
- **detection_rules** — detection library with MITRE fields and free-form `documentation` TEXT
- **indicators** — extracted IOCs; **global entity**, one row per unique `(type, value)` pair; `first_seen`, `last_seen` TIMESTAMP; `malice` TEXT enum; `enrichment_results` JSONB; unique constraint on `(type, value)`
- **alert_indicators** — many-to-many join between alerts and indicators; composite unique on `(alert_id, indicator_id)`; same IOC in 50 alerts = 1 indicator row + 50 join rows
- **enrichment_providers** — runtime-configurable enrichment provider configs; `provider_name` (unique), `display_name`, `is_builtin`, `is_active`, `supported_indicator_types` TEXT[], `http_config` JSONB (templated HTTP steps), `auth_type`, `auth_config` JSONB (encrypted at rest), `env_var_mapping` JSONB (builtin env var fallback), `malice_rules` JSONB (threshold-based verdict rules), `cache_ttl_by_type` JSONB; 4 builtins seeded at startup; custom providers added via CRUD API at `/v1/enrichment-providers`; `DatabaseDrivenProvider` adapter wraps each row as an `EnrichmentProviderBase` implementation
- **enrichment_field_extractions** — configurable field extraction schema for enrichment provider responses; `provider_name`, `indicator_type`, `source_path` (dot-notation into raw response), `target_key` (key in `extracted` dict surfaced to agents), `value_type`, `is_system`, `is_active`, `description`; ~64 system defaults seeded at startup for builtins; both `extracted` subset and full `raw` response are persisted per provider in `indicators.enrichment_results`
- **context_documents** — runbooks, IR plans, SOPs; `targeting_rules` JSONB, `content` TEXT
- **workflows** — Python automation functions; `code` TEXT, `code_version` INTEGER, `state` TEXT (`draft`/`active`/`inactive`), `documentation` TEXT; includes `approval_mode` TEXT (`always`/`agent_only`/`never`), `approval_channel`, `approval_timeout_seconds`, `risk_level` for human-in-the-loop approval gate
- **workflow_runs** — execution audit log; `log_output` TEXT, `result` JSONB, `code_version_executed` INTEGER
- **workflow_approval_requests** — human-in-the-loop approval lifecycle; `status` TEXT (`pending`/`approved`/`rejected`/`expired`/`cancelled`), `trigger_context` JSONB, `reason`, `confidence`, `notifier_type`, `responder_id`, `responded_at`, `expires_at`
- **workflow_code_versions** — version history for workflow code; `workflow_id` FK, `version` INTEGER, `code` TEXT, `saved_at`; written on every code edit before incrementing `code_version`
- **agent_registrations** — registered agent webhook endpoints with trigger filters
- **agent_runs** — webhook delivery audit log
- **activity_events** — immutable audit log of every significant action on every entity; `event_type`, `actor_type` (`system`/`api`/`mcp`), `actor_key_prefix`, polymorphic FKs to alert/workflow/detection_rule, `references` JSONB; append-only, no `updated_at`; surfaced via `GET /v1/alerts/{uuid}/activity` and MCP resource `calseta://alerts/{uuid}/activity`
- **source_integrations** — configured alert sources
- **indicator_field_mappings** — system normalized-field mappings + custom per-source mappings; `extraction_target` values: `'normalized'` (against normalized alert columns) or `'raw_payload'` (against source-specific raw data); separate from enrichment field extractions — these extract IOCs from alert payloads, not from provider responses
- **api_keys** — `key_prefix`, `key_hash` (bcrypt), `scopes` TEXT[], `allowed_sources` TEXT[] (NULL = unrestricted)

---

## Key Plugin Interfaces

### Alert Source Plugin (`AlertSourceBase`)
```python
class AlertSourceBase(ABC):
    source_name: str       # "elastic", "sentinel", "splunk"
    display_name: str

    def validate_payload(self, raw: dict) -> bool: ...
    def normalize(self, raw: dict) -> CalsetaAlert: ...
    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]: ...
    def extract_detection_rule_ref(self, raw: dict) -> str | None: ...  # optional
```

`CalsetaAlert` is the Calseta agent-native schema — clean field names designed for AI consumption (`title`, `severity`, `severity_id`, `occurred_at`, `source_name`, etc.). Not OCSF. Source-specific fields that don't map are preserved in `raw_payload` by the caller, not this method.

### Enrichment Provider System (Database-Driven)

Enrichment providers are **database-driven** — each provider is a row in the `enrichment_providers` table with templated HTTP configs, malice threshold rules, and field extraction mappings. A single adapter class (`DatabaseDrivenProvider`) implements the `EnrichmentProviderBase` ABC for all providers. Adding a new provider requires zero code changes — either seed it as a builtin in `app/seed/enrichment_providers.py` or add it at runtime via `POST /v1/enrichment-providers`.

```python
class EnrichmentProviderBase(ABC):                    # Internal ABC (the port)
    async def enrich(self, value, indicator_type) -> EnrichmentResult: ...
    def is_configured(self) -> bool: ...

class DatabaseDrivenProvider(EnrichmentProviderBase):  # The single adapter
    # Wraps a DB row; delegates HTTP execution to GenericHttpEnrichmentEngine
```

`enrich()` must never raise — catch all errors and return `success=False`. The `EnrichmentService` pipeline is completely unchanged by the database-driven architecture. See `app/integrations/enrichment/CONTEXT.md` for full details.

### Task Queue (`TaskQueueBase`)
```python
class TaskQueueBase(ABC):
    async def enqueue(self, task_name: str, payload: dict, *, queue: str, delay_seconds: int, priority: int) -> str: ...
    async def get_task_status(self, task_id: str) -> TaskStatus: ...
    async def start_worker(self, queues: list[str]) -> None: ...
```
Default backend: procrastinate + PostgreSQL. Configured via `QUEUE_BACKEND` env var.

### Workflow Interface
Every workflow is an HTTP automation script: an `async def run(ctx: WorkflowContext) -> WorkflowResult` function. Python is the glue layer for constructing HTTP requests, calling external endpoints via `ctx.http`, and parsing responses.
- `WorkflowContext` provides: `indicator`, `alert`, `http` (httpx.AsyncClient), `log`, `secrets`, `integrations`
- `WorkflowResult` has `success: bool`, `message: str`, `data: dict`
- Must never raise; all errors returned as `WorkflowResult.fail(...)`
- Allowed imports validated via AST at save time (standard lib + `calseta.workflows` only)
- See `docs/HOW_TO_WRITE_WORKFLOWS.md` for patterns and copy-paste examples

---

## API Conventions

- All routes: `/v1/` prefix
- All responses: JSON
- All timestamps: ISO 8601 with timezone
- All IDs in paths/responses: UUIDs
- Pagination: `page` (1-indexed), `page_size` (default 50, max 500)
- Success single: `{ "data": {...}, "meta": {} }`
- Success list: `{ "data": [...], "meta": { "total": N, "page": 1, "page_size": 50 } }`
- Error: `{ "error": { "code": "...", "message": "...", "details": {} } }`
- Ingestion endpoint returns `202 Accepted` within 200ms; all enrichment/dispatch is async via task queue

---

## Authentication

- API key format: `cai_{random_32_char_urlsafe_string}`
- Stored as bcrypt hash; `key_prefix` (first 8 chars) stored for display
- Full key shown once on creation, never again
- Header: `Authorization: Bearer cai_xxxxx`
- Scopes: `alerts:read`, `alerts:write`, `enrichments:read`, `workflows:read`, `workflows:execute`, `approvals:write`, `agents:read`, `agents:write`, `admin`
- Auth is abstracted via DI — v1 implements API key auth; architecture is BetterAuth-ready

---

## Indicator Extraction Pipeline (3-Pass)

1. **Pass 1** — Source plugin `extract_indicators(raw_payload)` — source-specific, hardcoded
2. **Pass 2** — System normalized-field mappings against the normalized alert columns (pre-seeded at startup, `is_system=True`, `extraction_target='normalized'`)
3. **Pass 3** — Custom per-source field mappings against `raw_payload` (user-defined, dot-notation, `extraction_target='raw_payload'`)

Results merged and deduplicated by `(type, value)` before storage.

Indicator types: `ip`, `domain`, `hash_md5`, `hash_sha1`, `hash_sha256`, `url`, `email`, `account`

---

## Task Queue Operations

All async operations are enqueued to the durable task queue before HTTP response returns:

| Task | Queue |
|---|---|
| Alert enrichment pipeline | `enrichment` |
| Alert trigger evaluation | `dispatch` |
| Agent webhook delivery | `dispatch` |
| Workflow execution | `workflows` |
| On-demand enrichment | `enrichment` |

All task handlers must be **idempotent** — safe to execute more than once.

---

## MCP Server

Thin adapter over the REST API. No independent business logic.

**Resources (read):** `calseta://alerts`, `calseta://alerts/{uuid}`, `calseta://alerts/{uuid}/activity`, `calseta://alerts/{uuid}/context`, `calseta://detection-rules`, `calseta://detection-rules/{uuid}`, `calseta://context-documents`, `calseta://context-documents/{uuid}`, `calseta://workflows`, `calseta://workflows/{uuid}`, `calseta://metrics/summary`, `calseta://enrichments/{type}/{value}`

**Tools (write/execute):** `post_alert_finding`, `update_alert_status`, `execute_workflow`, `enrich_indicator`, `search_alerts`, `search_detection_rules`

---

## v1 Integration Catalog

**Alert Sources:** Microsoft Sentinel, Elastic Security, Splunk, Generic webhook

**Enrichment Providers:** VirusTotal (IP, domain, hash), AbuseIPDB (IP), Okta (account), Microsoft Entra (account)

**Integration Development Rule:** Before writing any integration code, fetch and analyze the official API documentation. Produce `docs/integrations/{name}/api_notes.md` with: field names/types, pagination patterns, rate limits, available automation endpoints, edge cases. This is mandatory, not optional.

---

## Out of Scope for v1

Do not implement: frontend UI, incidents entity, pull/polling sources, user management/RBAC, analytics dashboard, containerized agent hosting, multi-tenancy, SSO/OAuth, alternative queue backends beyond procrastinate, MITRE auto-tagging, Slack SOC bot (v2.2 roadmap — distinct from `SlackApprovalNotifier` which **is** in v1 scope as the targeted approval notification/callback handler for the workflow approval gate), execution rules engine (rule-based condition→action automation), named secrets store (database-backed `tenant_secrets` table), database-driven indicator types (runtime-configurable via `indicator_types` table), knowledge base integrations (Confluence/GitHub/GitLab automated sync).

Architecture must not preclude these. If you discover something related, log it in your completion log — do not implement it.

---

## Project Execution

Work is tracked in `PROJECT_PLAN.md`. It is organized into 9 waves of work chunks. Each chunk has:
- Status: `pending` → `in_progress` → `complete` (or `blocked`)
- Dependencies that must be `complete` before starting
- Acceptance criteria that must all pass before marking `complete`
- A completion log entry describing what was built, any deviations, and notes for downstream chunks

**Before starting any chunk:** verify all dependencies are `complete`, read the linked PRD sections, review output artifacts of every dependency chunk.

**Do not scope-creep.** Implement only what the chunk specifies. Log discoveries; don't implement them.

---

## Testing Standards

- Framework: pytest + pytest-asyncio
- All async code tested with `pytest-asyncio`
- Integration tests use a real test PostgreSQL instance (Docker)
- Unit tests mock external dependencies
- Workflow sandboxed testing uses mock HTTP interception — no real external calls
- Run: `make test`

---

## Code Quality

```
make lint       # ruff
make typecheck  # mypy
make test       # pytest
make migrate    # alembic upgrade head
```

All code must pass linting and type checking before marking a chunk complete.

---

## Architecture & Coding Principles

These are enforced by example in the codebase — the first implementation chunks set the patterns that all subsequent contributors follow.

### Layered Architecture — strict, no skipping layers

Every request follows this path. No layer imports from a layer below its neighbor.

```
Route Handler     app/api/v1/          Parse/validate HTTP, call service, return envelope
     │
Service Layer     app/services/        Business logic, orchestration — no HTTP, no raw SQL
     │
     ├── Repository     app/repositories/    All DB reads/writes via SQLAlchemy session
     ├── Integration    app/integrations/    External APIs through abstract base classes only
     └── Task Queue     app/queue/           Enqueue async work — never execute inline
```

**How to find any bug:** Wrong HTTP response shape → route handler. Wrong business logic → service. Wrong data from DB → repository. Enrichment failing → integration. Task not running → queue/worker.

### Dependency Injection — nothing is a global

Every dependency injected via FastAPI DI (`Depends(...)`). DB sessions, queue backends, auth context, settings — all received as parameters, never imported as module-level singletons. Every function's dependencies are visible from its signature.

### DRY — one place, one source of truth

- Pagination → `PaginationParams` dependency
- Error formatting → `CalsetaException` + one global handler
- Auth failure logging → `log_auth_failure()` in `app/auth/audit.py`
- Response envelopes → `DataResponse[T]` / `PaginatedResponse[T]`
- Webhook signature check → `AlertSourceBase.verify_webhook_signature()` default + source override

If logic appears in two places, extract it. Never copy-paste business logic between routes or services.

### Ports and Adapters — core never imports adapters

`AlertSourceBase`, `EnrichmentProviderBase`, `TaskQueueBase` are the ports. Concrete implementations (Sentinel, `DatabaseDrivenProvider`, procrastinate) are the adapters. Services and routes only ever import the base class. This is what makes plugins swappable and tests fast.

### Explicit over implicit

No magic imports, no monkeypatching, no hidden global state. If a function needs something, it receives it as a parameter. Configuration lives in `app/config.py` and is injected. Behavior is never changed by importing a module as a side effect.

---

## Database Strategy

- **PostgreSQL 15+ only** — non-negotiable. `JSONB`, `TEXT[]`, and procrastinate's `LISTEN/NOTIFY` are all Postgres-specific.
- **Connection abstraction** — `DATABASE_URL` env var is the single connection point. RDS, Azure DB for PostgreSQL, Cloud SQL, or self-hosted Postgres all work identically.
- **Required extension** — `pgcrypto` for `gen_random_uuid()`. Must be enabled on the Postgres instance.
- **Driver** — `asyncpg` (`postgresql+asyncpg://` DSN prefix).
- **Migrations** — Alembic only. Never alter schema outside a migration. All migrations reversible.
- **Local dev** — `postgres:15-alpine` in Docker Compose, port 5432, data in `postgres_data` named volume.

---

## Logging

Library: `structlog`. Configured once in `app/logging_config.py`, called at process startup.

- `LOG_FORMAT=json` (production) → newline-delimited JSON to stdout
- `LOG_FORMAT=text` (local dev) → colored human-readable console output
- `LOG_LEVEL` — `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`
- `request_id` is automatically bound to all log calls within an HTTP request via `structlog.contextvars` — never pass it as a parameter
- All logging via `structlog.get_logger()` — no `print()`, no `logging.getLogger()`

**Stdout is the contract.** The deployment layer routes stdout to CloudWatch, Azure Monitor, Datadog, etc. No application code changes needed to switch log destinations.

---

## CI/CD

| Event | Workflow | What runs |
|---|---|---|
| Every push / PR | `ci.yml` | ruff → mypy → pytest (real Postgres container) → Docker build |
| Tag `v*` push | `release.yml` | CI → multi-arch Docker build → push to GHCR → GitHub Release |

- `make ci` runs the same sequence locally — run it before opening a PR
- Images: `ghcr.io/{org}/calseta-{api,worker,mcp}:{version}` and `:latest`
- Versioning: `v{major}.{minor}.{patch}` — tag `main` after merging the release PR

**Branch protection on `main`:** CI must pass, no direct pushes, linear history (rebase/squash only).

---

## Security Stack

All security is env-var-driven. Secure defaults ship out of the box — deployers opt out, not in.

| Layer | Implementation | Key Env Vars |
|---|---|---|
| Rate limiting | `slowapi` — keyed by API key prefix (authed) or IP (unauthed) | `RATE_LIMIT_*_PER_MINUTE` |
| Security headers | Custom `SecurityHeadersMiddleware` — all responses | `HTTPS_ENABLED`, `SECURITY_HEADER_*` |
| CORS | `CORSMiddleware` — disabled by default | `CORS_ALLOWED_ORIGINS` |
| Body size limits | `BodySizeLimitMiddleware` — enforced before route handlers | `MAX_REQUEST_BODY_SIZE_MB`, `MAX_INGEST_PAYLOAD_SIZE_MB` |
| Auth expiry | Checked in `APIKeyAuthBackend` on every request | — |
| Auth failure logging | `app/auth/audit.py` — structured JSON to stdout | — |
| Webhook signature | `AlertSourceBase.verify_webhook_signature()` — called before `validate_payload()` | `SENTINEL_WEBHOOK_SECRET`, `ELASTIC_WEBHOOK_SECRET`, `SPLUNK_WEBHOOK_SECRET` |

**Critical implementation rules:**
- Signature comparisons always use `hmac.compare_digest()` — never `==`
- Rate limiter reads real client IP from `X-Forwarded-For` only when `TRUSTED_PROXY_COUNT > 0`
- Auth failure logging lives in one place: `app/auth/audit.py:log_auth_failure()`
- 429 responses always include `Retry-After` header

---

## Component Context Documentation

Every major component ships a `CONTEXT.md` file alongside its source code. An agent working on a specific component reads that file first — before reading any source files.

**What a `CONTEXT.md` must contain:**
1. **What this component does** — one paragraph, no fluff
2. **Interfaces** — inputs, outputs, and the contracts that callers must uphold
3. **Key design decisions** — the "why" behind non-obvious choices; what alternatives were rejected and why
4. **Extension pattern** — the exact steps to add a new plugin/handler/backend (concrete, not abstract)
5. **Common failure modes** — what breaks here and how to diagnose it
6. **Test coverage** — which test files cover this component and what scenarios they test

**Required locations (Wave 8, chunk 8.12):**

| File | Component |
|---|---|
| `app/integrations/sources/CONTEXT.md` | Alert source plugin system |
| `app/integrations/enrichment/CONTEXT.md` | Enrichment provider system |
| `app/workflows/CONTEXT.md` | Workflow engine and sandbox |
| `app/queue/CONTEXT.md` | Task queue abstraction |
| `app/mcp/CONTEXT.md` | MCP server adapter |
| `app/auth/CONTEXT.md` | Authentication and API key management |
| `app/services/CONTEXT.md` | Service layer conventions |

**Writing style:** LLM reader first, human second. Precise and concrete. Code blocks over prose for behavior that needs illustration. No filler sentences. An agent should be able to read a `CONTEXT.md` and make a correct change to that component without reading the source files first.

---

## Git Conventions

### Branching Strategy (MVP Phase)
Single long-running feature branch merged to `main` when MVP ships:

```
main                  ← stable; tagged releases only
└── feat/mvp-dev      ← all MVP work lands here
```

Branch naming prefixes (Conventional Commits standard):

| Prefix | Use for |
|---|---|
| `feat/` | New features |
| `fix/` | Bug fixes |
| `docs/` | Documentation only |
| `refactor/` | Code restructuring, no behavior change |
| `chore/` | Tooling, dependencies, config |
| `test/` | Adding or fixing tests |
| `hotfix/` | Urgent fix branched from `main` |

### Commit Message Format
```
<type>: <short description>

feat: add VirusTotal enrichment provider
fix: handle missing ocsf_data.unmapped field on normalization
docs: add api_notes.md for Elastic Security
chore: pin procrastinate to 2.x in pyproject.toml
```

- Lowercase, imperative tense, no period at end
- Keep the subject line under 72 characters
- Body (optional) explains *why*, not *what*

### PR Target
All work during MVP phase targets `feat/mvp-dev`. Direct commits to `main` are not allowed.

---

## Environment Configuration

All config via `.env` file (never committed). See `.env.local.example` (dev) and `.env.prod.example` (production) for all variables with descriptions. Key variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL DSN |
| `QUEUE_BACKEND` | `postgres` (default), `celery_redis`, `sqs`, `azure_service_bus` |
| `VIRUSTOTAL_API_KEY` | VirusTotal v3 |
| `ABUSEIPDB_API_KEY` | AbuseIPDB v2 |
| `OKTA_DOMAIN`, `OKTA_API_TOKEN` | Okta enrichment + workflows |
| `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET` | Microsoft Entra |
| `ENCRYPTION_KEY` | For encrypting auth configs and agent auth header values at rest |
| `AZURE_KEY_VAULT_URL` | If set, loads secrets from Azure Key Vault at startup (optional) |
| `AWS_SECRETS_MANAGER_SECRET_NAME` | If set, loads secrets from AWS Secrets Manager at startup (optional) |
| `AWS_REGION` | AWS region for Secrets Manager (required if `AWS_SECRETS_MANAGER_SECRET_NAME` is set) |

---

## Secrets Management

By default, all secrets are read from environment variables or a `.env` file — no external dependencies, compatible with `docker compose up` for self-hosters.

For production deployments on cloud infrastructure, two optional secrets backends are supported. Set **one** of the following to activate:

### Azure Key Vault
Set `AZURE_KEY_VAULT_URL`. Uses `azure-identity` for authentication (supports Managed Identity, workload identity, `DefaultAzureCredential` chain). Install with `pip install calseta[azure]`.

### AWS Secrets Manager
Set `AWS_SECRETS_MANAGER_SECRET_NAME` and `AWS_REGION`. Uses `boto3` with the standard AWS credential chain (IAM role, instance profile, env vars). The secret value must be a JSON object whose keys match settings field names. Install with `pip install calseta[aws]`.

### Priority Order
```
Azure Key Vault  (if AZURE_KEY_VAULT_URL set)
AWS Secrets Mgr  (if AWS_SECRETS_MANAGER_SECRET_NAME set)
Environment vars
.env file
Defaults
```

Only one cloud provider is active at a time. If neither is configured, the Azure and AWS SDKs are never imported — no startup penalty for self-hosters. A structured log line at startup always indicates which source is active: `secrets_source=azure_key_vault | aws_secrets_manager | environment`.
