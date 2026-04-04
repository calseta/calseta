# How to Write Workflows

## What Workflows Are

Workflows are **HTTP automation scripts** that call external APIs on behalf of your SOC. Python is the glue layer — you use it to construct HTTP requests, parse responses, and decide what to return. Every workflow is a single `async def run(ctx)` function that receives a context object and returns a result.

The execution model is simple: Calseta hands your function an indicator (and optionally an alert), an HTTP client, access to secrets, and structured logging. Your function calls an endpoint, checks the response, and returns success or failure.

```python
from app.workflows.context import WorkflowContext, WorkflowResult

async def run(ctx: WorkflowContext) -> WorkflowResult:
    api_key = ctx.secrets.get("MY_API_KEY")
    resp = await ctx.http.post("https://api.example.com/action", json={...}, headers={...})
    if resp.status_code == 200:
        return WorkflowResult.ok("Done")
    return WorkflowResult.fail(f"API returned {resp.status_code}")
```

## What You Can Do

- **Call any HTTP endpoint** — REST APIs, webhooks, Lambda Function URLs, Logic App triggers, serverless functions, internal services
- **Parse JSON responses** — extract IDs, status codes, error messages from API responses
- **Use environment variables for secrets** — API keys, tokens, webhook URLs via `ctx.secrets.get("KEY")`
- **Access indicator and alert data** — type, value, malice verdict, alert title, severity, source, tags
- **Use safe stdlib modules** — `json`, `hashlib`, `hmac`, `base64`, `datetime`, `re`, `uuid`, `urllib`, and more
- **Log structured events** — `ctx.log.info("event_name", key=value)` captured in the run audit log
- **Use builtin integration clients** — `ctx.integrations.okta` and `ctx.integrations.entra` for pre-built Okta/Entra actions

## What You Can't Do

- **Install packages** — no `pip install`, no third-party libraries
- **Access the filesystem** — `open()`, `pathlib`, `shutil` are blocked
- **Import dangerous modules** — `os`, `subprocess`, `sys`, `socket`, `pickle` are blocked
- **Run shell commands** — no `exec()`, `eval()`, `compile()`
- **Use threading or multiprocessing** — single async function only

These restrictions are enforced by AST validation at save time and a restricted builtins namespace at runtime.

## The Interface

### `WorkflowContext` — what your function receives

| Field | Type | Description |
|---|---|---|
| `ctx.indicator.type` | `str` | Indicator type: `ip`, `domain`, `hash_sha256`, `account`, etc. |
| `ctx.indicator.value` | `str` | The indicator value (e.g. `"203.0.113.42"`, `"jsmith@corp.com"`) |
| `ctx.indicator.malice` | `str` | Verdict: `Pending`, `Benign`, `Suspicious`, `Malicious` |
| `ctx.indicator.enrichment_results` | `dict \| None` | Enrichment data from all providers |
| `ctx.alert` | `AlertContext \| None` | Alert that triggered this workflow (None for standalone indicators) |
| `ctx.alert.title` | `str` | Alert title |
| `ctx.alert.severity` | `str` | `Informational`, `Low`, `Medium`, `High`, `Critical` |
| `ctx.alert.source_name` | `str` | Source integration (e.g. `"sentinel"`, `"elastic"`) |
| `ctx.alert.status` | `str` | `Open`, `Triaging`, `Escalated`, `Closed` |
| `ctx.alert.tags` | `list[str]` | Alert tags |
| `ctx.alert.raw_payload` | `dict` | Original source payload |
| `ctx.http` | `httpx.AsyncClient` | Pre-configured HTTP client (timeout matches workflow setting) |
| `ctx.log` | `WorkflowLogger` | Structured logger: `.info()`, `.warning()`, `.error()`, `.debug()` |
| `ctx.secrets` | `SecretsAccessor` | Read env vars: `.get("KEY")` returns `str \| None` |
| `ctx.integrations.okta` | `OktaClient \| None` | Okta lifecycle client (None if not configured) |
| `ctx.integrations.entra` | `EntraClient \| None` | Entra lifecycle client (None if not configured) |

### `WorkflowResult` — what your function returns

```python
WorkflowResult.ok("Success message", data={"key": "value"})   # success
WorkflowResult.fail("Error message", data={"details": "..."})  # failure
```

Your `run()` function must **never raise exceptions**. Catch all errors and return `WorkflowResult.fail()`.

### Allowed Imports

```python
import asyncio, base64, collections, copy, datetime, enum, functools
import hashlib, hmac, html, http, inspect, io, ipaddress, itertools
import json, logging, math, operator, re, statistics, string
import textwrap, time, typing, typing_extensions, unicodedata
import urllib, uuid
from app.workflows.context import WorkflowContext, WorkflowResult
```

## Patterns

These patterns cover the most common SOC automation use cases. Full source files are in `docs/workflows/examples/`.

