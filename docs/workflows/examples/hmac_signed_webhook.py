"""
HMAC-Signed Webhook — POST with an HMAC-SHA256 signature header.

Use case: Many webhook receivers (GitHub, Stripe, custom services) require
requests to include an HMAC signature so they can verify the sender. This
pattern constructs the signature using a shared secret from env vars.
"""

import hashlib
import hmac
import json

from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    webhook_url = ctx.secrets.get("SIGNED_WEBHOOK_URL")
    webhook_secret = ctx.secrets.get("SIGNED_WEBHOOK_SECRET")
    if not webhook_url or not webhook_secret:
        return WorkflowResult.fail(
            "SIGNED_WEBHOOK_URL and SIGNED_WEBHOOK_SECRET must be set"
        )

    # Build the payload
    payload = {
        "event": "indicator_detected",
        "indicator_type": ctx.indicator.type,
        "indicator_value": ctx.indicator.value,
        "malice": ctx.indicator.malice,
    }
    if ctx.alert:
        payload["alert_title"] = ctx.alert.title
        payload["alert_severity"] = ctx.alert.severity

    # Serialize to bytes for signing (sorted keys for deterministic output)
    body_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")

    # Compute HMAC-SHA256 signature
    signature = hmac.new(
        webhook_secret.encode("utf-8"),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Signature-256": f"sha256={signature}",
    }

    ctx.log.info("sending_signed_webhook", url=webhook_url)
    try:
        resp = await ctx.http.post(webhook_url, headers=headers, content=body_bytes)
    except Exception as exc:
        ctx.log.error("signed_webhook_failed", error=str(exc))
        return WorkflowResult.fail(f"HTTP request failed: {exc}")

    if resp.status_code >= 400:
        ctx.log.error("webhook_error", status=resp.status_code, body=resp.text[:200])
        return WorkflowResult.fail(
            f"Webhook returned {resp.status_code}",
            data={"status_code": resp.status_code},
        )

    ctx.log.info("signed_webhook_sent", status=resp.status_code)
    return WorkflowResult.ok(
        f"Signed webhook delivered (HTTP {resp.status_code})",
        data={"status_code": resp.status_code},
    )
