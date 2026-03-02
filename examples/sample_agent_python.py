#!/usr/bin/env python3
"""
Calseta AI — Sample SOC Investigation Agent (REST API + Claude)

A working sample agent that demonstrates how to build an AI-powered SOC
investigation agent using the Calseta AI REST API. This agent:

  1. Receives alert webhooks from Calseta AI (via a registered agent)
  2. Fetches full alert context from the REST API
  3. Builds a token-efficient investigation prompt
  4. Calls the Claude API for analysis
  5. Posts the finding back to the alert

Requirements:
  pip install httpx anthropic uvicorn starlette

Environment variables:
  CALSETA_API_URL    — Base URL of the Calseta API (default: http://localhost:8000)
  CALSETA_API_KEY    — Calseta API key (starts with cai_)
  ANTHROPIC_API_KEY  — Anthropic API key for Claude
  AGENT_PORT         — Port for this webhook listener (default: 9000)
  CLAUDE_MODEL       — Claude model to use (default: claude-sonnet-4-20250514)
  LOG_LEVEL          — Logging level (default: INFO)

Usage:
  export CALSETA_API_URL=http://localhost:8000
  export CALSETA_API_KEY=cai_your_key_here
  export ANTHROPIC_API_KEY=sk-ant-your_key_here
  python examples/sample_agent_python.py

Then register this agent with Calseta:
  curl -X POST http://localhost:8000/v1/agents \\
    -H "Authorization: Bearer cai_your_admin_key" \\
    -H "Content-Type: application/json" \\
    -d '{
      "name": "sample-investigation-agent",
      "endpoint_url": "http://localhost:9000/webhook",
      "trigger_on_severities": ["Medium", "High", "Critical"],
      "documentation": "Sample Claude-powered investigation agent"
    }'
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any

import anthropic
import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

# ---------------------------------------------------------------------------
# Configuration — all from environment variables
# ---------------------------------------------------------------------------

CALSETA_API_URL: str = os.environ.get("CALSETA_API_URL", "http://localhost:8000")
CALSETA_API_KEY: str = os.environ.get("CALSETA_API_KEY", "")
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
AGENT_PORT: int = int(os.environ.get("AGENT_PORT", "9000"))
CLAUDE_MODEL: str = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

# Agent identity — used when posting findings back to Calseta
AGENT_NAME = "sample-investigation-agent"

# Set up logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(AGENT_NAME)


# ---------------------------------------------------------------------------
# Calseta API client — thin wrapper around httpx for Calseta REST calls
# ---------------------------------------------------------------------------


class CalsetaClient:
    """
    Async HTTP client for the Calseta AI REST API.

    All Calseta API responses follow the envelope format:
      Single object:  {"data": {...}, "meta": {...}}
      List:           {"data": [...], "meta": {"total": N, "page": 1, ...}}
      Error:          {"error": {"code": "...", "message": "...", "details": {}}}
    """

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def get_alert(self, alert_uuid: str) -> dict[str, Any]:
        """
        Fetch full alert detail including indicators, enrichment, and _metadata.

        GET /v1/alerts/{uuid}
        Returns the "data" field from the response envelope.
        The "meta" field contains the _metadata block (alert_source, indicator_count, etc.).
        """
        url = f"{self.base_url}/v1/alerts/{alert_uuid}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            body = response.json()
            return body

    async def get_alert_context(self, alert_uuid: str) -> list[dict[str, Any]]:
        """
        Fetch applicable context documents (runbooks, SOPs, IR plans) for an alert.

        GET /v1/alerts/{uuid}/context
        Returns the "data" array from the response envelope.
        """
        url = f"{self.base_url}/v1/alerts/{alert_uuid}/context"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            body = response.json()
            return body.get("data", [])

    async def get_detection_rule(self, rule_uuid: str) -> dict[str, Any] | None:
        """
        Fetch a detection rule by UUID for its documentation and MITRE context.

        GET /v1/detection-rules/{uuid}
        Returns the "data" field, or None if the request fails.
        """
        url = f"{self.base_url}/v1/detection-rules/{rule_uuid}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self.headers)
                response.raise_for_status()
                return response.json().get("data")
            except httpx.HTTPStatusError:
                return None

    async def post_finding(
        self,
        alert_uuid: str,
        summary: str,
        confidence: str | None = None,
        recommended_action: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Post an investigation finding back to the alert.

        POST /v1/alerts/{uuid}/findings
        Body: {agent_name, summary, confidence, recommended_action, evidence}
        """
        url = f"{self.base_url}/v1/alerts/{alert_uuid}/findings"
        payload: dict[str, Any] = {
            "agent_name": AGENT_NAME,
            "summary": summary,
        }
        if confidence:
            payload["confidence"] = confidence
        if recommended_action:
            payload["recommended_action"] = recommended_action
        if evidence:
            payload["evidence"] = evidence

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=self.headers)
            response.raise_for_status()
            return response.json()


