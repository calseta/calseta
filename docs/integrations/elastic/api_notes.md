# Elastic Security API Notes

Source: Elastic Security / Kibana Detection Engine API, ECS (Elastic Common Schema) 8.x
References:
- https://www.elastic.co/guide/en/kibana/current/detection-engine-api.html
- https://www.elastic.co/guide/en/ecs/current/ecs-reference.html

---

## Authentication

Two authentication methods supported:

**API Key (preferred for production):**
```
Authorization: ApiKey {base64(id:api_key)}
```
Create via Kibana UI: Stack Management > API Keys, or via API:
```
POST /_security/api_key
{ "name": "calseta-ingest", "role_descriptors": { "calseta_reader": { "cluster": ["monitor"], "index": [{ "names": [".alerts-security.alerts-*"], "privileges": ["read"] }] } } }
```

**Basic Auth (development):**
```
Authorization: Basic {base64(username:password)}
```

Webhook signature: Elastic Kibana connector actions support a `secret` header value that Calseta AI verifies.

---

## Key Endpoints Used by Calseta AI

### Find alerts (paginated POST)
```
POST {kibana_url}/api/detection_engine/signals/search
kbn-xsrf: true
Authorization: ApiKey {key}
Content-Type: application/json

{
  "query": { "bool": { "filter": [{ "term": { "kibana.alert.workflow_status": "open" } }] } },
  "size": 50,
  "from": 0,
  "sort": [{ "kibana.alert.start": { "order": "desc" } }],
  "_source": true
}
```

Pagination uses `from` (offset) + `size` (page size, max 10000). For deep pagination use `search_after` with a sort cursor.

### Get alert by ID
```
GET {kibana_url}/api/detection_engine/signals?id={signal_id}
```

### Update alert status
```
POST {kibana_url}/api/detection_engine/signals/status
{ "signal_ids": ["{id}"], "status": "closed" }
```

---

## Request/Response Field Reference

### Alert document structure

Each alert is a flat JSON document with two categories of fields that coexist at the same level in `_source`:

**1. Kibana alert metadata fields** (prefixed `kibana.alert.*`)

| Field | Type | Notes |
|---|---|---|
| `kibana.alert.uuid` | string (UUID) | Calseta alert UUID source — use as `raw_payload` reference |
| `kibana.alert.rule.uuid` | string (UUID) | Detection rule UUID — maps to Calseta `detection_rule_ref` |
| `kibana.alert.rule.name` | string | Rule name — maps to Calseta `title` |
| `kibana.alert.rule.description` | string | Rule description |
| `kibana.alert.rule.type` | string | `query`, `threshold`, `machine_learning`, `eql`, `new_terms` |
| `kibana.alert.rule.severity` | string | **`critical`, `high`, `medium`, `low`** — maps to Calseta severity |
| `kibana.alert.rule.risk_score` | integer | 0–100 risk score |
| `kibana.alert.rule.tags` | string[] | Rule tags — maps to Calseta `tags` |
| `kibana.alert.rule.threat` | array | MITRE ATT&CK: `[{ tactic: {id, name}, technique: [{id, name}] }]` |
| `kibana.alert.severity` | string | Alert-level severity override (same enum as rule severity) |
| `kibana.alert.risk_score` | float | Alert-level risk score |
| `kibana.alert.start` | string (ISO 8601) | Alert start time — maps to Calseta `occurred_at` |
| `kibana.alert.end` | string (ISO 8601) | Alert end time |
| `kibana.alert.workflow_status` | string | `open`, `acknowledged`, `closed` |
| `kibana.alert.status` | string | Active/recovered state |
| `kibana.alert.reason` | string | Human-readable alert reason message |
| `kibana.alert.original_event` | object | Original event metadata (action, category, kind) |
| `kibana.alert.building_block_type` | string | Present only for building block alerts |
| `kibana.alert.threshold_result` | object | Present only for threshold rules |
| `kibana.alert.new_terms` | object | Present only for new_terms rules |

**2. ECS (Elastic Common Schema) event fields** — same level as `kibana.alert.*`

These are the raw event fields from the underlying security event that triggered the alert:

| ECS Field | Type | Notes |
|---|---|---|
| `@timestamp` | string (ISO 8601) | Event timestamp |
| `event.id` | string | Unique event ID |
| `event.action` | string | e.g. `process_started`, `network_connection` |
| `event.category` | string[] | e.g. `["network"]`, `["process"]`, `["authentication"]` |
| `event.kind` | string | `signal` (always for alerts) |
| `event.dataset` | string | e.g. `endpoint.events.process` |
| `event.module` | string | e.g. `endpoint`, `winlogbeat`, `auditd` |
| `event.severity` | integer | Source event severity (not the rule severity) |
| `event.outcome` | string | `success`, `failure`, `unknown` |
| `host.id` | string | Unique host ID |
| `host.name` | string | Hostname — maps to Calseta indicator extraction |
| `host.hostname` | string | FQDN |
| `host.ip` | string[] | Host IP addresses — maps to Calseta indicator extraction |
| `host.os.name` | string | OS name |
| `host.os.platform` | string | e.g. `windows`, `linux`, `macos` |
| `source.ip` | string | Source IP — maps to Calseta indicator extraction |
| `source.port` | integer | Source port |
| `destination.ip` | string | Destination IP — maps to Calseta indicator extraction |
| `destination.port` | integer | Destination port |
| `destination.domain` | string | Destination domain — maps to Calseta indicator extraction |
| `user.name` | string | Username — maps to Calseta indicator extraction |
| `user.domain` | string | User domain |
| `user.email` | string | User email |
| `user.id` | string | User ID |
| `process.name` | string | Process name |
| `process.pid` | integer | Process ID |
| `process.executable` | string | Full path |
| `process.hash.md5` | string | MD5 hash — maps to Calseta indicator extraction |
| `process.hash.sha1` | string | SHA1 hash |
| `process.hash.sha256` | string | SHA256 hash — maps to Calseta indicator extraction |
| `file.name` | string | File name |
| `file.path` | string | File path |
| `file.hash.md5` | string | File MD5 |
| `file.hash.sha256` | string | File SHA256 |
| `network.direction` | string | `inbound`, `outbound`, `internal`, `external`, `unknown` |
| `network.protocol` | string | e.g. `tcp`, `udp`, `dns` |
| `url.full` | string | Full URL — maps to Calseta indicator extraction |
| `url.domain` | string | URL domain |
| `dns.question.name` | string | DNS query name — maps to Calseta domain indicator |
| `threat.indicator.ip` | string | Threat intel IP indicator |
| `threat.indicator.domain` | string | Threat intel domain indicator |
| `threat.indicator.file.hash.sha256` | string | Threat intel hash indicator |

