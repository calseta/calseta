# Service Layer Conventions

## What This Component Does

The service layer (`app/services/`) contains all business logic for the Calseta platform. It sits between route handlers (which parse HTTP and return envelopes) and repositories (which execute database queries). Services orchestrate multi-step operations — alert ingestion, enrichment pipelines, workflow execution, agent dispatch, metric computation — and coordinate between repositories, integrations, and the task queue. No service ever imports from `app/api/` or touches HTTP concerns. No service ever executes raw SQL — that is the repository's job.

## Interfaces

### Layer Boundaries

```
Route Handler     app/api/v1/          Parse HTTP, validate input, call service, wrap response
     |
Service Layer     app/services/        Business logic, orchestration — no HTTP, no raw SQL
     |
     +-- Repository     app/repositories/    DB reads/writes via SQLAlchemy session
     +-- Integration    app/integrations/    External APIs through abstract base classes
     +-- Task Queue     app/queue/           Enqueue async work — never execute inline
```

**How to locate any bug:** Wrong HTTP response shape → route handler. Wrong business logic → service. Wrong data from DB → repository. Enrichment failing → integration. Task not running → queue/worker.

### Service Inventory

#### v1 Core Services

| Service | File | Responsibility |
|---|---|---|
| `AlertIngestionService` | `alert_ingestion.py` | Full ingest pipeline: normalize, fingerprint, dedup, persist, associate detection rule, enqueue enrichment |
| `EnrichmentService` | `enrichment.py` | Parallel enrichment: cache-first, all providers per indicator, malice aggregation |
| `IndicatorExtractionService` | `indicator_extraction.py` | 3-pass IOC extraction: source plugin (Pass 1), normalized fields (Pass 2), raw_payload fields (Pass 3) |
| `ActivityEventService` | `activity_event.py` | Fire-and-forget audit event writer; never raises |
| `DetectionRuleService` | `detection_rules.py` | Resolve/create detection rules; associate with alerts at ingest time |
| `WorkflowExecutor` | `workflow_executor.py` | Build WorkflowContext, delegate to sandbox, return execution result |
| `WorkflowASTValidator` | `workflow_ast.py` | Static code validation: imports whitelist, blocked builtins, `async def run` required |
| `WorkflowGenerator` | `workflow_generator.py` | Template-based workflow code generation for built-in workflows |
| `AgentTriggerService` | `agent_trigger.py` | Evaluate which registered agents match an alert's trigger criteria |
| `AgentDispatchService` | `agent_dispatch.py` | Build webhook payloads and deliver to agents with retries |
| `AgentRunsService` | `agent_runs.py` | Record webhook delivery attempts in `agent_runs` audit table |
| `ContextTargetingService` | `context_targeting.py` | Evaluate targeting rules to determine applicable context documents |
| `MetricsService` | `metrics.py` | Compute all alert/workflow/approval metrics from raw SQL aggregates |
| `IndicatorMappingCache` | `indicator_mapping_cache.py` | In-memory TTL cache for normalized indicator field mappings |

#### v2 Agent Control Plane Services

| Service | File | Responsibility |
|---|---|---|
| `ActionService` | `action_service.py` | Agent action lifecycle: propose, approve, reject, cancel, execute; notifies operators |
| `AlertQueueService` | `alert_queue_service.py` | Alert queue checkout/release with agent-scoped and operator-scoped paths; atomic assignment |
| `KBService` | `kb_service.py` | Knowledge base CRUD, folder management, revision tracking, full-text search, memory folder |
| `InvocationService` | `invocation_service.py` | Multi-agent task delegation: single and parallel, status tracking, long-poll |
| `IssueService` | `issue_service.py` | Issue/task lifecycle: create, assign, checkout, resolve, comment |
| `RoutineService` | `routine_service.py` | Routine scheduling: cron and event-based triggers, pause/resume, manual trigger, run history |
| `CampaignService` | `campaign_service.py` | Campaign management: link alerts/issues/routines, compute aggregated metrics |
| `CostService` | `cost_service.py` | Token/cost tracking, per-agent and per-alert aggregates, budget enforcement data |
| `HeartbeatService` | `heartbeat_service.py` | Heartbeat recording, run creation, last-seen timestamp updates |
| `SecretService` | `secret_service.py` | Encrypted secrets: create, rotate, version history; uses `ENCRYPTION_KEY` env var |
| `TopologyService` | `topology_service.py` | Agent fleet topology: node list, delegation edges, routing config |

### Common Patterns

**Constructor injection via DB session:**

Every service receives an `AsyncSession` in its constructor. The session is created by the route handler's `Depends(get_db)` and passed down. Services never create their own sessions.

