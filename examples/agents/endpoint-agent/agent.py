#!/usr/bin/env python3
"""
Endpoint Agent — Calseta Phase 7 Reference Implementation

Investigates endpoint artifacts: host context, process trees, file hashes,
and determines whether host isolation should be proposed.

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

HASH_INDICATOR_TYPES = {"hash_md5", "hash_sha1", "hash_sha256"}

# Raw payload keys that indicate endpoint context
ENDPOINT_CONTEXT_KEYS = {
    "host", "hostname", "computer_name", "device_name",
    "process", "process_name", "process_id", "parent_process",
    "command_line", "file_hash", "file_path", "file_name",
}


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
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/enrichments/{indicator_type}/{indicator_value}",
        headers=HEADERS,
    )
    if resp.status_code == 200:
        return resp.json().get("data")
    if resp.status_code == 404:
        return None
    print(
        f"WARNING: Enrichment failed for {indicator_type}/{indicator_value}: {resp.status_code}",
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
# EDR API stub documentation
# ---------------------------------------------------------------------------

def document_edr_api_calls(hostname: str) -> list[dict]:
    """
    Documents EDR API calls that would provide additional endpoint context.
    These are stubs — actual calls require EDR API keys and are not implemented here.
    """
    return [
        {
            "source": "CrowdStrike Falcon",
            "endpoint": f"GET https://api.crowdstrike.com/devices/queries/devices/v1?filter=hostname:'{hostname}'",
            "auth": "Bearer $CS_ACCESS_TOKEN (OAuth2: clientId + clientSecret)",
            "returns": "device_id, status, policies, agent_version, platform_name",
            # TODO: implement API call
            # First obtain OAuth token:
            # resp = await http_client.post(
            #     "https://api.crowdstrike.com/oauth2/token",
            #     data={
            #         "client_id": os.environ["CS_CLIENT_ID"],
            #         "client_secret": os.environ["CS_CLIENT_SECRET"]
            #     }
            # )
            # token = resp.json()["access_token"]
            # Then query for device:
            # resp = await http_client.get(
            #     "https://api.crowdstrike.com/devices/queries/devices/v1",
            #     headers={"Authorization": f"Bearer {token}"},
            #     params={"filter": f"hostname:'{hostname}'"}
            # )
        },
        {
            "source": "CrowdStrike Falcon — Process Execution Events",
            "endpoint": "GET https://api.crowdstrike.com/incidents/queries/behaviors/v1 (filtered by device_id)",
            "auth": "Bearer $CS_ACCESS_TOKEN",
            "returns": "tactic, technique, parent_details, cmdline, filename, filepath",
            # TODO: implement API call
            # resp = await http_client.get(
            #     "https://api.crowdstrike.com/incidents/queries/behaviors/v1",
            #     headers={"Authorization": f"Bearer {token}"},
            #     params={"filter": f"device_id:'{device_id}'"}
            # )
        },
        {
            "source": "Microsoft Defender for Endpoint",
            "endpoint": f"GET https://api.securitycenter.microsoft.com/api/machines?$filter=computerDnsName eq '{hostname}'",
            "auth": "Bearer $MDE_ACCESS_TOKEN (app: WindowsDefenderATP — Machine.Read.All)",
            "returns": "id, healthStatus, riskScore, exposureLevel, lastSeen, osPlatform",
            # TODO: implement API call
            # Similar MSAL auth pattern as identity-agent Graph API calls
            # app = msal.ConfidentialClientApplication(
            #     client_id=os.environ["MDE_CLIENT_ID"],
            #     authority=f"https://login.microsoftonline.com/{os.environ['ENTRA_TENANT_ID']}",
            #     client_credential=os.environ["MDE_CLIENT_SECRET"],
            # )
            # token = app.acquire_token_for_client(
            #     scopes=["https://api.securitycenter.microsoft.com/.default"]
            # )
        },
        {
            "source": "SentinelOne",
            "endpoint": f"GET https://$S1_TENANT.sentinelone.net/web/api/v2.1/agents?computerName={hostname}",
            "auth": "Header: Authorization: ApiToken $S1_API_TOKEN",
            "returns": "id, isActive, threatStatus, networkStatus, computerName, osName, agentVersion",
            # TODO: implement API call
            # resp = await http_client.get(
            #     f"https://{os.environ['S1_TENANT']}.sentinelone.net/web/api/v2.1/agents",
            #     headers={"Authorization": f"ApiToken {os.environ['S1_API_TOKEN']}"},
            #     params={"computerName": hostname}
            # )
        },
    ]


# ---------------------------------------------------------------------------
# Context extraction
# ---------------------------------------------------------------------------

def extract_endpoint_context(alert: dict) -> dict:
    """Extract all endpoint-relevant context from the alert."""
    raw = alert.get("raw_payload", {})
    indicators = alert.get("indicators", [])

    # Hostname extraction
    hostname = (
        alert.get("source_hostname")
        or raw.get("host")
        or raw.get("hostname")
        or raw.get("computer_name")
        or raw.get("device_name")
        or ""
    )

    # Process context
    process_name = raw.get("process_name") or raw.get("process") or ""
    parent_process = raw.get("parent_process") or raw.get("parent_process_name") or ""
    command_line = raw.get("command_line") or raw.get("cmdline") or ""
    process_id = raw.get("process_id") or raw.get("pid") or ""

    # File context
    file_path = raw.get("file_path") or raw.get("file_name") or ""
    file_hash_raw = raw.get("file_hash") or ""

    # Hash indicators from indicator list
    hash_indicators = [
        ind for ind in indicators
        if ind.get("type", "").lower() in HASH_INDICATOR_TYPES
    ]

    # Extract raw_payload keys that are endpoint-relevant
    endpoint_raw_fields = {
        k: v for k, v in raw.items()
        if k.lower() in ENDPOINT_CONTEXT_KEYS
    }

    return {
        "hostname": hostname,
        "process_name": process_name,
        "parent_process": parent_process,
        "command_line": command_line,
        "process_id": process_id,
        "file_path": file_path,
        "file_hash_from_raw": file_hash_raw,
        "hash_indicators": hash_indicators,
        "endpoint_raw_fields": endpoint_raw_fields,
    }


# ---------------------------------------------------------------------------
# LLM assessment
# ---------------------------------------------------------------------------

def assess_endpoint_compromise(
    system_prompt: str,
    alert: dict,
    endpoint_context: dict,
    hash_enrichments: dict,
) -> dict:
    """Call the LLM to assess endpoint compromise and isolation need."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = f"""
