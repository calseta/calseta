# Calseta Architecture Deepening

**Date**: 2026-03-27
**Author**: Jorge Castro + Claude
**Status**: Draft

## Problem Statement

Calseta v1.0.0 shipped fast and works. But the codebase has a structural pattern that creates friction for both AI agents and human contributors: **many small files connected by implicit contracts**. The enrichment pipeline requires reading 5-6 files to understand one concept. The task queue registry is a 671-line file with 8 tasks duplicating session management boilerplate. Alert ingestion runs 8 sequential steps with no failure recovery between them. 16 repositories reimplement the same pagination/CRUD patterns. 19 route handlers duplicate auth, pagination, and response envelope wiring.

This matters now because:
1. **v2 work is imminent** — the agent control plane PRD adds orchestration, tool systems, and multi-agent delegation on top of these pipelines. If enrichment is already 5 files to understand, adding agent-driven enrichment makes it 8+.
2. **AI navigability is poor** — every conversation starts with expensive re-discovery of implicit contracts between modules. This is ironic for a product designed to be AI-agent-readable.
3. **Seam bugs are untested** — the real bugs hide in the orchestration between modules, not in the individual pure functions. The test suite mocks at module boundaries, which is exactly where the bugs live.

## Solution

Seven priorities that deepen shallow modules, consolidate scattered logic, eliminate boilerplate, and make the codebase AI-navigable — all as pure refactors with zero behavior changes:

1. **Enrichment Pipeline Orchestrator** — Consolidate 6 scattered enrichment files into a deep `EnrichmentPipeline` class with a single `run()` boundary
2. **Task Queue Registry** — Break 671-line registry into typed task handler classes with shared session management
3. **Alert Ingestion Pipeline** — Make the 8-step pipeline explicit with step-level error recovery and an end-to-end test
4. **Repository Base Class** — Extract shared pagination/CRUD/upsert into a generic `BaseRepository[T]`
5. **API Route Utilities** — Extract shared route wiring (list endpoint pattern, detail endpoint pattern) into reusable helpers
6. **Shallow Utility Consolidation** — Inline single-function modules into their parent services
7. **AGENTS.md Navigation System** — Add per-directory AI navigation files documenting pipelines, call graphs, troubleshooting, and extension patterns

## User Stories

1. As an AI agent working on the enrichment pipeline, I want to read one file to understand the full enrichment flow, so that I don't burn tokens bouncing between 6 files
2. As a developer adding a new enrichment feature for v2, I want to modify the enrichment pipeline without risk of breaking 5+ files, so that config schema changes are localized
3. As a developer adding a new task type for the agent control plane, I want a clear pattern for task handlers with typed payloads and injected dependencies, so that I don't copy-paste 40 lines of session boilerplate
4. As a developer debugging a failed enrichment enqueue during alert ingestion, I want explicit step-level error handling so I can see exactly which step failed and what state the alert is in
5. As a test author, I want to write a single end-to-end pipeline test for alert ingestion (ingest -> enrich -> dispatch) instead of mocking each module boundary separately
6. As a developer adding a new CRUD entity for v2, I want to inherit pagination, UUID lookup, and count from a base repository instead of reimplementing them
7. As a developer adding a new API endpoint, I want a shared list-endpoint helper that wires auth, pagination, filtering, and response envelopes, so that I write only the entity-specific logic
8. As an AI agent navigating the services layer, I want indicator_validation, url_validation, context_targeting, and agent_trigger logic to live inside the service that calls them, so that I don't have to trace through single-function modules
9. As a developer running the test suite, I want tests that catch seam bugs (e.g., template resolver produces a URL that the HTTP engine handles differently) not just unit tests of pure functions in isolation
10. As a contributor reading the codebase for the first time, I want fewer files with clearer boundaries so that I can understand a concept by reading one module, not six
11. As an AI agent starting a new conversation about the service layer, I want to read a single `AGENTS.md` file (~50-100 lines) to understand all pipelines, call graphs, and seam points, instead of exploring 6+ files (~800 lines)
12. As an AI agent debugging an enrichment failure, I want `AGENTS.md` to tell me "check provider `is_configured()` first, then trace through `pipeline.run()`" so I go straight to the problem
13. As an AI agent extending the codebase for v2, I want `AGENTS.md` to document extension patterns ("add a new provider via DB seed or API, no code changes") so I don't reverse-engineer the pattern
14. As a human contributor, I want a file-to-responsibility map so I know which file to modify for a given change without grep-ing through imports

## Implementation Decisions

### Priority 1: Enrichment Pipeline Orchestrator

**Current state:** Understanding indicator enrichment requires reading 6 files:
- `app/services/enrichment.py` (258 lines) — `EnrichmentService` with `enrich_indicator()` and `enrich_alert()`
- `app/services/enrichment_engine.py` (366 lines) — `GenericHttpEnrichmentEngine` with multi-step HTTP execution
- `app/services/field_extractor.py` (121 lines) — `FieldExtractor` with dot-path extraction and type coercion
- `app/services/malice_evaluator.py` (132 lines) — `MaliceRuleEvaluator` with threshold-based verdict rules
- `app/services/enrichment_template.py` (129 lines) — `TemplateResolver` with namespace-based placeholder resolution
- `app/integrations/enrichment/database_provider.py` (278 lines) — `DatabaseDrivenProvider` wrapping engine + auth resolution

The pipeline call graph is: `EnrichmentService` -> `EnrichmentRegistry` -> `DatabaseDrivenProvider` -> `GenericHttpEnrichmentEngine` -> (`TemplateResolver` + `FieldExtractor` + `MaliceRuleEvaluator`). Config schema changes (`http_config`, `malice_rules`, `field_extractions`) break 5+ files.

**Target state:** A single `EnrichmentPipeline` class that encapsulates template resolution, HTTP execution, field extraction, and malice evaluation behind one `async run(indicator_value, indicator_type, provider_config) -> EnrichmentResult` method. The existing `EnrichmentService` becomes thinner — it handles caching and alert-level orchestration, delegating per-indicator work to the pipeline.

**Key design decisions:**
- `FieldExtractor`, `MaliceRuleEvaluator`, and `TemplateResolver` become **private implementation details** of `EnrichmentPipeline`, not standalone modules. They are still separate classes internally for readability, but they move into the pipeline module (or a sub-package) and are not imported by any other module.
- `DatabaseDrivenProvider.enrich()` delegates to `EnrichmentPipeline.run()` instead of `GenericHttpEnrichmentEngine.execute()`. The provider remains the adapter between the registry and the pipeline.
- The `_resolve_dot_path()` helper is currently **duplicated across 3 files** (`field_extractor.py`, `malice_evaluator.py`, `enrichment_template.py`). Consolidate into one private utility within the pipeline module.
- `EnrichmentResult` schema stays in `app/schemas/enrichment.py` — it's the pipeline's output contract and is used by callers.
- Mock mode and debug step capture stay in `DatabaseDrivenProvider` — they're adapter concerns, not pipeline concerns.
- `validate_outbound_url()` (SSRF check) is called by the pipeline during HTTP step execution. It stays as an import from `app/services/url_validation.py` since it's also used by workflow execution.

