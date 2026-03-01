# Microsoft Sentinel API Notes

Source: Microsoft Security Insights REST API 2025-09-01
Reference: https://learn.microsoft.com/en-us/rest/api/securityinsights/incidents

---

## Authentication

Sentinel uses Azure Active Directory OAuth2. Calseta AI uses the **client credentials flow** (application permissions, no user login):

```
POST https://login.microsoftonline.com/{tenantId}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

client_id={ENTRA_CLIENT_ID}
&client_secret={ENTRA_CLIENT_SECRET}
&scope=https://management.azure.com/.default
&grant_type=client_credentials
```

Response: `{ "access_token": "eyJ...", "expires_in": 3599 }`

All subsequent requests send: `Authorization: Bearer {access_token}`

Required Azure role for the service principal: **Microsoft Sentinel Reader** (read incidents) or **Microsoft Sentinel Responder** (read + update incidents).

**Webhook ingest path**: Sentinel also pushes alerts to external URLs via Logic Apps automation rules. Calseta AI receives these pushes — the payload schema is the same incident object.

---

## Key Endpoints Used by Calseta AI

### Get a single incident
```
GET https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.OperationalInsights/workspaces/{workspaceName}/providers/Microsoft.SecurityInsights/incidents/{incidentId}?api-version=2025-09-01
```

### List incidents (paginated)
```
GET https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.OperationalInsights/workspaces/{workspaceName}/providers/Microsoft.SecurityInsights/incidents?api-version=2025-09-01&$filter=...&$orderby=properties/createdTimeUtc desc&$top=50&$skipToken=...
```

Pagination uses `$top` (max 1000) + `$skipToken` cursor. Response includes `nextLink` when more pages exist.

---

## Request/Response Field Reference

### Incident object (top-level)

| Field | Type | Notes |
|---|---|---|
| `id` | string (ARM resource ID) | Internal ARM path — not for external use |
| `name` | string (UUID) | The incident UUID — use this as `raw_payload` reference ID |
| `type` | string | Always `"Microsoft.SecurityInsights/incidents"` |
| `etag` | string | Concurrency control |
| `properties.title` | string | Human-readable incident name — maps to Calseta `title` |
| `properties.description` | string | Narrative description |
| `properties.severity` | string (enum) | **`High`, `Medium`, `Low`, `Informational`** — maps to Calseta severity |
| `properties.status` | string (enum) | `New`, `Active`, `Closed` |
| `properties.createdTimeUtc` | string (ISO 8601) | When incident was created in Sentinel |
| `properties.firstActivityTimeUtc` | string (ISO 8601) | Earliest event time — maps to Calseta `occurred_at` |
| `properties.lastActivityTimeUtc` | string (ISO 8601) | Latest event time |
| `properties.lastModifiedTimeUtc` | string (ISO 8601) | Last update time |
| `properties.incidentNumber` | integer | Sequential counter per workspace |
| `properties.incidentUrl` | string (URL) | Direct link to incident in Azure portal |
| `properties.providerName` | string | Source provider e.g. `"Azure Sentinel"` |
| `properties.providerIncidentId` | string | Provider-assigned ID |
| `properties.relatedAnalyticRuleIds` | string[] | ARM IDs of the analytic rules that triggered this incident — maps to Calseta `detection_rule_ref` |
| `properties.classification` | string (enum) | `Undetermined`, `TruePositive`, `BenignPositive`, `FalsePositive` |
| `properties.classificationComment` | string | Free text reason for closure |
| `properties.classificationReason` | string (enum) | `SuspiciousActivity`, `SuspiciousButExpected`, `IncorrectAlertLogic`, `InaccurateData` |
| `properties.labels` | array | `[{ "labelName": string, "labelType": "User"\|"AutoAssigned" }]` — maps to Calseta `tags` |
| `properties.owner` | object | `{ objectId, email, userPrincipalName, assignedTo, ownerType }` |
| `properties.additionalData` | object | See below |

### `properties.additionalData` sub-object