## Alert Context

Title: {alert.get('title', 'Unknown')}
Severity: {alert.get('severity', 'Unknown')}
Source: {alert.get('source_name', 'Unknown')}
Occurred: {alert.get('occurred_at', 'Unknown')}
Description: {alert.get('description', 'No description')}

## Endpoint Context Extracted from Alert

```json
{json.dumps(endpoint_context, indent=2)}
```

## File Hash Enrichment Results

```json
{json.dumps(hash_enrichments, indent=2)}
```

Please analyze the endpoint artifacts for compromise indicators. Note any suspicious
process lineage, LOLBin usage, encoded command lines, or persistence patterns you
can identify from the available data. For each identified artifact, reference the
relevant MITRE ATT&CK technique where applicable.

Provide a clear recommendation on whether host isolation should be proposed.
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = message.content[0].text

    # Determine isolation recommendation
    isolation_recommended = False
    lower_response = response_text.lower()
    if "isolation recommended: yes" in lower_response or "recommend isolation" in lower_response:
        isolation_recommended = True

    # Determine compromise assessment
    compromise_level = "Possible"
    for level in ("confirmed", "likely", "possible", "clean"):
        if f"compromise assessment: {level}" in lower_response:
            compromise_level = level.capitalize()
            break

    return {
        "assessment": response_text,
        "isolation_recommended": isolation_recommended,
        "compromise_level": compromise_level,
    }


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