### 1. Generic Webhook

POST indicator/alert context to any URL. Works with SOAR platforms, ticketing systems, or custom endpoints.

```python
async def run(ctx: WorkflowContext) -> WorkflowResult:
    webhook_url = ctx.secrets.get("WEBHOOK_URL")
    if not webhook_url:
        return WorkflowResult.fail("WEBHOOK_URL is not set")

    payload = {
        "indicator_type": ctx.indicator.type,
        "indicator_value": ctx.indicator.value,
        "malice": ctx.indicator.malice,
    }
    if ctx.alert:
        payload["alert"] = {"title": ctx.alert.title, "severity": ctx.alert.severity}

    resp = await ctx.http.post(webhook_url, json=payload)
    if resp.status_code >= 400:
        return WorkflowResult.fail(f"Webhook returned {resp.status_code}")
    return WorkflowResult.ok(f"Webhook delivered (HTTP {resp.status_code})")
```

See: [`docs/workflows/examples/generic_webhook.py`](workflows/examples/generic_webhook.py)

### 2. REST API with Bearer Token

Call a REST API (ServiceNow, Jira, PagerDuty) using an API key from environment variables.

```python
async def run(ctx: WorkflowContext) -> WorkflowResult:
    instance = ctx.secrets.get("SERVICENOW_INSTANCE")
    api_token = ctx.secrets.get("SERVICENOW_API_TOKEN")
    if not instance or not api_token:
        return WorkflowResult.fail("ServiceNow credentials not set")

    resp = await ctx.http.post(
        f"https://{instance}/api/now/table/incident",
        headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
        json={"short_description": f"SOC: {ctx.indicator.value}", "urgency": "2"},
    )
    if resp.status_code not in (200, 201):
        return WorkflowResult.fail(f"ServiceNow returned {resp.status_code}")

    number = resp.json().get("result", {}).get("number", "unknown")
    return WorkflowResult.ok(f"Incident created: {number}", data={"number": number})
```

See: [`docs/workflows/examples/rest_api_bearer_token.py`](workflows/examples/rest_api_bearer_token.py)

### 3. AWS Lambda Trigger

Invoke a Lambda via its Function URL or API Gateway endpoint. No AWS SDK needed.

```python
async def run(ctx: WorkflowContext) -> WorkflowResult:
    url = ctx.secrets.get("LAMBDA_FUNCTION_URL")
    if not url:
        return WorkflowResult.fail("LAMBDA_FUNCTION_URL is not set")

    event = {"indicator_type": ctx.indicator.type, "indicator_value": ctx.indicator.value}
    resp = await ctx.http.post(url, json=event)
    if resp.status_code >= 400:
        return WorkflowResult.fail(f"Lambda returned {resp.status_code}")
    return WorkflowResult.ok("Lambda invoked", data=resp.json())
```

See: [`docs/workflows/examples/aws_lambda_trigger.py`](workflows/examples/aws_lambda_trigger.py)

### 4. Azure Logic App Trigger

POST to a Logic App HTTP trigger URL. Same pattern as any webhook — Logic Apps expose an HTTPS endpoint.

```python
async def run(ctx: WorkflowContext) -> WorkflowResult:
    trigger_url = ctx.secrets.get("LOGIC_APP_TRIGGER_URL")
    if not trigger_url:
        return WorkflowResult.fail("LOGIC_APP_TRIGGER_URL is not set")

    payload = {
        "indicator": ctx.indicator.value,
        "type": ctx.indicator.type,
        "malice": ctx.indicator.malice,
    }
    if ctx.alert:
        payload["alert_title"] = ctx.alert.title

    resp = await ctx.http.post(trigger_url, json=payload)
    if resp.status_code >= 400:
        return WorkflowResult.fail(f"Logic App returned {resp.status_code}")
    return WorkflowResult.ok("Logic App triggered")
```

### 5. HMAC-Signed Webhook

POST with a cryptographic signature header for receivers that verify request authenticity.

```python
import hashlib
import hmac
import json

async def run(ctx: WorkflowContext) -> WorkflowResult:
    url = ctx.secrets.get("SIGNED_WEBHOOK_URL")
    secret = ctx.secrets.get("SIGNED_WEBHOOK_SECRET")
    if not url or not secret:
        return WorkflowResult.fail("Webhook URL and secret must be set")

    payload = {"indicator": ctx.indicator.value, "type": ctx.indicator.type}
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    resp = await ctx.http.post(
        url, content=body,
        headers={"Content-Type": "application/json", "X-Signature-256": f"sha256={sig}"},
    )
    if resp.status_code >= 400:
        return WorkflowResult.fail(f"Webhook returned {resp.status_code}")
    return WorkflowResult.ok("Signed webhook delivered")
```

See: [`docs/workflows/examples/hmac_signed_webhook.py`](workflows/examples/hmac_signed_webhook.py)