# ---------------------------------------------------------------------------
# Prompt builder — constructs a token-efficient investigation prompt
# ---------------------------------------------------------------------------

# System prompt: defines the agent's role and output format.
# Kept concise to minimize token overhead on every call.
SYSTEM_PROMPT = """\
You are a SOC analyst AI agent. You receive security alert data that has already \
been normalized, enriched with threat intelligence, and annotated with applicable \
playbooks by Calseta AI.

Your job: analyze the alert, assess the threat, and produce a structured investigation finding.

Output format (use exactly these sections):

## Assessment
One paragraph summary of what happened and how severe it is.

## Threat Analysis
- What indicators are present and what do the enrichment results tell us?
- Are any indicators rated Malicious or Suspicious?
- What MITRE ATT&CK techniques are relevant (if a detection rule matched)?

## Recommended Actions
Numbered list of specific, actionable next steps for the SOC team.

## Confidence
State your confidence level: low, medium, or high. Explain why.

Rules:
- Be concise. SOC analysts need actionable findings, not essays.
- Reference specific indicator values and enrichment verdicts.
- If context documents (playbooks/SOPs) are provided, follow their guidance.
- If enrichment data is missing or incomplete, note it and adjust confidence.\
"""


def build_investigation_prompt(
    alert: dict[str, Any],
    metadata: dict[str, Any],
    indicators: list[dict[str, Any]],
    detection_rule: dict[str, Any] | None,
    context_docs: list[dict[str, Any]],
) -> str:
    """
    Build a structured, token-efficient prompt from alert data.

    Design decisions for token optimization:
    - Use compact key=value format instead of verbose prose
    - Only include non-null fields
    - Summarize enrichment results (extracted verdicts, not raw API responses)
    - Include detection rule documentation and MITRE context inline
    - Include context document content (playbooks, SOPs) so the LLM can follow them
    """
    sections: list[str] = []

    # --- Section 1: Alert overview (compact key=value) ---
    sections.append("# Alert")
    sections.append(f"title: {alert.get('title', 'Unknown')}")
    sections.append(f"severity: {alert.get('severity', 'Unknown')}")
    sections.append(f"status: {alert.get('status', 'Unknown')}")
    sections.append(f"source: {alert.get('source_name', 'Unknown')}")
    if alert.get("occurred_at"):
        sections.append(f"occurred_at: {alert['occurred_at']}")
    if alert.get("tags"):
        sections.append(f"tags: {', '.join(alert['tags'])}")
    sections.append(f"is_enriched: {alert.get('is_enriched', False)}")

    # --- Section 2: Indicators with enrichment verdicts ---
    if indicators:
        sections.append("")
        sections.append(f"# Indicators ({len(indicators)} total)")
        for ind in indicators:
            # Compact format: type=value malice=verdict [provider: extracted_key=val]
            line = f"- {ind.get('type', '?')}={ind.get('value', '?')} malice={ind.get('malice', 'Pending')}"
            # Append enrichment summaries (only the extracted verdicts, not raw data)
            enrichment = ind.get("enrichment_results") or {}
            for provider, data in enrichment.items():
                if not isinstance(data, dict):
                    continue
                extracted = data.get("extracted", {})
                if isinstance(extracted, dict) and extracted:
                    # Pick the most informative keys from the extracted data
                    parts = []
                    for key in ("verdict", "malice", "risk_score", "abuse_confidence_score",
                                "country", "isp", "positives", "total"):
                        if key in extracted:
                            parts.append(f"{key}={extracted[key]}")
                    if parts:
                        line += f" [{provider}: {', '.join(parts)}]"
                elif data.get("success") is False:
                    line += f" [{provider}: enrichment_failed]"
            sections.append(line)
    else:
        sections.append("")
        sections.append("# Indicators: none extracted")

    # --- Section 3: Detection rule (if matched) ---
    if detection_rule:
        sections.append("")
        sections.append("# Detection Rule")
        sections.append(f"name: {detection_rule.get('name', 'Unknown')}")
        if detection_rule.get("severity"):
            sections.append(f"severity: {detection_rule['severity']}")
        if detection_rule.get("mitre_tactics"):
            sections.append(f"mitre_tactics: {', '.join(detection_rule['mitre_tactics'])}")
        if detection_rule.get("mitre_techniques"):
            sections.append(f"mitre_techniques: {', '.join(detection_rule['mitre_techniques'])}")
        if detection_rule.get("documentation"):
            sections.append(f"documentation: {detection_rule['documentation']}")

    # --- Section 4: Context documents (playbooks, SOPs, IR plans) ---
    if context_docs:
        sections.append("")
        sections.append(f"# Applicable Context Documents ({len(context_docs)})")
        for doc in context_docs:
            sections.append(f"\n## {doc.get('title', 'Untitled')} ({doc.get('document_type', 'unknown')})")
            if doc.get("description"):
                sections.append(f"Description: {doc['description']}")
            # Include the full content — this is the playbook/SOP the agent should follow
            if doc.get("content"):
                sections.append(doc["content"])

    # --- Section 5: Enrichment metadata ---
    sections.append("")
    sections.append("# Enrichment Summary")
    enrichment_meta = metadata.get("enrichment", {})
    succeeded = enrichment_meta.get("succeeded", [])
    failed = enrichment_meta.get("failed", [])
    if succeeded:
        sections.append(f"providers_succeeded: {', '.join(succeeded)}")
    if failed:
        sections.append(f"providers_failed: {', '.join(failed)}")
    if enrichment_meta.get("enriched_at"):
        sections.append(f"enriched_at: {enrichment_meta['enriched_at']}")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Investigation pipeline — the core logic
