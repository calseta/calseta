"""
Workflow code generation service (Chunk 4.7).

Calls the Anthropic API to generate valid workflow Python code from a
natural language description. Returns the generated code plus metadata
for human review before saving.

The generated code is always AST-validated before returning. If the LLM
produces invalid code, the error is surfaced to the caller rather than
silently failing.
"""

from __future__ import annotations

import json

import httpx

from app.config import Settings
from app.schemas.workflows import WorkflowGenerateResponse
from app.services.workflow_ast import validate_workflow_code

# ---------------------------------------------------------------------------
# System prompt for code generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert security automation engineer. You write workflow functions
for the Calseta SOC platform. Every workflow must follow these rules exactly.

## Workflow Interface

```python
from app.workflows.context import WorkflowContext, WorkflowResult

async def run(ctx: WorkflowContext) -> WorkflowResult:
    ...
```

### WorkflowContext fields
- `ctx.indicator.type` — indicator type string (e.g. "ip", "domain", "account", "hash_sha256")
- `ctx.indicator.value` — indicator value string
- `ctx.alert` — AlertContext or None; has fields: uuid, title, severity, status, source_name, tags
- `ctx.http` — httpx.AsyncClient for external HTTP requests (pre-configured with timeout)
- `ctx.log.info(msg, **kv)` / `ctx.log.warning(msg, **kv)` / `ctx.log.error(msg, **kv)` — structured logging
- `ctx.secrets.get("KEY_NAME")` — reads a named env var; returns str or None
- `ctx.integrations.okta` — OktaClient or None
- `ctx.integrations.entra` — EntraClient or None

### OktaClient methods
- `await ctx.integrations.okta.revoke_sessions(user_id: str) -> None`
- `await ctx.integrations.okta.suspend_user(user_id: str) -> None`
- `await ctx.integrations.okta.unsuspend_user(user_id: str) -> None`
- `await ctx.integrations.okta.reset_password(user_id: str) -> str | None`
- `await ctx.integrations.okta.expire_password(user_id: str) -> None`

### EntraClient methods
- `await ctx.integrations.entra.revoke_sessions(user_id: str) -> None`
- `await ctx.integrations.entra.disable_account(user_id: str) -> None`
- `await ctx.integrations.entra.enable_account(user_id: str) -> None`
- `await ctx.integrations.entra.reset_mfa(user_id: str) -> None`

### WorkflowResult
- `WorkflowResult.ok(message, data={})` — success result
- `WorkflowResult.fail(message, data={})` — failure result

## Rules
1. The function signature MUST be exactly `async def run(ctx: WorkflowContext) -> WorkflowResult:`
2. Allowed imports ONLY: asyncio, datetime, json, re, typing, uuid, app.workflows.context, calseta.workflows
3. Never import os, sys, subprocess, importlib, socket, ctypes, pickle, pathlib, shutil
4. Never use exec(), eval(), open(), compile(), breakpoint(), input()
5. Always handle exceptions; never let run() raise — return WorkflowResult.fail() on error
6. Check integrations are not None before using (e.g. if ctx.integrations.okta is None: return fail)
7. Log key events with ctx.log.info/warning/error

## Response format
Respond ONLY with a JSON object (no markdown fences) with exactly these keys:
- "code": the complete workflow Python code as a string
- "suggested_name": a short, descriptive name (e.g. "Okta — Suspend User")
- "suggested_documentation": markdown documentation with sections: ## Description, ## When to Use, ## Required Secrets, ## Expected Outcome, ## Error Cases
- "warnings": list of strings (empty list if none)
"""


_USER_PROMPT_TEMPLATE = """\
Generate a Calseta workflow for the following task:

{description}

Workflow type: {workflow_type}
Indicator types: {indicator_types}

Respond only with the JSON object as specified in the system prompt.
"""


async def generate_workflow_code(
    description: str,
    workflow_type: str | None,
    indicator_types: list[str],
    cfg: Settings,
) -> WorkflowGenerateResponse:
    """
    Call the Anthropic API to generate workflow code from a description.

    Returns a WorkflowGenerateResponse with the generated code, suggested
    name/documentation, and any warnings.

    Raises ValueError if generation fails or returns invalid code.
    """
    if not cfg.ANTHROPIC_API_KEY:
        raise ValueError(
            "ANTHROPIC_API_KEY is not configured. "
            "Set it in your .env file to use workflow generation."
        )

    user_prompt = _USER_PROMPT_TEMPLATE.format(
        description=description,
        workflow_type=workflow_type or "indicator",
        indicator_types=", ".join(indicator_types) if indicator_types else "any",
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": cfg.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "system": _SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_prompt}],
            },
        )

    if response.status_code != 200:
        raise ValueError(
            f"Anthropic API returned {response.status_code}: {response.text[:500]}"
        )

    payload = response.json()
    content_blocks = payload.get("content", [])
    raw_text = ""
    for block in content_blocks:
        if block.get("type") == "text":
            raw_text = block.get("text", "")
            break

    if not raw_text:
        raise ValueError("Anthropic API returned empty response content")

    # Parse the JSON response from the LLM
    try:
        # Strip possible markdown code fences if the model added them anyway
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        generated = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Failed to parse LLM response as JSON: {exc}") from exc

    code = generated.get("code", "")
    if not code:
        raise ValueError("LLM response missing 'code' field")

    suggested_name = generated.get("suggested_name", "Generated Workflow")
    suggested_doc = generated.get("suggested_documentation", "")
    warnings = list(generated.get("warnings", []))

    # Validate the generated code
    ast_errors = validate_workflow_code(code)
    if ast_errors:
        raise ValueError(
            f"Generated code failed AST validation: {'; '.join(ast_errors)}"
        )

    return WorkflowGenerateResponse(
        generated_code=code,
        suggested_name=suggested_name,
        suggested_documentation=suggested_doc,
        warnings=warnings,
    )
