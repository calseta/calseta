# VirusTotal API Notes

Source: VirusTotal API v3
Reference: https://docs.virustotal.com/reference/overview

---

## Authentication

API key passed as HTTP header on every request:
```
x-apikey: {VIRUSTOTAL_API_KEY}
```

No OAuth, no token exchange. The key is a 64-character hex string.

Free tier keys work but have severe rate limits. Standard/Premium keys required for production.

---

## Key Endpoints Used by Calseta

### IP address report
```
GET https://www.virustotal.com/api/v3/ip_addresses/{ip}
x-apikey: {key}
```

### Domain report
```
GET https://www.virustotal.com/api/v3/domains/{domain}
x-apikey: {key}
```

### File hash report (MD5, SHA1, or SHA256)
```
GET https://www.virustotal.com/api/v3/files/{hash}
x-apikey: {key}
```
Any hash type accepted; VirusTotal normalizes internally.

All three endpoints return `200 OK` with the object, or `404 Not Found` if not in VT database.

---

## Request/Response Field Reference

### Common response envelope

All three endpoints return the same top-level structure:
```json
{
  "data": {
    "id": "{ip|domain|hash}",
    "type": "ip_address|domain|file",
    "links": { "self": "https://www.virustotal.com/api/v3/..." },
    "attributes": { ... }
  }
}
```

All enrichment data lives inside `data.attributes`.

---

### IP Address (`data.attributes`)

| Field path | Type | Notes |
|---|---|---|
| `last_analysis_stats` | object | **Primary malice signal** — see sub-fields below |
| `last_analysis_stats.malicious` | integer | Count of AV engines flagging as malicious |
| `last_analysis_stats.suspicious` | integer | Count flagging as suspicious |
| `last_analysis_stats.harmless` | integer | Count flagging as harmless/clean |
| `last_analysis_stats.undetected` | integer | Count with no detection (not the same as clean) |
| `last_analysis_stats.timeout` | integer | Count that timed out |
| `reputation` | integer | VT community reputation score (negative = bad, -100 to +100) |
| `country` | string | 2-letter country code e.g. `"US"`, `"RU"` |
| `continent` | string | Continent code |
| `as_owner` | string | Autonomous System owner name e.g. `"Google LLC"` |
| `asn` | integer | AS number |
| `network` | string | CIDR block e.g. `"8.8.8.0/24"` |
| `regional_internet_registry` | string | `"ARIN"`, `"RIPE NCC"`, etc. |
| `tags` | string[] | VT-applied tags e.g. `["cdn"]` |
| `categories` | object | `{ provider_name: category_string }` e.g. `{ "Forcepoint ThreatSeeker": "malicious sites" }` |
| `last_analysis_results` | object | Per-engine results: `{ engine_name: { category, result, method, engine_version } }` |
| `last_modification_date` | integer | Unix timestamp of last VT scan |
| `last_https_certificate` | object | TLS cert info (issuer, subject, validity dates) |
| `whois` | string | Raw WHOIS data |
| `whois_date` | integer | Unix timestamp of WHOIS data |
| `total_votes` | object | `{ harmless: int, malicious: int }` — community votes |

---

### Domain (`data.attributes`)

| Field path | Type | Notes |
|---|---|---|
| `last_analysis_stats` | object | Same structure as IP (malicious, suspicious, harmless, undetected, timeout) |
| `reputation` | integer | Community reputation score |
| `categories` | object | `{ provider_name: category_string }` |
| `tags` | string[] | VT-applied tags |
| `registrar` | string | Domain registrar name |
| `creation_date` | integer | Unix timestamp of domain creation |
| `expiration_date` | integer | Unix timestamp of domain expiration |
| `last_dns_records` | array | DNS records: `[{ type, ttl, value }]` — e.g. `{ type: "A", value: "1.2.3.4" }` |
| `last_dns_records_date` | integer | Unix timestamp of last DNS record fetch |
| `whois` | string | Raw WHOIS data |
| `whois_date` | integer | Unix timestamp of WHOIS data |
| `last_analysis_results` | object | Per-engine results (same structure as IP) |
| `last_modification_date` | integer | Unix timestamp |
| `total_votes` | object | `{ harmless: int, malicious: int }` |
| `popularity_ranks` | object | `{ provider: { rank: int, timestamp: int } }` e.g. Alexa, Cisco Umbrella |

---

### File Hash (`data.attributes`)

