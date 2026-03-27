# API Routes (v1) -- Agent Navigation

## Shared Patterns

Every route handler follows this stack:
```
Auth -> Scope check -> Rate limit -> Route handler -> Service/Repository -> Response envelope
```

- Auth: `Depends(require_scope(Scope.X))` from `app/auth/dependencies.py` -- returns `AuthContext`
- Pagination: `PaginationParams = Depends()` from `app/api/pagination.py` -- provides `.offset`, `.page_size`
- Response envelopes: `DataResponse[T]` (single), `PaginatedResponse[T]` (list) from `app/schemas/common.py`
- Error handling: raise `CalsetaException(code, message, status_code)` from `app/api/errors.py`
- Rate limiting: `@limiter.limit()` decorator from `app/middleware/rate_limit.py`
- DI for DB: `Depends(get_db)` -> `AsyncSession`; DI for queue: `Depends(get_queue)` -> `TaskQueueBase`
- Scope aliases: `_Read = Annotated[AuthContext, Depends(require_scope(Scope.X_READ))]`

## Route -> Service -> Repository Map

| Route File | Prefix | Key Endpoints | Service/Repository |
|-----------|--------|---------------|-------------------|
| ingest.py | /ingest, /alerts (POST) | webhook_ingest, generic_ingest | AlertIngestionService -> AlertRepository, queue |
| alerts.py | /alerts | list, detail, patch, delete, findings, indicators, activity, relationship-graph | AlertRepository, IndicatorRepository, ActivityEventService |
| indicators.py | /indicators | list, detail | IndicatorRepository |
| detection_rules.py | /detection-rules | CRUD | DetectionRuleRepository |
| enrichments.py | /enrichments | on-demand enrich | EnrichmentService |
| enrichment_providers.py | /enrichment-providers | CRUD + test | EnrichmentProviderRepository, enrichment_registry |
| enrichment_field_extractions.py | /enrichment-field-extractions | CRUD | EnrichmentFieldExtractionRepository |
| context_documents.py | /context-documents | CRUD (JSON + multipart) | ContextDocumentRepository |
| workflows.py | /workflows | CRUD, execute, test, generate, runs, versions | WorkflowRepository, WorkflowRunRepository, workflow_executor |
| workflow_approvals.py | /workflow-approvals | list, detail | WorkflowApprovalRepository |
| approvals.py | /approvals | approve/reject | WorkflowApprovalRepository, queue |
| agents.py | /agents | CRUD | AgentRepository |
| sources.py | /sources | CRUD, test-extraction | SourceRepository, source_registry |
| indicator_mappings.py | /indicator-mappings | CRUD | IndicatorMappingRepository |
| api_keys.py | /api-keys | CRUD (key shown once on create) | ApiKeyRepository |
| metrics.py | /metrics | summary dashboard | MetricsService |
| settings.py | /settings | runtime config | settings |

## Custom (Non-CRUD) Routes

| Endpoint | What It Does | Calls |
|----------|-------------|-------|
| POST /v1/ingest/{source_name} | Webhook ingest with signature verify | source.verify_webhook_signature() -> AlertIngestionService.ingest() |
| POST /v1/alerts (body) | Programmatic ingest, no sig verify | AlertIngestionService.ingest() |
| POST /v1/alerts/{uuid}/findings | Add agent finding | AlertRepository.add_finding() |
| POST /v1/alerts/{uuid}/indicators | Link indicators to alert | IndicatorRepository.upsert() + link_to_alert() |
| GET /v1/alerts/{uuid}/relationship-graph | Alert-indicator-sibling graph | AlertRepository + IndicatorRepository |
| POST /v1/enrichments/{type}/{value} | On-demand enrichment | EnrichmentService.enrich_indicator() |
| POST /v1/workflows/{uuid}/execute | Enqueue workflow run (202) | WorkflowRunRepository.create() + queue.enqueue() |
| POST /v1/workflows/{uuid}/test | Sandbox test (mock HTTP) | execute_workflow() with mock transport |
| POST /v1/workflows/generate | LLM code generation | WorkflowGeneratorService |
| POST /v1/approvals/{uuid}/approve | Approve workflow | WorkflowApprovalRepository + queue.enqueue() |
| POST /v1/sources/{name}/test-extraction | Dry-run indicator extraction | test_extraction() from indicator_extraction.py |

## How to Add an Endpoint
1. Add route function in existing or new file under `app/api/v1/`
2. Use `Depends(require_scope(Scope.X))` for auth
3. Use `PaginationParams = Depends()` for list endpoints
4. Call service layer or repository -- never write raw SQL in routes
5. Return `DataResponse[T]` or `PaginatedResponse[T]`
6. Add `@limiter.limit()` decorator with appropriate rate
7. Register router in `router.py` via `v1_router.include_router()`
8. Add corresponding Pydantic schemas in `app/schemas/`