# ---------------------------------------------------------------------------


async def investigate_alert(webhook_payload: dict[str, Any]) -> None:
    """
    Main investigation pipeline. Called when a webhook arrives from Calseta.

    Steps:
      1. Extract alert UUID from the webhook payload
      2. Fetch full alert context from the Calseta REST API
      3. Build a token-efficient prompt
      4. Call Claude for analysis
      5. Post the finding back to the alert

    The webhook payload already contains much of the data we need (alert,
    indicators, detection_rule, context_documents), but we also demonstrate
    fetching from the REST API — which is the pattern for agents that operate
    outside the webhook flow (e.g., polling, scheduled investigation).
    """
    # --- Step 1: Extract alert UUID ---
    # The webhook payload has an "alert" object with a "uuid" field.
    # For test webhooks, the UUID is all-zeros — skip investigation.
    alert_data = webhook_payload.get("alert", {})
    alert_uuid = alert_data.get("uuid")

    if not alert_uuid:
        logger.error("Webhook payload missing alert UUID — skipping")
        return

    if webhook_payload.get("test"):
        logger.info("Received test webhook — acknowledging without investigation")
        return

    logger.info("Starting investigation for alert %s", alert_uuid)

    calseta = CalsetaClient(CALSETA_API_URL, CALSETA_API_KEY)

    # --- Step 2: Fetch full alert context from the REST API ---
    # Even though the webhook payload includes alert data, fetching from the
    # API ensures we have the latest state (enrichment may have completed
    # after the webhook was dispatched).
    try:
        alert_response = await calseta.get_alert(alert_uuid)
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Failed to fetch alert %s: HTTP %d — %s",
            alert_uuid, exc.response.status_code, exc.response.text[:200],
        )
        return
    except httpx.RequestError as exc:
        logger.error("Failed to connect to Calseta API for alert %s: %s", alert_uuid, exc)
        return

    # Unpack the response envelope:
    #   {"data": {alert fields + indicators list}, "meta": {_metadata block}}
    alert = alert_response.get("data", {})
    metadata = alert_response.get("meta", {})
    indicators = alert.get("indicators", [])

    # Fetch applicable context documents (playbooks, SOPs, IR plans).
    # These are automatically matched by Calseta's targeting rules engine
    # based on the alert's source, severity, and tags.
    try:
        context_docs = await calseta.get_alert_context(alert_uuid)
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        logger.warning("Failed to fetch context documents for alert %s: %s", alert_uuid, exc)
        context_docs = []

    # If the webhook included a detection rule, use it. Otherwise, the
    # alert response does not include the full detection rule object, so
    # we use what came in the webhook payload.
    detection_rule = webhook_payload.get("detection_rule")

    logger.info(
        "Alert %s: severity=%s, indicators=%d, detection_rule=%s, context_docs=%d",
        alert_uuid,
        alert.get("severity", "?"),
        len(indicators),
        "yes" if detection_rule else "no",
        len(context_docs),
    )

    # --- Step 3: Build the investigation prompt ---
    prompt = build_investigation_prompt(
        alert=alert,
        metadata=metadata,
        indicators=indicators,
        detection_rule=detection_rule,
        context_docs=context_docs,
    )

    logger.debug("Investigation prompt (%d chars):\n%s", len(prompt), prompt)

    # --- Step 4: Call Claude API for analysis ---
    try:
        claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = claude_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Investigate this security alert and produce your finding.\n\n{prompt}",
                }
            ],
        )
    except anthropic.APIError as exc:
        logger.error("Claude API call failed for alert %s: %s", alert_uuid, exc)
        return

    # Extract the text response from Claude's message
    finding_text = ""
    for block in message.content:
        if block.type == "text":
            finding_text += block.text

    if not finding_text:
        logger.error("Claude returned empty response for alert %s", alert_uuid)
        return

    # Log token usage for cost tracking
    usage = message.usage
    logger.info(
        "Claude analysis complete for alert %s: input_tokens=%d, output_tokens=%d",
        alert_uuid,
        usage.input_tokens,
        usage.output_tokens,
    )

    # --- Step 5: Determine confidence from Claude's response ---
    # Parse the confidence level from the structured output
    confidence = _extract_confidence(finding_text)

    # Extract recommended actions section for the dedicated field
    recommended_action = _extract_section(finding_text, "## Recommended Actions")

    # --- Step 6: Post finding back to the alert ---
    try:
        result = await calseta.post_finding(
            alert_uuid=alert_uuid,
            summary=finding_text,
            confidence=confidence,
            recommended_action=recommended_action,
            evidence={
                "model": CLAUDE_MODEL,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "investigated_at": datetime.now(timezone.utc).isoformat(),
                "indicator_count": len(indicators),
                "context_docs_used": len(context_docs),
                "detection_rule_available": detection_rule is not None,
            },
        )
        finding_id = result.get("data", {}).get("id", "unknown")
        logger.info(
            "Finding posted for alert %s: finding_id=%s", alert_uuid, finding_id
        )
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Failed to post finding for alert %s: HTTP %d — %s",
            alert_uuid, exc.response.status_code, exc.response.text[:200],
        )
    except httpx.RequestError as exc:
        logger.error("Failed to post finding for alert %s: %s", alert_uuid, exc)


