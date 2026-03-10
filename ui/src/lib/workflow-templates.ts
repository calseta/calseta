export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  code: string;
}

export const WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  {
    id: "starter",
    name: "Starter Template",
    description: "Annotated scaffold with all available context fields",
    code: `\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    # ── Available context ──────────────────────────────────────────────
    # ctx.indicator.type       → "ip", "domain", "hash_sha256", etc.
    # ctx.indicator.value      → "1.2.3.4", "evil.com", etc.
    # ctx.indicator.malice     → "Pending", "Benign", "Suspicious", "Malicious"
    # ctx.alert.title          → alert title (None if standalone workflow)
    # ctx.alert.severity       → "Low", "Medium", "High", "Critical"
    # ctx.http                 → async HTTP client (httpx.AsyncClient)
    # ctx.secrets.get("KEY")   → read environment variables
    # ctx.log.info("message")  → structured logging

    # ── Your code here ─────────────────────────────────────────────────
    ctx.log.info("workflow_started", indicator=ctx.indicator.value)

    # Example: POST to an external endpoint
    # url = ctx.secrets.get("WEBHOOK_URL")
    # resp = await ctx.http.post(url, json={"value": ctx.indicator.value})

    # ── Return result ──────────────────────────────────────────────────
    return WorkflowResult.ok("Workflow completed", data={})
    # On failure: return WorkflowResult.fail("Something went wrong")
`,
  },
  {
    id: "generic-webhook",
    name: "Generic Webhook",
    description: "POST indicator/alert context to any URL (SOAR, ticketing, custom endpoint)",
    code: `\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    # ── Step 1: Load config ──────────────────────────────────────────
    # You can hardcode the URL or load it from an env var via ctx.secrets.get()
    # Using secrets keeps the URL configurable across environments without editing code
    webhook_url = ctx.secrets.get("WEBHOOK_URL")
    if not webhook_url:
        return WorkflowResult.fail("WEBHOOK_URL environment variable is not set")

    # ── Step 2: Build the payload ────────────────────────────────────
    # Always include the indicator that triggered this workflow
    payload = {
        "indicator_type": ctx.indicator.type,
        "indicator_value": ctx.indicator.value,
        "malice": ctx.indicator.malice,
    }
    # If this workflow was triggered from an alert, include alert context too
    if ctx.alert:
        payload["alert"] = {
            "title": ctx.alert.title,
            "severity": ctx.alert.severity,
            "source": ctx.alert.source_name,
            "status": ctx.alert.status,
        }

    # ── Step 3: Send the webhook ─────────────────────────────────────
    ctx.log.info("sending_webhook", url=webhook_url)
    try:
        resp = await ctx.http.post(webhook_url, json=payload)
    except Exception as exc:
        # Network errors, DNS failures, timeouts, etc.
        ctx.log.error("webhook_request_failed", error=str(exc))
        return WorkflowResult.fail(f"HTTP request failed: {exc}")

    # ── Step 4: Check the response ───────────────────────────────────
    if resp.status_code >= 400:
        ctx.log.error("webhook_error", status=resp.status_code, body=resp.text[:200])
        return WorkflowResult.fail(
            f"Webhook returned {resp.status_code}",
            data={"status_code": resp.status_code},
        )

    # ── Done — return success with delivery status ───────────────────
    ctx.log.info("webhook_sent", status=resp.status_code)
    return WorkflowResult.ok(
        f"Webhook delivered (HTTP {resp.status_code})",
        data={"status_code": resp.status_code},
    )
`,
  },
  {
    id: "rest-api-bearer",
    name: "REST API (Bearer Token)",
    description: "Call a REST API with bearer token auth (ServiceNow, Jira, PagerDuty)",
    code: `\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    # ── Step 1: Load config ──────────────────────────────────────────
    # URLs can be hardcoded or loaded from env vars via ctx.secrets.get()
    # Tokens/credentials should always use ctx.secrets.get() — never hardcode secrets
    api_url = ctx.secrets.get("API_BASE_URL")
    api_token = ctx.secrets.get("API_TOKEN")
    if not api_url or not api_token:
        return WorkflowResult.fail("API_BASE_URL and API_TOKEN must be set")

    # ── Step 2: Build the ticket payload ─────────────────────────────
    # Customize these fields to match your ticketing system's API schema
    payload = {
        "summary": f"SOC Alert: {ctx.indicator.type} {ctx.indicator.value}",
        "description": f"Indicator {ctx.indicator.value} detected with verdict: {ctx.indicator.malice}",
        "priority": ctx.alert.severity if ctx.alert else "Medium",
    }

    # ── Step 3: Create the ticket via REST API ───────────────────────
    # Change the path "/api/tickets" to match your system's endpoint
    ctx.log.info("creating_ticket", url=api_url)
    try:
        resp = await ctx.http.post(
            f"{api_url}/api/tickets",
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    except Exception as exc:
        # Network errors, DNS failures, timeouts, etc.
        ctx.log.error("api_request_failed", error=str(exc))
        return WorkflowResult.fail(f"HTTP request failed: {exc}")

    # ── Step 4: Check the response ───────────────────────────────────
    # Most REST APIs return 200 or 201 on successful creation
    if resp.status_code not in (200, 201):
        ctx.log.error("api_error", status=resp.status_code, body=resp.text[:200])
        return WorkflowResult.fail(
            f"API returned {resp.status_code}",
            data={"status_code": resp.status_code},
        )

    # ── Done — return the created ticket data ────────────────────────
    # resp.json() parses the JSON response body into a Python dict
    result = resp.json()
    ctx.log.info("ticket_created", ticket_id=result.get("id"))
    return WorkflowResult.ok(
        f"Ticket created: {result.get('id', 'unknown')}",
        data=result,
    )
`,
  },
  {
    id: "slack-notification",
    name: "Slack Notification",
    description: "Post an alert summary to Slack via incoming webhook",
    code: `\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    # ── Step 1: Load config ──────────────────────────────────────────
    # Create a Slack incoming webhook at: https://api.slack.com/messaging/webhooks
    # You can hardcode the URL or load it from an env var
    webhook_url = ctx.secrets.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return WorkflowResult.fail("SLACK_WEBHOOK_URL environment variable is not set")

    # ── Step 2: Build the Slack Block Kit message ────────────────────
    # Slack Block Kit docs: https://api.slack.com/block-kit
    # "blocks" controls the rich layout; "text" is the fallback for notifications
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Indicator Detected: {ctx.indicator.value}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Type:* \`{ctx.indicator.type}\`"},
                {"type": "mrkdwn", "text": f"*Verdict:* {ctx.indicator.malice}"},
            ],
        },
    ]

    # If triggered from an alert, add alert details as an extra section
    if ctx.alert:
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Alert:* {ctx.alert.title}"},
                {"type": "mrkdwn", "text": f"*Severity:* {ctx.alert.severity}"},
                {"type": "mrkdwn", "text": f"*Source:* {ctx.alert.source_name}"},
            ],
        })

    # ── Step 3: Send the message ─────────────────────────────────────
    ctx.log.info("sending_slack_notification")
    try:
        resp = await ctx.http.post(
            webhook_url,
            json={"text": f"Indicator: {ctx.indicator.value}", "blocks": blocks},
            headers={"Content-Type": "application/json"},
        )
    except Exception as exc:
        ctx.log.error("slack_webhook_failed", error=str(exc))
        return WorkflowResult.fail(f"Slack webhook failed: {exc}")

    # ── Step 4: Check the response ───────────────────────────────────
    # Slack webhooks return 200 with body "ok" on success
    if resp.status_code != 200:
        ctx.log.error("slack_error", status=resp.status_code, body=resp.text[:200])
        return WorkflowResult.fail(f"Slack returned {resp.status_code}")

    # ── Done ─────────────────────────────────────────────────────────
    ctx.log.info("slack_notification_sent")
    return WorkflowResult.ok("Slack notification sent")
`,
  },
  {
    id: "hmac-webhook",
    name: "HMAC-Signed Webhook",
    description: "POST with cryptographic signature for receivers that verify authenticity",
    code: `\
import hashlib
import hmac
import json

from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    # ── Step 1: Load config ──────────────────────────────────────────
    # URL can be hardcoded or loaded from env vars
    # The shared secret should always use ctx.secrets.get() — never hardcode secrets
    webhook_url = ctx.secrets.get("SIGNED_WEBHOOK_URL")
    webhook_secret = ctx.secrets.get("SIGNED_WEBHOOK_SECRET")
    if not webhook_url or not webhook_secret:
        return WorkflowResult.fail(
            "SIGNED_WEBHOOK_URL and SIGNED_WEBHOOK_SECRET must be set"
        )

    # ── Step 2: Build the payload ────────────────────────────────────
    payload = {
        "indicator_type": ctx.indicator.type,
        "indicator_value": ctx.indicator.value,
        "malice": ctx.indicator.malice,
    }
    if ctx.alert:
        payload["alert_title"] = ctx.alert.title
        payload["alert_severity"] = ctx.alert.severity

    # ── Step 3: Compute HMAC-SHA256 signature ────────────────────────
    # sort_keys=True ensures deterministic JSON so both sides compute the same hash
    body_bytes = json.dumps(payload, sort_keys=True).encode()
    # The receiver verifies this signature using the same shared secret
    signature = hmac.new(
        webhook_secret.encode(), body_bytes, hashlib.sha256
    ).hexdigest()

    # ── Step 4: Send the signed request ──────────────────────────────
    # We use "content=" (raw bytes) instead of "json=" because we already
    # serialized the body — this ensures the signature matches exactly
    ctx.log.info("sending_signed_webhook", url=webhook_url)
    try:
        resp = await ctx.http.post(
            webhook_url,
            content=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Signature-256": f"sha256={signature}",
            },
        )
    except Exception as exc:
        ctx.log.error("signed_webhook_failed", error=str(exc))
        return WorkflowResult.fail(f"HTTP request failed: {exc}")

    # ── Step 5: Check the response ───────────────────────────────────
    if resp.status_code >= 400:
        return WorkflowResult.fail(
            f"Webhook returned {resp.status_code}",
            data={"status_code": resp.status_code},
        )

    # ── Done ─────────────────────────────────────────────────────────
    return WorkflowResult.ok(f"Signed webhook delivered (HTTP {resp.status_code})")
`,
  },
];