```python
class EnrichmentService:
    def __init__(self, db: AsyncSession, cache: CacheBackendBase) -> None:
        self._db = db
        self._cache = cache
        self._alert_repo = AlertRepository(db)
        self._indicator_repo = IndicatorRepository(db)
```

**No direct session commits in services:**

Services call `session.flush()` to synchronize ORM state but do NOT call `session.commit()`. The commit is the caller's responsibility (route handler or task handler). Exception: the enrichment task handler commits after the full pipeline completes.

**Fire-and-forget pattern for audit events:**

`ActivityEventService.write()` catches all exceptions and logs them. Callers always `await` it but never need to handle errors:

```python
await self._activity_service.write(
    ActivityEventType.ALERT_INGESTED,
    actor_type="api",
    actor_key_prefix=auth.key_prefix,
    alert_id=alert.id,
    references={"source_name": "sentinel", "severity": "High"},
)
# If this fails, it logs and returns. The alert ingest is not affected.
```

**Never-raise services:**

Several services have explicit never-raise contracts:
- `ActivityEventService.write()` — audit events must never break the main flow
- `EnrichmentService.enrich_alert()` — catches and logs all pipeline errors
- `execute_workflow()` in `workflow_executor.py` — returns `WorkflowExecutionResult` with failure info

### AlertIngestionService Pipeline

The most complex service. Pipeline steps (all synchronous within the HTTP request except step 7):

```
1. source.normalize(raw_payload) -> CalsetaAlert
2. Extract indicators for fingerprinting (Pass 1 + Pass 2, no DB writes)
3. Generate indicator-based fingerprint: SHA-256(title + source + sorted indicators)
4. Check for duplicates within ALERT_DEDUP_WINDOW_HOURS
5. If duplicate: increment duplicate_count, write activity event, return early
6. If new: persist alert, associate detection rule
7. Enqueue "enrich_alert" task (async — returns before enrichment runs)
8. Write alert_ingested activity event (fire-and-forget)
```

### EnrichmentService Pipeline

Runs in the worker process via `enrich_alert_task`:

```
1. Load all indicators for the alert
2. For each indicator, run enrich_indicator():
   a. Check cache for each configured provider
   b. Call provider.enrich() for cache misses (async parallel)
   c. Cache successful results with provider-specific TTL
3. Aggregate malice per indicator (worst-wins: Malicious > Suspicious > Benign > Pending)
4. Update indicator.enrichment_results, malice, is_enriched
5. Mark alert.is_enriched = True, status = "enriched"
6. Write alert_enrichment_completed activity event
```

### IndicatorExtractionService 3-Pass Pipeline

```
Pass 1: source.extract_indicators(raw_payload)     — source-specific hardcoded extraction
Pass 2: normalized field mappings (indicator_field_mappings where extraction_target='normalized')
Pass 3: raw_payload field mappings (indicator_field_mappings where extraction_target='raw_payload')
```

Each pass is wrapped in try/except — failures are logged, never raised. Results are merged and deduplicated by `(type, value)`. Empty/whitespace values are discarded.

### AlertQueueService — Dual Code Paths

`alert_queue_service.py` handles two distinct callers with different behavior:

- **Agent path** (caller has `agent_registration_id`): `checkout()` creates an `alert_assignment` row for this agent and marks the alert as assigned. `release()` removes the assignment and returns the alert to the queue. Query scope is filtered to alerts the agent is eligible for (based on trigger config).
- **Operator path** (caller has no `agent_registration_id`): Read-only — `list_queue()` returns all queued alerts without eligibility filtering. Operators cannot checkout/release through this service.

### ActionService — Approval Gate

`action_service.py` manages the human-in-the-loop gate for agent-proposed actions:

```
propose()  → creates agent_action row with status='pending', notifies operator
approve()  → transitions to 'approved', enqueues execution task
reject()   → transitions to 'rejected', records reason
cancel()   → agent cancels own pending action (only while still 'pending')
execute()  → (internal) runs the approved action; called by queue task
```

Actions have a configurable `approval_mode` on the action type. Some actions auto-approve if the agent has the `auto_approve` flag set. The service never executes actions inline — it always enqueues.

## Key Design Decisions

1. **Services own orchestration, repositories own queries.** A service never executes a SQLAlchemy `select()` statement. If it needs data, it calls a repository method. This means you can test a service by mocking its repositories, and you can test a repository with a real DB session without needing any service logic.

2. **No service-to-service imports.** Services do not import each other. When a service needs another service's logic, it either: (a) delegates to a shared repository method, (b) uses a shared utility function, or (c) the caller (route handler or task handler) coordinates between services.

3. **Fingerprint-based deduplication over time-window matching.** `AlertIngestionService` generates a SHA-256 fingerprint from `(title, source_name, sorted_indicator_tuples)`. This is more precise than fuzzy matching on titles and more robust than source-specific dedup IDs. The dedup window (`ALERT_DEDUP_WINDOW_HOURS`, default 24) prevents indefinite suppression.

