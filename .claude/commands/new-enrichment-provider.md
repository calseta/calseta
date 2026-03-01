---
name: new-enrichment-provider
description: Scaffold a new enrichment provider plugin for Calseta AI. Use when adding a new threat intelligence or identity source for IOC enrichment.
argument-hint: "<provider-name> (e.g. shodan, greynoise)"
allowed-tools: Read, Write, Glob, WebFetch
---

Scaffold a new enrichment provider for: **$ARGUMENTS**

Follow these steps exactly:

1. **Research first.** Before writing any code, fetch and read the official API documentation for $ARGUMENTS. Produce `docs/integrations/$ARGUMENTS/api_notes.md` with:
   - Relevant endpoint(s) and request/response field names and types
   - Which indicator types are supported (ip, domain, hash_md5, hash_sha1, hash_sha256, url, email, account)
   - Authentication method and how to configure credentials
   - Rate limits and any pagination behavior
   - Edge cases (e.g., what does the API return for an unknown/clean indicator?)
   - Any automation endpoints that could power pre-built workflows (document even if not implemented now)

2. **Create the provider file** at `app/integrations/enrichment/$ARGUMENTS.py` implementing `EnrichmentProviderBase`:
   ```python
   class <ProviderName>EnrichmentProvider(EnrichmentProviderBase):
       provider_name = "$ARGUMENTS"
       display_name = "<Human Readable Name>"
       supported_types = [...]  # list[IndicatorType]
       cache_ttl_seconds = ...  # use defaults from PRD Section 7.2 unless provider-specific TTL makes more sense

       async def enrich(self, value: str, indicator_type: IndicatorType) -> EnrichmentResult: ...
       def is_configured(self) -> bool: ...
   ```
   - `enrich()` must NEVER raise exceptions — catch all errors and return `EnrichmentResult(success=False, ...)`.
   - `is_configured()` checks that required env vars are present.
   - Use `ctx.http` (httpx.AsyncClient) for all HTTP calls — never import httpx directly.
   - Structure `EnrichmentResult.data` to be minimal and agent-readable — not a raw API dump.

3. **Add env var keys** to `.env.local.example` and `.env.prod.example` with descriptive comments.

4. **Register the provider** in `app/integrations/enrichment/__init__.py`.

5. **Write tests** in `tests/integrations/enrichment/test_$ARGUMENTS.py` covering:
   - Successful enrichment returns structured `EnrichmentResult` with expected fields
   - API error returns `EnrichmentResult(success=False)` — no exception raised
   - `is_configured()` returns False when env vars are absent
   - Cache key format is correct

6. **Consider pre-built workflows.** If the API supports lifecycle/remediation actions (e.g., block an IP, submit a file for sandbox analysis), note them in `api_notes.md` under "Available Automation Endpoints". Pre-built workflows can be added alongside the provider.

7. **Update `docs/HOW_TO_ADD_ENRICHMENT_PROVIDER.md`** if the implementation reveals anything not covered.
