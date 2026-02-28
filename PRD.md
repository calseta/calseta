# Calseta AI — Product Requirements Document
**Version:** 1.0  
**Status:** Final Draft — Pre-Implementation  
**Last Updated:** February 2026  

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Vision and Positioning](#3-vision-and-positioning)
4. [Target User](#4-target-user)
5. [Core Philosophy](#5-core-philosophy)
6. [System Architecture Overview](#6-system-architecture-overview)
7. [Feature Specifications](#7-feature-specifications)
8. [Data Model](#8-data-model)
9. [Integration Catalog v1](#9-integration-catalog-v1)
10. [Non-Functional Requirements](#10-non-functional-requirements)
11. [Out of Scope for v1](#11-out-of-scope-for-v1)
12. [Roadmap Post-v1](#12-roadmap-post-v1)
13. [Open Source Strategy](#13-open-source-strategy)
14. [Success Criteria](#14-success-criteria)
15. [Validation Case Study](#15-validation-case-study)

---

## 1. Executive Summary

Calseta AI is an open-source, single-tenant, self-hostable SOC data platform built specifically for AI agent consumption. It ingests security alerts from multiple sources, normalizes them to a clean agent-native schema (`CalsetaAlert`), enriches them with threat intelligence, and exposes the resulting structured, context-rich data via a REST API and MCP server so that customer-owned AI agents can investigate and respond to security events effectively.

Calseta AI is not an AI SOC product. It does not build, host, or run AI agents. It is the data infrastructure layer that makes customer-built agents fast, accurate, and cost-efficient — eliminating the token waste and integration burden that currently prevents security teams from operationalizing AI at scale.

The platform is released as open-source under Apache 2.0. Calseta the company offers a hosted, managed version with multi-tenancy, SLAs, and enterprise features on top of this foundation.

---

## 2. Problem Statement

Security teams building AI agents for security investigation and response consistently hit the same set of problems:

**Context gap.** Agents lack access to organizational context — detection rule documentation, historical alert dispositions, incident response runbooks, SOPs, and workflow inventory. Without this, agents produce generic analysis that doesn't reflect the organization's environment, stack, or procedures.

**Integration burden.** To investigate a single alert, an agent must call 5+ external APIs (SIEM, EDR, threat intel, identity provider, ticketing). Each integration requires custom code, authentication management, error handling, and maintenance. This is expensive to build and fragile to maintain.

**Token cost and latency.** Raw API responses are verbose and unstructured. Stuffing them into agent context windows is expensive and degrades reasoning quality. Pre-normalized, pre-enriched data dramatically reduces token consumption and improves agent output.

**No runtime infrastructure.** Customer-built agents typically run on a developer's laptop or a basic VM — no multi-user access, no audit trail, no structured way for agents to write findings back to a shared system.

**Deterministic operations done non-deterministically.** Tasks like IOC enrichment, alert normalization, and workflow execution are deterministic by nature — they should never consume LLM tokens. Today, agents often perform these tasks themselves because no purpose-built infrastructure handles them.

Calseta AI solves all of these problems. It handles the deterministic work, provides the organizational context, and exposes everything through a clean API surface so agents can focus on reasoning.

---

## 3. Vision and Positioning

**Positioning statement:**
> Calseta AI is the data layer for your security AI agents. Ingest alerts from any source, enrich them automatically, add your detection documentation and runbooks, and your agents get everything they need in a single enriched payload — no custom integrations, no wasted tokens, no black boxes.

**What Calseta AI is:**
- A security alert ingestion, normalization, and enrichment pipeline
- An organizational knowledge store (detection rules, runbooks, IR plans, SOPs, workflows)
- An API and MCP server purpose-built for AI agent consumption
- A Python-based workflow execution engine with an AI-first authoring interface
- A workflow catalog that gives agents the context to decide what automations are appropriate
- An open-source foundation that security engineers can understand, extend, and trust

**What Calseta AI is not:**
- An AI SOC product (we do not build or run agents)
- A SIEM (we do not store raw logs or provide detection/query capabilities)
- A visual playbook editor or traditional SOAR UI
- A multi-tenant SaaS product (single-tenant, self-hosted)

**Counter-positioning:**
AI SOC products are black boxes — you outsource the AI to them. Calseta AI is for teams who want control: their own agents, their own models, their own logic, running against their own data. It is the infrastructure that makes that possible without requiring a dedicated platform engineering team to build it from scratch.

**The workflow engine:**
Teams without an existing SOAR get a Python-based automation engine out of the box — write a workflow function, describe what it does, and the platform runs it when an agent decides it's appropriate. Teams that already have Splunk SOAR, Tines, or any other automation platform don't replace it — they write a thin Python wrapper that triggers their existing playbooks from Calseta's execution context. Either way, the agent's job is the same: reason about the enriched alert, consult the workflow catalog to understand what automations are available, and decide what to do. Calseta handles execution. The agent handles judgment.

---

## 4. Target User

**Primary segment — Digital Native organizations (50–500 employees):**
- SaaS, fintech, high-tech companies where software is core to the business
- Small or no dedicated security operations team
- Staff responsible for responding to security alerts with engineering skills
- Production-ready or actively experimenting with agentic workflows in other business areas
- Titles: CTO, Cloud Engineer, IT Manager, Software Development Manager

**Secondary segment — Security-forward organizations (500–2000 employees):**
- Dedicated security engineering or small SOC team
- Active interest in building internal AI tooling for security
- Frustration with black-box AI SOC vendors
- Titles: CISO, Head of Security, Security Engineer, Detection Engineer

**The builder persona (both segments):**
The target user is technical enough to clone a repo, run Docker Compose, and write a Python script that calls an API. They are not necessarily a security expert by title, but they are the person in the organization responsible for responding to security alerts. They want control over their AI tooling and have the skills to exercise that control.

---

## 5. Core Philosophy

These principles should inform every implementation decision:

**Deterministic operations stay deterministic.** Enrichment, normalization, workflow execution, and metric calculation never consume LLM tokens. These operations run in the platform, not in the agent.

**Token optimization is a first-class concern.** Every API response and MCP resource is designed to give agents exactly what they need with minimal noise. Structured, concise, well-labeled data. Not raw JSON dumps from upstream APIs.

**AI-readable documentation is a feature.** Every entity in the system — detection rules, workflows, context documents, enrichment providers — has a documentation field. This documentation is surfaced through the API and MCP server so agents can reason about what tools and context are available.

**Framework agnosticism.** The REST API and MCP server work equally well with LangChain, LangGraph, raw Claude API, CrewAI, n8n, or a Slack slash command. No agent framework is privileged.

**Open by default.** The platform is designed to be understood, extended, and contributed to. LLM-friendly documentation in the repo. Clear extension points with well-documented interfaces. A community integration catalog.

**Self-hostable without pain.** Single Docker Compose command to run locally. Minimal external dependencies in v1. A security engineer should be able to deploy this in their environment in under an hour.

---

### Engineering & Code Quality Philosophy

These principles govern how the codebase is written. They exist so that any engineer — including a community contributor reading the code for the first time — can navigate the codebase, understand where to make a change, and trust that their change won't break something else. Good examples in the codebase teach these patterns better than any document.

**Layered architecture — strict separation of concerns.** Every request travels through a defined path and no layer reaches past its neighbor:

```
HTTP Request
    │
    ▼
Route Handler  (app/api/v1/)        — parse request, validate input, return response envelope
    │
    ▼
Service Layer  (app/services/)      — business logic, orchestration, no HTTP concepts
    │
    ├──▶ Repository Layer (app/repositories/)  — all DB reads/writes, no business logic
    │
    ├──▶ Integration Layer (app/integrations/) — external APIs via plugin interfaces
    │
    └──▶ Task Queue (app/queue/)               — enqueue async work, never execute inline
```

Route handlers never import SQLAlchemy models directly. Services never construct HTTP responses. Repositories never call external APIs. This separation means a junior engineer can locate any bug in under two minutes: wrong data returned → service or repository; wrong HTTP shape → route handler; enrichment failing → integration.

**Dependency injection everywhere.** Every dependency (DB session, queue backend, auth context, settings) is injected via FastAPI's DI system. Nothing is a module-level global. This makes every function's dependencies visible from its signature and every component trivially testable in isolation.

**Don't Repeat Yourself (DRY) — one source of truth.** Shared logic lives in one place and is called, not copied:
- Pagination parsing: one `PaginationParams` dependency
- Error formatting: one `CalsetaException` base and one global handler
- Auth failure logging: one `log_auth_failure()` function in `app/auth/audit.py`
- Response envelope shaping: one `DataResponse[T]` / `PaginatedResponse[T]` schema

If you find yourself writing the same logic in two places, extract it. The rule of three: write it once, write it twice, extract it on the third.

**Ports and adapters for all integrations.** External systems are accessed only through abstract base classes (`AlertSourceBase`, `EnrichmentProviderBase`, `TaskQueueBase`). Core business logic never imports a concrete adapter. This is what makes the plugin system work and what makes tests fast — mock the interface, not the network.

**Explicit over implicit.** No magic. No hidden global state. No monkeypatching. If a function needs something, it receives it as a parameter. If behavior is configurable, the config key is documented in `.env.example`. The goal: a new contributor should be able to understand any function by reading only that function and its type signatures.

**Tests as documentation.** Unit tests for services and repositories describe the expected behavior of the system. Integration tests use a real Postgres instance (no mocking the DB). Test fixture files in `tests/fixtures/` are realistic payloads that serve as living examples of what each source integration receives.

**Component-level LLM context documentation is a shipping requirement.** Every major component ships a `CONTEXT.md` file alongside its source code. This is not a high-level README — it is a machine-readable, LLM-optimized operational guide for that component: its responsibilities, interfaces, key design decisions, extension patterns, common failure modes, and pointers to the tests that describe its behavior. These files serve two purposes: they let human contributors understand a component in minutes rather than hours, and they enable autonomous AI agent workflows where an agent can understand and modify a component without reading the entire codebase. See Section 12 (v4.0 roadmap) for the long-term vision this enables.

Required `CONTEXT.md` locations:

| Path | Covers |
|---|---|
| `app/integrations/sources/CONTEXT.md` | Alert source plugin system: base class contract, normalization patterns, indicator extraction, testing fixtures |
| `app/integrations/enrichment/CONTEXT.md` | Enrichment provider system: base class contract, no-raise rule, caching, TTL, `is_configured()` pattern |
| `app/workflows/CONTEXT.md` | Workflow engine: sandbox, AST import validation, WorkflowContext fields, execution lifecycle, retry behavior |
| `app/queue/CONTEXT.md` | Task queue abstraction: TaskQueueBase interface, backend selection, idempotency requirements, queue names |
| `app/mcp/CONTEXT.md` | MCP server adapter: resources, tools, how it maps to the REST API, auth, extension patterns |
| `app/auth/CONTEXT.md` | Auth layer: API key format, bcrypt storage, scope enforcement, BetterAuth-ready architecture |
| `app/services/CONTEXT.md` | Service layer conventions: what belongs here vs. repository vs. route handler, orchestration patterns |

Each `CONTEXT.md` is written for an LLM reader first, human second. Tone: precise, concrete, no filler. Code examples over prose wherever behavior needs illustration.

---

## 6. System Architecture Overview

### Process Architecture

Two long-running processes, shipped in the same repository, started together via Docker Compose:

```
┌──────────────────────────────────────┐   ┌──────────────────────────────┐
│         FastAPI Server               │   │        MCP Server            │
│         Port 8000                    │   │        Port 8001             │
│                                      │   │                              │
│  POST /v1/ingest/{source}            │   │  Resources: alerts,          │
│  REST API (/v1/...)                  │   │  detection rules, workflows, │
│  Enqueues async tasks                │   │  context docs, metrics       │
│  Metrics computation                 │   │                              │
│                                      │   │  Tools: post finding,        │
│                                      │   │  update alert, run workflow, │
│                                      │   │  trigger enrichment          │
└──────────────┬───────────────────────┘   └──────────────┬───────────────┘
               │                                           │
               └─────────────────┬─────────────────────────┘
                                 │
                  ┌──────────────▼──────────────┐
                  │          PostgreSQL          │
                  │          Port 5432           │
                  │   (also task queue store)    │
                  └──────────────┬──────────────┘
                                 │
                  ┌──────────────▼──────────────┐
                  │       Worker Process         │
                  │                              │
                  │  Enrichment pipeline         │
                  │  Agent webhook dispatch      │
                  │  Workflow execution          │
                  │  Alert trigger evaluation    │
                  └─────────────────────────────┘
```

### Core Data Flow

```
Alert Source (Elastic / Sentinel / Splunk / Generic Webhook)
    │
    ▼
Ingestion Layer (FastAPI — synchronous, fast)
    • Source provider validates and normalizes payload to CalsetaAlert
    • Detection rule auto-created or associated
    • Indicators extracted from alert
    • Alert stored (status: pending_enrichment)
    • Enrichment task enqueued to durable task queue → 202 Accepted
    │
    ▼
Task Queue (PostgreSQL via procrastinate, or pluggable backend)
    • Tasks are durable — survive server restarts and crashes
    │
    ▼
Worker Process (long-running, consumes from task queue)
    │
    ├─► Enrichment Engine
    │       • For each indicator: run all configured providers in parallel
    │       • Cache results with provider-specific TTLs
    │       • Aggregate enrichment results onto alert record
    │       • Alert status: enriched
    │       • Trigger evaluation task enqueued
    │
    └─► Agent Trigger Evaluation
            • Check alert against all active agent registrations
            • For matching agents: dispatch webhook with enriched payload
            • Workflow execution tasks enqueued on agent request
    │
    ▼
REST API / MCP Server
    • Agents query alert details, detection rule docs, context docs
    • Agents post findings, update alert status
    • Agents discover and execute workflows
```

### Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Web framework | FastAPI |
| Validation | Pydantic v2 |
| Database | PostgreSQL 15+ |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| Task queue | Task queue abstraction layer (default: procrastinate + PostgreSQL) |
| Caching | In-memory with TTL (v1), Redis-ready interface |
| MCP server | Anthropic mcp Python SDK |
| HTTP client | httpx async |
| Auth | API keys (BetterAuth-ready architecture) |
| Testing | pytest + pytest-asyncio |
| Containerization | Docker + Docker Compose |
| Linting | ruff |
| Type checking | mypy |
| Logging | structlog (structured JSON to stdout) |
| CI/CD | GitHub Actions |
| Container registry | GitHub Container Registry (GHCR) |

### Database Strategy

PostgreSQL 15+ is the **only supported database** and this is intentional. The platform uses Postgres-specific features that cannot be abstracted away:
- `JSONB` and `TEXT[]` column types for alert and enrichment data
- `gen_random_uuid()` via the `pgcrypto` extension for UUID generation
- `procrastinate` task queue uses PostgreSQL `LISTEN/NOTIFY` and a Postgres-native job table — it cannot run on any other database engine

**What is abstracted:** The database connection is a single `DATABASE_URL` environment variable. Any PostgreSQL 15+ instance works — Docker Compose (local/self-hosted), Amazon RDS for PostgreSQL, Azure Database for PostgreSQL Flexible Server, Google Cloud SQL for PostgreSQL, or any other managed Postgres service. Swapping providers requires only a DSN change; no code changes.

**Required Postgres extensions:**
- `pgcrypto` — for `gen_random_uuid()` (UUID default values on all tables)
- No other extensions required

**Migrations:** Alembic manages all schema changes. `alembic upgrade head` is the only step needed to initialize or update a schema on any Postgres instance. All migrations are reversible (`alembic downgrade`).

**Local development:** Docker Compose provides a `postgres:15-alpine` container on port 5432. Data is persisted in a named Docker volume (`postgres_data`). The volume is gitignored.

**Production:** Use any managed PostgreSQL 15+ service. The Terraform modules (v3.1 roadmap) provision RDS (AWS) and Azure Database for PostgreSQL (Azure) and wire `DATABASE_URL` automatically.

---

## 7. Feature Specifications

---

### 7.1 Alert Source Integration System

#### Purpose
Ingest security alerts from multiple source systems, normalize them to the Calseta agent-native schema (`CalsetaAlert`), extract indicators, and associate detection rules — without requiring code changes to the core platform when a new source is added.

#### Ingestion Patterns

**Pattern 1: Push (Webhook)**
Source systems that support outbound webhooks send alerts to Calseta AI when triggered.

- Endpoint: `POST /v1/ingest/{source_name}`
- `source_name` maps to a configured source integration (e.g., `elastic`, `sentinel`, `splunk`)
- Each source integration validates the payload shape and normalizes to `CalsetaAlert`
- Returns `202 Accepted` immediately; processing is async

**Pattern 2: Generic Alert Webhook**
For sources that don't have a native integration, or for technically sophisticated users who want direct control.

- Endpoint: `POST /v1/alerts`
- Payload must conform to the `CalsetaAlert` schema
- No additional normalization required — stored directly
- This is the "escape hatch" and the integration target for custom scripts

**Pattern 3: Pull (Polling) — Roadmap**
Calseta AI polls the source system's API on a configurable interval. Not in v1 scope. Architecture must not preclude this being added later.

#### Source Integration Plugin System

Each alert source is a Python class implementing `AlertSourceBase`:

```python
class AlertSourceBase(ABC):
    source_name: str        # "elastic", "sentinel", "splunk"
    display_name: str       # "Elastic Security"

    @abstractmethod
    def validate_payload(self, raw: dict) -> bool:
        """Return False to reject with 400."""

    @abstractmethod
    def normalize(self, raw: dict) -> CalsetaAlert:
        """Transform raw payload to the Calseta agent-native schema.
        Source-specific fields that don't map are preserved in raw_payload by the caller."""

    @abstractmethod
    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]:
        """Extract IOCs: ip, domain, hash_md5, hash_sha1, hash_sha256, url, email, account.
        This is Pass 1 of the three-pass extraction pipeline. See Section 7.12 for the full
        pipeline including normalized field mappings (Pass 2) and custom field mappings (Pass 3)."""

    def extract_detection_rule_ref(self, raw: dict) -> str | None:
        """Optional. Return source rule ID for auto-association."""

    def verify_webhook_signature(self, headers: dict[str, str], raw_body: bytes) -> bool:
        """Optional. Verify the request originated from the legitimate source system.
        Called by the ingest route BEFORE validate_payload — rejection is immediate with 401;
        no payload parsing occurs on failure.
        Default implementation returns True and emits a structured log warning that
        signature verification is not implemented for this source. Override to enforce.
        Return False to reject with 401 INVALID_SIGNATURE."""
```

#### v1 Source Integrations
- Microsoft Sentinel
- Elastic Security
- Splunk
- Generic alert webhook (`POST /v1/alerts`)

#### Detection Rule Auto-Association
On every alert ingestion:
1. Extract detection rule reference from source payload
2. Check if a detection rule with that reference exists
3. If yes: associate alert with existing rule
4. If no: create a new detection rule record with extracted metadata, leave documentation fields empty

#### Agent-Native Schema
All alerts are normalized to the `CalsetaAlert` schema — clean, human-readable field names designed for AI agent consumption. Source-specific fields that don't map to `CalsetaAlert` are preserved in `raw_payload` by the ingestion service. `CalsetaAlert` is not OCSF: OCSF is designed for SIEM-to-SIEM interoperability (numeric class IDs, epoch timestamps, `unmapped` buckets). The agent-native schema prioritizes readable labels, enrichment as first-class data, and minimal token cost.

---

### 7.2 Enrichment Engine

#### Purpose
Automatically enrich threat indicators extracted from alerts with external threat intelligence, and support on-demand enrichment for ad-hoc analysis (e.g., from a Slack SOC bot or agent during investigation).

#### Enrichment Modes

**Mode 1: Automatic (on alert ingestion)**
When an alert is ingested and its indicators are extracted, the enrichment pipeline runs as an async background task. The alert is immediately available via the API with `is_enriched: false`. Enrichment results are written back as they complete.

**Mode 2: On-demand (API-triggered)**
Enrichment can be triggered for any indicator value at any time:

```
POST /v1/enrichments
{
  "type": "ip",
  "value": "1.2.3.4"
}
```

Supports ad-hoc use cases: Slack SOC bot commands, agent-initiated enrichment during investigation, manual analyst lookups. Results are cached so subsequent requests for the same indicator are fast.

#### Enrichment Provider Plugin System

Each enrichment provider implements `EnrichmentProviderBase`:

```python
class EnrichmentProviderBase(ABC):
    provider_name: str
    display_name: str
    supported_types: list[IndicatorType]
    cache_ttl_seconds: int

    @abstractmethod
    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
        """Never raise exceptions — catch all errors and return success=False."""

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if valid credentials are present."""
```

`EnrichmentResult` carries both the full provider response and the enrichment outcome:

```python
@dataclass
class EnrichmentResult:
    success: bool
    provider_name: str
    raw_response: dict      # full provider API response — stored for auditing and re-extraction
    error: str | None = None
```

The provider plugin is responsible only for making the API call and returning `EnrichmentResult`. It does **not** decide what fields to surface. That is the job of the enrichment field extraction configuration described in the next section.

#### Enrichment Response Field Extraction

> **Design note (carried forward from Calseta v1):** One of the most impactful features of the original platform was the ability to configure, per provider, exactly which fields from the raw enrichment response to extract and how to name them in the stored result. This approach must be preserved and made a first-class citizen of the data model. Before finalizing the enrichment engine implementation, review how this was done in v1 and carry the best parts forward. The design decisions here directly affect token efficiency and agent reasoning quality.

##### Why This Matters

Enrichment providers return far more data than an agent needs. A VirusTotal IP lookup returns dozens of fields — file submission history, crowdsourced comments, category tags, sandbox verdicts, certificate details. Dumping the entire raw response into an alert's enrichment payload wastes agent context window and degrades reasoning quality. The field extraction configuration is what converts a noisy provider response into a precise, labeled enrichment record that agents can reason about efficiently.

The same mechanism also normalizes data across providers. AbuseIPDB returns `abuseConfidenceScore`; VirusTotal returns `last_analysis_stats.malicious`. With extraction configuration, both resolve to consistent, labeled keys that an agent can compare across indicators without parsing different schemas.

##### How It Works

After `enrich()` returns a successful `EnrichmentResult`, the enrichment engine service applies the configured field extractions for that provider and indicator type combination. The extraction uses dot-notation paths against `raw_response` and produces a flat, labeled dictionary — the **extracted subset** — which is what gets stored in the active `enrichment_results` record and surfaced to agents.

Both the `extracted` subset and the original `raw_response` are persisted. Storing the raw response means new field extractions added later can be applied to existing enrichment records without re-fetching from the external API.

**Storage structure in `indicators.enrichment_results` JSONB:**
```json
{
  "virustotal": {
    "success": true,
    "extracted": {
      "malicious_votes": 15,
      "suspicious_votes": 2,
      "reputation_score": -85,
      "country": "RU",
      "asn_owner": "DigitalOcean LLC"
    },
    "raw": { "...full VirusTotal API response..." },
    "enriched_at": "2026-02-27T14:32:00Z"
  },
  "abuseipdb": {
    "success": true,
    "extracted": {
      "abuse_confidence_score": 92,
      "country_code": "RU",
      "total_reports": 847,
      "is_public": true
    },
    "raw": { "...full AbuseIPDB API response..." },
    "enriched_at": "2026-02-27T14:32:01Z"
  }
}
```

Agents and the MCP server receive only the `extracted` values. The `raw` sub-object is accessible via the API for debugging, auditing, and re-extraction — but is excluded from agent-facing payloads by default to protect token budget.

##### Enrichment Field Extraction Configuration

Field extractions are stored in the `enrichment_field_extractions` table. System defaults are seeded at startup with `is_system = true`. Users can add custom extractions, disable system ones, or override paths without modifying plugin code.

Each extraction entry defines:
- `provider_name` — which provider this applies to (`virustotal`, `abuseipdb`, `okta`, `entra`)
- `indicator_type` — which indicator type it applies to (`ip`, `domain`, `hash_md5`, `account`, etc.)
- `source_path` — dot-notation path into `raw_response` (e.g., `data.attributes.last_analysis_stats.malicious`)
- `target_key` — the key name in the `extracted` dict (e.g., `malicious_votes`)
- `value_type` — `string`, `integer`, `float`, `boolean`, `json` — for type coercion on extraction
- `is_system` — `true` for startup-seeded defaults; `false` for user-defined
- `is_active` — whether this extraction runs
- `description` — what this field represents, written for LLM consumption

**Example system-seeded extractions for v1 providers:**

| Provider | Indicator Type | Source Path | Target Key | Value Type |
|---|---|---|---|---|
| `virustotal` | `ip` | `data.attributes.last_analysis_stats.malicious` | `malicious_votes` | `integer` |
| `virustotal` | `ip` | `data.attributes.reputation` | `reputation_score` | `integer` |
| `virustotal` | `ip` | `data.attributes.country` | `country` | `string` |
| `virustotal` | `ip` | `data.attributes.as_owner` | `asn_owner` | `string` |
| `virustotal` | `domain` | `data.attributes.last_analysis_stats.malicious` | `malicious_votes` | `integer` |
| `virustotal` | `domain` | `data.attributes.registrar` | `registrar` | `string` |
| `virustotal` | `hash_sha256` | `data.attributes.last_analysis_stats.malicious` | `malicious_votes` | `integer` |
| `virustotal` | `hash_sha256` | `data.attributes.meaningful_name` | `file_name` | `string` |
| `virustotal` | `hash_sha256` | `data.attributes.type_description` | `file_type` | `string` |
| `abuseipdb` | `ip` | `data.abuseConfidenceScore` | `abuse_confidence_score` | `integer` |
| `abuseipdb` | `ip` | `data.countryCode` | `country_code` | `string` |
| `abuseipdb` | `ip` | `data.totalReports` | `total_reports` | `integer` |
| `abuseipdb` | `ip` | `data.isPublic` | `is_public` | `boolean` |
| `okta` | `account` | `status` | `account_status` | `string` |
| `okta` | `account` | `profile.login` | `login` | `string` |
| `okta` | `account` | `profile.department` | `department` | `string` |
| `entra` | `account` | `accountEnabled` | `account_enabled` | `boolean` |
| `entra` | `account` | `userPrincipalName` | `user_principal_name` | `string` |
| `entra` | `account` | `signInActivity.lastSignInDateTime` | `last_sign_in` | `string` |

The exact field paths for each provider must be confirmed against official API documentation before seeding — this is part of the mandatory API research step defined in Section 9.

##### Re-Extraction Against Existing Raw Responses

When a new `enrichment_field_extractions` entry is created or an existing one is re-activated, an API endpoint allows re-running extraction against already-stored raw responses — no external API call needed:

```
POST /v1/enrichment-extractions/reextract
{
  "provider_name": "virustotal",
  "indicator_type": "ip"
}
```

This enqueues a background task that iterates all indicators of that type enriched by that provider and applies the current active extraction configuration to their stored `raw_response`, updating the `extracted` sub-object in place. Useful when a new field is added to the extraction schema after enrichment has already run for many indicators.

##### Relationship to Indicator Field Mapping System

The indicator field mapping system (Section 7.12) and the enrichment field extraction system are conceptual mirrors:

| | Indicator Field Mappings (§7.12) | Enrichment Field Extractions (§7.2) |
|---|---|---|
| Direction | Alert payload **→** indicator types | Provider response **→** enrichment record |
| Applies to | `normalized` alert columns / `raw_payload` on ingest | `raw_response` from enrichment API |
| Output | `indicators` table rows | `extracted` sub-object in `enrichment_results` |
| Purpose | Extract IOCs from alerts | Normalize provider data for agents |

Both share the same operational model: system-seeded defaults, user-configurable overrides, dot-notation paths, and a test endpoint for validating mappings before applying to live data.

#### Parallel Execution
All enrichment calls for a given indicator run concurrently via `asyncio.gather()`. Multiple indicators in the same alert are also processed concurrently. A single slow or failing provider does not block others.

#### Caching
Results cached in-memory with configurable TTLs. Cache key: `enrichment:{provider}:{type}:{value}`.

Default TTLs (all configurable via environment variables):

| Indicator Type | Default TTL |
|---|---|
| IP | 1 hour |
| Domain | 6 hours |
| Hash (any) | 24 hours |
| URL | 30 minutes |
| Account | 15 minutes |

#### Enrichment Provider Documentation
Each provider has a `documentation` field surfaced via MCP so agents understand what enrichment capabilities are available and what data each provider returns.

#### v1 Enrichment Providers
- **VirusTotal** — IP reputation, domain reputation, file hash analysis
- **AbuseIPDB** — IP abuse confidence score and category
- **Okta** — Account details, group membership, recent activity, MFA status
- **Microsoft Entra** — Account details, sign-in risk, group membership, conditional access

---

### 7.3 Detection Rule Management

#### Purpose
Maintain a structured library of detection rules with rich documentation that provides AI agents and human analysts with the context needed to understand what triggered an alert and how to respond.

#### Auto-Creation on Alert Ingestion
When an alert arrives referencing a detection rule (by name or source ID):
- If the rule exists: associate the alert
- If the rule does not exist: create a new rule record with available metadata, leave documentation empty

The detection rule library self-populates as alerts flow in. Users enrich it with documentation over time.

#### Detection Rule Data Model

**Structured fields (machine-readable):**
- `name`, `source_rule_id`, `source_name`, `severity`, `is_active`
- `mitre_tactics[]`, `mitre_techniques[]`, `mitre_subtechniques[]`
- `data_sources[]`, `false_positive_tags[]`
- `run_frequency`, `created_by`

**Free-form documentation (markdown):**
A single `documentation` field. Recommended template sections:

```
## Overview
## Query
## Threshold (optional)
## Alert Suppression (optional)
## Goal
## Strategy Abstract
## Blind Spots & Assumptions
## False Positives
## Validation
## Priority
## Responses
## Additional Notes
```

#### AI Consumption
Detection rule documentation is included in:
- The agent webhook payload
- The `GET /v1/alerts/{uuid}` response
- MCP resource: `calseta://detection-rules/{uuid}`
- MCP resource: `calseta://alerts/{uuid}`

---

### 7.4 Context Documentation System

#### Purpose
Allow users to upload organizational documents — runbooks, incident response plans, SOPs, playbooks — that are automatically surfaced as context when an AI agent investigates an alert.

#### Document Types
`runbook`, `ir_plan`, `sop`, `playbook`, `detection_guide`, `other`

#### Document Data Model

**Structured fields:**
- `title`, `document_type`, `is_global`, `tags[]`, `version`
- `targeting_rules` JSONB — which alerts this document applies to
- `description` — one-line summary for MCP listings

**Free-form content:**
- `content` — full markdown document text

#### Ingest Paths

`POST /v1/context-documents` accepts two content types:

1. **JSON body (default):** `Content-Type: application/json` with `content` field containing markdown text. All other metadata fields (`name`, `tags`, `targeting_rules`, etc.) supplied in the same body.

2. **File upload:** `Content-Type: multipart/form-data` with a `file` field. The platform converts the uploaded file to markdown using [markitdown](https://github.com/microsoft/markitdown) (MIT license, pure Python, no LLM required) and stores the result in `content`. The original file is not persisted. Optional metadata fields (`name`, `tags`, `targeting_rules`) may be included as additional form fields.

Supported input formats via markitdown: PDF, DOCX, PPTX, XLSX, HTML, CSV, XML, JSON, ZIP (extracts and converts contained documents), plain text, Markdown passthrough. Unsupported formats return `422 Unprocessable Entity` with a clear error message. The `content` field in the response always contains converted markdown regardless of input path.

**Dependency:** `markitdown` is a required dependency listed in `pyproject.toml`.

#### Targeting Rules
Documents can be targeted to specific alert types using a JSONB rule system:

```json
{
  "match_any": [
    { "field": "source_name", "operator": "eq", "value": "sentinel" },
    { "field": "severity", "operator": "in", "values": ["High", "Critical"] },
    { "field": "tags", "operator": "contains", "value": "lateral-movement" }
  ],
  "match_all": [
    { "field": "severity_id", "operator": "gte", "value": 4 }
  ]
}
```

`match_any` = OR logic. `match_all` = AND logic. Both can coexist.

#### Context Resolution
`GET /v1/alerts/{uuid}/context` returns:
1. All documents with `is_global: true`
2. All non-global documents whose `targeting_rules` evaluate true against the alert

Ordered: global first, then targeted by document type. This endpoint populates the `context_documents` array in agent webhook payloads.

---

### 7.5 Workflow Engine

#### Purpose
Provide a Python-based automation execution engine and an AI-readable workflow catalog. Teams without an existing SOAR use the engine to write and run automations directly in the platform. Teams with an existing SOAR onboard thin wrapper workflows that trigger their existing playbooks. In both cases, the agent's role is to consult the catalog, decide what action is appropriate given the enriched alert context, and request execution. Calseta handles the running; the agent handles the judgment.

#### Design Philosophy: AI-First Authoring

Every aspect of the workflow system is designed so that an LLM can read, understand, and generate valid workflows without human guidance:

- **One entry point, always.** Every workflow is an `async def run(ctx: WorkflowContext) -> WorkflowResult` function. The AI never has to guess the structure.
- **Fully typed context.** `WorkflowContext` exposes everything the workflow needs — indicator, alert, HTTP client, logger, secrets, integration clients — all with complete type annotations and docstrings. The AI can introspect the interface and know exactly what's available.
- **Strict import whitelist.** Workflows may only import from an explicit allowlist. This is documented in the interface spec so the AI generating code never produces an import it cannot use.
- **Documentation is executable spec.** The `documentation` field is written as instructions the AI can follow: what the workflow does, what it expects, what success and failure look like. A new LLM instance reading the catalog should understand every workflow without additional context.

#### The `WorkflowContext` Interface

This is the complete contract an AI must follow when writing a workflow. It is the only object passed to `run()`. Nothing else is available.

```python
@dataclass
class WorkflowContext:
    # ── Trigger context ──────────────────────────────────────────────────────
    indicator: IndicatorContext | None
    # Present for indicator-type workflows. None for alert-type workflows.
    # indicator.type: IndicatorType  (ip, domain, hash_md5, account, etc.)
    # indicator.value: str

    alert: AlertContext
    # Always present.
    # alert.uuid: str
    # alert.title: str
    # alert.severity: str          ("Critical", "High", "Medium", "Low", "Informational", "Pending")
    # alert.severity_id: int       (5, 4, 3, 2, 1, 0)
    # alert.source_name: str       ("sentinel", "elastic", "splunk", etc.)
    # alert.status: str            ("Open", "Triaging", "Escalated", "Closed", "enriched", "pending_enrichment")
    # alert.occurred_at: str       (ISO 8601 timestamp when the source event occurred)
    # alert.tags: list[str]
    # alert.raw_payload: dict      (original unmodified source payload; avoid in token-constrained contexts)
    # alert.enrichment_results: dict  (keyed by provider_name → {extracted: {...}, enriched_at: "..."})

    # ── Execution tools ──────────────────────────────────────────────────────
    http: httpx.AsyncClient
    # Pre-configured async HTTP client. Timeout enforced by platform.
    # Use this for ALL external HTTP calls. Do not import httpx directly.

    log: WorkflowLogger
    # Structured logger. Methods: log.info(msg), log.warning(msg), log.error(msg)
    # All log output is captured in the WorkflowRun audit record.

    secrets: SecretsAccessor
    # secrets.get("KEY_NAME") -> str | None
    # Returns the value of the named environment variable / secret.
    # Never hardcode credentials. Always use secrets.get().

    integrations: IntegrationClients
    # Pre-built clients for configured integrations.
    # integrations.okta  -> OktaClient   (if OKTA_DOMAIN + OKTA_API_TOKEN are set)
    # integrations.entra -> EntraClient  (if Entra credentials are set)
    # Check availability: integrations.okta is not None
```

#### The `WorkflowResult` Interface

```python
@dataclass
class WorkflowResult:
    success: bool
    message: str           # Human-readable summary logged to the audit record
    data: dict = {}        # Optional structured output (shown in findings, MCP responses)

    @classmethod
    def ok(cls, message: str, data: dict = {}) -> "WorkflowResult":
        """Return this when the automation completed successfully."""

    @classmethod
    def fail(cls, message: str, data: dict = {}) -> "WorkflowResult":
        """Return this when the automation failed. Do not raise exceptions — return fail()."""
```

**Contract:** `run()` must always return a `WorkflowResult`. It must never raise an unhandled exception. All errors must be caught and returned as `WorkflowResult.fail(...)`.

#### Allowed Imports

Workflows may only use the following. Any other import will be rejected at save time with a clear validation error:

```
httpx           — via ctx.http only (do not import directly)
json            — standard library
datetime        — standard library
re              — standard library
typing          — standard library
dataclasses     — standard library
calseta.workflows  — WorkflowContext, WorkflowResult, IndicatorContext, AlertContext
```

The platform validates imports at save time by parsing the AST of the workflow code. A workflow referencing `os`, `subprocess`, `importlib`, `__builtins__`, or any filesystem operation will be rejected before it is ever executed.

#### Example Workflows

These examples are the primary training material for an LLM generating new workflows. They are committed to `docs/workflows/examples/` and surfaced via the API.

**Example 1 — Indicator workflow, pre-built integration client:**
```python
async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Revoke all active Okta sessions for a compromised account."""
    if ctx.integrations.okta is None:
        return WorkflowResult.fail("Okta integration not configured")

    user_login = ctx.indicator.value
    ctx.log.info(f"Revoking Okta sessions for {user_login}")

    result = await ctx.integrations.okta.revoke_sessions(user_login)
    if result.success:
        return WorkflowResult.ok(
            f"All Okta sessions revoked for {user_login}",
            data={"sessions_cleared": result.count}
        )
    return WorkflowResult.fail(f"Failed to revoke sessions: {result.error}")
```

**Example 2 — Alert workflow, external HTTP call:**
```python
async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Create a Jira ticket for a high-severity alert."""
    jira_url = ctx.secrets.get("JIRA_URL")
    jira_token = ctx.secrets.get("JIRA_API_TOKEN")
    if not jira_url or not jira_token:
        return WorkflowResult.fail("JIRA_URL or JIRA_API_TOKEN not configured")

    response = await ctx.http.post(
        f"{jira_url}/rest/api/3/issue",
        json={
            "fields": {
                "project": {"key": "SEC"},
                "summary": f"[{ctx.alert.severity}] {ctx.alert.title}",
                "issuetype": {"name": "Task"}
            }
        },
        headers={"Authorization": f"Basic {jira_token}",
                 "Content-Type": "application/json"}
    )
    if response.status_code == 201:
        ticket_key = response.json()["key"]
        return WorkflowResult.ok(f"Jira ticket created: {ticket_key}",
                                  data={"ticket_key": ticket_key})
    return WorkflowResult.fail(f"Jira API error {response.status_code}: {response.text}")
```

**Example 3 — SOAR bridge (team with existing Splunk SOAR):**
```python
async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Trigger the Account Compromise playbook in Splunk SOAR."""
    soar_url = ctx.secrets.get("SPLUNK_SOAR_URL")
    soar_token = ctx.secrets.get("SPLUNK_SOAR_TOKEN")

    response = await ctx.http.post(
        f"{soar_url}/rest/playbook_run",
        json={
            "playbook_id": ctx.secrets.get("SPLUNK_ACCOUNT_COMPROMISE_PLAYBOOK_ID"),
            "container_id": ctx.alert.uuid,
            "inputs": {"username": ctx.indicator.value,
                       "alert_severity": ctx.alert.severity}
        },
        headers={"ph-auth-token": soar_token}
    )
    if response.status_code == 200:
        return WorkflowResult.ok("Splunk SOAR playbook triggered",
                                  data={"run_id": response.json().get("playbook_run_id")})
    return WorkflowResult.fail(f"SOAR error: {response.status_code}")
```

#### Workflow Types

**Indicator Workflows** — `ctx.indicator` is populated; `ctx.alert` provides surrounding context:
- Revoke user session
- Suspend / unsuspend account
- Reset account password
- Add IP to network blocklist
- Submit file hash for sandbox analysis
- Trigger SOAR playbook with indicator as input

**Alert Workflows** — `ctx.indicator` is None; `ctx.alert` is the full enriched alert:
- Create ticket in Jira / ServiceNow
- Notify on-call via PagerDuty
- Pull related logs from SIEM
- Run threat hunting query
- Trigger SOAR playbook with alert as input

#### Workflow Data Model

**Structured fields:**
- `name`, `workflow_type` (indicator/alert), `indicator_types[]`
- `code` TEXT — the Python source; must define `async def run(ctx: WorkflowContext) -> WorkflowResult`
- `code_version` INTEGER — incremented on each code edit
- `state` TEXT — `draft`, `active`, `inactive`
- `timeout_seconds`, `retry_count`, `is_active`, `is_system` BOOLEAN, `tags[]`
- `time_saved_minutes` — per-execution estimate for metrics

**Free-form documentation (markdown) — written for LLM consumption:**
```
## Description
One paragraph. What this workflow does and when an agent should choose it.

## When to Use
Bullet list of conditions under which this workflow is appropriate.
Agents read this to decide whether to execute.

## Required Secrets
List each ctx.secrets.get("KEY") call with what the value should contain.

## Expected Outcome
What success looks like. What the WorkflowResult.data dict will contain.

## Error Cases
Known failure modes and what WorkflowResult.fail message to expect.

## Notes
Any assumptions, rate limits, or side effects the agent should know about.
```

#### AI Workflow Generation

`POST /v1/workflows/generate` accepts a natural language description and returns generated Python code ready for review and activation. The generation prompt includes:
- The full `WorkflowContext` and `WorkflowResult` interface specs (from this section)
- The allowed imports list
- All example workflows from `docs/workflows/examples/`
- The names of currently configured secrets (not values)
- The available integration client method signatures

The generated code is not saved automatically — it is returned for review and then saved via `POST /v1/workflows`.

Request:
```json
{
  "description": "When a suspicious IP is detected, add it to our CrowdStrike Custom IOC list and create a Jira ticket",
  "workflow_type": "indicator",
  "indicator_types": ["ip"]
}
```

Response:
```json
{
  "generated_code": "async def run(ctx: WorkflowContext) -> WorkflowResult:\n    ...",
  "suggested_name": "CrowdStrike IOC Block + Jira Ticket",
  "suggested_documentation": "## Description\n...",
  "warnings": ["CROWDSTRIKE_API_KEY not found in configured secrets — add it to .env before activating"]
}
```

#### Workflow Versioning

Every save to an existing workflow's code creates a new version. `code_version` increments on each edit. Previous versions are stored and can be restored. A workflow must be in `active` state to be executed by agents or appear in the catalog.

#### Workflow Testing

`POST /v1/workflows/{uuid}/test` executes the workflow in a sandboxed context:
- Provides a synthetic `WorkflowContext` built from a configurable fixture payload
- Intercepts all `ctx.http` calls and returns mock responses (no real external calls)
- Captures all `ctx.log` output
- Returns the full `WorkflowResult`, execution log, and duration

Workflows should be tested before being set to `active`. AI-generated workflows must be tested before activation.

#### Execution Security

Workflows run inside the worker process with enforced restrictions:
- **Import validation at save time** — AST-parsed; rejected before storage if disallowed imports found
- **Execution timeout** — `asyncio.wait_for` enforces `timeout_seconds` (default 30s); times out as `WorkflowResult.fail`
- **HTTP via `ctx.http` only** — all external calls go through the platform's httpx client with configured timeouts and request logging
- **No filesystem, no subprocess, no shell** — any attempt fails at import validation
- **Secrets by name only** — secret values never appear in code, logs, or audit records

#### AI Discovery and Execution

**MCP resource:** `calseta://workflows` — full catalog with documentation so agents can reason about available automations before deciding to execute.

**MCP tool:** `execute_workflow` — execute a workflow from within an agent session.

**REST:** `POST /v1/workflows/{uuid}/execute` — ad-hoc execution from Slack commands, scripts, or any HTTP client.

Key flow: agent receives enriched alert → reads `calseta://workflows` → determines "Revoke Okta Sessions" is appropriate → calls `execute_workflow` with `reason` and `confidence` → platform creates approval request and notifies designated channel → human approves via Slack or Teams → workflow runs → `WorkflowResult` stored → agent retrieves result via `GET /v1/workflow-approvals/{uuid}` and posts finding as evidence.

---

#### Human-in-the-Loop Workflow Approval

##### Purpose

Agents can identify appropriate workflows and propose their execution, but they must never execute destructive automations autonomously. The approval gate sits between an agent's execution request and the workflow actually running.

**Core principle: agents propose, humans approve, Calseta executes.**

##### When Approval Applies

Approval is required when:
- `trigger_source` is `agent` (MCP tool call or authenticated API call from an agent session)
- The workflow has `requires_approval = true` (the default for all workflows)

Approval is **not** required when:
- The request is a sandboxed test execution (`POST /v1/workflows/{uuid}/test`)
- `requires_approval = false` is explicitly set on the workflow record (opt-out — use only for low-risk, fully reversible automations)
- A human calls `POST /v1/workflows/{uuid}/execute` directly via REST (not an agent trigger)

##### Execution Flow

```
Agent calls execute_workflow (MCP tool or REST)
         │
         ▼
  requires_approval?
         │ Yes                    No
         │                        └──────────── Execute immediately → WorkflowResult
         ▼
Create workflow_approval_request (status: pending)
Enqueue approval notification task
Return 202: { "status": "pending_approval", "approval_request_uuid": "..." }
         │
         ▼
ApprovalNotifier sends message to configured channel
(Slack Block Kit or Teams Adaptive Card)
         │
    ┌────┴────────────────┐
    ▼                     ▼
 Approved           Rejected / Timed Out
    │                     │
    ▼                     ▼
Enqueue workflow      Mark status =
execution task        rejected / expired
    │
    ▼
WorkflowResult stored → approval_request.execution_result updated
Optional: result follow-up notification sent to same thread
```

##### `execute_workflow` — Updated Contract

The `execute_workflow` MCP tool and `POST /v1/workflows/{uuid}/execute` REST endpoint accept two additional required fields for agent-triggered calls:

```json
{
  "workflow_uuid": "...",
  "indicator_value": "jorge.castro@company.com",
  "indicator_type": "account",
  "reason": "This account shows 47 failed MFA attempts from 3 countries in 2 hours. VirusTotal and AbuseIPDB flag the source IP as malicious. Revoking sessions prevents further access while investigation continues.",
  "confidence": 0.94
}
```

- `reason` (string, required for agent-triggered executions) — the agent's natural language explanation for why this workflow should run. Shown verbatim in the approval notification.
- `confidence` (float 0.0–1.0, required for agent-triggered executions) — the agent's self-assessed confidence in its recommendation. Displayed as a percentage in the approval notification.

**When approval is required** — response is `202 Accepted`:
```json
{
  "status": "pending_approval",
  "approval_request_uuid": "a7f3c2e1-...",
  "message": "Workflow execution is pending human approval. The approver has been notified.",
  "expires_at": "2026-02-27T16:45:00Z"
}
```

**When approval is not required** — response is the `WorkflowResult` as before.

Agents should treat a `pending_approval` response as a successful request and can continue other investigation steps. They may poll `GET /v1/workflow-approvals/{uuid}` to retrieve the final `WorkflowResult` once a decision has been made.

##### Approval Notifier Abstraction

Notification delivery is handled by a pluggable `ApprovalNotifierBase`. The workflow engine imports only the abstract base — the concrete implementation is configured via environment variable and injected at startup. This ensures Slack and Teams are equally supported and neither is privileged in the core logic.

```python
class ApprovalNotifierBase(ABC):
    notifier_name: str  # "slack", "teams", "none"

    async def send_approval_request(self, request: ApprovalRequest) -> str:
        """
        Send the approval message to the configured channel.
        Returns an external message ID (used for result follow-up threading).
        Must never raise — catch all errors, log them, return empty string on failure.
        """

    async def send_result_notification(
        self, request: ApprovalRequest, approved: bool, responder: str | None
    ) -> None:
        """
        Send a follow-up to the same thread after the workflow executes or is rejected.
        Optional — implementations may no-op this.
        Must never raise.
        """

    def is_configured(self) -> bool:
        """Return True if required credentials and channel config are present."""
```

`ApprovalRequest` carries all context needed to render a notification:

```python
@dataclass
class ApprovalRequest:
    uuid: str
    workflow: WorkflowSummary        # name, description, risk_level, documentation
    alert: AlertContext              # title, severity, source, uuid
    indicator: IndicatorContext | None
    reason: str                      # agent's stated reason
    confidence: float                # 0.0–1.0
    requested_at: datetime
    expires_at: datetime
    channel: str                     # resolved channel (workflow-level or global fallback)
    trigger_agent_key_prefix: str    # which API key made the request
```

**v1 implementations:**
- `SlackApprovalNotifier` — Slack Block Kit interactive messages
- `TeamsApprovalNotifier` — Microsoft Teams Adaptive Cards
- `NullApprovalNotifier` — no-op; used when `APPROVAL_NOTIFIER=none`. Approval requests are still created and can be approved or rejected via REST.

##### Slack Notification (v1)

Requires a Slack app with `chat:write` scope and an interactive components endpoint pointing to `POST /v1/approvals/callback/slack`.

**Block Kit message layout:**

```
🔔  Workflow Approval Requested

Alert       Account Compromise — High Severity
Source      Microsoft Sentinel  |  ID: abc1…def9
Workflow    Okta — Revoke All Sessions
            Terminate all active sessions for the compromised account.
Target      jorge.castro@company.com  (account)
Risk        High  |  Confidence: 94%

Agent Reasoning
"This account shows 47 failed MFA attempts from 3 countries in 2 hours.
VirusTotal and AbuseIPDB flag the source IP as malicious. Revoking sessions
prevents further access while investigation continues."

Requested   2:45 PM UTC by Agent (key: cai_abc1…)
Expires     3:45 PM UTC (1 hour)

[ ✅  Approve ]    [ ❌  Reject ]
```

Approve/Reject button payloads embed the `approval_request_uuid` — never a sequential ID. The callback endpoint verifies the `X-Slack-Signature` header using `hmac.compare_digest` before processing any payload.

**Result follow-up** (posted to the same thread after execution):
```
✅  Approved and Executed
Okta — Revoke All Sessions: All sessions revoked for jorge.castro@company.com
Approved by @jane.doe at 2:52 PM UTC  |  Duration: 1.2s
```

##### Microsoft Teams Notification (v1)

Uses Teams Adaptive Cards delivered via a configured incoming webhook URL or Bot Framework bot. Content mirrors the Slack message.

Adaptive Card includes:
- Alert and workflow context `TextBlock` and `FactSet` elements
- Agent reasoning `TextBlock`
- Risk level, confidence, and expiry `FactSet`
- `Action.Submit` actions: Approve, Reject

Teams action payloads are delivered to `POST /v1/approvals/callback/teams`. The callback verifies the Bot Framework JWT before processing.

Two deployment modes are supported:
- **Incoming webhook** (simpler) — set `TEAMS_WEBHOOK_URL`. Supports send-only; approval responses are collected via a separate mechanism or via REST fallback.
- **Bot Framework bot** (full interactive) — set `TEAMS_BOT_APP_ID` and `TEAMS_BOT_APP_PASSWORD`. Supports full Approve/Reject button interactivity.

##### Per-Workflow Approval Configuration

Four new fields on the `workflows` table control per-workflow approval behavior:

| Field | Type | Default | Description |
|---|---|---|---|
| `requires_approval` | boolean | `true` | Whether agent-triggered executions require human approval before running |
| `approval_channel` | string \| null | `null` | Notification channel (Slack channel ID or Teams channel URL); falls back to `APPROVAL_DEFAULT_CHANNEL` |
| `approval_timeout_seconds` | integer | 3600 | Seconds before a pending request auto-expires; overrides global `APPROVAL_REQUEST_TIMEOUT_SECONDS` |
| `risk_level` | string | `medium` | `low`, `medium`, `high`, `critical` — displayed prominently in the approval notification |

##### Callback Endpoints

These endpoints receive interactive button responses from Slack and Teams. They must be reachable from the messaging platform's servers (public IP or hostname required in production). Both are unauthenticated at the HTTP layer — security is enforced by platform-specific signature/JWT verification before any payload is read.

| Endpoint | Purpose | Verification |
|---|---|---|
| `POST /v1/approvals/callback/slack` | Receive Slack interactive component payloads | `X-Slack-Signature` HMAC-SHA256 (`SLACK_SIGNING_SECRET`) |
| `POST /v1/approvals/callback/teams` | Receive Teams action payloads | Bot Framework JWT |
| `POST /v1/workflow-approvals/{uuid}/approve` | Manual approval via REST | Standard API key auth (`workflows:execute` scope) |
| `POST /v1/workflow-approvals/{uuid}/reject` | Manual rejection via REST | Standard API key auth (`workflows:execute` scope) |

The REST approval endpoints serve as the fallback for organizations without Slack or Teams, and for automated testing pipelines that simulate human approvers.

##### Approval Notifier Environment Variables

| Variable | Description |
|---|---|
| `APPROVAL_NOTIFIER` | `slack`, `teams`, or `none` (default: `none`) |
| `APPROVAL_DEFAULT_CHANNEL` | Fallback channel for workflows without an explicit `approval_channel` configured |
| `APPROVAL_REQUEST_TIMEOUT_SECONDS` | Global approval window in seconds (default: `3600`); overridden per-workflow by `approval_timeout_seconds` |
| `SLACK_BOT_TOKEN` | OAuth bot token (`xoxb-…`) for sending Block Kit messages |
| `SLACK_SIGNING_SECRET` | Used to verify `X-Slack-Signature` on interactive callbacks |
| `TEAMS_WEBHOOK_URL` | Incoming webhook URL for Teams send-only mode |
| `TEAMS_BOT_APP_ID` | Bot Framework app ID (required for full interactive Teams mode) |
| `TEAMS_BOT_APP_PASSWORD` | Bot Framework app password (required for full interactive Teams mode) |

---

#### Audit Log
Every execution logged: trigger type, indicator/alert context, code version executed, log output captured from `ctx.log`, `WorkflowResult`, duration, retry count.

Every approval request lifecycle logged in `workflow_approval_requests`: creation, notifier delivery status, human decision (responder identity, timestamp), and final execution result. See Section 8 for the full schema.

---

### 7.6 Metrics and KPIs

#### Purpose
Provide quantitative SOC health data via API and MCP so AI agents can reason about operational state, prioritize work, and identify systemic issues. v1 is API-only; a dashboard is a roadmap item.

#### Alert Metrics

All support `from` and `to` time range parameters (defaults: last 30 days).

| Metric | Description |
|---|---|
| `alerts_by_status` | Count grouped by alert status |
| `alerts_by_severity` | Count grouped by severity |
| `alerts_by_source` | Count grouped by source system |
| `alerts_over_time` | Volume by day/hour |
| `false_positive_rate` | Percentage of closed alerts tagged as FP |
| `mean_time_to_enrich` | Avg time from ingestion to enrichment completion |
| `mean_time_to_detect` (MTTD) | Avg time from source detection to Calseta ingestion |
| `mean_time_to_acknowledge` (MTTA) | Avg time from ingestion to first status change out of `Open` |
| `mean_time_to_triage` (MTTT) | Avg time from ingestion to `Triaging` status |
| `mean_time_to_conclusion` (MTTC) | Avg time from ingestion to closure |
| `active_alerts_by_severity` | Open alert count by severity |
| `top_detection_rules` | Most frequently triggering rules |
| `enrichment_coverage` | Percentage of alerts with full enrichment |

#### MTTX Computation Details

All MTTX metrics return `null` when the required timestamps are unavailable. All values in seconds.

| Metric | Computation | Null condition |
|---|---|---|
| `mean_time_to_detect` (MTTD) | `avg(created_at − occurred_at)` | NULL if `occurred_at` is NULL for all alerts in window |
| `mean_time_to_acknowledge` (MTTA) | `avg(acknowledged_at − created_at)` | NULL if no alerts left `Open` in the window |
| `mean_time_to_triage` (MTTT) | `avg(triaged_at − created_at)` | NULL if no alerts reached `Triaging` in the window |
| `mean_time_to_conclusion` (MTTC) | `avg(closed_at − created_at)` | NULL if no alerts reached `Closed` in the window |

> **MTTD caveat:** MTTD measures Calseta ingestion latency relative to the source alert timestamp (`occurred_at`) — it is **not** true dwell time from incident occurrence, which is generally unknowable from alert data alone. `occurred_at` reflects when the SIEM detected the activity, not when the underlying incident began.

#### Workflow Metrics

| Metric | Description |
|---|---|
| `workflows_by_type` | Count by type (indicator/alert) |
| `workflow_run_count` | Total executions in time range |
| `workflow_success_rate` | Percentage successful |
| `workflow_runs_over_time` | Execution volume by day |
| `time_saved` | Sum of successful runs × per-workflow `time_saved_minutes` estimate |
| `most_executed_workflows` | Top workflows by run count |

#### Approval Metrics

| Metric | Description |
|---|---|
| `approval_requests_total` | Total approval requests created in time range |
| `approval_requests_by_status` | Count grouped by `pending`, `approved`, `rejected`, `expired` |
| `approval_response_time_seconds` | Median and p95 time from request creation to human decision |
| `approval_rate` | Percentage of non-expired requests that were approved |
| `approvals_by_workflow` | Top workflows by approval request volume |

#### MCP Resource
`calseta://metrics/summary` — compact SOC health snapshot optimized for agent context injection:

```json
{
  "period": "last_30_days",
  "alerts": {
    "total": 342,
    "active": 47,
    "by_severity": { "Critical": 3, "High": 12, "Medium": 28, "Low": 4 },
    "false_positive_rate": 0.31,
    "mttd_seconds": 12.4,
    "mtta_seconds": 840.0,
    "mttt_seconds": 1380.0,
    "mttc_seconds": 15120.0
  },
  "workflows": {
    "total_configured": 12,
    "executions": 89,
    "success_rate": 0.97,
    "estimated_time_saved_hours": 14.5
  },
  "approvals": {
    "pending": 2,
    "approved_last_30_days": 34,
    "approval_rate": 0.89,
    "median_response_time_minutes": 8.3
  }
}
```

---

### 7.7 Agent Integration Layer

#### Purpose
Enable customer-built AI agents to receive alert notifications automatically and write findings back to the platform — without requiring agents to poll.

#### Agent Registration
```json
{
  "name": "Identity Investigation Agent",
  "description": "Investigates account compromise alerts using Okta and Entra enrichment.",
  "endpoint_url": "https://my-agent.internal/webhooks/calseta",
  "auth_header_name": "X-Agent-Token",
  "auth_header_value": "...",
  "trigger_on_sources": ["sentinel"],
  "trigger_on_severities": ["High", "Critical"],
  "trigger_filter": null,
  "timeout_seconds": 30,
  "retry_count": 3,
  "documentation": "What this agent does and when it should be triggered."
}
```

#### Trigger Evaluation
After enrichment completes:
1. Check `trigger_on_sources` (empty = all)
2. Check `trigger_on_severities` (empty = all)
3. Check `trigger_filter` JSONB rules
4. If all match: dispatch webhook

#### Webhook Payload
The enriched alert payload delivered to agents includes:
- Full normalized alert (`CalsetaAlert` fields)
- All indicators with enrichment results from all providers
- Associated detection rule with full documentation
- Applicable context documents (global + targeted)
- Available workflows relevant to the alert
- Calseta API base URL for callbacks
- `_metadata` block — compact data source provenance (alert source, enrichment providers succeeded/failed, detection rule match, context doc count)

#### `_metadata` Block

Included at the top level of the alert object in both the REST detail response and the webhook payload. Computed at serialization time from existing relational data — no new database columns required.

```json
"_metadata": {
  "generated_at": "2026-02-28T14:32:00Z",
  "alert_source": "microsoft_sentinel",
  "indicator_count": 5,
  "enrichment": {
    "succeeded": ["virustotal", "abuseipdb"],
    "failed": ["okta"],
    "enriched_at": "2026-02-28T14:32:01Z"
  },
  "detection_rule_matched": true,
  "context_documents_applied": 2
}
```

**Field descriptions:**
- `generated_at` — ISO 8601 timestamp when this response was serialized
- `alert_source` — value of `alerts.source_name`
- `indicator_count` — count of associated `alert_indicators` rows
- `enrichment.succeeded` — provider names where at least one indicator has `success=true` in `enrichment_results`
- `enrichment.failed` — provider names where at least one indicator has `success=false` in `enrichment_results` and none succeeded
- `enrichment.enriched_at` — maximum `enriched_at` timestamp across all providers for this alert; `null` if no enrichment has run
- `detection_rule_matched` — `true` iff `alerts.detection_rule_id` is non-null
- `context_documents_applied` — count of context documents included in this response

When no enrichment has run: `"enrichment": { "succeeded": [], "failed": [], "enriched_at": null }`

#### Agent Callback API
Agents write results back using their API key:
- `POST /v1/alerts/{uuid}/findings` — post analysis finding
- `PATCH /v1/alerts/{uuid}` — update alert status
- `POST /v1/workflows/{uuid}/execute` — execute a workflow
- `POST /v1/enrichments` — request on-demand enrichment

Finding payload:
```json
{
  "agent_name": "Identity Investigation Agent",
  "summary": "...",
  "confidence": "high",
  "recommended_action": "...",
  "evidence": { }
}
```

#### Trigger Methods Supported
- **Webhooks (v1)** — platform POSTs enriched alert to registered endpoint. Framework-agnostic, works with everything.
- **MCP sampling** — documented for Claude-native agents using the MCP server. Agent is a long-running process connected to the MCP server and receives alerts via MCP notifications.

---

### 7.8 MCP Server

#### Purpose
Expose Calseta AI data and actions via Model Context Protocol so Claude Code, Claude Desktop, Cursor, and any MCP-compatible agent can access security data without writing custom API client code.

#### Authentication
Same API key mechanism as REST API. Configured in MCP client settings.

#### MCP Resources (Read)

| URI | Description |
|---|---|
| `calseta://alerts` | Recent alerts with status and severity |
| `calseta://alerts/{uuid}` | Full alert with enrichments, detection rule, context docs, and `_metadata` block (inherited from REST adapter — no additional MCP work required) |
| `calseta://alerts/{uuid}/activity` | Ordered activity log for this alert — status changes, workflow runs, findings, enrichment completions |
| `calseta://alerts/{uuid}/context` | Applicable context documents |
| `calseta://detection-rules` | Rule catalog with MITRE mappings |
| `calseta://detection-rules/{uuid}` | Full rule with documentation |
| `calseta://context-documents` | All documents with descriptions |
| `calseta://context-documents/{uuid}` | Full document content |
| `calseta://workflows` | Workflow catalog with documentation |
| `calseta://workflows/{uuid}` | Full workflow with documentation |
| `calseta://metrics/summary` | Current SOC health snapshot |
| `calseta://enrichments/{type}/{value}` | On-demand enrichment result |

#### MCP Tools (Write / Execute)

| Tool | Description |
|---|---|
| `post_alert_finding` | Post agent analysis finding to an alert |
| `update_alert_status` | Update alert status |
| `execute_workflow` | Run a registered workflow with context |
| `enrich_indicator` | Request on-demand enrichment |
| `search_alerts` | Search alerts by criteria |
| `search_detection_rules` | Search rules by MITRE or name |

The MCP server is a thin adapter over the REST API. No independent business logic.

---

### 7.9 REST API

#### Conventions
- All routes prefixed `/v1/`
- All responses JSON
- All timestamps ISO 8601 with timezone
- All IDs in responses/paths are UUIDs
- Pagination: `page` (1-indexed), `page_size` (default 50, max 500)

#### Standard Response Envelopes

Success single: `{ "data": {...}, "meta": {} }`

Success list: `{ "data": [...], "meta": { "total": 342, "page": 1, "page_size": 50, "total_pages": 7 } }`

Error: `{ "error": { "code": "ALERT_NOT_FOUND", "message": "...", "details": {} } }`

#### Full Endpoint Map

**Ingestion**
- `POST /v1/ingest/{source_name}` — ingest from named source
- `POST /v1/alerts` — ingest pre-normalized `CalsetaAlert` payload (generic webhook)

**Alerts**
- `GET /v1/alerts` — list with filters (status, severity, source, is_enriched, from_time, to_time, detection_rule_uuid, tags)
- `GET /v1/alerts/{uuid}` — full alert with enrichments, detection rule, context docs; response `data` object includes `_metadata` at top level (see §7.7 for shape)
- `PATCH /v1/alerts/{uuid}` — update status, severity, tags
- `DELETE /v1/alerts/{uuid}`
- `GET /v1/alerts/{uuid}/indicators` — extracted IOCs with enrichment
- `GET /v1/alerts/{uuid}/activity` — ordered activity log; supports `event_type` filter; paginated; newest first
- `GET /v1/alerts/{uuid}/context` — applicable context documents
- `POST /v1/alerts/{uuid}/findings` — post agent finding
- `GET /v1/alerts/{uuid}/findings` — list agent findings
- `POST /v1/alerts/{uuid}/trigger-agents` — manually trigger applicable agents

**Detection Rules**
- `GET /v1/detection-rules` — list with filters (source_name, mitre_tactic, mitre_technique, is_active)
- `POST /v1/detection-rules` — create
- `GET /v1/detection-rules/{uuid}` — full rule with documentation
- `PATCH /v1/detection-rules/{uuid}` — update rule and documentation
- `DELETE /v1/detection-rules/{uuid}`
- `GET /v1/detection-rules/{uuid}/alerts` — associated alerts

**Enrichments**
- `POST /v1/enrichments` — on-demand enrichment for any indicator
- `GET /v1/enrichments/providers` — configured providers with status and documentation

**Enrichment Field Extractions**
- `GET /v1/enrichment-extractions` — list all extraction configs; supports filters: `provider_name`, `indicator_type`, `is_system`, `is_active`
- `POST /v1/enrichment-extractions` — create custom extraction entry; returns `400` if `source_path` is invalid dot-notation
- `GET /v1/enrichment-extractions/{uuid}`
- `PATCH /v1/enrichment-extractions/{uuid}` — update `source_path`, `target_key`, `value_type`, `is_active`, `description`; system entries can be deactivated but not deleted
- `DELETE /v1/enrichment-extractions/{uuid}` — custom entries only; system entries return `403`
- `POST /v1/enrichment-extractions/test` — test an extraction config against a sample raw provider response; returns the extracted value or a path resolution error
- `POST /v1/enrichment-extractions/reextract` — re-run active extraction configs against stored raw responses for a given `provider_name` + `indicator_type`; enqueues background task, no external API calls made

**Context Documents**
- `GET /v1/context-documents`
- `POST /v1/context-documents`
- `GET /v1/context-documents/{uuid}`
- `PATCH /v1/context-documents/{uuid}`
- `DELETE /v1/context-documents/{uuid}`

**Workflows**
- `GET /v1/workflows` — list with documentation summaries
- `POST /v1/workflows` — create; validates code via AST before saving; returns `400` if disallowed imports found
- `GET /v1/workflows/{uuid}`
- `PATCH /v1/workflows/{uuid}` — update; re-validates AST on code changes; increments `code_version`
- `DELETE /v1/workflows/{uuid}`
- `POST /v1/workflows/generate` — AI-generate workflow code from natural language description; returns code for review, not saved automatically
- `POST /v1/workflows/{uuid}/test` — sandboxed execution with mock HTTP calls and fixture context; no real external calls made
- `GET /v1/workflows/{uuid}/versions` — version history; lists all prior code versions with diff metadata
- `POST /v1/workflows/{uuid}/execute` — execute with context payload
- `GET /v1/workflows/{uuid}/runs` — execution history
- `GET /v1/workflow-runs` — all runs across all workflows

**Workflow Approvals**
- `GET /v1/workflow-approvals` — list approval requests; supports filters: `status`, `workflow_uuid`, `from`, `to`
- `GET /v1/workflow-approvals/{uuid}` — get approval request with full trigger context and execution result
- `POST /v1/workflow-approvals/{uuid}/approve` — approve request; triggers workflow execution immediately via task queue
- `POST /v1/workflow-approvals/{uuid}/reject` — reject request; accepts optional `{ "reason": "..." }` body
- `POST /v1/approvals/callback/slack` — Slack interactive component webhook; verifies `X-Slack-Signature` before processing
- `POST /v1/approvals/callback/teams` — Teams action webhook; verifies Bot Framework JWT before processing

**Agent Registrations**
- `GET /v1/agents`
- `POST /v1/agents`
- `GET /v1/agents/{uuid}`
- `PATCH /v1/agents/{uuid}`
- `DELETE /v1/agents/{uuid}`
- `GET /v1/agents/{uuid}/runs` — webhook delivery history
- `POST /v1/agents/{uuid}/test` — send test payload

**Metrics**
- `GET /v1/metrics/alerts?from=&to=`
- `GET /v1/metrics/workflows?from=&to=`
- `GET /v1/metrics/summary`

**Indicator Field Mappings**
- `GET /v1/indicator-mappings` — list all mappings with filters (`source_name`, `is_system`, `indicator_type`, `is_active`)
- `POST /v1/indicator-mappings` — create custom mapping
- `GET /v1/indicator-mappings/{uuid}`
- `PATCH /v1/indicator-mappings/{uuid}` — update `field_path`, `indicator_type`, `is_active`, `description`
- `DELETE /v1/indicator-mappings/{uuid}` — custom mappings only; system mappings return `403`
- `POST /v1/indicator-mappings/test` — test a mapping config against a sample payload; returns extracted indicators

**Source Integrations**
- `GET /v1/sources`
- `POST /v1/sources`
- `GET /v1/sources/{uuid}`
- `PATCH /v1/sources/{uuid}`
- `DELETE /v1/sources/{uuid}`

**API Keys**
- `GET /v1/api-keys`
- `POST /v1/api-keys` — returns full key once
- `DELETE /v1/api-keys/{uuid}`

**Health**
- `GET /health`

---

### 7.10 Authentication

#### v1: API Keys
- Format: `cai_{random_32_char_urlsafe_string}` (prefix `cai` = Calseta AI)
- Stored as bcrypt hash; first 8 chars stored as `key_prefix` for display
- Full key shown once on creation, never stored in plaintext
- Scopes: `alerts:read`, `alerts:write`, `enrichments:read`, `workflows:read`, `workflows:execute`, `agents:read`, `agents:write`, `admin`
- Header: `Authorization: Bearer cai_xxxxx`

#### BetterAuth-Ready Architecture
Auth is abstracted behind a dependency injection interface. v1 implements API key auth against this interface. Future versions add username/password and SSO/OIDC by extending the interface without touching route code. This is documented explicitly as the extension path.

#### API Key Expiry Enforcement
The `expires_at` column exists on the `api_keys` table. The auth middleware checks it on every request. If `expires_at` is not null and the current UTC time is past it, the request is rejected with `401 {"code": "KEY_EXPIRED"}`. `last_used_at` is updated on every successful authentication via a fire-and-forget async write — it does not block the response.

#### Auth Failure Audit Logging
All authentication failures are emitted as structured JSON log lines to stdout alongside regular request logs. Not stored in the database — stdout is the correct path to a log aggregator for security events.

Log format:
```json
{
  "event": "auth_failure",
  "reason": "invalid_key | key_expired | key_inactive | missing_key | insufficient_scope | invalid_signature",
  "key_prefix": "cai_abc1",
  "required_scope": "alerts:write",
  "ip": "1.2.3.4",
  "endpoint": "POST /v1/alerts",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-02-26T12:00:00Z"
}
```

`key_prefix` is null when no key was provided. It is never the full key — only the 8-char stored prefix. `required_scope` is only populated for `insufficient_scope` failures.

---

### 7.11 Task Queue System

#### Purpose
Provide durable, reliable task execution for all async operations — alert enrichment, workflow execution, agent webhook dispatch, and alert trigger evaluation — ensuring tasks survive server restarts and are never silently lost if the platform goes down mid-processing.

FastAPI's built-in `BackgroundTasks` runs in-process and is not durable: a server restart or crash drops all queued work. This is unacceptable for a security platform where a missed enrichment or failed webhook delivery has direct operational consequences. All async operations are therefore routed through a persistent task queue.

#### Queued Operations
Every operation that runs asynchronously and must not be lost is enqueued:

| Task | Trigger | Queue |
|---|---|---|
| Alert enrichment pipeline | After ingestion | `enrichment` |
| Alert trigger evaluation | After enrichment completes | `dispatch` |
| Agent webhook delivery | After trigger match | `dispatch` |
| Workflow execution | Via REST, MCP, or agent callback | `workflows` |
| On-demand enrichment | Via `POST /v1/enrichments` | `enrichment` |

#### Queue Abstraction Interface
The queue system is abstracted behind `TaskQueueBase`. All enqueue call sites are identical regardless of the backend in use:

```python
class TaskQueueBase(ABC):
    @abstractmethod
    async def enqueue(
        self,
        task_name: str,
        payload: dict,
        *,
        queue: str = "default",
        delay_seconds: int = 0,
        priority: int = 0,
    ) -> str:
        """Enqueue a task. Returns task ID."""

    @abstractmethod
    async def get_task_status(self, task_id: str) -> TaskStatus:
        """Return current status of a queued task."""

    @abstractmethod
    async def start_worker(self, queues: list[str]) -> None:
        """Start consuming tasks from specified queues."""
```

#### Default Implementation: Procrastinate (PostgreSQL)
Out of the box, Calseta AI uses **[procrastinate](https://procrastinate.readthedocs.io/)**, a Python async task queue backed by PostgreSQL:

- **No additional infrastructure** — uses the existing Postgres instance already required by the platform. No Redis, no RabbitMQ, no external broker needed for a standard deployment.
- **ACID guarantees** — task state is transactional. Tasks are written and committed before the ingestion endpoint returns `202 Accepted`. They cannot be lost by a server crash.
- **At-least-once delivery** — tasks that fail or whose worker crashes mid-execution are re-enqueued automatically.
- **Native async** — integrates cleanly with FastAPI's async worker model.

The worker process runs as a separate Docker Compose service, consuming from the shared Postgres task store:

```yaml
services:
  api:
    command: uvicorn calseta.main:app --host 0.0.0.0 --port 8000
    depends_on: [db]
  worker:
    command: python -m calseta.worker
    depends_on: [db]
  mcp:
    command: python -m calseta.mcp_server
    depends_on: [db]
  db:
    image: postgres:15
```

The API server enqueues tasks; the worker process dequeues and executes them. They share no in-memory state — only the database.

#### Configuration
All queue behavior is controlled via environment variables. Switching backends requires only a `QUEUE_BACKEND` change and the addition of relevant credentials — no code changes.

| Variable | Default | Description |
|---|---|---|
| `QUEUE_BACKEND` | `postgres` | Backend: `postgres`, `celery_redis`, `sqs`, `azure_service_bus` |
| `QUEUE_POSTGRES_DSN` | (inherits `DATABASE_URL`) | DSN for procrastinate backend |
| `QUEUE_REDIS_URL` | — | Redis URL for Celery+Redis backend |
| `QUEUE_SQS_QUEUE_URL` | — | AWS SQS queue URL |
| `QUEUE_AZURE_CONNECTION_STRING` | — | Azure Service Bus connection string |
| `QUEUE_CONCURRENCY` | `10` | Worker concurrency (parallel tasks) |
| `QUEUE_MAX_RETRIES` | `3` | Default retry attempts for failed tasks |
| `QUEUE_RETRY_BACKOFF_SECONDS` | `60` | Base backoff interval (exponential) |

#### Pluggable Backends
Four adapters ship with the platform. All implement `TaskQueueBase`; swapping requires only a config change:

| Backend | `QUEUE_BACKEND` value | When to use |
|---|---|---|
| Procrastinate (PostgreSQL) | `postgres` | Default. No extra infra. ACID guarantees. |
| Celery + Redis | `celery_redis` | Higher throughput; existing Redis investment. |
| AWS SQS | `sqs` | AWS-native deployments; managed queue service. |
| Azure Service Bus | `azure_service_bus` | Azure-native deployments. |

All task registration, enqueue call sites, and worker startup code are backend-agnostic. The adapter is resolved at startup from `QUEUE_BACKEND`.

#### Queues and Concurrency
Tasks are organized into named queues with independent worker concurrency settings:

| Queue | Tasks | Default Concurrency |
|---|---|---|
| `enrichment` | Alert enrichment, on-demand enrichment | 10 |
| `dispatch` | Agent webhook delivery, trigger evaluation | 20 |
| `workflows` | Workflow execution | 10 |
| `default` | Miscellaneous background tasks | 5 |

#### Reliability Guarantees
- **Durability** — tasks are written to the queue store (Postgres or external broker) before the originating HTTP request returns. No task is held only in memory.
- **At-least-once delivery** — failed tasks are retried up to `QUEUE_MAX_RETRIES` with exponential backoff.
- **Idempotency** — all task handlers are written to be idempotent; safe to execute more than once without side effects.
- **Crash recovery** — tasks claimed by a worker that crashes before completion are re-enqueued via visibility timeout mechanisms native to each backend.
- **Dead letter** — tasks exceeding `max_retries` are moved to a dead letter store and logged with full payload and error context for manual inspection.

#### Observability
- Active queue depth and worker health included in `GET /health`
- Task failure count surfaced in `GET /v1/metrics/summary`
- All failed task payloads and error traces logged for debugging
- Worker process logs structured as JSON for log aggregator compatibility

---

### 7.12 Indicator Extraction & Field Mapping System

#### Purpose
Define a consistent, extensible pipeline for extracting threat indicators from every ingested alert — whether that alert was normalized from a known source (Sentinel, Elastic, Splunk) or arrived as a generic `CalsetaAlert` payload. The system handles standard normalized fields out of the box, while allowing teams to map arbitrary source-specific fields (e.g., `okta.data.client.ipAddress` inside an Elastic alert body) without writing code.

#### Three-Pass Extraction Pipeline

Every alert passes through three extraction stages in sequence. Results from all three passes are merged and deduplicated by `(type, value)` before storage.

```
Alert ingested
    │
    ▼
Pass 1 — Source Plugin Extraction
    • AlertSourceBase.extract_indicators(raw_payload)
    • Hard-coded in the source plugin; covers the most common
      indicators the plugin author knows are present
    • Returns: list[IndicatorExtract]
    │
    ▼
Pass 2 — System Normalized-Field Mapping Extraction
    • Runs against CalsetaAlert normalized columns (extraction_target='normalized')
    • Mapping table pre-seeded at startup; stored in DB so
      entries are visible and editable via API
    • Handles standard CalsetaAlert fields using dot-notation paths
    • Returns: list[IndicatorExtract]
    │
    ▼
Pass 3 — Custom Per-Source Field Mapping Extraction
    • Runs against raw_payload (original pre-normalization JSON)
    • Mapping entries created by users for source-specific or
      integration-specific fields not present in CalsetaAlert columns
    • Dot-notation path resolution with automatic array unwrapping
    • Returns: list[IndicatorExtract]
    │
    ▼
Merge + Deduplicate
    • Combine all three result sets
    • Deduplicate by (type, value) — same indicator from multiple
      passes stored once
    • Store in indicators table; attach to alert record
```

#### Pass 2: System Normalized-Field Mappings

These mappings are pre-seeded into `indicator_field_mappings` at application startup with `is_system = True`, `source_name = NULL`, and `extraction_target = 'normalized'`. They target the normalized `CalsetaAlert` columns using dot-notation paths. Users can view and disable individual mappings via the API but cannot delete system mappings.

**Standard `CalsetaAlert` → indicator mappings (seeded at startup):**

| CalsetaAlert Field Path | Indicator Type | Notes |
|---|---|---|
| `src_ip` | `ip` | Source IP address |
| `dst_ip` | `ip` | Destination IP address |
| `src_hostname` | `domain` | Source hostname |
| `dst_hostname` | `domain` | Destination hostname |
| `file_hash_md5` | `hash_md5` | File hash, MD5 |
| `file_hash_sha256` | `hash_sha256` | File hash, SHA-256 |
| `file_hash_sha1` | `hash_sha1` | File hash, SHA-1 |
| `actor_email` | `email` | Actor email address |
| `actor_username` | `account` | Actor username |
| `dns_query` | `domain` | DNS query target |
| `http_url` | `url` | Full URL string |
| `http_hostname` | `domain` | URL hostname |
| `email_from` | `email` | Email sender |
| `email_reply_to` | `email` | Email reply-to address |

> **Note:** The exact `CalsetaAlert` field names for each normalized column are confirmed during chunk 1.3 schema definition and 1.8 API research. Source plugins are responsible for mapping source-specific fields to these columns in `normalize()`. The field paths above should be verified against the finalized `CalsetaAlert` Pydantic schema before the seeder in chunk 1.7 is implemented.

#### Pass 3: Custom Per-Source Field Mappings

User-defined mappings that target `raw_payload` using dot-notation paths (`extraction_target = 'raw_payload'`). These handle source-specific or integration-specific fields not present as columns on the normalized `CalsetaAlert` — for example, Okta event fields embedded inside an Elastic Security alert body.

**Example use case:** An Elastic detection rule triggers on an Okta authentication event. The Elastic alert payload contains the full raw Okta event under `okta.data.*`. These fields don't map to `CalsetaAlert` columns, so Pass 2 won't reach them. A custom mapping resolves this:

```json
{
  "source_name": "elastic",
  "field_path": "okta.data.client.ipAddress",
  "indicator_type": "ip",
  "description": "Okta client IP address from Elastic-forwarded Okta event"
}
```

```json
{
  "source_name": "elastic",
  "field_path": "okta.data.actor.login",
  "indicator_type": "account",
  "description": "Okta actor login from Elastic-forwarded Okta event"
}
```

**Field path resolution rules:**
1. Dot-notation traversal: `okta.data.client.ipAddress` → `payload["okta"]["data"]["client"]["ipAddress"]`
2. Array unwrapping: if any traversal segment resolves to a list, the extractor iterates each element and continues traversal on each — every scalar string at the end of the path becomes one indicator
3. Missing or null field → silently skipped, no error
4. Non-string scalar values (integers, booleans) → cast to string and extracted

**Array unwrapping example:**
```json
Field path: "related.ip"
Payload:    { "related": { "ip": ["1.2.3.4", "5.6.7.8"] } }
Extracted:  [IndicatorExtract(type="ip", value="1.2.3.4"),
             IndicatorExtract(type="ip", value="5.6.7.8")]
```

#### Indicator Field Mapping Data Model

All mappings — both system and custom — are stored in a single `indicator_field_mappings` table. This unified table means the full mapping configuration is always visible in one place and can be managed through a single API.

| Column | Type | Description |
|---|---|---|
| `source_name` | TEXT nullable | `NULL` = applies to all sources (system mappings); source name (e.g., `elastic`) = custom |
| `field_path` | TEXT | Dot-notation path into the extraction target |
| `indicator_type` | TEXT | `IndicatorType` enum value |
| `extraction_target` | TEXT | `normalized` for system mappings (against `CalsetaAlert` fields); `raw_payload` for custom (against source-specific raw data) |
| `is_system` | BOOLEAN | `True` for startup-seeded system mappings; `False` for user-defined |
| `is_active` | BOOLEAN | Allows disabling a mapping without deletion |
| `description` | TEXT | Human-readable explanation of what the field contains and why it is mapped |

#### API Endpoints

```
GET    /v1/indicator-mappings                — list all mappings; filters: source_name, is_system, indicator_type, is_active
POST   /v1/indicator-mappings                — create a custom mapping (is_system always False on creation)
GET    /v1/indicator-mappings/{uuid}         — get single mapping
PATCH  /v1/indicator-mappings/{uuid}         — update mapping (field_path, indicator_type, is_active, description)
DELETE /v1/indicator-mappings/{uuid}         — delete custom mapping (system mappings cannot be deleted; use PATCH to disable)
POST   /v1/indicator-mappings/test           — test a mapping against a sample payload; returns what indicators would be extracted
```

The `POST /v1/indicator-mappings/test` endpoint accepts a field path, indicator type, extraction target (`normalized` or `raw_payload`), and a sample payload. It returns the indicators that would be extracted, making it easy to validate a mapping before enabling it.

#### Deduplication

After all three passes complete, indicators are deduplicated by `(type, value)`. If the same IP address is extracted by both the source plugin and a custom field mapping, it is stored as a single indicator and enriched once. The enrichment cache key `enrichment:{provider}:{type}:{value}` ensures the same indicator is never enriched twice across alerts within the TTL window.

#### Roadmap: Indicator Mapping UI (v1.3)

The indicator field mapping system is designed as a first-class candidate for a visual configuration UI in v1.3. The UI would surface:
- The full system mapping table with field documentation and inline enable/disable toggles
- A per-source custom mapping editor with a live field tester: paste a sample alert payload → see which indicators would be extracted and from which passes
- Mapping validation against historical alerts (dry-run enrichment preview)

This is one of the features most likely to be used by non-engineering security staff, making a UI substantially more accessible than the API alone.

---

## 8. Data Model

### Shared Column Pattern
Every table includes: `id` (serial PK), `uuid` (UUID unique, external-facing), `created_at`, `updated_at`. External-facing IDs are always UUIDs. Internal joins use integer `id` for performance.

---

### Alert Lifecycle Enums

These four enums govern the alert and indicator lifecycle throughout the platform. They appear in ORM columns, Pydantic schemas, API filters, MCP resources, metrics groupings, and agent payloads. **These values are finalized and locked — do not change without a migration and a breaking API version bump.**

#### Alert Status

Tracks the SOC workflow state of an alert from arrival to resolution. Stored as `TEXT` with application-level validation (Pydantic enum). All six values are API-visible.

| Value | Description |
|---|---|
| `pending_enrichment` | Alert has been ingested; enrichment pipeline has not yet completed. Set on creation. |
| `enriched` | Enrichment pipeline has completed; alert is ready for agent or analyst review. Set by worker after enrichment. |
| `Open` | Alert is enriched and acknowledged as needing investigation; no active action taken yet. |
| `Triaging` | Alert is under active investigation by an analyst or agent. Sets `triaged_at`. |
| `Escalated` | Alert has been escalated to a higher tier or external team. Sets `acknowledged_at` if not already set. |
| `Closed` | Alert has been resolved; `close_classification` must be set. Sets `closed_at`. |

**Lifecycle transitions:** `pending_enrichment` → `enriched` (by worker, automatic) → `Open` (by agent or analyst, explicit) → `Triaging` / `Escalated` → `Closed`. Agents and analysts interact with alerts from `enriched` status onward. The `acknowledged_at` timestamp is set on the first transition out of `enriched` or `Open`. **Storage:** TEXT column with Pydantic enum validation; do not use a Postgres `ENUM` type (makes migrations harder without benefit).

#### Alert Severity

Assigned from the source alert on ingest; can be overridden by an analyst or agent via `PATCH /v1/alerts/{uuid}`.

| Value | `severity_id` | Description |
|---|---|---|
| `Pending` | `0` | Severity not yet determined; default when the source does not provide one |
| `Informational` | `1` | No immediate threat; logged for awareness |
| `Low` | `2` | Minor risk; does not require immediate action |
| `Medium` | `3` | Moderate risk; should be reviewed within normal SLA |
| `High` | `4` | Significant threat; requires prompt attention |
| `Critical` | `5` | Severe threat; requires immediate response |

**Source mapping:** Sources that emit severity values outside this set use the following fallbacks: `Fatal` → `Critical`; `Unknown` or absent → `Pending`. Source plugins are responsible for applying this mapping in `normalize()`.

The `severity_id` integer is stored alongside `severity` string to allow fast numeric range filtering (`severity_id >= 4` for High and above) without string comparison.

#### Indicator Malice Classification

Set on each `indicator` row after enrichment completes. Represents the platform's assessment of whether the indicator is malicious, based on aggregated enrichment results.

| Value | Description |
|---|---|
| `Pending` | Enrichment has not yet run or all providers failed; verdict not available |
| `Benign` | Enrichment results indicate no known malicious association |
| `Suspicious` | One or more providers flag the indicator as suspicious but not definitively malicious (e.g., VirusTotal `suspicious_votes > 0` but `malicious_votes == 0`) |
| `Malicious` | One or more enrichment providers definitively flag the indicator as malicious |

**Column name:** `malice` — a categorical TEXT enum, not a numeric score. If a numeric confidence score is needed in a future version, it would be a separate `malice_score` float column; that is out of scope for v1. **Enrichment engine logic:** after all providers complete, the engine sets `malice` to the worst verdict across all successful provider results (`Malicious` > `Suspicious` > `Benign` > `Pending`).

#### Alert Close Classification

Required when `status` transitions to `Closed`. Records why the alert was closed — used for false positive rate metrics, detection rule quality tracking, and agent training signal.

| Value | Description |
|---|---|
| `True Positive - Suspicious Activity` | Alert correctly detected genuinely suspicious or malicious activity |
| `Benign Positive - Suspicious but Expected` | Alert fired correctly but the activity was authorized or expected (e.g., a known pentest, a scheduled admin task) |
| `False Positive - Incorrect Detection Logic` | Alert fired due to a flaw in the detection rule itself; the rule needs to be updated |
| `False Positive - Inaccurate Data` | Alert fired due to missing or incorrect data (e.g., stale asset records, wrong IP assignment); detection logic is sound |
| `Undetermined` | Alert closed without a definitive conclusion |
| `Duplicate` | Alert is a duplicate of another alert already being investigated |
| `Not Applicable` | Alert closed for administrative reasons; does not reflect detection quality |

**Design notes:**
- `close_classification` is only valid when `status = Closed`. The API should enforce this: `PATCH /v1/alerts/{uuid}` with `status: Closed` must include `close_classification`; setting `close_classification` without `status: Closed` should return `400`.
- The distinction between the two `False Positive` subtypes is intentional and high-value — it tells detection engineers whether to fix the rule or fix the data, which are very different remediation paths.
- **`false_positive_rate` metric definition:** any `close_classification` whose value starts with `False Positive` counts as a false positive. Currently that is `False Positive - Incorrect Detection Logic` and `False Positive - Inaccurate Data`. This string-prefix approach means new FP subtypes added in future versions are automatically counted without a metric code change.

**Storage:** Store as a `TEXT` column with application-level validation (Pydantic enum). Consider a Postgres `CHECK` constraint as a secondary guard.

---

### Core Tables

**alerts** — one row per security alert
- `title`, `severity` TEXT, `severity_id` INTEGER, `occurred_at` TIMESTAMPTZ, `source_name` TEXT — normalized `CalsetaAlert` fields stored as direct columns
- `source_time`, `ingested_at`, `enriched_at` TIMESTAMPTZ, `is_enriched` BOOLEAN, `fingerprint` TEXT
- `status` TEXT — see Alert Status enum (§8 Alert Lifecycle Enums); `pending_enrichment` on creation
- `close_classification` TEXT nullable — see Alert Close Classification enum; required when `status = Closed`
- `acknowledged_at` TIMESTAMP WITH TIME ZONE nullable — set by service layer on first transition out of `enriched` or `Open`; write-once, never updated; NULL until that transition occurs
- `triaged_at` TIMESTAMP WITH TIME ZONE nullable — set by service layer when status changes to `Triaging`; write-once, never updated; NULL until that transition occurs
- `closed_at` TIMESTAMP WITH TIME ZONE nullable — set by service layer when status changes to `Closed`; write-once, never updated; NULL until that transition occurs
- `raw_payload` JSONB — original unmodified source payload; preserves all source-specific fields that don't map to `CalsetaAlert` columns
- `agent_findings` JSONB — findings array from agents
- `tags` TEXT[]
- `detection_rule_id` FK → detection_rules
- **No `ocsf_data` JSONB column** — the platform uses the agent-native schema (`CalsetaAlert`), not OCSF
- **No `indicators` JSONB column** — indicators are a first-class relational entity; alert indicator summaries are queried via the `alert_indicators` join table

**detection_rules** — detection logic library
- `name`, `source_rule_id`, `source_name`, `severity`, `is_active`
- `mitre_tactics` TEXT[], `mitre_techniques` TEXT[], `mitre_subtechniques` TEXT[]
- `data_sources` TEXT[], `run_frequency`, `created_by`
- `documentation` TEXT — free-form markdown

**indicators** — extracted IOCs; global entity, one row per unique `(type, value)` pair across all alerts
- `type` TEXT — `IndicatorType` enum value
- `value` TEXT — the IOC value (IP address, domain, hash, etc.)
- Unique constraint on `(type, value)` — same IOC appearing in multiple alerts shares one row
- `first_seen` TIMESTAMP WITH TIME ZONE — timestamp of the earliest alert that contained this indicator
- `last_seen` TIMESTAMP WITH TIME ZONE — timestamp of the most recent alert that contained this indicator; updated whenever a new alert references this indicator
- `is_enriched` BOOLEAN — true after at least one enrichment provider has successfully run
- `malice` TEXT — see Indicator Malice Classification enum (§8 Alert Lifecycle Enums); categorical verdict, not a numeric score
- `enrichment_results` JSONB — keyed by `provider_name`; each entry contains `success`, `extracted` (the configured field subset surfaced to agents), `raw` (full API response, excluded from agent payloads), and `enriched_at`
- **No `alert_id` FK** — relationship to alerts is via the `alert_indicators` join table; this is what makes indicators reusable and enrichable once across many alerts

**alert_indicators** — many-to-many join between alerts and indicators
- `alert_id` FK → alerts.id (NOT NULL)
- `indicator_id` FK → indicators.id (NOT NULL)
- Composite unique constraint on `(alert_id, indicator_id)` — no duplicate associations
- No additional columns; context (when the association was created) comes from shared `created_at`
- **Design rationale:** an IP address appearing in 50 alerts is stored and enriched once; all 50 alerts reference the same indicator row; `first_seen`/`last_seen` track the indicator's history across the full alert corpus without aggregation queries

**enrichment_field_extractions** — configurable field extraction schema for enrichment provider responses
- `provider_name` TEXT — which provider this applies to (`virustotal`, `abuseipdb`, `okta`, `entra`)
- `indicator_type` TEXT — which indicator type this extraction applies to
- `source_path` TEXT — dot-notation path into the provider's raw response JSONB
- `target_key` TEXT — the key name in the `extracted` dict surfaced to agents
- `value_type` TEXT — `string`, `integer`, `float`, `boolean`, `json`; controls type coercion on extraction
- `is_system` BOOLEAN — `true` for startup-seeded defaults; `false` for user-defined entries
- `is_active` BOOLEAN
- `description` TEXT — LLM-readable explanation of what this field represents and why it matters

**context_documents** — runbooks, IR plans, SOPs
- `title`, `document_type`, `is_global`, `targeting_rules` JSONB
- `description`, `content` TEXT, `tags` TEXT[], `version`

**workflows** — Python automation functions
- `name`, `workflow_type`, `indicator_types` TEXT[]
- `code` TEXT — Python source defining `async def run(ctx: WorkflowContext) -> WorkflowResult`
- `code_version` INTEGER — increments on each code edit; starts at 1
- `state` TEXT — `draft`, `active`, `inactive`
- `timeout_seconds`, `retry_count`, `is_active`, `is_system` BOOLEAN, `tags` TEXT[]
- `time_saved_minutes` INTEGER
- `requires_approval` BOOLEAN — default `true`; whether agent-triggered executions require human approval before running
- `approval_channel` TEXT nullable — Slack channel ID or Teams channel URL; if null, `APPROVAL_DEFAULT_CHANNEL` applies
- `approval_timeout_seconds` INTEGER — default 3600; per-workflow override for the global approval window
- `risk_level` TEXT — `low`, `medium`, `high`, `critical`; displayed in approval notifications
- `documentation` TEXT — free-form markdown with LLM-oriented headings (see Section 7.5)

**workflow_runs** — execution audit log
- `workflow_id` FK, `trigger_type`, `trigger_context` JSONB
- `code_version_executed` INTEGER — which `code_version` was run
- `log_output` TEXT — captured output from `ctx.log` calls during execution
- `result` JSONB — serialized `WorkflowResult` (`success`, `message`, `data`)
- `status`, `attempt_count`, `duration_ms`, timestamps

**workflow_approval_requests** — human-in-the-loop approval lifecycle
- `workflow_id` FK, `workflow_run_id` FK nullable — set to the created `workflow_run` UUID after approved execution
- `trigger_type` TEXT — `mcp_agent` or `rest_agent`
- `trigger_agent_key_prefix` TEXT — first 8 chars of the requesting API key
- `trigger_context` JSONB — snapshot of `indicator` and `alert` context at request creation time
- `reason` TEXT — agent's stated reason for requesting execution
- `confidence` FLOAT — agent's confidence score (0.0–1.0)
- `notifier_type` TEXT — `slack`, `teams`, `none`
- `notifier_channel` TEXT — resolved channel used for notification
- `external_message_id` TEXT — Slack `ts` / Teams activity ID for result follow-up threading
- `status` TEXT — `pending`, `approved`, `rejected`, `expired`, `cancelled`
- `responder_id` TEXT — Slack user ID / Teams user ID / `rest:{api_key_prefix}` for REST approvals
- `responded_at` TIMESTAMP nullable
- `expires_at` TIMESTAMP — set at creation; computed from `approval_timeout_seconds`
- `execution_result` JSONB — serialized `WorkflowResult` (set after execution if approved)

**agent_registrations** — registered agent endpoints
- `name`, `description`, `endpoint_url`, `auth_header_name`, `auth_header_value_encrypted`
- `trigger_on_sources` TEXT[], `trigger_on_severities` TEXT[], `trigger_filter` JSONB
- `timeout_seconds`, `retry_count`, `is_active`
- `documentation` TEXT

**agent_runs** — webhook delivery audit log
- `agent_registration_id` FK, `alert_id` FK
- `request_payload` JSONB, `response_status_code`, `response_body` JSONB
- `status`, `attempt_count`, timestamps

**activity_events** — immutable, append-only audit log of every significant action taken on platform entities
- `event_type` TEXT — see Activity Event Types table below; records are never modified after creation
- `actor_type` TEXT — `system` (worker / startup tasks), `api` (REST API caller), `mcp` (MCP tool caller)
- `actor_key_prefix` TEXT nullable — first 8 chars of the API key for `api` and `mcp` actor types; NULL for `system`
- `alert_id` FK → alerts.id nullable
- `workflow_id` FK → workflows.id nullable
- `detection_rule_id` FK → detection_rules.id nullable
- `references` JSONB — structured event-specific payload; shape is fixed per `event_type` (see table below); never free-form
- **No `updated_at`** — activity events are write-once; the shared mixin's `created_at` is the event timestamp
- **Design rationale:** an agent reading `calseta://alerts/{uuid}/activity` gets the complete history of an alert — what happened, in what order, triggered by whom — without re-investigating questions the platform has already answered. This is the primary mechanism for preventing duplicate agent work and for giving agents the full picture before they act.

#### Activity Event Types

| Event Type | FK Set | `references` Keys |
|---|---|---|
| `alert_ingested` | `alert_id` | `source_name`, `indicator_count` |
| `alert_enrichment_completed` | `alert_id` | `indicator_count`, `providers_succeeded` (list of provider name strings), `providers_failed` (list of provider name strings), `malice_counts` (object: `{Malicious: N, Benign: N, Pending: N}`) |
| `alert_status_updated` | `alert_id` | `old_status`, `new_status` |
| `alert_severity_updated` | `alert_id` | `old_severity`, `new_severity` |
| `alert_closed` | `alert_id` | `close_classification` |
| `alert_finding_added` | `alert_id` | `actor_key_prefix` |
| `alert_workflow_triggered` | `alert_id`, `workflow_id` | `trigger_type` (`agent` or `manual`), `workflow_name` |
| `workflow_executed` | `workflow_id` | `workflow_run_uuid`, `success`, `duration_ms` |
| `workflow_approval_requested` | `workflow_id` | `workflow_run_uuid`, `reason`, `confidence` |
| `workflow_approval_responded` | `workflow_id` | `decision` (`approved` or `rejected`), `responder_id` |
| `detection_rule_created` | `detection_rule_id` | `source_rule_id`, `source_name` |
| `detection_rule_updated` | `detection_rule_id` | `changed_fields` (list of field names modified) |

**source_integrations** — configured alert sources
- `source_name`, `display_name`, `is_active`
- `auth_type`, `auth_config` JSONB (encrypted)
- `documentation` TEXT

**indicator_field_mappings** — system normalized-field mappings and custom per-source mappings
- `source_name` TEXT nullable — NULL = system/global; source name = per-source custom
- `field_path` TEXT — dot-notation path into extraction target
- `indicator_type` TEXT — IndicatorType enum value
- `extraction_target` TEXT — `normalized` (against `CalsetaAlert` columns) or `raw_payload` (against source JSON)
- `is_system` BOOLEAN — True for startup-seeded system defaults; False for user-defined
- `is_active` BOOLEAN
- `description` TEXT

**api_keys** — authentication credentials
- `name`, `key_prefix`, `key_hash` (bcrypt), `scopes` TEXT[]
- `is_active`, `expires_at`, `last_used_at`

---

## 9. Integration Catalog v1

### Alert Sources
| Integration | Ingestion Pattern |
|---|---|
| Microsoft Sentinel | Push webhook → `/v1/ingest/sentinel` |
| Elastic Security | Push webhook → `/v1/ingest/elastic` |
| Splunk | Push webhook → `/v1/ingest/splunk` |
| Generic webhook | Push webhook → `POST /v1/alerts` |

### Enrichment Providers
| Integration | Indicator Types |
|---|---|
| VirusTotal | IP, Domain, MD5, SHA1, SHA256 |
| AbuseIPDB | IP |
| Okta | Account |
| Microsoft Entra | Account |

### Integration Development Methodology

Each v1 integration is built by first fetching and analyzing the official API documentation for the target service before writing any implementation code. This is not optional — it is the required first step for every integration. An agent or developer that skips this step will produce field mappings and response parsers based on assumptions rather than reality.

**Why this matters in practice:** API documentation reveals field names, data types, nested structures, and edge cases that are not obvious from high-level product descriptions. For example, the Okta Users API returns account status as a string enum with values like `ACTIVE`, `DEPROVISIONED`, `SUSPENDED` — knowing this in advance means the enrichment provider maps it correctly instead of guessing. The Elastic Security alert payload includes the full raw event that triggered the rule (buried under `_source`), which is where the Okta-specific fields live — only the docs reveal this structure.

**Documentation sources fetched during development:**

| Integration | Documentation Targets |
|---|---|
| Microsoft Sentinel | Azure Monitor REST API, Sentinel Alerts schema, Microsoft Security Graph API |
| Elastic Security | ECS (Elastic Common Schema) field reference, Kibana alerting action payload schema, detection rule response format |
| Splunk | Splunk REST API reference, alert action webhook payload documentation |
| VirusTotal | VT API v3 reference — IP addresses, domains, files endpoints |
| AbuseIPDB | AbuseIPDB API v2 — check endpoint response schema |
| Okta | Okta Users API, Sessions API, Lifecycle Management API, System Log API |
| Microsoft Entra | Microsoft Graph API — users, authentication methods, sign-in logs, conditional access |

**Research artifacts produced:** For each integration, the documentation fetch produces a reference file at `docs/integrations/{integration_name}/api_notes.md` containing:
- Relevant request/response field names and types
- Pagination patterns
- Rate limit constraints
- Available automation endpoints (for workflow catalog seeding)
- Edge cases and known quirks

These artifacts are committed to the repository and serve as the primary reference for implementation agents, future community contributors, and anyone debugging unexpected data shapes.

---

### Pre-built Workflow Catalog

Because Calseta AI already holds API credentials for Okta and Microsoft Entra (configured for enrichment providers), those same credentials can power pre-built security workflows with no additional setup. These workflows are seeded into the workflow catalog at startup — available to agents and analysts from day one.

**Seeding behavior:** Pre-built workflows use `is_system = True` and can be disabled but not deleted. Each workflow is a Python function using `ctx.integrations.okta` or `ctx.integrations.entra` — the pre-built integration clients provided by `WorkflowContext`. No credentials are stored in the workflow record. Credentials are accessed at execution time via `ctx.secrets.get()`, which reads from the same environment variables already configured for the enrichment providers — no duplicate credential storage. If the required environment variables are absent, the associated workflows are seeded with `is_active = False` and become active automatically once credentials are added.

#### Okta Pre-built Workflows
_Requires: `OKTA_DOMAIN`, `OKTA_API_TOKEN`_

| Workflow Name | Action | Implementation | Trigger Type | Indicator Type |
|---|---|---|---|---|
| Okta — Revoke All Sessions | Terminate all active sessions for the user | `ctx.integrations.okta.revoke_sessions(ctx.indicator.value)` | Indicator | `account` |
| Okta — Suspend User | Suspend user account | `ctx.integrations.okta.suspend_user(ctx.indicator.value)` | Indicator | `account` |
| Okta — Unsuspend User | Reactivate a suspended user | `ctx.integrations.okta.unsuspend_user(ctx.indicator.value)` | Indicator | `account` |
| Okta — Reset Password | Expire current password and send reset email | `ctx.integrations.okta.reset_password(ctx.indicator.value)` | Indicator | `account` |
| Okta — Force Password Expiry | Force password change on next login without sending email | `ctx.integrations.okta.expire_password(ctx.indicator.value)` | Indicator | `account` |

#### Microsoft Entra Pre-built Workflows
_Requires: `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`_

| Workflow Name | Action | Implementation | Trigger Type | Indicator Type |
|---|---|---|---|---|
| Entra — Revoke Sign-in Sessions | Invalidate all refresh tokens and active sessions | `ctx.integrations.entra.revoke_sessions(ctx.indicator.value)` | Indicator | `account` |
| Entra — Disable Account | Set `accountEnabled: false` via Graph API | `ctx.integrations.entra.disable_account(ctx.indicator.value)` | Indicator | `account` |
| Entra — Enable Account | Set `accountEnabled: true` via Graph API | `ctx.integrations.entra.enable_account(ctx.indicator.value)` | Indicator | `account` |
| Entra — Force MFA Re-registration | Delete all registered authentication methods, forcing re-enrollment | `ctx.integrations.entra.reset_mfa(ctx.indicator.value)` | Indicator | `account` |

#### Roadmap: Expanded Pre-built Catalog (post-v1)
As additional enrichment providers and alert source integrations are added to the platform, their pre-built workflows follow. Because the API documentation is already fetched and committed as part of the integration development process, identifying available automation endpoints has zero marginal cost — it is a byproduct of building the integration. Community contributors adding a new enrichment provider are expected to include pre-built workflows for any lifecycle or remediation actions the API supports.

Candidates for post-v1 pre-built workflows include: VirusTotal URL/file submission, CrowdStrike host containment, SentinelOne threat mitigation, Palo Alto Networks EDL update, and Cisco Umbrella domain blocking.

---

### Community Extension
Both plugin systems (alert sources and enrichment providers) are explicitly designed for community contribution. Ships with:
- `docs/HOW_TO_ADD_ALERT_SOURCE.md`
- `docs/HOW_TO_ADD_ENRICHMENT_PROVIDER.md`
Each with a complete worked example, stub class template, and a reminder to fetch and commit API documentation as `docs/integrations/{name}/api_notes.md` before beginning implementation.

---

---

### 7.14 Structured Logging

#### Purpose
Provide consistent, machine-readable logs across all three processes (API, worker, MCP) that any log aggregation system can ingest without code changes. Logs are the primary observability tool for a self-hosted deployment — they must be good enough for an engineer to diagnose any production issue from logs alone.

#### Design: Stdout is the Contract (12-Factor)

The application logs to **stdout only**. The deployment layer (Docker, ECS, Container Apps, Kubernetes) is responsible for routing stdout to the appropriate destination. This means zero code changes are required to send logs to CloudWatch, Azure Monitor, Datadog, Splunk, or any other aggregator — configure the log driver in the container runtime, not in the application.

Library: **`structlog`** — provides structured context binding, consistent JSON output, and clean async support. Configured at application startup in `app/logging_config.py`.

#### Log Formats

Controlled by `LOG_FORMAT` env var:
- `json` (default, production) — newline-delimited JSON, one object per log line
- `text` (development) — human-readable colored console output via structlog's `ConsoleRenderer`

#### Standard Fields on Every Log Line

| Field | Description |
|---|---|
| `timestamp` | ISO 8601 UTC |
| `level` | `debug`, `info`, `warning`, `error`, `critical` |
| `message` | Human-readable event description |
| `service` | `api`, `worker`, or `mcp` — set at process startup |
| `version` | App version string (from `pyproject.toml` or `APP_VERSION` env var) |
| `request_id` | Present on all logs emitted during an HTTP request (bound to context) |
| `logger` | Module name (e.g., `app.services.enrichment`) |

#### Context Binding

`structlog` context variables are bound per-request using `structlog.contextvars`. The `RequestIDMiddleware` binds `request_id` at the start of every request so all downstream log calls (in services, repositories, integrations) automatically include it without being passed explicitly.

Worker tasks bind `task_id` and `task_name` at the start of each task execution.

#### Log Levels

Controlled by `LOG_LEVEL` env var (default: `INFO`):
- `DEBUG` — request/response bodies, enrichment provider raw responses, DB query details
- `INFO` — request summary (method, path, status, duration), task start/complete, enrichment complete
- `WARNING` — degraded state (enrichment provider unavailable, webhook signature not implemented, task retry)
- `ERROR` — unhandled exceptions, enrichment pipeline failure, webhook delivery failure after all retries
- `CRITICAL` — startup failure, DB connection failure

#### Env Vars

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Minimum log level emitted |
| `LOG_FORMAT` | `json` | `json` or `text` |
| `APP_VERSION` | `dev` | Included in every log line; set to git tag in CI |

#### Post-MVP: Direct Log Destination Adapters (Roadmap)

For deployments that cannot route stdout (uncommon but possible), a `LOG_DESTINATION` env var will activate optional direct handlers:
- `stdout` (default)
- `cloudwatch` — via `watchtower` library, requires `AWS_LOG_GROUP` and IAM permissions
- `azure_monitor` — via `opencensus-ext-azure`, requires `APPLICATIONINSIGHTS_CONNECTION_STRING`

Each adapter lives in `app/logging/handlers/` and is loaded only when the corresponding `LOG_DESTINATION` value is set. The core application code never imports handler-specific libraries directly.

---

## 10. Non-Functional Requirements

### Performance
- Alert ingestion endpoint returns `202 Accepted` within 200ms
- Enrichment pipeline (3–5 indicators, 2–3 providers) completes within 10 seconds
- REST API p95 < 500ms for list endpoints, < 200ms for single-resource
- MCP resource reads < 500ms

### Reliability
- Enrichment failures never fail the alert — failed providers are logged, alert proceeds with partial results
- Webhook delivery to agents retries up to 3 times with exponential backoff
- Workflow execution retries up to `retry_count` (configurable per workflow)
- All async operations (enrichment, webhook dispatch, workflow execution) are enqueued to a durable task queue before the originating HTTP request returns — no async work is held only in memory
- Tasks survive server restarts and worker crashes; at-least-once delivery is guaranteed by the queue backend
- All task handlers are idempotent; retrying a task after a partial execution produces no duplicate side effects

### Deployability
- Single `docker compose up` for full local stack
- All configuration via `.env` file
- Migrations run automatically on startup in development
- Production deployment guide in `docs/HOW_TO_DEPLOY.md`
- Alembic migration operations guide in `docs/HOW_TO_RUN_MIGRATIONS.md`
- Version upgrade procedure guide in `docs/HOW_TO_UPGRADE.md`

### Security
- No credentials in plaintext — all secrets encrypted at rest
- API keys never logged or returned after creation
- All outbound HTTP requests use configured timeouts
- Input validation on all ingestion endpoints

### CI/CD

#### Continuous Integration (every PR and push)

Platform: **GitHub Actions** (`.github/workflows/ci.yml`). Free for public repositories.

All checks must pass before a PR can be merged. No exceptions.

| Check | Tool | Failure = |
|---|---|---|
| Lint | `ruff check` | Cannot merge |
| Type check | `mypy` | Cannot merge |
| Unit + integration tests | `pytest` with real Postgres 15 container (`services:` in Actions job) | Cannot merge |
| Docker build validation | `docker build --target prod` | Cannot merge |

The Postgres test container is provisioned by GitHub Actions `services:` — no external DB required. Tests run with `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/calseta_test`.

#### Continuous Delivery (on tag push)

Platform: **GitHub Actions** (`.github/workflows/release.yml`). Triggers on `v*` tag pushes.

Steps:
1. Run full CI suite (lint + typecheck + tests) — must pass before release proceeds
2. Build multi-architecture Docker images (`linux/amd64` + `linux/arm64`)
3. Push to **GitHub Container Registry (GHCR)** with two tags: `v{semver}` and `latest`
4. Create GitHub Release with auto-generated changelog from merged PR titles

Images:
```
ghcr.io/{org}/calseta-api:{version}
ghcr.io/{org}/calseta-worker:{version}
ghcr.io/{org}/calseta-mcp:{version}
```

#### Release Process

Semantic versioning: `v{major}.{minor}.{patch}`

```
1. All work lands on feat/mvp-dev via PRs (CI must pass on each PR)
2. When ready to release: open PR from feat/mvp-dev → main
3. PR CI passes → merge
4. git tag v1.0.0 && git push origin v1.0.0
5. release.yml triggers automatically
6. GitHub Release page created; Docker images published
```

#### Branch Protection Rules (`main`)

- Require CI passing before merge
- No direct pushes — all changes via PR
- Require linear history (no merge commits — rebase or squash)

#### Local CI Parity

`make ci` runs the same checks locally in the same order as GitHub Actions. Engineers should run this before opening a PR. All checks pass locally before they pass remotely.

### Extensibility
- New alert source: one new file, no core changes required
- New enrichment provider: one new file, no core changes required
- New MCP tool: one new function, register in tool list
- Every extension point has a worked example in `docs/`

### Documentation
- Every module, class, and abstract method has a docstring
- `docs/` folder with LLM-friendly extension guides
- `examples/` folder with working sample agents
- OpenAPI spec auto-generated from FastAPI

---

---

### 7.13 Security Infrastructure

#### Purpose
Protect the API from abuse, enforce authentication consistently, limit the blast radius of a compromised key, and produce audit signals needed to detect attacks. All security limits and toggles are environment-variable-driven so deployers can tune for their environment without code changes. Secure defaults ship out of the box — deployers opt out, not in.

---

#### Rate Limiting

Library: `slowapi` (wraps the `limits` library; FastAPI-native middleware integration).

Rate limit keys:
- **Unauthenticated requests** — keyed by client IP address
- **Authenticated requests** — keyed by API key prefix

Default limits (all configurable via environment variables):

| Env Var | Default | Scope |
|---|---|---|
| `RATE_LIMIT_UNAUTHED_PER_MINUTE` | `30` | Per IP, unauthenticated endpoints |
| `RATE_LIMIT_AUTHED_PER_MINUTE` | `600` | Per API key, all authenticated endpoints |
| `RATE_LIMIT_INGEST_PER_MINUTE` | `100` | Per key, `POST /v1/ingest/*` and `POST /v1/alerts` |
| `RATE_LIMIT_ENRICHMENT_PER_MINUTE` | `60` | Per key, `POST /v1/enrichments` |
| `RATE_LIMIT_WORKFLOW_EXECUTE_PER_MINUTE` | `30` | Per key, `POST /v1/workflows/*/execute` |

**429 response** (always `ErrorResponse` format):
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded. Retry after 42 seconds.",
    "details": { "retry_after_seconds": 42 }
  }
}
```
Include `Retry-After: 42` header in all 429 responses.

**Trusted proxy configuration:** When running behind a reverse proxy or load balancer, the connection IP is the proxy IP — not the client IP. `TRUSTED_PROXY_COUNT` (default: `0`) specifies the number of proxy hops. When nonzero, the rate limiter reads the real client IP from `X-Forwarded-For`. **Warning:** setting this incorrectly allows clients to spoof their IP via a forged `X-Forwarded-For` header. This must be documented clearly in `.env.example`.

---

#### Security Headers

Applied by a single middleware class added to the FastAPI application. Adds the following headers to **every response**:

| Header | Value | Condition |
|---|---|---|
| `X-Content-Type-Options` | `nosniff` | Always |
| `X-Frame-Options` | `DENY` | Always |
| `X-XSS-Protection` | `1; mode=block` | Always |
| `Referrer-Policy` | `no-referrer` | Always |
| `Content-Security-Policy` | `default-src 'none'` | Always |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` | Always |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` | Only when `HTTPS_ENABLED=true` |

Individual headers can be disabled via env vars (e.g., `SECURITY_HEADER_HSTS_ENABLED=false`) for development or non-HTTPS environments. All enabled by default.

---

#### CORS

Disabled by default — no CORS headers are added unless explicitly configured. Enable with:

```
CORS_ALLOWED_ORIGINS=https://my-app.example.com,https://other.example.com
```

When enabled:
- Allowed methods: `GET, POST, PATCH, DELETE, OPTIONS`
- Allowed headers: `Authorization, Content-Type, X-Request-ID`
- `allow_credentials: true` (required for the `Authorization` header to be sent cross-origin)

`CORS_ALLOW_ALL_ORIGINS=true` is available for local development only. `.env.example` must document that this must never be used in production.

---

#### Request Body Size Limits

Enforced at middleware level before any route handler or payload parsing executes.

| Env Var | Default | Applies To |
|---|---|---|
| `MAX_REQUEST_BODY_SIZE_MB` | `10` | All endpoints |
| `MAX_INGEST_PAYLOAD_SIZE_MB` | `5` | `POST /v1/ingest/*` and `POST /v1/alerts` |

**413 response**:
```json
{
  "error": {
    "code": "PAYLOAD_TOO_LARGE",
    "message": "Request body exceeds the 5MB limit for ingest endpoints.",
    "details": {}
  }
}
```

---

#### Webhook Signature Verification

See `AlertSourceBase.verify_webhook_signature()` in Section 7.1. The ingest route handler calls this method **before** `validate_payload()`. If it returns `False`, the request is immediately rejected — no payload parsing occurs.

Signing mechanisms by source:

| Source | Mechanism | Header |
|---|---|---|
| Microsoft Sentinel | HMAC-SHA256 shared secret | `X-Ms-Signature` or `Authorization` (varies by Sentinel version — confirm in `docs/integrations/sentinel/api_notes.md`) |
| Elastic Security | Configurable shared secret or bearer token in Elastic alerting connector settings | `Authorization` (Basic or Bearer) |
| Splunk | Shared token configured in the Splunk alert action | `Authorization: Bearer <token>` |
| Generic webhook (`POST /v1/alerts`) | API key auth only — no additional webhook signature | n/a |

Each source plugin's `verify_webhook_signature()` implementation must:
1. Read the relevant header(s) from `headers`
2. Compute the expected signature using the configured secret (read from env via `settings`)
3. Compare using `hmac.compare_digest()` (constant-time) — never use `==` for signature comparison
4. Return `False` on any failure, including missing header or unconfigured secret

The source-specific secret env var must be documented in `docs/integrations/{source}/api_notes.md` and `.env.example`.

**401 response on failure**:
```json
{
  "error": {
    "code": "INVALID_SIGNATURE",
    "message": "Webhook signature verification failed.",
    "details": {}
  }
}
```
Also emitted as an `auth_failure` log event with `reason: "invalid_signature"`.

---

## 11. Out of Scope for v1

Architecture must not preclude these, but they will not be built in v1:

- **Frontend UI** — API-only
- **Incidents** — roadmap item (v1.1)
- **Alert source pull/polling** — push/webhook only
- **User management / RBAC** — single API key system
- **Analytics dashboard** — metrics via API only
- **Containerized agent hosting** — agents run in customer environment
- **Multi-tenancy** — single-tenant only
- **SSO / OAuth / username-password** — architecture ready, not implemented
- **Redis / Celery / SQS / Azure Service Bus queue backends** — `postgres` backend ships in v1; alternative backends (Celery+Redis, SQS, Azure Service Bus) are supported via config but not tested or documented in the v1 launch checklist
- **MITRE auto-tagging** — manual tagging only
- **Slack SOC bot** — roadmap v2.2; not in v1. Architecture must not preclude adding a fourth Docker Compose service for the bot process. Note: the workflow approval notifier (`SlackApprovalNotifier`) **is** in scope for v1 — it is a targeted message sender and callback receiver for the approval gate, not a general-purpose SOC bot. These are distinct features.
- **API key source restriction** — locking an API key to specific ingest sources (e.g., a key that can only POST to `/v1/ingest/elastic`). Useful for agent key provisioning. Architecture must not preclude this: the `api_keys` table should have an `allowed_sources` TEXT[] column stubbed as NULL (= unrestricted) so the restriction can be enforced by the auth middleware in a future version without a schema migration.
- **Execution rules (rule-based automation engine)** — a deterministic condition→action engine that fires workflows automatically based on alert field conditions (e.g., "if severity=Critical AND source_name=sentinel → run isolate_host workflow"). Distinct from agent dispatch: runs before agents, no LLM involved, purely rule-based. Architecture must not preclude this; the `agent_registrations` trigger filter JSONB is the closest current shape and should remain extensible. Roadmap: v1.2.
- **Named secrets store** — a database-backed secrets table (name, encrypted value, description) that workflow authors can reference by name rather than requiring every secret in env vars. Useful when teams want to add integration credentials via API without redeploying. Workflow `ctx.secrets` already abstracts secret access; the backing store can be swapped without changing workflow code. Roadmap: v1.1.

---

## 12. Roadmap Post-v1

**v1.1 — Incidents + Named Secrets Store + Bidirectional Status Sync + Knowledge Base Sync**
Lightweight incident entity for teams without external ticketing. Groups alerts, tracks status, surfaces as MCP resource. Agents create incidents via REST/MCP. Not full case management — structured grouping with notes. Also includes: database-backed named secrets store (`tenant_secrets` table) so workflow authors can reference credentials by name via API rather than requiring env var redeploys.

**Knowledge Base Integrations (v1.1):** Automated context document sync from Confluence spaces and Git repositories (GitHub/GitLab). Eliminates the manual re-upload requirement for keeping runbooks current. Architecture:
- New `context_sources` table: `source_type` (`confluence`/`github`/`gitlab`), `config` JSONB (URL, space/repo, auth), `sync_interval_minutes`, `last_synced_at`
- New `context_source_runs` table: sync audit log (started, completed, docs created/updated/deleted, errors)
- Scheduled procrastinate worker tasks: crawl configured sources, create/update `context_documents` rows; uses markitdown for format conversion during sync (PDF runbooks attached to Confluence pages, etc.)
- Auth: Confluence uses Atlassian OAuth 2.0 or API token; GitHub/GitLab use Personal Access Token or GitHub/GitLab App tokens
- v1 story without KB sync: operators upload files via `POST /v1/context-documents` with `multipart/form-data` (markitdown ships in v1 for this path); v1.1 adds automated sync on top of the same `context_documents` table — no schema changes to existing tables required

**Bidirectional Status Sync:** When an alert is closed in Calseta, optionally propagate closure back to the originating source SIEM. Requires a new optional `async sync_status(alert_ref: str, close_classification: str) -> bool` method on `AlertSourceBase`. Sources with API support: Sentinel (incident close), Elastic (case update), Splunk (notable status update). Generic webhook sources have no upstream to sync. Configurable per `source_integration` (opt-in). Best-effort and non-blocking — sync failures create an `activity_event` (`alert_sync_failed`) but never block alert closure.

**v1.2 — Pull-Based Alert Sources + Execution Rules**
Add polling to the alert source plugin system. Implement for at least one major source. For environments where webhook egress is restricted. Also includes: rule-based automation engine (`execution_rules` table) — deterministic condition→action dispatch that fires workflows based on alert field conditions without requiring an agent. Pairs with the existing alert trigger system to give teams a no-LLM automation layer for high-confidence response patterns.

**v1.3 — Frontend UI**
Minimal web UI: alert list and drill-down, detection rule management, context document upload, workflow catalog, agent registration, metrics overview. Includes the indicator field mapping configuration UI: a visual editor for system and custom mappings with a live field tester (paste a sample alert payload → see extracted indicators in real time). This is flagged as a priority UI surface because non-engineering security staff will benefit most from a visual interface for configuring indicator extraction.

**v1.5 — Hosted Sandbox Environment**

A publicly accessible Calseta AI instance running against synthetic fixture data, available without installation at `sandbox.calseta.ai`. The sandbox lets developers explore the full API, test MCP client integrations, and validate agent implementations before committing to a self-hosted deployment.

**What it is:** The same Calseta AI codebase running in a single-tenant cloud deployment with three differences from a production installation:
1. **Mock enrichment providers** — VirusTotal, AbuseIPDB, Okta, and Entra providers return realistic but canned responses. No real API keys are required; no real threat data is queried. The response shapes and field names are identical to real provider responses.
2. **Pre-seeded fixture data** — the five alert scenarios from the validation case study (Section 15) are pre-loaded and always available. A new visitor can immediately query `GET /v1/alerts`, retrieve a fully enriched alert, and explore the full data model without ingesting anything.
3. **Auto-reset every 24 hours** — all user-created data (custom alerts, detection rules, workflows, context documents) is wiped and the instance is restored to its seeded state. Protects against state accumulation from concurrent visitors.

**What it is not:** A simulator or a static mock API. It is the actual Calseta AI platform running live. Ingest endpoints work, the enrichment pipeline runs, the MCP server is active, agent webhooks can be registered and will fire. The only difference from self-hosted is that the enrichment results are canned.

**Access model:**
- Public API key displayed on the sandbox landing page — no sign-up required
- Rate limited at 200 requests/hour per IP to prevent abuse
- MCP server endpoint available at `sandbox.calseta.ai:8001` for Claude Desktop / Cursor testing
- Read-only access to pre-seeded data requires no key (for zero-friction exploration); write operations require the public key

**Relationship to the benchmark page:** The sandbox is the "Run it yourself" layer for the `/benchmark` page on the Calseta website. Every claim on the benchmark page links to the sandbox so skeptics can reproduce the comparison independently. This combination — published numbers + live reproducibility — is the primary credibility mechanism for the platform.

**Infrastructure:** Single-tenant ECS Fargate deployment (AWS) using the Terraform module from v3.1, running `dev`-tier sizing. Total cost is a small fixed monthly amount. Auto-reset is a scheduled ECS task that runs the database seeder on a 24-hour cron.

---

**v2.0 — Calseta Agent Schema (Open Specification)**

An open, versioned schema specification for delivering security alert context to AI agents. Extracted from Calseta's internal payload design and published as a standalone community spec.

**The problem it solves:**
OCSF solved "how do security tools talk to each other." No equivalent standard exists for "how does security infrastructure talk to AI agents." Every team building security agents today is inventing their own payload shapes — what fields to include, how to label them, how to attach enrichment data, how to reference detection context. Calseta's internal schema is already a well-considered answer to this problem. The roadmap item is to extract it, version it, and publish it.

**What the spec defines:**
- Top-level payload envelope: `event`, `alert`, `indicators`, `detection_rule`, `context_documents`, `workflows`, `activity`
- Field naming conventions: human-readable labels, no numeric type IDs, designed for LLM context windows not machine parsing
- Indicator structure: `type`/`value` pair with per-provider enrichment blocks (`extracted` subset + `enriched_at`, raw excluded by default)
- Context attachment pattern: how runbooks, SOPs, and detection documentation attach to an alert payload
- Schema versioning: `schema_version` field in the envelope; breaking changes require a major version bump

**Why publish it:**
A published spec reframes "Calseta uses its own schema" as "Calseta implements the agent alert schema." It creates a community surface: SIEM vendors adding agent dispatch features, security agent framework developers, and teams building their own data layers can implement the same spec. Calseta becomes the reference implementation rather than just one vendor's opinion. It also creates an external credibility mechanism — the spec can be referenced in agent framework documentation independent of Calseta's marketing.

**What ships with the spec:**
- `spec/` directory in the Calseta repo — YAML schema definitions + versioned JSON examples
- `docs/AGENT_SCHEMA.md` — specification document written for detection engineers and security platform builders
- Calseta REST API updated to include `X-Calseta-Schema-Version` header on all alert responses
- JSON Schema files published to a stable public URL

**Blog/guide angle:**
*"Why we didn't use OCSF — and what we built instead"* — walk through the OCSF evaluation, explain why OCSF's design goals (SIEM interoperability, numeric type IDs, breadth of event types) don't translate to the agent consumption layer, introduce the schema, publish the spec. Targeted at detection engineers and security platform builders facing the same architectural decision.

---

**v2.1 — Alternative Queue Backends (validation + docs)**
The queue abstraction ships in v1 with the PostgreSQL backend. v2.1 validates and documents the Celery+Redis, AWS SQS, and Azure Service Bus adapters for teams with high-throughput requirements or cloud-native queue preferences. Because the abstraction is already in place, this is a documentation and testing effort, not an architectural change.

**v2.2 — Slack SOC Bot**

A first-party Slack application built into the platform, running as a fourth process in Docker Compose alongside the API server, MCP server, and worker. Built with the **Slack Bolt for Python** framework. Connects to Slack via the Events API and Interactive Components API, handling all incoming events through a single inbound webhook registered in the Slack App manifest.

The bot provides two primary interaction surfaces and one push notification surface.

---

**Surface 1: Indicator Enrichment via CLI Commands**

Analysts type CLI-style commands as direct messages to the bot or as `@calseta` mentions in any channel the bot is invited to.

Command syntax:
```
enrich ip 1.2.3.4
enrich domain malicious-example.com
enrich hash a3f1b2c4d5e6...
enrich email user@example.com
enrich account jsmith
```

The bot resolves the indicator type, calls `POST /v1/enrichments` against the platform's REST API, and responds in the same thread with a rich **Slack Block Kit** message. The response is structured — not a raw JSON dump — showing only the fields that matter for analyst triage:

- Header: indicator type, value, and an overall risk badge (Critical / High / Medium / Low / Clean) derived from provider scores
- One collapsible section per enrichment provider that returned results, with key findings surfaced as labeled fields
- Contextual actions: "Search alerts for this indicator" (links to the alerts list filtered by the indicator), "Run workflow" (opens the workflow modal — see Surface 2)
- Footer: cache status (live vs. cached result) and timestamp

Example response for `enrich ip 1.2.3.4`:

```
┌─────────────────────────────────────────────────────────┐
│  IP Address  1.2.3.4                        🔴 HIGH RISK │
├─────────────────────────────────────────────────────────┤
│  VirusTotal                                             │
│  Malicious detections   47 / 93 engines                 │
│  Categories             malware, botnet                 │
│  Last analysis          2026-02-24                      │
├─────────────────────────────────────────────────────────┤
│  AbuseIPDB                                              │
│  Abuse confidence       94%                             │
│  Reports (90 days)      312                             │
│  Country                RU                              │
├─────────────────────────────────────────────────────────┤
│  [ Search alerts ]   [ Run workflow ]                   │
│  Source: live   ·   Enriched at 14:32:01 UTC            │
└─────────────────────────────────────────────────────────┘
```

The response reflects whichever enrichment providers are configured and active in the platform — no hardcoded provider names in the bot layer. If only AbuseIPDB is configured, only the AbuseIPDB block renders.

---

**Surface 2: Workflow Invocation**

Workflows can be invoked from Slack using a mention-based trigger:

```
@calseta run workflow
@calseta run workflow block-ip
```

**Without a workflow name:** The bot responds with an in-channel message containing a "Select workflow" dropdown populated from the live workflow catalog (`GET /v1/workflows`). Selecting a workflow and clicking "Open" triggers a modal.

**With a workflow name:** The bot looks up the workflow by name (fuzzy match) and opens the modal directly.

**The workflow modal:** Because different workflows require different inputs (an IP blocklist workflow needs an IP; an account suspension workflow needs a username), Slack modals are the right mechanism — they allow collecting structured, validated input without polluting the channel with back-and-forth prompts. The modal renders labeled input fields for each parameter the workflow needs (derived from the workflow's `documentation` → `## Required Secrets` and parameter hints). The workflow's `documentation` field is displayed as helper text so the analyst understands what they're executing and what to expect.

On modal submission, the bot calls `POST /v1/workflows/{uuid}/execute` and posts a result message to the originating channel:

- Success: green header, execution summary, "View run details" link
- Failure: red header, error message, retry button if the workflow has retries remaining

**Workflow discovery:** Analysts can also browse available workflows:

```
@calseta workflows
@calseta workflows account
```

Returns a paginated Block Kit list of active workflows matching the optional filter, each with its description and a "Run" button.

---

**Surface 3: Alert Notifications**

When a new alert is enriched and meets configured notification criteria, the bot proactively posts to configured Slack channels. This is push-only — no polling. The notification is dispatched by the worker process as part of the same post-enrichment task flow, after agent trigger evaluation.

Notification channels and severity thresholds are configured per channel in the platform (stored in `slack_channel_configs`). Example: `#soc-critical` receives Critical and High alerts; `#soc-all` receives all severities.

Each alert notification is a Block Kit message containing:
- Alert title, source system, severity badge, and ingestion timestamp
- Top indicators with their highest-severity enrichment finding (e.g., "IP 1.2.3.4 — AbuseIPDB: 94% confidence")
- Associated detection rule name and MITRE tactics (if available)
- Action buttons: "View alert", "Enrich indicators", "Run workflow", "Acknowledge"

The "Acknowledge" button calls `PATCH /v1/alerts/{uuid}` to update alert status without leaving Slack. The "Run workflow" button opens the workflow modal described in Surface 2, pre-populated with the alert's indicators as context.

---

**Additional bot commands:**

| Command | Response |
|---|---|
| `@calseta help` | Command reference with examples |
| `@calseta metrics` | Compact SOC health summary (from `GET /v1/metrics/summary`) |
| `@calseta alert <uuid>` | Alert summary card with enrichment and action buttons |
| `@calseta status` | Platform health (API, worker, queue depth, enrichment providers online) |

---

**Technical notes:**

- Implemented with **Slack Bolt for Python** (async mode), running on port 3000 in Docker Compose
- Connects to Slack via the Events API (HTTP mode) — no WebSocket process required
- All REST calls go to the platform's own API using an internal API key; the bot has no direct database access
- Slack bot token, signing secret, and channel configs stored in `.env`; never logged
- All block payloads are built server-side from templates, never interpolated from raw API responses (prevents injection of untrusted content into Slack messages)

**v2.2 — Additional Auth**
Username/password and SSO/OIDC using the BetterAuth-ready architecture foundation.

**v3.0 — Hosted Calseta AI**
Multi-tenant hosted product with managed Postgres, maintained integrations, SSO, SLA, compliance exports.

**v3.1 — Infrastructure as Code (Terraform)**

Production-ready Terraform modules for deploying the full Calseta AI stack on AWS and Azure. The goal is a single `terraform apply` that provisions everything required to run the platform in a cloud environment with no manual console steps.

---

**AWS Module (`terraform/aws/`)**

Provisions a complete, production-ready deployment on AWS:

| Resource | Service |
|---|---|
| Compute (API, worker, MCP, Slack bot) | ECS Fargate |
| Container registry | Amazon ECR |
| Database | Amazon RDS (PostgreSQL 15, Multi-AZ) |
| Task queue (optional swap from Postgres queue) | Amazon SQS |
| Load balancer | Application Load Balancer (ALB) |
| TLS termination | AWS Certificate Manager |
| Secrets management | AWS Secrets Manager (API keys, DB credentials, Slack tokens) |
| Container networking | VPC with public/private subnets, NAT gateway |
| DNS | Route 53 (optional, configurable) |

The module exposes variables for environment (`dev` / `prod`), instance sizing, retention windows, and whether to enable the SQS queue backend (setting `QUEUE_BACKEND=sqs` automatically in the ECS task definition). A `dev` preset runs Fargate Spot and a single-AZ RDS instance to minimize cost for evaluation deployments.

---

**Azure Module (`terraform/azure/`)**

Provisions an equivalent deployment on Azure:

| Resource | Service |
|---|---|
| Compute (API, worker, MCP, Slack bot) | Azure Container Apps |
| Container registry | Azure Container Registry (ACR) |
| Database | Azure Database for PostgreSQL (Flexible Server) |
| Task queue (optional swap) | Azure Service Bus |
| Load balancer / ingress | Azure Application Gateway |
| TLS termination | App Gateway managed certificates |
| Secrets management | Azure Key Vault |
| Container networking | Azure Virtual Network with delegated subnets |
| DNS | Azure DNS (optional, configurable) |

---

**Module Design Principles**

- **Minimal required variables:** a working deployment requires only a domain name, a region, and cloud credentials. All other variables have sensible defaults.
- **Environment tiers:** `dev` (cost-optimized, single-AZ) and `prod` (HA, multi-AZ, backups enabled) presets configurable via a single `environment` variable.
- **Secrets never in state:** all sensitive values (DB passwords, API keys, Slack tokens) are generated and stored directly in Secrets Manager / Key Vault; Terraform state contains only references.
- **Queue backend wired automatically:** selecting the cloud module sets the appropriate `QUEUE_BACKEND` environment variable in container definitions and provisions the corresponding queue service.
- **Modular structure:** each major component (networking, database, compute, secrets) is a separate sub-module so teams can adopt individual pieces into existing Terraform codebases.

Ships as open-source in the main repository under `terraform/`. Community contributions for GCP and on-premises (Kubernetes/Helm) deployments are explicitly welcomed.

---

**v4.0 — Autonomous Development Agent Workflow**

A documented, first-party workflow for using AI agents to participate in codebase development — reading GitHub issues, creating branches, implementing fixes, writing tests, and opening PRs that pass the full CI/CD pipeline automatically.

This capability is enabled by two things being simultaneously true:
1. Every major component ships a `CONTEXT.md` (see Section 5 philosophy) giving an LLM enough structured context to reason correctly about that component without reading all the source files.
2. The CI/CD pipeline has full automated test coverage so an AI-authored change can be validated without manual human review of every line.

**What the workflow looks like in practice:**

```
GitHub Issue Created (bug, feature request, security advisory)
    │
    ▼
Triage Agent (reads issue, reads relevant CONTEXT.md files, proposes approach)
    │
    ▼
Implementation Agent (creates branch, implements change, writes tests)
    │
    ▼
CI Pipeline (ruff → mypy → pytest → Docker build — must pass fully)
    │
    ▼
Review Agent (reads diff, checks against CONTEXT.md conventions, flags deviations)
    │
    ▼
PR opened with: implementation diff, test coverage report, CONTEXT.md update (if needed)
    │
    ▼
Human review (optional for small fixes where CI + review agent both pass)
```

**What this is not:** Autonomous agents committing directly to `main` or bypassing review. The agents produce PRs — humans remain in the merge decision loop. The goal is to reduce the time from issue to reviewable PR from days to minutes for well-scoped, well-documented changes.

**Prerequisites for v4.0:**
- All `CONTEXT.md` files complete and accurate (Wave 8 deliverable)
- Test coverage ≥ 85% across all core components (Wave 8)
- CI pipeline catching regressions reliably (Wave 1 chunk 1.11)
- Published `docs/HOW_TO_CONTRIBUTE_WITH_AI.md` — step-by-step guide for configuring Claude Code (or any agent) against this repo

This is a post-v3 milestone — the platform and its documentation must be fully mature before autonomous agent development workflows are reliable.

---

**Community Guides — Integration Patterns**

A series of first-party guides covering alternative architecture patterns for teams whose existing infrastructure doesn't fit the default Calseta configuration. These are not software features — they are documentation deliverables published to `docs/guides/` and the Calseta website.

**Guide: External Automation with AWS API Gateway + Lambda**

> For teams that do not want to use Calseta's built-in Python workflow engine.

Some organizations already operate a large AWS Lambda ecosystem — security automations built as individual Lambda functions, triggered by EventBridge, Step Functions, or direct API calls — and don't want to migrate that investment into Calseta's sandboxed Python runtime. This guide covers how to keep those automations where they are while still getting Calseta's enrichment data, MCP discovery, and human-in-the-loop approval gate.

**The pattern:**
1. Each existing Lambda function is exposed via an AWS API Gateway endpoint (one route per automation)
2. A thin Calseta workflow is registered for each automation — typically 10–20 lines that call `ctx.http.post(api_gateway_url, ...)`, pass the enriched indicator/alert context, and return the Lambda response as a `WorkflowResult`
3. The Calseta workflow catalog and approval system work exactly as designed — the agent discovers the workflow, requests execution, the human approves, and Calseta's thin wrapper fires the Lambda
4. All the Calseta plumbing (enrichment context, audit log, MCP discoverability, approval gate, retry logic, result storage) is preserved; only the execution backend lives in AWS

**Why this matters:** This is the same "thin wrapper" pattern already established for teams with Splunk SOAR or Tines, applied to serverless-native AWS shops. It makes clear that Calseta's workflow engine is not a replacement for existing automation infrastructure — it is the orchestration and approval layer that sits in front of it.

**Guide contents (rough outline):**
- When to use this pattern vs. the native workflow engine
- Setting up API Gateway with IAM auth; storing the endpoint URL and credentials via `ctx.secrets`
- Writing the thin wrapper Calseta workflow (template provided)
- Passing enriched indicator and alert context as Lambda input
- Mapping Lambda response codes and output to `WorkflowResult.ok()` / `WorkflowResult.fail()`
- End-to-end test: agent triggers approval → human approves → Lambda fires → result stored in Calseta

Additional guides in this series (candidates — not committed):
- **Azure Functions + APIM** — same pattern on Azure, using Azure API Management and Functions
- **Tines integration** — using Calseta thin workflows to trigger Tines stories with enriched context
- **n8n integration** — using Calseta as the data layer for n8n security automation workflows

---

## 13. Open Source Strategy

### License
Apache License 2.0.

### What is Open Source
Everything needed to self-host a single-tenant deployment: full data model, all v1 integrations, integration plugin systems, REST API, MCP server, workflow engine, agent registry, context system, metrics API, Docker Compose, all documentation.

### What is Proprietary (Hosted Product)
Multi-tenancy infrastructure, managed Postgres, hosted MCP endpoint, guaranteed integration maintenance, SLA, enterprise auth (SSO), compliance exports, agent hosting runtime.

### Community Contribution Model
Integration plugin systems designed for community contribution. `CONTRIBUTING.md` with clear guides. Community-contributed integrations in `app/integrations/community/`.

### Documentation as a Differentiator
LLM-friendly documentation is a first-class feature. A security engineer using Claude Code or Cursor should be able to clone the repo and immediately understand how to extend it, build a sample agent, or add a new integration.

### Benchmark Page as a Trust Asset

The validation case study (Section 15) produces more than internal validation — it produces the most credible marketing asset an open-source developer tool can have: public, reproducible evidence that the platform does what it claims.

The Calseta website will include a dedicated **`/benchmark`** page (working title: "The Numbers" or "Show Your Work") structured as follows:

- **Results table** — averaged token counts, cost per alert, and finding quality scores for both approaches across all 5 scenarios, with percentage deltas. Stamped with the model version and run date.
- **Methodology summary** — a concise description of the experimental design, linking to the full `docs/VALIDATION_CASE_STUDY.md` in the repository.
- **"View the code" link** — direct link to `examples/case_study/` on GitHub. The study is reproducible by anyone.
- **"Run it yourself" section** — hands the visitor a sandbox API key (v1.5) and a one-command quickstart for running `calseta_agent.py` against the live sandbox. Skeptics can reproduce the comparison without a local deployment.
- **Version history** — a table showing how results change over time as the platform improves or as model versions change. This signals ongoing commitment to honesty over one-time cherry-picked numbers.

**Why a dedicated page, not a blog post:** Blog posts are launch assets. They drive traffic once and are quickly perceived as marketing. A permanent benchmark page is a reference — something that can be linked in GitHub discussions, Hacker News threads, and security community Slacks as a factual answer to "does this actually save tokens?" The blog post is the launch vehicle that drives people to the benchmark page; the benchmark page is what they bookmark.

This page is built and published as part of the v1.5 milestone, after the sandbox is live so the "Run it yourself" section is functional from day one.

---

## 14. Success Criteria

### v1 Launch (8–12 weeks)
- [ ] Alert ingestion working for all 4 v1 sources
- [ ] Enrichment engine with all 4 v1 providers (automatic + on-demand)
- [ ] Detection rule auto-association on ingestion
- [ ] Context document system with targeting rules
- [ ] Workflow engine with indicator and alert types
- [ ] Agent registration and webhook delivery
- [ ] MCP server with all resources and tools
- [ ] Metrics API for alerts and workflows
- [ ] API key authentication (BetterAuth-ready)
- [ ] Durable task queue operational (procrastinate + PostgreSQL); all async ops enqueued before HTTP response returns
- [ ] Worker process runs as separate Docker Compose service; survives API server restart without task loss
- [ ] Single `docker compose up` deployment
- [ ] OpenAPI spec auto-generated
- [ ] `docs/` folder complete with all extension guides
- [ ] `examples/` with at least 2 working sample agents
- [ ] Pre-built Okta workflows (5) and Entra workflows (4) seeded and functional when credentials are configured
- [ ] `docs/integrations/` folder populated with `api_notes.md` for all 7 v1 integrations
- [ ] Validation case study completed (Section 15): all 5 scenarios run, results documented, artifacts committed to repo

### Early Adoption (12–16 weeks post-launch)
- [ ] 3–5 organizations self-hosting
- [ ] At least 1 community-contributed integration
- [ ] GitHub activity indicating real-world usage
- [ ] Sample agents being forked and adapted

### Core Thesis Validated
A security engineer can clone, deploy, connect a SIEM source, and have their first AI agent receiving enriched alert webhooks within one working day.

An AI agent using only the MCP server can investigate an alert — reading enrichment results, detection rule documentation, applicable runbooks, and available workflows — and post a finding back, without any custom API client code.

The validation case study (Section 15) must be completed before launch and its results published in the repository. The case study is the empirical foundation for every efficiency claim made about the platform.

---

## 15. Validation Case Study

### Purpose

The claims in Section 2 (Problem Statement) are specific and measurable — token cost, integration burden, latency, and the waste of using LLMs for deterministic work. Before launch, those claims must be validated empirically with a controlled experiment comparing a naive AI agent implementation against a Calseta-powered agent investigating the same alerts. The results become the primary technical evidence in launch materials, the README, and community discussions.

This is not optional polish. If the case study shows weaker-than-expected savings, that is a signal to improve the platform before launch — not to omit the study.

---

### Methodology

#### What is held constant
The same alert payload, the same LLM (Claude Sonnet, latest version), the same model parameters (temperature=0), the same enrichment provider credentials, and the same evaluation prompt are used in both approaches for each scenario. The only variable is whether Calseta AI processes the alert before the agent sees it.

#### Approach A — Naive AI Agent (Baseline)
The agent receives the raw alert payload directly from the source system and is responsible for all processing:

1. Raw alert JSON passed directly to the agent's context window
2. Agent uses tool calls to identify and extract indicators from the unstructured payload
3. Agent calls enrichment APIs directly (VirusTotal, AbuseIPDB, Okta/Entra as applicable) via tool calls
4. Agent receives raw API responses and must parse them itself
5. Agent has no access to pre-loaded detection rule documentation or runbooks — it either goes without or fetches them via additional tool calls
6. Agent synthesizes findings and produces a structured investigation summary

This represents the current state-of-the-art for teams building security AI agents without purpose-built infrastructure.

#### Approach B — Calseta AI Agent
The same alert is ingested by Calseta AI, processed through the full pipeline, and delivered to the agent as an enriched webhook payload:

1. Agent receives a single, pre-structured webhook payload containing:
   - Normalized alert in `CalsetaAlert` format (not raw JSON)
   - All indicator enrichment results, already parsed and structured per PRD Section 7.7
   - Detection rule documentation attached
   - Applicable context documents (runbooks, SOPs) already resolved
   - Available workflows listed with descriptions
2. Agent reads the pre-structured payload and produces an investigation summary
3. Agent optionally queries the MCP server for additional context
4. Agent posts finding via `POST /v1/alerts/{uuid}/findings`

#### Metrics Captured Per Run

| Metric | How Measured |
|---|---|
| **Input tokens (prompt)** | From LLM API response `usage.input_tokens` |
| **Output tokens (completion)** | From LLM API response `usage.output_tokens` |
| **Total tokens** | Sum of all LLM calls in the session |
| **Estimated cost (USD)** | Total tokens × current model pricing |
| **Number of LLM tool calls** | Count of tool calls made by the agent |
| **Number of external API calls** | Count of HTTP calls to enrichment providers |
| **Time to first finding (seconds)** | Wall clock from alert receipt to finding posted |
| **Finding quality score** | Blind evaluation by a separate LLM judge (1–5) on completeness, accuracy, and actionability |

Each run is executed three times and results are averaged to account for non-determinism in tool call patterns.

---

### Test Scenarios

Five alert scenarios are used, chosen to exercise different enrichment paths and represent realistic SOC workloads:

#### Scenario 1 — Account Compromise (Identity-focused)
A Sentinel alert for a suspicious sign-in: impossible travel detection or sign-in from a new country. Indicators: one account, one IP.

- Enrichment exercised: Okta (account status, MFA, recent activity) + AbuseIPDB (IP reputation)
- Why included: account compromise is the highest-volume alert type for the target segment; Okta/Entra enrichment is the most differentiated capability

#### Scenario 2 — Malware Detection (File Hash-focused)
An Elastic Security alert for a known-malicious executable detected on an endpoint. Indicators: one SHA-256 file hash, one source IP.

- Enrichment exercised: VirusTotal (hash analysis, detection count) + AbuseIPDB (IP)
- Why included: hash enrichment via VirusTotal is the most universally applicable capability and produces a large raw API response that benefits most from pre-structuring

#### Scenario 3 — Network Intrusion Attempt (IP-focused)
A Splunk alert for repeated failed authentication attempts from an external IP. Indicators: one source IP, one destination IP.

- Enrichment exercised: VirusTotal (IP reputation) + AbuseIPDB (IP)
- Why included: high-volume alert type; tests the caching layer — if both IPs resolve to the same ASN, only one enrichment call should fire for each unique IP

#### Scenario 4 — Lateral Movement (Multi-indicator)
A Sentinel alert for a user executing commands on multiple internal hosts after an initial compromise. Indicators: one account, two IPs, one domain (C2 beacon).

- Enrichment exercised: Okta + VirusTotal (domain, IPs) + AbuseIPDB (IPs)
- Why included: multi-indicator alert is the hardest case for a naive agent (many parallel API calls, many raw responses to parse); Calseta's parallel enrichment pipeline has the largest advantage here

#### Scenario 5 — Phishing / Email-based Threat (URL and Email-focused)
An Elastic alert for a user clicking a known-malicious URL in an email. Indicators: one URL, one email address, one domain extracted from the URL.

- Enrichment exercised: VirusTotal (URL, domain)
- Why included: tests the URL and email indicator types; email-based threats are common in the target segment

---

### Expected Results

These are the hypotheses to be validated — not guaranteed outcomes. If results differ materially, the methodology and platform design should be revisited before launch.

| Metric | Expected Direction | Rationale |
|---|---|---|
| Input tokens | A >> B | Raw API responses are verbose; Calseta delivers structured, minimal payloads |
| Output tokens | A ≈ B | Finding length should be similar; quality may differ |
| Total cost per alert | A >> B | Driven by input token reduction |
| LLM tool calls | A >> B | Naive agent needs tool calls for each enrichment; Calseta agent may need zero |
| External API calls by agent | A > 0, B = 0 | Calseta handles all enrichment before agent involvement |
| Time to first finding | A > B | Calseta's parallel enrichment is faster than sequential agent tool calls |
| Finding quality score | A ≤ B | Pre-structured, complete context should produce equal or better findings |

The minimum result that validates the platform's core thesis: **Approach B produces input token counts at least 50% lower than Approach A across all five scenarios**, with equal or better finding quality scores.

---

### Output Artifacts

The completed case study produces:

- `docs/VALIDATION_CASE_STUDY.md` — full methodology, raw results table, analysis, and conclusions
- `examples/case_study/naive_agent.py` — the Approach A implementation (runnable with API keys)
- `examples/case_study/calseta_agent.py` — the Approach B implementation (runnable against a local Calseta instance)
- `examples/case_study/fixtures/` — the five alert payloads used (anonymized/synthetic, realistic shapes)
- `examples/case_study/results/` — raw metric CSVs from each run

These artifacts are committed to the public repository. The case study is designed to be reproducible by anyone with the appropriate API keys — a community member should be able to clone the repo, configure `.env`, and re-run the study to verify the results independently.