# Service Layer — Agent Navigation

## Pipelines

### Alert Ingestion (8 steps, synchronous within request)
- Entry: `alert_ingestion.py:AlertIngestionService.ingest()`
- Steps: normalize → extract_for_fingerprint → generate_fingerprint → find_duplicate → persist alert → associate detection rule → enqueue enrichment → write activity event
- Call graph: `ingest()` → `source.normalize()` → `extract_for_fingerprint()` (indicator_extraction.py) → `AlertRepository.find_duplicate()` → `AlertRepository.create()` → `DetectionRuleService.associate_detection_rule()` → `queue.enqueue("enrich_alert")` → `ActivityEventService.write()`
- Key seams: Step 2 uses `get_normalized_mappings()` from indicator_mapping_cache.py (in-memory cache); step 6 best-effort (caught exception); step 7 enqueue failure is logged but does not fail the request
- To debug: If alerts ingest but never enrich, check step 7 enqueue. If duplicates are not detected, check `ALERT_DEDUP_WINDOW_HOURS` setting and fingerprint generation
- To extend: Add a new post-ingest step between steps 7 and 8 in `ingest()`; never add blocking calls before the 202 response

### Enrichment Pipeline (async, worker process)
- Entry: `enrichment.py:EnrichmentService.enrich_alert(alert_id)`
- Steps: load indicators → enrich_indicator() per indicator (concurrent) → update indicator enrichment_results/malice → mark alert enriched → write activity event
- Call graph per indicator: `enrich_indicator()` → `is_enrichable()` (indicator_validation.py) → `enrichment_registry.list_for_type()` → cache check → `provider.enrich()` (DatabaseDrivenProvider) → `EnrichmentPipeline.run()` (enrichment_pipeline/) → `TemplateResolver` + `GenericHttpEnrichmentEngine` + `FieldExtractor` + `MaliceRuleEvaluator`
- Key seams: Cache miss triggers live HTTP call; `_worst_malice()` aggregates across providers; `provider.enrich()` never raises (contract)
- To debug: Check `is_enrichable()` first (skips private IPs, localhost). Then check provider `is_configured()`. Then trace HTTP execution in `enrichment_pipeline/engine.py`
- To extend: Add enrichment provider via DB seed or `POST /v1/enrichment-providers` — zero code changes

### Indicator Extraction (3-pass, called from worker task)
- Entry: `indicator_extraction.py:IndicatorExtractionService.extract_and_persist()`
- Fingerprint-only variant: `extract_for_fingerprint()` (Pass 1 + 2, no DB writes)
- Steps: Pass 1 `source.extract_indicators(raw_payload)` → Pass 2 `_extract_normalized()` against CalsetaAlert fields → Pass 3 `_extract_raw()` against raw_payload dot-paths → deduplicate by (type, value) → `IndicatorRepository.upsert()` + `link_to_alert()`
- Key seams: Pass 2 uses `IndicatorMappingRepository` (DB query); Pass 3 uses dot-notation traversal via `_traverse()`; each pass is independently try/except wrapped
- To debug: Check per-pass error logs (`indicator_extraction_pass{N}_failed`). Check `indicator_field_mappings` table for correct `extraction_target` values

### Workflow Execution
- Entry: `workflow_executor.py:execute_workflow(workflow, trigger_context, db)`
- Steps: load indicator from DB → build AlertContext (optional) → build IntegrationClients → create httpx.AsyncClient with SSRF hook → build WorkflowContext → `run_workflow_code()` (workflows/sandbox.py)
- Key seams: SSRF check via `_ssrf_check_hook` on every HTTP request; sandbox uses AST validation + memory limits; this module does NOT write to DB — caller persists results
- To debug: Check `WorkflowResult.success` and `log_output` on the WorkflowRun record. If HTTP fails, check SSRF allowlist (`SSRF_ALLOWED_HOSTS`)

### Alert Queue Checkout (v2)
- Entry: `alert_queue_service.py:AlertQueueService.checkout(agent, alert_uuid)`
- Steps: load alert → verify eligibility (not already assigned, matches agent trigger config) → create alert_assignment row (status='in_progress') → update alert.status → write activity event
- Agent path vs operator path: agents call `checkout()`; operators can only read via `list_queue()` (no checkout)
- Concurrency: checkout uses SELECT FOR UPDATE or equivalent to prevent double-checkout race conditions
- To debug: If checkout fails with conflict, check `alert_assignments` table for existing active assignment

### Action Proposal + Approval (v2)
- Entry propose: `action_service.py:ActionService.propose(agent, action_type, payload)`
- Entry approve: `ActionService.approve(action_uuid, operator_auth)`
- Entry execute: called by queue task, not directly by routes
- Steps (propose): validate action type → create agent_action row (status='pending') → notify operator via configured notifier → return 202
- Steps (approve): transition status → enqueue execute task → return 200
- To debug: If action stuck in pending, check operator notification logs. If approve doesn't trigger execution, check queue worker

