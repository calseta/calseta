#!/usr/bin/env python3
"""
Calseta - Sample MCP Agent
==============================

A working sample agent that demonstrates end-to-end autonomous alert
investigation using ONLY the Calseta MCP server. No direct REST API calls
are made — all data reads and writes go through MCP resources and tools.

This agent:
  1. Connects to the Calseta MCP server via SSE transport
  2. Reads alerts from the calseta://alerts resource
  3. Picks an enriched alert and reads full context via calseta://alerts/{uuid}
  4. Reads matching context documents via calseta://alerts/{uuid}/context
  5. Discovers available workflows via calseta://workflows
  6. Calls Claude API to analyze the alert and produce a finding
  7. Posts the finding back via the post_alert_finding MCP tool
  8. Executes a matching workflow via the execute_workflow MCP tool

Why MCP-only matters:
  MCP (Model Context Protocol) provides a standardized interface for AI agents
  to interact with data platforms. By using MCP exclusively, this agent works
  with any MCP-compatible client (Claude Desktop, Cursor, custom agents) and
  does not depend on REST API endpoint paths, pagination conventions, or
  response envelope formats. The MCP server handles all of that, presenting
  data in a clean, agent-optimized format.

Requirements:
  pip install mcp anthropic

Environment variables:
  CALSETA_MCP_URL      - MCP server SSE endpoint (default: http://localhost:8001/sse)
  CALSETA_API_KEY      - Calseta API key (cai_xxx format)
  ANTHROPIC_API_KEY    - Anthropic API key for Claude reasoning

Usage:
  export CALSETA_MCP_URL="http://localhost:8001/sse"
  export CALSETA_API_KEY="cai_your_api_key_here"
  export ANTHROPIC_API_KEY="sk-ant-your_key_here"
  python examples/sample_agent_mcp.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

# ---------------------------------------------------------------------------
# MCP SDK imports — these provide the client-side MCP transport and session.
# The sse_client establishes an SSE connection to the MCP server, while
# ClientSession provides the high-level API for reading resources and
# calling tools.
# ---------------------------------------------------------------------------
from mcp import ClientSession
from mcp.client.sse import sse_client

# ---------------------------------------------------------------------------
# Anthropic SDK — used to call Claude for the reasoning/analysis step.
# The agent reads structured data from the MCP server, builds a prompt,
# and uses Claude to produce an investigation finding.
# ---------------------------------------------------------------------------
import anthropic


# ===========================================================================
# Configuration
# ===========================================================================

# MCP server URL — the Calseta MCP server exposes an SSE endpoint.
# Default matches the Docker Compose setup (mcp service on port 8001).
MCP_URL = os.environ.get("CALSETA_MCP_URL", "http://localhost:8001/sse")

# Calseta API key — used for authenticating with the MCP server.
# Keys follow the format cai_{random_32_char_urlsafe_string}.
# The MCP server validates this key the same way the REST API does.
CALSETA_API_KEY = os.environ.get("CALSETA_API_KEY", "")

# Anthropic API key — used for calling Claude to reason about the alert.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Agent identity — included in findings posted back to Calseta.
AGENT_NAME = "sample-mcp-agent"

# Claude model to use for analysis.
CLAUDE_MODEL = "claude-sonnet-4-20250514"


# ===========================================================================
# Helper: parse MCP resource content
# ===========================================================================

def parse_resource_content(result: Any) -> dict | list:
    """
    Extract and parse JSON from an MCP read_resource response.

    MCP resources return content as a list of content blocks. Each block
    has a `text` field containing the JSON string. We parse the first
    text block and return the deserialized Python object.
    """
    # The result object has a `contents` list; each entry has a `text` field
    # containing the resource data as a JSON string.
    for content_block in result.contents:
        if hasattr(content_block, "text") and content_block.text:
            return json.loads(content_block.text)

    raise ValueError("MCP resource returned no text content")


def parse_tool_result(result: Any) -> dict:
    """
    Extract and parse JSON from an MCP call_tool response.

    MCP tool results return content as a list of content blocks, similar
    to resources. We parse the first text block.
    """
    for content_block in result.content:
        if hasattr(content_block, "text") and content_block.text:
            return json.loads(content_block.text)

    raise ValueError("MCP tool returned no text content")


# ===========================================================================
# Step 1: Read alerts from the MCP server
# ===========================================================================

async def read_alerts(session: ClientSession) -> list[dict]:
    """
    Read recent alerts from the calseta://alerts resource.

    This returns the last 50 alerts with summary fields: uuid, title,
    severity, status, source_name, occurred_at, is_enriched, tags.
    No indicators or enrichment details — those come from the detail view.
    """
    print("\n[Step 1] Reading alerts from calseta://alerts ...")

    result = await session.read_resource("calseta://alerts")
    data = parse_resource_content(result)

    alerts = data.get("alerts", [])
    count = data.get("count", 0)
    print(f"  Found {count} alerts")

    # Print a summary table for visibility
    for alert in alerts[:10]:  # Show first 10
        print(
            f"  - [{alert['severity']:>12}] [{alert['status']:>20}] "
            f"{alert['title'][:60]}"
        )

    return alerts


# ===========================================================================
# Step 2: Select an alert to investigate
# ===========================================================================

def select_alert(alerts: list[dict]) -> dict | None:
    """
    Pick the best alert to investigate from the list.

    Strategy: prefer enriched alerts with High or Critical severity that
    are not yet closed. If none match, fall back to any enriched alert,
    then any non-closed alert.
    """
    print("\n[Step 2] Selecting an alert to investigate ...")

    # Priority 1: enriched, high/critical severity, not closed
    for alert in alerts:
        if (
            alert.get("is_enriched")
            and alert.get("severity") in ("High", "Critical")
            and alert.get("status") != "Closed"
        ):
            print(f"  Selected: {alert['title']}")
            print(f"  UUID: {alert['uuid']}")
            print(f"  Severity: {alert['severity']} | Status: {alert['status']}")
            return alert

    # Priority 2: any enriched alert not closed
    for alert in alerts:
        if alert.get("is_enriched") and alert.get("status") != "Closed":
            print(f"  Selected (fallback - enriched): {alert['title']}")
            return alert

    # Priority 3: any alert not closed
    for alert in alerts:
        if alert.get("status") != "Closed":
            print(f"  Selected (fallback - any open): {alert['title']}")
            return alert

    print("  No suitable alert found to investigate.")
    return None


# ===========================================================================
# Step 3: Read full alert detail
# ===========================================================================

async def read_alert_detail(session: ClientSession, alert_uuid: str) -> dict:
    """
    Read the full alert detail from calseta://alerts/{uuid}.

    This returns everything an agent needs to investigate:
      - All normalized alert fields (title, severity, status, timestamps)
      - Indicators with enrichment results (IOCs extracted from the alert)
      - Detection rule with MITRE mappings and documentation
      - Applicable context documents (playbooks, SOPs)
      - Existing agent findings (from previous agent runs)
    """
    print(f"\n[Step 3] Reading alert detail from calseta://alerts/{alert_uuid} ...")

    result = await session.read_resource(f"calseta://alerts/{alert_uuid}")
    detail = parse_resource_content(result)

    # Print key details for visibility
    print(f"  Title: {detail.get('title')}")
    print(f"  Severity: {detail.get('severity')} | Status: {detail.get('status')}")
    print(f"  Source: {detail.get('source_name')}")
    print(f"  Occurred: {detail.get('occurred_at')}")
    print(f"  Enriched: {detail.get('enriched_at') or 'Not yet'}")

    # Indicators summary
    indicators = detail.get("indicators", [])
    print(f"  Indicators: {len(indicators)}")
    for ind in indicators:
        malice = ind.get("malice", "Pending")
        enriched = "enriched" if ind.get("is_enriched") else "not enriched"
        print(f"    - {ind['type']}: {ind['value']} ({malice}, {enriched})")

        # Show enrichment highlights if available
        enrichment = ind.get("enrichment_results") or {}
        for provider, data in enrichment.items():
            extracted = data.get("extracted", {})
            if extracted:
                highlights = ", ".join(f"{k}={v}" for k, v in list(extracted.items())[:3])
                print(f"      {provider}: {highlights}")

    # Detection rule summary
    rule = detail.get("detection_rule")
    if rule:
        print(f"  Detection Rule: {rule.get('name')}")
        print(f"    MITRE: {rule.get('mitre_tactics', [])}")
        if rule.get("documentation"):
            doc_preview = rule["documentation"][:100]
            print(f"    Documentation: {doc_preview}...")

    # Context documents summary
    ctx_docs = detail.get("context_documents", [])
    print(f"  Context Documents: {len(ctx_docs)}")
    for doc in ctx_docs:
        print(f"    - [{doc.get('document_type')}] {doc.get('title')}")

    return detail


# ===========================================================================
# Step 4: Read context documents for the alert
# ===========================================================================

async def read_alert_context(session: ClientSession, alert_uuid: str) -> list[dict]:
    """
    Read applicable context documents from calseta://alerts/{uuid}/context.

    Context documents are playbooks, runbooks, SOPs, and IR plans that match
    this alert based on targeting rules (severity, source, tags, etc.).
    They tell the agent HOW to investigate and respond.
    """
    print(f"\n[Step 4] Reading context documents from calseta://alerts/{alert_uuid}/context ...")

    result = await session.read_resource(f"calseta://alerts/{alert_uuid}/context")
    data = parse_resource_content(result)

    docs = data.get("context_documents", [])
    print(f"  Found {len(docs)} applicable context documents")
    for doc in docs:
        scope = "global" if doc.get("is_global") else "targeted"
        print(f"  - [{scope}] [{doc.get('document_type')}] {doc.get('title')}")
        if doc.get("content"):
            # Show first 200 chars of content
            preview = doc["content"][:200].replace("\n", " ")
            print(f"    Preview: {preview}...")

    return docs


# ===========================================================================
# Step 5: Discover available workflows
# ===========================================================================

async def discover_workflows(session: ClientSession) -> list[dict]:
    """
    Read the workflow catalog from calseta://workflows.

    Workflows are automated actions the agent can trigger — IP blocking,
    account suspension, enrichment runs, etc. Each workflow lists:
      - indicator_types it supports (ip, domain, hash, email, account)
      - risk_level (low, medium, high)
      - approval_mode ("always", "agent_only", or "never")
      - documentation (what it does and when to use it)
    """
    print("\n[Step 5] Discovering workflows from calseta://workflows ...")

    result = await session.read_resource("calseta://workflows")
    data = parse_resource_content(result)

    workflows = data.get("workflows", [])
    print(f"  Found {len(workflows)} workflows")
    for wf in workflows:
        status = "active" if wf.get("is_active") else "inactive"
        approval = f"approval: {wf.get('approval_mode', 'never')}"
        print(
            f"  - {wf['name']} ({status}, {approval})"
            f" | types: {wf.get('indicator_types', [])}"
            f" | risk: {wf.get('risk_level', 'unknown')}"
        )
        if wf.get("documentation"):
            doc_preview = wf["documentation"][:120].replace("\n", " ")
            print(f"    Doc: {doc_preview}...")

    return workflows


# ===========================================================================
# Step 6: Analyze the alert using Claude
# ===========================================================================

async def analyze_with_claude(
    alert_detail: dict,
    context_docs: list[dict],
    workflows: list[dict],
) -> dict:
    """
    Build a prompt from MCP data and call Claude for investigation analysis.

    This is the reasoning step. The agent provides Claude with:
      - Full alert context (indicators, enrichment, detection rule)
      - Applicable playbooks and SOPs
      - Available workflows
    Claude produces a structured finding with:
      - summary: what was found and why it matters
      - confidence: low / medium / high
      - recommended_action: what the SOC analyst should do next
      - suggested_workflow: which workflow to execute (if any)
    """
    print("\n[Step 6] Analyzing alert with Claude ...")

    # Build the context sections for the prompt
    # ---- Alert data ----
    alert_section = json.dumps(
        {
            "title": alert_detail.get("title"),
            "severity": alert_detail.get("severity"),
            "status": alert_detail.get("status"),
            "source_name": alert_detail.get("source_name"),
            "occurred_at": alert_detail.get("occurred_at"),
            "tags": alert_detail.get("tags"),
            "indicators": alert_detail.get("indicators", []),
            "detection_rule": alert_detail.get("detection_rule"),
            "agent_findings": alert_detail.get("agent_findings", []),
        },
        indent=2,
    )

    # ---- Context documents ----
    docs_section = ""
    for doc in context_docs:
        docs_section += f"\n### {doc.get('title')} ({doc.get('document_type')})\n"
        docs_section += doc.get("content", "(no content)") + "\n"

    # ---- Available workflows ----
    workflow_section = ""
    for wf in workflows:
        if wf.get("is_active"):
            workflow_section += (
                f"\n- {wf['name']} (uuid: {wf['uuid']})"
                f"\n  Types: {wf.get('indicator_types', [])}"
                f"\n  Risk: {wf.get('risk_level', 'unknown')}"
                f"\n  Approval mode: {wf.get('approval_mode', 'never')}"
                f"\n  Doc: {wf.get('documentation', 'N/A')}\n"
            )

    # ---- Build the prompt ----
    prompt = f"""You are a SOC analyst AI agent investigating a security alert from Calseta.

