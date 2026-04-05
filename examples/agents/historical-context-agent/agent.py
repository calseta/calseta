#!/usr/bin/env python3
"""
Historical Context Agent — Calseta Phase 7 Reference Implementation

Retrieves historical alert context using only the Calseta REST API.
Identifies recurrence patterns and surfaces prior investigation verdicts.

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

# How many prior alerts to fetch per indicator
PRIOR_ALERTS_PAGE_SIZE = 10


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


async def search_alerts_by_indicator(
    client: httpx.AsyncClient,
    indicator_value: str,
    exclude_uuid: str,
) -> list[dict]:
    """
    Search for prior alerts containing this indicator value.
    Excludes the current alert from results.
    """
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/alerts",
        headers=HEADERS,
        params={
            "indicator": indicator_value,
            "page_size": PRIOR_ALERTS_PAGE_SIZE,
            "page": 1,
        },
    )
    if resp.status_code != 200:
        print(
            f"WARNING: Alert search failed for indicator={indicator_value}: {resp.status_code}",
            file=sys.stderr,
        )
        return []
    all_results = resp.json().get("data", [])
    # Exclude the current alert
    return [a for a in all_results if a.get("uuid") != exclude_uuid]


async def search_alerts_by_query(
    client: httpx.AsyncClient,
    query: str,
    exclude_uuid: str,
) -> list[dict]:
    """Search alerts by free-text query (account name, hostname, etc.)."""
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/alerts",
        headers=HEADERS,
        params={
            "q": query,
            "page_size": PRIOR_ALERTS_PAGE_SIZE,
            "page": 1,
        },
    )
    if resp.status_code != 200:
        print(
            f"WARNING: Alert search failed for q={query}: {resp.status_code}",
            file=sys.stderr,
        )
        return []
    all_results = resp.json().get("data", [])
    return [a for a in all_results if a.get("uuid") != exclude_uuid]


async def fetch_alert_findings(
    client: httpx.AsyncClient,
    alert_uuid: str,
) -> list[dict]:
    """Fetch prior investigation findings for an alert."""
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/alerts/{alert_uuid}/findings",
        headers=HEADERS,
    )
    if resp.status_code == 200:
        return resp.json().get("data", [])
    if resp.status_code == 404:
        return []
    print(
        f"WARNING: Failed to fetch findings for {alert_uuid}: {resp.status_code}",
        file=sys.stderr,
    )
    return []


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
# History collection
# ---------------------------------------------------------------------------

async def collect_history(
    client: httpx.AsyncClient,
    alert: dict,
) -> dict:
    """
    Collect historical context from Calseta for this alert.
    Queries by indicator values and account/hostname.

    Returns structured history dict for LLM consumption.
    """
    alert_uuid = alert["uuid"]
    indicators = alert.get("indicators", [])
    raw = alert.get("raw_payload", {})

    indicator_history = []
    seen_prior_alert_uuids: set[str] = set()
    all_prior_findings = []

    # Search by each indicator value
    for ind in indicators:
        ind_value = ind.get("value", "")
        ind_type = ind.get("type", "")
        if not ind_value:
            continue

        print(f"  Searching history for {ind_type}: {ind_value}")
        prior_alerts = await search_alerts_by_indicator(client, ind_value, alert_uuid)
        print(f"    Found {len(prior_alerts)} prior alert(s)")

        # Fetch findings for each prior alert
        findings_for_indicator = []
        for prior_alert in prior_alerts:
            prior_uuid = prior_alert.get("uuid", "")
            if prior_uuid in seen_prior_alert_uuids:
                continue
            seen_prior_alert_uuids.add(prior_uuid)
            findings = await fetch_alert_findings(client, prior_uuid)
            if findings:
                finding_summary = {
                    "alert_uuid": prior_uuid,
                    "alert_title": prior_alert.get("title", ""),
                    "alert_severity": prior_alert.get("severity", ""),
                    "alert_occurred_at": prior_alert.get("occurred_at", ""),
                    "findings": [
                        {
                            "content_excerpt": f.get("content", "")[:300],
                            "severity_assessment": f.get("severity_assessment", ""),
                            "created_at": f.get("created_at", ""),
                        }
                        for f in findings
                    ],
                }
                findings_for_indicator.append(finding_summary)
                all_prior_findings.extend(findings)

        indicator_history.append({
            "indicator_type": ind_type,
            "indicator_value": ind_value,
            "prior_alert_count": len(prior_alerts),
            "prior_alerts": [
                {
                    "uuid": a.get("uuid", ""),
                    "title": a.get("title", ""),
                    "severity": a.get("severity", ""),
                    "status": a.get("status", ""),
                    "occurred_at": a.get("occurred_at", ""),
                    "source_name": a.get("source_name", ""),
                }
                for a in prior_alerts
            ],
            "prior_findings": findings_for_indicator,
        })

    # Also search by account from raw_payload
    account_query = (
        raw.get("user")
        or raw.get("account")
        or raw.get("upn")
        or raw.get("username")
    )
    account_history = None
    if account_query:
        print(f"  Searching history for account: {account_query}")
        prior_by_account = await search_alerts_by_query(client, account_query, alert_uuid)
        print(f"    Found {len(prior_by_account)} prior alert(s) for account")
        account_history = {
            "query": account_query,
            "prior_alert_count": len(prior_by_account),
            "prior_alerts": [
                {
                    "uuid": a.get("uuid", ""),
                    "title": a.get("title", ""),
                    "severity": a.get("severity", ""),
                    "occurred_at": a.get("occurred_at", ""),
                }
                for a in prior_by_account
            ],
        }

    total_prior = len(seen_prior_alert_uuids)
    total_findings = len(all_prior_findings)
    print(f"  Total prior alerts found: {total_prior}, with {total_findings} finding(s)")

    return {
        "indicator_history": indicator_history,
        "account_history": account_history,
        "total_prior_alerts": total_prior,
        "total_prior_findings": total_findings,
    }


# ---------------------------------------------------------------------------
# LLM analysis
# ---------------------------------------------------------------------------

def analyze_history(
    system_prompt: str,
    alert: dict,
    history: dict,
) -> dict:
    """Call the LLM to identify patterns and produce a historical context summary."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = f"""
