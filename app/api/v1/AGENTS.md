# API Routes (v1) — Agent Navigation

## Shared Patterns

Every route handler follows this stack:
```
Auth → Scope check → Rate limit → Route handler → Service/Repository → Response envelope
```

- **Auth:** `Depends(require_scope(Scope.X))` from `app/auth/dependencies.py` — returns `AuthContext`
- **Pagination:** `PaginationParams = Depends()` from `app/api/pagination.py` — provides `.offset`, `.page_size`
- **Response envelopes:** `DataResponse[T]` (single), `PaginatedResponse[T]` (list) from `app/schemas/common.py`
- **Error handling:** raise `CalsetaException(code, message, status_code)` from `app/api/errors.py`
- **Rate limiting:** `@limiter.limit()` decorator from `app/middleware/rate_limit.py`
- **DI for DB:** `Depends(get_db)` → `AsyncSession`; DI for queue: `Depends(get_queue)` → `TaskQueueBase`
- **Scope aliases:** `_Read = Annotated[AuthContext, Depends(require_scope(Scope.X_READ))]`

---

## Auth Key Types (v2 addition)

Two API key formats exist. They are routed to different auth backends in `app/auth/dependencies.py`:

| Key Prefix | Type | Created via | `AuthContext` field populated |
|------------|------|-------------|-------------------------------|
| `cai_` | Operator/human key | `POST /v1/api-keys` | `auth.key_prefix`, `auth.scopes` |
| `cak_` | Agent API key | `POST /v1/agents/{uuid}/keys` | `auth.agent_registration_id` (int FK) |

**Operator keys (`cai_*`):** Human-facing. Carry named scopes (`alerts:read`, `admin`, etc.). Used for all v1 routes and operator-accessible v2 routes.

**Agent keys (`cak_*`):** Tied to a specific `AgentRegistration` row. Used by running agents to call queue/checkout, actions, invocations, and heartbeat endpoints. The auth backend sets `auth.agent_registration_id` — this is the identity signal consumed by `_get_agent()`.

---

## The `_get_agent()` Helper Pattern

Used in `alert_queue.py`, `actions.py`, and `invocations.py`. Resolves the calling agent from auth context:

```python
async def _get_agent(
    auth: AuthContext,
    db: AsyncSession,
    *,
    allow_operator: bool = False,
) -> AgentRegistration | None:
    # auth.agent_registration_id set  → load and return AgentRegistration
    # not set + allow_operator=True   → return None (operator mode, wider scope)
    # not set + allow_operator=False  → raise 403
```

**When to use:** Any endpoint where agent callers see only their own data and operator callers see all data. The `None` return signals operator mode — routes widen their query accordingly.

**When NOT to use:** Pure operator-admin endpoints (use `require_scope(Scope.ADMIN)` directly). Read-only topology/metrics endpoints that don't need agent identity.

The related helper `_require_orchestrator()` (used in `invocations.py`) additionally asserts `agent.agent_type == "orchestrator"`.

---

## Operator vs Agent-Only Endpoints

| Endpoint | Agent key (`cak_*`) | Operator key (`cai_*`) |
|----------|---------------------|------------------------|
| `GET /v1/queue` | ✓ sees own-eligible alerts | ✓ operator mode — sees all |
| `POST /v1/queue/{uuid}/checkout` | ✓ required | ✗ 403 |
| `POST /v1/queue/{uuid}/release` | ✓ required | ✗ 403 |
| `GET /v1/assignments/mine` | ✓ own assignments only | ✗ 403 |
| `POST /v1/actions` | ✓ required | ✗ 403 |
| `PATCH /v1/actions/{uuid}` (approve/reject) | ✗ — operator action | ✓ `AGENTS_WRITE` scope |
| `POST /v1/invocations` | ✓ orchestrator only | ✗ 403 |
| `POST /v1/heartbeat` | ✓ own agent_id inferred | ✓ with explicit `agent_id` body field |
| All CRUD on agents/tools/kb/secrets | — | ✓ operator/admin |

---

## Route → Service → Repository Map

### v1 Core Routes