**What moves where:**

| Current location | Target location | Rationale |
|---|---|---|
| `app/services/enrichment_engine.py` | `app/services/enrichment_pipeline/engine.py` | Core of the pipeline |
| `app/services/field_extractor.py` | `app/services/enrichment_pipeline/field_extractor.py` | Private implementation detail |
| `app/services/malice_evaluator.py` | `app/services/enrichment_pipeline/malice_evaluator.py` | Private implementation detail |
| `app/services/enrichment_template.py` | `app/services/enrichment_pipeline/template_resolver.py` | Private implementation detail |
| (new) | `app/services/enrichment_pipeline/__init__.py` | Exports only `EnrichmentPipeline` class |
| (new) | `app/services/enrichment_pipeline/_dot_path.py` | Shared `resolve_dot_path()` utility |

**Public interface (the only thing callers see):**
```python
class EnrichmentPipeline:
    """Deep module: hides template resolution, HTTP execution, field extraction,
    and malice evaluation behind a single run() method."""

    def __init__(
        self,
        provider_name: str,
        http_config: dict[str, Any],
        malice_rules: dict[str, Any] | None,
        field_extractions: list[dict[str, Any]],
    ) -> None: ...

    async def run(
        self,
        indicator_value: str,
        indicator_type: str,
        auth_config: dict[str, Any],
        *,
        capture_debug: bool = False,
    ) -> EnrichmentResult:
        """Execute the full enrichment pipeline. Never raises."""
        ...
```

This is essentially `GenericHttpEnrichmentEngine.execute()` renamed and promoted to be the pipeline's sole entry point. The engine class may be kept internally or merged — implementation detail.

**Test strategy:**
- New boundary test: `tests/test_enrichment_pipeline.py` tests `EnrichmentPipeline.run()` with real `FieldExtractor`, `MaliceRuleEvaluator`, and `TemplateResolver` instances (no mocks of internals). Uses `httpx.MockTransport` to intercept HTTP calls.
- Existing `test_enrichment_service.py` tests stay — they test cache behavior and alert-level orchestration, which is `EnrichmentService` responsibility.
- Existing `test_enrichment_providers.py` tests stay — they test provider-specific behavior (VT, AbuseIPDB, Okta, Entra) through `DatabaseDrivenProvider`.
- Individual unit tests for `FieldExtractor`, `MaliceRuleEvaluator`, `TemplateResolver` can be **removed or reduced** since the pipeline boundary test covers their behavior in context. Keep only edge-case unit tests if they cover scenarios not reachable through the pipeline boundary.

---

### Priority 2: Task Queue Registry Refactor

**Current state:** `app/queue/registry.py` is 671 lines containing:
- 7 async task functions + 1 periodic task, each registered with `@procrastinate_app.task`
- Every task duplicates the `async with AsyncSessionLocal() as session: try...commit/rollback` pattern (6 instances)
- All imports are inline (inside function bodies) to avoid serialization issues with procrastinate
- One string-based task lookup: `procrastinate_app.tasks.get("dispatch_agent_webhooks")` to avoid circular imports
- Untyped dict payloads — callers pass `{"alert_id": int}` etc. with no schema validation

**The 8 tasks:**

| Task | Queue | Payload | Lines of logic |
|---|---|---|---|
| `enrich_alert` | enrichment | `{alert_id: int}` | ~50 lines |
| `execute_workflow_run` | workflows | `{workflow_run_id: int}` | ~80 lines |
| `send_approval_notification_task` | dispatch | `{approval_request_id: int}` | ~40 lines |
| `execute_approved_workflow_task` | workflows | `{approval_request_id: int}` | ~115 lines |
| `dispatch_agent_webhooks` | dispatch | `{alert_id: int}` | ~55 lines |
| `dispatch_single_agent_webhook` | dispatch | `{alert_id: int, agent_id: int}` | ~60 lines |
| `sandbox_reset` | default | `{timestamp: int}` | ~15 lines (delegates to reset function) |

**Target state:** Each task becomes a typed handler class in `app/queue/handlers/`. The registry becomes a thin registration layer. Session management is extracted into a shared decorator or context manager.

**Key design decisions:**
- **Typed payloads:** Each task defines a Pydantic model for its payload. The `enqueue()` call validates the payload before serialization. The handler receives a validated payload object, not a raw dict.
- **Session management decorator:** A `@with_session` decorator (or async context manager) wraps the common `AsyncSessionLocal() / try / commit / rollback` pattern. Handlers receive the session as a parameter.
- **No more inline imports:** Handler classes live in separate files, so imports are at module level. The registry file imports handler classes — it doesn't contain business logic.
- **String-based task lookup replaced:** The `enrich_alert` handler that needs to enqueue `dispatch_agent_webhooks` receives the queue backend as an injected dependency and calls `queue.enqueue("dispatch_agent_webhooks", ...)` instead of `procrastinate_app.tasks.get(...)`.
- **procrastinate registration stays in registry.py:** The `@procrastinate_app.task` decorators stay in `registry.py`, but each decorated function is a 3-line shim that parses the payload and delegates to the handler class.

**File structure:**
```
app/queue/
  registry.py              # Thin: @task decorators, each delegates to handler
  handlers/
    __init__.py
    base.py                # with_session decorator, BaseTaskHandler ABC (optional)
    enrich_alert.py        # EnrichAlertHandler + EnrichAlertPayload
    execute_workflow.py    # ExecuteWorkflowHandler + payload
    approval_notification.py
    execute_approved.py
    dispatch_webhooks.py   # Both dispatch_agent_webhooks and dispatch_single
    sandbox_reset.py
```

**Payload model example:**
```python
class EnrichAlertPayload(BaseModel):
    alert_id: int

class EnrichAlertHandler:
    async def execute(self, payload: EnrichAlertPayload, session: AsyncSession) -> None:
        # All business logic here, no session management boilerplate
        ...
```

**Registry shim example:**
```python
@procrastinate_app.task(name="enrich_alert", queue="enrichment", retry=...)
async def enrich_alert_task(alert_id: int) -> None:
    payload = EnrichAlertPayload(alert_id=alert_id)
    async with task_session() as session:
        handler = EnrichAlertHandler()
        await handler.execute(payload, session)
```

**Test strategy:**
- Handler classes are testable with a real or mock `AsyncSession` — no need to go through procrastinate
- Integration tests that mock the queue (`MockQueue` in conftest) continue to work unchanged — they test that the right task name is enqueued with the right payload
- New unit tests for each handler class test the business logic directly

