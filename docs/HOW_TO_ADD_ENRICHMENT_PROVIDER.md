# How to Add an Enrichment Provider

This guide walks through adding a new enrichment provider to Calseta AI. By the end, your provider will be queried automatically during the alert enrichment pipeline and available for on-demand enrichment via `POST /v1/enrichments`.

Enrichment providers are **database-driven** — each provider is a row in the `enrichment_providers` table with templated HTTP configs, malice threshold rules, and field extraction mappings. There are three ways to add a provider, depending on your use case:

| Method | When to Use | Code Changes? | Restart? |
|--------|-------------|---------------|----------|
| **Runtime (API)** | Custom provider for your deployment | No | No |
| **Builtin (Seed)** | Ships with every Calseta installation | Yes | Yes |
| **Community (JSON)** | Shareable config contributed to the repo | No app code | No |

---

## Architecture Overview

```
Alert Ingested
    │
    ├─ enrich_alert task (worker queue)
    │       │
    │       ├─ For each indicator:
    │       │     ├─ Check cache (enrichment:{provider}:{type}:{value})
    │       │     ├─ If miss: call provider.enrich(value, type) concurrently
    │       │     ├─ Cache successful results for TTL
    │       │     └─ Aggregate malice verdict (worst wins)
    │       │
    │       └─ Update indicator.enrichment_results, indicator.malice
    │
    └─ POST /v1/enrichments (on-demand, synchronous)
            └─ Same flow, single indicator, returns results immediately
```

All providers run concurrently via `asyncio.gather()`. A single provider failure never blocks other providers or other indicators. The `EnrichmentService` pipeline is completely decoupled from how providers are configured — it only sees `EnrichmentProviderBase` instances.

---

## Step 0: Research the Provider API

**Before writing any config**, fetch and analyze the official API documentation. Create `docs/integrations/{name}/api_notes.md` with:

- API base URL and version
- Authentication method (API key header, bearer token, OAuth2)
- Endpoint paths for each indicator type
- Response schema and which fields are useful for SOC analysts
- Rate limits and error codes
- How to derive a malice verdict from the response

This is mandatory. See existing examples: `docs/integrations/virustotal/api_notes.md`, `docs/integrations/abuseipdb/api_notes.md`.

---

## Method A: Add a Custom Provider at Runtime (API)

This is the simplest method. No code changes, no restart, no migration. Just one API call.

### 1. Create the provider

```bash
curl -X POST http://localhost:8000/v1/enrichment-providers \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_name": "greynoise",
    "display_name": "GreyNoise",
    "description": "GreyNoise Community API — IP noise and classification lookups.",
    "supported_indicator_types": ["ip"],
    "auth_type": "api_key",
    "auth_config": {
      "api_key": "your-greynoise-api-key"
    },
    "http_config": {
      "steps": [
        {
          "name": "lookup",
          "method": "GET",
          "url": "https://api.greynoise.io/v3/community/{{indicator.value}}",
          "headers": {
            "key": "{{auth.api_key}}",
            "Accept": "application/json"
          },
          "timeout_seconds": 30,
          "expected_status": [200],
          "not_found_status": [404]
        }
      ]
    },
    "malice_rules": {
      "rules": [
        {
          "field": "classification",
          "operator": "==",
          "value": "malicious",
          "verdict": "Malicious"
        },
        {
          "field": "noise",
          "operator": "==",
          "value": true,
          "verdict": "Suspicious"
        }
      ],
      "default_verdict": "Benign",
      "not_found_verdict": "Pending"
    },
    "default_cache_ttl_seconds": 3600,
    "cache_ttl_by_type": {
      "ip": 3600
    }
  }'
```

The response includes the provider's UUID. The provider is **immediately active** in the enrichment pipeline.

### 2. Test the provider

```bash
curl -X POST http://localhost:8000/v1/enrichment-providers/$PROVIDER_UUID/test \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "indicator_type": "ip",
    "indicator_value": "8.8.8.8"
  }'
```

### 3. Manage the provider

