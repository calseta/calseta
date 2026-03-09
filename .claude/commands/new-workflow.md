---
name: new-workflow
description: Create a new HTTP automation workflow for Calseta. Use when the user wants to build a workflow that calls an external API, webhook, or service.
argument-hint: "<description> (e.g. block IP in Cloudflare WAF, create Jira ticket, post to Slack)"
allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---

Create a new Calseta workflow for: **$ARGUMENTS**

Workflows are **HTTP automation scripts** — Python is the glue layer for constructing HTTP requests, calling external endpoints via `ctx.http`, and parsing responses.

## Reference files (read these first)

Read these files to understand the workflow interface, sandbox constraints, and existing patterns:

1. `app/workflows/context.py` — `WorkflowContext`, `WorkflowResult`, `SecretsAccessor`, integration clients
2. `app/services/workflow_ast.py` — allowed imports list and blocked modules/builtins
3. `docs/HOW_TO_WRITE_WORKFLOWS.md` — patterns and examples
4. `docs/workflows/examples/` — 5 standalone example files

## Workflow rules

Every workflow MUST follow these rules:

1. **Signature:** `async def run(ctx: WorkflowContext) -> WorkflowResult:`
2. **Import:** `from app.workflows.context import WorkflowContext, WorkflowResult`
3. **Allowed imports ONLY:**
   ```
   asyncio, base64, collections, copy, datetime, enum, functools,
   hashlib, hmac, html, http, inspect, io, ipaddress, itertools,
   json, logging, math, operator, re, statistics, string, textwrap,
   time, typing, typing_extensions, unicodedata, urllib, uuid,
   app.workflows.context, calseta.workflows
   ```
4. **Blocked:** `os`, `subprocess`, `sys`, `importlib`, `socket`, `ctypes`, `pickle`, `shutil`, `tempfile`, `pathlib` (and all other modules not in the allowed list)
5. **Blocked builtins:** `exec()`, `eval()`, `compile()`, `open()`, `breakpoint()`, `input()`, `__import__()`
6. **Never raise:** catch all exceptions and return `WorkflowResult.fail()` on error
7. **Check integrations:** if using `ctx.integrations.okta` or `.entra`, check for `None` first
8. **Check secrets:** always handle `ctx.secrets.get("KEY")` returning `None`
9. **Log key events:** use `ctx.log.info()`, `ctx.log.warning()`, `ctx.log.error()`

## The pattern

Every workflow follows this structure:

```python
from app.workflows.context import WorkflowContext, WorkflowResult

async def run(ctx: WorkflowContext) -> WorkflowResult:
    # 1. Read credentials
    api_key = ctx.secrets.get("SERVICE_API_KEY")
    if not api_key:
        return WorkflowResult.fail("SERVICE_API_KEY is not set")

    # 2. Build request with indicator/alert data
    payload = {"indicator": ctx.indicator.value, "type": ctx.indicator.type}

    # 3. Call endpoint via ctx.http
    ctx.log.info("calling_service", indicator=ctx.indicator.value)
    try:
        resp = await ctx.http.post(
            "https://api.example.com/action",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"}
        )
    except Exception as exc:
        ctx.log.error("request_failed", error=str(exc))
        return WorkflowResult.fail(f"Request failed: {exc}")

    # 4. Check response and return result
    if resp.status_code >= 400:
        ctx.log.error("api_error", status=resp.status_code)
        return WorkflowResult.fail(f"API returned {resp.status_code}")

    ctx.log.info("action_completed", status=resp.status_code)
    return WorkflowResult.ok("Action completed", data=resp.json())
```

## Available context

