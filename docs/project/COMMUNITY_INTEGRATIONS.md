# Community Integrations

This document explains how the Calseta community integration ecosystem works — how providers are distributed, installed, and contributed.

---

## How It Works

Calseta enrichment providers are **database-driven**. Each provider is a row in the `enrichment_providers` table with:

- HTTP config (API endpoints, headers, request templates)
- Auth config (encrypted credentials)
- Malice rules (threshold-based verdict derivation)
- Field extraction rules (which fields to surface to agents)

Because providers are just data — not Python code — they can be shared as JSON files and installed with a single API call. No code review, no dependency installation, no restart.

---

## Distribution Model

```
Calseta Repo
├── app/seed/enrichment_providers.py    ← Builtins (VT, AbuseIPDB, Okta, Entra)
│                                         Seeded at startup. Ship with every installation.
│
└── docs/integrations/community/        ← Community providers
    ├── greynoise/
    │   ├── provider.json               ← POST body for /v1/enrichment-providers
    │   ├── field_extractions.json      ← Optional extraction rules
    │   └── README.md                   ← Setup instructions
    ├── shodan/
    │   ├── provider.json
    │   └── README.md
    └── ...
```

### Builtins vs Custom vs Community

| Category | How It's Added | Where It Lives | Seeded at Startup? | Deletable? |
|----------|---------------|----------------|-------------------|------------|
| **Builtin** | Coded in `app/seed/enrichment_providers.py` | Database (seeded) | Yes | No (deactivate only) |
| **Custom** | `POST /v1/enrichment-providers` at runtime | Database | No | Yes |
| **Community** | JSON in repo → installed via API call | Repo (JSON) + Database (after install) | No | Yes |

Community providers are just custom providers with a documented, shareable config. They are NOT seeded at startup — operators choose which ones to install.

---

## Installing a Community Provider

### Step 1: Find the provider

Browse `docs/integrations/community/` in the repo. Each subdirectory is a community provider with a `README.md` explaining what it does and how to get API keys.

### Step 2: Install via API

```bash
# Install the provider config
curl -s -X POST \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d @docs/integrations/community/greynoise/provider.json \
  http://localhost:8000/v1/enrichment-providers | jq
```

### Step 3: Set credentials

The `provider.json` ships without real credentials (the `auth_config` field contains placeholder values or is omitted). After installing, set your credentials:

```bash
curl -X PATCH \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"auth_config": {"api_key": "your-real-api-key"}}' \
  http://localhost:8000/v1/enrichment-providers/$PROVIDER_UUID
```

### Step 4: Test

```bash
curl -X POST \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"indicator_type": "ip", "indicator_value": "8.8.8.8"}' \
  http://localhost:8000/v1/enrichment-providers/$PROVIDER_UUID/test | jq
```

### Step 5: (Optional) Install field extractions

Some community providers include a `field_extractions.json` with recommended extraction rules. These map fields from the provider's raw API response to the agent-facing `extracted` dict.

```bash
# Field extractions are installed via the field extractions API
# (if the provider includes a field_extractions.json)
cat docs/integrations/community/greynoise/field_extractions.json | \
  jq -c '.[]' | \
  while read -r rule; do
    curl -s -X POST \
      -H "Authorization: Bearer $ADMIN_API_KEY" \
      -H "Content-Type: application/json" \
      -d "$rule" \
      http://localhost:8000/v1/enrichment-field-extractions
  done
```

---

## Removing a Community Provider

```bash
curl -X DELETE \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  http://localhost:8000/v1/enrichment-providers/$PROVIDER_UUID
```

The provider is immediately removed from the enrichment pipeline. No restart needed.

---

## Contributing a Community Provider

Want to share your enrichment provider config with the community? Here's how.

### Directory Structure

Create a directory under `docs/integrations/community/{provider_name}/` with:

```
docs/integrations/community/greynoise/
├── provider.json               # Required: POST body for the create endpoint
├── field_extractions.json      # Optional: recommended field extraction rules
└── README.md                   # Required: setup instructions
```

### provider.json

This is the exact request body for `POST /v1/enrichment-providers`, minus real credentials. Use placeholder values in `auth_config` or omit it entirely.

```json
{
  "provider_name": "greynoise",
  "display_name": "GreyNoise",
  "description": "GreyNoise Community API — IP noise and classification lookups.",
  "supported_indicator_types": ["ip"],
  "auth_type": "api_key",
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
}
```

**Important:** Do NOT include `auth_config` with real credentials. Operators set their own credentials after installation.

### field_extractions.json (optional)

An array of field extraction rule objects:

```json
[
  {
    "provider_name": "greynoise",
    "indicator_type": "ip",
    "source_path": "classification",
    "target_key": "classification",
    "value_type": "string",
    "description": "GreyNoise classification (benign, malicious, unknown)"
  },
  {
    "provider_name": "greynoise",
    "indicator_type": "ip",
    "source_path": "noise",
    "target_key": "is_noise",
    "value_type": "bool",
    "description": "Whether the IP is seen as internet background noise"
  }
]
```

### README.md

Include:

1. **What the provider does** — one paragraph
2. **How to get API keys** — link to the provider's developer portal
3. **Rate limits** — what to expect
4. **Supported indicator types** — which types this provider handles
5. **Installation instructions** — copy-paste `curl` commands
6. **Malice logic** — how verdicts are derived
7. **Notes** — any caveats, limitations, or quirks

See `docs/integrations/community/greynoise/README.md` for a complete example.

### PR Checklist

- [ ] `provider_name` is lowercase, alphanumeric + underscores only
- [ ] `provider.json` is valid JSON and creates successfully via the API
- [ ] No real credentials in `provider.json`
- [ ] `README.md` includes API key instructions and rate limit info
- [ ] `field_extractions.json` (if included) has correct `source_path` values verified against the real API response
- [ ] Tested against the real API with a valid key

### What NOT to Include

- **Python code.** Community providers are JSON configs, not code.
- **Real API keys or credentials.** Use placeholder values or omit `auth_config`.
- **Sensitive data in test examples.** Use well-known safe IPs (8.8.8.8, 1.1.1.1) in examples.

---

## Future: Integration Catalog (v1.1+)

A browsable catalog of available community integrations — either in the admin UI or on the Calseta website. For now, the `docs/integrations/community/` directory in the repo IS the catalog.

Planned features:
- **UI "Import" button** — browse and install community providers from the admin UI
- **Provider marketplace** — a web page listing all community providers with install instructions
- **One-click install** — `POST /v1/enrichment-providers/import?source=community&name=greynoise`

---

## FAQ

### Can community providers access my database?

No. Community providers are JSON configs — they define HTTP requests to external APIs. They do not execute code and have no access to your database, filesystem, or internal network.

### Are community provider credentials stored securely?

Yes. When you set `auth_config` via the API, credentials are encrypted at rest using Fernet encryption. They are decrypted only at execution time when making the API call.

### What happens if I install a community provider and the API changes?

The provider will start returning errors. You can update the provider's `http_config` and `malice_rules` via the PATCH endpoint, or deactivate it until the config is updated.

### Can I modify a community provider after installing it?

Yes. Once installed, it's just a regular custom provider in your database. Use the PATCH endpoint to adjust any config.

### How do I update a community provider when a new version is released?

Delete the old provider and re-install from the updated `provider.json`, or use the PATCH endpoint to apply specific changes.