```bash
# List all providers
curl http://localhost:8000/v1/enrichment-providers \
  -H "Authorization: Bearer $API_KEY"

# Deactivate (temporarily remove from pipeline)
curl -X POST http://localhost:8000/v1/enrichment-providers/$UUID/deactivate \
  -H "Authorization: Bearer $ADMIN_API_KEY"

# Update credentials
curl -X PATCH http://localhost:8000/v1/enrichment-providers/$UUID \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"auth_config": {"api_key": "new-key-here"}}'

# Delete (custom providers only)
curl -X DELETE http://localhost:8000/v1/enrichment-providers/$UUID \
  -H "Authorization: Bearer $ADMIN_API_KEY"
```

---

## Method B: Add a Builtin Provider (Ships with Calseta)

Builtins are seeded at startup from `app/seed/enrichment_providers.py`. They are marked `is_builtin: true` and cannot be deleted. Use this for providers that every Calseta installation should have.

### 1. Add the provider definition

Edit `app/seed/enrichment_providers.py` and add to `_BUILTIN_PROVIDERS`:

```python
{
    "provider_name": "shodan",
    "display_name": "Shodan",
    "description": "Shodan API — internet-wide scan data for IP addresses.",
    "supported_indicator_types": ["ip"],
    "auth_type": "api_key",
    "env_var_mapping": {"api_key": "SHODAN_API_KEY"},
    "default_cache_ttl_seconds": 3600,
    "cache_ttl_by_type": {"ip": 3600},
    "http_config": {
        "steps": [
            {
                "name": "lookup",
                "method": "GET",
                "url": "https://api.shodan.io/shodan/host/{{indicator.value}}",
                "headers": {},
                "timeout_seconds": 30,
                "expected_status": [200],
                "not_found_status": [404],
            }
        ],
    },
    "malice_rules": {
        "rules": [
            {
                "field": "tags",
                "operator": "contains",
                "value": "malware",
                "verdict": "Malicious",
            },
        ],
        "default_verdict": "Benign",
        "not_found_verdict": "Pending",
    },
},
```

### 2. Add field extraction rules

In the same file, add extractions in `_build_extractions()`:

```python
# Shodan
result.extend([
    ("shodan", "ip", "ports", "open_ports", "list", "Open ports"),
    ("shodan", "ip", "org", "organization", "string", "Organization"),
    ("shodan", "ip", "os", "os", "string", "Operating system"),
    ("shodan", "ip", "tags", "tags", "list", "Shodan tags"),
    ("shodan", "ip", "vulns", "vulnerabilities", "list", "Known CVEs"),
])
```

### 3. Add env var mapping

Add the env var to `app/config.py`:

```python
SHODAN_API_KEY: str = ""
```

And to `.env.local.example` / `.env.prod.example`:

```
SHODAN_API_KEY=
```

### 4. Restart

The provider is seeded idempotently on next startup. Existing installations get it automatically.

---

## HTTP Config Reference

The `http_config` JSONB column defines how the provider makes API calls.

### Single-Step Provider (most common)

```json
{
  "steps": [
    {
      "name": "lookup",
      "method": "GET",
      "url": "https://api.example.com/v1/check/{{indicator.value}}",
      "headers": {
        "Authorization": "Bearer {{auth.api_key}}",
        "Accept": "application/json"
      },
      "timeout_seconds": 30,
      "expected_status": [200],
      "not_found_status": [404]
    }
  ]
}
```

### Multi-Step Provider (OAuth + data lookup)

For providers requiring an OAuth2 token before the data lookup:

```json
{
  "steps": [
    {
      "name": "token",
      "method": "POST",
      "url": "https://auth.example.com/oauth2/token",
      "headers": {"Content-Type": "application/x-www-form-urlencoded"},
      "form_body": {
        "client_id": "{{auth.client_id}}",
        "client_secret": "{{auth.client_secret}}",
        "grant_type": "client_credentials"
      },
      "timeout_seconds": 30,
      "expected_status": [200]
    },
    {
      "name": "user_lookup",
      "method": "GET",
      "url": "https://api.example.com/v1/users/{{indicator.value | urlencode}}",
      "headers": {
        "Authorization": "Bearer {{steps.token.response.access_token}}"
      },
      "timeout_seconds": 30,
      "expected_status": [200],
      "not_found_status": [404]
    },
    {
      "name": "user_groups",
      "method": "GET",
      "url": "https://api.example.com/v1/users/{{steps.user_lookup.response.id}}/groups",
      "headers": {
        "Authorization": "Bearer {{steps.token.response.access_token}}"
      },
      "timeout_seconds": 30,
      "expected_status": [200],
      "optional": true
    }
  ]
}
```