| Field path | Type | Notes |
|---|---|---|
| `last_analysis_stats` | object | Same structure (malicious, suspicious, harmless, undetected, timeout, confirmed-timeout, failure, type-unsupported) |
| `reputation` | integer | Community reputation score |
| `names` | string[] | Known filenames this hash has been seen as |
| `type_description` | string | File type e.g. `"Win32 EXE"`, `"PDF"` |
| `type_tag` | string | Short type tag e.g. `"peexe"`, `"pdf"` |
| `magic` | string | `file` command output |
| `size` | integer | File size in bytes |
| `md5` | string | MD5 hash |
| `sha1` | string | SHA1 hash |
| `sha256` | string | SHA256 hash |
| `ssdeep` | string | Fuzzy hash |
| `tlsh` | string | TLSH fuzzy hash |
| `creation_date` | integer | Unix timestamp of PE compilation time (for PE files) |
| `first_submission_date` | integer | Unix timestamp of first VT submission |
| `last_submission_date` | integer | Unix timestamp of most recent submission |
| `last_analysis_date` | integer | Unix timestamp of last scan |
| `times_submitted` | integer | Total submission count |
| `unique_sources` | integer | Distinct submitters |
| `tags` | string[] | VT-applied tags e.g. `["peexe", "signed"]` |
| `total_votes` | object | `{ harmless: int, malicious: int }` |
| `signature_info` | object | Code signing info: `{ subject, issuer, valid usage, ... }` |
| `sandbox_verdicts` | object | `{ sandbox_name: { category, malware_names: [] } }` |

---

### Enrichment field extraction paths (Calseta `enrichment_field_extractions` seeding)

These are the dot-notation paths in `data.attributes` that Calseta extracts by default:

| `target_key` | `source_path` | Applies to |
|---|---|---|
| `malicious_count` | `last_analysis_stats.malicious` | IP, domain, file |
| `suspicious_count` | `last_analysis_stats.suspicious` | IP, domain, file |
| `harmless_count` | `last_analysis_stats.harmless` | IP, domain, file |
| `undetected_count` | `last_analysis_stats.undetected` | IP, domain, file |
| `reputation` | `reputation` | IP, domain, file |
| `country` | `country` | IP |
| `as_owner` | `as_owner` | IP |
| `asn` | `asn` | IP |
| `network` | `network` | IP |
| `categories` | `categories` | IP, domain |
| `registrar` | `registrar` | domain |
| `creation_date` | `creation_date` | domain, file |
| `type_description` | `type_description` | file |
| `sha256` | `sha256` | file |
| `names` | `names` | file |

---

## Available Automation Endpoints (for pre-built workflows)

VirusTotal API v3 is read-only for enrichment. Write operations available on Enterprise:

### Submit URL for scanning (Enterprise)
```
POST https://www.virustotal.com/api/v3/urls
{ "url": "https://example.com/malware.exe" }
```

### Submit file for scanning (not typical for Calseta)
```
POST https://www.virustotal.com/api/v3/files
Content-Type: multipart/form-data
file={binary}
```

For Calseta v1, VirusTotal is read-only enrichment only. No write workflow actions needed.

---

## Rate Limits

| Tier | Requests/minute | Requests/day |
|---|---|---|
| Free (Public API) | 4 | 500 |
| Premium / Standard | 1000+ | varies by plan |
| Enterprise | custom | custom |

Rate limit response: `429 Too Many Requests`
Headers on 429: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (Unix timestamp)

**Important**: The free tier is completely insufficient for production. Require `VIRUSTOTAL_API_KEY` with at least Standard tier.

Calseta respects rate limits via:
1. Cache TTL on `EnrichmentProviderBase` — default 3600 seconds for VT
2. Respect `Retry-After` or `X-RateLimit-Reset` header on 429

---

## Known Quirks / Edge Cases

- **`last_analysis_stats.malicious = 0` does not mean clean**: An IP/domain/hash not flagged by any engine could still be malicious but new/unknown. Check `undetected` count alongside `malicious`.
- **`reputation` is community-sourced and volatile**: Scores change based on VT community votes. A score of -1 with 0 malicious engine detections is not reliable. Use `last_analysis_stats` as the primary signal.
- **Timestamps are Unix integers, not ISO 8601**: All `_date` fields in attributes are Unix epoch seconds. Convert before storing.
- **`last_analysis_results` can be very large**: Contains one entry per AV engine (70+ engines). Do not store the full object in `enrichment_results.extracted` — store only `last_analysis_stats` and other extracted fields. Store the full response in `enrichment_results.raw`.
- **Hash lookup is case-insensitive**: VT accepts MD5, SHA1, SHA256 in any case. Normalize to lowercase before lookup.
- **Private IPs return 404**: `10.x.x.x`, `192.168.x.x`, `172.16-31.x.x` are not in VT database. Handle 404 as `success=True, malice=Benign` or skip enrichment for RFC1918 ranges.
- **Domain format**: Submit the bare domain, not a URL. `evil.com` not `https://evil.com`. Strip scheme and path before lookup.
- **`categories` object keys are vendor names**: Keys vary by VT plan (different vendors licensed per plan). Do not hardcode vendor names — iterate all keys.