def _extract_confidence(text: str) -> str | None:
    """
    Extract the confidence level from Claude's structured response.

    Looks for "low", "medium", or "high" in the ## Confidence section.
    Returns the confidence string suitable for the findings API, or None.
    """
    confidence_section = _extract_section(text, "## Confidence")
    if not confidence_section:
        return None

    lower = confidence_section.lower()
    # Check in order of specificity
    if "high" in lower:
        return "high"
    if "medium" in lower:
        return "medium"
    if "low" in lower:
        return "low"
    return None


def _extract_section(text: str, heading: str) -> str | None:
    """
    Extract a markdown section from the response text.

    Returns the content between the heading and the next ## heading (or end of text).
    Returns None if the heading is not found.
    """
    idx = text.find(heading)
    if idx == -1:
        return None

    # Start after the heading line
    start = text.find("\n", idx)
    if start == -1:
        return None
    start += 1

    # Find the next heading or end of text
    next_heading = text.find("\n## ", start)
    if next_heading == -1:
        section = text[start:]
    else:
        section = text[start:next_heading]

    return section.strip() or None


# ---------------------------------------------------------------------------
# Webhook receiver — HTTP server that accepts Calseta agent webhooks
# ---------------------------------------------------------------------------


async def webhook_handler(request: Request) -> JSONResponse:
    """
    Webhook endpoint that receives alert notifications from Calseta AI.

    Calseta's agent dispatch service sends a POST with this payload shape:
    {
        "alert": {uuid, title, severity, status, source_name, occurred_at, ...},
        "indicators": [{uuid, type, value, malice, enrichment_results, ...}, ...],
        "detection_rule": {uuid, name, documentation, mitre_tactics, ...} | null,
        "context_documents": [{uuid, title, document_type, content, ...}, ...],
        "workflows": [{uuid, name, documentation, risk_level, ...}, ...],
        "calseta_api_base_url": "http://...",
        "_metadata": {generated_at, alert_source, indicator_count, enrichment, ...}
    }

    For test webhooks, the payload includes "test": true.
    """
    try:
        payload = await request.json()
    except Exception:
        logger.warning("Received non-JSON webhook payload")
        return JSONResponse(
            {"error": "Invalid JSON"}, status_code=400
        )

    alert_title = payload.get("alert", {}).get("title", "unknown")
    alert_uuid = payload.get("alert", {}).get("uuid", "unknown")
    is_test = payload.get("test", False)

    logger.info(
        "Webhook received: alert=%s uuid=%s test=%s",
        alert_title, alert_uuid, is_test,
    )

    # Run investigation asynchronously.
    # In a production agent, you would likely push this to a task queue
    # rather than running inline in the request handler.
    try:
        await investigate_alert(payload)
    except Exception:
        logger.error(
            "Unhandled error investigating alert %s:\n%s",
            alert_uuid, traceback.format_exc(),
        )

    # Always return 200 to acknowledge receipt.
    # Calseta records the HTTP status in the agent_runs audit log.
    return JSONResponse({"status": "received", "alert_uuid": alert_uuid})


