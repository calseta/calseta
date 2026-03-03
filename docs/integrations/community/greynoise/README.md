# GreyNoise Community Provider

## What It Does

GreyNoise identifies IPs that are mass-scanning the internet (internet background noise) vs IPs engaged in targeted attacks. This is valuable context for SOC triage — if an IP flagged in an alert is a known mass-scanner, it's likely opportunistic rather than targeted.

The Community API provides:
- **Noise classification** — is this IP mass-scanning the internet?
- **RIOT classification** — does this IP belong to a known benign service (Google, Microsoft, etc.)?
- **Malice classification** — benign, malicious, or unknown
- **Actor identification** — named actors or services associated with the IP

## Supported Indicator Types

- `ip` — IPv4 addresses only (Community API does not support IPv6)

## How to Get an API Key

1. Create a free account at [https://www.greynoise.io/](https://www.greynoise.io/)
2. Navigate to **Account** → **API Key**
3. Copy your Community API key

The Community API tier is free and includes:
- 50 requests/day (IP lookups)
- Basic noise + RIOT + classification data

For higher rate limits and additional data (tags, CVEs, raw scan data), upgrade to the paid Enterprise API.

## Rate Limits

| Tier | Requests/Day | Notes |
|------|-------------|-------|
| Community (free) | 50 | Basic classification data |
| Enterprise | Varies by plan | Full scan data, tags, CVEs |

Recommended cache TTL: **3600 seconds (1 hour)** — IP classification doesn't change frequently.

## Installation

### 1. Install the provider

```bash
curl -s -X POST \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d @docs/integrations/community/greynoise/provider.json \
  http://localhost:8000/v1/enrichment-providers | jq
```

Save the returned `uuid` for the next steps.

### 2. Set your API key

```bash
curl -X PATCH \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"auth_config": {"api_key": "YOUR_GREYNOISE_API_KEY"}}' \
  http://localhost:8000/v1/enrichment-providers/$PROVIDER_UUID
```

### 3. Test

```bash
curl -s -X POST \
  -H "Authorization: Bearer $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"indicator_type": "ip", "indicator_value": "8.8.8.8"}' \
  http://localhost:8000/v1/enrichment-providers/$PROVIDER_UUID/test | jq
```

Expected response for 8.8.8.8 (Google DNS):
```json
{
  "success": true,
  "extracted": {
    "classification": "benign",
    "is_noise": false,
    "is_riot": true,
    "actor_name": "Google",
    "malice": "Benign"
  }
}
```

## Malice Logic

| Condition | Verdict |
|-----------|---------|
| `classification == "malicious"` | Malicious |
| `noise == true` (mass-scanning) | Suspicious |
| All other cases | Benign |
| IP not found in GreyNoise | Pending |

## Sample API Response (Community)

```json
{
  "ip": "8.8.8.8",
  "noise": false,
  "riot": true,
  "classification": "benign",
  "name": "Google",
  "link": "https://viz.greynoise.io/riot/8.8.8.8",
  "last_seen": "2026-03-01",
  "message": "Success"
}
```

## Notes

- The Community API only returns basic classification. For detailed scan data (ports, protocols, tags, CVEs), you need the Enterprise API with different endpoints.
- GreyNoise focuses on IPv4. IPv6 support is limited.
- The `riot` field identifies known benign services — useful for reducing false positives.