| Field | Type | Description |
|---|---|---|
| `ctx.indicator.type` | `str` | `ip`, `domain`, `hash_sha256`, `account`, `url`, `email`, etc. |
| `ctx.indicator.value` | `str` | The indicator value |
| `ctx.indicator.malice` | `str` | `Pending`, `Benign`, `Suspicious`, `Malicious` |
| `ctx.indicator.enrichment_results` | `dict \| None` | Enrichment data from all providers |
| `ctx.alert` | `AlertContext \| None` | May be `None` for standalone indicator workflows |
| `ctx.alert.uuid` | `UUID` | Alert UUID |
| `ctx.alert.title` | `str` | Alert title |
| `ctx.alert.severity` | `str` | `Informational`, `Low`, `Medium`, `High`, `Critical` |
| `ctx.alert.source_name` | `str` | e.g. `sentinel`, `elastic`, `splunk` |
| `ctx.alert.status` | `str` | `Open`, `Triaging`, `Escalated`, `Closed` |
| `ctx.alert.tags` | `list[str]` | Alert tags |
| `ctx.alert.raw_payload` | `dict` | Original source payload |
| `ctx.http` | `httpx.AsyncClient` | HTTP client (timeout matches workflow setting) |
| `ctx.log` | `WorkflowLogger` | `.info()`, `.warning()`, `.error()`, `.debug()` |
| `ctx.secrets` | `SecretsAccessor` | `.get("KEY")` → `str \| None` |
| `ctx.integrations.okta` | `OktaClient \| None` | Pre-built Okta lifecycle client |
| `ctx.integrations.entra` | `EntraClient \| None` | Pre-built Entra lifecycle client |

## Steps to follow

1. **Understand the target.** Ask clarifying questions if the user's description is ambiguous — what API endpoint, what auth method, what data to send, what response to expect.

2. **Write the workflow code.** Create the Python code following the pattern above. Save it to a file the user can review:
   - If adding as a new example: `docs/workflows/examples/<name>.py`
   - If the user wants to register it via API, output the code for them to copy

3. **Validate the code.** Run AST validation to confirm it passes:
   ```bash
   python -c "
   from app.services.workflow_ast import validate_workflow_code
   with open('<path>') as f:
       errors = validate_workflow_code(f.read())
   print('PASS' if not errors else f'FAIL: {errors}')
   "
   ```

4. **Determine metadata.** Suggest values for:
   - `name` — short, descriptive (e.g. "Block IP in Cloudflare WAF")
   - `workflow_type` — `indicator` (most common)
   - `indicator_types` — which indicator types this applies to (e.g. `["ip"]`, `["account"]`, `["ip", "domain"]`)
   - `risk_level` — `low`, `medium`, or `high`
   - `approval_mode` — `"always"` for destructive actions (block, disable, delete), `"agent_only"` for agent-triggered approval only, `"never"` for read-only or notification workflows
   - `documentation` — markdown with sections: Description, When to Use, Required Secrets, Expected Outcome, Error Cases

5. **Provide the API call** to register the workflow:
   ```bash
   curl -X POST http://localhost:8000/v1/workflows \
     -H "Authorization: Bearer cai_YOUR_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "...",
       "code": "...",
       "workflow_type": "indicator",
       "indicator_types": ["ip"],
       "state": "draft",
       "risk_level": "medium",
       "approval_mode": "always",
       "timeout_seconds": 30,
       "documentation": "..."
     }'
   ```

6. **Suggest a test call** with appropriate mock responses:
   ```bash
   curl -X POST http://localhost:8000/v1/workflows/{uuid}/test \
     -H "Authorization: Bearer cai_YOUR_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "indicator_type": "ip",
       "indicator_value": "203.0.113.42",
       "mock_responses": [...]
     }'
   ```

## Required env vars

Document which environment variables the workflow needs. The user must add these to their `.env` file before the workflow can execute successfully.

## Do NOT

- Do not import blocked modules — the AST validator will reject them
- Do not use `open()` or any filesystem access
- Do not let `run()` raise — always catch exceptions and return `WorkflowResult.fail()`
- Do not hardcode secrets — always use `ctx.secrets.get()`
- Do not make the workflow overly complex — keep it focused on one HTTP automation task