## Builtin Workflows

Calseta ships with 9 pre-built workflows for Okta and Microsoft Entra identity lifecycle management. These are the "batteries included" version of the HTTP automation pattern — they use the same `ctx.http` under the hood, wrapped in typed integration clients.

**Okta** (requires `OKTA_DOMAIN` + `OKTA_API_TOKEN`):

| Workflow | What it does | Risk |
|---|---|---|
| Okta — Revoke All Sessions | Terminates all active sessions | Low |
| Okta — Suspend User | Blocks all sign-in attempts | High |
| Okta — Unsuspend User | Restores a suspended account | Medium |
| Okta — Reset Password | Sends a password reset email | Medium |
| Okta — Force Password Expiry | Requires new password at next login | Low |

**Microsoft Entra** (requires `ENTRA_TENANT_ID` + `ENTRA_CLIENT_ID` + `ENTRA_CLIENT_SECRET`):

| Workflow | What it does | Risk |
|---|---|---|
| Entra — Revoke Sign-in Sessions | Invalidates refresh tokens | Low |
| Entra — Disable Account | Sets accountEnabled=false | High |
| Entra — Enable Account | Re-enables a disabled account | Medium |
| Entra — Force MFA Re-registration | Deletes all registered auth methods | High |

All builtin workflows have `approval_mode="agent_only"` — they require human approval when triggered by an AI agent, but execute immediately when triggered by a human.

## Code Generation

Use `POST /v1/workflows/generate` to describe what you want in plain English. The API returns generated workflow code, a suggested name, and documentation.

```bash
curl -X POST http://localhost:8000/v1/workflows/generate \
  -H "Authorization: Bearer cai_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "description": "When a malicious IP is detected, add it to our Cloudflare WAF block list",
    "indicator_types": ["ip"]
  }'
```

The generated code is AST-validated before being returned. Review the code, then save it as a new workflow via `POST /v1/workflows`.

**Requires** `ANTHROPIC_API_KEY` in your environment.

## Testing

Use `POST /v1/workflows/{uuid}/test` to run a workflow with mock HTTP responses. No real external calls are made.

```bash
curl -X POST http://localhost:8000/v1/workflows/{uuid}/test \
  -H "Authorization: Bearer cai_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "indicator_type": "ip",
    "indicator_value": "203.0.113.42",
    "mock_responses": [
      {
        "url_pattern": "https://api.example.com/*",
        "status_code": 200,
        "body": {"result": "blocked"}
      }
    ]
  }'
```

The response includes the `WorkflowResult`, execution duration, and the full log output from `ctx.log`.

## Approval Gate

Workflows can require human approval before execution via the `approval_mode` field.

Three modes are available:

- `"always"` — approval is required for every execution, regardless of trigger source
- `"agent_only"` — approval is required only when triggered by an AI agent (`trigger_source: "agent"`); human-triggered executions bypass the gate
- `"never"` (default) — no approval required; executes immediately

When the approval gate fires, the execution is paused and an approval request is created. A human must approve or reject via:

- `POST /v1/workflow-approvals/{uuid}/approve`
- `POST /v1/workflow-approvals/{uuid}/reject`

If a Slack or Teams notifier is configured (`APPROVAL_NOTIFIER=slack` or `teams`), the approver receives a notification with action buttons (Slack) or REST API links (Teams).

Agent-triggered execute requests must include `reason` and `confidence` fields explaining why the workflow should run.

---

## Proposing Response Actions from Agents

Workflows execute arbitrary HTTP automation scripts. For pre-defined, auditable containment and response operations (block an IP in a firewall, disable a user in Entra ID, isolate a host in CrowdStrike), agents use the **actions system** instead.

Actions are proposed via `POST /v1/actions` (or the MCP tool `propose_action`) with an `action_type`, `action_subtype`, structured `payload`, `confidence` score, and `reasoning`. The platform routes the action to the correct integration, applies the approval gate, and executes it. No custom Python code is required.

```bash
curl -X POST http://localhost:8000/v1/actions \
  -H "Authorization: Bearer cai_YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "action_type": "containment",
    "action_subtype": "isolate_host",
    "payload": {"device_id": "abc123", "comment": "Suspected C2 beacon"},
    "confidence": 0.91,
    "reasoning": "Process tree shows injected svchost.exe contacting known C2 IP"
  }'
```

- **Integration setup guides** — `docs/integrations/crowdstrike/SETUP.md`, `docs/integrations/entra-id-actions/SETUP.md`, `docs/integrations/slack-actions/SETUP.md`
- **Adding a new integration** — see `app/integrations/actions/CONTEXT.md` for the extension pattern
- **Approval routing** — containment/remediation require human approval by default; see `HOW_TO_SETUP_SLACK_APPROVALS.md` for the confidence-override thresholds