| Route File | Prefix | Key Endpoints | Service/Repository |
|-----------|--------|---------------|-------------------|
| `ingest.py` | `/ingest`, `/alerts (POST)` | webhook_ingest, generic_ingest | `AlertIngestionService` → `AlertRepository`, queue |
| `alerts.py` | `/alerts` | list, detail, patch, delete, findings, indicators, activity, relationship-graph | `AlertRepository`, `IndicatorRepository`, `ActivityEventService` |
| `indicators.py` | `/indicators` | list, detail | `IndicatorRepository` |
| `detection_rules.py` | `/detection-rules` | CRUD | `DetectionRuleRepository` |
| `enrichments.py` | `/enrichments` | on-demand enrich | `EnrichmentService` |
| `enrichment_providers.py` | `/enrichment-providers` | CRUD + test | `EnrichmentProviderRepository`, enrichment_registry |
| `enrichment_field_extractions.py` | `/enrichment-field-extractions` | CRUD | `EnrichmentFieldExtractionRepository` |
| `context_documents.py` | `/context-documents` | CRUD (JSON + multipart) | `ContextDocumentRepository` |
| `workflows.py` | `/workflows` | CRUD, execute, test, generate, runs, versions | `WorkflowRepository`, `WorkflowRunRepository`, `workflow_executor` |
| `workflow_approvals.py` | `/workflow-approvals` | list, detail, approve/reject, browser decide page, Slack/Teams callbacks | `WorkflowApprovalRepository`, queue |
| `agents.py` | `/agents` | CRUD, pause, resume, terminate, capabilities, key mgmt, `/catalog` | `AgentRepository` |
| `sources.py` | `/sources` | CRUD, test-extraction | `SourceRepository`, source_registry |
| `indicator_mappings.py` | `/indicator-mappings` | CRUD | `IndicatorMappingRepository` |
| `api_keys.py` | `/api-keys` | CRUD (key shown once on create) | `ApiKeyRepository` |
| `metrics.py` | `/metrics` | summary dashboard | `MetricsService` |
| `settings.py` | `/settings` | runtime config | settings |

### v2 Agent Control Plane Routes

| Route File | Prefix | Key Endpoints | Service/Repository |
|-----------|--------|---------------|-------------------|
| `alert_queue.py` | `/queue`, `/assignments`, `/dashboard` | queue list, checkout, release, mine, update assignment, dashboard | `AlertQueueService` → `AlertAssignmentRepository` |
| `actions.py` | `/actions` | propose, list, detail, approve/reject, cancel | `ActionService` → `AgentActionRepository` |
| `invocations.py` | `/invocations`, `/agents/{uuid}/invocations` | delegate, delegate-parallel, status, long-poll, history | `InvocationService` → `InvocationRepository` |
| `issues.py` | `/issues`, `/agents/{uuid}/issues` | CRUD, checkout, release, comments | `IssueService` → `IssueRepository` |
| `routines.py` | `/routines` | CRUD, pause, resume, trigger, triggers CRUD, webhook, runs | `RoutineService` → `RoutineRepository` |
| `topology.py` | `/topology` | full topology, routing, delegation | `TopologyService` → `AgentRepository` |
| `secrets.py` | `/secrets` | CRUD, rotate, versions | `SecretService` → `SecretRepository` |
| `kb.py` | `/kb` | CRUD, `/folders`, `/search`, `/sync`, revisions, links | `KBService` → `KBPageRepository` |
| `memory.py` | `/memory`, `/agents/{uuid}/memory` | agent memory, shared, CRUD, promote | `KBService` (memory folder) → `KBPageRepository` |
| `llm_integrations.py` | `/llm-integrations` | CRUD, usage | `LLMIntegrationRepository` |
| `heartbeat.py` | `/heartbeat`, `/heartbeat-runs`, `/cost-events`, `/costs` | heartbeat record, runs, cost events, summaries | `HeartbeatService`, `CostService` |
| `agent_tools.py` | `/tools` | list, detail, register, update, delete, sync (501 stub) | `AgentToolRepository` |
| `sessions.py` | `/sessions`, `/agents/{uuid}/sessions` | session list and detail | `AgentTaskSessionRepository` |

---

## Custom (Non-CRUD) Routes

### v1 Core

