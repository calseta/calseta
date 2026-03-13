# Enrichment Provider System

## What This Component Does

The enrichment provider system queries external threat intelligence APIs (VirusTotal, AbuseIPDB, Okta, Microsoft Entra, and any custom providers) to annotate indicators of compromise with reputation data, account metadata, and malice verdicts. Providers are **database-driven** — each provider is a row in the `enrichment_providers` table with templated HTTP configs, malice threshold rules, and field extraction mappings. Adding a new provider requires zero code changes: either seed it as a builtin or add it at runtime via the CRUD API.

The `EnrichmentService` in `app/services/enrichment.py` orchestrates parallel execution with cache-first lookup and malice aggregation. It is **completely unchanged** by the database-driven architecture — the `DatabaseDrivenProvider` adapter implements `EnrichmentProviderBase`, so the entire pipeline, cache system, and malice aggregation work identically.

## Architecture

```
EnrichmentService (unchanged — orchestrates parallel enrichment)
    ↓ calls enrichment_registry.list_for_type()
EnrichmentRegistry (loads providers from DB at startup)
    ↓ returns DatabaseDrivenProvider instances
DatabaseDrivenProvider(EnrichmentProviderBase)     ← adapter
    ↓ delegates to
GenericHttpEnrichmentEngine                        ← HTTP execution
    ├── TemplateResolver       (resolves {{auth.api_key}}, {{indicator.value}}, etc.)
    ├── FieldExtractor         (applies enrichment_field_extractions rows)
    └── MaliceRuleEvaluator    (evaluates threshold rules from provider config)
```

## Key Components

### EnrichmentProviderBase (`base.py`)

Abstract base class. `DatabaseDrivenProvider` implements this for all DB-driven providers.

```python
class EnrichmentProviderBase(ABC):
    provider_name: str
    display_name: str
    supported_types: list[IndicatorType]
    cache_ttl_seconds: int = 3600
    _TTL_BY_TYPE: dict[IndicatorType, int] = {}

    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult: ...
    def is_configured(self) -> bool: ...
    def get_cache_ttl(self, indicator_type: IndicatorType) -> int: ...
```

**Critical contract — `enrich()` must NEVER raise.** All exceptions are caught and returned as `EnrichmentResult.failure_result()`. The pipeline relies on this for safe `asyncio.gather()`.

### DatabaseDrivenProvider (`database_provider.py`)

Adapter that wraps a DB row (`EnrichmentProvider` ORM model) and implements `EnrichmentProviderBase`. Credential resolution priority:

1. Decrypted `auth_config` from DB (encrypted at rest via Fernet)
2. Env var fallback via `env_var_mapping` (for builtins using existing `.env` config)

### GenericHttpEnrichmentEngine (`app/services/enrichment_engine.py`)

Executes the HTTP steps defined in `http_config`. Supports:

- **Single-step** (VT, AbuseIPDB): one API call per enrichment
- **Multi-step** (Okta, Entra): sequential calls where later steps reference earlier step responses via `{{steps.<name>.response.<path>}}`
- **URL templates by type**: per-indicator-type URL overrides (e.g., VT uses different endpoints for IP vs domain vs hash)
- **Optional steps**: `"optional": true` — step failure doesn't abort the pipeline
- **Form body**: `form_body` for OAuth token requests

### TemplateResolver (`app/services/enrichment_template.py`)

Simple `{{namespace.field}}` regex replacer. Whitelisted namespaces:

- `{{indicator.value}}` / `{{indicator.type}}` — the IOC being enriched
- `{{auth.<field>}}` — resolved credentials (API key, token, etc.)
- `{{steps.<name>.response.<path>}}` — previous step responses (multi-step only)

One filter: `{{value | urlencode}}`. No Jinja2 — eliminates template injection risk.

### MaliceRuleEvaluator (`app/services/malice_evaluator.py`)

Evaluates ordered threshold rules from `malice_rules` JSONB. First match wins. Operators: `>`, `>=`, `<`, `<=`, `==`, `!=`, `contains`, `in`.

```json
{
  "rules": [
    {"field": "data.abuseConfidenceScore", "operator": ">=", "value": 75, "verdict": "Malicious"},
    {"field": "data.abuseConfidenceScore", "operator": ">=", "value": 25, "verdict": "Suspicious"}
  ],
  "default_verdict": "Benign",
  "not_found_verdict": "Pending"
}
```

### FieldExtractor (`app/services/field_extractor.py`)

Applies extraction rules from the `enrichment_field_extractions` table. Each rule maps a dot-notation `source_path` in the raw API response to a `target_key` in the agent-facing `extracted` dict. Type coercion supported: string, int, float, bool, list, dict, any.

### EnrichmentRegistry (`registry.py`)

