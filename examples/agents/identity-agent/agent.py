#!/usr/bin/env python3
"""
Identity Agent — Calseta Phase 7 Reference Implementation

Assesses account compromise risk from identity indicators using Calseta enrichment
and documents patterns for Microsoft Graph API and Okta API calls.

Usage:
    python agent.py --mode queue
    python agent.py --mode invocation --invocation-id <uuid>
    python agent.py --help
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import anthropic
import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CALSETA_API_URL = os.environ.get("CALSETA_API_URL", "http://localhost:8000")
CALSETA_AGENT_KEY = os.environ.get("CALSETA_AGENT_KEY", "")  # cak_* key
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

HEADERS = {"Authorization": f"Bearer {CALSETA_AGENT_KEY}"}

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"

ACCOUNT_INDICATOR_TYPES = {"account", "email"}


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def validate_env() -> None:
    missing = []
    if not CALSETA_AGENT_KEY:
        missing.append("CALSETA_AGENT_KEY")
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)


def load_system_prompt() -> str:
    if not SYSTEM_PROMPT_PATH.exists():
        print(f"ERROR: system_prompt.md not found at {SYSTEM_PROMPT_PATH}", file=sys.stderr)
        sys.exit(1)
    return SYSTEM_PROMPT_PATH.read_text()


# ---------------------------------------------------------------------------
# Calseta API helpers
# ---------------------------------------------------------------------------

async def fetch_alert(client: httpx.AsyncClient, alert_uuid: str) -> dict:
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/alerts/{alert_uuid}",
        headers=HEADERS,
    )
    if resp.status_code != 200:
        print(f"ERROR: Failed to fetch alert {alert_uuid}: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["data"]


async def fetch_enrichment(
    client: httpx.AsyncClient,
    indicator_type: str,
    indicator_value: str,
) -> dict | None:
    """Fetch Calseta enrichment for an account indicator."""
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/enrichments/{indicator_type}/{indicator_value}",
        headers=HEADERS,
    )
    if resp.status_code == 200:
        return resp.json().get("data")
    if resp.status_code == 404:
        return None
    print(
        f"WARNING: Enrichment fetch failed for {indicator_type}/{indicator_value}: {resp.status_code}",
        file=sys.stderr,
    )
    return None


async def fetch_invocation(client: httpx.AsyncClient, invocation_id: str) -> dict:
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/invocations/{invocation_id}",
        headers=HEADERS,
    )
    if resp.status_code != 200:
        print(f"ERROR: Failed to fetch invocation {invocation_id}: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["data"]


async def checkout_alert_from_queue(client: httpx.AsyncClient) -> dict | None:
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/queue",
        headers=HEADERS,
        params={"page_size": 1},
    )
    if resp.status_code != 200:
        print(f"ERROR: Failed to poll queue: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    items = resp.json().get("data", [])
    if not items:
        print("Queue is empty — no alerts to process.")
        return None
    return items[0]


async def patch_invocation_result(
    client: httpx.AsyncClient,
    invocation_id: str,
    result: dict,
) -> None:
    resp = await client.patch(
        f"{CALSETA_API_URL}/v1/invocations/{invocation_id}",
        headers=HEADERS,
        json={"status": "completed", "result": result},
    )
    if resp.status_code not in (200, 204):
        print(
            f"ERROR: Failed to patch invocation {invocation_id}: {resp.status_code} {resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Invocation {invocation_id} marked completed.")


# ---------------------------------------------------------------------------
# External identity API stub documentation
# ---------------------------------------------------------------------------

def document_graph_api_calls(account_value: str) -> list[dict]:
    """
    Documents Microsoft Graph API calls that would enrich this account indicator.
    These are stubs — actual calls require OAuth token and are not implemented here.
    """
    return [
        {
            "source": "Microsoft Graph — User Profile",
            "endpoint": f"GET https://graph.microsoft.com/v1.0/users/{account_value}",
            "auth": "Bearer $ENTRA_ACCESS_TOKEN (app-only, User.Read.All)",
            "returns": "displayName, userPrincipalName, jobTitle, department, accountEnabled, createdDateTime",
            # TODO: implement API call
            # import msal  # pip install msal
            # app = msal.ConfidentialClientApplication(
            #     client_id=os.environ["ENTRA_CLIENT_ID"],
            #     authority=f"https://login.microsoftonline.com/{os.environ['ENTRA_TENANT_ID']}",
            #     client_credential=os.environ["ENTRA_CLIENT_SECRET"],
            # )
            # token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
            # resp = await http_client.get(
            #     f"https://graph.microsoft.com/v1.0/users/{account_value}",
            #     headers={"Authorization": f"Bearer {token['access_token']}"}
            # )
        },
        {
            "source": "Microsoft Graph — Sign-in Logs",
            "endpoint": f"GET https://graph.microsoft.com/v1.0/auditLogs/signIns?$filter=userPrincipalName eq '{account_value}'&$top=50&$orderby=createdDateTime desc",
            "auth": "Bearer $ENTRA_ACCESS_TOKEN (AuditLog.Read.All)",
            "returns": "createdDateTime, ipAddress, location, deviceDetail, status, riskLevelDuringSignIn",
            # TODO: implement API call
            # resp = await http_client.get(
            #     "https://graph.microsoft.com/v1.0/auditLogs/signIns",
            #     headers={"Authorization": f"Bearer {token['access_token']}"},
            #     params={
            #         "$filter": f"userPrincipalName eq '{account_value}'",
            #         "$top": 50,
            #         "$orderby": "createdDateTime desc"
            #     }
            # )
        },
        {
            "source": "Microsoft Graph — Active Sessions",
            "endpoint": f"GET https://graph.microsoft.com/v1.0/users/{account_value}/authentication/signInPreferences",
            "auth": "Bearer $ENTRA_ACCESS_TOKEN (UserAuthenticationMethod.Read.All)",
            "returns": "Registered MFA methods, FIDO2 keys, authenticator app enrollments",
            # TODO: implement API call
        },
        {
            "source": "Microsoft Graph — Group Memberships",
            "endpoint": f"GET https://graph.microsoft.com/v1.0/users/{account_value}/memberOf",
            "auth": "Bearer $ENTRA_ACCESS_TOKEN (GroupMember.Read.All)",
            "returns": "Group names and IDs — critical for blast radius assessment",
            # TODO: implement API call
        },
    ]


def document_okta_api_calls(account_value: str) -> list[dict]:
    """
    Documents Okta API calls that would enrich this account indicator.
    These are stubs — actual calls require Okta API token and are not implemented here.
    """
    return [
        {
            "source": "Okta — User Profile",
            "endpoint": f"GET https://$OKTA_DOMAIN/api/v1/users/{account_value}",
            "auth": "Header: Authorization: SSWS $OKTA_API_TOKEN",
            "returns": "status, profile (email, login, firstName, lastName, department), created, lastLogin",
            # TODO: implement API call
            # resp = await http_client.get(
            #     f"https://{os.environ['OKTA_DOMAIN']}/api/v1/users/{account_value}",
            #     headers={"Authorization": f"SSWS {os.environ['OKTA_API_TOKEN']}"}
            # )
        },
        {
            "source": "Okta — User Sessions",
            "endpoint": f"GET https://$OKTA_DOMAIN/api/v1/users/{account_value}/sessions",
            "auth": "Header: Authorization: SSWS $OKTA_API_TOKEN",
            "returns": "Active session IDs, createdAt, expiresAt, lastFactorVerification",
            # TODO: implement API call
        },
        {
            "source": "Okta — System Log (User Events)",
            "endpoint": f"GET https://$OKTA_DOMAIN/api/v1/logs?filter=actor.id eq \"{account_value}\"&since=<24h ago>",
            "auth": "Header: Authorization: SSWS $OKTA_API_TOKEN",
            "returns": "eventType, displayMessage, outcome, client.ipAddress, client.geographicalContext",
            # TODO: implement API call
        },
    ]


# ---------------------------------------------------------------------------
# LLM assessment
# ---------------------------------------------------------------------------

def assess_account_risk(
    system_prompt: str,
    alert: dict,
    accounts_with_context: list[dict],
) -> dict:
    """Call the LLM to assess account compromise risk."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = f"""
