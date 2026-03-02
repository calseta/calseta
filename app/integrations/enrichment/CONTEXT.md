# Enrichment Provider System

## What This Component Does

The enrichment provider system queries external threat intelligence APIs (VirusTotal, AbuseIPDB, Okta, Microsoft Entra) to annotate indicators of compromise with reputation data, account metadata, and malice verdicts. Each provider implements a no-raise async `enrich()` method that returns structured results. The enrichment registry resolves which configured providers support a given indicator type, and the `EnrichmentService` in `app/services/enrichment.py` orchestrates parallel execution with cache-first lookup and malice aggregation.

## Interfaces

### EnrichmentProviderBase (`base.py`)

Abstract base class. Every provider must subclass and implement:

```python
class EnrichmentProviderBase(ABC):
    provider_name: str                      # e.g. "virustotal"
    display_name: str                       # e.g. "VirusTotal"
    supported_types: list[IndicatorType]    # e.g. [IP, DOMAIN, HASH_SHA256]
    cache_ttl_seconds: int = 3600           # default; per-type TTLs preferred
    _TTL_BY_TYPE: dict[IndicatorType, int] = {}  # optional per-type overrides

    # --- Required (abstract) ---
    async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult: ...
    def is_configured(self) -> bool: ...

    # --- Provided ---
    def get_cache_ttl(self, indicator_type: IndicatorType) -> int:
        # Merges DEFAULT_TTL_BY_TYPE with _TTL_BY_TYPE, falls back to cache_ttl_seconds
```

**Critical contract -- `enrich()` must NEVER raise.** This is non-negotiable. All exceptions must be caught and returned as `EnrichmentResult.failure_result(self.provider_name, str(e))`. The outer enrichment pipeline relies on this guarantee to run providers concurrently via `asyncio.gather()` without exception propagation.

### EnrichmentResult (defined in `app/schemas/enrichment.py`)

Every `enrich()` call returns one of three result types:

```python
EnrichmentResult.success_result(provider_name, extracted, raw, enriched_at)
EnrichmentResult.failure_result(provider_name, error_message)
EnrichmentResult.skipped_result(provider_name, reason)
```

- `extracted`: Agent-facing dict with curated fields (e.g. `malice`, `abuse_confidence_score`, `country`)
- `raw`: Full API response (preserved for debugging; stripped from MCP/webhook payloads)
- `status`: `"success"`, `"failed"`, or `"skipped"`

### EnrichmentRegistry (`registry.py`)

Module-level singleton: `enrichment_registry`.

```python
enrichment_registry.register(MyProvider())       # raises ValueError on duplicate
enrichment_registry.get("virustotal")            # EnrichmentProviderBase | None
enrichment_registry.list_all()                   # all providers (configured + unconfigured)
enrichment_registry.list_configured()            # only is_configured() == True
enrichment_registry.list_for_type(IndicatorType.IP)  # configured + supports this type
```

### Registration (`__init__.py`)

```python
enrichment_registry.register(VirusTotalProvider())
enrichment_registry.register(AbuseIPDBProvider())
enrichment_registry.register(OktaProvider())
enrichment_registry.register(EntraProvider())
```

### Cache TTL Defaults (from `base.py`)

```python
DEFAULT_TTL_BY_TYPE = {
    IP: 3600, DOMAIN: 21600, HASH_*: 86400, URL: 1800, EMAIL: 3600, ACCOUNT: 900
}
```

Cache key format: `enrichment:{provider_name}:{type}:{value}`.

## Key Design Decisions

1. **No-raise contract enforced by convention, not runtime guard.** The base class documents the contract but does not wrap `enrich()` calls in try/except. Every concrete provider is responsible for its own exception handling. This was chosen over a decorator approach because the error context (which provider, what indicator) is richer when caught inside the provider.

2. **Three-state result (success/failed/skipped) instead of two.** `skipped` means the provider deliberately did not process the indicator (unconfigured, unsupported type). This distinction matters for the activity event's `providers_failed` vs simply absent. A provider returning `skipped` is normal; `failed` indicates an operational error.

3. **Entra OAuth token caching in provider instance.** `EntraProvider` caches the OAuth2 access token in memory (`_access_token`, `_token_expires_at`) with a 60-second buffer before expiry. This avoids a token acquisition roundtrip on every enrichment call. The token is per-process (not shared across workers), which is acceptable for single-tenant deployment.

