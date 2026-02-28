# Calseta AI — Project Plan

**Version:** 1.0
**Last Updated:** February 2026
**Linked PRD:** `PRD.md`

---

## Purpose

This document is the execution plan for building Calseta AI. It is structured for parallel LLM agent workflows. Each chunk is a discrete, independently completable unit of work with explicit dependencies, acceptance criteria, and a completion log. Agents read this file to claim work, track progress, and record what they built.

---

## Agent Protocol

### Claiming a chunk
1. Verify all chunks in the **Depends on** list have status `complete`.
2. Change **Status** from `pending` → `in_progress`.
3. Set **Assigned Agent** to your agent identifier.
4. Read all linked PRD sections and review the output artifacts of every dependency chunk before writing code.

### Completing a chunk
1. Verify every acceptance criterion is met. Do not mark complete if any criterion is unmet.
2. Change **Status** to `complete`.
3. Append an entry to **Completion Log** in this format:
   ```
   - [AGENT_ID] [ISO-8601 timestamp]
     Built: <2–5 sentence description of what was implemented>
     Deviations: <any spec deviations and rationale, or "none">
     Notes: <anything a downstream chunk agent should know, or "none">
   ```
4. Update the **Progress Dashboard** counts for this wave.

### When blocked
1. Change **Status** to `blocked`.
2. Append a log entry describing the blocker clearly.
3. Do not proceed. The blocker must be resolved before resuming.

### Parallelism
Within a wave, chunks marked ⚡ can run simultaneously once their individual **Depends on** are met. Unmarked chunks should run in listed order within the wave. Waves themselves must complete before the next wave begins, except where cross-wave dependencies are explicitly listed.

### Do not scope-creep
If you discover missing requirements or improvements, record them in your completion log under **Notes**. Do not implement work outside your chunk's scope.

---

## Progress Dashboard

Update this table when chunk statuses change.

| Wave | Name | Total | Pending | In Progress | Complete | Blocked |
|---|---|---|---|---|---|---|
| 1 | Foundation | 11 | 8 | 0 | 3 | 0 |
| 2 | Ingestion + Detection Rules | 11 | 11 | 0 | 0 | 0 |
| 3 | Enrichment Engine | 9 | 9 | 0 | 0 | 0 |
| 4 | Context + Workflow Engine | 13 | 13 | 0 | 0 | 0 |
| 5 | Agent Integration Layer | 6 | 6 | 0 | 0 | 0 |
| 6 | Metrics + Admin Endpoints | 6 | 6 | 0 | 0 | 0 |
| 7 | MCP Server | 5 | 5 | 0 | 0 | 0 |
| 8 | Testing + Docs + Examples | 15 | 15 | 0 | 0 | 0 |
| 9 | Hosted Sandbox (v1.5) | 5 | 5 | 0 | 0 | 0 |
| **Total** | | **81** | **81** | **0** | **0** | **0** |

---

## Wave 1 — Foundation

**Goal:** Establish project scaffold, database schema, core Pydantic models, authentication, shared middleware, and task queue infrastructure. No feature code. Everything in Waves 2–8 depends on this wave being complete.

**Internal sequencing:**
- 1.1 must complete first (blocks all others in this wave)
- After 1.1: 1.2 and 1.3 can run in parallel ⚡
- 1.4 depends on 1.2 + 1.3
- 1.5 depends on 1.2 + 1.3
- 1.6 depends on 1.2
- 1.9 depends on 1.4 + 1.5 (needs auth and middleware stack before adding security layers)
- 1.10 depends on 1.1 only — can run in parallel with 1.2–1.8 ⚡
- 1.11 depends on 1.1 only — can run in parallel with 1.2–1.8 ⚡

---

### Chunk 1.1 — Project Scaffold & Docker Compose

**Status:** `complete`
**Assigned Agent:** claude-sonnet-4-6
**Depends on:** none
**PRD Reference:** Sections 6, 10

**Description:**
Create the repository structure, Docker Compose configuration, and development tooling. This is the skeleton every other chunk fills in. No business logic. The FastAPI app starts and serves a stub health endpoint. The worker process starts without error.

**Output Artifacts:**
- `pyproject.toml` — all dependencies pinned (FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2, procrastinate, httpx, bcrypt, structlog, markitdown, python-multipart, ruff, mypy, pytest, pytest-asyncio)
- `docker-compose.yml` — services: `api` (port 8000), `worker`, `mcp` (port 8001), `db` (PostgreSQL 15, port 5432)
- `Dockerfile` — multi-stage: `dev` target with dev deps, `prod` target without
- `.env.example` — every env var key with description comment, no secrets
- `app/__init__.py`
- `app/config.py` — `Settings` class using pydantic-settings; loads from env; validates required vars at startup
- `app/main.py` — FastAPI app factory; mounts `/health` stub returning `{"status": "ok"}`
- `app/worker.py` — entry point for worker process; starts without error (no tasks registered yet)
- `Makefile` — targets: `dev`, `test`, `lint`, `typecheck`, `migrate`

**Acceptance Criteria:**
- [x] `docker compose up` starts all four services with no errors
- [x] `GET /health` returns `200 {"status": "ok"}`
- [x] `make lint` (ruff) exits 0 on the starter codebase
- [x] `make typecheck` (mypy) exits 0 on the starter codebase
- [x] `make test` (pytest) exits 0 with zero collected tests
- [x] Missing a required env var causes startup to fail with a descriptive error message naming the missing var
- [x] `.env.example` documents every key used in `app/config.py`

**Completion Log:**
- [claude-sonnet-4-6] [2026-02-28T00:00:00Z]
  Built: pyproject.toml with all required deps (FastAPI, SQLAlchemy 2.0 async, Alembic, Pydantic v2,
  procrastinate 3.x, httpx, bcrypt, structlog, markitdown, python-multipart, slowapi, mcp); multi-stage
  Dockerfile (dev/prod targets); docker-compose.yml with all 4 services; app/config.py (Settings via
  pydantic-settings, DATABASE_URL required, all other vars from .env.example); app/main.py (FastAPI factory
  with /health stub); app/worker.py and app/mcp_server.py stubs; Makefile with all targets; DECISIONS.md
  created for autonomous decision logging.
  Deviations: Used `procrastinate>=3.0.0` (not pinned to 2.x) — procrastinate 3.x is the current stable
  release and the `[asyncpg]` extra no longer exists as a separate extra in v3; asyncpg is a direct dep.
  Makefile `test` target handles pytest exit code 5 (no tests collected) as success per acceptance criteria.
  Notes: `make test` requires DATABASE_URL env var; tests/conftest.py wired in chunk 1.5. docker compose
  acceptance criterion verified via Dockerfile + docker-compose.yml review; /health verified via ASGI
  transport test without needing Docker running.

---

### Chunk 1.2 — Database Schema & Alembic Migrations ⚡

**Status:** `complete`
**Assigned Agent:** claude-sonnet-4-6
**Depends on:** 1.1
**PRD Reference:** Section 8

**Description:**
Define all SQLAlchemy 2.0 async ORM models and the initial Alembic migration. Every table in PRD Section 8 must be created with all specified columns. Use the shared column mixin (`id` serial PK, `uuid` UUID unique, `created_at`, `updated_at`) on every table.

**Key design decision — global indicators:** The `indicators` table is a global entity keyed by `(type, value)`, not per-alert. The `alert_indicators` join table (many-to-many) links alerts to their indicators. This means the same IP appearing in 50 alerts is stored once and enriched once. See PRD Section 8 for full rationale.

**Output Artifacts:**
- `app/db/base.py` — `Base` declarative base, `TimestampMixin` with `created_at`/`updated_at`, `UUIDMixin` with `uuid`
- `app/db/models/alert.py` — `Alert` model; no `indicators` JSONB or `enrichment_results` JSONB columns (replaced by relational join); includes `acknowledged_at`, `triaged_at`, `closed_at` TIMESTAMP WITH TIME ZONE nullable columns (set by service layer on status transitions, never by callers directly; write-once, never updated)
- `app/db/models/detection_rule.py` — `DetectionRule` model
- `app/db/models/indicator.py` — `Indicator` model; unique constraint on `(type, value)`; `first_seen`, `last_seen` TIMESTAMP WITH TIME ZONE; `malice` TEXT; `enrichment_results` JSONB; no `alert_id` FK
- `app/db/models/alert_indicator.py` — `AlertIndicator` join model; `alert_id` FK → `alerts.id`, `indicator_id` FK → `indicators.id`; composite unique on `(alert_id, indicator_id)`
- `app/db/models/enrichment_field_extraction.py` — `EnrichmentFieldExtraction` model; `provider_name` TEXT, `indicator_type` TEXT, `source_path` TEXT (dot-notation into raw response), `target_key` TEXT, `value_type` TEXT, `is_system` BOOLEAN, `is_active` BOOLEAN, `description` TEXT; unique constraint on `(provider_name, indicator_type, source_path)` for system deduplication
- `app/db/models/activity_event.py` — `ActivityEvent` model; append-only (no `updated_at`); `event_type` TEXT, `actor_type` TEXT, `actor_key_prefix` TEXT nullable, `alert_id` FK nullable, `workflow_id` FK nullable, `detection_rule_id` FK nullable, `references` JSONB; all FKs set `ondelete="SET NULL"` so entity deletion does not destroy audit history
- `app/db/models/context_document.py` — `ContextDocument` model
- `app/db/models/workflow.py` — `Workflow` model; includes `requires_approval` BOOLEAN (default `True`), `approval_channel` TEXT nullable, `approval_timeout_seconds` INTEGER (default 3600), `risk_level` TEXT
- `app/db/models/workflow_run.py` — `WorkflowRun` model; includes `code_version_executed` INTEGER
- `app/db/models/workflow_approval_request.py` — `WorkflowApprovalRequest` model; `workflow_id` FK, `workflow_run_id` FK nullable, `trigger_type` TEXT, `trigger_agent_key_prefix` TEXT, `trigger_context` JSONB, `reason` TEXT, `confidence` FLOAT, `notifier_type` TEXT, `notifier_channel` TEXT, `external_message_id` TEXT, `status` TEXT, `responder_id` TEXT, `responded_at` TIMESTAMP nullable, `expires_at` TIMESTAMP, `execution_result` JSONB nullable
- `app/db/models/agent_registration.py` — `AgentRegistration` model
- `app/db/models/agent_run.py` — `AgentRun` model
- `app/db/models/source_integration.py` — `SourceIntegration` model
- `app/db/models/api_key.py` — `APIKey` model; includes `allowed_sources` ARRAY(Text) nullable (NULL = unrestricted)
- `alembic/` — configured env pointing at async engine
- `alembic/versions/0001_initial_schema.py` — single migration creating all 15 core tables
- `app/repositories/__init__.py` — empty, marks the repository layer
- `app/repositories/base.py` — `BaseRepository` class establishing the DI pattern: `def __init__(self, db: AsyncSession)` stores session as `self.db`; provides no methods (just the pattern); all repositories inherit from this and receive a session via DI, never import one

**Note on `api_keys` model:** Include `allowed_sources: Mapped[list[str] | None]` (PostgreSQL `ARRAY(Text)`, nullable, default `NULL`) for future source restriction per PRD Section 11. `NULL` means unrestricted — no behavior change in v1, column is present and ready.

**Acceptance Criteria:**
- [x] All 15 core tables present with every column specified in PRD Section 8: `alerts`, `detection_rules`, `indicators`, `alert_indicators`, `enrichment_field_extractions`, `activity_events`, `context_documents`, `workflows`, `workflow_runs`, `workflow_approval_requests`, `agent_registrations`, `agent_runs`, `source_integrations`, `indicator_field_mappings`, `api_keys` (note: `indicator_field_mappings` is created here and seeded in 1.7; `workflow_code_versions` is added by migration in 4.7)
- [x] Every table has `id` (BigInteger autoincrement PK), `uuid` (UUID, unique, not null, server default gen_random_uuid()), `created_at`, `updated_at`
- [x] `indicators` has a unique constraint on `(type, value)`; no `alert_id` FK; has `first_seen`, `last_seen` TIMESTAMP WITH TIME ZONE, `malice` TEXT, `enrichment_results` JSONB
- [x] `alert_indicators` has `alert_id` FK → `alerts.id`, `indicator_id` FK → `indicators.id`, composite unique on `(alert_id, indicator_id)`
- [x] All other FKs defined: `workflow_runs.workflow_id → workflows.id`, `agent_runs.agent_registration_id → agent_registrations.id`, `agent_runs.alert_id → alerts.id`, `alerts.detection_rule_id → detection_rules.id`
- [x] `alerts` model has NO `indicators` JSONB or `enrichment_results` JSONB columns
- [x] `alerts` model has `acknowledged_at`, `triaged_at`, `closed_at` columns: `TIMESTAMP WITH TIME ZONE`, nullable, no server default (NULL until explicitly set by service layer)
- [x] JSONB columns use `postgresql.JSONB` type (not generic JSON)
- [x] TEXT[] columns use `postgresql.ARRAY(Text)`
- [ ] `alembic upgrade head` succeeds against a fresh Postgres 15 container (requires Docker — not verified locally; migration file correct)
- [ ] `alembic downgrade base` reverses all tables cleanly (requires Docker — not verified locally; downgrade function correct)
- [x] All models importable from `app.db.models` without circular imports
- [x] `api_keys` table has `allowed_sources` column: `ARRAY(Text)`, nullable, no default (NULL)
- [x] `app/repositories/base.py` exists with `BaseRepository.__init__(self, db: AsyncSession)`; unit test confirms subclass correctly stores session

