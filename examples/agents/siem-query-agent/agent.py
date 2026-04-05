#!/usr/bin/env python3
"""
SIEM Query Agent — Calseta Phase 7 Reference Implementation

Generates SIEM queries (KQL/SPL/EQL) based on alert context to help analysts
find related events and build investigation timelines.

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

# Map from Calseta source_name to SIEM query language
SOURCE_TO_QUERY_LANG = {
    "sentinel": "KQL",
    "microsoft_sentinel": "KQL",
    "splunk": "SPL",
    "elastic": "EQL",
    "elastic_security": "EQL",
    "generic": "KQL",  # default to KQL for unknown sources
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
# Alert context extraction
# ---------------------------------------------------------------------------

def extract_investigation_context(alert: dict) -> dict:
    """
    Extract the context needed for query generation from a Calseta alert.
    Returns a structured dict for LLM consumption.
    """
    source_name = alert.get("source_name", "generic").lower()
    query_language = SOURCE_TO_QUERY_LANG.get(source_name, "KQL")

    indicators = alert.get("indicators", [])
    ips = [ind["value"] for ind in indicators if ind.get("type") == "ip"]
    domains = [ind["value"] for ind in indicators if ind.get("type") == "domain"]
    hashes = [
        ind["value"]
        for ind in indicators
        if ind.get("type") in ("hash_md5", "hash_sha1", "hash_sha256")
    ]
    accounts = [
        ind["value"]
        for ind in indicators
        if ind.get("type") in ("account", "email")
    ]

    return {
        "alert_uuid": alert.get("uuid"),
        "title": alert.get("title"),
        "severity": alert.get("severity"),
        "source_name": source_name,
        "query_language": query_language,
        "occurred_at": alert.get("occurred_at"),
        "description": alert.get("description"),
        "ip_indicators": ips,
        "domain_indicators": domains,
        "hash_indicators": hashes,
        "account_indicators": accounts,
        "raw_payload_keys": list(alert.get("raw_payload", {}).keys()),
    }


# ---------------------------------------------------------------------------
# LLM query generation
# ---------------------------------------------------------------------------

def generate_queries(system_prompt: str, context: dict, task_description: str) -> dict:
    """
    Call the LLM to generate SIEM queries based on the alert context.

    Returns a dict with: queries (list), explanation, findings.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = f"""
## Investigation Task

{task_description}

## Alert Context

```json
{json.dumps(context, indent=2)}
```

Please generate 2-3 {context['query_language']} queries for this alert. For each query:
1. Include a comment line describing what it searches for
2. Make it copy-paste ready with actual indicator values substituted
3. Explain what a positive result would mean for the investigation

Format your response as:

### Query 1: [Description]
```{context['query_language'].lower()}
[query here]
```
**If positive:** [what it means]

### Query 2: [Description]
...

### Summary
[Brief explanation of investigation approach and expected findings]
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = message.content[0].text

    # Extract individual queries for structured result
    import re
    query_pattern = re.compile(
        r'###\s+Query\s+\d+:\s+(.+?)\n```\w*\n(.*?)```',
        re.DOTALL,
    )
    queries = []
    for match in query_pattern.finditer(response_text):
        queries.append({
            "description": match.group(1).strip(),
            "query": match.group(2).strip(),
            "language": context["query_language"],
        })

    return {
        "queries": queries,
        "full_response": response_text,
        "query_language": context["query_language"],
        "alert_uuid": context["alert_uuid"],
        "indicators_analyzed": {
            "ips": context["ip_indicators"],
            "domains": context["domain_indicators"],
            "hashes": context["hash_indicators"],
            "accounts": context["account_indicators"],
        },
    }


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

async def run_siem_query_agent(
    alert_uuid: str,
    invocation_id: str | None,
    task_description: str,
    system_prompt: str,
) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Fetching alert {alert_uuid}...")
        alert = await fetch_alert(client, alert_uuid)
        print(f"Alert: {alert.get('title', 'Untitled')} | Source: {alert.get('source_name', 'unknown')}")

        context = extract_investigation_context(alert)
        print(f"Query language: {context['query_language']}")
        print(
            f"Indicators: {len(context['ip_indicators'])} IPs, "
            f"{len(context['domain_indicators'])} domains, "
            f"{len(context['hash_indicators'])} hashes, "
            f"{len(context['account_indicators'])} accounts"
        )

        print("Generating SIEM queries...")
        result = generate_queries(system_prompt, context, task_description)

        # Print generated queries to stdout for human review
        print("\n" + "=" * 60)
        print(f"Generated {len(result['queries'])} {result['query_language']} queries:")
        print("=" * 60)
        for i, q in enumerate(result["queries"], 1):
            print(f"\nQuery {i}: {q['description']}")
            print(f"Language: {q['language']}")
        print("=" * 60 + "\n")

        # Post result
        if invocation_id:
            await patch_invocation_result(
                client,
                invocation_id,
                result={
                    "findings": [
                        {
                            "type": "siem_queries",
                            "query_language": result["query_language"],
                            "queries": result["queries"],
                            "summary": result["full_response"][:1000],
                        }
                    ],
                    "summary": f"Generated {len(result['queries'])} {result['query_language']} queries for investigation timeline",
                },
            )
        else:
            # Standalone queue mode — print full output
            print(result["full_response"])

        print("SIEM query generation complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="SIEM Query Agent — generates KQL/SPL/EQL investigation queries",
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
        task = invocation.get("task", "Generate SIEM queries to build an investigation timeline.")
        await run_siem_query_agent(alert_uuid, args.invocation_id, task, system_prompt)

    elif args.mode == "queue":
        async with httpx.AsyncClient(timeout=30.0) as client:
            queue_item = await checkout_alert_from_queue(client)
        if queue_item is None:
            sys.exit(0)
        alert_uuid = queue_item.get("alert_uuid") or queue_item.get("uuid")
        if not alert_uuid:
            print(f"ERROR: No alert UUID in queue item: {queue_item}", file=sys.stderr)
            sys.exit(1)
        await run_siem_query_agent(
            alert_uuid,
            invocation_id=None,
            task="Generate SIEM queries to build an investigation timeline.",
            system_prompt=system_prompt,
        )


if __name__ == "__main__":
    asyncio.run(main())
