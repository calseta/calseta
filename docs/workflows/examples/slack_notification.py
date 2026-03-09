"""
Slack Notification — Post an alert summary to a Slack channel via webhook.

Use case: Notify your SOC team channel when a high-severity indicator is
detected. Uses Slack's Incoming Webhook URL — no bot token or app required.
"""

import json

from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    webhook_url = ctx.secrets.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return WorkflowResult.fail("SLACK_WEBHOOK_URL environment variable is not set")

    # Build a Slack message with Block Kit formatting
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
                {"type": "mrkdwn", "text": f"*Type:* `{ctx.indicator.type}`"},
                {"type": "mrkdwn", "text": f"*Verdict:* {ctx.indicator.malice}"},
            ],
        },
    ]

    if ctx.alert:
        blocks.append(
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Alert:* {ctx.alert.title}"},
                    {"type": "mrkdwn", "text": f"*Severity:* {ctx.alert.severity}"},
                    {"type": "mrkdwn", "text": f"*Source:* {ctx.alert.source_name}"},
                    {"type": "mrkdwn", "text": f"*Status:* {ctx.alert.status}"},
                ],
            }
        )

    slack_payload = {
        "text": f"Indicator detected: {ctx.indicator.type} {ctx.indicator.value}",
        "blocks": blocks,
    }

    ctx.log.info("sending_slack_notification")
    try:
        resp = await ctx.http.post(
            webhook_url,
            json=slack_payload,
            headers={"Content-Type": "application/json"},
        )
    except Exception as exc:
        ctx.log.error("slack_webhook_failed", error=str(exc))
        return WorkflowResult.fail(f"Slack webhook failed: {exc}")

    # Slack incoming webhooks return "ok" with 200 on success
    if resp.status_code != 200:
        ctx.log.error("slack_error", status=resp.status_code, body=resp.text[:200])
        return WorkflowResult.fail(
            f"Slack returned {resp.status_code}",
            data={"status_code": resp.status_code},
        )

    ctx.log.info("slack_notification_sent")
    return WorkflowResult.ok("Slack notification sent")
