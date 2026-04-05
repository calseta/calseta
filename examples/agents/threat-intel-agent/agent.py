#!/usr/bin/env python3
"""
Threat Intelligence Agent — Calseta Phase 7 Reference Implementation

Analyzes threat intelligence for IP, domain, hash, and URL indicators.
Uses Calseta enrichment results and documents external TI API call patterns.

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

# Indicator types handled by this agent
SUPPORTED_INDICATOR_TYPES = {"ip", "domain", "hash_md5", "hash_sha1", "hash_sha256", "url"}

# Indicator malice values that are already conclusive — skip external enrichment
CONCLUSIVE_MALICE_VALUES = {"Malicious", "Benign"}


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
    """
    Fetch Calseta enrichment for a specific indicator.
    Returns the enrichment data dict or None on failure.
    """
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/enrichments/{indicator_type}/{indicator_value}",
        headers=HEADERS,
    )
    if resp.status_code == 200:
        return resp.json().get("data")
    if resp.status_code == 404:
        return None
    print(
        f"WARNING: Enrichment fetch failed for {indicator_type}/{indicator_value}: "
        f"{resp.status_code}",
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
# External TI API stub documentation
# ---------------------------------------------------------------------------

def document_external_ti_calls(indicator_type: str, indicator_value: str) -> list[dict]:
    """
    Documents which external TI API calls would be made for this indicator type.
    These are stubs — actual HTTP calls require API keys and are not implemented here.

    Returns a list of documented API call patterns.
    """
    calls = []

    if indicator_type == "ip":
        calls.append({
            "source": "VirusTotal",
            "endpoint": f"GET https://www.virustotal.com/api/v3/ip_addresses/{indicator_value}",
            "auth": "Header: x-apikey: $VIRUSTOTAL_API_KEY",
            "returns": "last_analysis_stats, last_analysis_results, reputation, tags",
            # TODO: implement API call
            # import virustotal_python  # pip install virustotal-python
            # async with vt.Client(api_key=os.environ['VIRUSTOTAL_API_KEY']) as client:
            #     result = await client.get_object_async(f'/ip_addresses/{indicator_value}')
        })
        calls.append({
            "source": "AbuseIPDB",
            "endpoint": f"GET https://api.abuseipdb.com/api/v2/check?ipAddress={indicator_value}&maxAgeInDays=90",
            "auth": "Header: Key: $ABUSEIPDB_API_KEY",
            "returns": "abuseConfidenceScore, totalReports, lastReportedAt, usageType, isp, countryCode",
            # TODO: implement API call
            # resp = await http_client.get(
            #     "https://api.abuseipdb.com/api/v2/check",
            #     headers={"Key": os.environ["ABUSEIPDB_API_KEY"], "Accept": "application/json"},
            #     params={"ipAddress": indicator_value, "maxAgeInDays": 90}
            # )
        })
        calls.append({
            "source": "GreyNoise",
            "endpoint": f"GET https://api.greynoise.io/v3/community/{indicator_value}",
            "auth": "Header: key: $GREYNOISE_API_KEY",
            "returns": "classification (benign/malicious/unknown), name, link, last_seen",
            # TODO: implement API call
            # import greynoise  # pip install greynoise
            # client = greynoise.GreyNoise(api_key=os.environ['GREYNOISE_API_KEY'])
            # result = client.ip(indicator_value)
        })
        calls.append({
            "source": "Shodan",
            "endpoint": f"GET https://api.shodan.io/shodan/host/{indicator_value}?key=$SHODAN_API_KEY",
            "auth": "Query param: key=$SHODAN_API_KEY",
            "returns": "open ports, banners, hostnames, org, isp, vulns",
            # TODO: implement API call
            # import shodan  # pip install shodan
            # api = shodan.Shodan(os.environ['SHODAN_API_KEY'])
            # host = api.host(indicator_value)
        })

    elif indicator_type == "domain":
        calls.append({
            "source": "VirusTotal",
            "endpoint": f"GET https://www.virustotal.com/api/v3/domains/{indicator_value}",
            "auth": "Header: x-apikey: $VIRUSTOTAL_API_KEY",
            "returns": "last_analysis_stats, categories, creation_date, last_dns_records",
            # TODO: implement API call (see IP stub above for pattern)
        })
        calls.append({
            "source": "OTX AlienVault",
            "endpoint": f"GET https://otx.alienvault.com/api/v1/indicators/domain/{indicator_value}/general",
            "auth": "Header: X-OTX-API-KEY: $OTX_API_KEY",
            "returns": "pulse_info (count, pulses with MITRE tags), validation",
            # TODO: implement API call
            # resp = await http_client.get(
            #     f"https://otx.alienvault.com/api/v1/indicators/domain/{indicator_value}/general",
            #     headers={"X-OTX-API-KEY": os.environ["OTX_API_KEY"]}
            # )
        })

    elif indicator_type in ("hash_md5", "hash_sha1", "hash_sha256"):
        hash_type = indicator_type.replace("hash_", "")
        calls.append({
            "source": "VirusTotal",
            "endpoint": f"GET https://www.virustotal.com/api/v3/files/{indicator_value}",
            "auth": "Header: x-apikey: $VIRUSTOTAL_API_KEY",
            "returns": "last_analysis_stats, meaningful_name, type_description, magic, tlsh, vhash",
            # TODO: implement API call (see IP stub above for pattern)
        })
        calls.append({
            "source": "MalwareBazaar",
            "endpoint": "POST https://mb-api.abuse.ch/api/v1/ (query_hash)",
            "auth": "No auth required for queries",
            "returns": "query_status, file_type, file_name, tags, signature, vendor_intel",
            # TODO: implement API call
            # resp = await http_client.post(
            #     "https://mb-api.abuse.ch/api/v1/",
            #     data={"query": "get_info", f"{hash_type}_hash": indicator_value}
            # )
        })
        calls.append({
            "source": "OTX AlienVault",
            "endpoint": f"GET https://otx.alienvault.com/api/v1/indicators/file/{indicator_value}/general",
            "auth": "Header: X-OTX-API-KEY: $OTX_API_KEY",
            "returns": "pulse_info, malware_families",
            # TODO: implement API call (see domain stub above for pattern)
        })

    elif indicator_type == "url":
        calls.append({
            "source": "VirusTotal",
            "endpoint": "POST https://www.virustotal.com/api/v3/urls (url=<encoded>)",
            "auth": "Header: x-apikey: $VIRUSTOTAL_API_KEY",
            "returns": "Analysis ID; then GET /v3/analyses/{id} for results",
            # TODO: implement API call
            # First submit URL for scanning, then poll for results
            # resp = await http_client.post(
            #     "https://www.virustotal.com/api/v3/urls",
            #     headers={"x-apikey": os.environ["VIRUSTOTAL_API_KEY"]},
            #     data={"url": indicator_value}
            # )
        })

    return calls


# ---------------------------------------------------------------------------
# LLM assessment
# ---------------------------------------------------------------------------

def assess_indicators(
    system_prompt: str,
    alert: dict,
    indicators_with_enrichment: list[dict],
) -> dict:
    """
    Call the LLM to synthesize enrichment data into a threat intelligence assessment.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    indicators_block = json.dumps(indicators_with_enrichment, indent=2)

    user_message = f"""
## Alert Context

Title: {alert.get('title', 'Unknown')}
Severity: {alert.get('severity', 'Unknown')}
Source: {alert.get('source_name', 'Unknown')}
Occurred: {alert.get('occurred_at', 'Unknown')}

## Indicators and Enrichment Data

```json
{indicators_block}
```

Please assess each indicator following your output format. For any indicator where
Calseta enrichment is unavailable or inconclusive, note what additional external
intelligence sources would contribute (VirusTotal, GreyNoise, Shodan, OTX, etc.)
and what their results would mean.

End with an **Overall Threat Assessment** for this alert.
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = message.content[0].text

    # Determine overall malice from response
    overall_malice = "Pending"
    for verdict in ("Malicious", "Suspicious", "Benign", "Inconclusive"):
        if verdict.lower() in response_text.lower():
            overall_malice = verdict
            break

    return {
        "assessment": response_text,
        "overall_malice": overall_malice,
        "indicators_assessed": len(indicators_with_enrichment),
    }


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

async def run_threat_intel_agent(
    alert_uuid: str,
    invocation_id: str | None,
    system_prompt: str,
) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Fetching alert {alert_uuid}...")
        alert = await fetch_alert(client, alert_uuid)
        print(f"Alert: {alert.get('title', 'Untitled')} [{alert.get('severity', 'Unknown')}]")

        # Filter to threat intel relevant indicators
        all_indicators = alert.get("indicators", [])
        relevant_indicators = [
            ind for ind in all_indicators
            if ind.get("type", "").lower() in SUPPORTED_INDICATOR_TYPES
        ]
        print(f"Found {len(relevant_indicators)} relevant indicator(s) for threat intel analysis.")

        if not relevant_indicators:
            print("No IP/domain/hash/URL indicators found — skipping threat intel analysis.")
            result = {
                "findings": [],
                "summary": "No threat intel indicators found in this alert.",
                "overall_malice": "Pending",
            }
            if invocation_id:
                await patch_invocation_result(client, invocation_id, result)
            return

        # Enrich via Calseta + document external TI calls
        indicators_with_enrichment = []
        for ind in relevant_indicators:
            ind_type = ind.get("type", "").lower()
            ind_value = ind.get("value", "")
            current_malice = ind.get("malice", "Pending")

            print(f"  Processing {ind_type}: {ind_value} (Calseta malice={current_malice})")

            enrichment = None
            if current_malice not in CONCLUSIVE_MALICE_VALUES:
                enrichment = await fetch_enrichment(client, ind_type, ind_value)

            external_ti_calls = []
            if current_malice not in CONCLUSIVE_MALICE_VALUES:
                external_ti_calls = document_external_ti_calls(ind_type, ind_value)
                print(
                    f"    Would call {len(external_ti_calls)} external TI API(s): "
                    + ", ".join(c["source"] for c in external_ti_calls)
                )

            indicators_with_enrichment.append({
                "type": ind_type,
                "value": ind_value,
                "calseta_malice": current_malice,
                "calseta_enrichment": enrichment,
                "external_ti_sources_available": [c["source"] for c in external_ti_calls],
                "note": (
                    "External TI API stubs documented in agent.py — implement to add live data"
                    if external_ti_calls
                    else "Calseta enrichment is conclusive — no external calls needed"
                ),
            })

        # LLM assessment
        print("Synthesizing threat intelligence assessment with LLM...")
        assessment = assess_indicators(system_prompt, alert, indicators_with_enrichment)

        print(f"Overall malice assessment: {assessment['overall_malice']}")

        # Post result
        result = {
            "findings": [
                {
                    "type": "threat_intel_assessment",
                    "overall_malice": assessment["overall_malice"],
                    "indicators_assessed": assessment["indicators_assessed"],
                    "assessment": assessment["assessment"],
                }
            ],
            "summary": (
                f"Threat intel analysis of {assessment['indicators_assessed']} indicator(s). "
                f"Overall malice: {assessment['overall_malice']}."
            ),
        }

        if invocation_id:
            await patch_invocation_result(client, invocation_id, result)
        else:
            print("\n" + "=" * 60)
            print(assessment["assessment"])
            print("=" * 60)

        print("Threat intelligence analysis complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Threat Intelligence Agent — IOC assessment via enrichment and TI sources",
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
        await run_threat_intel_agent(alert_uuid, args.invocation_id, system_prompt)

    elif args.mode == "queue":
        async with httpx.AsyncClient(timeout=30.0) as client:
            queue_item = await checkout_alert_from_queue(client)
        if queue_item is None:
            sys.exit(0)
        alert_uuid = queue_item.get("alert_uuid") or queue_item.get("uuid")
        if not alert_uuid:
            print(f"ERROR: No alert UUID in queue item: {queue_item}", file=sys.stderr)
            sys.exit(1)
        await run_threat_intel_agent(alert_uuid, invocation_id=None, system_prompt=system_prompt)


if __name__ == "__main__":
    asyncio.run(main())