Module-level singleton: `enrichment_registry`.

```python
enrichment_registry.register(provider)              # manual registration
enrichment_registry.get("virustotal")                # by name
enrichment_registry.list_all()                       # all providers
enrichment_registry.list_configured()                # only is_configured() == True
enrichment_registry.list_for_type(IndicatorType.IP)  # configured + supports type

# DB-driven methods:
await enrichment_registry.load_from_database(db)     # reload all from DB
enrichment_registry.clear()                          # remove all
```

At startup, `load_from_database()` queries all active `EnrichmentProvider` rows and active `EnrichmentFieldExtraction` rows, creates `DatabaseDrivenProvider` instances, and registers them.

### CRUD API (`app/api/v1/enrichment_providers.py`)

| Method | Path | Scope | Notes |
|--------|------|-------|-------|
| GET | `/v1/enrichment-providers` | `enrichments:read` | Paginated list |
| POST | `/v1/enrichment-providers` | `admin` | Create custom provider |
| GET | `/v1/enrichment-providers/{uuid}` | `enrichments:read` | Detail |
| PATCH | `/v1/enrichment-providers/{uuid}` | `admin` | Update (builtin restrictions) |
| DELETE | `/v1/enrichment-providers/{uuid}` | `admin` | Non-builtin only |
| POST | `/v1/enrichment-providers/{uuid}/test` | `admin` | Live test |
| POST | `/v1/enrichment-providers/{uuid}/activate` | `admin` | Set active |
| POST | `/v1/enrichment-providers/{uuid}/deactivate` | `admin` | Set inactive |

Responses include `has_credentials: bool` and `is_configured: bool` — never actual credentials.

## Key Design Decisions

1. **Adapter pattern preserves the pipeline.** `DatabaseDrivenProvider` implements `EnrichmentProviderBase`, so `EnrichmentService`, the cache layer, and malice aggregation work without any modification.

2. **Steps array for multi-step providers.** Okta (user + groups) and Entra (OAuth token + user + groups) are single logical providers with multiple sequential HTTP calls. Steps can reference previous step responses via `{{steps.<name>.response.<path>}}`.

3. **Env var fallback for builtins.** Builtins have `env_var_mapping` so existing `VIRUSTOTAL_API_KEY` etc. in `.env` files keep working. Custom providers use encrypted `auth_config` in the DB.

4. **Minimal template engine — no Jinja2.** Simple `{{namespace.field}}` regex replacer with whitelisted namespaces. Eliminates template injection risk.

5. **`enrichment_field_extractions` IS the field mapping.** The table was already there with the right schema. System defaults seeded for builtins; operators can add custom extractions for any provider.

6. **Credentials encrypted at rest.** Reuses `app/auth/encryption.py` (Fernet). `auth_config` stored as `{"_encrypted": "<ciphertext>"}`. Decrypted at execution time only.

7. **Three-state result (success/failed/skipped).** `skipped` means the provider deliberately did not process the indicator (unconfigured, unsupported type). `failed` indicates an operational error.

8. **Builtin protection.** Builtins cannot be deleted. Only specific fields can be patched: `is_active`, `auth_config`, `description`, `malice_rules`, `default_cache_ttl_seconds`, `cache_ttl_by_type`.

## Extension Pattern: Adding a New Provider

### Option A: Runtime (Custom Provider — No Code Changes)

```bash
curl -X POST http://localhost:8000/v1/enrichment-providers \
  -H "Authorization: Bearer cai_..." \
  -H "Content-Type: application/json" \
  -d '{
    "provider_name": "greynoise",
    "display_name": "GreyNoise",
    "supported_indicator_types": ["ip"],
    "auth_type": "api_key",
    "auth_config": {"api_key": "your-key-here"},
    "http_config": {
      "steps": [{
        "name": "lookup",
        "method": "GET",
        "url": "https://api.greynoise.io/v3/community/{{indicator.value}}",
        "headers": {"key": "{{auth.api_key}}"},
        "timeout_seconds": 30,
        "expected_status": [200],
        "not_found_status": [404]
      }]
    },
    "malice_rules": {
      "rules": [
        {"field": "classification", "operator": "==", "value": "malicious", "verdict": "Malicious"},
        {"field": "noise", "operator": "==", "value": true, "verdict": "Suspicious"}
      ],
      "default_verdict": "Benign",
      "not_found_verdict": "Pending"
    },
    "default_cache_ttl_seconds": 3600
  }'
```

Provider is immediately available in the enrichment pipeline. No restart needed.

### Option B: Builtin (Ships with Calseta — Requires Code Change)