---

### Priority 3: Alert Ingestion Pipeline

**Current state:** `AlertIngestionService.ingest()` in `app/services/alert_ingestion.py` (178 lines) performs 8 sequential steps:

1. `source.normalize(raw_payload)` -> `CalsetaAlert`
2. `extract_for_fingerprint(source, normalized, raw_payload, cached_mappings)` -> indicators
3. `generate_fingerprint(title, source_name, indicator_tuples)` -> fingerprint string
4. `alert_repo.find_duplicate(fingerprint, window_start)` -> existing alert or None
5. **Branch A (duplicate):** `alert_repo.increment_duplicate()` + activity event -> return
5. **Branch B (new):** `alert_repo.create(normalized, raw_payload, fingerprint=fingerprint)`
6. `detection_rule_service.associate_detection_rule(alert, source_name, rule_ref)` — best-effort
7. `queue.enqueue("enrich_alert", {"alert_id": alert.id})` — best-effort
8. `activity_service.write(ALERT_INGESTED, ...)` — fire-and-forget

**Problems:**
- Steps 5B (persist) and 7 (enqueue) are not in the same error boundary. If enrichment enqueue fails after persist, the alert exists but has no enrichment task queued. The `enrichment_status` stays `Pending` forever.
- No end-to-end pipeline test exists. Each step is tested separately.
- The `IndicatorExtractionService.extract_and_persist()` (3-pass pipeline, 362 lines) runs during the worker enrichment task, not during ingestion. But `extract_for_fingerprint()` runs 2 of the 3 passes during ingestion for deduplication. This split is correct but not obvious.

**Target state:** The `ingest()` method stays as the orchestrator but gains:
1. **Explicit step results:** An `IngestStepLog` that records which steps succeeded/failed with timing, returned in the `IngestResult` for debugging
2. **Enrichment enqueue retry:** If enqueue fails, the alert is marked with `enrichment_status=Failed` and a structured log is emitted with enough context for a human or monitoring system to re-trigger
3. **End-to-end pipeline test:** A single test that ingests an alert, runs the enrichment task (with mocked HTTP), and verifies the indicator is enriched and the agent webhook is dispatched

**Key design decisions:**
- This is NOT a rewrite of `AlertIngestionService`. The 8-step structure is correct. The changes are:
  - Add `enrichment_status=Failed` marking when enqueue fails (currently it stays `Pending`)
  - Add structured step logging for observability
  - Write the missing end-to-end test
- The `IndicatorExtractionService` stays separate — it's called by the worker task, not by ingestion. The 2-pass fingerprint extraction during ingestion is a different code path with different error handling (no persistence).
- `extract_for_fingerprint()` is a module-level function, not a method on `IndicatorExtractionService`. This is correct — it doesn't need a DB session.

**Test strategy:**
- New `tests/test_ingest_pipeline_e2e.py` that:
  1. Posts a raw alert payload to `POST /v1/ingest/elastic`
  2. Asserts 202 response with alert UUID
  3. Runs the `enrich_alert` task handler directly (from Priority 2 refactor)
  4. Asserts indicators are created and enriched (mock HTTP for providers)
  5. Runs the `dispatch_agent_webhooks` task handler
  6. Asserts webhook was dispatched (mock HTTP)
- This test catches seam bugs that unit tests miss

---

### Priority 4: Repository Base Class

**Current state:** 16 repository files (~1947 lines) with these duplicated patterns:

1. **Constructor:** `def __init__(self, db: AsyncSession)` — identical across all repos
2. **`get_by_uuid(uuid)`** — implemented in 7 repos with identical logic: `select(Model).where(Model.uuid == uuid)` -> `scalar_one_or_none()`
3. **Pagination:** `list_xxx(page, page_size, ...)` -> `tuple[list[Model], int]` — offset/limit + count query, duplicated in 8 repos
4. **Patch:** Two styles — explicit kwargs (alert, workflow) vs. `_UPDATABLE_FIELDS` frozenset (agent, source)
5. **Delete:** `session.delete(obj); session.flush()` — identical across all repos

**Target state:** A generic `BaseRepository[ModelT]` that provides:

```python
class BaseRepository(Generic[ModelT]):
    model: type[ModelT]  # Set by subclass

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, id: int) -> ModelT | None: ...
    async def get_by_uuid(self, uuid: UUID) -> ModelT | None: ...
    async def count(self, *filters) -> int: ...
    async def paginate(
        self,
        *filters,
        order_by=None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ModelT], int]: ...
    async def delete(self, obj: ModelT) -> None: ...
    async def flush_and_refresh(self, obj: ModelT) -> ModelT: ...
```

**Key design decisions:**
- `BaseRepository` is opt-in — existing repos inherit from it but keep all their custom methods. This is additive, not destructive.
- The `paginate()` method accepts SQLAlchemy filter expressions (e.g., `Model.status == "Open"`) and an optional `order_by` clause. Each repo's `list_xxx()` method calls `self.paginate(...)` with entity-specific filters.
- The `_UPDATABLE_FIELDS` patch pattern is NOT extracted into the base — it's too entity-specific. Repos keep their own `patch()` methods.
- The PostgreSQL upsert pattern stays in `IndicatorRepository` — it uses `pg_insert().on_conflict_do_update()` which is specific to the `(type, value)` uniqueness constraint.
- Existing `BaseRepository` in `app/repositories/base.py` (19 lines, rarely used) is expanded rather than replaced.

**Test strategy:**
- New `tests/test_base_repository.py` tests the generic methods against a simple test model
- Existing repo tests continue to pass — the base class doesn't change behavior, just eliminates duplication

---

### Priority 5: API Route Utilities

**Current state:** 19 route files, each importing 10-25 modules. Every list endpoint repeats this pattern:

```python
@router.get("", response_model=PaginatedResponse[SummarySchema])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_entities(
    request: Request,
    auth: Annotated[AuthContext, Depends(require_scope(Scope.XXX_READ))],
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    sort_by: str | None = Query(None),
    sort_order: str = Query("desc"),
    # ... entity-specific filters ...
) -> PaginatedResponse[SummarySchema]:
    repo = EntityRepository(db)
    items, total = await repo.list_entities(
        page=pagination.page,
        page_size=pagination.page_size,
        sort_by=sort_by,
        sort_order=sort_order,
        # ... filters ...
    )
    return PaginatedResponse(
        data=[SummarySchema.model_validate(item) for item in items],
        meta=PaginationMeta.from_total(total=total, page=pagination.page, page_size=pagination.page_size),
    )
```