4. **Malice aggregation is worst-wins, not majority-vote.** If VirusTotal says `Malicious` and AbuseIPDB says `Benign`, the indicator is `Malicious`. False negatives (missing a threat) are more dangerous than false positives in a SOC context.

5. **Workflow execution never modifies the database directly.** `execute_workflow()` in `workflow_executor.py` returns a `WorkflowExecutionResult` dataclass. The caller (route handler or queue task) is responsible for writing the `WorkflowRun` record. This keeps the execution engine stateless and testable.

6. **KB and memory share the same table.** `KBService` uses the `kb_pages` table for both knowledge base content (arbitrary folders) and agent memory (`/memory/agents/{id}/` folder). The distinction is folder path, not a separate table. `memory.py` routes delegate to `KBService` methods.

## Extension Pattern: Adding a New Service

1. **Create `app/services/my_service.py`**:
   ```python
   from sqlalchemy.ext.asyncio import AsyncSession
   from app.repositories.my_repository import MyRepository

   class MyService:
       def __init__(self, db: AsyncSession) -> None:
           self._db = db
           self._repo = MyRepository(db)

       async def do_something(self, entity_id: int) -> SomeResult:
           entity = await self._repo.get_by_id(entity_id)
           # ... business logic ...
           return result
   ```

2. **Use in route handler**:
   ```python
   @router.post("/my-entity")
   async def create_entity(
       body: MyCreateSchema,
       db: Annotated[AsyncSession, Depends(get_db)],
       auth: AuthContext = Depends(require_scope(Scope.ADMIN)),
   ):
       service = MyService(db)
       result = await service.do_something(body.id)
       await db.commit()
       return DataResponse(data=result)
   ```

3. **Rules to follow:**
   - Constructor takes `AsyncSession` (and optionally cache, queue)
   - Never import from `app/api/`
   - Never call `session.commit()` — let the caller commit
   - Never execute raw SQL — use repository methods
   - Log via `structlog.get_logger(__name__)`
   - If the service should never break callers, wrap the body in try/except and log errors

## Common Failure Modes

| Symptom | Cause | Diagnosis |
|---|---|---|
| Alert ingested but enrichment never runs | `enqueue("enrich_alert", ...)` failed silently | Check `enrichment_enqueue_failed` in logs; verify worker is running |
| Duplicate alerts not being detected | `ALERT_DEDUP_WINDOW_HOURS=0` disables dedup | Check config; fingerprint mismatch also prevents dedup |
| Indicators missing from enriched alert | Extraction passes 1-3 all failed or returned empty | Check per-pass error logs; verify `indicator_field_mappings` table has mappings for the source |
| Activity events missing | `ActivityEventService.write()` failed silently | Check `activity_event_write_failed` in logs; the failure is intentionally swallowed |
| Metrics show null values | No alerts in the time window, or missing timestamp columns | Check query time range; `occurred_at` must be non-null for MTTD calculation |
| Context documents not matching alerts | Targeting rules evaluate to False | Check rule operators (eq, in, contains, gte, lte) and field paths (source_name, severity, tags) |
| Agent can't checkout alert | Alert already assigned, or agent not eligible | Check `alert_assignments` table; verify agent trigger config matches alert source/severity |
| Proposed action stuck in pending | No operator reviewed it, or notifier failed | Check `agent_actions` table status; check operator notification logs |

## Test Coverage

| Test file | Scenarios |
|---|---|
| `tests/test_enrichment_service.py` | Parallel enrichment, cache-first logic, malice aggregation, mixed provider results |
| `tests/test_context_targeting.py` | Targeting rule evaluation: match_any, match_all, operators, type mismatches, global documents |
| `tests/test_context_documents.py` | Context document CRUD and targeting rule persistence |
| `tests/test_workflow_executor.py` | Workflow execution lifecycle: context building, sandbox delegation, result capture |
| `tests/test_workflow_ast.py` | AST validation: imports whitelist, blocked modules/builtins, `async def run` requirement |
| `tests/test_builtin_workflows.py` | Built-in workflow code validation and execution |
| `tests/test_agent_trigger.py` | Agent trigger evaluation: source filter, severity filter, JSONB filter, inactive agent skip |
| `tests/test_approval_gate.py` | Approval creation, decision processing, expiry handling |
| `tests/integration/test_ingest.py` | Full ingest pipeline: 202 response, alert created, enrichment enqueued |
| `tests/integration/test_metrics.py` | Metric computation: alert counts, MTTX values, workflow stats |
| `tests/integration/agent_control_plane/` | Queue checkout/release, actions, invocations, budget enforcement, orchestration |
