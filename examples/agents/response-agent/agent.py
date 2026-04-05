#!/usr/bin/env python3
"""
Response Agent — Calseta Phase 7 Reference Implementation

Generates prioritized response actions with confidence scores.
Submits actions with confidence >= 0.85 to the approval gate.

Usage:
    python agent.py --mode queue
    python agent.py --mode invocation --invocation-id <uuid>
    python agent.py --help
"""

import argparse
import asyncio
import json
import os
import re
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

# Actions at or above this confidence are auto-submitted to the approval gate
ACTION_CONFIDENCE_THRESHOLD = float(
    os.environ.get("ACTION_CONFIDENCE_THRESHOLD", "0.85")
)


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


async def fetch_alert_findings(client: httpx.AsyncClient, alert_uuid: str) -> list[dict]:
    """Fetch all investigation findings for this alert."""
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


async def post_action(
    client: httpx.AsyncClient,
    alert_uuid: str,
    action_type: str,
    target: str,
    reason: str,
    confidence: float,
) -> bool:
    """
    Post a response action to Calseta for human-in-the-loop approval.
    Returns True on success.
    """
    resp = await client.post(
        f"{CALSETA_API_URL}/v1/actions",
        headers=HEADERS,
        json={
            "alert_uuid": alert_uuid,
            "action_type": action_type,
            "target": target,
            "reason": reason,
            "confidence": confidence,
        },
    )
    if resp.status_code in (200, 201, 202):
        print(f"  Action submitted: {action_type} → {target} (confidence={confidence:.2f})")
        return True
    print(
        f"  WARNING: Failed to post action {action_type} for {alert_uuid}: "
        f"{resp.status_code} {resp.text}",
        file=sys.stderr,
    )
    return False


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
# LLM response planning
# ---------------------------------------------------------------------------

def generate_response_plan(
    system_prompt: str,
    alert: dict,
    findings: list[dict],
    invocation_context: dict | None,
) -> dict:
    """
    Call the LLM to generate a prioritized action plan.

    Returns a dict with: actions (list), summary, raw_response.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Include synthesized findings from orchestrator if available via invocation context
    orchestrator_findings = ""
    if invocation_context:
        ctx_findings = invocation_context.get("context", {}).get("findings") or invocation_context.get("findings")
        if ctx_findings:
            orchestrator_findings = f"\n## Synthesized Findings from Orchestrator\n\n```json\n{json.dumps(ctx_findings, indent=2)}\n```\n"

    findings_block = ""
    if findings:
        findings_block = f"\n## Investigation Findings\n\n```json\n{json.dumps([{'content': f.get('content', '')[:500], 'severity_assessment': f.get('severity_assessment', ''), 'created_at': f.get('created_at', '')} for f in findings], indent=2)}\n```\n"

    user_message = f"""
## Alert

UUID: {alert.get('uuid', 'Unknown')}
Title: {alert.get('title', 'Unknown')}
Severity: {alert.get('severity', 'Unknown')}
Source: {alert.get('source_name', 'Unknown')}
Occurred: {alert.get('occurred_at', 'Unknown')}
Indicators: {json.dumps([{'type': i.get('type'), 'value': i.get('value'), 'malice': i.get('malice')} for i in alert.get('indicators', [])], indent=2)}
{orchestrator_findings}
{findings_block}

Please generate a prioritized response action plan. Output the JSON array of actions first,
then the Response Plan Summary. Use the exact JSON format specified in your system prompt.