And every detail endpoint repeats:
```python
@router.get("/{uuid}", response_model=DataResponse[DetailSchema])
@limiter.limit(...)
async def get_entity(
    request: Request,
    uuid: UUID,
    auth: _Read,
    db: AsyncSession,
) -> DataResponse[DetailSchema]:
    repo = EntityRepository(db)
    entity = await repo.get_by_uuid(uuid)
    if not entity:
        raise CalsetaException(code="NOT_FOUND", message="...", status_code=404)
    return DataResponse(data=DetailSchema.model_validate(entity))
```

**Target state:** Shared utility functions that eliminate the boilerplate:

```python
async def paginated_list(
    repo_class: type[BaseRepository[T]],
    summary_schema: type[BaseModel],
    db: AsyncSession,
    pagination: PaginationParams,
    *,
    filters: list = None,
    order_by=None,
) -> PaginatedResponse:
    repo = repo_class(db)
    items, total = await repo.paginate(*filters, order_by=order_by, page=pagination.page, page_size=pagination.page_size)
    return PaginatedResponse(
        data=[summary_schema.model_validate(item) for item in items],
        meta=PaginationMeta.from_total(total=total, page=pagination.page, page_size=pagination.page_size),
    )

async def get_or_404(
    repo_class: type[BaseRepository[T]],
    detail_schema: type[BaseModel],
    db: AsyncSession,
    uuid: UUID,
    entity_name: str = "Resource",
) -> DataResponse:
    repo = repo_class(db)
    entity = await repo.get_by_uuid(uuid)
    if not entity:
        raise CalsetaException(code="NOT_FOUND", message=f"{entity_name} not found.", status_code=404)
    return DataResponse(data=detail_schema.model_validate(entity))
```

**Key design decisions:**
- These are utility functions in `app/api/utils.py`, not base classes. Route handlers call them explicitly.
- Routes that need custom logic (e.g., `alerts.py` with enrichment result filtering, `_metadata` block) don't use the utilities — they keep their custom implementation.
- Auth and rate limiting stay as decorators/dependencies on the route functions — they're not part of the utilities.
- This depends on Priority 4 (BaseRepository) for the `paginate()` and `get_by_uuid()` methods.

**Test strategy:**
- Existing integration tests for all routes continue to pass
- No new tests needed for the utilities themselves — they're thin wrappers

---

### Priority 6: Shallow Utility Consolidation

**Current state:** Four single-function modules that are each called from exactly one service:

| Module | Function | Lines | Called from |
|---|---|---|---|
| `app/services/indicator_validation.py` | `is_enrichable(indicator_type, value)` | 94 | `app/services/enrichment.py` |
| `app/services/url_validation.py` | `validate_outbound_url(url)` / `is_safe_outbound_url(url)` | 116 | `app/services/enrichment_engine.py` (-> pipeline) |
| `app/services/context_targeting.py` | `get_applicable_documents(alert, db)` | 169 | `app/api/v1/alerts.py` (context endpoint) |
| `app/services/agent_trigger.py` | `get_matching_agents(alert, db)` | 67 | `app/queue/registry.py` (dispatch task) |

**Target state:**
- `indicator_validation.py` -> private method `_is_enrichable()` in `enrichment.py` (or the enrichment pipeline module)
- `url_validation.py` -> stays as-is. It's called from the enrichment pipeline AND potentially from workflow execution. It's a genuine cross-cutting utility.
- `context_targeting.py` -> stays as-is. While called from one route today, it's a query helper that may be called from MCP or other routes in v2.
- `agent_trigger.py` -> inline into the dispatch webhook handler (from Priority 2 refactor)

**Revised scope:** Only `indicator_validation.py` and `agent_trigger.py` are true candidates for inlining. `url_validation.py` and `context_targeting.py` stay.

**Key design decisions:**
- `is_enrichable()` moves into the enrichment pipeline module as a private function. Its logic (RFC 1918 checks, internal domain checks) is enrichment-specific.
- `get_matching_agents()` moves into `DispatchWebhooksHandler` (from Priority 2) as a private method. It's only called during webhook dispatch.
- The original files are deleted after migration, not left as re-exports.

**Test strategy:**
- Tests that import `is_enrichable` or `get_matching_agents` are updated to test through their parent module's boundary
- This is the lowest-risk change in the entire PRD

---

### Priority 7: AGENTS.md Navigation System

**Current state:** An AI agent starting work on the enrichment pipeline has no navigation aid. It must:
1. Read the root `CLAUDE.md` (~500 lines) for project context
2. Explore `app/services/` to find relevant files
3. Read 5-6 files (~800 lines) to trace the call graph
4. Infer seam points and error handling from code

This burns ~1500 tokens on orientation before a single useful action. Every new conversation repeats this.

**Target state:** Three `AGENTS.md` files at service layer boundaries. Each is 50-100 lines with a fixed structure:

1. **`app/services/AGENTS.md`** — Service layer orchestration
2. **`app/queue/AGENTS.md`** — Task execution flows
3. **`app/api/v1/AGENTS.md`** — Route-to-service mapping

**Fixed structure per file:**

```markdown
# [Layer Name] — Agent Navigation

## Pipelines

### [Pipeline Name]
- Entry: `file.py:Class.method()`
- Steps: step1 → step2 → step3
- Call graph: A → B → C → (D + E)
- Key seams: [where bugs hide, what can fail between steps]
- To debug: [where to start, what to check first]
- To extend: [how to add a new X without breaking Y]

## File → Responsibility Map
| File | Owns | Calls |
|------|------|-------|
| file.py | Description | Dependencies |
```

**What goes in each file:**

**`app/services/AGENTS.md`** covers:
- Alert Ingestion pipeline (8 steps, entry point, seam between persist and enqueue)
- Enrichment pipeline (EnrichmentService → Registry → Provider → Pipeline, cache-first strategy)
- Indicator Extraction (3-pass pipeline, fingerprint vs persist paths)
- Workflow Execution (context building, sandbox, approval gate)
- File → responsibility map for all service files

**`app/queue/AGENTS.md`** covers:
- All 7 task handlers with payload schemas
- Session management pattern
- Task-to-task chaining (enrich_alert → dispatch_agent_webhooks)
- Retry and error handling per task
- How to add a new task type

**`app/api/v1/AGENTS.md`** covers:
- Route → service → repo mapping for each endpoint group
- Shared patterns (auth, pagination, response envelope, rate limiting)
- Which routes have custom logic vs. standard CRUD
- How to add a new CRUD entity endpoint

**Key design decisions:**
- `AGENTS.md` is the name, not `CONTEXT.md`. CONTEXT.md files already exist per the Wave 8 spec and document component contracts. AGENTS.md documents *navigation and orchestration* — how an AI agent should move through the code.
- Max 100 lines per file. If it's longer, the directory scope is too broad.
- No code snippets longer than 3 lines. This isn't documentation — it's a map.
- Updated as part of each refactoring chunk. When the enrichment pipeline moves to a sub-package, `app/services/AGENTS.md` is updated to reflect the new entry point.
- These files are checked into git and maintained alongside the code. Stale navigation docs are worse than none.