| Field | Type | Notes |
|---|---|---|
| `alertsCount` | integer | Number of alerts grouped in this incident |
| `bookmarksCount` | integer | Hunting bookmarks attached |
| `commentsCount` | integer | Comments on the incident |
| `alertProductNames` | string[] | Source product names e.g. `["Microsoft Defender for Endpoint"]` |
| `tactics` | string[] | MITRE ATT&CK tactics — maps to Calseta detection rule tactic fields |

### Severity mapping to Calseta

| Sentinel severity | Calseta `severity` | Calseta `severity_id` |
|---|---|---|
| `High` | `High` | 4 |
| `Medium` | `Medium` | 3 |
| `Low` | `Low` | 2 |
| `Informational` | `Informational` | 1 |

### Alert trigger (Logic Apps / webhook payload)

When Sentinel fires a Logic Apps automation rule, the incident trigger provides these dynamic fields:
- All `properties.*` fields from the incident object above
- `Alerts` — array of alert objects with fields: `Alert: Severity`, `Alert: Start Time`, `Alert: End Time`, `Alert: Name`, `Alert: Description`, `Alert: Tactics`, `Alert: Entities`
- `Entities` — array of entity objects (IP, Account, Host, URL, FileHash)
- Workspace metadata: `Subscription ID`, `Workspace name`, `Workspace ID`, `Resource group name`

When Calseta AI receives the webhook body, it is the full serialized incident JSON object identical to the REST API GET response.

---

## Available Automation Endpoints (for pre-built workflows)

These endpoints enable agent-driven remediation actions on incidents. All require `Microsoft Sentinel Responder` role.

### Update incident status / close incident
```
PUT https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.OperationalInsights/workspaces/{ws}/providers/Microsoft.SecurityInsights/incidents/{incidentId}?api-version=2025-09-01
Content-Type: application/json

{
  "properties": {
    "status": "Closed",
    "classification": "TruePositive",
    "classificationReason": "SuspiciousActivity",
    "classificationComment": "Confirmed malicious activity"
  }
}
```

### Add comment to incident
```
POST https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.OperationalInsights/workspaces/{ws}/providers/Microsoft.SecurityInsights/incidents/{incidentId}/comments/{commentId}?api-version=2025-09-01
Content-Type: application/json

{ "properties": { "message": "Agent investigation complete. IOCs blocked." } }
```

### List incident entities (for IOC extraction)
```
POST https://management.azure.com/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.OperationalInsights/workspaces/{ws}/providers/Microsoft.SecurityInsights/incidents/{incidentId}/entities?api-version=2025-09-01
```
Returns entities with types: `ip`, `account`, `host`, `url`, `filehash`, `malware`, `process`, `registrykey`.

---

## Rate Limits

Sentinel REST API is governed by Azure Resource Manager (ARM) throttling:
- **Read requests**: 12,000 per hour per subscription
- **Write requests**: 1,200 per hour per subscription
- Throttling response: `429 Too Many Requests` with `Retry-After` header
- Workspace-level operations (incidents, entities) count against subscription quota

---

## Known Quirks / Edge Cases

- **`firstActivityTimeUtc` vs `createdTimeUtc`**: Use `firstActivityTimeUtc` as `occurred_at` (when the attack happened). `createdTimeUtc` is when Sentinel created the incident (detection lag).
- **`relatedAnalyticRuleIds` is an ARM ID array**: To get the rule name, strip the ARM path suffix — or call the Analytic Rules GET endpoint. Only the last UUID segment is needed for Calseta's `detection_rule_ref`.
- **Alert vs Incident**: Sentinel groups multiple alerts into an incident. Calseta AI ingests at the incident level. Individual alert payloads are available via Logic Apps `Alert` trigger but have a different (less complete) schema.
- **Severity `None`**: Rare — seen when rules don't set severity explicitly. Treat as `Informational` (severity_id=1).
- **Closed incidents come via webhook too**: Automation rules fire on `IncidentCreated` and `IncidentUpdated`. Filter by `properties.status != "Closed"` on ingest, or model status mapping explicitly.
- **Entity types are not normalized**: A `Host` entity may have `hostName`, `dnsDomain`, `ntDomain` — not all populated. Extract what's present.
- **`$skipToken` is opaque**: Do not parse or cache it beyond the current pagination loop.