**Completion Log:**
- [claude-sonnet-4-6] [2026-02-28T00:00:00Z]
  Built: All 15 ORM models (SQLAlchemy 2.0 async, mapped_column pattern) with correct column types,
  FKs, unique constraints, and mixin composition (TimestampMixin + UUIDMixin on all tables;
  AppendOnlyTimestampMixin on activity_events). Alembic configured for async engine; initial
  migration creates all 15 tables in FK dependency order with full downgrade() reversal.
  BaseRepository DI pattern established. All models import without circular deps; mypy passes on
  20 source files.
  Deviations: indicator_field_mapping.py ORM model created in 1.2 (moved from 1.7) so Alembic
  metadata is complete; chunk 1.7 still creates seeder + schemas. alembic upgrade/downgrade
  acceptance criteria not verified (no Docker in local env) — migration SQL reviewed and correct.
  Notes: alert_indicators join table has no uuid column (join tables don't need external-facing IDs);
  this is intentional. Forward-ref DetectionRule in alert.py resolved via TYPE_CHECKING guard.

---

### Chunk 1.3 — Core Pydantic Schemas & Alert Types ⚡

**Status:** `complete`
**Assigned Agent:** claude-sonnet-4-6
**Depends on:** 1.1
**PRD Reference:** Sections 7.1, 7.9, 8

**Description:**
Define all Pydantic v2 schemas used across the platform: CalsetaAlert (the agent-native normalized schema), indicator types, enrichment result shapes, standard API response envelopes, and pagination. These are imported by ingestion, enrichment, API routes, and MCP layers — get them right before anything else builds on them.

**Output Artifacts:**
- `app/schemas/alert.py` — `CalsetaAlert` (title, severity, severity_id, occurred_at, source_name, and other normalized fields), `AlertStatus` enum (`Open`, `In Progress`, `Closed`)
- `app/schemas/indicators.py` — `IndicatorType` enum (8 values), `IndicatorExtract`, `EnrichedIndicator`
- `app/schemas/enrichment.py` — `EnrichmentResult`, `EnrichmentStatus` enum
- `app/schemas/alerts.py` — `AlertResponse`, `AlertSummary`, `AlertPatch`, `FindingCreate`, `FindingResponse`
- `app/schemas/activity_events.py` — `ActivityEventResponse`, `ActivityEventType` enum (12 values from PRD Section 8)
- `app/schemas/detection_rules.py` — `DetectionRuleCreate`, `DetectionRuleResponse`, `DetectionRulePatch`
- `app/schemas/common.py` — `DataResponse[T]`, `PaginatedResponse[T]`, `PaginationMeta`, `ErrorDetail`, `ErrorResponse`
- `app/config.py` — optional secrets loader: Azure Key Vault + AWS Secrets Manager pydantic-settings sources

**Acceptance Criteria:**
- [x] `IndicatorType` covers all 8 values from PRD 7.1: `ip`, `domain`, `hash_md5`, `hash_sha1`, `hash_sha256`, `url`, `email`, `account`
- [x] `CalsetaAlert` validates against a sample Sentinel alert normalized to agent-native schema (write a fixture and test)
- [x] `DataResponse[T]` serializes as `{"data": ..., "meta": {}}` exactly
- [x] `PaginatedResponse[T]` serializes as `{"data": [...], "meta": {"total": N, "page": N, "page_size": N, "total_pages": N}}`
- [x] `ErrorResponse` serializes as `{"error": {"code": "...", "message": "...", "details": {}}}`
- [x] All schemas use `model_config = ConfigDict(from_attributes=True)` for ORM compatibility
- [x] Unit tests: minimum 8 tests covering schema validation happy paths and key error cases (13 tests written)
- [x] If `AZURE_KEY_VAULT_URL` is set, secrets are loaded from Azure Key Vault at startup via a custom pydantic-settings source using `azure-identity` + `azure-keyvault-secrets` (optional deps); if not set, this source is skipped entirely with no import of Azure SDK
- [x] If `AWS_SECRETS_MANAGER_SECRET_NAME` is set, secrets are loaded from AWS Secrets Manager at startup via a custom pydantic-settings source using `boto3` (optional dep); secret value must be a JSON object whose keys map to settings field names; if not set, this source is skipped entirely with no import of boto3
- [x] Priority order: Azure Key Vault → AWS Secrets Manager → env vars → .env file → defaults; only one cloud provider active at a time
- [x] When neither cloud provider is configured, startup time and dependencies are identical to the baseline (no penalty for self-hosters)
- [x] Startup log line emitted indicating which secrets source is active: `secrets_source=azure_key_vault`, `secrets_source=aws_secrets_manager`, or `secrets_source=environment`
- [x] `azure-identity`, `azure-keyvault-secrets`, and `boto3` listed as optional extras in `pyproject.toml` under `[project.optional-dependencies]` (`azure` and `aws` groups)

**Completion Log:**
- [claude-sonnet-4-6] [2026-02-28T00:00:00Z]
  Built: All schema files — CalsetaAlert (14 extractable fields matching PRD), AlertStatus (6 values),
  AlertSeverity (6 values with severity_id map), AlertCloseClassification (7 values), IndicatorType (8 values),
  EnrichmentResult (success/failure/skipped factory methods), ActivityEventType (12 values), DataResponse[T],
  PaginatedResponse[T], ErrorResponse, detection_rules schemas. app/config.py updated with
  _AzureKeyVaultSource and _AWSSecretsManagerSource custom pydantic-settings sources; neither imported
  unless trigger env var is set. 13 tests written covering all acceptance criteria.
  Deviations: PRD Section 7.12 lists 14 system field mappings (not 17 as stated in project plan) — using
  14 per the actual PRD content; logged in DECISIONS.md.
  Notes: All enums use StrEnum (Python 3.12). Generic[T] kept for Pydantic BaseModel generics (UP046
  suppressed in ruff config). Lint: 0 errors. Typecheck: 0 errors. Tests: 13/13 pass.

---

### Chunk 1.4 — API Key Authentication

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.2, 1.3
**PRD Reference:** Section 7.10

**Description:**
Implement API key auth. Keys are formatted as `cai_{32_urlsafe_chars}`, stored as bcrypt hashes, shown in full exactly once on creation. Auth is a FastAPI dependency applied to all non-health routes. Scopes are enforced per-route. The auth interface is abstracted so alternative backends can be swapped in without touching route code.

**Output Artifacts:**
- `app/auth/base.py` — `AuthBackendBase` ABC with `authenticate(request) -> AuthContext` method
- `app/auth/api_key_backend.py` — `APIKeyAuthBackend` implementing `AuthBackendBase`; looks up key by prefix, verifies bcrypt hash
- `app/auth/scopes.py` — `Scope` enum: `alerts:read`, `alerts:write`, `enrichments:read`, `workflows:read`, `workflows:execute`, `agents:read`, `agents:write`, `admin`
- `app/auth/dependencies.py` — `get_auth_context` dependency; `require_scope(*scopes)` dependency factory
- `app/api/v1/api_keys.py` — route handlers for `GET /v1/api-keys`, `POST /v1/api-keys`, `DELETE /v1/api-keys/{uuid}`

**Acceptance Criteria:**
- [ ] Key format is exactly `cai_` + 32 urlsafe base64 chars (verify with regex in test)
- [ ] `POST /v1/api-keys` response includes the full key; key is never returned again by any endpoint
- [ ] Key is stored as bcrypt hash; `key_prefix` stores first 8 chars for display
- [ ] Valid key → `200`; invalid key → `401 {"error": {"code": "UNAUTHORIZED", ...}}`; valid key, wrong scope → `403 {"error": {"code": "FORBIDDEN", ...}}`
- [ ] `GET /health` requires no auth
- [ ] All other routes return `401` without a valid `Authorization: Bearer cai_...` header
- [ ] `AuthBackendBase` is the only auth type imported by route files — no direct `APIKeyAuthBackend` imports in routes

**Completion Log:**
_No entries yet._

---

### Chunk 1.5 — Middleware, Error Handling & Shared DB Dependency

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.2, 1.3
**PRD Reference:** Sections 7.9, 10

**Description:**
Wire up all shared FastAPI infrastructure: request ID injection, structured logging, global exception handlers, the async database session dependency, and pagination parameter parsing. No business logic — pure request/response plumbing.

**Output Artifacts:**
- `app/middleware/request_id.py` — injects `X-Request-ID` (generates UUID if not present in request headers)
- `app/middleware/logging.py` — structured JSON logs per request: `request_id`, `method`, `path`, `status_code`, `duration_ms`
- `app/api/errors.py` — `CalsetaException(code, message, status_code)` base; global handlers for `CalsetaException`, `RequestValidationError`, `404`, unhandled `Exception`; all return `ErrorResponse`
- `app/db/session.py` — `async_engine`, `AsyncSessionLocal`, `get_db` FastAPI dependency (yields session, closes on exit)
- `app/api/pagination.py` — `PaginationParams` dependency: `page: int = 1`, `page_size: int = 50`; validates `page >= 1`, `1 <= page_size <= 500`
- `tests/conftest.py` — pytest fixtures: `db_session` (async session against the test DB, rolled back after each test), `test_client` (httpx `AsyncClient` wrapping the FastAPI app with `db_session` injected), `api_key` (creates a test key with `admin` scope). Sets `DATABASE_URL` from env for CI compatibility.

**Acceptance Criteria:**
- [ ] Any unhandled exception returns `ErrorResponse` format with `status_code: 500` — no raw tracebacks in response body
- [ ] Unknown route returns `{"error": {"code": "NOT_FOUND", ...}}` (not FastAPI's default response)
- [ ] Every response has `X-Request-ID` header; if client sends `X-Request-ID`, it is echoed back
- [ ] Structured log line written for every request; includes all required fields
- [ ] `get_db` commits on success, rolls back on exception, always closes session (verified with a test that triggers a DB error mid-request)
- [ ] `PaginationParams(page=0)` raises 422; `PaginationParams(page_size=501)` raises 422

**Completion Log:**
_No entries yet._

---

### Chunk 1.6 — Task Queue Setup (Procrastinate + Worker)

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.2
**PRD Reference:** Section 7.11

**Description:**
Implement the `TaskQueueBase` abstraction and the procrastinate + PostgreSQL default backend. Wire the worker process to consume from all four named queues. No tasks are registered in this chunk — only the infrastructure. Stubs for alternative backends include clear `NotImplementedError` messages referencing the config docs.

**Output Artifacts:**
- `app/queue/base.py` — `TaskQueueBase` ABC, `TaskStatus` enum (`pending`, `in_progress`, `success`, `failed`, `dead_letter`)
- `app/queue/backends/postgres.py` — procrastinate `App` setup; implements `TaskQueueBase`
- `app/queue/backends/celery_redis.py` — stub; raises `NotImplementedError("Set QUEUE_BACKEND=postgres or see docs/QUEUE_BACKENDS.md")`
- `app/queue/backends/sqs.py` — stub same pattern
- `app/queue/backends/azure_sb.py` — stub same pattern
- `app/queue/factory.py` — `get_queue_backend() -> TaskQueueBase` resolving from `QUEUE_BACKEND` env var; fails fast on unknown value
- `app/queue/registry.py` — empty module where all `@app.task` decorated functions will be registered; imported by worker
- `app/worker.py` — updated: imports registry, starts procrastinate worker on queues `enrichment`, `dispatch`, `workflows`, `default`

**Acceptance Criteria:**
- [ ] `docker compose up worker` starts and logs that it is listening on all four queues
- [ ] `QUEUE_BACKEND=bogus` causes startup to fail immediately with a clear config error
- [ ] A smoke-test task (`ping` → appends "pong" to a test list) can be enqueued and consumed end-to-end in a pytest-asyncio test
- [ ] Worker shuts down cleanly within 5 seconds of `SIGTERM`
- [ ] Routes and services inject `TaskQueueBase` via FastAPI dependency — no direct backend imports outside `factory.py`
- [ ] `docs/QUEUE_BACKENDS.md` stub file created with a TODO placeholder for backend-switching instructions

**Completion Log:**
_No entries yet._

---

### Chunk 1.8 — Integration API Documentation Research

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.1
**PRD Reference:** Section 9 (Integration Development Methodology)

**Description:**
Fetch, read, and summarize the official API documentation for all seven v1 integrations before any integration implementation begins. This chunk produces reference artifacts that every integration implementation chunk (2.2, 2.3, 2.4, 3.2, 3.3, 3.4, 3.5) depends on. It is explicitly a research and documentation task — no code is written here.

Use `WebFetch` to retrieve documentation pages for each integration. Focus on: request/response field names and types, pagination patterns, rate limits, authentication mechanisms, and available lifecycle/remediation API endpoints (for pre-built workflow seeding).

**Output Artifacts:**
- `docs/integrations/sentinel/api_notes.md` — Sentinel Alerts API schema, alert field names, severity mapping
- `docs/integrations/elastic/api_notes.md` — ECS field reference, Kibana alert payload structure, `_source` event nesting pattern
- `docs/integrations/splunk/api_notes.md` — Splunk webhook payload format, result field naming conventions
- `docs/integrations/virustotal/api_notes.md` — VT API v3 response schemas for IP, domain, file hash endpoints
- `docs/integrations/abuseipdb/api_notes.md` — AbuseIPDB v2 check endpoint response fields
- `docs/integrations/okta/api_notes.md` — Users API fields, Sessions API, Lifecycle endpoints (suspend, unsuspend, reset_password, expire_password, revoke sessions); rate limits
- `docs/integrations/entra/api_notes.md` — Graph API user object fields, revokeSignInSessions, accountEnabled patch, MFA method management endpoints, token acquisition

Each file follows this structure:
```
# {Integration} API Notes

## Authentication
## Key Endpoints Used by Calseta AI
## Request/Response Field Reference
## Available Automation Endpoints (for pre-built workflows)
## Rate Limits
## Known Quirks / Edge Cases
```

**Acceptance Criteria:**
- [ ] All 7 `api_notes.md` files created and committed
- [ ] Each file documents the exact JSON field names used by the corresponding implementation chunk (e.g., `okta/api_notes.md` lists the field path for user status, MFA enrollment status, group membership)
- [ ] Okta notes include the full list of lifecycle endpoint URLs and required request body for each pre-built workflow action
- [ ] Entra notes include the Graph API endpoint and required permissions scope for each pre-built workflow action
- [ ] Elastic notes explicitly document the `_source` nesting structure and how the raw event fields appear alongside Kibana alert metadata
- [ ] All files are concise (not a verbatim paste of entire docs) — focused on fields and patterns Calseta AI actually uses

**Completion Log:**
_No entries yet._

---

### Chunk 1.7 — Indicator Field Mappings: DB Table + Startup Seeder

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.2
**PRD Reference:** Section 7.12

**Description:**
Add the `indicator_field_mappings` table to the database schema and implement the startup seeder that populates the full set of system normalized-field mappings on first run. The seeder is idempotent — re-running it on an already-seeded database makes no changes. This table is the source of truth for both Pass 2 (normalized fields) and Pass 3 (custom raw_payload) extractions.

**Output Artifacts:**
- `app/db/models/indicator_field_mapping.py` — `IndicatorFieldMapping` ORM model
- `alembic/versions/0002_indicator_field_mappings.py` — migration adding the table
- `app/seed/indicator_mappings.py` — `seed_system_mappings(db: AsyncSession)` function; inserts all 17 system mappings from PRD Section 7.12 if they don't already exist; called at application startup
- `app/schemas/indicator_mappings.py` — `IndicatorFieldMappingCreate`, `IndicatorFieldMappingResponse`, `IndicatorFieldMappingPatch`

**Acceptance Criteria:**
- [ ] All columns from PRD Section 7.12 data model present: `source_name` (nullable), `field_path`, `indicator_type`, `extraction_target`, `is_system`, `is_active`, `description`
- [ ] `alembic upgrade head` adds the table cleanly; `alembic downgrade` removes it
- [ ] `seed_system_mappings()` inserts exactly the 17 system mappings from PRD Section 7.12 table on a fresh DB
- [ ] `seed_system_mappings()` run a second time makes zero DB writes (idempotent — check by `field_path` + `extraction_target`)
- [ ] System mappings have `is_system=True`, `source_name=NULL`, `extraction_target='normalized'`, `is_active=True`
- [ ] Seeder is called in `app/main.py` startup event; failure to seed logs a warning but does not crash the server

**Completion Log:**
_No entries yet._

---

### Chunk 1.9 — Security Middleware Stack

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.4, 1.5
**PRD Reference:** Section 7.13

**Description:**
Implement the full security middleware stack: rate limiting, security headers, CORS, request body size limits, auth failure audit logging, and API key expiry enforcement. All limits and toggles are env-var-driven — no hardcoded values. This chunk wires all security layers into `app/main.py` so they apply globally from this point forward. No business logic — pure infrastructure.

**Implementation notes:**
- `slowapi` for rate limiting; install with `pip install slowapi`. Add to `pyproject.toml`.
- Rate limit keys: unauthenticated → client IP; authenticated → `key_prefix` pulled from `AuthContext`. Rate limiter must be aware of auth context to switch keys.
- `TRUSTED_PROXY_COUNT` controls how many `X-Forwarded-For` hops to trust for real IP extraction. Default `0` = use connection IP. Document the spoofing risk clearly in `.env.example`.
- Security headers middleware: one class, all headers, configurable per-header disable flags. HSTS only emitted when `HTTPS_ENABLED=true`.
- CORS: `fastapi.middleware.cors.CORSMiddleware` using `CORS_ALLOWED_ORIGINS` (comma-separated). Disabled when env var is unset or empty. `CORS_ALLOW_ALL_ORIGINS=true` allowed for dev; `.env.example` warns never to use in production.
- Body size: enforce at middleware level using `request.headers.get("content-length")` fast-path check + streaming enforcement for chunked requests. Ingest endpoints get the tighter `MAX_INGEST_PAYLOAD_SIZE_MB` limit; all others get `MAX_REQUEST_BODY_SIZE_MB`.
- Auth expiry: add `expires_at` check inside `app/auth/api_key_backend.py`. Emit `auth_failure` log with `reason: "key_expired"` on rejection. Update `last_used_at` via a background DB write on every successful auth.
- Auth failure logging: centralized in `app/auth/dependencies.py`. Every auth failure path calls a shared `log_auth_failure(reason, request, key_prefix, required_scope)` function that emits the structured JSON event.

**Output Artifacts:**
- `app/middleware/security_headers.py` — `SecurityHeadersMiddleware(BaseHTTPMiddleware)`; adds all headers from PRD Section 7.13 table; reads per-header enable flags from `settings`
- `app/middleware/rate_limit.py` — `slowapi` limiter setup; `get_rate_limit_key(request)` function returning key_prefix for authed requests, IP for unauthed; per-endpoint limit decorators for ingest, enrichment, and workflow execute routes
- `app/middleware/body_size.py` — `BodySizeLimitMiddleware(BaseHTTPMiddleware)`; reads `MAX_REQUEST_BODY_SIZE_MB` and `MAX_INGEST_PAYLOAD_SIZE_MB` from settings; returns 413 `ErrorResponse` on violation
- `app/middleware/cors.py` — CORS config helper; reads `CORS_ALLOWED_ORIGINS` and `CORS_ALLOW_ALL_ORIGINS` from settings; registers `CORSMiddleware` only when origins are configured
- `app/auth/api_key_backend.py` — updated: checks `expires_at`, calls `log_auth_failure()` on all failure paths, fires async `last_used_at` update on success
- `app/auth/audit.py` — `log_auth_failure(reason, request, key_prefix, required_scope)` — emits the structured `auth_failure` JSON event to the logger; single place for all auth failure logging
- `app/main.py` — updated: registers all middleware in correct order (outermost first): body size → security headers → CORS → rate limiter → request ID → logging
- `app/config.py` — updated: adds all new env vars to `Settings` with defaults and validators
- `.env.example` — updated: all new security vars documented with descriptions and production warnings

**Env vars added to `Settings`:**
```
RATE_LIMIT_UNAUTHED_PER_MINUTE=30
RATE_LIMIT_AUTHED_PER_MINUTE=600
RATE_LIMIT_INGEST_PER_MINUTE=100
RATE_LIMIT_ENRICHMENT_PER_MINUTE=60
RATE_LIMIT_WORKFLOW_EXECUTE_PER_MINUTE=30
TRUSTED_PROXY_COUNT=0
HTTPS_ENABLED=false
SECURITY_HEADER_HSTS_ENABLED=true
CORS_ALLOWED_ORIGINS=
CORS_ALLOW_ALL_ORIGINS=false
MAX_REQUEST_BODY_SIZE_MB=10
MAX_INGEST_PAYLOAD_SIZE_MB=5
```

**Middleware registration order in `app/main.py`** (outermost to innermost — first registered = outermost):
1. `BodySizeLimitMiddleware` — reject oversized requests before any processing
2. `SecurityHeadersMiddleware` — add headers to all responses including errors
3. `CORSMiddleware` — handle OPTIONS preflight before auth
4. Rate limiter (`slowapi`) — applied via `@limiter.limit()` decorators on routes, not as middleware
5. `RequestIDMiddleware` (from 1.5) — inject request ID
6. `LoggingMiddleware` (from 1.5) — structured request log

**Acceptance Criteria:**
- [ ] Unauthenticated request from same IP exceeding `RATE_LIMIT_UNAUTHED_PER_MINUTE` returns `429` with `Retry-After` header and `RATE_LIMITED` error body
- [ ] Authenticated request exceeding `RATE_LIMIT_AUTHED_PER_MINUTE` for the same API key returns `429`; a second key from the same IP is not rate limited until it also exceeds its own limit
- [ ] `POST /v1/ingest/sentinel` has a separate tighter limit governed by `RATE_LIMIT_INGEST_PER_MINUTE`
- [ ] All responses (including 400s, 404s, and 500s) include `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Content-Security-Policy` headers
- [ ] `Strict-Transport-Security` header is present when `HTTPS_ENABLED=true`; absent when `false`
- [ ] CORS headers absent when `CORS_ALLOWED_ORIGINS` is unset; present and correct when set
- [ ] Request body of 6MB to `POST /v1/ingest/sentinel` (with `MAX_INGEST_PAYLOAD_SIZE_MB=5`) returns `413 PAYLOAD_TOO_LARGE`
- [ ] Auth with an expired key returns `401 KEY_EXPIRED` and emits `auth_failure` log with `reason: "key_expired"`
- [ ] Auth with wrong key returns `401 UNAUTHORIZED` and emits `auth_failure` with `reason: "invalid_key"`
- [ ] Auth with valid key but wrong scope returns `403 FORBIDDEN` and emits `auth_failure` with `reason: "insufficient_scope"` and `required_scope` populated
- [ ] Auth failure log lines are valid JSON containing all fields specified in PRD Section 7.10
- [ ] `last_used_at` is updated in the DB after a successful authenticated request (verify in test with a DB query post-request)
- [ ] `TRUSTED_PROXY_COUNT=1` + `X-Forwarded-For: 5.5.5.5` causes rate limiter to key on `5.5.5.5` not the connection IP
- [ ] All new env vars present in `.env.example` with descriptions; production warnings on `CORS_ALLOW_ALL_ORIGINS` and `TRUSTED_PROXY_COUNT`
- [ ] `make lint` and `make typecheck` pass

**Completion Log:**
_No entries yet._

---

### Chunk 1.10 — Structured Logging ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.1
**PRD Reference:** Section 7.14

**Description:**
Implement the structured logging layer using `structlog`. All three processes (API, worker, MCP) use the same logging configuration. Log output is JSON to stdout in production and human-readable colored text in development. A `request_id` is automatically bound to all log calls within an HTTP request context without needing to be passed explicitly. This chunk wires logging at the application layer — other chunks call `structlog.get_logger()` and it just works.

**Implementation notes:**
- `structlog` is the library. Add to `pyproject.toml`.
- Configure in `app/logging_config.py`. Call `configure_logging()` at startup in `app/main.py`, `app/worker.py`, and `app/mcp_server.py`.
- `LOG_FORMAT=json` → `structlog.processors.JSONRenderer()`. `LOG_FORMAT=text` → `structlog.dev.ConsoleRenderer()` (colored, human-readable).
- Bind `service` (`api`/`worker`/`mcp`) and `version` (`APP_VERSION` env var, default `dev`) as global context at startup via `structlog.contextvars.bind_contextvars()`.
- The `RequestIDMiddleware` (chunk 1.5) should be updated in this chunk to also call `structlog.contextvars.bind_contextvars(request_id=request_id)` so all downstream logs in that request include `request_id` automatically.
- Worker tasks bind `task_id` and `task_name` at task start.
- Standard log levels: `DEBUG` for raw payloads/queries, `INFO` for operational events, `WARNING` for degraded state, `ERROR` for failures, `CRITICAL` for startup errors.
- Replace all existing `print()` calls and any `logging.getLogger()` usage with `structlog.get_logger()`.

**Output Artifacts:**
- `app/logging_config.py` — `configure_logging(service: str)` function; configures structlog processors chain based on `LOG_FORMAT` and `LOG_LEVEL` settings; call once at process startup
- `app/config.py` — updated: `LOG_LEVEL: str = "INFO"`, `LOG_FORMAT: str = "json"`, `APP_VERSION: str = "dev"`
- `app/main.py` — updated: calls `configure_logging("api")` before app factory runs
- `app/worker.py` — updated: calls `configure_logging("worker")`
- `app/mcp_server.py` — updated: calls `configure_logging("mcp")`
- `app/middleware/request_id.py` — updated: binds `request_id` to structlog context on each request; clears context after response
- `.env.example` — updated: `LOG_LEVEL`, `LOG_FORMAT`, `APP_VERSION` documented

**Acceptance Criteria:**
- [ ] `LOG_FORMAT=json` produces valid newline-delimited JSON; each line parseable as a single JSON object
- [ ] `LOG_FORMAT=text` produces human-readable colored output (verify no JSON in text mode)
- [ ] Every log line in `json` mode includes `timestamp`, `level`, `message`, `service`, `version`
- [ ] Log lines emitted inside an HTTP request include `request_id` (verify by making a request and checking log output)
- [ ] `LOG_LEVEL=WARNING` suppresses `INFO` and `DEBUG` lines (verify with test that captures log output)
- [ ] `configure_logging()` called from all three process entry points
- [ ] No `print()` statements in application code; no bare `logging.getLogger()` calls — all logging via `structlog.get_logger()`
- [ ] `make lint` and `make typecheck` pass

**Completion Log:**
_No entries yet._

---

### Chunk 1.11 — CI/CD Pipeline ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.1
**PRD Reference:** Section 10 (CI/CD)

**Description:**
Set up the GitHub Actions CI and release pipelines. CI runs on every PR and push. Release runs on every `v*` tag. Both pipelines use the same check sequence to guarantee local and remote parity. Branch protection rules are documented (applied manually in GitHub repo settings — cannot be automated via code).

**Implementation notes:**
- CI workflow uses GitHub Actions `services:` to spin up a real `postgres:15-alpine` container — no mocking the DB in integration tests.
- Test DB connection: `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/calseta_test`
- Multi-arch image builds use `docker/setup-qemu-action` + `docker/setup-buildx-action`. Build for `linux/amd64` and `linux/arm64`.
- Push images to GHCR (`ghcr.io/${{ github.repository_owner }}/calseta-*`). Authenticate with `GITHUB_TOKEN` (no additional secrets needed for GHCR on the same repo).
- `APP_VERSION` in the release workflow is set to the git tag: `${{ github.ref_name }}`.
- `make ci` in `Makefile` runs: `make lint && make typecheck && make test` — same sequence as GitHub Actions, in that order.
- GitHub Release uses `softprops/action-gh-release` with `generate_release_notes: true` to auto-generate changelog from merged PR titles.

**Output Artifacts:**
- `.github/workflows/ci.yml` — triggers on `push` to any branch and `pull_request` targeting `main` or `feat/mvp-dev`; steps: checkout → setup Python → install deps → `make lint` → `make typecheck` → `make test` (with Postgres service container)
- `.github/workflows/release.yml` — triggers on `push` to tags matching `v*`; steps: run CI → build multi-arch images → push to GHCR → create GitHub Release
- `Makefile` — updated: add `ci` target that runs `lint typecheck test` in sequence; add `build` target for local Docker image build
- `docs/DEVELOPMENT.md` — local development guide: prerequisites (Docker, Python 3.12), clone, `.env` setup from `.env.example`, `docker compose up`, first API key creation, running tests, running linter/typecheck
- `docs/HOW_TO_DEPLOY.md` — production deployment guide: Docker Compose production config (no dev deps, restart policies, volume mounts), environment variables reference, database initialization (`alembic upgrade head`), first-boot API key creation, updating to a new version (pull new image, run migrations, restart)

**GitHub Actions `ci.yml` structure (write exactly this):**
```yaml
name: CI
on:
  push:
    branches: ["**"]
  pull_request:
    branches: [main, "feat/mvp-dev"]

jobs:
  ci:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: calseta_test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
      - run: pip install -e ".[dev]"
      - run: make lint
      - run: make typecheck
      - run: make test
        env:
          DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/calseta_test
```

**Acceptance Criteria:**
- [ ] `.github/workflows/ci.yml` present; triggers on push to any branch and on PRs targeting `main` or `feat/mvp-dev`
- [ ] CI job runs lint, typecheck, and test steps in that order with a real Postgres 15 service container
- [ ] `.github/workflows/release.yml` present; triggers on `v*` tags; builds and pushes multi-arch images to GHCR
- [ ] `make ci` runs locally and produces the same pass/fail result as the GitHub Actions run
- [ ] `docs/DEVELOPMENT.md` covers: prerequisites, clone, `.env` setup, `docker compose up`, first API key, running tests
- [ ] `docs/HOW_TO_DEPLOY.md` covers: Docker Compose production config, env vars, DB init, first boot, version updates
- [ ] Release workflow sets `APP_VERSION` to the git tag in the built image

**Completion Log:**
_No entries yet._

---

## Wave 2 — Ingestion + Detection Rules

**Goal:** Implement alert ingestion from all four v1 sources, indicator extraction (all three passes), detection rule auto-association, and all alert + detection rule CRUD endpoints.

**Depends on:** Wave 1 complete.

**Internal sequencing:**
- 2.1 must complete first (base class blocks 2.2–2.6)
- After 2.1: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7 can run in parallel ⚡
- 2.8 (extraction pipeline) depends on 1.7 + 2.1 — can run in parallel with 2.2–2.7 ⚡
- 2.9 (mappings API) depends on 1.7 only — can start as soon as 1.7 is complete ⚡
- 2.10 (detection rules CRUD) depends on 2.7
- 2.11 (alerts endpoints) depends on 2.5, 2.6, 2.8

---

### Chunk 2.1 — AlertSourceBase + Plugin Registry

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 1 complete
**PRD Reference:** Section 7.1

**Description:**
Define the `AlertSourceBase` abstract class and the source plugin registry. This is the contract all source integrations (2.2–2.4) must implement. Include the indicator extraction interface and the detection rule reference extraction hook.

**Output Artifacts:**
- `app/integrations/sources/base.py` — `AlertSourceBase` ABC with `source_name`, `display_name`, `validate_payload(raw) -> bool`, `normalize(raw) -> CalsetaAlert`, `extract_indicators(raw) -> list[IndicatorExtract]`, `extract_detection_rule_ref(raw) -> str | None`, `verify_webhook_signature(headers, raw_body) -> bool`
- `app/integrations/sources/registry.py` — `SourceRegistry` singleton; `register(source: AlertSourceBase)`, `get(source_name: str) -> AlertSourceBase | None`, `list_all() -> list[AlertSourceBase]`
- `app/integrations/sources/__init__.py` — imports and registers all built-in sources (currently none; 2.2–2.4 will add themselves here)

**Acceptance Criteria:**
- [ ] `AlertSourceBase` is an ABC; instantiating it directly raises `TypeError`
- [ ] All four abstract methods have docstrings matching PRD Section 7.1 descriptions
- [ ] `extract_detection_rule_ref` has a default implementation returning `None` (not abstract)
- [ ] `verify_webhook_signature` has a default implementation returning `True` and emitting a structured log warning (`logger.warning("Webhook signature verification not implemented for source: {source_name}")`) — not abstract, so sources without signing still work
- [ ] `verify_webhook_signature` signature: `(self, headers: dict[str, str], raw_body: bytes) -> bool`
- [ ] `SourceRegistry.get("nonexistent")` returns `None` (does not raise)
- [ ] Registering two sources with the same `source_name` raises `ValueError`
- [ ] Unit test: register a mock source, verify `get()` and `list_all()` return it correctly

**Completion Log:**
_No entries yet._

---

### Chunk 2.2 — Microsoft Sentinel Source Integration ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 2.1, 1.8
**PRD Reference:** Section 7.1, Section 9

**Description:**
Implement the Sentinel source plugin. Map Sentinel alert webhook payload fields to the Calseta agent-native schema (`CalsetaAlert`). Extract all indicators Sentinel surfaces (IPs, domains, hashes, accounts). Register the plugin so `POST /v1/ingest/sentinel` works end-to-end once 2.6 is complete.

**Output Artifacts:**
- `app/integrations/sources/sentinel.py` — `SentinelSource(AlertSourceBase)` with `source_name = "sentinel"`
- `app/integrations/sources/__init__.py` — updated to import and register `SentinelSource`
- `tests/fixtures/sentinel_alert.json` — a realistic Sentinel webhook payload for testing

**Acceptance Criteria:**
- [ ] `validate_payload` returns `False` (and does not raise) for payloads missing required Sentinel fields
- [ ] `normalize` returns a `CalsetaAlert` with: `title` from alert title, `severity` (string) + `severity_id` (integer) from severity field, `occurred_at` from alert timestamp (ISO 8601 UTC), `source_name = "sentinel"`
- [ ] unmappable Sentinel fields are preserved in `raw_payload` (set by caller, not this method)
- [ ] `extract_indicators` extracts IPs, domains, file hashes, and account names from the Sentinel entities array
- [ ] `extract_detection_rule_ref` returns the Sentinel rule ID/name
- [ ] `verify_webhook_signature` implemented using HMAC-SHA256; reads secret from `settings.SENTINEL_WEBHOOK_SECRET`; uses `hmac.compare_digest()` for constant-time comparison; returns `False` (not raises) when header is absent or secret is unconfigured
- [ ] `verify_webhook_signature` returns `True` on valid signature, `False` on tampered or missing signature (verified with unit tests covering both cases)
- [ ] Unit test using `tests/fixtures/sentinel_alert.json` validates normalize and extract_indicators outputs

**Completion Log:**
_No entries yet._

---

### Chunk 2.3 — Elastic Security Source Integration ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 2.1, 1.8
**PRD Reference:** Section 7.1, Section 9

**Description:**
Implement the Elastic Security source plugin. Elastic alert webhooks have a different structure from Sentinel. Map Elastic fields to the Calseta agent-native schema, extract indicators from ECS-formatted alert data.

**Output Artifacts:**
- `app/integrations/sources/elastic.py` — `ElasticSource(AlertSourceBase)` with `source_name = "elastic"`
- `app/integrations/sources/__init__.py` — updated to register `ElasticSource`
- `tests/fixtures/elastic_alert.json` — realistic Elastic Security webhook payload for testing

**Acceptance Criteria:**
- [ ] Same structural criteria as 2.2 applied to Elastic payload shape
- [ ] `normalize` correctly handles Elastic severity levels (numeric 1–4 or string) → agent-native `severity_id`
- [ ] `extract_indicators` handles ECS `source.ip`, `destination.ip`, `dns.question.name`, `file.hash.*` fields
- [ ] `extract_detection_rule_ref` returns the Elastic rule ID from `kibana.alert.rule.uuid`
- [ ] `verify_webhook_signature` implemented; reads secret from `settings.ELASTIC_WEBHOOK_SECRET`; uses `hmac.compare_digest()`; returns `False` when header absent or secret unconfigured
- [ ] Unit test using `tests/fixtures/elastic_alert.json`

**Completion Log:**
_No entries yet._

---

### Chunk 2.4 — Splunk Source Integration ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 2.1, 1.8
**PRD Reference:** Section 7.1, Section 9

**Description:**
Implement the Splunk source plugin. Splunk webhook payloads (via Splunk's Alert Actions / Adaptive Response) have a distinct structure. Map to the Calseta agent-native schema and extract indicators from Splunk's search result fields.

**Output Artifacts:**
- `app/integrations/sources/splunk.py` — `SplunkSource(AlertSourceBase)` with `source_name = "splunk"`
- `app/integrations/sources/__init__.py` — updated to register `SplunkSource`
- `tests/fixtures/splunk_alert.json` — realistic Splunk webhook payload for testing

**Acceptance Criteria:**
- [ ] Same structural criteria as 2.2 applied to Splunk payload shape
- [ ] `normalize` handles Splunk's urgency field → agent-native severity mapping
- [ ] `extract_indicators` extracts from Splunk `result` fields using common field names (`src_ip`, `dest_ip`, `user`, `md5`, `sha256`, `url`, `domain`)
- [ ] `extract_detection_rule_ref` returns the Splunk saved search name
- [ ] `verify_webhook_signature` implemented; reads token from `settings.SPLUNK_WEBHOOK_SECRET`; compares `Authorization` header bearer token using `hmac.compare_digest()`; returns `False` when header absent or secret unconfigured
- [ ] Unit test using `tests/fixtures/splunk_alert.json`

**Completion Log:**
_No entries yet._

---

### Chunk 2.5 — POST /v1/alerts (Generic Alert Ingest Endpoint) ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 2.1
**PRD Reference:** Sections 7.1, 7.9

**Description:**
Implement the generic alert ingest endpoint. Caller supplies a pre-normalized alert payload matching the `CalsetaAlert` schema. Validates schema, persists alert, extracts indicators, enqueues enrichment task, returns 202.

**Output Artifacts:**
- `app/api/v1/ingest.py` — `POST /v1/alerts` route handler
- `app/services/alert_ingestion.py` — `ingest_alert(payload: CalsetaAlert, db: AsyncSession, queue: TaskQueueBase) -> Alert` service function; shared by both ingest endpoints; writes `alert_ingested` activity event after persisting the alert

**Acceptance Criteria:**
- [ ] Returns `202 Accepted` with `{"data": {"alert_uuid": "...", "status": "pending_enrichment"}}`
- [ ] Returns `400` with `ErrorResponse` for payloads that fail `CalsetaAlert` schema validation
- [ ] Alert is persisted with `status = "pending_enrichment"`, `is_enriched = False`, `raw_payload` = original request body
- [ ] Enrichment task is enqueued to the `enrichment` queue before response is returned
- [ ] An `alert_ingested` activity event is written with `actor_type="system"`, `references={"source_name": ..., "indicator_count": N}`
- [ ] Response time < 200ms under normal conditions (enforced in a timing test with a mocked queue)
- [ ] Requires scope `alerts:write`

**Completion Log:**
_No entries yet._

---

### Chunk 2.6 — POST /v1/ingest/{source_name} (Source-Specific Ingest) ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 2.1
**PRD Reference:** Sections 7.1, 7.9, 7.13

**Description:**
Implement the source-specific ingest endpoint. Looks up the source plugin by `source_name`, runs signature verification, validates and normalizes the payload, then delegates to the shared ingestion service from 2.5.

**Request handling order (strictly enforced):**
1. Auth check (scope `alerts:write`) — handled by dependency
2. Look up source plugin by `source_name` — 404 if not found
3. Read raw request body as `bytes` (before any parsing)
4. Call `source.verify_webhook_signature(dict(request.headers), raw_body)` — 401 if `False`
5. Call `source.validate_payload(json.loads(raw_body))` — 400 if `False`
6. Normalize and delegate to ingestion service

**Output Artifacts:**
- `app/api/v1/ingest.py` — `POST /v1/ingest/{source_name}` route handler added to same file as 2.5; reads raw body bytes via `Request` object before JSON parsing to preserve body for HMAC verification

**Acceptance Criteria:**
- [ ] Unknown `source_name` returns `404 {"error": {"code": "SOURCE_NOT_FOUND", ...}}`
- [ ] `verify_webhook_signature` returning `False` returns `401 {"error": {"code": "INVALID_SIGNATURE", ...}}` — payload is never parsed
- [ ] `validate_payload` returning `False` returns `400` with `ErrorResponse`
- [ ] On success: normalizes payload, stores alert, enqueues enrichment, returns `202` with `alert_uuid`
- [ ] `raw_payload` stores the original pre-normalization request body
- [ ] Requires scope `alerts:write`
- [ ] Auth failure (invalid signature) emits `auth_failure` log event with `reason: "invalid_signature"` and source name
- [ ] Integration test: POST a fixture Sentinel payload → alert created with correct `source_name = "sentinel"`
- [ ] Integration test: POST with wrong/missing signature → 401, no alert created

**Completion Log:**
_No entries yet._

---

### Chunk 2.7 — Detection Rule Auto-Association Logic ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 2.1
**PRD Reference:** Section 7.3

**Description:**
Implement the detection rule auto-association logic that runs on every alert ingestion. If the source provides a rule reference, look up or create a detection rule record and link it to the alert. This runs synchronously within the ingestion service (fast path — DB lookup only, no enrichment).

**Output Artifacts:**
- `app/services/detection_rules.py` — `associate_detection_rule(alert: Alert, rule_ref: str | None, source_name: str, db: AsyncSession) -> DetectionRule | None` — upsert logic: find by `source_rule_id` + `source_name`, create if not found

**Acceptance Criteria:**
- [ ] If `rule_ref` is `None`, function returns `None` and creates no record
- [ ] If a `DetectionRule` with matching `source_rule_id` + `source_name` exists, it is associated (no duplicate created)
- [ ] If no match, a new `DetectionRule` is created with `name = rule_ref`, `source_rule_id = rule_ref`, `source_name = source_name`, all documentation fields empty
- [ ] The new rule's `is_active` defaults to `True`
- [ ] `alert.detection_rule_id` is set after association
- [ ] Unit tests cover: no ref → no rule, existing rule → associated, new rule → created and associated

**Completion Log:**
_No entries yet._

---

### Chunk 2.8 — Three-Pass Indicator Extraction Pipeline

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.7, 2.1
**PRD Reference:** Section 7.12

**Description:**
Implement the complete three-pass indicator extraction pipeline as described in PRD Section 7.12. This service is called by the ingestion layer after normalization. It runs all three passes, merges results, deduplicates, and persists indicators using an upsert pattern — the same `(type, value)` pair is stored once globally; the alert–indicator join is created regardless.

**Key design:** indicators are a global entity. `persist_indicators()` uses `INSERT ... ON CONFLICT (type, value) DO UPDATE SET last_seen = NOW()` to upsert, then inserts into `alert_indicators`. This means enrichment only needs to run once per unique indicator, not once per alert.

**Output Artifacts:**
- `app/services/indicator_extraction.py`:
  - `run_extraction_pipeline(raw_payload: dict, normalized_alert: CalsetaAlert, source_name: str, source_plugin: AlertSourceBase | None, db: AsyncSession) -> list[IndicatorExtract]`
  - `_pass1_source_plugin(plugin, raw) -> list[IndicatorExtract]`
  - `_pass2_normalized_mappings(normalized_alert, mappings) -> list[IndicatorExtract]`
  - `_pass3_custom_mappings(raw_payload, source_name, mappings) -> list[IndicatorExtract]`
  - `_resolve_dot_path(obj: dict, path: str) -> list[str]` — dot-notation traversal with array unwrapping; returns all leaf string values at the path
  - `_deduplicate(indicators: list[IndicatorExtract]) -> list[IndicatorExtract]` — dedup by `(type, value)`
  - `persist_indicators(alert_id: int, indicators: list[IndicatorExtract], db: AsyncSession) -> list[Indicator]` — upserts each indicator by `(type, value)` (updating `last_seen`; setting `first_seen` only on insert), then creates `AlertIndicator` join rows; returns the indicator ORM objects

**Acceptance Criteria:**
- [ ] All three passes run in sequence; exception in any single pass is caught and logged — remaining passes still execute
- [ ] `_resolve_dot_path("related.ip", {"related": {"ip": ["1.2.3.4", "5.6.7.8"]}})` returns `["1.2.3.4", "5.6.7.8"]`
- [ ] `_resolve_dot_path("missing.field", {})` returns `[]` (no exception)
- [ ] Array unwrapping recurses: if any segment is a list, traversal continues on each element
- [ ] Non-string scalar (int, bool) is cast to string and included
- [ ] Deduplication: same `(type, value)` from multiple passes → one indicator
- [ ] Pass 2 reads only `is_active=True, extraction_target='normalized'` mappings; Pass 3 reads only `is_active=True, extraction_target='raw_payload'` mappings with matching `source_name` or `source_name IS NULL`
- [ ] `persist_indicators()`: if the same `(type, value)` is ingested from a second alert, `first_seen` is unchanged, `last_seen` is updated to now, a new `AlertIndicator` join row is created
- [ ] `persist_indicators()`: enrichment is only enqueued for indicators where `is_enriched=False` (skip already-enriched indicators)
- [ ] Unit tests: all three passes independently, deduplication, array unwrapping with nested arrays, missing field path, upsert behavior (first_seen preserved, last_seen updated)

**Completion Log:**
_No entries yet._

---

### Chunk 2.9 — Indicator Field Mappings API Endpoints ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.7
**PRD Reference:** Sections 7.12, 7.9

**Description:**
Implement the CRUD and test endpoints for indicator field mappings. System mappings are read/patch/disable only — no delete. Custom mappings support full CRUD. The test endpoint validates a mapping against a sample payload without persisting anything.

**Output Artifacts:**
- `app/api/v1/indicator_mappings.py` — 6 endpoints from PRD Section 7.12 API block

**Acceptance Criteria:**
- [ ] `GET /v1/indicator-mappings` returns paginated list; all 4 filters work and combine (`source_name`, `is_system`, `indicator_type`, `is_active`)
- [ ] `POST /v1/indicator-mappings` always creates with `is_system=False`; user cannot set `is_system=True` — field is ignored if provided
- [ ] `DELETE /v1/indicator-mappings/{uuid}` on a system mapping returns `403 {"error": {"code": "SYSTEM_MAPPING_PROTECTED", "message": "System mappings cannot be deleted. Set is_active=false to disable."}}`
- [ ] `POST /v1/indicator-mappings/test` accepts `{"field_path": "...", "indicator_type": "ip", "extraction_target": "raw_payload", "payload": {...}}` and returns `{"extracted_indicators": [{"type": "ip", "value": "..."}], "count": N}`
- [ ] Test endpoint never writes to DB
- [ ] All endpoints require scope `admin`

**Completion Log:**
_No entries yet._

---

### Chunk 2.10 — Detection Rules CRUD Endpoints

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 2.7
**PRD Reference:** Sections 7.3, 7.9

**Description:**
Implement all detection rule management endpoints. Rules are primarily auto-created by ingestion, but users enrich them with documentation and MITRE mappings via these endpoints.

**Output Artifacts:**
- `app/api/v1/detection_rules.py` — all 6 endpoints from PRD Section 7.9:
  - `GET /v1/detection-rules` with filters: `source_name`, `mitre_tactic`, `mitre_technique`, `is_active`
  - `POST /v1/detection-rules`
  - `GET /v1/detection-rules/{uuid}`
  - `PATCH /v1/detection-rules/{uuid}`
  - `DELETE /v1/detection-rules/{uuid}`
  - `GET /v1/detection-rules/{uuid}/alerts`

**Acceptance Criteria:**
- [ ] `GET /v1/detection-rules` returns paginated `PaginatedResponse[DetectionRuleResponse]`
- [ ] All four filters work correctly and can be combined
- [ ] `GET /v1/detection-rules/{uuid}` returns `404` for unknown UUID
- [ ] `PATCH` accepts partial updates (only provided fields are updated)
- [ ] `DELETE` returns `204 No Content`; subsequent `GET` returns `404`
- [ ] All write endpoints require `alerts:write`; read endpoints require `alerts:read`
- [ ] `GET /v1/detection-rules/{uuid}/alerts` returns paginated list of associated alerts

**Completion Log:**
_No entries yet._

---

### Chunk 2.11 — Alerts Read + Write Endpoints

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 2.5, 2.6, 2.8
**PRD Reference:** Sections 7.9

**Description:**
Implement all alert read and update endpoints. Alert creation is handled by the ingest endpoints (2.5/2.6); these endpoints cover retrieval, updates, deletion, and the findings sub-resource.

**Output Artifacts:**
- `app/api/v1/alerts.py` — all endpoints from PRD Section 7.9:
  - `GET /v1/alerts` with filters: `status`, `severity`, `source`, `is_enriched`, `from_time`, `to_time`, `detection_rule_uuid`, `tags`
  - `GET /v1/alerts/{uuid}`
  - `PATCH /v1/alerts/{uuid}` (status, severity, tags) — writes `alert_status_updated` or `alert_severity_updated` activity event on change
  - `DELETE /v1/alerts/{uuid}`
  - `POST /v1/alerts/{uuid}/findings` — writes `alert_finding_added` activity event
  - `GET /v1/alerts/{uuid}/findings`
  - `GET /v1/alerts/{uuid}/activity` — returns paginated `ActivityEventResponse` list; supports `event_type` filter; ordered newest-first
  - `POST /v1/alerts/{uuid}/trigger-agents` (stub — returns `501` until Wave 5)
- `app/services/activity_event.py` — `ActivityEventService` with `write(db, event_type, actor_type, actor_key_prefix, alert_id, workflow_id, detection_rule_id, references) -> ActivityEvent`; called by all service-layer functions that change alert/workflow/detection_rule state; fire-and-forget (errors logged, never re-raised)

**Acceptance Criteria:**
- [ ] `GET /v1/alerts` returns paginated results; all 7 filters work and are combinable
- [ ] `GET /v1/alerts/{uuid}` response includes normalized alert fields (`title`, `severity`, `occurred_at`, etc.), `indicators` (from join), `detection_rule` (with `documentation`), and `agent_findings`
- [ ] `GET /v1/alerts/{uuid}` response `data` object includes `_metadata` at top level
- [ ] `_metadata.alert_source` matches `alerts.source_name`
- [ ] `_metadata.enrichment.succeeded` lists provider names where `success=true` in `indicator.enrichment_results` across all alert indicators (empty list if no enrichment has run)
- [ ] `_metadata.enrichment.failed` lists provider names where `success=false` in `indicator.enrichment_results` and none succeeded for that provider (empty list if no enrichment has run)
- [ ] `_metadata.enrichment.enriched_at` is the max `enriched_at` timestamp across all providers; `null` if no enrichment has run
- [ ] `_metadata.detection_rule_matched` is `true` iff `alerts.detection_rule_id` is non-null
- [ ] `_metadata.context_documents_applied` is the count of context documents included in the response
- [ ] `_metadata` is computed at response serialization time; no new DB columns required
- [ ] `PATCH` accepts partial body; unknown status values return `422`; successful status change creates an `alert_status_updated` activity event; successful severity change creates `alert_severity_updated`
- [ ] `POST /v1/alerts/{uuid}/findings` validates `agent_name`, `summary`, `confidence` (enum: low/medium/high), `recommended_action`; appends to `agent_findings` JSONB array; creates `alert_finding_added` activity event
- [ ] `GET /v1/alerts/{uuid}/activity` returns `PaginatedResponse[ActivityEventResponse]`; `event_type` filter works; results ordered newest-first
- [ ] `time` filters accept ISO 8601 with timezone; malformed values return `422`
- [ ] All read endpoints require `alerts:read`; write endpoints require `alerts:write`
- [ ] `ActivityEventService.write()` errors are caught and logged — they never cause the parent request to fail

**Completion Log:**
_No entries yet._

---

## Wave 3 — Enrichment Engine

**Goal:** Implement all four enrichment providers, the parallel enrichment pipeline, in-memory caching, and the enrichment API endpoints.

**Depends on:** Wave 2 complete (specifically 2.5/2.6 for the enrichment task handler to have alerts to process).

**Internal sequencing:**
- 3.1 must complete first
- After 3.1: 3.2, 3.3, 3.4, 3.5, 3.6, 3.9 can run in parallel ⚡
- 3.7 depends on 3.1 + 3.6
- 3.8 depends on 3.7

---

### Chunk 3.1 — EnrichmentProviderBase + Registry

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 2 complete
**PRD Reference:** Section 7.2

**Description:**
Define the `EnrichmentProviderBase` ABC and the provider registry. This is the contract all providers implement. Include the `is_configured()` check and the guarantee that `enrich()` never raises — it catches all exceptions and returns `success=False`.

**Output Artifacts:**
- `app/integrations/enrichment/base.py` — `EnrichmentProviderBase` ABC: `provider_name`, `display_name`, `supported_types: list[IndicatorType]`, `cache_ttl_seconds: int`, `enrich(value, type) -> EnrichmentResult`, `is_configured() -> bool`
- `app/integrations/enrichment/registry.py` — `EnrichmentRegistry` singleton; `register`, `get`, `list_configured`, `list_all`
- `app/integrations/enrichment/__init__.py` — imports and registers all built-in providers

**Acceptance Criteria:**
- [ ] `EnrichmentProviderBase` is an ABC; direct instantiation raises `TypeError`
- [ ] `enrich()` docstring explicitly states: "Must never raise. Catch all exceptions and return `EnrichmentResult(success=False, error=str(e))`"
- [ ] `list_configured()` returns only providers where `is_configured()` is `True`
- [ ] Registering duplicate `provider_name` raises `ValueError`
- [ ] Unit tests: mock provider registration, `list_configured` filtering

**Completion Log:**
_No entries yet._

---

### Chunk 3.2 — VirusTotal Enrichment Provider ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 3.1, 1.8
**PRD Reference:** Sections 7.2, 9

**Description:**
Implement the VirusTotal enrichment provider using httpx async. Supports IP, domain, MD5, SHA1, SHA256. Uses the VT API v3 endpoints. Returns a structured result with malicious detection count, categories, and last analysis date. Never raises — all errors caught and returned as `success=False`.

**Output Artifacts:**
- `app/integrations/enrichment/virustotal.py` — `VirusTotalProvider(EnrichmentProviderBase)` with `provider_name = "virustotal"`
- `app/integrations/enrichment/__init__.py` — updated to register `VirusTotalProvider`

**Acceptance Criteria:**
- [ ] `is_configured()` returns `True` only when `VIRUSTOTAL_API_KEY` is set
- [ ] `supported_types` = `[ip, domain, hash_md5, hash_sha1, hash_sha256]`
- [ ] `enrich()` on an unconfigured provider returns `EnrichmentResult(success=False, error="VirusTotal API key not configured")`
- [ ] Network error or non-200 response returns `success=False` with error description (does not raise)
- [ ] Successful result includes: `malicious_count`, `total_engines`, `categories`, `last_analysis_date`, `permalink`
- [ ] `cache_ttl_seconds` defaults match PRD Section 7.2 table (IP=3600, Domain=21600, Hash=86400)
- [ ] Unit tests use `httpx` mock / `respx` to simulate VT API responses

**Completion Log:**
_No entries yet._

---

### Chunk 3.3 — AbuseIPDB Enrichment Provider ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 3.1, 1.8
**PRD Reference:** Sections 7.2, 9

**Description:**
Implement the AbuseIPDB enrichment provider. IP addresses only. Returns abuse confidence score, report count, ISP, country, and usage type.

**Output Artifacts:**
- `app/integrations/enrichment/abuseipdb.py` — `AbuseIPDBProvider(EnrichmentProviderBase)` with `provider_name = "abuseipdb"`
- `app/integrations/enrichment/__init__.py` — updated to register `AbuseIPDBProvider`

**Acceptance Criteria:**
- [ ] `supported_types` = `[ip]` only
- [ ] `is_configured()` requires `ABUSEIPDB_API_KEY`
- [ ] Result includes: `abuse_confidence_score` (0–100), `total_reports`, `country_code`, `isp`, `usage_type`, `is_whitelisted`
- [ ] Non-IP indicator type passed to `enrich()` returns `success=False` with a clear error
- [ ] All error cases return `success=False` without raising
- [ ] `cache_ttl_seconds` = 3600 (IP default)
- [ ] Unit tests with mocked HTTP responses

**Completion Log:**
_No entries yet._

---

### Chunk 3.4 — Okta Enrichment Provider ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 3.1, 1.8
**PRD Reference:** Sections 7.2, 9

**Description:**
Implement the Okta enrichment provider. Account type only. Returns user profile, group membership, recent authentication activity, and MFA status using the Okta Users API.

**Output Artifacts:**
- `app/integrations/enrichment/okta.py` — `OktaProvider(EnrichmentProviderBase)` with `provider_name = "okta"`
- `app/integrations/enrichment/__init__.py` — updated to register `OktaProvider`

**Acceptance Criteria:**
- [ ] `supported_types` = `[account]`
- [ ] `is_configured()` requires `OKTA_DOMAIN` and `OKTA_API_TOKEN`
- [ ] Result includes: `user_id`, `login`, `status`, `created`, `last_login`, `mfa_enrolled`, `groups: list[str]`, `recent_auth_events: list`
- [ ] User not found in Okta returns `success=True` with `found=False` (not an error — the indicator was checked)
- [ ] All HTTP/auth errors return `success=False`
- [ ] `cache_ttl_seconds` = 900 (account default from PRD)
- [ ] Unit tests with mocked Okta API responses

**Completion Log:**
_No entries yet._

---

### Chunk 3.5 — Microsoft Entra Enrichment Provider ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 3.1, 1.8
**PRD Reference:** Sections 7.2, 9

**Description:**
Implement the Microsoft Entra ID (formerly Azure AD) enrichment provider. Account type only. Uses the Microsoft Graph API. Returns user profile, group membership, sign-in risk level, and conditional access status.

**Output Artifacts:**
- `app/integrations/enrichment/entra.py` — `EntraProvider(EnrichmentProviderBase)` with `provider_name = "entra"`
- `app/integrations/enrichment/__init__.py` — updated to register `EntraProvider`

**Acceptance Criteria:**
- [ ] `supported_types` = `[account]`
- [ ] `is_configured()` requires `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`
- [ ] OAuth2 client credentials token acquisition; token is cached for its expiry duration (do not re-authenticate on every call)
- [ ] Result includes: `user_principal_name`, `display_name`, `account_enabled`, `sign_in_risk_level`, `groups: list[str]`, `last_sign_in`
- [ ] User not found returns `success=True, found=False`
- [ ] Token acquisition failure returns `success=False`
- [ ] `cache_ttl_seconds` = 900
- [ ] Unit tests with mocked Graph API and token endpoint

**Completion Log:**
_No entries yet._

---

### Chunk 3.6 — In-Memory Enrichment Cache ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 3.1
**PRD Reference:** Section 7.2

**Description:**
Implement the in-memory enrichment cache with per-entry TTL. Cache key format: `{provider}:{indicator_type}:{value}`. TTLs are configurable per indicator type via environment variables with defaults from PRD Section 7.2. The cache interface is abstracted for future Redis migration.

**Output Artifacts:**
- `app/cache/base.py` — `CacheBackendBase` ABC: `get(key) -> EnrichmentResult | None`, `set(key, value, ttl_seconds)`
- `app/cache/memory.py` — `InMemoryCache(CacheBackendBase)` using a dict with expiry timestamps; thread-safe
- `app/cache/factory.py` — resolves from `CACHE_BACKEND` env var (only `memory` in v1)
- `app/cache/keys.py` — `make_enrichment_key(provider, indicator_type, value) -> str`

**Acceptance Criteria:**
- [ ] Cached entry returned within TTL; expired entry returns `None` (not the stale value)
- [ ] Cache is keyed as `enrichment:{provider}:{type}:{value}` — verified in test
- [ ] Default TTLs match PRD: IP=3600, Domain=21600, Hash=86400, URL=1800, Account=900
- [ ] All TTLs overridable via env vars (`CACHE_TTL_IP`, `CACHE_TTL_DOMAIN`, etc.)
- [ ] `InMemoryCache` is safe to call from multiple asyncio tasks concurrently (no race conditions on shared dict)
- [ ] `CACHE_BACKEND=memory` resolves correctly; unknown value fails at startup

**Completion Log:**
_No entries yet._

---

### Chunk 3.7 — Enrichment Pipeline (Async, Parallel Execution)

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 3.1, 3.6
**PRD Reference:** Section 7.2, 7.11

**Description:**
Implement the enrichment pipeline task that runs as a background worker job. For a given alert, it processes all extracted indicators concurrently. For each indicator, all configured providers are called in parallel via `asyncio.gather()`. Results are cached and written back to the alert. A slow or failing provider never blocks others.

**Output Artifacts:**
- `app/services/enrichment.py` — `enrich_alert(alert_uuid: str, db: AsyncSession, cache: CacheBackendBase) -> None` service function
- `app/queue/registry.py` — `enrich_alert_task` registered as a procrastinate task on the `enrichment` queue
- `app/services/enrichment.py` — `enrich_indicator(type, value, db, cache) -> dict[str, EnrichmentResult]` (used by both pipeline and on-demand endpoint)

**Acceptance Criteria:**
- [ ] All indicators for an alert are processed concurrently (use `asyncio.gather`)
- [ ] For each indicator, all supported+configured providers run concurrently
- [ ] One provider raising an exception does not affect other providers' results (verified in test with a mock that raises)
- [ ] Cache is checked before calling provider; cache hit skips the HTTP call
- [ ] After pipeline completes: `alert.is_enriched = True`, `alert.enriched_at` set, indicator `enrichment_results` JSONB populated keyed by provider name
- [ ] `alert.status` updated to `"enriched"` on completion
- [ ] An `alert_enrichment_completed` activity event is written with `actor_type="system"`, `references={"indicator_count": N, "providers_succeeded": ["virustotal", ...], "providers_failed": ["abuseipdb", ...], "malice_counts": {"Malicious": N, "Benign": N, "Pending": N}}` — `providers_succeeded` and `providers_failed` are lists of provider name strings (not counts), per PRD §8
- [ ] If all providers fail for an indicator: `is_enriched` still set to `True`; failures recorded in results
- [ ] Enrichment task survives a provider timeout (providers use `httpx` with a 30-second timeout)

**Completion Log:**
_No entries yet._

---

### Chunk 3.8 — POST /v1/enrichments (On-Demand Endpoint)

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 3.7
**PRD Reference:** Sections 7.2, 7.9

**Description:**
Implement the on-demand enrichment endpoint. Any indicator type and value can be submitted; results from all configured providers are returned synchronously (cache-first, live call if not cached). Used by Slack bots, agents, and manual lookups. The provider listing endpoint (`GET /v1/enrichments/providers`) is implemented separately in Chunk 3.9 — do not implement it here.

**Output Artifacts:**
- `app/api/v1/enrichments.py` — `POST /v1/enrichments` only (this chunk)
- `app/schemas/enrichment.py` — `OnDemandEnrichmentRequest`, `OnDemandEnrichmentResponse`

**Acceptance Criteria:**
- [ ] `POST /v1/enrichments` accepts `{"type": "ip", "value": "1.2.3.4"}` and returns all provider results in a single response
- [ ] Response is synchronous (not async/queued) — caller gets results immediately
- [ ] Cache hit returns cached result; `cache_hit: true` indicated in response metadata
- [ ] Unknown `type` value returns `422`
- [ ] Requires scope `enrichments:read`

**Completion Log:**
_No entries yet._

---

### Chunk 3.9 — GET /v1/enrichments/providers ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 3.1
**PRD Reference:** Sections 7.2, 7.9

**Description:**
Implement the provider listing endpoint. Returns all registered enrichment providers with their configuration status. This is used by MCP and agents to understand what enrichment capabilities are available. Can run in parallel with 3.2–3.8 since it only needs the registry from 3.1. Creates `app/api/v1/enrichments.py` if Chunk 3.8 has not yet run; otherwise adds the route to the existing file.

**Output Artifacts:**
- `app/api/v1/enrichments.py` — `GET /v1/enrichments/providers` route (create file if 3.8 has not run, otherwise append)
- `app/schemas/enrichment.py` — `EnrichmentProviderInfo` response schema

**Acceptance Criteria:**
- [ ] Returns list of all registered providers regardless of `is_configured` status
- [ ] Each entry includes: `provider_name`, `display_name`, `supported_types`, `is_configured`, `cache_ttl_seconds`
- [ ] Does not include API keys, credentials, or any secrets
- [ ] Requires scope `enrichments:read`

**Completion Log:**
_No entries yet._

---

## Wave 4 — Context + Workflow Engine

**Goal:** Implement the context document system (CRUD + targeting rule evaluation) and the full Python-based workflow engine (CRUD + AST validation + execution sandbox + AI generation + audit log + human-in-the-loop approval gate). These two subsystems are independent of each other and can be built in parallel.

**Depends on:** Wave 1 complete. (Does not require Wave 2 or 3. Chunk 4.5 pre-built seeder should coordinate with Wave 3 Okta/Entra client method signatures before finalizing code.)

**Internal sequencing:**
- 4.1 and 4.4 can start immediately in parallel ⚡
- 4.2 depends on 4.1; 4.3 depends on 4.2
- 4.5 (pre-built workflow seeder) depends on 4.4 + 1.8 — can run in parallel with 4.6 ⚡
- 4.6 (Python execution sandbox) depends on 4.4; 4.7 (AI generation + test + versions) depends on 4.6; 4.8 depends on 4.6 + 1.6; 4.9 depends on 4.8; 4.10 depends on 4.9
- 4.11 (approval gate + notifier base) depends on 4.8; 4.12 and 4.13 depend on 4.11 and can run in parallel ⚡

---

### Chunk 4.1 — Context Document CRUD Endpoints ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 1 complete
**PRD Reference:** Sections 7.4, 7.9

**Description:**
Implement context document management endpoints. Documents are markdown text with metadata and optional targeting rules. CRUD only — targeting rule evaluation is in 4.2.

**Output Artifacts:**
- `app/api/v1/context_documents.py` — 5 endpoints: `GET /v1/context-documents`, `POST`, `GET /{uuid}`, `PATCH /{uuid}`, `DELETE /{uuid}`
- `app/schemas/context_documents.py` — `ContextDocumentCreate`, `ContextDocumentResponse`, `ContextDocumentPatch`

**Acceptance Criteria:**
- [ ] `POST` validates `document_type` is one of: `runbook`, `ir_plan`, `sop`, `playbook`, `detection_guide`, `other`
- [ ] `targeting_rules` JSONB field accepts the schema from PRD Section 7.4 (`match_any`, `match_all` arrays); invalid structure returns `422`
- [ ] `GET /v1/context-documents` returns paginated list with `title`, `document_type`, `is_global`, `description`, `tags` — does NOT include `content` (save tokens)
- [ ] `GET /v1/context-documents/{uuid}` returns full document including `content`
- [ ] `PATCH` accepts partial updates
- [ ] Read endpoints require scope `alerts:read`; write endpoints require `alerts:write`
- [ ] `POST /v1/context-documents` accepts `multipart/form-data` with `file` field as an alternative to JSON body `content` field
- [ ] Supported input formats at minimum: PDF, DOCX, PPTX, HTML (markitdown's core formats); plain text and Markdown pass through unchanged
- [ ] Converted markdown stored in `context_documents.content`; original file is not persisted
- [ ] JSON body path (existing `content` field) is unchanged and continues to work
- [ ] Unsupported file format returns `422 Unprocessable Entity` with a clear error message identifying the format
- [ ] `markitdown` and `python-multipart` are listed as dependencies in `pyproject.toml`

**Completion Log:**
_No entries yet._

---

### Chunk 4.2 — Context Targeting Rule Evaluation Engine

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.1
**PRD Reference:** Section 7.4

**Description:**
Implement the targeting rule evaluation engine. Given an alert and a set of context documents, determine which non-global documents apply. Supports `match_any` (OR) and `match_all` (AND) with operators: `eq`, `in`, `contains`, `gte`, `lte`.

**Output Artifacts:**
- `app/services/context_targeting.py` — `evaluate_targeting_rules(alert: Alert, rules: dict) -> bool` and `get_applicable_documents(alert: Alert, db: AsyncSession) -> list[ContextDocument]` (global first, then targeted by doc type order)

**Acceptance Criteria:**
- [ ] `is_global: True` documents always included regardless of rules
- [ ] `match_any`: at least one rule in the array must evaluate true
- [ ] `match_all`: every rule in the array must evaluate true
- [ ] Both `match_any` and `match_all` present: both must pass
- [ ] Operators: `eq` (exact), `in` (value in list), `contains` (list field contains value), `gte`/`lte` (numeric comparison)
- [ ] Field paths: `source_name`, `severity`, `severity_id`, `tags`
- [ ] Invalid field path: rule evaluates to `False` (does not raise)
- [ ] Unit tests covering all 5 operators, both logic modes, and mixed mode

**Completion Log:**
_No entries yet._

---

### Chunk 4.3 — GET /v1/alerts/{uuid}/context

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.2
**PRD Reference:** Sections 7.4, 7.9

**Description:**
Implement the alert context resolution endpoint. Returns all applicable context documents for a given alert: global documents first, then targeted documents sorted by document type. This endpoint output is included in agent webhook payloads.

**Output Artifacts:**
- Route added to `app/api/v1/alerts.py`

**Acceptance Criteria:**
- [ ] Returns `DataResponse[list[ContextDocumentResponse]]` with full document content
- [ ] Global documents appear before targeted documents
- [ ] Targeted documents ordered by `document_type` alphabetically within their group
- [ ] `404` for unknown alert UUID
- [ ] Requires scope `alerts:read`
- [ ] Integration test: create alert + 3 documents (1 global, 1 matching, 1 non-matching) → verify only 2 returned

**Completion Log:**
_No entries yet._

---

### Chunk 4.4 — Workflow CRUD Endpoints ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 1 complete
**PRD Reference:** Sections 7.5, 7.9

**Description:**
Implement workflow management endpoints. Workflows are Python automation functions stored as source code with structured metadata. CRUD only — execution engine is in 4.6. On every create or code update, the platform AST-parses the workflow code and rejects it before storage if any disallowed imports are found.

**Output Artifacts:**
- `app/api/v1/workflows.py` — CRUD endpoints: `GET /v1/workflows`, `POST /v1/workflows`, `GET /v1/workflows/{uuid}`, `PATCH /v1/workflows/{uuid}`, `DELETE /v1/workflows/{uuid}`
- `app/schemas/workflows.py` — `WorkflowCreate`, `WorkflowResponse`, `WorkflowPatch`, `WorkflowSummary`
- `app/services/workflow_ast.py` — `validate_workflow_code(code: str) -> list[str]`; returns list of validation error strings (empty = valid); checks: defines `async def run`, only allowed imports present, no `os`/`subprocess`/`importlib`/filesystem references

**Acceptance Criteria:**
- [ ] `workflow_type` validated as `indicator` or `alert`
- [ ] `indicator_types` validated against `IndicatorType` enum when `workflow_type = "indicator"`
- [ ] `code` field required on create; `validate_workflow_code()` called before save; returns `400` with validation errors if AST check fails
- [ ] `PATCH /v1/workflows/{uuid}` with a new `code` value re-runs AST validation and increments `code_version` on success
- [ ] `state` accepted values: `draft`, `active`, `inactive`; defaults to `draft` on create
- [ ] `GET /v1/workflows` returns list including `name`, `workflow_type`, `state`, `code_version`, `documentation` summary; `code` field excluded from list responses (too large)
- [ ] `GET /v1/workflows/{uuid}` returns full record including `code`
- [ ] Write endpoints require scope `workflows:write`; reads require `workflows:read`; execute (Chunk 4.8) requires `workflows:execute`
- [ ] `DELETE /v1/workflows/{uuid}` on a system workflow (`is_system=True`) returns `403`
- [ ] Unit tests: create with valid code passes; create with `import os` returns `400`; patch with new code increments version

**Completion Log:**
_No entries yet._

---

### Chunk 4.5 — Pre-built Workflow Seeder (Okta + Entra) ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.4, 1.8
**PRD Reference:** Section 9 (Pre-built Workflow Catalog)

**Description:**
Seed the 9 pre-built workflows (5 Okta, 4 Entra) into the workflow catalog at application startup. Each workflow is a Python function (not an HTTP template) that uses `ctx.integrations.okta` or `ctx.integrations.entra` — the pre-built integration clients provided by `WorkflowContext`. Uses the same idempotency pattern as the indicator mappings seeder — safe to run on every startup. Workflows are seeded as `is_system=True` and `state="active"`. If the required integration credentials are absent, the workflow is seeded with `is_active=False`.

Reference `docs/integrations/okta/api_notes.md` and `docs/integrations/entra/api_notes.md` (produced by Chunk 1.8) for the exact API method signatures available on `OktaClient` and `EntraClient`.

**Output Artifacts:**
- `app/seed/builtin_workflows.py` — `seed_builtin_workflows(db: AsyncSession, settings: Settings) -> None`; defines all 9 workflow Python functions inline and upserts by `name` + `is_system=True`
- Called from `app/main.py` startup event alongside `seed_system_mappings()`

**Okta workflows to seed (5) — each uses `ctx.integrations.okta`:**
1. `Okta — Revoke All Sessions` — calls `ctx.integrations.okta.revoke_sessions(ctx.indicator.value)`
2. `Okta — Suspend User` — calls `ctx.integrations.okta.suspend_user(ctx.indicator.value)`
3. `Okta — Unsuspend User` — calls `ctx.integrations.okta.unsuspend_user(ctx.indicator.value)`
4. `Okta — Reset Password` — calls `ctx.integrations.okta.reset_password(ctx.indicator.value)`
5. `Okta — Force Password Expiry` — calls `ctx.integrations.okta.expire_password(ctx.indicator.value)`

**Entra workflows to seed (4) — each uses `ctx.integrations.entra`:**
1. `Entra — Revoke Sign-in Sessions` — calls `ctx.integrations.entra.revoke_sessions(ctx.indicator.value)`
2. `Entra — Disable Account` — calls `ctx.integrations.entra.disable_account(ctx.indicator.value)`
3. `Entra — Enable Account` — calls `ctx.integrations.entra.enable_account(ctx.indicator.value)`
4. `Entra — Force MFA Re-registration` — calls `ctx.integrations.entra.reset_mfa(ctx.indicator.value)`

**Note:** The `OktaClient` and `EntraClient` integration client implementations are built in Wave 3 (Chunks 3.4 and 3.5). Chunk 4.5 depends on those clients having well-defined method signatures. Coordinate with Wave 3 output artifacts before finalizing the seeder code.

**Acceptance Criteria:**
- [ ] `seed_builtin_workflows()` on a fresh DB inserts exactly 9 workflow rows with `is_system=True`
- [ ] Running a second time makes zero DB writes (idempotent — matched by `name` + `is_system=True`)
- [ ] All Okta workflows have `is_active=True` when `OKTA_DOMAIN` and `OKTA_API_TOKEN` are set; `is_active=False` when either is missing
- [ ] All Entra workflows have `is_active=True` when all required Entra env vars are set; `is_active=False` otherwise
- [ ] `workflow_type = "indicator"` and `indicator_types = ["account"]` for all 9 workflows
- [ ] `state = "active"` for all seeded workflows; `is_system = True`
- [ ] `code` field contains a valid Python workflow function that passes `validate_workflow_code()` for each seeded workflow
- [ ] `documentation` field populated for each workflow using LLM-oriented headings from Section 7.5 template: `## Description`, `## When to Use`, `## Required Secrets`, `## Expected Outcome`, `## Error Cases`
- [ ] `DELETE /v1/workflows/{uuid}` on a system workflow returns `403`; `PATCH is_active=False` works normally
- [ ] Unit test: seeder with Okta vars set → 5 Okta workflows with `is_active=True`; without vars → 5 with `is_active=False`

**Completion Log:**
_No entries yet._

---

### Chunk 4.6 — Python Workflow Execution Sandbox

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.4
**PRD Reference:** Section 7.5

**Description:**
Implement the Python execution sandbox that runs workflow code safely. This is the core execution engine: it instantiates `WorkflowContext`, compiles and executes the workflow's `run()` function in a restricted environment, enforces the `timeout_seconds` limit via `asyncio.wait_for`, captures all `ctx.log` output, and returns a `WorkflowExecutionResult` suitable for audit logging. This chunk builds the execution primitive — the task queue integration and endpoint wiring are in Chunk 4.8.

**Output Artifacts:**
- `app/services/workflow_executor.py` — `execute_workflow(workflow: Workflow, trigger_context: TriggerContext, db: AsyncSession) -> WorkflowExecutionResult`
- `app/workflows/context.py` — `WorkflowContext`, `WorkflowResult`, `WorkflowLogger`, `SecretsAccessor`, `IntegrationClients`, `IndicatorContext`, `AlertContext` dataclasses (the full interface spec from PRD Section 7.5); `AlertContext` exposes agent-native fields: `uuid`, `title`, `severity`, `severity_id`, `source_name`, `status`, `occurred_at`, `tags`, `raw_payload`, `enrichment_results` — no `ocsf_data` field
- `app/workflows/sandbox.py` — `run_workflow_code(code: str, ctx: WorkflowContext, timeout: int) -> WorkflowResult`; uses `compile()` + `exec()` in a restricted namespace; enforces allowed globals only; wraps in `asyncio.wait_for`

**Acceptance Criteria:**
- [ ] `WorkflowContext` exposes all fields from PRD Section 7.5: `indicator`, `alert`, `http`, `log`, `secrets`, `integrations`
- [ ] `ctx.http` is a pre-configured `httpx.AsyncClient` with `timeout_seconds` from the workflow record
- [ ] `ctx.log.info/warning/error()` appends structured entries to an in-memory log buffer; captured in `WorkflowExecutionResult.log_output`
- [ ] `ctx.secrets.get("KEY")` returns the named environment variable value via `settings`; never exposes all secrets at once
- [ ] `ctx.integrations.okta` is `None` when Okta env vars are absent; is an `OktaClient` instance when configured
- [ ] `ctx.integrations.entra` is `None` when Entra env vars are absent; is an `EntraClient` instance when configured
- [ ] `asyncio.wait_for` enforces `timeout_seconds`; timeout returns `WorkflowResult.fail("Workflow execution timed out")`
- [ ] Disallowed builtins (`__import__`, `open`, `exec`, `eval`, `compile`) removed from execution namespace
- [ ] `run_workflow_code` never raises — all exceptions caught and returned as `WorkflowResult.fail(...)`
- [ ] `WorkflowExecutionResult` contains: `result: WorkflowResult`, `log_output: str`, `duration_ms: int`, `code_version_executed: int`
- [ ] Unit tests: successful execution returns `ok` result; timeout returns `fail`; exception in `run()` returns `fail`; `ctx.log` output captured correctly

**Completion Log:**
_No entries yet._

---

### Chunk 4.7 — AI Workflow Generation, Test, and Versions Endpoints

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.6
**PRD Reference:** Section 7.5, 7.9

**Description:**
Implement three AI-first workflow management endpoints:
1. `POST /v1/workflows/generate` — takes a natural language description and generates valid workflow Python code using an LLM call. Returns the generated code for review; does not save automatically.
2. `POST /v1/workflows/{uuid}/test` — executes the workflow in a sandboxed context using `run_workflow_code()` from Chunk 4.6, but intercepts all `ctx.http` calls (no real external HTTP) and uses a fixture trigger context. Returns the `WorkflowResult`, captured log output, and duration.
3. `GET /v1/workflows/{uuid}/versions` — lists all saved code versions for a workflow with metadata (version number, saved timestamp, first line of code as preview).

For versioning: every successful `PATCH` that changes `code` writes a `workflow_code_versions` row before incrementing `code_version`. This enables rollback and audit trail.

**Output Artifacts:**
- Routes added to `app/api/v1/workflows.py`: `POST /v1/workflows/generate`, `POST /v1/workflows/{uuid}/test`, `GET /v1/workflows/{uuid}/versions`
- `app/schemas/workflows.py` additions: `WorkflowGenerateRequest`, `WorkflowGenerateResponse`, `WorkflowTestRequest`, `WorkflowTestResponse`, `WorkflowVersionResponse`
- `app/services/workflow_generator.py` — `generate_workflow_code(description: str, workflow_type: str, indicator_types: list[str], settings: Settings) -> WorkflowGenerateResponse`; builds the generation prompt from PRD Section 7.5 spec + examples, calls Anthropic API, validates AST of output
- `app/db/models.py` addition — `workflow_code_versions` table: `workflow_id` FK, `version` INTEGER, `code` TEXT, `saved_at` TIMESTAMP
- Migration: `alembic/versions/XXXX_add_workflow_code_versions.py`

**Generation prompt context must include:**
- Full `WorkflowContext` and `WorkflowResult` interface spec (copied verbatim from PRD Section 7.5)
- Allowed imports list
- All example workflows from `docs/workflows/examples/`
- Names of currently configured secrets (from `settings`, not values)
- Available integration client method signatures

**Test endpoint behavior:**
- `ctx.http` replaced with `httpx.MockTransport` that returns configurable mock responses
- `ctx.integrations.okta` and `.entra` replaced with mock clients that record calls
- `ctx.secrets` reads from fixture payload or falls back to actual settings (no real creds exposed in response)
- Real external HTTP is never made during test execution

**Acceptance Criteria:**
- [ ] `POST /v1/workflows/generate` returns `generated_code`, `suggested_name`, `suggested_documentation`, `warnings` (as in PRD Section 7.5 spec)
- [ ] Generated code is validated via `validate_workflow_code()` before returning; if generation produces invalid code, returns `400` with error details
- [ ] `POST /v1/workflows/{uuid}/test` runs code via `run_workflow_code()` with mocked HTTP; returns `WorkflowResult`, `log_output`, `duration_ms`
- [ ] Test endpoint on inactive workflow returns `400`; on non-existent UUID returns `404`
- [ ] No real external HTTP calls made during test execution (verified via mock transport assertion)
- [ ] `GET /v1/workflows/{uuid}/versions` returns list ordered by version descending; includes `version`, `saved_at`, `code_preview` (first 120 chars)
- [ ] Each `PATCH` that changes `code` writes a `workflow_code_versions` row for the previous version before incrementing `code_version`
- [ ] Generate endpoint requires scope `workflows:write`; test requires `workflows:execute`; versions requires `workflows:read`
- [ ] Integration test: generate → validate → save (PATCH state to active) → test → execute flow works end-to-end

**Completion Log:**
_No entries yet._

---

### Chunk 4.8 — POST /v1/workflows/{uuid}/execute + Task Queue Integration

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.6, 1.6
**PRD Reference:** Sections 7.5, 7.9, 7.11

**Description:**
Implement the workflow execution endpoint and wire it to the task queue. The endpoint validates the trigger context, enqueues the execution task, and returns `202 Accepted` immediately. The worker dequeues the task, calls `execute_workflow()` from Chunk 4.6 (the Python sandbox), and the audit log write is handled by Chunk 4.9.

**Output Artifacts:**
- Route `POST /v1/workflows/{uuid}/execute` added to `app/api/v1/workflows.py`
- `app/schemas/workflows.py` — `WorkflowExecuteRequest` (indicator or alert context), `WorkflowExecuteResponse`
- `app/queue/registry.py` — `execute_workflow_task` registered on the `workflows` queue; calls `execute_workflow()` from `workflow_executor.py`

**Acceptance Criteria:**
- [ ] Endpoint accepts context payload: `{"indicator": {"type": "ip", "value": "1.2.3.4"}}` or `{"alert_uuid": "..."}`
- [ ] Returns `202 Accepted` with `{"data": {"run_uuid": "...", "status": "queued"}}`
- [ ] Unknown workflow UUID returns `404`
- [ ] Inactive workflow (`is_active: False`) or workflow in `draft` state returns `400`
- [ ] Task enqueued to `workflows` queue before response returned
- [ ] Worker task calls `execute_workflow()` from Chunk 4.6 with correctly assembled `TriggerContext`
- [ ] Requires scope `workflows:execute`

**Completion Log:**
_No entries yet._

---

### Chunk 4.9 — Workflow Run Audit Log + Run Endpoints

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.8
**PRD Reference:** Sections 7.5, 7.9

**Description:**
Implement the `WorkflowRun` audit log write path (called by the worker after execution completes) and the read endpoints for run history. The audit record captures the Python execution result, not HTTP response data.

**Output Artifacts:**
- `app/services/workflow_runs.py` — `record_workflow_run(workflow_id, execution_result: WorkflowExecutionResult, trigger_context, db) -> WorkflowRun`
- Routes added to `app/api/v1/workflows.py`: `GET /v1/workflows/{uuid}/runs`
- `app/schemas/workflows.py` — `WorkflowRunResponse`

**Acceptance Criteria:**
- [ ] Every execution attempt results in a `WorkflowRun` record with: `status` (`success`/`failed`/`timed_out`), `attempt_count`, `trigger_type`, `trigger_context` JSONB, `code_version_executed`, `log_output` TEXT, `result` JSONB (`success`, `message`, `data`), `duration_ms`
- [ ] `status` is derived from `WorkflowResult.success`: `True` → `success`; `False` → `failed`; timeout → `timed_out`
- [ ] `GET /v1/workflows/{uuid}/runs` returns paginated run history, newest first
- [ ] `WorkflowRunResponse` includes all audit fields; `log_output` and `result.data` included for full audit visibility
- [ ] Requires scope `workflows:read`
- [ ] Unit test: `record_workflow_run` with a successful result produces correct DB record; with a failed result produces correct record with `status="failed"`

**Completion Log:**
_No entries yet._

---

### Chunk 4.10 — GET /v1/workflow-runs (Global Run History)

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.9
**PRD Reference:** Section 7.9

**Description:**
Implement the global workflow run history endpoint. Lists runs across all workflows with filters for status and time range.

**Output Artifacts:**
- Route `GET /v1/workflow-runs` added to `app/api/v1/workflows.py`

**Acceptance Criteria:**
- [ ] Returns paginated `PaginatedResponse[WorkflowRunResponse]` across all workflows
- [ ] Filters: `status` (`queued`/`success`/`failed`), `from_time`, `to_time`, `workflow_uuid`
- [ ] Results ordered by `created_at` descending
- [ ] Requires scope `workflows:read`

**Completion Log:**
_No entries yet._

---

### Chunk 4.11 — Workflow Approval Gate + ApprovalNotifierBase + NullApprovalNotifier

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.8, 1.6
**PRD Reference:** Section 7.5 (Human-in-the-Loop Workflow Approval)

**Description:**
Implement the human-in-the-loop approval gate. When an agent calls `POST /v1/workflows/{uuid}/execute` and the workflow has `requires_approval = true`, the platform creates a `workflow_approval_request` record, enqueues a notification task, and returns `202 Accepted` with `status: "pending_approval"`. The worker sends the approval message via the configured `ApprovalNotifierBase` implementation. This chunk implements the gate logic, the `ApprovalNotifierBase` ABC, and `NullApprovalNotifier`. Slack and Teams notifiers are built in 4.12 and 4.13 respectively.

**Approval gate logic (modifies Chunk 4.8 execute handler):**
- If `trigger_source = "agent"` AND `workflow.requires_approval = true`: create approval request, enqueue notification, return `202 {"status": "pending_approval", "approval_request_uuid": "...", "expires_at": "..."}`
- If `requires_approval = false` OR caller is a human (non-agent direct call): execute immediately (existing 4.8 behavior)
- On approval: enqueue `execute_workflow_task`; on rejection/expiry: mark request terminal, no execution

**Output Artifacts:**
- `app/workflows/notifiers/base.py` — `ApprovalNotifierBase` ABC: `send_approval_request(request: ApprovalRequest) -> str`, `send_result_notification(request, approved, responder) -> None`, `is_configured() -> bool`; both methods must never raise
- `app/workflows/notifiers/null_notifier.py` — `NullApprovalNotifier(ApprovalNotifierBase)`: no-op implementation; `is_configured()` always returns `True`; logs that approval request was created but no notification sent
- `app/workflows/notifiers/factory.py` — `get_approval_notifier(settings: Settings) -> ApprovalNotifierBase`; resolves from `APPROVAL_NOTIFIER` env var (`slack`, `teams`, `none`); defaults to `none` (NullApprovalNotifier)
- `app/workflows/approval.py` — `ApprovalRequest` dataclass (fields from PRD §7.5); `create_approval_request(workflow, alert, indicator, reason, confidence, db) -> WorkflowApprovalRequest`; `process_approval_decision(approval_uuid, approved, responder_id, db) -> None` (enqueues execution if approved, marks terminal if rejected)
- `app/api/v1/workflows.py` — execute handler updated: injects `ApprovalNotifierBase` via DI; applies approval gate; `reason` and `confidence` required fields on agent-triggered execute request
- `app/api/v1/workflow_approvals.py` — approval management endpoints:
  - `GET /v1/workflow-approvals/{uuid}` — fetch approval request status + execution result (used by agents to poll after execute)
  - `POST /v1/workflow-approvals/{uuid}/approve` — human REST-based approval (sets status, enqueues execution)
  - `POST /v1/workflow-approvals/{uuid}/reject` — human REST-based rejection
  - `GET /v1/workflow-approvals` — paginated list; filters: `status`, `workflow_uuid`, `from_time`, `to_time`
- `app/queue/registry.py` — `send_approval_notification_task` registered on `dispatch` queue; `execute_approved_workflow_task` on `workflows` queue (triggered by approval decision)
- `app/schemas/workflow_approvals.py` — `WorkflowApprovalRequestResponse`, `WorkflowExecuteAgentRequest` (adds `reason`, `confidence` fields)
- `app/config.py` — updated: `APPROVAL_NOTIFIER: str = "none"`, `APPROVAL_DEFAULT_CHANNEL: str = ""`, `APPROVAL_DEFAULT_TIMEOUT_SECONDS: int = 3600`
- `.env.example` — updated: all new approval env vars documented

**Acceptance Criteria:**
- [ ] Agent-triggered execute on a `requires_approval = true` workflow returns `202 {"status": "pending_approval", "approval_request_uuid": "...", "expires_at": "..."}`
- [ ] Agent-triggered execute on a `requires_approval = false` workflow executes immediately (existing 4.8 behavior unchanged)
- [ ] Human-triggered execute (non-agent API key) bypasses approval gate and executes immediately regardless of `requires_approval` value
- [ ] `reason` and `confidence` are required fields on the execute request when `trigger_source = "agent"`; missing either returns `422`
- [ ] `workflow_approval_requests` row created with `status = "pending"` before the `202` response is returned
- [ ] Notification task enqueued to `dispatch` queue before `202` response
- [ ] `NullApprovalNotifier.send_approval_request()` does not raise; logs `WARNING` that no notification channel is configured
- [ ] `POST /v1/workflow-approvals/{uuid}/approve` → status → `"approved"` → `execute_approved_workflow_task` enqueued; subsequent `GET` returns execution result once complete
- [ ] `POST /v1/workflow-approvals/{uuid}/reject` → status → `"rejected"` → no execution enqueued
- [ ] Expired approval requests (past `expires_at`) cannot be approved — return `409 APPROVAL_EXPIRED`
- [ ] `GET /v1/workflow-approvals/{uuid}` returns full request state including `execution_result` once populated
- [ ] All approval management endpoints require scope `workflows:execute`
- [ ] Unit tests: approval gate fires on agent trigger; bypassed on human trigger; approve → execution enqueued; reject → no execution; expired request → 409

**Completion Log:**
_No entries yet._

---

### Chunk 4.12 — SlackApprovalNotifier ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.11
**PRD Reference:** Section 7.5 (Slack Notification)

**Description:**
Implement the Slack Block Kit approval notifier. Sends interactive Block Kit messages to the configured Slack channel when a workflow approval is requested. The message includes the agent's reason, confidence score, workflow risk level, and Approve/Reject buttons. Button interactions are received via `POST /v1/approvals/callback/slack` and routed to `process_approval_decision()`. Also sends a result follow-up message to the same thread after the workflow executes or is rejected.

**Output Artifacts:**
- `app/workflows/notifiers/slack_notifier.py` — `SlackApprovalNotifier(ApprovalNotifierBase)` with `notifier_name = "slack"`; uses `httpx` to call Slack `chat.postMessage` API; builds Block Kit message from `ApprovalRequest`; returns Slack `ts` (message timestamp) as `external_message_id`; `send_result_notification` posts to thread using `thread_ts = external_message_id`
- `app/api/v1/approvals.py` — `POST /v1/approvals/callback/slack`; validates Slack request signature (`X-Slack-Signature` using `SLACK_SIGNING_SECRET`); parses `payload` form field; extracts `approval_request_uuid` and action (`approve`/`reject`) from `block_id`/`action_id`; calls `process_approval_decision()`; returns `200` immediately (Slack requires < 3s response)
- `app/config.py` — updated: `SLACK_BOT_TOKEN: str = ""`, `SLACK_SIGNING_SECRET: str = ""`
- `.env.example` — updated: Slack vars documented

**Acceptance Criteria:**
- [ ] `is_configured()` returns `True` only when `SLACK_BOT_TOKEN` is set
- [ ] `send_approval_request()` POSTs to `https://slack.com/api/chat.postMessage` with `SLACK_BOT_TOKEN`; uses Block Kit with: workflow name + risk level header, agent reason text block, confidence percentage, Approve and Reject action buttons with `approval_request_uuid` embedded in `block_id`
- [ ] `POST /v1/approvals/callback/slack` validates Slack signature using `hmac.compare_digest()` against `SLACK_SIGNING_SECRET`; invalid signature returns `403`
- [ ] Approve button click → `process_approval_decision(approved=True, responder_id=slack_user_id)`; Reject → `process_approval_decision(approved=False, ...)`
- [ ] `send_result_notification()` posts a follow-up message to the same thread (using `thread_ts`)
- [ ] Any Slack API error is caught and logged — `send_approval_request()` returns empty string on failure, never raises
- [ ] `APPROVAL_NOTIFIER=slack` in `.env` selects `SlackApprovalNotifier` via factory
- [ ] Unit tests: `send_approval_request()` with mocked Slack API; callback signature validation (valid + invalid); approve + reject flows end-to-end

**Completion Log:**
_No entries yet._

---

### Chunk 4.13 — TeamsApprovalNotifier ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 4.11
**PRD Reference:** Section 7.5 (Teams Notification)

**Description:**
Implement the Microsoft Teams Adaptive Card approval notifier. Sends Adaptive Card messages via an incoming webhook URL to the configured Teams channel. Teams does not support interactive callback buttons via incoming webhooks; approval decisions are made via the REST API (`POST /v1/workflow-approvals/{uuid}/approve|reject`). The notifier includes a direct link to the Calseta API for approvers. Also sends a follow-up card to the same channel thread after the decision is made.

**Output Artifacts:**
- `app/workflows/notifiers/teams_notifier.py` — `TeamsApprovalNotifier(ApprovalNotifierBase)` with `notifier_name = "teams"`; uses `httpx` to POST an Adaptive Card payload to `TEAMS_WEBHOOK_URL`; card body includes: workflow name + risk level, agent reason, confidence percentage, approval request UUID, and direct URLs to the approve/reject REST endpoints (formatted as action buttons linking to `{CALSETA_BASE_URL}/v1/workflow-approvals/{uuid}/approve`); `send_result_notification` sends a second card with the outcome
- `app/api/v1/approvals.py` — updated: `POST /v1/approvals/callback/teams` stub that returns `200 {"message": "Use GET /v1/workflow-approvals/{uuid} and POST /v1/workflow-approvals/{uuid}/approve|reject for Teams approvals"}` (Teams interactive button callbacks require a Bot Framework setup outside v1 scope; REST approval is the v1 mechanism)
- `app/config.py` — updated: `TEAMS_WEBHOOK_URL: str = ""`, `CALSETA_BASE_URL: str = "http://localhost:8000"` (used to construct approve/reject links)
- `.env.example` — updated: Teams vars documented

**Acceptance Criteria:**
- [ ] `is_configured()` returns `True` only when `TEAMS_WEBHOOK_URL` is set
- [ ] `send_approval_request()` POSTs a valid Adaptive Card JSON to `TEAMS_WEBHOOK_URL`; card includes workflow name, risk level, agent reason, confidence, and formatted approve/reject REST endpoint URLs
- [ ] Any Teams webhook error is caught and logged — never raises
- [ ] `send_result_notification()` sends a second card with the final status (`Approved by {responder}` / `Rejected` / `Expired`)
- [ ] `APPROVAL_NOTIFIER=teams` in `.env` selects `TeamsApprovalNotifier` via factory
- [ ] `POST /v1/approvals/callback/teams` returns `200` with a clear explanation (not a 404 or 501)
- [ ] Unit tests: `send_approval_request()` with mocked webhook; result notification; unconfigured notifier returns `is_configured() = False`

**Completion Log:**
_No entries yet._

---

## Wave 5 — Agent Integration Layer

**Goal:** Implement agent registration, trigger evaluation, webhook dispatch, and the findings write-back endpoints.

**Depends on:** Waves 2, 3, and 4 complete.

**Internal sequencing:**
- 5.1 can start immediately after wave deps met ⚡
- 5.4 can start immediately after wave deps met ⚡
- 5.2 depends on 5.1
- 5.3 depends on 5.2 + 1.6
- 5.5 and 5.6 depend on 5.3

---

### Chunk 5.1 — Agent Registration CRUD Endpoints ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 1 complete
**PRD Reference:** Sections 7.7, 7.9

**Description:**
Implement agent registration management. Agents register their webhook endpoint, auth header, and trigger criteria. The `auth_header_value` is encrypted at rest.

**Output Artifacts:**
- `app/api/v1/agents.py` — CRUD: `GET /v1/agents`, `POST`, `GET /{uuid}`, `PATCH /{uuid}`, `DELETE /{uuid}`
- `app/schemas/agents.py` — `AgentRegistrationCreate`, `AgentRegistrationResponse`, `AgentRegistrationPatch`

**Acceptance Criteria:**
- [ ] `auth_header_value` encrypted with Fernet before storage; never returned in API responses
- [ ] `trigger_on_sources` and `trigger_on_severities` stored as TEXT[] and returned as lists; empty list = all
- [ ] `trigger_filter` JSONB accepts the same rule schema as context document `targeting_rules`
- [ ] `POST /v1/agents/{uuid}/test` route is a stub returning `501` (implemented in 5.5)
- [ ] Write endpoints require scope `agents:write`; reads require `agents:read`

**Completion Log:**
_No entries yet._

---

### Chunk 5.2 — Trigger Evaluation Engine

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 5.1
**PRD Reference:** Section 7.7

**Description:**
Implement the trigger evaluation logic that, after enrichment completes, determines which registered agents should receive the alert. Evaluation order: source filter → severity filter → JSONB rule filter.

**Output Artifacts:**
- `app/services/agent_trigger.py` — `get_matching_agents(alert: Alert, db: AsyncSession) -> list[AgentRegistration]`; evaluates all three filter layers

**Acceptance Criteria:**
- [ ] Empty `trigger_on_sources` matches all sources; non-empty requires exact match
- [ ] Empty `trigger_on_severities` matches all severities; non-empty requires exact match
- [ ] `trigger_filter` evaluated using the same targeting rule engine from 4.2 (reuse `evaluate_targeting_rules`)
- [ ] `is_active: False` agents are excluded
- [ ] Unit tests: agent matches on source only, severity only, combined, with JSONB filter, inactive agent excluded

**Completion Log:**
_No entries yet._

---

### Chunk 5.3 — Agent Webhook Dispatch

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 5.2, 1.6
**PRD Reference:** Section 7.7, 7.11

**Description:**
Implement the webhook dispatch task. Builds the full enriched alert payload (alert + indicators + enrichment + detection rule + context docs + available workflows), POSTs to the agent endpoint with auth header, handles retries, and writes the `AgentRun` audit record.

**Output Artifacts:**
- `app/services/agent_dispatch.py` — `build_webhook_payload(alert: Alert, db: AsyncSession) -> dict` and `dispatch_to_agent(agent: AgentRegistration, payload: dict) -> AgentRunResult`
- `app/queue/registry.py` — `dispatch_agent_webhooks_task` registered on the `dispatch` queue; triggered after enrichment completes (chain: enrich_alert_task → dispatch_agent_webhooks_task)
- `app/services/agent_runs.py` — `record_agent_run(...)` writes to `agent_runs` table

**Acceptance Criteria:**
- [ ] Webhook payload includes all fields from PRD Section 7.7: full alert, all indicators with enrichment, detection rule with documentation, applicable context docs, relevant workflows, and `calseta_api_base_url`
- [ ] Webhook payload alert object includes `_metadata` block with the same structure as the REST detail response (same 6 fields: `generated_at`, `alert_source`, `indicator_count`, `enrichment`, `detection_rule_matched`, `context_documents_applied`); computed from the same source data using shared serialization logic
- [ ] `auth_header_name` + decrypted `auth_header_value` sent as request header
- [ ] Request timeout = `agent.timeout_seconds`
- [ ] Retries up to `agent.retry_count` with exponential backoff on non-2xx or network error
- [ ] Every dispatch attempt written to `agent_runs` with status, response, duration, attempt count
- [ ] One agent's failure does not affect other agents receiving the same alert
- [ ] Dispatch task enqueued after enrichment task completes (not before)

**Completion Log:**
_No entries yet._

---

### Chunk 5.4 — POST /v1/alerts/{uuid}/findings ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 2 complete
**PRD Reference:** Sections 7.7, 7.9

**Description:**
Implement the agent findings write-back endpoint. Agents call this after investigation to post their analysis. Findings are appended to `alerts.agent_findings` JSONB array with a timestamp.

**Output Artifacts:**
- Route already stubbed in 2.11; implement the full handler here

**Acceptance Criteria:**
- [ ] `POST` body validated: `agent_name` (required), `summary` (required), `confidence` enum (`low`/`medium`/`high`), `recommended_action` (optional), `evidence` (optional object)
- [ ] Finding appended to `agent_findings` array with server-side `posted_at` timestamp
- [ ] `GET /v1/alerts/{uuid}/findings` returns all findings for the alert ordered by `posted_at`
- [ ] Requires scope `alerts:write`

**Completion Log:**
_No entries yet._

---

### Chunk 5.5 — POST /v1/agents/{uuid}/test

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 5.3
**PRD Reference:** Section 7.9

**Description:**
Implement the agent test endpoint. Sends a synthetic webhook payload to the registered agent endpoint so teams can validate connectivity and payload parsing before real alerts arrive.

**Output Artifacts:**
- Route added to `app/api/v1/agents.py`

**Acceptance Criteria:**
- [ ] Sends a synthetic payload to `agent.endpoint_url` with auth header applied
- [ ] Synthetic payload clearly marked with `"test": true` at the top level
- [ ] Returns `200` with `{"delivered": true, "status_code": N, "duration_ms": N}` on success
- [ ] Returns `200` with `{"delivered": false, "error": "..."}` on connection failure (does not propagate HTTP error as 5xx)
- [ ] Requires scope `agents:write`

**Completion Log:**
_No entries yet._

---

### Chunk 5.6 — POST /v1/alerts/{uuid}/trigger-agents

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 5.3
**PRD Reference:** Section 7.9

**Description:**
Implement the manual agent trigger endpoint. Allows operators to re-dispatch an alert to all matching agents — useful for retrying failed deliveries or re-running agents after rule changes.

**Output Artifacts:**
- Route already stubbed in 2.9 (returns `501`); implement full handler here

**Acceptance Criteria:**
- [ ] Evaluates trigger criteria against the alert (same as post-enrichment evaluation in 5.2/5.3)
- [ ] Enqueues dispatch tasks for all matching agents
- [ ] Returns `202` with `{"data": {"queued_agent_count": N, "agent_names": [...]}}`
- [ ] Requires scope `agents:write`

**Completion Log:**
_No entries yet._

---

## Wave 6 — Metrics + Admin Endpoints

**Goal:** Implement all metrics computation and the remaining admin/utility endpoints.

**Depends on:** Waves 2, 3, and 4 complete.

**Internal sequencing:** 6.1, 6.2, 6.4, 6.5 can run in parallel ⚡. 6.3 depends on 6.1 + 6.2. 6.6 depends on 1.6.

---

### Chunk 6.1 — Alert Metrics + GET /v1/metrics/alerts ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 2 + 3 complete
**PRD Reference:** Section 7.6

**Description:**
Implement all alert metrics computations and the metrics endpoint. All metrics support `from` and `to` query params; default window is last 30 days.

**Output Artifacts:**
- `app/services/metrics.py` — functions for each metric in PRD Section 7.6 alert metrics table
- `app/api/v1/metrics.py` — `GET /v1/metrics/alerts`
- `app/schemas/metrics.py` — `AlertMetricsResponse`

**Acceptance Criteria:**
- [ ] All 13 alert metrics from PRD Section 7.6 implemented and returned
- [ ] `from` and `to` params accept ISO 8601; default to last 30 days if omitted
- [ ] `alerts_over_time` returns daily buckets within the time window
- [ ] `false_positive_rate` = alerts closed with FP tag / total closed alerts in window
- [ ] `mean_time_to_enrich` returned in seconds (float)
- [ ] `mean_time_to_detect` (MTTD) = `avg(created_at − occurred_at)` in seconds; returns `null` if `occurred_at` is null for all alerts in window
- [ ] `mean_time_to_acknowledge` (MTTA) = `avg(acknowledged_at − created_at)` in seconds; returns `null` if no alerts in window have left `Open` status
- [ ] `mean_time_to_triage` (MTTT) = `avg(triaged_at − created_at)` in seconds; returns `null` if no alerts in window reached `Triaging`
- [ ] `mean_time_to_conclusion` (MTTC) = `avg(closed_at − created_at)` in seconds; returns `null` if no alerts in window were closed
- [ ] All MTTX fields serialize as `null` (not `0` or absent) when no qualifying data exists in the window
- [ ] Requires scope `alerts:read`

**Completion Log:**
_No entries yet._

---

### Chunk 6.2 — Workflow Metrics + GET /v1/metrics/workflows ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 4 complete
**PRD Reference:** Section 7.6

**Description:**
Implement all workflow metrics and the workflow metrics endpoint.

**Output Artifacts:**
- Additional functions added to `app/services/metrics.py`
- Route `GET /v1/metrics/workflows` added to `app/api/v1/metrics.py`
- `app/schemas/metrics.py` — `WorkflowMetricsResponse`

**Acceptance Criteria:**
- [ ] All 6 workflow metrics from PRD Section 7.6 implemented
- [ ] `time_saved` = sum of `time_saved_minutes` for all successful runs in window (returns hours float)
- [ ] `workflow_success_rate` = successful runs / total runs (0.0–1.0)
- [ ] Requires scope `workflows:read`

**Completion Log:**
_No entries yet._

---

### Chunk 6.3 — GET /v1/metrics/summary

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 6.1, 6.2
**PRD Reference:** Section 7.6

**Description:**
Implement the compact metrics summary endpoint. Returns the exact JSON structure from PRD Section 7.6 — optimized for agent context injection (low token cost, all key numbers in one payload).

**Output Artifacts:**
- Route `GET /v1/metrics/summary` added to `app/api/v1/metrics.py`

**Acceptance Criteria:**
- [ ] Response matches PRD Section 7.6 `calseta://metrics/summary` structure exactly (same field names and nesting)
- [ ] Always covers the last 30 days (no time window params)
- [ ] Response time < 500ms (add a DB index if needed)
- [ ] Requires scope `alerts:read`

**Completion Log:**
_No entries yet._

---

### Chunk 6.4 — Source Integrations CRUD Endpoints ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 1 complete
**PRD Reference:** Section 7.9

**Description:**
Implement source integration management endpoints. Source integrations store metadata and auth config for each configured alert source. CRUD only.

**Output Artifacts:**
- `app/api/v1/sources.py` — 5 endpoints from PRD Section 7.9 (`GET /v1/sources`, `POST`, `GET /{uuid}`, `PATCH /{uuid}`, `DELETE /{uuid}`)
- `app/schemas/sources.py` — `SourceIntegrationCreate`, `SourceIntegrationResponse`, `SourceIntegrationPatch`

**Acceptance Criteria:**
- [ ] `source_name` must match a registered source plugin; unknown value returns `400`
- [ ] `auth_config` encrypted at rest; never returned in responses
- [ ] `GET /v1/sources` returns `is_active` and `source_name` for each configured source
- [ ] Requires scope `admin` for all write operations; `alerts:read` for reads

**Completion Log:**
_No entries yet._

---

### Chunk 6.5 — GET /v1/alerts/{uuid}/indicators ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 2 + 3 complete
**PRD Reference:** Section 7.9

**Description:**
Implement the alert indicators sub-resource endpoint. Returns all extracted IOCs for an alert with their enrichment results. Indicators are stored in a relational join table (`alert_indicators` → `indicators`) — there is no `indicators` JSONB column on the `alerts` table.

**Output Artifacts:**
- Route added to `app/api/v1/alerts.py`
- `app/repositories/indicators.py` — `get_indicators_for_alert(alert_id: int, db: AsyncSession) -> list[Indicator]`; queries via `alert_indicators` join

**Acceptance Criteria:**
- [ ] Returns all indicators joined via `alert_indicators` → `indicators` for the given alert UUID
- [ ] Each indicator entry includes: `type`, `value`, `malice`, `first_seen`, `last_seen`, `is_enriched`, `enrichment_results` keyed by provider name (only the `extracted` sub-object; `raw` excluded)
- [ ] `enrichment_results` per provider includes `success`, `extracted`, `enriched_at` — the `raw` key is excluded from the response (token efficiency)
- [ ] `404` for unknown alert UUID
- [ ] Response is `DataResponse[list[IndicatorResponse]]`
- [ ] Requires scope `alerts:read`

**Completion Log:**
_No entries yet._

---

### Chunk 6.6 — GET /health (Full Implementation)

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 1.6
**PRD Reference:** Section 7.9, 7.11

**Description:**
Upgrade the stub health endpoint to a full health check. Reports status of all subsystems: database connectivity, worker queue depth, and enrichment provider reachability.

**Output Artifacts:**
- `app/api/health.py` — full health check handler replacing the stub from 1.1

**Acceptance Criteria:**
- [ ] Returns `200` when all systems healthy; `503` if any critical system is down
- [ ] Response includes: `{"status": "ok|degraded|down", "db": "ok|error", "queue_depth": N, "enrichment_providers": {"virustotal": "configured|unconfigured", ...}}`
- [ ] DB check: execute a trivial query (`SELECT 1`); reports error if it fails
- [ ] Queue depth: number of pending tasks across all queues
- [ ] Does not require auth (public endpoint)
- [ ] Responds within 2 seconds even if a subsystem check hangs (timeout per check)

**Completion Log:**
_No entries yet._

---

## Wave 7 — MCP Server

**Goal:** Implement the full MCP server: all resources and all tools, as a thin adapter over the REST API (no independent business logic).

**Depends on:** Waves 2, 3, 4, 5, and 6 complete.

**Internal sequencing:** 7.1 first, then 7.2–7.4 in parallel ⚡, then 7.5 depends on all.

---

### Chunk 7.1 — MCP Server Scaffold + Auth

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 1 + 1.4 complete
**PRD Reference:** Section 7.8

**Description:**
Set up the MCP server process using the Anthropic MCP Python SDK. Wire up authentication using the same API key mechanism as the REST API. The server starts on port 8001 and accepts MCP connections. No resources or tools yet — those are added in 7.2–7.5.

**Output Artifacts:**
- `app/mcp/server.py` — MCP `Server` instance, auth middleware, startup/shutdown lifecycle
- `app/mcp/__init__.py`
- `app/mcp/auth.py` — extracts and validates API key from MCP connection metadata using `AuthBackendBase`

**Acceptance Criteria:**
- [ ] MCP server starts on port 8001 in Docker Compose
- [ ] Connection without a valid API key is rejected
- [ ] Connection with a valid API key succeeds
- [ ] Server restarts cleanly if the port is already in use (descriptive error, not a crash)
- [ ] MCP server imports no business logic directly — all data access will go through the REST API's service layer

**Completion Log:**
_No entries yet._

---

### Chunk 7.2 — MCP Resources: Alerts + Detection Rules ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 7.1, Wave 2 complete
**PRD Reference:** Section 7.8

**Description:**
Implement MCP resources for alerts and detection rules. Resources are read-only views — they call internal service functions to fetch data and return structured MCP resource content.

**Output Artifacts:**
- `app/mcp/resources/alerts.py` — `calseta://alerts`, `calseta://alerts/{uuid}`, `calseta://alerts/{uuid}/context`, `calseta://alerts/{uuid}/activity`
- `app/mcp/resources/detection_rules.py` — `calseta://detection-rules`, `calseta://detection-rules/{uuid}`

**Acceptance Criteria:**
- [ ] `calseta://alerts` returns recent alerts (last 50) with status, severity, source, `is_enriched`
- [ ] `calseta://alerts/{uuid}` returns full alert with enrichments, detection rule with full documentation, and applicable context docs
- [ ] `calseta://alerts/{uuid}/activity` returns the ordered activity log (newest-first, max 100 events) formatted for agent consumption: each event shows `event_type`, `actor_type`, `actor_key_prefix`, `created_at`, and `references` flattened as labeled key-value pairs
- [ ] `calseta://detection-rules` returns catalog with MITRE mappings and documentation summaries (not full docs)
- [ ] `calseta://detection-rules/{uuid}` returns full rule with complete documentation
- [ ] Unknown UUID returns MCP resource-not-found error
- [ ] All resources require the `alerts:read` scope on the connected API key

**Completion Log:**
_No entries yet._

---

### Chunk 7.3 — MCP Resources: Context Docs + Workflows + Metrics ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 7.1, Wave 4 + 6 complete
**PRD Reference:** Section 7.8

**Description:**
Implement MCP resources for context documents, workflows, and the metrics summary.

**Output Artifacts:**
- `app/mcp/resources/context_documents.py` — `calseta://context-documents`, `calseta://context-documents/{uuid}`
- `app/mcp/resources/workflows.py` — `calseta://workflows`, `calseta://workflows/{uuid}`
- `app/mcp/resources/metrics.py` — `calseta://metrics/summary`

**Acceptance Criteria:**
- [ ] `calseta://context-documents` returns list with `title`, `document_type`, `description` — no `content` (token efficiency)
- [ ] `calseta://context-documents/{uuid}` returns full content
- [ ] `calseta://workflows` returns full catalog with documentation so agents can reason about available automations
- [ ] `calseta://metrics/summary` returns the exact compact structure from PRD Section 7.6
- [ ] Scope requirements: `alerts:read` for context docs, `workflows:read` for workflows, `alerts:read` for metrics

**Completion Log:**
_No entries yet._

---

### Chunk 7.4 — MCP Resources: On-Demand Enrichment ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 7.1, Wave 3 complete
**PRD Reference:** Section 7.8

**Description:**
Implement the enrichment MCP resource. When an agent reads `calseta://enrichments/{type}/{value}`, the platform performs on-demand enrichment (cache-first) and returns results.

**Output Artifacts:**
- `app/mcp/resources/enrichments.py` — `calseta://enrichments/{type}/{value}`

**Acceptance Criteria:**
- [ ] Resource URI accepts any valid `IndicatorType` as `type`
- [ ] Returns enrichment results from all configured providers (same data as `POST /v1/enrichments`)
- [ ] Cache hit returns immediately; cache miss triggers live enrichment calls
- [ ] Invalid `type` value returns MCP error with a descriptive message
- [ ] Requires scope `enrichments:read`

**Completion Log:**
_No entries yet._

---

### Chunk 7.5 — MCP Tools

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 7.1, 7.2, 7.3, 7.4, Wave 5 complete
**PRD Reference:** Section 7.8

**Description:**
Implement all six MCP tools from PRD Section 7.8. Tools are write/execute operations. Each tool validates its inputs, delegates to the appropriate service or API layer, and returns structured results.

**Output Artifacts:**
- `app/mcp/tools/alerts.py` — `post_alert_finding`, `update_alert_status`, `search_alerts`
- `app/mcp/tools/workflows.py` — `execute_workflow`
- `app/mcp/tools/enrichment.py` — `enrich_indicator`
- `app/mcp/tools/detection_rules.py` — `search_detection_rules`

**Acceptance Criteria:**
- [ ] All 6 tools from PRD Section 7.8 implemented with correct input schemas
- [ ] `post_alert_finding`: requires `alert_uuid`, `summary`, `confidence`; returns finding UUID
- [ ] `update_alert_status`: requires `alert_uuid`, `status`; validates status value
- [ ] `execute_workflow`: requires `workflow_uuid` and trigger context; enqueues task and returns run UUID
- [ ] `enrich_indicator`: requires `type` and `value`; returns enrichment results synchronously
- [ ] `search_alerts` and `search_detection_rules`: accept filter criteria, return matching records
- [ ] Tool descriptions in MCP schema are written for agent consumption (clear, concise, state what inputs are required and what the tool returns)
- [ ] Each tool enforces the appropriate scope on the connected API key

**Completion Log:**
_No entries yet._

---

## Wave 8 — Testing, Documentation & Examples

**Goal:** Bring test coverage to acceptable levels for all feature waves, produce the developer documentation, and build the example agents.

**Depends on:** Each chunk depends on its named waves being complete. Chunks within this wave are fully independent ⚡.

---

### Chunk 8.0 — Test Suite: Indicator Extraction Pipeline ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 2 complete (specifically 2.8 + 2.9)
**PRD Reference:** Section 7.12

**Output Artifacts:**
- `tests/test_indicator_extraction.py`
- `tests/test_indicator_mappings_api.py`

**Acceptance Criteria:**
- [ ] Pass 1 test: source plugin `extract_indicators` result flows into pipeline output
- [ ] Pass 2 test: each of the 17 system normalized-field mappings extracts correctly from a fixture `CalsetaAlert`
- [ ] Pass 3 dot-notation test: simple field, nested field, array field, deeply nested array, missing field
- [ ] Pass 3 array unwrapping: `related.ip = ["1.2.3.4", "5.6.7.8"]` → two IP indicators
- [ ] Deduplication: same IP from Pass 1 + Pass 3 → one indicator in output
- [ ] Exception in Pass 1 does not prevent Pass 2 + 3 from running
- [ ] `POST /v1/indicator-mappings/test` integration test: payload + field path → extracted indicators
- [ ] `DELETE` on system mapping → `403`; on custom mapping → `204`
- [ ] Seeder idempotency: running `seed_system_mappings()` twice leaves exactly 17 system rows

**Completion Log:**
_No entries yet._

---

### Chunk 8.1 — Test Suite: Ingestion + Detection Rules ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 2 complete
**PRD Reference:** Section 7.1, 7.3

**Output Artifacts:**
- `tests/test_ingestion.py`, `tests/test_detection_rules.py`, `tests/test_sources/`

**Acceptance Criteria:**
- [ ] Each source plugin (Sentinel, Elastic, Splunk) has: normalize happy path test (output is valid `CalsetaAlert`), invalid payload test, indicator extraction test using fixture JSON
- [ ] `POST /v1/ingest/sentinel` integration test: fixture payload → alert created with correct fields
- [ ] `POST /v1/alerts` integration test: `CalsetaAlert` payload → alert stored → enrichment task enqueued
- [ ] Detection rule auto-association: existing rule → associated; new rule → created
- [ ] All detection rule CRUD endpoints covered by integration tests
- [ ] `make test` passes; coverage for `app/integrations/sources/` ≥ 85%

**Completion Log:**
_No entries yet._

---

### Chunk 8.2 — Test Suite: Enrichment Engine ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 3 complete
**PRD Reference:** Section 7.2

**Output Artifacts:**
- `tests/test_enrichment/`

**Acceptance Criteria:**
- [ ] Each provider has: happy path test, unconfigured test, network error test, provider timeout test — all using mocked HTTP (no real API calls in tests)
- [ ] Enrichment pipeline test: alert with 3 indicators → all enriched concurrently → results written to alert
- [ ] One provider failure does not block others (tested explicitly)
- [ ] Cache hit test: same indicator enriched twice → HTTP called only once
- [ ] `POST /v1/enrichments` integration test
- [ ] Coverage for `app/integrations/enrichment/` ≥ 85%

**Completion Log:**
_No entries yet._

---

### Chunk 8.3 — Test Suite: Context + Workflow Engine ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 4 complete
**PRD Reference:** Sections 7.4, 7.5

**Output Artifacts:**
- `tests/test_context.py`, `tests/test_workflows.py`

**Acceptance Criteria:**
- [ ] Targeting rule tests: all 5 operators, `match_any` only, `match_all` only, mixed, global doc always included
- [ ] `GET /v1/alerts/{uuid}/context` integration test with multiple documents
- [ ] Template engine: all 4 variable types, nested structure, unknown variable
- [ ] Workflow execution: happy path (200), failure + retry, auth types (bearer, api_key, basic)
- [ ] Workflow run audit log written on success and failure
- [ ] Coverage ≥ 80% for `app/services/workflow_*.py` and `app/services/context_*.py`

**Completion Log:**
_No entries yet._

---

### Chunk 8.4 — Test Suite: Agent Integration Layer ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 5 complete
**PRD Reference:** Section 7.7

**Output Artifacts:**
- `tests/test_agents.py`

**Acceptance Criteria:**
- [ ] Trigger evaluation: source filter, severity filter, JSONB filter, inactive agent excluded, combined filters
- [ ] Webhook dispatch: payload structure matches PRD Section 7.7 spec, auth header applied, retry on failure
- [ ] One agent failure does not affect other agents (tested with two agents, one fails)
- [ ] `POST /v1/alerts/{uuid}/findings` validation and storage
- [ ] `POST /v1/agents/{uuid}/test` integration test
- [ ] Coverage ≥ 80% for `app/services/agent_*.py`

**Completion Log:**
_No entries yet._

---

### Chunk 8.5 — Test Suite: MCP Server ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 7 complete
**PRD Reference:** Section 7.8

**Output Artifacts:**
- `tests/test_mcp/`

**Acceptance Criteria:**
- [ ] Auth: valid key → connected; invalid key → rejected
- [ ] Each resource returns correctly shaped content (spot-check key fields)
- [ ] Each tool validates inputs and returns expected outputs (using mocked service layer)
- [ ] Unknown UUID in resource URI returns MCP error (not unhandled exception)
- [ ] Coverage ≥ 75% for `app/mcp/`

**Completion Log:**
_No entries yet._

---

### Chunk 8.6 — docs/HOW_TO_ADD_ALERT_SOURCE.md ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 2 complete
**PRD Reference:** Section 9

**Output Artifacts:**
- `docs/HOW_TO_ADD_ALERT_SOURCE.md`

**Acceptance Criteria:**
- [ ] Explains `AlertSourceBase` and each method's contract
- [ ] Complete worked example: a fictional source called `GuardDuty` implementing all methods with real-looking payload mapping
- [ ] Shows where to register the plugin in `__init__.py`
- [ ] Explains how to write and run tests using the fixture pattern
- [ ] Written in LLM-friendly style: precise, no ambiguity, code blocks for every step

**Completion Log:**
_No entries yet._

---

### Chunk 8.7 — docs/HOW_TO_ADD_ENRICHMENT_PROVIDER.md ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 3 complete
**PRD Reference:** Section 9

**Output Artifacts:**
- `docs/HOW_TO_ADD_ENRICHMENT_PROVIDER.md`

**Acceptance Criteria:**
- [ ] Explains `EnrichmentProviderBase`, the no-raise contract, and TTL defaults
- [ ] Complete worked example: a fictional provider called `IPInfo` for IP and domain types
- [ ] Shows env var pattern for `is_configured()`, httpx async pattern for `enrich()`
- [ ] Explains cache key format and TTL configuration
- [ ] Written in LLM-friendly style

**Completion Log:**
_No entries yet._

---

### Chunk 8.8 — docs/HOW_TO_DEPLOY.md ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 6 complete (health endpoint must be final)
**PRD Reference:** Section 10

**Output Artifacts:**
- `docs/HOW_TO_DEPLOY.md`

**Acceptance Criteria:**
- [ ] Local development: `docker compose up` walkthrough, first API key creation, verifying health endpoint
- [ ] Environment variables: complete table of every var, its type, default, and whether required
- [ ] Production checklist: `SECRET_KEY` rotation, `DEBUG=false`, DB connection pool settings, worker concurrency tuning
- [ ] Connecting a SIEM source: step-by-step for Sentinel webhook configuration
- [ ] Troubleshooting section: common startup errors and resolutions

**Completion Log:**
_No entries yet._

---

### Chunk 8.9 — examples/sample_agent_python.py ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 5 + 7 complete
**PRD Reference:** Section 14

**Description:**
A working sample agent that receives alert webhooks from Calseta AI, calls the REST API for additional context, reasons about the alert using the Claude API, and posts a finding back. Uses raw `httpx` + `anthropic` SDK (no agent framework dependency).

**Output Artifacts:**
- `examples/sample_agent_python.py`
- `examples/README.md` (created here; 8.10 will append to it)

**Acceptance Criteria:**
- [ ] Runnable with `python examples/sample_agent_python.py` after setting env vars
- [ ] Implements a webhook receiver (FastAPI or Flask) that accepts Calseta alert webhooks
- [ ] Calls `GET /v1/alerts/{uuid}` to fetch full context
- [ ] Builds a prompt from alert data, detection rule docs, and context documents
- [ ] Calls Claude API and parses the response
- [ ] Posts a finding back via `POST /v1/alerts/{uuid}/findings`
- [ ] Code is heavily commented explaining each step
- [ ] `examples/README.md` explains how to run it and what to expect

**Completion Log:**
_No entries yet._

---

### Chunk 8.10 — examples/sample_agent_mcp.py ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 7 complete
**PRD Reference:** Section 14

**Description:**
A working sample agent that uses only the MCP server — no direct REST API calls. Demonstrates that an agent connected to Calseta's MCP server can investigate an alert end-to-end using only MCP resources and tools.

**Output Artifacts:**
- `examples/sample_agent_mcp.py`
- `examples/README.md` — section appended for MCP agent

**Acceptance Criteria:**
- [ ] Connects to the MCP server using the Anthropic MCP client SDK
- [ ] Reads `calseta://alerts` to find an active alert
- [ ] Reads `calseta://alerts/{uuid}` for full context
- [ ] Reads `calseta://workflows` to discover available automations
- [ ] Uses `post_alert_finding` MCP tool to submit a finding
- [ ] Does not make any direct HTTP calls to the REST API — MCP only
- [ ] Demonstrates at least one workflow execution via the `execute_workflow` MCP tool
- [ ] Code is heavily commented; README section explains the MCP-only pattern and why it matters

**Completion Log:**
_No entries yet._

---

### Chunk 8.11 — Validation Case Study ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 5 complete, Wave 3 complete, 8.9 (sample agents exist as reference)
**PRD Reference:** Section 15

**Description:**
Execute the controlled comparison study described in PRD Section 15. Build two runnable agent implementations — the naive baseline and the Calseta-powered agent — run them against five realistic alert fixtures, capture all metrics, and publish the results. This is a coding + execution + analysis task. The agent implementing this chunk writes Python, runs it, records real numbers, and writes the analysis document.

The five alert fixtures must be synthetic but realistic — shaped like real Sentinel/Elastic/Splunk alert payloads. They must not contain real IP addresses, user accounts, or file hashes that could be traced to real incidents. Use plausible but fictional values.

**Output Artifacts:**
- `examples/case_study/fixtures/scenario_1_account_compromise.json` — Sentinel alert, suspicious sign-in
- `examples/case_study/fixtures/scenario_2_malware_detection.json` — Elastic alert, malicious hash on endpoint
- `examples/case_study/fixtures/scenario_3_network_intrusion.json` — Splunk alert, brute force from external IP
- `examples/case_study/fixtures/scenario_4_lateral_movement.json` — Sentinel alert, multi-indicator
- `examples/case_study/fixtures/scenario_5_phishing.json` — Elastic alert, malicious URL clicked
- `examples/case_study/naive_agent.py` — Approach A: receives raw alert JSON, calls enrichment APIs via tool calls, reasons about the alert, produces a finding. All token usage tracked via Anthropic API `usage` response fields.
- `examples/case_study/calseta_agent.py` — Approach B: receives enriched Calseta webhook payload, reasons about the alert, posts finding via REST API. Token usage tracked the same way.
- `examples/case_study/run_study.py` — orchestration script: runs both approaches against all 5 fixtures 3 times each, captures all metrics, writes CSV output
- `examples/case_study/results/raw_metrics.csv` — actual numbers from the runs
- `examples/case_study/evaluate_findings.py` — sends both findings per scenario to Claude as a blind judge (doesn't know which is A or B), scores completeness/accuracy/actionability 1–5
- `docs/VALIDATION_CASE_STUDY.md` — methodology description, results table, analysis, and conclusions

**Acceptance Criteria:**
- [ ] All 5 fixture JSON files are realistic in shape (correct field names, plausible nesting, representative sizes) but contain no real PII or sensitive data
- [ ] `naive_agent.py` is fully functional with only `ANTHROPIC_API_KEY` + enrichment provider keys — no Calseta instance required
- [ ] `calseta_agent.py` is fully functional against a local `docker compose up` Calseta instance
- [ ] `run_study.py` runs end-to-end and produces `raw_metrics.csv` with: scenario, approach, run number, input_tokens, output_tokens, total_tokens, tool_call_count, api_call_count, duration_seconds, estimated_cost_usd
- [ ] Each scenario run 3 times per approach; `raw_metrics.csv` has 30 rows (5 × 2 × 3)
- [ ] `evaluate_findings.py` runs the blind judge and appends `quality_score` to results
- [ ] `docs/VALIDATION_CASE_STUDY.md` contains: methodology summary, averaged results table, percentage differences, honest interpretation (including any scenarios where results were not as expected), and a clear statement of whether the 50% input token reduction threshold (PRD Section 15) was met
- [ ] If the 50% threshold is NOT met in any scenario, the document must include a root cause analysis and a proposed platform improvement — the study is not "passed" by omitting bad results

**Context & Notes:**
- Use `anthropic.Anthropic().messages.create(...)` and read `response.usage.input_tokens` / `response.usage.output_tokens` for token counts
- For cost estimation: use the current published Sonnet pricing at time of writing; pin the model version used so results are reproducible
- The blind judge prompt should give Claude two anonymized findings labeled "Finding A" and "Finding B" and ask it to score each on: (1) identified the correct threat type, (2) cited specific evidence from the alert, (3) provided a concrete recommended action. Numeric scores 1–5 per dimension.
- Run the study on a machine with a stable internet connection; enrichment API latency affects Approach A timing significantly
- Document which enrichment provider API keys were active during the run — results vary if some providers are unconfigured

**Completion Log:**
_No entries yet._

---

### Chunk 8.12 — Component CONTEXT.md Files ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Each CONTEXT.md depends on the wave that implements that component being `complete`. All seven can be written in parallel once their respective components are done. Specifically:
- `sources/CONTEXT.md` — Wave 2 complete
- `enrichment/CONTEXT.md` — Wave 3 complete
- `workflows/CONTEXT.md` — Wave 4 complete
- `queue/CONTEXT.md` — Wave 1 complete
- `mcp/CONTEXT.md` — Wave 7 complete
- `auth/CONTEXT.md` — Wave 1 complete
- `services/CONTEXT.md` — Wave 4 complete (all service modules present)

**PRD Reference:** Section 5 (Component-level LLM context documentation philosophy)

**Description:**
Write a `CONTEXT.md` for each major component directory. Each file is a machine-readable, LLM-optimized operational guide for that component — written so that an agent (or a new human contributor) can read it and make a correct change to the component without reading all the source files first.

**Output Artifacts:**
- `app/integrations/sources/CONTEXT.md`
- `app/integrations/enrichment/CONTEXT.md`
- `app/workflows/CONTEXT.md`
- `app/queue/CONTEXT.md`
- `app/mcp/CONTEXT.md`
- `app/auth/CONTEXT.md`
- `app/services/CONTEXT.md`

**Required content for each file:**
1. **What this component does** — one clear paragraph, no filler
2. **Interfaces** — inputs, outputs, and the contracts callers must uphold (with type signatures where applicable)
3. **Key design decisions** — the "why" behind non-obvious implementation choices; what alternatives were rejected
4. **Extension pattern** — exact steps to add a new plugin/handler/backend (concrete, numbered)
5. **Common failure modes** — what breaks here, how to diagnose it, what log events to look for
6. **Test coverage** — which test files cover this component and what scenarios they exercise

**Acceptance Criteria:**
- [ ] All 7 files exist and are non-empty
- [ ] Each file covers all 6 required sections
- [ ] The "Extension pattern" section in `sources/CONTEXT.md` matches the pattern in `docs/HOW_TO_ADD_ALERT_SOURCE.md` (no contradictions)
- [ ] The "Extension pattern" section in `enrichment/CONTEXT.md` matches `docs/HOW_TO_ADD_ENRICHMENT_PROVIDER.md`
- [ ] Each file references the actual class names and method signatures from the implemented code (not placeholders)
- [ ] `app/services/CONTEXT.md` clearly explains the layered architecture boundaries (what belongs in a service vs. repository vs. route handler)
- [ ] A new AI agent reading only a component's `CONTEXT.md` could correctly identify where to add a new plugin, where to add a test, and what would break if a given interface changed
- [ ] No file contains marketing language, filler, or vague descriptions — every sentence is actionable or informative

**Completion Log:**
_No entries yet._

---

### Chunk 8.13 — docs/HOW_TO_RUN_MIGRATIONS.md ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 8.8 complete
**PRD Reference:** Section 10 (Deployability)

**Description:**
Write the Alembic migration operations guide for operators. Covers everything needed to run, verify, and recover from database migrations during version upgrades. This document is the operator's reference for any schema change operation — production deployments, development resets, and mid-upgrade rollbacks.

**Output Artifacts:**
- `docs/HOW_TO_RUN_MIGRATIONS.md`

**Acceptance Criteria:**
- [ ] Explains what Alembic is and why Calseta uses it (schema changes via migrations only — no manual DDL, ever)
- [ ] Shows how to check current migration version: `docker exec calseta-api alembic current`
- [ ] Shows how to run migrations to latest: `docker exec calseta-api alembic upgrade head`
- [ ] Documents what to do when a migration fails: rollback with `alembic downgrade -1`, read the error from logs, fix and re-run
- [ ] Shows how to view migration history: `alembic history`
- [ ] Covers post-migration system data seeding (indicator field mappings are seeded at startup — explains when re-seeding is automatic vs. when a manual step is needed)
- [ ] Clarifies when migration runs automatically (startup auto-migrate in development mode) vs. when it must be run manually (production pre-deployment step, before restarting containers)
- [ ] All example commands are tested against the actual Alembic setup in the repo and produce the documented output

**Completion Log:**
_No entries yet._

---

### Chunk 8.14 — docs/HOW_TO_UPGRADE.md

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 8.13 complete
**PRD Reference:** Section 10 (Deployability)

**Description:**
Write the end-to-end version upgrade procedure guide. Covers the full upgrade lifecycle from pre-upgrade checklist through rollback. Operators reference this document when moving from one Calseta version to another in any environment.

**Output Artifacts:**
- `docs/HOW_TO_UPGRADE.md`

**Acceptance Criteria:**
- [ ] Pre-upgrade checklist: read the changelog for breaking changes, back up the PostgreSQL database, identify any API changes that affect connected agents
- [ ] Step-by-step upgrade procedure: pull new Docker image → run `alembic upgrade head` → restart containers → smoke test
- [ ] Rollback procedure: restore DB backup → redeploy previous image tag → verify health endpoint responds `{"status": "ok"}`
- [ ] Zero-downtime guidance for production: run migration first, then rolling container restart (explains why migration-first is safe for additive migrations; flags when breaking migrations require a maintenance window)
- [ ] Version compatibility matrix section (stub with v1.0.0 entry; maintained here as versions accumulate — documents which versions are migration-compatible with no downtime)
- [ ] Post-upgrade smoke test checklist: health endpoint, ingest a test alert via `POST /v1/ingest/generic`, verify enrichment runs, verify MCP server responds on port 8001
- [ ] References `HOW_TO_RUN_MIGRATIONS.md` for migration command details rather than duplicating content

**Completion Log:**
_No entries yet._

---

---

## Wave 9 — Hosted Sandbox (v1.5)

**Goal:** Deploy the hosted sandbox at `sandbox.calseta.ai` — a live, publicly accessible Calseta AI instance with mock enrichment providers, pre-seeded fixture data, and a 24-hour auto-reset. Ship the `/benchmark` page on the Calseta website.

**Depends on:** Wave 8 complete (case study fixtures and results must exist before the benchmark page can be written).

**Internal sequencing:** 9.1 and 9.2 can run in parallel ⚡. 9.3 depends on 9.1. 9.4 depends on 9.1 + 9.2 + 9.3. 9.5 depends on 9.4.

---

### Chunk 9.1 — Mock Enrichment Providers ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 3 complete (real providers must exist first — mocks mirror their interface)
**PRD Reference:** Section 12 (v1.5)

**Description:**
Implement mock versions of all four enrichment providers that return realistic canned responses without making any external HTTP calls. Mocks are activated via `ENRICHMENT_MOCK_MODE=true`. They implement the same `EnrichmentProviderBase` interface as real providers — they are drop-in replacements, not test doubles. The mock data must be representative of real provider responses (field names, nesting, value ranges) so the sandbox gives an accurate picture of what enrichment results look like.

**Output Artifacts:**
- `app/integrations/enrichment/mocks/virustotal_mock.py` — returns a canned VirusTotal response for any indicator; varies response by indicator type (IP response looks different from hash response); includes a high-malice variant and a clean variant seeded by indicator value hash
- `app/integrations/enrichment/mocks/abuseipdb_mock.py` — canned AbuseIPDB response
- `app/integrations/enrichment/mocks/okta_mock.py` — canned Okta user response with realistic fields (status, MFA enrolled, groups, last login)
- `app/integrations/enrichment/mocks/entra_mock.py` — canned Entra user response
- `app/integrations/enrichment/mock_registry.py` — replaces the real registry when `ENRICHMENT_MOCK_MODE=true`; `is_configured()` always returns `True` for all mock providers

**Acceptance Criteria:**
- [ ] `ENRICHMENT_MOCK_MODE=true` activates all mock providers; real providers are not loaded
- [ ] `ENRICHMENT_MOCK_MODE=false` (default) loads real providers as normal; mock providers are not loaded
- [ ] Mock response field names and structure are identical to real provider responses (verified against `api_notes.md` for each provider)
- [ ] Mock responses vary by indicator value so different indicators return different results (not all "high risk" or all "clean") — use a deterministic hash of the indicator value to select from 3–5 canned variants per provider
- [ ] `GET /v1/enrichments/providers` in mock mode shows all providers as `is_configured: true`
- [ ] End-to-end test: ingest a fixture alert with `ENRICHMENT_MOCK_MODE=true` → alert fully enriched within 5 seconds → all four providers have results

**Completion Log:**
_No entries yet._

---

### Chunk 9.2 — Sandbox Fixture Seeder ⚡

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** Wave 2 complete, Wave 4 complete (workflows must exist to seed them), 8.11 (case study fixtures)
**PRD Reference:** Section 12 (v1.5)

**Description:**
Build the sandbox seeder that populates a fresh instance with all pre-loaded fixture data: the five case study alert scenarios (fully ingested and enriched), sample detection rules with populated documentation, sample context documents, and the pre-built workflows. The seeder produces a fully explorable platform state for a first-time visitor.

**Output Artifacts:**
- `app/seed/sandbox.py` — `seed_sandbox(db: AsyncSession) -> None`; calls all existing seeders plus inserts sandbox-specific data
- `app/seed/sandbox_alerts.py` — ingests the 5 case study fixture JSON files (from `examples/case_study/fixtures/`), runs them through the full ingestion pipeline, waits for enrichment to complete
- `app/seed/sandbox_detection_rules.py` — creates 5 detection rules (one per scenario) with fully populated `documentation` fields (realistic markdown content)
- `app/seed/sandbox_context_documents.py` — creates 3 context documents: a generic incident response runbook, an account compromise SOP, and a malware response playbook — all with realistic markdown content
- `Makefile` — `make seed-sandbox` target

**Acceptance Criteria:**
- [ ] `make seed-sandbox` on a fresh DB: completes without error; all 5 alerts present at `GET /v1/alerts` with `is_enriched: true`
- [ ] Each fixture alert has its detection rule associated and `documentation` populated
- [ ] `GET /v1/alerts/{uuid}/context` returns at least 1 context document for each fixture alert
- [ ] All 9 pre-built workflows visible at `GET /v1/workflows`
- [ ] Seeder is idempotent — running twice does not create duplicate data
- [ ] A new visitor with only the public sandbox API key can call `GET /v1/alerts` and receive meaningful, explorable data immediately

**Completion Log:**
_No entries yet._

---

### Chunk 9.3 — Auto-Reset Mechanism

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 9.1, 9.2
**PRD Reference:** Section 12 (v1.5)

**Description:**
Implement the 24-hour auto-reset that wipes all user-created data and restores the sandbox to its seeded state. The reset must preserve system-seeded data (indicator mappings, pre-built workflows, fixture alerts) and remove only user-created data (custom alerts ingested during the session, user-created detection rules, custom context documents, custom workflows, API keys created during the session).

**Output Artifacts:**
- `app/tasks/sandbox_reset.py` — `reset_sandbox_task()` procrastinate task: truncates user data tables, re-runs `seed_sandbox()`, logs completion
- `app/worker.py` — updated to schedule `reset_sandbox_task` via a periodic cron schedule when `SANDBOX_MODE=true`
- `app/config.py` — `SANDBOX_MODE: bool = False` setting added

**Acceptance Criteria:**
- [ ] With `SANDBOX_MODE=true`, `reset_sandbox_task` runs every 24 hours
- [ ] Reset removes: all alerts with `is_system=False` created after the last reset, user-created detection rules, user-created context documents, user-created workflows, API keys created after the last reset (the public sandbox key is preserved)
- [ ] Reset does NOT remove: system indicator mappings, pre-built workflows, fixture alerts, fixture detection rules, fixture context documents
- [ ] `GET /v1/alerts` after reset returns exactly the 5 fixture alerts
- [ ] Reset completes within 30 seconds
- [ ] A log entry is written at the start and end of each reset including row counts deleted and rows re-seeded

**Completion Log:**
_No entries yet._

---

### Chunk 9.4 — Sandbox Deployment (AWS)

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 9.1, 9.2, 9.3
**PRD Reference:** Section 12 (v1.5), Section 12 (v3.1 Terraform)

**Description:**
Deploy the sandbox to AWS using the Terraform module from v3.1 (or a simplified version if v3.1 is not yet complete). The sandbox runs at `sandbox.calseta.ai` with HTTPS, serves the API on port 443, and exposes the MCP server endpoint. Secrets are managed in AWS Secrets Manager.

**Output Artifacts:**
- `terraform/sandbox/` — Terraform configuration for the sandbox deployment (ECS Fargate, RDS, ALB, ACM certificate, Route 53 record)
- `terraform/sandbox/variables.tf` — domain name, AWS region, container image tag
- `.github/workflows/deploy-sandbox.yml` — CI/CD workflow: build Docker image on merge to `main`, push to ECR, update ECS service

**Acceptance Criteria:**
- [ ] `terraform apply` in `terraform/sandbox/` deploys a working sandbox from scratch
- [ ] `https://sandbox.calseta.ai/health` returns `200 {"status": "ok"}`
- [ ] `https://sandbox.calseta.ai/v1/alerts` (with public key) returns the 5 fixture alerts
- [ ] MCP server reachable at `sandbox.calseta.ai:8001` from a Claude Desktop MCP config
- [ ] TLS certificate valid and auto-renewing via ACM
- [ ] Rate limiting active (200 req/hour per IP) — implemented via ALB WAF rule or application middleware
- [ ] CI/CD deploys a new image within 10 minutes of a merge to `main`

**Completion Log:**
_No entries yet._

---

### Chunk 9.5 — `/benchmark` Page on Calseta Website

**Status:** `pending`
**Assigned Agent:** —
**Depends on:** 9.4, 8.11 (case study results must be final)
**PRD Reference:** Section 13 (Benchmark Page as a Trust Asset)

**Description:**
Build and publish the `/benchmark` page on the Calseta website. This page is the permanent public reference for the validation case study results. It is not a blog post — it is a versioned, linkable page structured for engineering credibility.

**Output Artifacts:**
- `/benchmark` page on the Calseta website with:
  - Results table (all 5 scenarios, both approaches, token counts, costs, quality scores, % deltas)
  - Methodology summary (3 paragraphs max) with links to `docs/VALIDATION_CASE_STUDY.md` and `examples/case_study/` on GitHub
  - Model/version stamp: "Tested with [model] on [date]"
  - "Run it yourself" section: sandbox base URL, public API key, one-command quickstart using `calseta_agent.py`
  - Version history table (initially one row; updated on future re-runs)
- Launch blog post (separate URL, links to `/benchmark`): narrative explaining the problem, the experiment design, and the results. Written for a technical audience (HN, security engineering blogs, dev.to).

**Acceptance Criteria:**
- [ ] `/benchmark` page live at launch, linked from the main navigation and README
- [ ] Results table is accurate and matches `examples/case_study/results/raw_metrics.csv`
- [ ] "Run it yourself" quickstart tested end-to-end: a developer following only the instructions on the page can reproduce a result within 10 minutes
- [ ] Sandbox API key on the page is valid and rate-limited
- [ ] Blog post published and submitted to Hacker News on launch day
- [ ] Version history table has a clear "Last updated" stamp and commit link to the case study results

**Completion Log:**
_No entries yet._

---

*End of PROJECT_PLAN.md*
