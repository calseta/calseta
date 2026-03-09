"""
Generic Webhook — POST alert/indicator context to any URL.

Use case: Forward alert data to a SOAR, ticketing system, or custom webhook
endpoint for further processing. Works with any HTTP endpoint that accepts JSON.
"""

from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    # Read the webhook URL from environment variables
    webhook_url = ctx.secrets.get("WEBHOOK_URL")
    if not webhook_url:
        return WorkflowResult.fail("WEBHOOK_URL environment variable is not set")

    # Build the payload with indicator and alert context
    payload = {
        "indicator_type": ctx.indicator.type,
        "indicator_value": ctx.indicator.value,
        "malice": ctx.indicator.malice,
    }
    if ctx.alert:
        payload["alert"] = {
            "title": ctx.alert.title,
            "severity": ctx.alert.severity,
            "source": ctx.alert.source_name,
            "status": ctx.alert.status,
        }

    # POST to the webhook endpoint
    ctx.log.info("sending_webhook", url=webhook_url)
    try:
        resp = await ctx.http.post(webhook_url, json=payload)
    except Exception as exc:
        ctx.log.error("webhook_request_failed", error=str(exc))
        return WorkflowResult.fail(f"HTTP request failed: {exc}")

    if resp.status_code >= 400:
        ctx.log.error("webhook_error", status=resp.status_code, body=resp.text[:200])
        return WorkflowResult.fail(
            f"Webhook returned {resp.status_code}",
            data={"status_code": resp.status_code},
        )

    ctx.log.info("webhook_sent", status=resp.status_code)
    return WorkflowResult.ok(
        f"Webhook delivered (HTTP {resp.status_code})",
        data={"status_code": resp.status_code},
    )