async def run_endpoint_agent(
    alert_uuid: str,
    invocation_id: str | None,
    system_prompt: str,
) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Fetching alert {alert_uuid}...")
        alert = await fetch_alert(client, alert_uuid)
        print(f"Alert: {alert.get('title', 'Untitled')} [{alert.get('severity', 'Unknown')}]")

        # Extract endpoint context
        endpoint_context = extract_endpoint_context(alert)
        hostname = endpoint_context["hostname"]
        hash_indicators = endpoint_context["hash_indicators"]

        has_endpoint_context = bool(
            hostname
            or endpoint_context["process_name"]
            or endpoint_context["command_line"]
            or hash_indicators
        )

        if not has_endpoint_context:
            print("No endpoint artifacts found in this alert.")
            result = {
                "findings": [],
                "summary": "No endpoint artifacts found in this alert.",
                "isolation_recommended": False,
                "compromise_level": "Unknown",
            }
            if invocation_id:
                await patch_invocation_result(client, invocation_id, result)
            return

        print(f"Hostname: {hostname or 'unknown'}")
        print(f"Process: {endpoint_context['process_name'] or 'unknown'}")
        print(f"Hash indicators: {len(hash_indicators)}")

        # Enrich hash indicators
        hash_enrichments = {}
        for ind in hash_indicators:
            ind_type = ind.get("type", "").lower()
            ind_value = ind.get("value", "")
            print(f"  Enriching hash: {ind_value[:16]}...")
            enrichment = await fetch_enrichment(client, ind_type, ind_value)
            hash_enrichments[ind_value] = {
                "type": ind_type,
                "calseta_malice": ind.get("malice", "Pending"),
                "enrichment": enrichment,
            }

        # Document EDR API calls for this host
        if hostname:
            edr_calls = document_edr_api_calls(hostname)
            print(
                f"Would call {len(edr_calls)} EDR API(s) for host {hostname}: "
                + ", ".join(c["source"] for c in edr_calls)
            )
            endpoint_context["edr_apis_available"] = [c["source"] for c in edr_calls]
            endpoint_context["edr_note"] = "Implement stubs in agent.py to add live EDR telemetry"

        # LLM assessment
        print("Assessing endpoint compromise with LLM...")
        assessment = assess_endpoint_compromise(
            system_prompt, alert, endpoint_context, hash_enrichments
        )

        print(f"Compromise level: {assessment['compromise_level']}")
        print(f"Isolation recommended: {assessment['isolation_recommended']}")

        result = {
            "findings": [
                {
                    "type": "endpoint_assessment",
                    "compromise_level": assessment["compromise_level"],
                    "isolation_recommended": assessment["isolation_recommended"],
                    "hostname": hostname,
                    "hashes_assessed": len(hash_enrichments),
                    "assessment": assessment["assessment"],
                }
            ],
            "summary": (
                f"Endpoint assessment for host '{hostname or 'unknown'}'. "
                f"Compromise: {assessment['compromise_level']}. "
                f"Isolation recommended: {assessment['isolation_recommended']}."
            ),
        }

        if invocation_id:
            await patch_invocation_result(client, invocation_id, result)
        else:
            print("\n" + "=" * 60)
            print(assessment["assessment"])
            print("=" * 60)

        print("Endpoint analysis complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Endpoint Agent — process tree, hash, and host compromise assessment",
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
        await run_endpoint_agent(alert_uuid, args.invocation_id, system_prompt)

    elif args.mode == "queue":
        async with httpx.AsyncClient(timeout=30.0) as client:
            queue_item = await checkout_alert_from_queue(client)
        if queue_item is None:
            sys.exit(0)
        alert_uuid = queue_item.get("alert_uuid") or queue_item.get("uuid")
        if not alert_uuid:
            print(f"ERROR: No alert UUID in queue item: {queue_item}", file=sys.stderr)
            sys.exit(1)
        await run_endpoint_agent(alert_uuid, invocation_id=None, system_prompt=system_prompt)


if __name__ == "__main__":
    asyncio.run(main())