## Alert Data
{alert_section}

## Applicable Context Documents (Playbooks & SOPs)
{docs_section if docs_section.strip() else "(No context documents matched this alert)"}

## Available Workflows
{workflow_section if workflow_section.strip() else "(No active workflows available)"}

## Your Task
Analyze this alert and produce a structured investigation finding. Consider:
1. The indicators and their enrichment results (malice verdicts, threat intel data)
2. The detection rule's MITRE ATT&CK mapping and documentation
3. Any applicable playbooks or SOPs from the context documents
4. Whether any available workflow should be executed

Respond with ONLY a JSON object (no markdown, no code fences) with these fields:
{{
  "summary": "2-4 sentence analysis of what happened, threat assessment, and key evidence",
  "confidence": "low" or "medium" or "high",
  "recommended_action": "specific next step for the SOC analyst",
  "suggested_workflow_uuid": "UUID of a workflow to execute, or null if none appropriate",
  "suggested_workflow_indicator_type": "indicator type for the workflow, or null",
  "suggested_workflow_indicator_value": "indicator value for the workflow, or null",
  "reasoning": "brief explanation of your confidence level and workflow recommendation"
}}"""

    # Call Claude
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    # Parse Claude's response — expect a JSON object
    response_text = message.content[0].text.strip()
    print(f"  Claude response (raw): {response_text[:200]}...")

    try:
        analysis = json.loads(response_text)
    except json.JSONDecodeError:
        # If Claude didn't return clean JSON, try to extract it
        # Look for JSON between braces
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            analysis = json.loads(response_text[start:end])
        else:
            # Fallback: create a basic finding from the raw text
            analysis = {
                "summary": response_text[:500],
                "confidence": "low",
                "recommended_action": "Manual review required - agent could not parse structured response",
                "suggested_workflow_uuid": None,
                "suggested_workflow_indicator_type": None,
                "suggested_workflow_indicator_value": None,
                "reasoning": "Fallback finding due to unparseable Claude response",
            }

    print(f"  Confidence: {analysis.get('confidence')}")
    print(f"  Summary: {analysis.get('summary', '')[:150]}...")
    if analysis.get("suggested_workflow_uuid"):
        print(f"  Suggested workflow: {analysis['suggested_workflow_uuid']}")

    return analysis


# ===========================================================================
# Step 7: Post the finding via MCP tool
# ===========================================================================

async def post_finding(
    session: ClientSession,
    alert_uuid: str,
    analysis: dict,
) -> dict:
    """
    Post the investigation finding back to the alert using the
    post_alert_finding MCP tool.

    This records the agent's analysis in Calseta so SOC analysts and other
    agents can see what was found. The finding is immutable once posted.
    """
    print(f"\n[Step 7] Posting finding to alert {alert_uuid} via post_alert_finding ...")

    # The MCP tool expects these arguments:
    #   alert_uuid: str         - UUID of the alert
    #   summary: str            - Free-text analysis summary
    #   confidence: str         - "low", "medium", or "high"
    #   agent_name: str         - Name identifying this agent
    #   recommended_action: str - Optional suggested next step
    result = await session.call_tool(
        "post_alert_finding",
        arguments={
            "alert_uuid": alert_uuid,
            "summary": analysis.get("summary", "No summary available"),
            "confidence": analysis.get("confidence", "low"),
            "agent_name": AGENT_NAME,
            "recommended_action": analysis.get("recommended_action"),
        },
    )

    response = parse_tool_result(result)

    if "error" in response:
        print(f"  ERROR posting finding: {response['error']}")
    else:
        print(f"  Finding posted successfully!")
        print(f"  Finding ID: {response.get('finding_id')}")
        print(f"  Posted at: {response.get('posted_at')}")

    return response


# ===========================================================================
# Step 8: Execute a workflow via MCP tool
# ===========================================================================

async def execute_workflow(
    session: ClientSession,
    alert_uuid: str,
    analysis: dict,
) -> dict | None:
    """
    Execute a suggested workflow using the execute_workflow MCP tool.

    If Claude's analysis suggested a workflow (e.g., IP blocking, account
    suspension, enrichment), this step triggers it. The workflow runs
    asynchronously on the Calseta worker process — we get back a run UUID
    to track its progress.

    For workflows that require approval (high-risk actions like account
    suspension), the response will indicate "pending_approval" status and
    a human will need to approve via the Calseta UI or Slack before it
    executes.
    """
    workflow_uuid = analysis.get("suggested_workflow_uuid")
    indicator_type = analysis.get("suggested_workflow_indicator_type")
    indicator_value = analysis.get("suggested_workflow_indicator_value")

    if not workflow_uuid or not indicator_type or not indicator_value:
        print("\n[Step 8] No workflow suggested by analysis. Skipping execution.")
        return None

    print(f"\n[Step 8] Executing workflow {workflow_uuid} via execute_workflow ...")
    print(f"  Indicator: {indicator_type} = {indicator_value}")

    # The MCP tool expects these arguments:
    #   workflow_uuid: str        - UUID of the workflow to execute
    #   indicator_type: str       - Type of indicator (ip, domain, hash_*, email, account)
    #   indicator_value: str      - The indicator value
    #   alert_uuid: str           - Optional related alert UUID
    #   reason: str               - Why this should run (required for approval gate)
    #   confidence: float         - Agent's confidence 0.0-1.0 (required for approval gate)
    confidence_map = {"low": 0.3, "medium": 0.6, "high": 0.9}
    confidence_float = confidence_map.get(analysis.get("confidence", "medium"), 0.5)

    result = await session.call_tool(
        "execute_workflow",
        arguments={
            "workflow_uuid": workflow_uuid,
            "indicator_type": indicator_type,
            "indicator_value": indicator_value,
            "alert_uuid": alert_uuid,
            "reason": analysis.get("reasoning", "Automated investigation finding"),
            "confidence": confidence_float,
        },
    )

    response = parse_tool_result(result)

    if "error" in response:
        print(f"  ERROR executing workflow: {response['error']}")
    elif response.get("status") == "pending_approval":
        print(f"  Workflow requires human approval.")
        print(f"  Approval request UUID: {response.get('approval_request_uuid')}")
        print(f"  Expires at: {response.get('expires_at')}")
    elif response.get("status") == "queued":
        print(f"  Workflow queued for execution!")
        print(f"  Run UUID: {response.get('run_uuid')}")
    else:
        print(f"  Response: {json.dumps(response, indent=2)}")

    return response


# ===========================================================================
# Main investigation flow
# ===========================================================================

async def investigate() -> None:
    """
    Full autonomous investigation flow using only MCP resources and tools.

    This is the main entry point that orchestrates all steps:
      1. Connect to MCP server
      2. Read alerts
      3. Select an alert
      4. Read full alert detail
      5. Read context documents
      6. Discover workflows
      7. Analyze with Claude
      8. Post finding
      9. Execute workflow (if recommended)
    """
    # Validate configuration
    if not CALSETA_API_KEY:
        print("ERROR: CALSETA_API_KEY environment variable is required.")
        print("  Generate an API key via the Calseta admin CLI or API.")
        print("  Format: cai_{random_32_char_urlsafe_string}")
        sys.exit(1)

    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY environment variable is required.")
        print("  Get your key at https://console.anthropic.com/")
        sys.exit(1)

    print("=" * 72)
    print("  Calseta - MCP Agent Investigation")
    print("=" * 72)
    print(f"  MCP Server:  {MCP_URL}")
    print(f"  Agent Name:  {AGENT_NAME}")
    print(f"  Model:       {CLAUDE_MODEL}")
    print("=" * 72)

    # -----------------------------------------------------------------------
    # Connect to the MCP server via SSE transport.
    #
    # The sse_client context manager establishes a persistent SSE connection
    # to the Calseta MCP server. Authentication is handled via the
    # Authorization header — the same API key used for the REST API works
    # here. The MCP server validates it using CalsetaTokenVerifier.
    #
    # The connection yields (read_stream, write_stream) which are passed
    # to ClientSession to create the high-level MCP client interface.
    # -----------------------------------------------------------------------
    headers = {"Authorization": f"Bearer {CALSETA_API_KEY}"}

    print("\nConnecting to MCP server ...")

    async with sse_client(MCP_URL, headers=headers) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize the MCP session — this performs the protocol handshake
            # and exchanges capabilities between client and server.
            await session.initialize()
            print("  Connected and initialized!")

            # Optional: List available resources and tools for debugging
            resources = await session.list_resources()
            print(f"  Available resources: {len(resources.resources)}")
            for r in resources.resources:
                print(f"    - {r.uri}")

            tools = await session.list_tools()
            print(f"  Available tools: {len(tools.tools)}")
            for t in tools.tools:
                print(f"    - {t.name}: {t.description[:80]}...")

            # --- Step 1: Read alerts ---
            alerts = await read_alerts(session)
            if not alerts:
                print("\nNo alerts found. Ingest some alerts first:")
                print("  POST /v1/alerts/ingest with a source payload")
                return

            # --- Step 2: Select an alert ---
            selected = select_alert(alerts)
            if not selected:
                print("\nNo suitable alert to investigate. Exiting.")
                return

            alert_uuid = selected["uuid"]

            # --- Step 3: Read full alert detail ---
            alert_detail = await read_alert_detail(session, alert_uuid)

            # --- Step 4: Read context documents ---
            context_docs = await read_alert_context(session, alert_uuid)

            # --- Step 5: Discover workflows ---
            workflows = await discover_workflows(session)

            # --- Step 6: Analyze with Claude ---
            analysis = await analyze_with_claude(alert_detail, context_docs, workflows)

            # --- Step 7: Post finding ---
            finding_result = await post_finding(session, alert_uuid, analysis)

            # --- Step 8: Execute workflow (if suggested) ---
            workflow_result = await execute_workflow(session, alert_uuid, analysis)

            # --- Summary ---
            print("\n" + "=" * 72)
            print("  Investigation Complete")
            print("=" * 72)
            print(f"  Alert: {alert_detail.get('title')}")
            print(f"  Confidence: {analysis.get('confidence')}")
            print(f"  Finding posted: {'yes' if 'finding_id' in (finding_result or {}) else 'no'}")
            if workflow_result and "error" not in workflow_result:
                wf_status = workflow_result.get("status", "unknown")
                print(f"  Workflow status: {wf_status}")
            elif not analysis.get("suggested_workflow_uuid"):
                print("  Workflow: none suggested")
            print("=" * 72)


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    # Run the async investigation flow.
    # asyncio.run() creates a new event loop, runs the coroutine, and
    # cleans up. Ctrl+C will raise KeyboardInterrupt which propagates
    # through the context managers for clean shutdown.
    try:
        asyncio.run(investigate())
    except KeyboardInterrupt:
        print("\nInvestigation interrupted by user.")
        sys.exit(0)
    except Exception as exc:
        print(f"\nFatal error: {exc}")
        sys.exit(1)