**Test strategy:**
- No automated tests. These are documentation files.
- Acceptance criteria is review-based: an AI agent reading only the AGENTS.md file should be able to correctly answer "which file do I modify to change X?" for any pipeline.

## Testing Strategy

### Types of Tests

1. **Pipeline boundary tests (new):** Test entire pipelines through their public interface with real internal components, mocking only external I/O (HTTP, database). These catch seam bugs.
   - `test_enrichment_pipeline.py` — tests `EnrichmentPipeline.run()` with mock HTTP
   - `test_ingest_pipeline_e2e.py` — tests ingest -> enrich -> dispatch with mock HTTP

2. **Handler unit tests (new):** Test task handler classes with injected mock sessions.
   - One test file per handler in `tests/test_queue_handlers/`

3. **Base repository tests (new):** Test generic `BaseRepository[T]` methods against a test model.
   - `test_base_repository.py`

4. **Existing tests (preserved):** All existing integration and unit tests continue to pass. Import paths that change (e.g., `from app.services.field_extractor import FieldExtractor` -> `from app.services.enrichment_pipeline.field_extractor import FieldExtractor`) are updated.

### Test Patterns Already in Codebase
- `httpx.MockTransport` for HTTP mocking (used in enrichment provider tests)
- `AsyncMock` for DB sessions (used in service tests)
- `MockQueue` in `tests/conftest.py` for queue testing
- Real PostgreSQL via Docker for integration tests

### Coverage Goals
- Every pipeline boundary (enrichment, ingestion) has at least one end-to-end test
- Every task handler has unit tests for happy path and error paths
- `BaseRepository` generic methods have edge-case tests (empty results, no match, pagination boundaries)

## Out of Scope

- **Behavior changes**: This is a pure refactor. No new features, no API changes, no schema changes.
- **Database migrations**: No schema changes. All changes are code-level.
- **New abstractions beyond what's described**: No event bus, no middleware, no generic plugin framework.
- **Route handler rewrites**: Routes that have custom logic (alerts detail with `_metadata`, workflow execute with approval gate) keep their custom implementations.
- **Enrichment provider changes**: `DatabaseDrivenProvider`, `EnrichmentRegistry`, and the 4 builtin provider seeds are unchanged in behavior.
- **MCP server changes**: The MCP server is a thin adapter over REST and is not touched.
- **CI/CD changes**: No pipeline changes needed.

## Open Questions

1. **Should `EnrichmentPipeline` be a sub-package or a single file?** The combined logic is ~750 lines. A sub-package with `__init__.py` + 4 internal files keeps each file under 200 lines. A single file is simpler to navigate but longer. **Recommendation:** Sub-package, since the goal is module deepening (small public interface, large internal implementation).

2. **Should task handlers use a base class or just a protocol?** A `BaseTaskHandler` ABC adds formality but little value since each handler's `execute()` signature differs (different payloads, different session needs). **Recommendation:** No base class. Just a `@with_session` decorator and typed payload models.

3. **Should `BaseRepository.paginate()` accept raw SQLAlchemy expressions or a filter builder?** Raw expressions are simpler and match existing patterns. A filter builder adds abstraction without clear benefit. **Recommendation:** Raw SQLAlchemy expressions.

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Import path changes break existing tests | High | Low | Automated find-and-replace; CI catches any misses |
| Enrichment pipeline refactor introduces subtle behavior change | Medium | High | Pipeline boundary test written FIRST (red-green-refactor); all existing provider tests must pass |
| Task handler refactor breaks procrastinate task discovery | Medium | High | Registry shims call handlers; procrastinate decorators unchanged; worker startup test validates all tasks registered |
| BaseRepository generic methods don't cover all repo-specific query patterns | Low | Low | BaseRepository is opt-in; repos keep custom methods |
| File contention between parallel agents | Medium | Medium | Wave structure ensures no two chunks touch the same files |

## Project Management

### Overview

| Chunk | Wave | Status | Dependencies | Files Touched |
|-------|------|--------|-------------|---------------|
| 1.1 Enrichment Pipeline Package | 1 | pending | — | `app/services/enrichment_pipeline/` (new), `app/services/enrichment_engine.py`, `app/services/field_extractor.py`, `app/services/malice_evaluator.py`, `app/services/enrichment_template.py` |
| 1.2 Wire Pipeline to Provider | 2 | pending | 1.1 | `app/integrations/enrichment/database_provider.py`, `app/services/enrichment.py` |
| 1.3 Pipeline Boundary Tests | 2 | pending | 1.1 | `tests/test_enrichment_pipeline.py` (new) |
| 1.4 Cleanup Old Files & Update Imports | 3 | pending | 1.2, 1.3, 7.1 | Delete old files, update imports across codebase, update AGENTS.md |
| 2.1 Task Session Decorator + Payload Models | 1 | pending | — | `app/queue/handlers/` (new) |
| 2.2 Extract Task Handlers | 2 | pending | 2.1 | `app/queue/handlers/*.py`, `app/queue/registry.py` |
| 2.3 Task Handler Tests | 2 | pending | 2.1 | `tests/test_queue_handlers/` (new) |
| 3.1 Ingestion Error Recovery | 1 | pending | — | `app/services/alert_ingestion.py` |
| 3.2 E2E Pipeline Test | 3 | pending | 2.2, 3.1 | `tests/test_ingest_pipeline_e2e.py` (new) |
| 4.1 BaseRepository Generic | 1 | pending | — | `app/repositories/base.py` |
| 4.2 Migrate Repositories | 2 | pending | 4.1 | `app/repositories/*.py` (all 16) |
| 4.3 BaseRepository Tests | 2 | pending | 4.1 | `tests/test_base_repository.py` (new) |
| 5.1 Route Utility Functions | 3 | pending | 4.2 | `app/api/utils.py` (new), `app/api/v1/*.py` (subset) |
| 6.1 Inline Shallow Utilities | 3 | pending | 1.4, 2.2 | `app/services/indicator_validation.py`, `app/services/agent_trigger.py` |
| 7.1 AGENTS.md Navigation Files | 1 | pending | — | `app/services/AGENTS.md` (new), `app/queue/AGENTS.md` (new), `app/api/v1/AGENTS.md` (new) |

### Wave 1 — Foundation (5 chunks, all parallel)

All chunks create new files or modify isolated files with no overlap.

