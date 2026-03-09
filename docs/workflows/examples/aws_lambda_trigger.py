"""
AWS Lambda Trigger — Invoke a Lambda function via its Function URL.

Use case: Trigger serverless automation (quarantine an EC2 instance, update a
WAF rule, run a forensic snapshot) by calling a Lambda Function URL or API
Gateway endpoint. No AWS SDK needed — it's just an HTTP POST.
"""

from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    # Lambda Function URL (or API Gateway endpoint)
    function_url = ctx.secrets.get("LAMBDA_FUNCTION_URL")
    if not function_url:
        return WorkflowResult.fail("LAMBDA_FUNCTION_URL environment variable is not set")

    # Optional: IAM auth header (if using IAM-authenticated Function URL,
    # you'd sign the request with SigV4 — but most SOC automations use
    # a simpler auth approach like a shared secret in the payload)
    auth_token = ctx.secrets.get("LAMBDA_AUTH_TOKEN")

    # Build the event payload
    event = {
        "source": "calseta",
        "indicator_type": ctx.indicator.type,
        "indicator_value": ctx.indicator.value,
        "malice": ctx.indicator.malice,
    }
    if ctx.alert:
        event["alert_uuid"] = str(ctx.alert.uuid)
        event["alert_severity"] = ctx.alert.severity

    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    ctx.log.info("invoking_lambda", url=function_url)
    try:
        resp = await ctx.http.post(function_url, headers=headers, json=event)
    except Exception as exc:
        ctx.log.error("lambda_invoke_failed", error=str(exc))
        return WorkflowResult.fail(f"Lambda invocation failed: {exc}")

    if resp.status_code >= 400:
        ctx.log.error("lambda_error", status=resp.status_code, body=resp.text[:200])
        return WorkflowResult.fail(
            f"Lambda returned {resp.status_code}",
            data={"status_code": resp.status_code},
        )

    # Parse the Lambda response (Function URLs return the function's response directly)
    try:
        result_data = resp.json()
    except Exception:
        result_data = {"raw_response": resp.text[:500]}

    ctx.log.info("lambda_invoked", status=resp.status_code)
    return WorkflowResult.ok(
        f"Lambda invoked successfully (HTTP {resp.status_code})",
        data=result_data,
    )