async def health_handler(request: Request) -> JSONResponse:
    """Health check endpoint for monitoring."""
    return JSONResponse({
        "status": "healthy",
        "agent": AGENT_NAME,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

# Starlette app with two routes:
#   POST /webhook  — receives Calseta alert webhooks
#   GET  /health   — health check
app = Starlette(
    routes=[
        Route("/webhook", webhook_handler, methods=["POST"]),
        Route("/health", health_handler, methods=["GET"]),
    ],
)


def _validate_config() -> list[str]:
    """Check that all required environment variables are set."""
    errors: list[str] = []
    if not CALSETA_API_KEY:
        errors.append("CALSETA_API_KEY is not set")
    elif not CALSETA_API_KEY.startswith("cai_"):
        errors.append("CALSETA_API_KEY should start with 'cai_'")
    if not ANTHROPIC_API_KEY:
        errors.append("ANTHROPIC_API_KEY is not set")
    return errors


if __name__ == "__main__":
    # Validate configuration before starting
    config_errors = _validate_config()
    if config_errors:
        print("Configuration errors:", file=sys.stderr)
        for err in config_errors:
            print(f"  - {err}", file=sys.stderr)
        print(
            "\nSet the required environment variables and try again.\n"
            "See the module docstring or examples/README.md for details.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Starting {AGENT_NAME} webhook listener on port {AGENT_PORT}...")
    print(f"  Calseta API: {CALSETA_API_URL}")
    print(f"  Claude model: {CLAUDE_MODEL}")
    print(f"  Webhook URL: http://localhost:{AGENT_PORT}/webhook")
    print(f"  Health check: http://localhost:{AGENT_PORT}/health")
    print()

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT, log_level=LOG_LEVEL.lower())