#### Chunk 1.1: Enrichment Pipeline Package
- **What**: Create `app/services/enrichment_pipeline/` package. Move `GenericHttpEnrichmentEngine`, `FieldExtractor`, `MaliceRuleEvaluator`, `TemplateResolver` into the package. Consolidate duplicated `_resolve_dot_path()`. Export `EnrichmentPipeline` from `__init__.py`.
- **Why this wave**: No dependencies. Creates new files only (old files still exist and work).
- **Modules touched**: `app/services/enrichment_pipeline/__init__.py` (new), `app/services/enrichment_pipeline/engine.py` (moved from `app/services/enrichment_engine.py`), `app/services/enrichment_pipeline/field_extractor.py` (moved from `app/services/field_extractor.py`), `app/services/enrichment_pipeline/malice_evaluator.py` (moved from `app/services/malice_evaluator.py`), `app/services/enrichment_pipeline/template_resolver.py` (moved from `app/services/enrichment_template.py`), `app/services/enrichment_pipeline/_dot_path.py` (new shared utility)
- **Depends on**: None
- **Produces**: `EnrichmentPipeline` class importable from `app.services.enrichment_pipeline`
- **Acceptance criteria**:
  - [ ] `app/services/enrichment_pipeline/` package exists with `__init__.py` exporting `EnrichmentPipeline`
  - [ ] `EnrichmentPipeline.run()` accepts `(indicator_value, indicator_type, auth_config, *, capture_debug)` and returns `EnrichmentResult`
  - [ ] Internal classes (`FieldExtractor`, `MaliceRuleEvaluator`, `TemplateResolver`) are not importable from outside the package (not in `__init__.py` exports)
  - [ ] `_resolve_dot_path()` is consolidated into `_dot_path.py` and used by all 3 internal classes
  - [ ] Old files (`enrichment_engine.py`, `field_extractor.py`, `malice_evaluator.py`, `enrichment_template.py`) still exist with backward-compatible re-exports (temporary, removed in 1.4)
  - [ ] `ruff check app/services/enrichment_pipeline/` passes
  - [ ] `mypy app/services/enrichment_pipeline/` passes
- **Verification**: `python -c "from app.services.enrichment_pipeline import EnrichmentPipeline; print('OK')"` succeeds

#### Chunk 2.1: Task Session Decorator + Payload Models
- **What**: Create `app/queue/handlers/` package with `base.py` (session management decorator/context manager) and payload Pydantic models for all 7 tasks.
- **Why this wave**: No dependencies. Creates new files only.
- **Modules touched**: `app/queue/handlers/__init__.py` (new), `app/queue/handlers/base.py` (new — `task_session()` async context manager), `app/queue/handlers/payloads.py` (new — all 7 payload models)
- **Depends on**: None
- **Produces**: `task_session()` context manager, 7 payload models (`EnrichAlertPayload`, `ExecuteWorkflowPayload`, etc.)
- **Acceptance criteria**:
  - [ ] `task_session()` async context manager opens `AsyncSessionLocal`, yields session, commits on success, rolls back on exception
  - [ ] 7 Pydantic payload models defined with typed fields matching current dict payloads
  - [ ] `ruff check app/queue/handlers/` passes
  - [ ] `mypy app/queue/handlers/` passes
- **Verification**: `python -c "from app.queue.handlers.base import task_session; from app.queue.handlers.payloads import EnrichAlertPayload; print('OK')"` succeeds

#### Chunk 3.1: Ingestion Error Recovery
- **What**: In `AlertIngestionService.ingest()`, add `enrichment_status=Failed` marking when enrichment enqueue fails. Add structured step timing to `IngestResult`.
- **Why this wave**: Modifies only `app/services/alert_ingestion.py` — no overlap with other Wave 1 chunks.
- **Modules touched**: `app/services/alert_ingestion.py`
- **Depends on**: None
- **Produces**: Updated `ingest()` that marks `enrichment_status=Failed` on enqueue failure; `IngestResult` with optional `step_log` dict
- **Acceptance criteria**:
  - [ ] When `queue.enqueue("enrich_alert", ...)` raises, alert's `enrichment_status` is set to `"Failed"` via `alert_repo.patch()`
  - [ ] Structured log includes `enrichment_enqueue_failed` with `alert_id` and `alert_uuid`
  - [ ] `IngestResult` has optional `step_log: dict[str, float] | None` with step names and durations in ms
  - [ ] Existing ingest tests pass without modification
  - [ ] `ruff check app/services/alert_ingestion.py` passes
- **Verification**: `pytest tests/test_ingestion.py -x` passes; manually verify that a failing queue mock results in `enrichment_status=Failed`

#### Chunk 4.1: BaseRepository Generic
- **What**: Expand `app/repositories/base.py` into a generic `BaseRepository[ModelT]` with `get_by_id()`, `get_by_uuid()`, `count()`, `paginate()`, `delete()`, `flush_and_refresh()`.
- **Why this wave**: Modifies only `app/repositories/base.py` — no overlap with other chunks.
- **Modules touched**: `app/repositories/base.py`
- **Depends on**: None
- **Produces**: `BaseRepository[ModelT]` class with generic CRUD/pagination methods
- **Acceptance criteria**:
  - [ ] `BaseRepository` is generic over `ModelT` (SQLAlchemy model type)
  - [ ] `get_by_id(id: int)` returns `ModelT | None`
  - [ ] `get_by_uuid(uuid: UUID)` returns `ModelT | None` (only if model has `uuid` column)
  - [ ] `paginate(*filters, order_by, page, page_size)` returns `tuple[list[ModelT], int]`
  - [ ] `count(*filters)` returns `int`
  - [ ] `delete(obj)` calls `session.delete()` and `flush()`
  - [ ] `flush_and_refresh(obj)` calls `session.flush()` and `session.refresh()`
  - [ ] Existing repos that inherit from `BaseRepository` continue to work
  - [ ] `ruff check app/repositories/base.py` passes
  - [ ] `mypy app/repositories/base.py` passes
- **Verification**: `python -c "from app.repositories.base import BaseRepository; print('OK')"` succeeds

#### Chunk 7.1: AGENTS.md Navigation Files
- **What**: Create `AGENTS.md` files at three service layer boundaries documenting pipelines, call graphs, seam points, troubleshooting paths, extension patterns, and file-to-responsibility maps.
- **Why this wave**: No dependencies. Creates 3 new documentation files only — no code changes, no overlap with other chunks.
- **Modules touched**: `app/services/AGENTS.md` (new), `app/queue/AGENTS.md` (new), `app/api/v1/AGENTS.md` (new)
- **Depends on**: None
- **Produces**: AI-navigable documentation for all major pipelines and layers
- **Acceptance criteria**:
  - [ ] `app/services/AGENTS.md` exists and documents: Alert Ingestion pipeline (8 steps with entry point and seam points), Enrichment pipeline (full call graph from EnrichmentService through Pipeline), Indicator Extraction (3-pass with fingerprint vs persist distinction), Workflow Execution (context building, sandbox, approval gate), and a file → responsibility map for all service files
  - [ ] `app/queue/AGENTS.md` exists and documents: all 7 task handlers with payload key types, session management pattern, task-to-task chaining (enrich_alert → dispatch_agent_webhooks), retry/error behavior per task, and "how to add a new task type" recipe
  - [ ] `app/api/v1/AGENTS.md` exists and documents: route → service → repo mapping for each endpoint group, shared patterns (auth dependency, pagination, response envelope, rate limiting), which routes have custom logic vs standard CRUD, and "how to add a new CRUD entity" recipe
  - [ ] Each file is under 100 lines
  - [ ] No code snippets longer than 3 lines
  - [ ] An AI agent reading only the AGENTS.md file can correctly identify which file to modify for: adding a new enrichment step, changing alert status transitions, adding a new task type, adding a new CRUD endpoint