### Multi-Agent Invocation (v2)
- Entry: `invocation_service.py:InvocationService.delegate(orchestrator, specialist_uuid, task)`
- Parallel variant: `InvocationService.delegate_parallel(orchestrator, tasks_list)` — calls delegate() for each, returns list of invocation UUIDs
- Steps: validate orchestrator is orchestrator type → validate specialist exists and active → create invocation row (status='pending') → notify specialist agent → return invocation UUID
- Long-poll: `InvocationService.poll(invocation_uuid, timeout_seconds=30)` — blocks up to 30s waiting for status change from 'pending' to 'complete'/'failed'
- To debug: If specialist never picks up invocation, check specialist agent heartbeat (it should poll `GET /v1/assignments/mine` or watch for notifications)

## File → Responsibility Map

### v1 Core

| File | Owns | Calls |
|------|------|-------|
| `alert_ingestion.py` | 8-step ingest pipeline | AlertRepository, DetectionRuleService, extract_for_fingerprint, ActivityEventService, TaskQueueBase |
| `enrichment.py` | Cache-first enrichment orchestration, alert-level enrichment | enrichment_registry, IndicatorRepository, AlertRepository, CacheBackendBase |
| `enrichment_pipeline/` | Deep module: template resolution, HTTP execution, field extraction, malice evaluation | url_validation |
| `enrichment_pipeline/__init__.py` | Exports `EnrichmentPipeline` (single public entry point) | engine, field_extractor, malice_evaluator, template_resolver |
| `enrichment_pipeline/engine.py` | Multi-step HTTP execution for providers | template_resolver, field_extractor, malice_evaluator, url_validation |
| `enrichment_pipeline/template_resolver.py` | Placeholder resolution in HTTP configs | _dot_path |
| `enrichment_pipeline/field_extractor.py` | Dot-path field extraction from responses | _dot_path |
| `enrichment_pipeline/malice_evaluator.py` | Threshold-based malice verdict rules | _dot_path |
| `enrichment_pipeline/_dot_path.py` | Shared dot-path traversal utility | (pure function) |
| `indicator_extraction.py` | 3-pass IOC extraction + persistence | IndicatorRepository, IndicatorMappingRepository, source plugins |
| `workflow_executor.py` | Workflow sandbox orchestration (no DB writes) | IndicatorRepository, AlertRepository, run_workflow_code |
| `activity_event.py` | Fire-and-forget audit log writes | ActivityEventRepository |
| `agent_dispatch.py` | Webhook payload building + HTTP delivery | AgentRepository, AlertRepository |
| `agent_trigger.py` | Trigger filter matching for agents | AgentRepository |
| `context_targeting.py` | Match context docs to alerts by targeting_rules | ContextDocumentRepository |
| `detection_rules.py` | Rule association + CRUD | DetectionRuleRepository |
| `metrics.py` | MTTD, MTTE, volume, severity, enrichment stats | AlertRepository, IndicatorRepository |
| `workflow_ast.py` | AST import validation for workflow code | (pure function, no deps) |
| `workflow_generator.py` | LLM-powered workflow code generation | settings (LLM config) |
| `indicator_validation.py` | Enrichability checks (skip private IPs, etc.) | (pure function) |
| `url_validation.py` | SSRF outbound URL validation | settings (SSRF_ALLOWED_HOSTS) |
| `indicator_mapping_cache.py` | In-memory cache for normalized field mappings | (module-level dict) |

### v2 Agent Control Plane

| File | Owns | Calls |
|------|------|-------|
| `action_service.py` | Agent action lifecycle: propose, approve, reject, cancel, execute | AgentActionRepository, queue, operator notifiers |
| `alert_queue_service.py` | Queue checkout/release, agent eligibility check, operator list | AlertAssignmentRepository, AlertRepository, ActivityEventService |
| `kb_service.py` | KB CRUD, folder management, revision snapshots, full-text search | KBPageRepository, KBRevisionRepository |
| `invocation_service.py` | Delegation (single + parallel), status tracking, long-poll | InvocationRepository, AgentRepository |
| `issue_service.py` | Issue lifecycle: create, assign, checkout, resolve, comment | IssueRepository, IssueCommentRepository |
| `routine_service.py` | Routine scheduling, cron/event triggers, pause/resume, runs | RoutineRepository, RoutineTriggerRepository, RoutineRunRepository, queue |
| `campaign_service.py` | Campaign CRUD, item linking (alerts/issues/routines), metrics aggregation | CampaignRepository, CampaignItemRepository |
| `cost_service.py` | Cost event recording, per-agent/per-alert aggregates, budget data | CostEventRepository, AgentRepository |
| `heartbeat_service.py` | Heartbeat recording, run creation, last-seen updates | HeartbeatRepository, HeartbeatRunRepository |
| `secret_service.py` | Encrypted secret create/rotate/version; uses Fernet + ENCRYPTION_KEY | SecretRepository, SecretVersionRepository |
| `topology_service.py` | Agent fleet nodes, delegation edges, routing topology | AgentRepository, InvocationRepository |
