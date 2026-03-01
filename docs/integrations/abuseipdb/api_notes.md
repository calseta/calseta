# AbuseIPDB API Notes

Source: AbuseIPDB API v2
Reference: https://docs.abuseipdb.com/

---

## Authentication

API key passed as request header:
```
Key: {ABUSEIPDB_API_KEY}
```

No OAuth or token exchange. Keys are obtained from the AbuseIPDB web dashboard after account registration.

---

## Key Endpoints Used by Calseta AI

### Check IP address (primary enrichment endpoint)
```
GET https://api.abuseipdb.com/api/v2/check
Key: {ABUSEIPDB_API_KEY}
Accept: application/json

?ipAddress=185.220.101.1&maxAgeInDays=90&verbose
```

Query parameters:
| Parameter | Required | Notes |
|---|---|---|
| `ipAddress` | Yes | IPv4 or IPv6 address |
| `maxAgeInDays` | No | Report lookback window, 1–365, default 30. Calseta AI uses 90. |
| `verbose` | No | Flag (no value). Include `reports` array in response when present. Do not use in production — increases payload size significantly. |

Returns `200 OK` with JSON body, or `422 Unprocessable Entity` for invalid IP, or `429` for rate limit exceeded.

---

## Request/Response Field Reference

### Success response

```json
{
  "data": {
    "ipAddress": "185.220.101.1",
    "isPublic": true,
    "ipVersion": 4,
    "isWhitelisted": false,
    "abuseConfidenceScore": 100,
    "countryCode": "DE",
    "usageType": "Data Center/Web Hosting/Transit",
    "isp": "Tor-Exit",
    "domain": "dan.me.uk",
    "hostnames": ["dan.me.uk"],
    "isTor": true,
    "totalReports": 8941,
    "numDistinctUsers": 342,
    "lastReportedAt": "2024-01-15T14:23:00+00:00",
    "reports": []
  }
}
```

### Field reference (`data` object)

| Field | Type | Notes |
|---|---|---|
| `ipAddress` | string | Queried IP (may be normalized, e.g. IPv6 expanded) |
| `isPublic` | boolean | False for RFC1918 private IPs — should not normally appear |
| `ipVersion` | integer | `4` or `6` |
| `isWhitelisted` | boolean | Whether IP is on AbuseIPDB whitelist |
| `abuseConfidenceScore` | integer (0–100) | **Primary malice signal** — percentage confidence the IP is malicious based on recent reports |
| `countryCode` | string | ISO 3166-1 alpha-2 country code e.g. `"DE"`, `"US"` |
| `usageType` | string | ISP usage type — see enum below |
| `isp` | string | ISP/hosting provider name e.g. `"Amazon.com Inc."` |
| `domain` | string | Domain associated with the IP's ISP |
| `hostnames` | string[] | Reverse DNS hostnames for this IP |
| `isTor` | boolean | Whether this IP is a known Tor exit node |
| `totalReports` | integer | Total abuse reports in the `maxAgeInDays` window |
| `numDistinctUsers` | integer | Number of distinct users who reported this IP |
| `lastReportedAt` | string (ISO 8601) | Timestamp of most recent abuse report (null if never reported) |
| `reports` | array | Only present with `?verbose`. Individual report objects: `{ reportedAt, comment, categories: [int], reporterId, reporterCountryCode, reporterCountryName }` |

### `usageType` enum values

| Value | Meaning |
|---|---|
| `"Data Center/Web Hosting/Transit"` | Cloud/VPS/hosting |
| `"Internet Service Provider"` | Residential or business ISP |
| `"Search Engine Spider"` | Web crawler |
| `"Content Delivery Network"` | CDN edge node |
| `"Mobile ISP"` | Mobile carrier |
| `"Government"` | Government network |
| `"Military"` | Military network |
| `"University/College/School"` | Education |
| `"Library"` | Library |
| `"Fixed Line ISP"` | Fixed-line ISP |
| `"Organization"` | Business or organization |
| `"Reserved"` | Reserved IP space |
| `"Reserved - IANA"` | IANA reserved |