| Endpoint | What It Does | Calls |
|----------|-------------|-------|
| `POST /v1/ingest/{source_name}` | Webhook ingest with signature verify | `source.verify_webhook_signature()` → `AlertIngestionService.ingest()` |
| `POST /v1/alerts` (body) | Programmatic ingest, no sig verify | `AlertIngestionService.ingest()` |
| `POST /v1/alerts/{uuid}/findings` | Add agent finding | `AlertRepository.add_finding()` |
| `POST /v1/alerts/{uuid}/indicators` | Link indicators to alert | `IndicatorRepository.upsert()` + `link_to_alert()` |
| `GET /v1/alerts/{uuid}/relationship-graph` | Alert-indicator-sibling graph | `AlertRepository` + `IndicatorRepository` |
| `POST /v1/enrichments/{type}/{value}` | On-demand enrichment | `EnrichmentService.enrich_indicator()` |
| `POST /v1/workflows/{uuid}/execute` | Enqueue workflow run (202) | `WorkflowRunRepository.create()` + `queue.enqueue()` |
| `POST /v1/workflows/{uuid}/test` | Sandbox test (mock HTTP) | `execute_workflow()` with mock transport |
| `POST /v1/workflows/generate` | LLM code generation | `WorkflowGeneratorService` |
| `POST /v1/sources/{name}/test-extraction` | Dry-run indicator extraction | `test_extraction()` from `indicator_extraction.py` |

### v2 Agent Control Plane

| Endpoint | What It Does | Auth |
|----------|-------------|------|
| `POST /v1/queue/{uuid}/checkout` | Atomic checkout — creates assignment, locks alert | `cak_*` only |
| `POST /v1/queue/{uuid}/release` | Release alert back to queue | `cak_*` only |
| `GET /v1/assignments/mine` | Own in-progress assignments | `cak_*` only |
| `POST /v1/invocations` | Delegate single task to specialist | `cak_*` orchestrator |
| `POST /v1/invocations/parallel` | Delegate 2–10 tasks simultaneously (202) | `cak_*` orchestrator |
| `GET /v1/invocations/{uuid}/poll` | Long-poll ≤30s; 200 = done, 202 = pending | `cak_*` orchestrator |
| `PATCH /v1/actions/{uuid}` (approve/reject) | Operator approves/rejects proposed agent action | `cai_*`, `AGENTS_WRITE` |
| `POST /v1/actions/{uuid}/cancel` | Agent cancels its own pending action | `cak_*` |
| `POST /v1/routines/{uuid}/triggers/{tuuid}/webhook` | External webhook → routine trigger | **No API key** — HMAC-SHA256 signature only |
| `POST /v1/tools/sync` | Re-sync MCP tools | Returns 501 (stub, not yet implemented) |
| `GET /v1/topology` | Full agent fleet graph | `cai_*`, `AGENTS_READ` |
| `GET /v1/dashboard` | Control plane dashboard metrics | `cai_*` or `cak_*`, `AGENTS_READ` |
| `GET /v1/workflow-approvals/{uuid}/decide?token=…` | Browser approval page (HTML render) | Token in query param, not API key |
| `POST /v1/workflow-approvals/{uuid}/decide` | Browser form submit | Token in form body |
| `POST /v1/workflow-approvals/callback/slack` | Slack interactive button callback | HMAC-SHA256 signature |
| `POST /v1/memory/{id}/promote` | Promote private agent memory to shared KB | `cai_*`, `ADMIN` |

---

## Special Route Ordering Rules

Some files contain literal string routes that must appear **before** parameterized UUID routes or FastAPI treats the literal as a path parameter value:

- `agents.py`: `/catalog` must be declared before `/{uuid}`
- `kb.py`: `/folders`, `/search`, `/sync` must be declared before `/{uuid}`

When adding a new literal sub-route, add it above the `/{uuid}` route in the same file.

---

## approvals.py Does Not Exist

The file `approvals.py` was merged into `workflow_approvals.py`. The approve/reject actions for workflow approvals are handled by `POST /v1/workflow-approvals/{uuid}/approve` and `POST /v1/workflow-approvals/{uuid}/reject` in that file. Do not create a new `approvals.py`.

---

## How to Add an Endpoint

1. Add route function in existing or new file under `app/api/v1/`
2. Use `Depends(require_scope(Scope.X))` for operator auth, or `_get_agent()` for agent-identity-aware routes
3. Use `PaginationParams = Depends()` for list endpoints
4. Call service layer or repository — never write raw SQL in routes
5. Return `DataResponse[T]` or `PaginatedResponse[T]`
6. Add `@limiter.limit()` decorator
7. Register router in `router.py` via `v1_router.include_router()`
8. Add corresponding Pydantic schemas in `app/schemas/`