- **Verification**: Manual review — read each file and verify the call graphs and file maps are accurate against the current codebase

### Wave 2 — Integration (5 chunks)

Begins after all Wave 1 chunks complete.

#### Chunk 1.2: Wire Pipeline to Provider
- **What**: Update `DatabaseDrivenProvider.enrich()` to use `EnrichmentPipeline.run()` instead of `GenericHttpEnrichmentEngine.execute()`. Update `EnrichmentService` imports.
- **Why this wave**: Depends on Chunk 1.1 (pipeline package must exist).
- **Modules touched**: `app/integrations/enrichment/database_provider.py`, `app/services/enrichment.py`
- **Depends on**: 1.1
- **Produces**: `DatabaseDrivenProvider` using `EnrichmentPipeline`; `EnrichmentService` unchanged in behavior
- **Acceptance criteria**:
  - [ ] `DatabaseDrivenProvider.__init__()` creates `EnrichmentPipeline` instead of `GenericHttpEnrichmentEngine`
  - [ ] `DatabaseDrivenProvider.enrich()` calls `self._pipeline.run()` instead of `self._engine.execute()`
  - [ ] `DatabaseDrivenProvider.enrich_with_debug()` calls `self._pipeline.run(capture_debug=True)`
  - [ ] All existing enrichment provider tests pass: `pytest tests/test_enrichment_providers.py -x`
  - [ ] All existing enrichment service tests pass: `pytest tests/test_enrichment_service.py -x`
  - [ ] All existing enrichment API tests pass: `pytest tests/test_enrichment/ -x`
- **Verification**: `pytest tests/test_enrichment_providers.py tests/test_enrichment_service.py tests/test_enrichment/ -x`

#### Chunk 1.3: Pipeline Boundary Tests
- **What**: Write boundary tests for `EnrichmentPipeline.run()` that test the full pipeline with real internal components and mock HTTP.
- **Why this wave**: Depends on Chunk 1.1 (pipeline must exist to test it).
- **Modules touched**: `tests/test_enrichment_pipeline.py` (new)
- **Depends on**: 1.1
- **Produces**: Pipeline boundary tests that catch seam bugs
- **Acceptance criteria**:
  - [ ] Tests cover: single-step provider, multi-step provider, field extraction with type coercion, malice rule evaluation (all 4 verdicts), template resolution with step references, SSRF rejection, 404/not-found handling, timeout handling, optional step failure
  - [ ] All tests use real `FieldExtractor`, `MaliceRuleEvaluator`, `TemplateResolver` — no mocks of internals
  - [ ] HTTP calls intercepted via `httpx.MockTransport` or `respx`
  - [ ] Tests verify that the combined pipeline produces correct `EnrichmentResult` with `extracted`, `raw`, and `malice` fields
  - [ ] `pytest tests/test_enrichment_pipeline.py -x` passes
- **Verification**: `pytest tests/test_enrichment_pipeline.py -v`

#### Chunk 2.2: Extract Task Handlers
- **What**: Move business logic from each task function in `registry.py` into handler classes in `app/queue/handlers/`. Replace task functions with 3-line shims.
- **Why this wave**: Depends on Chunk 2.1 (session decorator and payload models must exist).
- **Modules touched**: `app/queue/registry.py` (shrinks to ~100 lines of shims), `app/queue/handlers/enrich_alert.py` (new), `app/queue/handlers/execute_workflow.py` (new), `app/queue/handlers/approval_notification.py` (new), `app/queue/handlers/execute_approved.py` (new), `app/queue/handlers/dispatch_webhooks.py` (new), `app/queue/handlers/sandbox_reset.py` (new)
- **Depends on**: 2.1
- **Produces**: 6 handler files with business logic; `registry.py` reduced to thin shims
- **Acceptance criteria**:
  - [ ] `registry.py` is under 150 lines (currently 671)
  - [ ] Each task function in `registry.py` is a 3-5 line shim: parse payload, open session, call handler
  - [ ] All inline imports moved to module-level imports in handler files
  - [ ] String-based task lookup (`procrastinate_app.tasks.get("dispatch_agent_webhooks")`) replaced with `queue.enqueue()` call in `EnrichAlertHandler`
  - [ ] All existing integration tests pass (they mock the queue, not the handlers)
  - [ ] `ruff check app/queue/` passes
  - [ ] `mypy app/queue/` passes
- **Verification**: `pytest tests/ -x` (full test suite passes)

#### Chunk 2.3: Task Handler Tests
- **What**: Write unit tests for each handler class.
- **Why this wave**: Depends on Chunk 2.1 (handlers must exist to test them). Can run in parallel with 2.2 if handler interfaces are stable.
- **Modules touched**: `tests/test_queue_handlers/` (new directory with test files)
- **Depends on**: 2.2
- **Produces**: Unit tests for all 6 handler classes
- **Acceptance criteria**:
  - [ ] Each handler has tests for: happy path, database error, and handler-specific edge cases
  - [ ] `EnrichAlertHandler` tests: successful enrichment, alert not found, extraction failure (continues to enrichment), enrichment failure (marks alert failed)
  - [ ] `ExecuteWorkflowHandler` tests: successful execution, workflow not found, execution failure (recorded in run)
  - [ ] `DispatchWebhooksHandler` tests: successful dispatch, no matching agents, webhook delivery failure (per-agent isolation)
  - [ ] Tests use `AsyncMock` for session and real payload models
  - [ ] `pytest tests/test_queue_handlers/ -x` passes
- **Verification**: `pytest tests/test_queue_handlers/ -v`