### URL Templates by Type

For providers that use different endpoints per indicator type (e.g., VirusTotal):

```json
{
  "steps": [
    {
      "name": "lookup",
      "method": "GET",
      "url": "https://api.example.com/v3/ip/{{indicator.value}}",
      "headers": {"x-apikey": "{{auth.api_key}}"},
      "timeout_seconds": 30,
      "expected_status": [200]
    }
  ],
  "url_templates_by_type": {
    "ip": "https://api.example.com/v3/ip/{{indicator.value}}",
    "domain": "https://api.example.com/v3/domain/{{indicator.value}}",
    "hash_sha256": "https://api.example.com/v3/file/{{indicator.value}}"
  }
}
```

When `url_templates_by_type` is present, the first step's URL is overridden based on the indicator type being enriched.

### Step Properties

| Property | Required | Description |
|----------|----------|-------------|
| `name` | Yes | Unique name for this step (used in `{{steps.<name>.response.*}}`) |
| `method` | Yes | HTTP method: `GET`, `POST` |
| `url` | Yes | URL template with `{{...}}` placeholders |
| `headers` | No | Request headers (templates supported) |
| `form_body` | No | URL-encoded form body (for OAuth token requests) |
| `timeout_seconds` | No | Request timeout (default: 30) |
| `expected_status` | No | HTTP status codes that mean success (default: `[200]`) |
| `not_found_status` | No | Status codes that mean "not found" (distinct from error) |
| `optional` | No | If `true`, step failure doesn't abort the pipeline |

### Template Variables

| Variable | Description |
|----------|-------------|
| `{{indicator.value}}` | The IOC value being enriched |
| `{{indicator.type}}` | The indicator type (`ip`, `domain`, etc.) |
| `{{auth.<field>}}` | Resolved credential field (from `auth_config` or `env_var_mapping`) |
| `{{steps.<name>.response.<path>}}` | Dot-path into a previous step's response body |
| `{{value \| urlencode}}` | URL-encode the resolved value |

---

## Malice Rules Reference

The `malice_rules` JSONB defines how to derive a malice verdict from the raw API response. Rules are evaluated in order — **first match wins**.

```json
{
  "rules": [
    {"field": "score", "operator": ">=", "value": 75, "verdict": "Malicious"},
    {"field": "score", "operator": ">=", "value": 25, "verdict": "Suspicious"}
  ],
  "default_verdict": "Benign",
  "not_found_verdict": "Pending"
}
```

### Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `>` | Greater than | `{"field": "score", "operator": ">", "value": 0}` |
| `>=` | Greater than or equal | `{"field": "score", "operator": ">=", "value": 75}` |
| `<` | Less than | `{"field": "score", "operator": "<", "value": 10}` |
| `<=` | Less than or equal | `{"field": "score", "operator": "<=", "value": 5}` |
| `==` | Equal | `{"field": "classification", "operator": "==", "value": "malicious"}` |
| `!=` | Not equal | `{"field": "status", "operator": "!=", "value": "clean"}` |
| `contains` | List contains value | `{"field": "tags", "operator": "contains", "value": "malware"}` |
| `in` | Value is in list | `{"field": "verdict", "operator": "in", "value": ["malicious", "phishing"]}` |

### Verdicts

Four possible values, aggregated across providers using worst-wins:

```
Malicious(3) > Suspicious(2) > Benign(1) > Pending(0)
```

### Field Paths

Use dot-notation to reach nested fields in the raw API response:

- `data.abuseConfidenceScore` → `response["data"]["abuseConfidenceScore"]`
- `data.attributes.last_analysis_stats.malicious` → deep nested access

For multi-step providers, the raw response is keyed by step name:
- `user_lookup.status` → `response["user_lookup"]["status"]`

---

## Auth Types

| Type | `auth_config` Shape | Description |
|------|---------------------|-------------|
| `no_auth` | `null` | No authentication needed |
| `api_key` | `{"api_key": "..."}` | Single API key |
| `api_token` | `{"domain": "...", "api_token": "..."}` | Domain + token (e.g., Okta) |
| `oauth2_client_credentials` | `{"tenant_id": "...", "client_id": "...", "client_secret": "..."}` | OAuth2 client credentials flow |