### `_source` nesting pattern

The key insight: **all fields are at the document root level in `_source`**. There is no `_source.kibana` nested object — the `.` in field names is an Elasticsearch convention for dot-notation field names, not actual JSON nesting. When deserializing the `_source` key from the Elasticsearch API response, use bracket notation or a dot-path resolver.

Example raw API hit structure:
```json
{
  "_index": ".alerts-security.alerts-default-000001",
  "_id": "uuid-of-alert",
  "_score": null,
  "_source": {
    "@timestamp": "2024-01-15T10:30:00.000Z",
    "kibana.alert.uuid": "abc123",
    "kibana.alert.rule.name": "Suspicious PowerShell Execution",
    "kibana.alert.rule.uuid": "rule-uuid",
    "kibana.alert.rule.severity": "high",
    "kibana.alert.start": "2024-01-15T10:29:50.000Z",
    "kibana.alert.workflow_status": "open",
    "kibana.alert.reason": "powershell.exe executed with suspicious arguments",
    "event.category": ["process"],
    "event.action": "start",
    "host.name": "WORKSTATION-01",
    "host.ip": ["192.168.1.100"],
    "user.name": "jdoe",
    "process.name": "powershell.exe",
    "process.command_line": "powershell -enc SQBFAB...",
    "process.hash.sha256": "abc123def456...",
    "agent.id": "agent-uuid"
  }
}
```

### Severity mapping to Calseta

| Elastic severity | Calseta `severity` | Calseta `severity_id` |
|---|---|---|
| `critical` | `Critical` | 5 |
| `high` | `High` | 4 |
| `medium` | `Medium` | 3 |
| `low` | `Low` | 2 |

---

## Available Automation Endpoints (for pre-built workflows)

### Update alert status
```
POST {kibana_url}/api/detection_engine/signals/status
kbn-xsrf: true

{ "signal_ids": ["alert-uuid"], "status": "closed" }
```
Status values: `open`, `acknowledged`, `closed`

### Add note/comment to alert (via Cases)
```
POST {kibana_url}/api/cases/{case_id}/comments
{ "comment": "Agent investigation: confirmed malicious", "type": "user", "owner": "securitySolution" }
```

### Isolate endpoint (requires Elastic Defend)
```
POST {kibana_url}/api/endpoint/action/isolate
{ "endpoint_ids": ["{agent.id}"], "comment": "Isolated by Calseta AI agent" }
```

---

## Rate Limits

Kibana does not publish specific per-minute rate limits in official docs. Observed behavior:
- No documented hard rate limit per endpoint
- Elasticsearch underlying search: limited by cluster resources, not a fixed API rate
- Recommend: max 100 requests/minute per API key, implement exponential backoff on 429/503
- `429 Too Many Requests` response includes `Retry-After` header when returned

---

## Known Quirks / Edge Cases

- **Dot-notation vs nested JSON**: `kibana.alert.rule.name` in `_source` is a flat string key with dots, NOT a nested JSON path `{ kibana: { alert: { rule: { name: ... } } } }`. Some Elasticsearch client libraries auto-convert; verify your deserialization behavior.
- **Alert deduplication**: Elastic may generate duplicate alert documents for the same rule firing on the same event. Use `kibana.alert.uuid` as the dedup key.
- **Building block alerts**: `kibana.alert.building_block_type = "default"` means this alert is a sub-component of a compound detection. Do not surface directly to agents — they are intermediate signals.
- **`_source` availability**: If using Elasticsearch directly (not Kibana API), alerts live in `.alerts-security.alerts-{space_id}-{ds_number}` indices. The Kibana API normalizes the index pattern.
- **`kibana.alert.start` vs `@timestamp`**: `@timestamp` is the indexing time (when Kibana wrote the alert). `kibana.alert.start` is when the underlying event occurred. Use `kibana.alert.start` for Calseta `occurred_at`.
- **ECS arrays**: Fields like `host.ip`, `event.category` are always arrays, even if single-valued. `source.ip`, `destination.ip` are usually strings.
- **ML alert fields**: Machine learning rule alerts include `kibana.alert.ml.is_interim`, `kibana.alert.ml.anomaly_score`, `kibana.alert.ml.anomaly_count` — relevant for severity mapping.
- **Rule type affects available fields**: EQL rules populate `kibana.alert.group.id` (correlation group). Threshold rules populate `kibana.alert.threshold_result.count`.
