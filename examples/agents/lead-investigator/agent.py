#!/usr/bin/env python3
"""
Lead Investigator Agent — Calseta Phase 7 Reference Implementation

Orchestrates specialist sub-agents in parallel to produce a comprehensive
investigation finding for a security alert.

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
import time
from pathlib import Path

import anthropic
import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CALSETA_API_URL = os.environ.get("CALSETA_API_URL", "http://localhost:8000")
CALSETA_AGENT_KEY = os.environ.get("CALSETA_AGENT_KEY", "")  # cak_* key
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Sub-agent UUIDs (registered in Calseta control plane)
THREAT_INTEL_AGENT_UUID = os.environ.get("THREAT_INTEL_AGENT_UUID", "")
IDENTITY_AGENT_UUID = os.environ.get("IDENTITY_AGENT_UUID", "")
ENDPOINT_AGENT_UUID = os.environ.get("ENDPOINT_AGENT_UUID", "")
HISTORICAL_CONTEXT_AGENT_UUID = os.environ.get("HISTORICAL_CONTEXT_AGENT_UUID", "")

HEADERS = {"Authorization": f"Bearer {CALSETA_AGENT_KEY}"}

SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.md"

# Timeout for polling each sub-agent invocation
SUB_AGENT_POLL_TIMEOUT_SECONDS = 30
SUB_AGENT_POLL_INTERVAL_SECONDS = 2


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
    """Fetch full alert detail including indicators and enrichment."""
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/alerts/{alert_uuid}",
        headers=HEADERS,
    )
    if resp.status_code != 200:
        print(f"ERROR: Failed to fetch alert {alert_uuid}: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["data"]


async def checkout_alert_from_queue(client: httpx.AsyncClient) -> dict | None:
    """Poll the alert queue and check out the next alert."""
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/queue",
        headers=HEADERS,
        params={"page_size": 1},
    )
    if resp.status_code != 200:
        print(f"ERROR: Failed to poll queue: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    data = resp.json()
    items = data.get("data", [])
    if not items:
        print("Queue is empty — no alerts to investigate.")
        return None
    item = items[0]
    # Check out the alert
    alert_uuid = item.get("alert_uuid") or item.get("uuid")
    if not alert_uuid:
        print(f"ERROR: Queue item missing alert UUID: {item}", file=sys.stderr)
        sys.exit(1)
    # Mark as checked out if the API supports it
    checkout_resp = await client.post(
        f"{CALSETA_API_URL}/v1/queue/{alert_uuid}/checkout",
        headers=HEADERS,
    )
    if checkout_resp.status_code not in (200, 204, 404):
        # 404 = no checkout endpoint; proceed anyway
        print(f"WARNING: Queue checkout returned {checkout_resp.status_code}", file=sys.stderr)
    return item


async def fetch_invocation(client: httpx.AsyncClient, invocation_id: str) -> dict:
    """Fetch a delegated invocation by ID."""
    resp = await client.get(
        f"{CALSETA_API_URL}/v1/invocations/{invocation_id}",
        headers=HEADERS,
    )
    if resp.status_code != 200:
        print(f"ERROR: Failed to fetch invocation {invocation_id}: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["data"]


async def delegate_parallel(
    client: httpx.AsyncClient,
    alert_uuid: str,
    specialist_agents: list[dict],
) -> list[str]:
    """
    Delegate to multiple specialists in parallel via POST /v1/invocations/parallel.

    Returns list of invocation UUIDs.
    """
    payload = {
        "alert_uuid": alert_uuid,
        "agents": specialist_agents,
        "task": "Investigate this alert and provide specialist findings.",
    }
    resp = await client.post(
        f"{CALSETA_API_URL}/v1/invocations/parallel",
        headers=HEADERS,
        json=payload,
    )
    if resp.status_code not in (200, 201, 202):
        print(
            f"ERROR: Failed to delegate parallel invocations: {resp.status_code} {resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    result = resp.json()
    # Accept both {"data": {"invocation_ids": [...]}} and {"invocation_ids": [...]}
    data = result.get("data", result)
    ids = data.get("invocation_ids", [])
    if not ids:
        print("WARNING: Parallel delegation returned no invocation IDs.", file=sys.stderr)
    return ids


async def poll_invocation(client: httpx.AsyncClient, invocation_id: str) -> dict | None:
    """
    Poll a single invocation until completed or timeout.

    Returns the invocation result dict, or None on timeout/failure.
    """
    deadline = time.monotonic() + SUB_AGENT_POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        resp = await client.get(
            f"{CALSETA_API_URL}/v1/invocations/{invocation_id}/poll",
            headers=HEADERS,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", resp.json())
            status = data.get("status", "")
            if status == "completed":
                return data.get("result", data)
            if status in ("failed", "cancelled", "expired"):
                print(
                    f"WARNING: Invocation {invocation_id} ended with status={status}",
                    file=sys.stderr,
                )
                return None
        await asyncio.sleep(SUB_AGENT_POLL_INTERVAL_SECONDS)
    print(
        f"WARNING: Invocation {invocation_id} timed out after {SUB_AGENT_POLL_TIMEOUT_SECONDS}s",
        file=sys.stderr,
    )
    return None


async def post_finding(
    client: httpx.AsyncClient,
    alert_uuid: str,
    content: str,
    severity_assessment: str,
    recommended_actions: list[str],
) -> None:
    """Post a final investigation finding to the alert."""
    resp = await client.post(
        f"{CALSETA_API_URL}/v1/alerts/{alert_uuid}/findings",
        headers=HEADERS,
        json={
            "content": content,
            "severity_assessment": severity_assessment,
            "recommended_actions": recommended_actions,
        },
    )
    if resp.status_code not in (200, 201):
        print(
            f"ERROR: Failed to post finding for alert {alert_uuid}: {resp.status_code} {resp.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Finding posted for alert {alert_uuid}.")


async def post_action(
    client: httpx.AsyncClient,
    alert_uuid: str,
    action_type: str,
    target: str,
    reason: str,
) -> None:
    """Propose a containment or remediation action."""
    resp = await client.post(
        f"{CALSETA_API_URL}/v1/actions",
        headers=HEADERS,
        json={
            "alert_uuid": alert_uuid,
            "action_type": action_type,
            "target": target,
            "reason": reason,
        },
    )
    if resp.status_code not in (200, 201, 202):
        print(
            f"WARNING: Failed to post action {action_type} for {alert_uuid}: {resp.status_code} {resp.text}",
            file=sys.stderr,
        )
    else:
        print(f"Action proposed: {action_type} → {target}")


async def patch_invocation_result(
    client: httpx.AsyncClient,
    invocation_id: str,
    result: dict,
) -> None:
    """Mark an invocation as completed with the given result."""
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
# Specialist selection (rule-based, no LLM)
# ---------------------------------------------------------------------------

def select_specialists(alert: dict) -> list[dict]:
    """
    Select which specialist agents to invoke based on alert indicators.
    Rule-based — no LLM tokens consumed here.

    Returns a list of agent dicts: {"agent_uuid": "...", "task": "..."}
    """
    specialists = []
    indicators = alert.get("indicators", [])

    indicator_types = {ind.get("type", "").lower() for ind in indicators}

    # Network/file indicators → threat intel
    threat_intel_types = {"ip", "domain", "hash_md5", "hash_sha1", "hash_sha256", "url"}
    if indicator_types & threat_intel_types:
        if THREAT_INTEL_AGENT_UUID:
            specialists.append({
                "agent_uuid": THREAT_INTEL_AGENT_UUID,
                "task": "Analyze threat intelligence for IP, domain, hash, and URL indicators in this alert.",
            })
        else:
            print("WARNING: THREAT_INTEL_AGENT_UUID not set — skipping threat intel specialist.", file=sys.stderr)

    # Account indicators → identity
    if "account" in indicator_types or "email" in indicator_types:
        if IDENTITY_AGENT_UUID:
            specialists.append({
                "agent_uuid": IDENTITY_AGENT_UUID,
                "task": "Assess account compromise risk based on identity indicators in this alert.",
            })
        else:
            print("WARNING: IDENTITY_AGENT_UUID not set — skipping identity specialist.", file=sys.stderr)

    # Host/process context → endpoint
    raw_payload = alert.get("raw_payload", {})
    has_host = bool(
        alert.get("source_hostname")
        or raw_payload.get("host")
        or raw_payload.get("hostname")
        or raw_payload.get("process")
        or raw_payload.get("process_name")
        or raw_payload.get("file_hash")
    )
    if has_host:
        if ENDPOINT_AGENT_UUID:
            specialists.append({
                "agent_uuid": ENDPOINT_AGENT_UUID,
                "task": "Investigate endpoint artifacts: host, process, and file hash context from this alert.",
            })
        else:
            print("WARNING: ENDPOINT_AGENT_UUID not set — skipping endpoint specialist.", file=sys.stderr)

    # Always invoke historical context
    if HISTORICAL_CONTEXT_AGENT_UUID:
        specialists.append({
            "agent_uuid": HISTORICAL_CONTEXT_AGENT_UUID,
            "task": "Retrieve historical context: prior alerts for these indicators and recurrence patterns.",
        })
    else:
        print("WARNING: HISTORICAL_CONTEXT_AGENT_UUID not set — skipping historical context specialist.", file=sys.stderr)

    return specialists


# ---------------------------------------------------------------------------
# LLM synthesis
# ---------------------------------------------------------------------------

def synthesize_findings(
    system_prompt: str,
    alert: dict,
    specialist_results: list[dict],
) -> dict:
    """
    Call the LLM to synthesize specialist findings into a final verdict.

    Returns a dict with keys: content, severity_assessment, recommended_actions, proposed_actions.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    alert_summary = json.dumps(
        {
            "uuid": alert.get("uuid"),
            "title": alert.get("title"),
            "severity": alert.get("severity"),
            "status": alert.get("status"),
            "source_name": alert.get("source_name"),
            "occurred_at": alert.get("occurred_at"),
            "description": alert.get("description"),
            "indicators": alert.get("indicators", []),
        },
        indent=2,
    )

    specialist_block = ""
    for i, result in enumerate(specialist_results, 1):
        specialist_block += f"\n### Specialist {i} Findings\n"
        specialist_block += json.dumps(result, indent=2)

    user_message = f"""
## Alert Under Investigation

```json
{alert_summary}
```

## Specialist Findings

{specialist_block if specialist_block else "No specialist findings available — proceed with alert data only."}

---

Please provide your investigation verdict following the output format in your system prompt.
Include a "proposed_actions" JSON array at the end in this exact format:
```json
{{
  "proposed_actions": [
    {{"action_type": "block_ip", "target": "<ip>", "reason": "<reason>"}},
    {{"action_type": "revoke_session", "target": "<account>", "reason": "<reason>"}}
  ]
}}
```
If no containment is warranted, set proposed_actions to an empty array.
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = message.content[0].text

    # Extract structured data from LLM response
    severity_assessment = "High"
    for line in response_text.splitlines():
        lower = line.lower()
        if "confidence: high" in lower:
            break
        if "confidence: medium" in lower:
            severity_assessment = "Medium"
            break
        if "confidence: low" in lower:
            severity_assessment = "Low"
            break

    # Extract severity from original alert for severity_assessment field
    alert_severity = alert.get("severity", "High")
    if alert_severity in ("Critical", "High", "Medium", "Low", "Informational"):
        severity_assessment = alert_severity

    # Parse proposed_actions from LLM output
    proposed_actions: list[dict] = []
    try:
        import re
        json_match = re.search(r'```json\s*(\{[^`]+\})\s*```', response_text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group(1))
            proposed_actions = parsed.get("proposed_actions", [])
    except (json.JSONDecodeError, AttributeError):
        pass

    # Build recommended actions list from response
    recommended_actions = []
    in_actions_section = False
    for line in response_text.splitlines():
        if "recommended actions" in line.lower():
            in_actions_section = True
            continue
        if in_actions_section:
            stripped = line.strip()
            if stripped.startswith(("-", "*", "•")) or (stripped and stripped[0].isdigit()):
                action = stripped.lstrip("-*•0123456789. ").strip()
                if action:
                    recommended_actions.append(action)
            elif stripped.startswith("#") and len(stripped) > 2:
                # New section — stop collecting
                in_actions_section = False

    if not recommended_actions:
        recommended_actions = ["Review findings and determine appropriate response."]

    return {
        "content": response_text,
        "severity_assessment": severity_assessment,
        "recommended_actions": recommended_actions[:5],  # top 5
        "proposed_actions": proposed_actions,
    }


# ---------------------------------------------------------------------------
# Main investigation flow
# ---------------------------------------------------------------------------

async def investigate(
    alert_uuid: str,
    invocation_id: str | None,
    system_prompt: str,
) -> None:
    """Full investigation pipeline: fetch → delegate → synthesize → post."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Fetching alert {alert_uuid}...")
        alert = await fetch_alert(client, alert_uuid)
        print(f"Alert: {alert.get('title', 'Untitled')} [{alert.get('severity', 'Unknown')}]")

        # Select specialists (rule-based)
        specialists = select_specialists(alert)
        print(f"Selected {len(specialists)} specialist(s): {[s['agent_uuid'][:8] + '...' for s in specialists]}")

        # Delegate in parallel
        specialist_results: list[dict] = []
        if specialists:
            print("Delegating to specialists in parallel...")
            invocation_ids = await delegate_parallel(client, alert_uuid, specialists)
            print(f"  Dispatched {len(invocation_ids)} invocation(s). Polling for results...")

            # Poll all in parallel
            poll_tasks = [poll_invocation(client, inv_id) for inv_id in invocation_ids]
            results = await asyncio.gather(*poll_tasks)
            specialist_results = [r for r in results if r is not None]
            print(f"  Received {len(specialist_results)}/{len(invocation_ids)} specialist results.")
        else:
            print("No specialists selected — proceeding with alert data only.")

        # LLM synthesis
        print("Synthesizing findings with LLM...")
        synthesis = synthesize_findings(system_prompt, alert, specialist_results)

        # Post finding
        await post_finding(
            client,
            alert_uuid,
            content=synthesis["content"],
            severity_assessment=synthesis["severity_assessment"],
            recommended_actions=synthesis["recommended_actions"],
        )

        # Post any containment actions
        for action in synthesis.get("proposed_actions", []):
            await post_action(
                client,
                alert_uuid,
                action_type=action.get("action_type", "unknown"),
                target=action.get("target", ""),
                reason=action.get("reason", ""),
            )

        # If running as invocation, patch result
        if invocation_id:
            await patch_invocation_result(
                client,
                invocation_id,
                result={
                    "alert_uuid": alert_uuid,
                    "verdict": synthesis["content"][:500],
                    "severity_assessment": synthesis["severity_assessment"],
                    "recommended_actions": synthesis["recommended_actions"],
                    "specialist_results_received": len(specialist_results),
                },
            )

        print("Investigation complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lead Investigator — Calseta orchestrator agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process next alert from queue
  python agent.py --mode queue

  # Handle a delegated invocation
  python agent.py --mode invocation --invocation-id <uuid>
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["queue", "invocation"],
        default="queue",
        help="Run mode: 'queue' polls for next alert, 'invocation' handles a delegated task",
    )
    parser.add_argument(
        "--invocation-id",
        help="Invocation UUID to handle (required for --mode invocation)",
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
            print(f"ERROR: No alert_uuid found in invocation {args.invocation_id}", file=sys.stderr)
            sys.exit(1)
        await investigate(alert_uuid, args.invocation_id, system_prompt)

    elif args.mode == "queue":
        async with httpx.AsyncClient(timeout=30.0) as client:
            queue_item = await checkout_alert_from_queue(client)
        if queue_item is None:
            sys.exit(0)
        alert_uuid = queue_item.get("alert_uuid") or queue_item.get("uuid")
        if not alert_uuid:
            print(f"ERROR: No alert UUID in queue item: {queue_item}", file=sys.stderr)
            sys.exit(1)
        await investigate(alert_uuid, invocation_id=None, system_prompt=system_prompt)


if __name__ == "__main__":
    asyncio.run(main())