4. **Malice verdict in `extracted` dict, not a separate field.** Each provider sets `extracted["malice"]` to one of: `Malicious`, `Suspicious`, `Benign`, or `Pending`. The `EnrichmentService` aggregates these using worst-wins logic (`Malicious > Suspicious > Benign > Pending`). This keeps the provider interface simple -- providers only need to map their own scoring to one of four values.

5. **Separate enrichment providers vs workflow integration clients.** `OktaProvider` (enrichment) reads user data. `OktaClient` (workflows, in `app/workflows/context.py`) performs lifecycle actions (suspend, revoke sessions). They share the same API but serve different purposes and live in different packages.

## Extension Pattern: Adding a New Provider (e.g. Shodan)

1. **Create `app/integrations/enrichment/shodan.py`**:
   ```python
   from app.integrations.enrichment.base import EnrichmentProviderBase
   from app.schemas.enrichment import EnrichmentResult
   from app.schemas.indicators import IndicatorType

   class ShodanProvider(EnrichmentProviderBase):
       provider_name = "shodan"
       display_name = "Shodan"
       supported_types = [IndicatorType.IP]
       cache_ttl_seconds = 3600

       def is_configured(self) -> bool:
           return bool(settings.SHODAN_API_KEY)

       async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult:
           try:
               if not self.is_configured():
                   return EnrichmentResult.skipped_result(self.provider_name, "Not configured")
               # ... API call, build extracted dict with "malice" key ...
               return EnrichmentResult.success_result(...)
           except Exception as exc:
               return EnrichmentResult.failure_result(self.provider_name, str(exc))
   ```

2. **Register in `app/integrations/enrichment/__init__.py`**:
   ```python
   from app.integrations.enrichment.shodan import ShodanProvider
   enrichment_registry.register(ShodanProvider())
   ```

3. **Add API key to `app/config.py`**: `SHODAN_API_KEY: str = ""`

4. **Add API research doc** at `docs/integrations/shodan/api_notes.md`.

5. **Seed field extractions** (optional) in `app/seed/` for the `enrichment_field_extractions` table if you want system-default field mapping.

## Common Failure Modes

| Symptom | Cause | Diagnosis |
|---|---|---|
| Provider returns `skipped` for every call | `is_configured()` returns False | Check env vars: `VIRUSTOTAL_API_KEY`, `ABUSEIPDB_API_KEY`, `OKTA_DOMAIN`+`OKTA_API_TOKEN`, `ENTRA_TENANT_ID`+`ENTRA_CLIENT_ID`+`ENTRA_CLIENT_SECRET` |
| Provider returns `failed` with HTTP 429 | Rate limit exceeded at the external API | AbuseIPDB explicitly handles 429; VT returns generic HTTP error. Check provider logs for rate limit messages |
| Entra token acquisition fails | Invalid client credentials or tenant ID | Check `entra_enrich_error` in logs; verify `ENTRA_*` env vars; check Azure app registration |
| Malice stays `Pending` after enrichment | No provider returned a `malice` field in `extracted` | Check that the provider's `_build_extracted()` or equivalent sets `extracted["malice"]` |
| Cache not working (all calls are live) | Cache backend misconfigured or TTL set to 0 | Check `app/cache/factory.py` config; verify `get_cache_ttl()` returns non-zero values |
| `enrichment_registry.list_for_type()` returns empty | No configured provider supports the indicator type | IP: VT + AbuseIPDB; Domain: VT; Hash: VT; Account: Okta + Entra; URL/Email: none in v1 |

## Test Coverage

| Test file | Scenarios |
|---|---|
| `tests/test_enrichment_providers.py` | Unit tests for each provider: success response parsing, 404 handling, HTTP error handling, rate limit handling, unconfigured skipping, `is_configured()` logic |
| `tests/test_enrichment_service.py` | `EnrichmentService.enrich_indicator()` with mocked providers: cache hit, cache miss, parallel execution, malice aggregation (worst-wins), mixed success/failure results |
| `tests/integration/test_enrichments.py` | Full enrichment flow via `POST /v1/enrichments`: on-demand enrichment returns structured results; validates response schema |