Credentials in `auth_config` are **encrypted at rest** using Fernet encryption. They are decrypted only at execution time.

For builtin providers, `env_var_mapping` provides a fallback:

```json
{
  "env_var_mapping": {
    "api_key": "VIRUSTOTAL_API_KEY"
  }
}
```

Resolution order: DB `auth_config` (decrypted) → env var fallback.

---

## Builtin Provider Restrictions

Builtin providers (`is_builtin: true`) have restrictions to prevent accidental misconfiguration:

| Operation | Allowed? |
|-----------|----------|
| Delete | No (use deactivate instead) |
| Change `provider_name` | No |
| Change `display_name` | No |
| Change `supported_indicator_types` | No |
| Change `http_config` | No |
| Change `is_active` | Yes |
| Change `auth_config` | Yes |
| Change `description` | Yes |
| Change `malice_rules` | Yes |
| Change `default_cache_ttl_seconds` | Yes |
| Change `cache_ttl_by_type` | Yes |

---

## Field Extractions

Field extraction rules define which fields from the raw API response are surfaced in the agent-facing `extracted` dict. They are stored in the `enrichment_field_extractions` table.

Builtins get ~64 system-seeded extraction rules. Custom providers can add extractions via the field extractions API (or they will be derived from the raw response).

Each extraction rule maps:
- `source_path` (dot-notation into raw response) → `target_key` (key in `extracted` dict)
- `value_type`: `string`, `int`, `float`, `bool`, `list`, `dict`, `any`

Example: For AbuseIPDB, the rule `source_path="data.abuseConfidenceScore"`, `target_key="abuse_confidence_score"`, `value_type="int"` extracts the confidence score from the raw response into the agent-facing `extracted` dict.

---

## Cache Key Format and TTL

Cache keys follow a deterministic format:

```
enrichment:{provider_name}:{indicator_type}:{value}
```

TTL is resolved per-provider:
1. Provider's `cache_ttl_by_type` (per-type overrides)
2. Provider's `default_cache_ttl_seconds` (fallback)

Default TTLs by type (recommended):

| Type | TTL | Rationale |
|------|-----|-----------|
| IP | 3600s (1h) | Reputation changes frequently |
| Domain | 21600s (6h) | Reputation changes less often |
| Hash | 86400s (24h) | File hashes are immutable |
| URL | 1800s (30m) | URLs can be taken down quickly |
| Account | 900s (15m) | Account status can change rapidly |

---

## Indicator Types

```python
class IndicatorType(StrEnum):
    IP = "ip"
    DOMAIN = "domain"
    HASH_MD5 = "hash_md5"
    HASH_SHA1 = "hash_sha1"
    HASH_SHA256 = "hash_sha256"
    URL = "url"
    EMAIL = "email"
    ACCOUNT = "account"
```

---

## Existing Builtin Providers

| Provider | Auth | Supported Types | Malice Logic |
|----------|------|-----------------|--------------|
| VirusTotal | API key header | ip, domain, hash_md5, hash_sha1, hash_sha256 | `malicious > 0` → Malicious; `suspicious > 0` → Suspicious |
| AbuseIPDB | API key header | ip | Score >= 75 → Malicious; >= 25 → Suspicious |
| Okta | SSWS token | account | N/A (account lookup, no malice scoring) |
| Entra | OAuth2 client credentials | account | N/A (account lookup, no malice scoring) |

---

## Common Pitfalls

### 1. Forgetting `not_found_status` in steps

Without `not_found_status`, a 404 response is treated as an error. Set `"not_found_status": [404]` so the engine correctly identifies "not found" vs "API error".

### 2. Wrong field paths in malice_rules

Field paths are relative to the raw API response. Test with the `/test` endpoint first to see the actual response structure, then write your malice rules against it.

### 3. Forgetting `| urlencode` for values in URLs

If indicator values can contain special characters (email addresses, URLs), use `{{indicator.value | urlencode}}` in the URL template.

### 4. Not encrypting credentials

When passing `auth_config` via the API, the system automatically encrypts it before storage. Never store plaintext credentials in the database directly.

### 5. Reusing `provider_name`

Each `provider_name` must be globally unique. The API returns `409 DUPLICATE_PROVIDER` if you try to create a provider with an existing name.