## Current Alert

UUID: {alert.get('uuid', 'Unknown')}
Title: {alert.get('title', 'Unknown')}
Severity: {alert.get('severity', 'Unknown')}
Source: {alert.get('source_name', 'Unknown')}
Occurred: {alert.get('occurred_at', 'Unknown')}
Detection Rule: {alert.get('detection_rule_name') or alert.get('detection_rule_uuid') or 'Unknown'}

## Historical Context Retrieved

```json
{json.dumps(history, indent=2)}
```

Please analyze this historical data and provide your historical context assessment following your output format. Focus on:
1. Whether the same indicators have appeared before and what verdicts were reached
2. Whether there is a concerning recurrence pattern
3. What weight the lead investigator should give to historical context when forming the final verdict
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = message.content[0].text

    # Determine pattern type from response
    pattern = "Unknown"
    for p in ("Chronic Noise", "Escalating Activity", "First Occurrence", "Sporadic", "Burst"):
        if p.lower() in response_text.lower():
            pattern = p
            break

    # Determine confidence modifier
    confidence_modifier = "Neutral"
    if "increases confidence" in response_text.lower():
        confidence_modifier = "Increases confidence in TP"
    elif "decreases confidence" in response_text.lower():
        confidence_modifier = "Decreases confidence in TP"

    return {
        "analysis": response_text,
        "recurrence_pattern": pattern,
        "confidence_modifier": confidence_modifier,
        "prior_alert_count": history["total_prior_alerts"],
        "prior_findings_count": history["total_prior_findings"],
    }


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

async def run_historical_context_agent(
    alert_uuid: str,
    invocation_id: str | None,
    system_prompt: str,
) -> None:
    async with httpx.AsyncClient(timeout=60.0) as client:
        print(f"Fetching alert {alert_uuid}...")
        alert = await fetch_alert(client, alert_uuid)
        print(f"Alert: {alert.get('title', 'Untitled')} [{alert.get('severity', 'Unknown')}]")

        print("Collecting historical context from Calseta...")
        history = await collect_history(client, alert)

        print("Analyzing patterns with LLM...")
        analysis = analyze_history(system_prompt, alert, history)

        print(f"Pattern: {analysis['recurrence_pattern']} | Modifier: {analysis['confidence_modifier']}")

        result = {
            "findings": [
                {
                    "type": "historical_context",
                    "recurrence_pattern": analysis["recurrence_pattern"],
                    "confidence_modifier": analysis["confidence_modifier"],
                    "prior_alert_count": analysis["prior_alert_count"],
                    "prior_findings_count": analysis["prior_findings_count"],
                    "analysis": analysis["analysis"],
                }
            ],
            "summary": (
                f"Historical context: {analysis['prior_alert_count']} prior alert(s), "
                f"{analysis['prior_findings_count']} prior finding(s). "
                f"Pattern: {analysis['recurrence_pattern']}. "
                f"Confidence modifier: {analysis['confidence_modifier']}."
            ),
        }

        if invocation_id:
            await patch_invocation_result(client, invocation_id, result)
        else:
            print("\n" + "=" * 60)
            print(analysis["analysis"])
            print("=" * 60)

        print("Historical context analysis complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Historical Context Agent — alert recurrence and prior verdict analysis",
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
        await run_historical_context_agent(alert_uuid, args.invocation_id, system_prompt)

    elif args.mode == "queue":
        async with httpx.AsyncClient(timeout=30.0) as client:
            queue_item = await checkout_alert_from_queue(client)
        if queue_item is None:
            sys.exit(0)
        alert_uuid = queue_item.get("alert_uuid") or queue_item.get("uuid")
        if not alert_uuid:
            print(f"ERROR: No alert UUID in queue item: {queue_item}", file=sys.stderr)
            sys.exit(1)
        await run_historical_context_agent(alert_uuid, invocation_id=None, system_prompt=system_prompt)


if __name__ == "__main__":
    asyncio.run(main())
