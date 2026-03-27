# Service Layer -- Agent Navigation

## Pipelines

### Alert Ingestion (8 steps, synchronous within request)
- Entry: `alert_ingestion.py:AlertIngestionService.ingest()`
- Steps: normalize -> extract_for_fingerprint -> generate_fingerprint -> find_duplicate -> persist alert -> associate detection rule -> enqueue enrichment -> write activity event
- Call graph: `ingest()` -> `source.normalize()` -> `extract_for_fingerprint()` (indicator_extraction.py) -> `generate_fingerprint()` (alert_repository.py) -> `AlertRepository.find_duplicate()` -> `AlertRepository.create()` -> `DetectionRuleService.associate_detection_rule()` -> `queue.enqueue("enrich_alert")` -> `ActivityEventService.write()`
- Key seams: Step 2 uses `get_normalized_mappings()` from indicator_mapping_cache.py (in-memory cache); step 6 is best-effort (caught exception); step 7 enqueue failure is logged but does not fail the request
- To debug: If alerts ingest but never enrich, check step 7 enqueue. If duplicates are not detected, check `ALERT_DEDUP_WINDOW_HOURS` setting and fingerprint generation
- To extend: Add a new post-ingest step between steps 7 and 8 in `ingest()`; never add blocking calls before the 202 response

### Enrichment Pipeline (async, worker process)
- Entry: `enrichment.py:EnrichmentService.enrich_alert(alert_id)`
- Steps: load indicators -> enrich_indicator() per indicator (concurrent) -> update indicator enrichment_results/malice -> mark alert enriched -> write activity event
- Call graph per indicator: `enrich_indicator()` -> `is_enrichable()` (indicator_validation.py) -> `enrichment_registry.list_for_type()` -> cache check -> `provider.enrich()` (DatabaseDrivenProvider) -> `GenericHttpEnrichmentEngine.execute()` (enrichment_engine.py) -> `TemplateResolver` + `FieldExtractor` + `MaliceRuleEvaluator` (enrichment_pipeline/ subpackage)
- Key seams: Cache miss triggers live HTTP call; `_worst_malice()` aggregates across providers; `provider.enrich()` never raises (contract)
- To debug: Check `is_enrichable()` first (skips private IPs, localhost). Then check provider `is_configured()`. Then trace HTTP execution in enrichment_engine.py
- To extend: Add enrichment provider via DB seed or `POST /v1/enrichment-providers` -- zero code changes. Add new malice logic in malice_evaluator.py

### Indicator Extraction (3-pass, called from worker task)
- Entry: `indicator_extraction.py:IndicatorExtractionService.extract_and_persist()`
- Fingerprint-only variant: `extract_for_fingerprint()` (Pass 1 + 2, no DB writes)
- Steps: Pass 1 `source.extract_indicators(raw_payload)` -> Pass 2 `_extract_normalized()` against CalsetaAlert fields -> Pass 3 `_extract_raw()` against raw_payload dot-paths -> deduplicate by (type, value) -> `IndicatorRepository.upsert()` + `link_to_alert()`
- Key seams: Pass 2 uses `IndicatorMappingRepository` (DB query); Pass 3 uses dot-notation traversal via `_traverse()`; each pass is independently try/except wrapped
- To debug: Check which pass is failing via structured logs (`indicator_extraction_pass{N}_failed`). Check `indicator_field_mappings` table for correct `extraction_target` values
- To extend: Add new indicator type in `schemas/indicators.py:IndicatorType` enum. Add field mappings via `POST /v1/indicator-mappings`

### Workflow Execution
- Entry: `workflow_executor.py:execute_workflow(workflow, trigger_context, db)`
- Steps: load indicator from DB -> build AlertContext (optional) -> build IntegrationClients -> create httpx.AsyncClient with SSRF hook -> build WorkflowContext -> `run_workflow_code()` (workflows/sandbox.py)
- Call graph: `execute_workflow()` -> `IndicatorRepository.get_by_type_and_value()` -> `_build_alert_context()` -> `_build_integrations()` -> `run_workflow_code()`
- Key seams: SSRF check via `_ssrf_check_hook` on every HTTP request; sandbox uses AST validation (workflow_ast.py) + memory limits; this module does NOT write to DB -- caller persists results
- To debug: Check `WorkflowResult.success` and `log_output` on the WorkflowRun record. If HTTP fails, check SSRF allowlist (`SSRF_ALLOWED_HOSTS`)
- To extend: Add new context fields to `WorkflowContext` in `workflows/context.py`. Add integration clients in `_build_integrations()`

## File -> Responsibility Map

| File | Owns | Calls |
|------|------|-------|
| alert_ingestion.py | 8-step ingest pipeline | AlertRepository, DetectionRuleService, extract_for_fingerprint, ActivityEventService, TaskQueueBase |
| enrichment.py | Cache-first enrichment orchestration, alert-level enrichment | enrichment_registry, IndicatorRepository, AlertRepository, CacheBackendBase |
| enrichment_engine.py | Multi-step HTTP execution for providers | TemplateResolver, FieldExtractor, MaliceRuleEvaluator, url_validation |
| indicator_extraction.py | 3-pass IOC extraction + persistence | IndicatorRepository, IndicatorMappingRepository, source plugins |
| workflow_executor.py | Workflow sandbox orchestration (no DB writes) | IndicatorRepository, AlertRepository, run_workflow_code |
| activity_event.py | Fire-and-forget audit log writes | ActivityEventRepository |
| agent_dispatch.py | Webhook payload building + HTTP delivery | AgentRepository, AlertRepository |
| agent_trigger.py | Trigger filter matching for agents | AgentRepository |
| context_targeting.py | Match context docs to alerts by targeting_rules | ContextDocumentRepository |
| detection_rules.py | Rule association + CRUD | DetectionRuleRepository |
| metrics.py | MTTD, MTTE, volume, severity, enrichment stats | AlertRepository, IndicatorRepository |
| workflow_ast.py | AST import validation for workflow code | (pure function, no deps) |
| workflow_generator.py | LLM-powered workflow code generation | settings (LLM config) |
| indicator_validation.py | Enrichability checks (skip private IPs, etc.) | (pure function) |
| url_validation.py | SSRF outbound URL validation | settings (SSRF_ALLOWED_HOSTS) |
| enrichment_template.py | Placeholder resolution in HTTP configs | (pure function) |
| field_extractor.py | Dot-path field extraction from responses | (pure function) |
| malice_evaluator.py | Threshold-based malice verdict rules | (pure function) |
| indicator_mapping_cache.py | In-memory cache for normalized field mappings | (module-level dict) |