#### Chunk 4.2: Migrate Repositories
- **What**: Update all 16 repository files to inherit from `BaseRepository[ModelT]`. Replace duplicated `get_by_uuid()`, pagination logic, and `delete()` with base class calls.
- **Why this wave**: Depends on Chunk 4.1 (base class must exist).
- **Modules touched**: All files in `app/repositories/` (16 files)
- **Depends on**: 4.1
- **Produces**: Slimmer repository files using inherited methods
- **Acceptance criteria**:
  - [ ] All repositories inherit from `BaseRepository[ModelT]` with `model = ModelClass` set
  - [ ] `get_by_uuid()` removed from repos that had identical implementations (at least 7 repos)
  - [ ] Pagination logic in `list_xxx()` methods uses `self.paginate()` from base
  - [ ] `delete()` removed from repos that had identical implementations
  - [ ] Total repository code reduced by at least 200 lines
  - [ ] All existing tests pass: `pytest tests/ -x`
  - [ ] `ruff check app/repositories/` passes
  - [ ] `mypy app/repositories/` passes
- **Verification**: `pytest tests/ -x` (full test suite)

#### Chunk 4.3: BaseRepository Tests
- **What**: Write tests for `BaseRepository` generic methods.
- **Why this wave**: Depends on Chunk 4.1.
- **Modules touched**: `tests/test_base_repository.py` (new)
- **Depends on**: 4.1
- **Produces**: Tests covering all BaseRepository methods
- **Acceptance criteria**:
  - [ ] Tests cover: `get_by_id` (found, not found), `get_by_uuid` (found, not found), `paginate` (first page, last page, empty, filters, ordering), `count` (with and without filters), `delete`, `flush_and_refresh`
  - [ ] Tests use a real async session with test database OR mock session with appropriate expectations
  - [ ] `pytest tests/test_base_repository.py -x` passes
- **Verification**: `pytest tests/test_base_repository.py -v`

### Wave 3 — Cleanup & Polish (4 chunks)

Begins after Wave 2 completes.

#### Chunk 1.4: Cleanup Old Enrichment Files & Update Imports
- **What**: Delete the old standalone files (`enrichment_engine.py`, `field_extractor.py`, `malice_evaluator.py`, `enrichment_template.py`). Update all imports across the codebase to use the new `app.services.enrichment_pipeline` package. Update test imports. Update `app/services/AGENTS.md` to reflect new enrichment pipeline entry point.
- **Why this wave**: Must wait until 1.2 (provider wired to pipeline) and 1.3 (new tests written) are complete.
- **Modules touched**: Delete 4 files in `app/services/`. Update imports in `app/integrations/enrichment/database_provider.py`, test files, any other importers. Update `app/services/AGENTS.md`.
- **Depends on**: 1.2, 1.3, 7.1
- **Produces**: Clean import graph with no backward-compatible re-exports; updated navigation docs
- **Acceptance criteria**:
  - [ ] `app/services/enrichment_engine.py` deleted
  - [ ] `app/services/field_extractor.py` deleted
  - [ ] `app/services/malice_evaluator.py` deleted
  - [ ] `app/services/enrichment_template.py` deleted
  - [ ] No file in the codebase imports from the deleted paths
  - [ ] `app/services/AGENTS.md` enrichment pipeline section updated to reference `enrichment_pipeline/` package
  - [ ] All tests pass: `pytest tests/ -x`
  - [ ] `ruff check app/` passes
  - [ ] `mypy app/` passes
- **Verification**: `pytest tests/ -x && ruff check app/ && mypy app/`

#### Chunk 3.2: E2E Pipeline Test
- **What**: Write an end-to-end test that exercises ingest -> enrich -> dispatch with mock HTTP.
- **Why this wave**: Depends on 2.2 (task handlers must be extracted to call them directly) and 3.1 (ingestion error recovery).
- **Modules touched**: `tests/test_ingest_pipeline_e2e.py` (new)
- **Depends on**: 2.2, 3.1
- **Produces**: End-to-end pipeline test
- **Acceptance criteria**:
  - [ ] Test posts a raw Elastic alert payload to `POST /v1/ingest/elastic`
  - [ ] Asserts 202 response with `is_duplicate=False`
  - [ ] Extracts `alert_id` from response and runs `EnrichAlertHandler.execute()` directly
  - [ ] Mock HTTP returns VT and AbuseIPDB responses
  - [ ] Asserts indicators are created in DB with enrichment results and correct malice verdicts
  - [ ] Runs `DispatchWebhooksHandler.execute()` with a pre-registered agent
  - [ ] Asserts webhook HTTP call was made with correct payload
  - [ ] Test uses real DB (test PostgreSQL) and mock HTTP
  - [ ] `pytest tests/test_ingest_pipeline_e2e.py -x` passes
- **Verification**: `pytest tests/test_ingest_pipeline_e2e.py -v`

#### Chunk 5.1: Route Utility Functions
- **What**: Create `app/api/utils.py` with `paginated_list()` and `get_or_404()` helpers. Migrate 3-4 simple route files to use them as proof of concept (e.g., `detection_rules.py`, `sources.py`, `indicators.py`).
- **Why this wave**: Depends on 4.2 (repositories must have `paginate()` method from BaseRepository).
- **Modules touched**: `app/api/utils.py` (new), `app/api/v1/detection_rules.py`, `app/api/v1/sources.py`, `app/api/v1/indicators.py`
- **Depends on**: 4.2
- **Produces**: Shared route utilities, 3-4 simplified route files
- **Acceptance criteria**:
  - [ ] `paginated_list()` accepts repo class, schema class, session, pagination, optional filters and ordering
  - [ ] `get_or_404()` accepts repo class, schema class, session, UUID, entity name
  - [ ] At least 3 route files use the new utilities
  - [ ] Migrated routes have fewer lines than before
  - [ ] All existing integration tests for migrated routes pass
  - [ ] `ruff check app/api/` passes
- **Verification**: `pytest tests/integration/ -x`

#### Chunk 6.1: Inline Shallow Utilities
- **What**: Move `is_enrichable()` into the enrichment pipeline module. Move `get_matching_agents()` into `DispatchWebhooksHandler`. Delete the original files. Update imports and tests.
- **Why this wave**: Depends on 1.4 (enrichment pipeline cleanup) and 2.2 (dispatch handler exists).
- **Modules touched**: `app/services/indicator_validation.py` (delete), `app/services/agent_trigger.py` (delete), `app/services/enrichment_pipeline/` or `app/services/enrichment.py`, `app/queue/handlers/dispatch_webhooks.py`
- **Depends on**: 1.4, 2.2
- **Produces**: Two fewer files; logic inlined into parent modules
- **Acceptance criteria**:
  - [ ] `app/services/indicator_validation.py` deleted
  - [ ] `app/services/agent_trigger.py` deleted
  - [ ] `is_enrichable()` accessible as private function in enrichment module
  - [ ] `get_matching_agents()` accessible as private method in `DispatchWebhooksHandler`
  - [ ] No file imports from deleted paths
  - [ ] All tests pass: `pytest tests/ -x`
- **Verification**: `pytest tests/ -x && ruff check app/`