## Alert Context

Title: {alert.get('title', 'Unknown')}
Severity: {alert.get('severity', 'Unknown')}
Source: {alert.get('source_name', 'Unknown')}
Occurred: {alert.get('occurred_at', 'Unknown')}
Description: {alert.get('description', 'No description')}

## Account Indicators and Identity Context

```json
{json.dumps(accounts_with_context, indent=2)}
```

Please assess each account for compromise risk following your output format. Note where
additional identity provider context (Graph API sign-in logs, Okta sessions) would
change your confidence level and what you would look for.

End with the **Overall Identity Risk Assessment** and single most urgent action.
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = message.content[0].text

    # Extract overall risk from response
    overall_risk = "Medium"
    for risk in ("Critical", "High", "Medium", "Low"):
        if risk.lower() in response_text.lower():
            overall_risk = risk
            break

    # Extract recommended actions
    recommended_actions = []
    in_actions = False
    for line in response_text.splitlines():
        if "recommended action" in line.lower() or "most urgent action" in line.lower():
            in_actions = True
            continue
        if in_actions:
            stripped = line.strip()
            if stripped.startswith(("-", "*", "•")) or (stripped and stripped[0].isdigit()):
                action = stripped.lstrip("-*•0123456789. ").strip()
                if action:
                    recommended_actions.append(action)
            elif stripped.startswith("#") and len(stripped) > 2:
                in_actions = False

    return {
        "assessment": response_text,
        "overall_risk": overall_risk,
        "recommended_actions": recommended_actions[:5],
    }


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