The confidence threshold for auto-submission to the approval gate is {ACTION_CONFIDENCE_THRESHOLD}.
Include ALL recommended actions in the JSON (even below threshold), but flag which ones
meet the auto-submission threshold.
"""

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = message.content[0].text

    # Parse the JSON action array from the response
    actions = []
    try:
        json_match = re.search(r'```json\s*(\[.*?\])\s*```', response_text, re.DOTALL)
        if json_match:
            actions = json.loads(json_match.group(1))
        else:
            # Try to find a bare JSON array
            array_match = re.search(r'\[\s*\{[^`]+\}\s*\]', response_text, re.DOTALL)
            if array_match:
                actions = json.loads(array_match.group(0))
    except (json.JSONDecodeError, AttributeError) as e:
        print(f"WARNING: Could not parse action JSON from LLM response: {e}", file=sys.stderr)

    # Validate action structure
    valid_actions = []
    for action in actions:
        if isinstance(action, dict) and "action_type" in action and "target" in action:
            # Ensure confidence is a float
            if "confidence" not in action:
                action["confidence"] = 0.5
            else:
                try:
                    action["confidence"] = float(action["confidence"])
                except (ValueError, TypeError):
                    action["confidence"] = 0.5
            valid_actions.append(action)

    return {
        "actions": valid_actions,
        "raw_response": response_text,
    }


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------

async def run_response_agent(
    alert_uuid: str,
    invocation_id: str | None,
    invocation_context: dict | None,
    system_prompt: str,
) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"Fetching alert {alert_uuid}...")
        alert = await fetch_alert(client, alert_uuid)
        print(f"Alert: {alert.get('title', 'Untitled')} [{alert.get('severity', 'Unknown')}]")

        # Fetch existing findings
        print("Fetching existing investigation findings...")
        findings = await fetch_alert_findings(client, alert_uuid)
        print(f"Found {len(findings)} existing finding(s).")

        # Generate response plan
        print("Generating response plan with LLM...")
        plan = generate_response_plan(system_prompt, alert, findings, invocation_context)

        actions = plan["actions"]
        print(f"Generated {len(actions)} recommended action(s).")

        # Submit high-confidence actions to approval gate
        submitted_actions = []
        held_actions = []

        for action in actions:
            confidence = action.get("confidence", 0.0)
            action_type = action.get("action_type", "unknown")
            target = action.get("target", "")
            reasoning = action.get("reasoning", "")

            if confidence >= ACTION_CONFIDENCE_THRESHOLD:
                print(f"  Auto-submitting: {action_type} → {target} (confidence={confidence:.2f})")
                success = await post_action(
                    client,
                    alert_uuid,
                    action_type=action_type,
                    target=target,
                    reason=reasoning,
                    confidence=confidence,
                )
                if success:
                    submitted_actions.append(action)
                else:
                    held_actions.append(action)
            else:
                print(
                    f"  Below threshold ({confidence:.2f} < {ACTION_CONFIDENCE_THRESHOLD}): "
                    f"{action_type} → {target} — holding for analyst review"
                )
                held_actions.append(action)

        print(
            f"Actions submitted: {len(submitted_actions)}, "
            f"held for analyst review: {len(held_actions)}"
        )

        # Build result
        result = {
            "findings": [
                {
                    "type": "response_plan",
                    "total_actions": len(actions),
                    "submitted_actions": len(submitted_actions),
                    "held_for_review": len(held_actions),
                    "action_list": actions,
                    "summary": plan["raw_response"][:1000],
                }
            ],
            "summary": (
                f"Response plan: {len(actions)} action(s) recommended. "
                f"{len(submitted_actions)} submitted to approval gate "
                f"(confidence >= {ACTION_CONFIDENCE_THRESHOLD}). "
                f"{len(held_actions)} held for analyst review."
            ),
        }

        if invocation_id:
            await patch_invocation_result(client, invocation_id, result)
        else:
            print("\n" + "=" * 60)
            print(plan["raw_response"])
            print("=" * 60)

        print("Response planning complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Response Agent — generates and submits prioritized response actions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent.py --mode queue
  python agent.py --mode invocation --invocation-id <uuid>

Environment:
  ACTION_CONFIDENCE_THRESHOLD  Actions at or above this confidence are auto-submitted (default: 0.85)
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
        await run_response_agent(alert_uuid, args.invocation_id, invocation, system_prompt)

    elif args.mode == "queue":
        async with httpx.AsyncClient(timeout=30.0) as client:
            queue_item = await checkout_alert_from_queue(client)
        if queue_item is None:
            sys.exit(0)
        alert_uuid = queue_item.get("alert_uuid") or queue_item.get("uuid")
        if not alert_uuid:
            print(f"ERROR: No alert UUID in queue item: {queue_item}", file=sys.stderr)
            sys.exit(1)
        await run_response_agent(
            alert_uuid,
            invocation_id=None,
            invocation_context=None,
            system_prompt=system_prompt,
        )


if __name__ == "__main__":
    asyncio.run(main())