1. Add the provider definition to `_BUILTIN_PROVIDERS` in `app/seed/enrichment_providers.py`
2. Add field extraction rules in `_build_extractions()`
3. Add `env_var_mapping` for credential fallback
4. The provider is seeded automatically at next startup

### Option C: Community Provider (JSON Config — PR to Repo)

See `docs/project/COMMUNITY_INTEGRATIONS.md` for the full contribution guide.

## Database Schema

### `enrichment_providers` table

| Column | Type | Notes |
|--------|------|-------|
| `provider_name` | TEXT UNIQUE | `"virustotal"`, `"my_shodan"` |
| `display_name` | TEXT | Human-readable |
| `is_builtin` | BOOLEAN | Seeded at startup, deletion-protected |
| `is_active` | BOOLEAN | Controls inclusion in pipeline |
| `supported_indicator_types` | TEXT[] | `["ip", "domain", "hash_sha256"]` |
| `http_config` | JSONB | Steps array, URL templates |
| `auth_type` | TEXT | `"no_auth"`, `"api_key"`, `"api_token"`, `"oauth2_client_credentials"` |
| `auth_config` | JSONB | Encrypted at rest |
| `env_var_mapping` | JSONB | Builtin env var fallback |
| `malice_rules` | JSONB | Ordered threshold rules |

### `enrichment_field_extractions` table (existing)

| Column | Type | Notes |
|--------|------|-------|
| `provider_name` | TEXT | Links to provider |
| `indicator_type` | TEXT | Which type this extraction applies to |
| `source_path` | TEXT | Dot-notation into raw response |
| `target_key` | TEXT | Key in `extracted` dict |
| `value_type` | TEXT | Type coercion |
| `is_system` | BOOLEAN | Seeded defaults vs user-added |

## Common Failure Modes

| Symptom | Cause | Diagnosis |
|---------|-------|-----------|
| Provider returns `skipped` for every call | `is_configured()` returns False | Check env vars or DB `auth_config`; verify `is_active` |
| Provider returns `failed` with HTTP 429 | Rate limit at external API | Check provider logs; consider adjusting cache TTL |
| `enrichment_registry_loaded` shows 0 providers | Table doesn't exist or no active providers | Run `alembic upgrade head`; check `is_active` column |
| `enrichment_provider_seed_skipped` at startup | Migration 0006 not applied | Run `alembic upgrade head` |
| Template resolution fails | Invalid `{{...}}` in http_config | Check step URLs/headers for typos in template variables |
| Malice stays `Pending` | No malice_rules configured or no rules match | Check provider's `malice_rules` JSONB; verify field paths |
| Entra token acquisition fails | Invalid OAuth2 credentials | Check `auth_config` or `ENTRA_*` env vars |
| Custom provider not enriching | Registry not reloaded after creation | All CRUD mutations call `load_from_database()`; check logs |

## File Map

| File | Purpose |
|------|---------|
| `app/integrations/enrichment/base.py` | `EnrichmentProviderBase` ABC |
| `app/integrations/enrichment/registry.py` | `EnrichmentRegistry` singleton |
| `app/integrations/enrichment/database_provider.py` | `DatabaseDrivenProvider` adapter |
| `app/integrations/enrichment/__init__.py` | Exports `enrichment_registry` |
| `app/services/enrichment_engine.py` | `GenericHttpEnrichmentEngine` |
| `app/services/enrichment_template.py` | `TemplateResolver` |
| `app/services/malice_evaluator.py` | `MaliceRuleEvaluator` |
| `app/services/field_extractor.py` | `FieldExtractor` |
| `app/db/models/enrichment_provider.py` | ORM model |
| `app/schemas/enrichment_providers.py` | Pydantic request/response schemas |
| `app/repositories/enrichment_provider_repository.py` | CRUD repository |
| `app/api/v1/enrichment_providers.py` | CRUD API routes |
| `app/seed/enrichment_providers.py` | Builtin provider + field extraction seeder |
| `app/services/enrichment.py` | `EnrichmentService` (unchanged) |

## Test Coverage

| Test file | Scenarios |
|-----------|-----------|
| `tests/test_enrichment_template.py` | Template resolution: indicator, auth, steps, urlencode filter, nested dicts/lists, missing variables |
| `tests/test_malice_evaluator.py` | All operators, not_found handling, default verdict, empty rules, missing fields |
| `tests/test_field_extractor.py` | Dot-path extraction, type coercion, missing paths, multi-step keyed responses |
| `tests/test_enrichment_engine.py` | Single-step and multi-step execution, URL templates by type, optional steps, not_found handling |
| `tests/test_enrichment_providers_api.py` | CRUD endpoints, builtin restrictions, scope enforcement, credential encryption |
| `tests/test_enrichment_service.py` | Pipeline integration: cache hit/miss, parallel execution, malice aggregation |
