# Splunk API Notes

Source: Splunk Enterprise / Splunk Cloud alert webhook documentation
References:
- https://docs.splunk.com/Documentation/Splunk/latest/Alert/Webhooks
- https://docs.splunk.com/Documentation/Splunk/latest/RESTREF/RESTsearch

---

## Authentication

### Webhook ingest (Calseta receiving alerts from Splunk)

Splunk sends webhooks via HTTP POST. Authentication options:

**Custom header token (recommended):**
Configure in the alert action. Splunk lets you add arbitrary HTTP headers to the webhook — use a shared secret in a custom header (`X-Splunk-Webhook-Secret: {secret}`). Calseta verifies this via `verify_webhook_signature()`.

**No built-in HMAC signing**: Unlike Sentinel or Elastic, native Splunk webhook action does not generate HMAC signatures. The recommended approach is:
1. Use a secret token in a custom header
2. Restrict webhook endpoint to Splunk's outbound IP range at the network level

### Splunk REST API (polling, if used)
```
Authorization: Bearer {splunk_token}
```
Create token: Splunk Web > Settings > Tokens > New Token, or via API:
```
POST https://{splunk_host}:8089/services/authorization/tokens
name=calseta&audience=calseta-ingest&expires_on=+30d
```
Alternatively, Basic Auth: `Authorization: Basic {base64(username:password)}`

---

## Key Endpoints Used by Calseta

### Receive webhook (Splunk pushes to Calseta)
Splunk calls `POST {calseta_url}/v1/alerts/ingest/splunk` with the payload below.

### Search for recent alerts (Splunk REST API — optional polling)
```
POST https://{splunk_host}:8089/services/search/jobs
output_mode=json
search=search index=notable | head 50
```
Then poll the job status and retrieve results.

---

## Request/Response Field Reference

### Webhook payload structure

Splunk sends a fixed JSON envelope when an alert fires:

```json
{
  "result": {
    "_bkt": "notable~1~ABCDEF1234567890",
    "_cd": "1:12345",
    "_indextime": "1705312200",
    "_raw": "<raw log event text>",
    "_serial": "0",
    "_si": ["splunk-indexer", "notable"],
    "_sourcetype": "stash",
    "_time": "1705312200",
    "dest": "192.168.1.50",
    "src": "10.0.0.1",
    "src_ip": "10.0.0.1",
    "dest_ip": "192.168.1.50",
    "user": "jdoe",
    "signature": "Brute Force Attack Detected",
    "rule_name": "Brute Force Attack Detected",
    "rule_description": "Multiple failed login attempts from a single source",
    "urgency": "high",
    "priority": "medium",
    "severity": "high",
    "drilldown_search": "index=notable ...",
    "event_id": "1705312200.12345"
  },
  "sid": "scheduler__admin__search_ZnVuY3Rpb24tYnJ1dGVmb3Jj_at_1705312200_1",
  "results_link": "https://splunk.corp.com/app/SplunkEnterpriseSecuritySuite/incidents",
  "search_name": "Brute Force Attack Detected",
  "owner": "admin",
  "app": "SplunkEnterpriseSecuritySuite",
  "server_host": "splunk-sh.corp.com",
  "server_uri": "https://splunk-sh.corp.com:8089"
}
```

### Field reference

**Envelope fields (top-level)**

| Field | Type | Notes |
|---|---|---|
| `result` | object | The alert result row — primary payload |
| `sid` | string | Search ID that generated the alert |
| `search_name` | string | Name of the saved search / alert — maps to Calseta `title` |
| `results_link` | string | URL to view results in Splunk Web |
| `owner` | string | Splunk user who owns the alert |
| `app` | string | Splunk app context (e.g. `SplunkEnterpriseSecuritySuite`) |
| `server_host` | string | Splunk search head hostname |
| `server_uri` | string | Splunk REST API base URL |

**`result` fields — Splunk ES notable events (most common)**

When using Splunk Enterprise Security, notable events (correlation search results) include:

