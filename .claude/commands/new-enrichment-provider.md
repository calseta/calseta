---
name: new-enrichment-provider
description: Scaffold a new enrichment provider plugin for Calseta. Use when adding a new threat intelligence or identity source for IOC enrichment.
argument-hint: "<provider-name> (e.g. shodan, greynoise)"
allowed-tools: Read, Write, Glob, WebFetch, WebSearch
---

Scaffold a new enrichment provider for: **$ARGUMENTS**

Enrichment providers are **database-driven** — each provider is a row in the `enrichment_providers` table with templated HTTP configs, malice rules, and field extraction mappings. No Python code is needed. Read `app/integrations/enrichment/CONTEXT.md` and `docs/HOW_TO_ADD_ENRICHMENT_PROVIDER.md` for full architecture context.

Follow these steps exactly:

1. **Research first.** Before writing any config, fetch and read the official API documentation for $ARGUMENTS. Produce `docs/integrations/$ARGUMENTS/api_notes.md` with:
   - Relevant endpoint(s) and request/response field names and types
   - Which indicator types are supported (ip, domain, hash_md5, hash_sha1, hash_sha256, url, email, account)
   - Authentication method (API key header, bearer token, OAuth2 client credentials)
   - Rate limits and any pagination behavior
   - Edge cases (e.g., what does the API return for an unknown/clean indicator? What status code for "not found"?)
   - How to derive a malice verdict from the response (which fields, what thresholds)
   - Any automation endpoints that could power pre-built workflows (document even if not implemented now)

2. **Determine provider type** — is this a builtin (ships with every Calseta installation) or a community provider (optional, installed by operators)?

3. **For a BUILTIN provider**, add the provider definition to `app/seed/enrichment_providers.py`:
   - Add to the `_BUILTIN_PROVIDERS` list with: `provider_name`, `display_name`, `description`, `supported_indicator_types`, `auth_type`, `env_var_mapping`, `http_config` (steps array), `malice_rules`, `default_cache_ttl_seconds`, `cache_ttl_by_type`
   - Add field extraction rules in `_build_extractions()` mapping raw response paths to agent-facing field names
   - Add env var(s) to `app/config.py`, `.env.local.example`, and `.env.prod.example`
   - Follow the patterns of the existing 4 builtins (virustotal, abuseipdb, okta, entra)

4. **For a COMMUNITY provider**, create `docs/integrations/community/$ARGUMENTS/`:
   - `provider.json` — the full `POST /v1/enrichment-providers` request body (NO real credentials)
   - `field_extractions.json` — recommended field extraction rules
   - `README.md` — setup instructions (how to get API keys, rate limits, installation curl commands, malice logic, sample response)
   - Follow the pattern in `docs/integrations/community/greynoise/`

5. **Build the HTTP config** following these patterns:
   - **Single-step** (most providers): one `steps` entry with `name`, `method`, `url`, `headers`, `expected_status`, `not_found_status`
   - **Multi-step** (OAuth + lookup): token step → data step, referencing `{{steps.token.response.access_token}}`
   - **Per-type URLs**: use `url_templates_by_type` if the provider has different endpoints per indicator type
   - Use `{{indicator.value}}` for the IOC, `{{auth.<field>}}` for credentials, `{{value | urlencode}}` for URL-safe encoding

6. **Build malice rules** with ordered threshold rules (first match wins):
   ```json
   {
     "rules": [
       {"field": "path.to.score", "operator": ">=", "value": 75, "verdict": "Malicious"},
       {"field": "path.to.score", "operator": ">=", "value": 25, "verdict": "Suspicious"}
     ],
     "default_verdict": "Benign",
     "not_found_verdict": "Pending"
   }
   ```
   Operators: `>`, `>=`, `<`, `<=`, `==`, `!=`, `contains`, `in`

7. **Test the provider** using the CRUD API test endpoint:
   ```bash
   # Create (or it will be seeded at startup for builtins)
   curl -X POST http://localhost:8000/v1/enrichment-providers \
     -H "Authorization: Bearer $ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d @provider.json

   # Test with a known indicator
   curl -X POST http://localhost:8000/v1/enrichment-providers/$UUID/test \
     -H "Authorization: Bearer $ADMIN_KEY" \
     -H "Content-Type: application/json" \
     -d '{"indicator_type": "ip", "indicator_value": "8.8.8.8"}'
   ```

8. **Consider pre-built workflows.** If the API supports lifecycle/remediation actions (e.g., block an IP, submit a file for sandbox analysis), note them in `api_notes.md` under "Available Automation Endpoints".
