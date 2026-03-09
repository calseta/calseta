"""
REST API with Bearer Token — Create a ServiceNow incident from alert data.

Use case: Automatically create incidents in ServiceNow (or any REST API that
uses Bearer token auth) when a malicious indicator is detected. Adapt the
payload and endpoint for Jira, PagerDuty, Opsgenie, or any similar service.
"""

import json

from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    # Load credentials from environment
    instance = ctx.secrets.get("SERVICENOW_INSTANCE")  # e.g. "mycompany.service-now.com"
    api_token = ctx.secrets.get("SERVICENOW_API_TOKEN")
    if not instance or not api_token:
        return WorkflowResult.fail(
            "SERVICENOW_INSTANCE and SERVICENOW_API_TOKEN must be set"
        )

    # Build the incident payload
    description = f"Indicator: {ctx.indicator.type} = {ctx.indicator.value}\n"
    description += f"Malice verdict: {ctx.indicator.malice}\n"
    if ctx.alert:
        description += f"Alert: {ctx.alert.title} (severity: {ctx.alert.severity})\n"
        description += f"Source: {ctx.alert.source_name}\n"

    incident_payload = {
        "short_description": f"SOC Alert: {ctx.indicator.type} {ctx.indicator.value}",
        "description": description,
        "urgency": "2",  # medium
        "impact": "2",
    }

    # Call the ServiceNow Table API
    url = f"https://{instance}/api/now/table/incident"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    ctx.log.info("creating_incident", instance=instance)
    try:
        resp = await ctx.http.post(url, headers=headers, json=incident_payload)
    except Exception as exc:
        ctx.log.error("servicenow_request_failed", error=str(exc))
        return WorkflowResult.fail(f"HTTP request failed: {exc}")

    if resp.status_code not in (200, 201):
        ctx.log.error("servicenow_error", status=resp.status_code, body=resp.text[:200])
        return WorkflowResult.fail(
            f"ServiceNow returned {resp.status_code}",
            data={"status_code": resp.status_code},
        )

    # Extract the incident number from the response
    result = resp.json()
    incident_number = result.get("result", {}).get("number", "unknown")
    sys_id = result.get("result", {}).get("sys_id", "")

    ctx.log.info("incident_created", number=incident_number)
    return WorkflowResult.ok(
        f"ServiceNow incident created: {incident_number}",
        data={"incident_number": incident_number, "sys_id": sys_id},
    )