| Field | Type | Notes |
|---|---|---|
| `event_id` | string | Unique notable event ID — use as `raw_payload` reference |
| `rule_name` | string | Correlation rule name — maps to Calseta `detection_rule_ref` |
| `rule_description` | string | Rule description |
| `urgency` | string | **`critical`, `high`, `medium`, `low`, `informational`** — primary severity signal |
| `priority` | string | Priority of the correlation rule |
| `severity` | string | Severity assigned to notable event (may differ from urgency) |
| `status` | string | `New`, `In Progress`, `Pending`, `Resolved`, `Closed` |
| `src` | string | Source (IP or hostname) |
| `src_ip` | string | Source IP — maps to Calseta indicator extraction |
| `dest` | string | Destination (IP or hostname) |
| `dest_ip` | string | Destination IP — maps to Calseta indicator extraction |
| `user` | string | Associated user — maps to Calseta indicator extraction |
| `signature` | string | Alert/event description |
| `drilldown_search` | string | SPL search to reproduce the alert |
| `_raw` | string | Raw log line that triggered the alert |
| `_time` | string | Unix timestamp (seconds) — maps to Calseta `occurred_at` |
| `_indextime` | string | Unix timestamp when event was indexed |
| `_sourcetype` | string | Sourcetype of the raw event |
| `mitre_attack_id` | string | MITRE technique ID if tagged by the rule |
| `kill_chain_phase` | string | Cyber kill chain phase |

**Non-ES (standard saved search webhook) result fields**

When using a standard Splunk saved search (not ES), `result` contains whatever columns the SPL search returns. Field names are exactly the column names from the SPL query. There is no standard schema — they are arbitrary. Calseta extracts what it can via the indicator_field_mappings Pass 3 configuration.

Common standard field names: `src_ip`, `dest_ip`, `user`, `action`, `bytes`, `url`, `file_path`, `hash`, `process_name`.

### Severity / urgency mapping to Calseta

| Splunk `urgency` | Calseta `severity` | Calseta `severity_id` |
|---|---|---|
| `critical` | `Critical` | 5 |
| `high` | `High` | 4 |
| `medium` | `Medium` | 3 |
| `low` | `Low` | 2 |
| `informational` | `Informational` | 1 |

Use `urgency` field when present (ES); fall back to `severity`; fall back to `Pending` if neither.

---

## Available Automation Endpoints (for pre-built workflows)

### Update notable event status (Splunk ES)
```
POST https://{splunk_host}:8089/services/notable_update
Authorization: Bearer {token}
output_mode=json

ruleUIDs={event_id}&status={status}&urgency={urgency}&comment={comment}&newOwner={owner}
```
Status values: `0` = Unassigned, `1` = New, `2` = In Progress, `3` = Pending, `4` = Resolved, `5` = Closed

### Run an ad-hoc SPL search (blocking, short timeouts only)
```
POST https://{splunk_host}:8089/services/search/jobs/export
Authorization: Bearer {token}
output_mode=json&search=search index=notable event_id={event_id}&earliest_time=-1h
```

### Add comment to notable event
Included in the `notable_update` POST above via the `comment` parameter.

---

## Rate Limits

Splunk does not publish specific REST API rate limits. Practical limits:
- Search concurrency: limited by `max_searches_per_process` (default varies by tier, typically 10–50)
- 429 responses are rare; resource exhaustion manifests as slow response times instead
- Splunk Cloud: REST API access may be IP-restricted; requires allow-listing Calseta's egress IP
- For webhook ingest: Splunk fires one HTTP request per alert trigger event, no batching

---

## Known Quirks / Edge Cases

- **`_time` is a Unix timestamp string**: Convert `float(result["_time"])` to datetime before storing as `occurred_at`. Not ISO 8601.
- **Non-ES result field names are arbitrary**: Standard saved search webhooks return SPL column names. Calseta must handle arbitrary field names via Pass 3 indicator_field_mappings, not hardcoded logic.
- **`result` can contain nested fields as JSON strings**: Some Splunk sourcetypes JSON-encode sub-objects into a single string field. Parse defensively.
- **`search_name` vs `rule_name`**: In ES, `result.rule_name` is the correlation rule. For standard searches, only `search_name` (envelope level) is available. Always check both.
- **Notable event ID format**: `event_id` in ES notable events is `{_time}.{random_suffix}`. Do NOT use `sid` (the search job ID) as a dedup key — a single `sid` can produce many notable events.
- **Splunk ES vs standard Splunk**: The `app` field tells you. `SplunkEnterpriseSecuritySuite` = ES. `search` = standard.
- **No batch delivery**: Each alert fires one webhook call. High-volume environments may generate many simultaneous POST requests to Calseta — the ingest endpoint must handle concurrent writes.
- **Webhook retry**: Splunk retries failed webhook deliveries up to 3 times with exponential backoff. Calseta must be idempotent on ingest — dedup by `event_id`.