### Enrichment field extraction paths (Calseta `enrichment_field_extractions` seeding)

| `target_key` | `source_path` | Notes |
|---|---|---|
| `abuse_confidence_score` | `abuseConfidenceScore` | 0–100 |
| `country_code` | `countryCode` | 2-letter code |
| `usage_type` | `usageType` | ISP type string |
| `isp` | `isp` | ISP name |
| `domain` | `domain` | ISP domain |
| `total_reports` | `totalReports` | Report count |
| `num_distinct_users` | `numDistinctUsers` | Distinct reporters |
| `last_reported_at` | `lastReportedAt` | ISO 8601 or null |
| `is_tor` | `isTor` | Boolean |
| `is_whitelisted` | `isWhitelisted` | Boolean |

### Malice determination

Calseta AI maps `abuseConfidenceScore` to `malice` enum:
| Score | `malice` |
|---|---|
| 0 | `Benign` |
| 1–24 | `Suspicious` |
| 25–100 | `Malicious` |

---

## Available Automation Endpoints (for pre-built workflows)

AbuseIPDB v2 is primarily a read API. One write endpoint exists:

### Report an IP address
```
POST https://api.abuseipdb.com/api/v2/report
Key: {ABUSEIPDB_API_KEY}
Content-Type: application/json

{
  "ip": "185.220.101.1",
  "categories": "18,22",
  "comment": "Port scanning observed from this IP. Alert: {alert_uuid}"
}
```

Categories (relevant subset):
| ID | Name |
|---|---|
| 14 | Port Scan |
| 15 | Hacking |
| 18 | Brute-Force |
| 19 | Bad Web Bot |
| 20 | Exploited Host |
| 21 | Web App Attack |
| 22 | SSH |
| 23 | IoT Targeted |

This is the pre-built workflow action for Calseta AI: when an agent confirms a malicious IP, it can report it back to AbuseIPDB.

---

## Rate Limits

| Tier | `/check` requests/day | `/report` requests/day |
|---|---|---|
| Free | 1,000 | 1,000 |
| Basic ($20/mo) | 3,000 | 3,000 |
| Premium ($40/mo) | 10,000 | 10,000 |
| Business ($80/mo) | 30,000 | 30,000 |

Rate limit response: `429 Too Many Requests`
Response body: `{ "errors": [{ "detail": "...", "status": 429 }] }`

Calseta AI uses cache TTL (default: 3600 seconds) to avoid re-fetching recently enriched IPs.

---

## Known Quirks / Edge Cases

- **AbuseIPDB only enriches IPv4 and IPv6 — not domains or hashes**: Only wire the AbuseIPDB provider for `indicator_type = ip`. Domain, hash, URL, email go to other providers.
- **Private IPs return `isPublic: false` with score 0**: RFC1918 addresses (`10.x`, `192.168.x`, `172.16-31.x`) should be skipped before calling the API. Return `success=True, malice=Benign` without an API call.
- **`lastReportedAt` can be null**: If an IP has never been reported, this field is `null` (not omitted). Handle both cases.
- **`totalReports` is window-bound**: This is reports within the `maxAgeInDays` window, not all-time. A score of 0 with `maxAgeInDays=90` doesn't mean the IP was never reported — it means no reports in the last 90 days.
- **`isTor` requires a data subscription**: May not be available on all API tiers. Handle missing field gracefully (default to `false`).
- **IPv6 addresses**: Pass in standard notation; AbuseIPDB normalizes. Compressed notation (`::1`) is accepted.
- **`abuseConfidenceScore` is probabilistic**: The score is calculated from report frequency and reporter credibility weighting — not a simple report count ratio. A score of 100 means many credible reporters recently flagged this IP.
- **Error format for invalid IP**: `422` with body `{ "errors": [{ "detail": "The ip address must be a valid IP address.", "status": 422, "source": { "parameter": "ipAddress" } }] }`. This is not a network failure — handle it as a validation error, not a retry case.