async def run_identity_agent(
    alert_uuid: str,
    invocation_id: str | None,
    system_prompt: str,
) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Fetching alert {alert_uuid}...")
        alert = await fetch_alert(client, alert_uuid)
        print(f"Alert: {alert.get('title', 'Untitled')} [{alert.get('severity', 'Unknown')}]")

        # Filter to account/email indicators
        all_indicators = alert.get("indicators", [])
        account_indicators = [
            ind for ind in all_indicators
            if ind.get("type", "").lower() in ACCOUNT_INDICATOR_TYPES
        ]

        # Also check raw_payload for account context not in indicators
        raw = alert.get("raw_payload", {})
        account_from_raw = raw.get("user") or raw.get("account") or raw.get("upn") or raw.get("username")

        if not account_indicators and not account_from_raw:
            print("No account/email indicators found — skipping identity analysis.")
            result = {
                "findings": [],
                "summary": "No identity indicators found in this alert.",
                "overall_risk": "Low",
            }
            if invocation_id:
                await patch_invocation_result(client, invocation_id, result)
            return

        print(f"Found {len(account_indicators)} account indicator(s).")

        accounts_with_context = []
        for ind in account_indicators:
            ind_type = ind.get("type", "account").lower()
            ind_value = ind.get("value", "")

            print(f"  Enriching account: {ind_value}")

            # Fetch Calseta enrichment (Okta/Entra)
            enrichment = await fetch_enrichment(client, ind_type, ind_value)

            # Document what Graph API / Okta would add
            # Heuristic: if value looks like a UPN/email, document both
            graph_calls = document_graph_api_calls(ind_value)
            okta_calls = document_okta_api_calls(ind_value)

            print(
                f"    Would call {len(graph_calls)} Graph API endpoint(s) and "
                f"{len(okta_calls)} Okta API endpoint(s)"
            )

            accounts_with_context.append({
                "type": ind_type,
                "value": ind_value,
                "calseta_enrichment": enrichment,
                "additional_context_available": {
                    "graph_api_endpoints": [c["endpoint"] for c in graph_calls],
                    "okta_api_endpoints": [c["endpoint"] for c in okta_calls],
                    "note": "Implement stubs in agent.py to add live identity provider data",
                },
            })

        # Add raw_payload account context if not already in indicators
        if account_from_raw:
            already_covered = any(
                acc["value"] == account_from_raw for acc in accounts_with_context
            )
            if not already_covered:
                accounts_with_context.append({
                    "type": "account",
                    "value": account_from_raw,
                    "source": "raw_payload",
                    "calseta_enrichment": None,
                    "additional_context_available": {
                        "note": "Extracted from raw_payload — enrich via /v1/enrichments/account/{value}",
                    },
                })

        # LLM assessment
        print("Assessing account compromise risk with LLM...")
        assessment = assess_account_risk(system_prompt, alert, accounts_with_context)

        print(f"Overall identity risk: {assessment['overall_risk']}")

        result = {
            "findings": [
                {
                    "type": "identity_risk_assessment",
                    "overall_risk": assessment["overall_risk"],
                    "accounts_assessed": len(accounts_with_context),
                    "assessment": assessment["assessment"],
                    "recommended_actions": assessment["recommended_actions"],
                }
            ],
            "summary": (
                f"Identity risk assessment for {len(accounts_with_context)} account(s). "
                f"Overall risk: {assessment['overall_risk']}."
            ),
        }

        if invocation_id:
            await patch_invocation_result(client, invocation_id, result)
        else:
            print("\n" + "=" * 60)
            print(assessment["assessment"])
            print("=" * 60)

        print("Identity analysis complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Identity Agent — account compromise risk assessment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent.py --mode queue
  python agent.py --mode invocation --invocation-id <uuid>
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["queue", "invocation"],
        default="queue",
        help="Run mode",
    )
    parser.add_argument(
        "--invocation-id",
        help="Invocation UUID (required for --mode invocation)",
    )
    args = parser.parse_args()

    validate_env()
    system_prompt = load_system_prompt()

    if args.mode == "invocation":
        if not args.invocation_id:
            print("ERROR: --invocation-id is required for --mode invocation", file=sys.stderr)
            sys.exit(1)
        async with httpx.AsyncClient(timeout=30.0) as client:
            invocation = await fetch_invocation(client, args.invocation_id)
        alert_uuid = invocation.get("alert_uuid") or invocation.get("context", {}).get("alert_uuid")
        if not alert_uuid:
            print(f"ERROR: No alert_uuid in invocation {args.invocation_id}", file=sys.stderr)
            sys.exit(1)
        await run_identity_agent(alert_uuid, args.invocation_id, system_prompt)

    elif args.mode == "queue":
        async with httpx.AsyncClient(timeout=30.0) as client:
            queue_item = await checkout_alert_from_queue(client)
        if queue_item is None:
            sys.exit(0)
        alert_uuid = queue_item.get("alert_uuid") or queue_item.get("uuid")
        if not alert_uuid:
            print(f"ERROR: No alert UUID in queue item: {queue_item}", file=sys.stderr)
            sys.exit(1)
        await run_identity_agent(alert_uuid, invocation_id=None, system_prompt=system_prompt)


if __name__ == "__main__":
    asyncio.run(main())
