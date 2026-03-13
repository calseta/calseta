#!/usr/bin/env python3
"""
Calseta Live Agent — End-to-End Investigation Test

A CLI tool that runs a real LLM-powered SOC investigation against a live
Calseta instance. Validates the full agent consumption loop:

  1. Connect via REST API or MCP
  2. List alerts and pick one (or use --alert UUID)
  3. Fetch full alert context (indicators, enrichment, detection rule, runbooks)
  4. Send to Claude or OpenAI for analysis
  5. Post the finding back to the alert
  6. Optionally execute a suggested workflow

Supports three modes:
  --mode rest       Direct REST API calls to localhost:8000 (pull)
  --mode mcp        MCP protocol to localhost:8001 (pull)
  --register        Webhook listener mode (push) — registers with Calseta,
                    listens for webhooks, investigates on arrival, deregisters on exit

Supports two LLM providers:
  --model claude    Claude via Anthropic API (default)
  --model openai    GPT-4o via OpenAI API

Requirements:
  pip install httpx anthropic openai mcp

Usage:
  # Start Calseta first
  make lab

  # Investigate with Claude via REST API
  python examples/agents/investigate_alert.py --mode rest --model claude

  # Investigate with OpenAI via MCP
  python examples/agents/investigate_alert.py --mode mcp --model openai

  # Target a specific alert
  python examples/agents/investigate_alert.py --alert <uuid>

  # Investigate all open alerts
  python examples/agents/investigate_alert.py --all

  # Register as webhook agent (push mode) — listens for alerts from Calseta
  python examples/agents/investigate_alert.py --register

  # Register with custom port and severity filter
  python examples/agents/investigate_alert.py --register --agent-port 9000 \
    --trigger-severities High,Critical

Environment variables:
  CALSETA_API_URL      Calseta REST API base URL (default: http://localhost:8000)
  CALSETA_MCP_URL      Calseta MCP SSE endpoint (default: http://localhost:8001/sse)
  CALSETA_API_KEY      Calseta API key (cai_xxx format)
  ANTHROPIC_API_KEY    Anthropic API key (for --model claude)
  OPENAI_API_KEY       OpenAI API key (for --model openai)
  AZURE_OPENAI_API_KEY      Azure OpenAI API key (for --model azure)
  AZURE_OPENAI_ENDPOINT     Azure OpenAI endpoint URL (for --model azure)
  AZURE_OPENAI_DEPLOYMENT   Azure OpenAI deployment name (for --model azure)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback as tb
from dataclasses import dataclass
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CALSETA_API_URL = os.environ.get("CALSETA_API_URL", "http://localhost:8000")
CALSETA_MCP_URL = os.environ.get("CALSETA_MCP_URL", "http://localhost:8001/sse")
CALSETA_API_KEY = os.environ.get("CALSETA_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_DEPLOYMENT = os.environ.get(
    "AZURE_OPENAI_DEPLOYMENT", ""
)
AZURE_OPENAI_API_VERSION = os.environ.get(
    "AZURE_OPENAI_API_VERSION", "2024-12-01-preview"
)

AGENT_NAME = "live-investigation-agent"

AGENT_KEY_SCOPES = [
    "alerts:read",
    "alerts:write",
    "enrichments:read",
    "workflows:read",
    "workflows:execute",
    "agents:read",
    "agents:write",
]


# ---------------------------------------------------------------------------
# Agent API key provisioning
# ---------------------------------------------------------------------------


async def _create_agent_api_key(admin_key: str) -> tuple[str, str]:
    """
    Use the admin API key to create a short-lived agent-type API key.

    Returns (agent_api_key, key_uuid).
    """
    import httpx

    async with httpx.AsyncClient(
        timeout=15.0,
        headers={
            "Authorization": f"Bearer {admin_key}",
            "Content-Type": "application/json",
        },
    ) as client:
        resp = await client.post(
            f"{CALSETA_API_URL}/v1/api-keys",
            json={
                "name": AGENT_NAME,
                "key_type": "agent",
                "scopes": AGENT_KEY_SCOPES,
            },
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return data["key"], data["uuid"]


async def _revoke_agent_api_key(admin_key: str, key_uuid: str) -> None:
    """Revoke the agent API key using the admin key."""
    import httpx

    try:
        async with httpx.AsyncClient(
            timeout=10.0,
            headers={"Authorization": f"Bearer {admin_key}"},
        ) as client:
            resp = await client.delete(
                f"{CALSETA_API_URL}/v1/api-keys/{key_uuid}"
            )
            if resp.status_code < 300:
                print("  Agent API key revoked")
            else:
                print(f"  Key revocation returned {resp.status_code}")
    except Exception as exc:
        print(f"  WARNING: Failed to revoke agent key: {exc}")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class InvestigationResult:
    """Result from a single alert investigation."""

    alert_uuid: str
    alert_title: str
    mode: str
    model: str
    finding_summary: str = ""
    confidence: str = ""
    recommended_action: str = ""
    workflow_suggested: str | None = None
    workflow_status: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    duration_seconds: float = 0.0
    finding_posted: bool = False
    error: str | None = None

    def print_summary(self) -> None:
        print(f"\n{'─' * 72}")
        print(f"  Alert: {self.alert_title}")
        print(f"  UUID:  {self.alert_uuid}")
        print(f"  Mode:  {self.mode} | Model: {self.model}")
        print(f"{'─' * 72}")
        if self.error:
            print(f"  ERROR: {self.error}")
        else:
            print(f"  Confidence: {self.confidence}")
            print(f"  Tokens: {self.input_tokens:,} in / {self.output_tokens:,} out")
            print(f"  Duration: {self.duration_seconds:.1f}s")
            print(f"  Finding posted: {'yes' if self.finding_posted else 'no'}")
            if self.workflow_suggested:
                print(f"  Workflow: {self.workflow_suggested} ({self.workflow_status})")
            print(f"\n  Summary: {self.finding_summary[:200]}...")
        print(f"{'─' * 72}")


# ---------------------------------------------------------------------------
# LLM providers
# ---------------------------------------------------------------------------


class LLMProvider(Protocol):
    """Protocol for LLM providers."""

    def analyze(self, system_prompt: str, user_prompt: str) -> dict[str, Any]: ...


class ClaudeProvider:
    """Claude via Anthropic API."""

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = model
        self.name = f"claude ({model})"

    def analyze(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = "\n".join(b.text for b in response.content if b.type == "text")
        return {
            "text": text,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }


class OpenAIProvider:
    """GPT-4o via OpenAI API."""

    def __init__(self, model: str = "gpt-4o") -> None:
        import openai

        self.client = openai.OpenAI(api_key=OPENAI_API_KEY)
        self.model = model
        self.name = f"openai ({model})"

    def analyze(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        choice = response.choices[0]
        usage = response.usage
        return {
            "text": choice.message.content or "",
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        }


class AzureOpenAIProvider:
    """Azure OpenAI via openai SDK."""

    def __init__(self) -> None:
        import openai

        self.client = openai.AzureOpenAI(
            api_key=AZURE_OPENAI_API_KEY,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            api_version=AZURE_OPENAI_API_VERSION,
        )
        self.deployment = AZURE_OPENAI_DEPLOYMENT
        self.name = f"azure-openai ({self.deployment})"

    def analyze(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self.client.chat.completions.create(
            model=self.deployment,
            temperature=0,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        choice = response.choices[0]
        usage = response.usage
        return {
            "text": choice.message.content or "",
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0,
        }


# ---------------------------------------------------------------------------
# Calseta data source — REST API
# ---------------------------------------------------------------------------


class RESTDataSource:
    """Fetch alert data from Calseta REST API."""

    def __init__(self, base_url: str, api_key: str) -> None:
        import httpx

        self.base_url = base_url.rstrip("/")
        self.http = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    async def close(self) -> None:
        await self.http.aclose()

    async def _get(self, path: str) -> Any:
        resp = await self.http.get(f"{self.base_url}{path}")
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", body)

    async def _post(self, path: str, payload: dict) -> Any:
        resp = await self.http.post(f"{self.base_url}{path}", json=payload)
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", body)

    async def list_alerts(self) -> list[dict]:
        result = await self._get("/v1/alerts?page_size=50")
        if isinstance(result, list):
            return result
        return result if isinstance(result, list) else []

    async def get_alert(self, uuid: str) -> dict:
        return await self._get(f"/v1/alerts/{uuid}")

    async def get_context(self, uuid: str) -> list[dict]:
        result = await self._get(f"/v1/alerts/{uuid}/context")
        return result if isinstance(result, list) else result.get("context_documents", [])

    async def get_detection_rule(self, rule_id: str) -> dict | None:
        try:
            return await self._get(f"/v1/detection-rules/{rule_id}")
        except Exception:
            return None

    async def get_workflows(self) -> list[dict]:
        result = await self._get("/v1/workflows")
        if isinstance(result, list):
            return result
        return result.get("workflows", []) if isinstance(result, dict) else []

    async def post_finding(
        self, alert_uuid: str, summary: str, confidence: str, action: str
    ) -> dict:
        return await self._post(
            f"/v1/alerts/{alert_uuid}/findings",
            {
                "agent_name": AGENT_NAME,
                "summary": summary[:50_000],
                "confidence": confidence,
                "recommended_action": action,
            },
        )

    async def execute_workflow(
        self,
        workflow_uuid: str,
        indicator_type: str,
        indicator_value: str,
        alert_uuid: str,
        reason: str,
        confidence: float,
    ) -> dict:
        return await self._post(
            f"/v1/workflows/{workflow_uuid}/execute",
            {
                "indicator_type": indicator_type,
                "indicator_value": indicator_value,
                "alert_uuid": alert_uuid,
                "reason": reason,
                "confidence": confidence,
            },
        )


# ---------------------------------------------------------------------------
# Calseta data source — MCP
# ---------------------------------------------------------------------------


class MCPDataSource:
    """Fetch alert data from Calseta MCP server."""

    def __init__(self, mcp_url: str, api_key: str) -> None:
        self.mcp_url = mcp_url
        self.api_key = api_key
        self._session: Any = None
        self._exit_stack: Any = None

    async def connect(self) -> None:
        from contextlib import AsyncExitStack

        from mcp import ClientSession
        from mcp.client.sse import sse_client

        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        headers = {"Authorization": f"Bearer {self.api_key}"}
        read_stream, write_stream = await self._exit_stack.enter_async_context(
            sse_client(self.mcp_url, headers=headers)
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()
        print("  MCP connected and initialized")

        # List available resources and tools
        resources = await self._session.list_resources()
        tools = await self._session.list_tools()
        print(f"  Resources: {len(resources.resources)} | Tools: {len(tools.tools)}")

    async def close(self) -> None:
        if self._exit_stack:
            await self._exit_stack.aclose()

    def _parse_resource(self, result: Any) -> Any:
        for block in result.contents:
            if hasattr(block, "text") and block.text:
                return json.loads(block.text)
        raise ValueError("MCP resource returned no content")

    def _parse_tool(self, result: Any) -> Any:
        for block in result.content:
            if hasattr(block, "text") and block.text:
                return json.loads(block.text)
        raise ValueError("MCP tool returned no content")

    async def list_alerts(self) -> list[dict]:
        result = await self._session.read_resource("calseta://alerts")
        data = self._parse_resource(result)
        return data.get("alerts", [])

    async def get_alert(self, uuid: str) -> dict:
        result = await self._session.read_resource(f"calseta://alerts/{uuid}")
        return self._parse_resource(result)

    async def get_context(self, uuid: str) -> list[dict]:
        result = await self._session.read_resource(f"calseta://alerts/{uuid}/context")
        data = self._parse_resource(result)
        return data.get("context_documents", [])

    async def get_detection_rule(self, rule_id: str) -> dict | None:
        try:
            result = await self._session.read_resource(
                f"calseta://detection-rules/{rule_id}"
            )
            return self._parse_resource(result)
        except Exception:
            return None

    async def get_workflows(self) -> list[dict]:
        result = await self._session.read_resource("calseta://workflows")
        data = self._parse_resource(result)
        return data.get("workflows", [])

    async def post_finding(
        self, alert_uuid: str, summary: str, confidence: str, action: str
    ) -> dict:
        result = await self._session.call_tool(
            "post_alert_finding",
            arguments={
                "alert_uuid": alert_uuid,
                "summary": summary[:50_000],
                "confidence": confidence,
                "agent_name": AGENT_NAME,
                "recommended_action": action,
            },
        )
        return self._parse_tool(result)

    async def execute_workflow(
        self,
        workflow_uuid: str,
        indicator_type: str,
        indicator_value: str,
        alert_uuid: str,
        reason: str,
        confidence: float,
    ) -> dict:
        result = await self._session.call_tool(
            "execute_workflow",
            arguments={
                "workflow_uuid": workflow_uuid,
                "indicator_type": indicator_type,
                "indicator_value": indicator_value,
                "alert_uuid": alert_uuid,
                "reason": reason,
                "confidence": confidence,
            },
        )
        return self._parse_tool(result)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a SOC analyst AI agent investigating a security alert. All data has \
been pre-structured by Calseta: normalized alert fields, extracted and enriched \
indicators, detection rule documentation, and applicable runbooks/SOPs.

Produce an investigation finding with these sections:

## Assessment
One paragraph: what happened, how severe, true/false positive assessment.

## Indicator Analysis
For each indicator: type, value, enrichment verdict, risk assessment.

## MITRE ATT&CK
Relevant techniques (if a detection rule matched). Skip if none.

## Recommended Actions
Numbered list of specific next steps for the SOC team.

## Workflow Recommendation
If one or more workflows should be executed, list each on its own line using \
EXACTLY this format (one per line):

EXECUTE workflow_uuid=<uuid> indicator_type=<type> indicator_value=<value>

Example:
EXECUTE workflow_uuid=b8f29992-a6f9-48c8-8b86-c34eedaee0b2 indicator_type=account indicator_value=j.martinez@contoso.com

If none, say "None recommended."

## Confidence
State: low, medium, or high. Explain why.

Rules:
- ONLY use data provided below. Do NOT invent enrichment results.
- If enrichment is missing or pending, say so explicitly.
- Be concise. SOC analysts need actionable findings, not essays.
- Reference specific indicator values and verdicts.\
"""


def build_prompt(
    alert: dict,
    context_docs: list[dict],
    detection_rule: dict | None,
    workflows: list[dict],
) -> str:
    """Build a token-efficient investigation prompt from Calseta data."""
    sections: list[str] = []

    # Alert summary
    sections.append("# Alert")
    for key in ("title", "severity", "status", "source_name", "occurred_at", "description"):
        val = alert.get(key)
        if val:
            sections.append(f"{key}: {val}")
    tags = alert.get("tags", [])
    if tags:
        sections.append(f"tags: {', '.join(tags)}")

    # Indicators with enrichment
    indicators = alert.get("indicators", [])
    if indicators:
        sections.append(f"\n# Indicators ({len(indicators)})")
        for ind in indicators:
            itype = ind.get("type", "?")
            ival = ind.get("value", "?")
            imalice = ind.get("malice", "Pending")
            line = f"- {itype}={ival} malice={imalice}"
            enrichment = ind.get("enrichment_results") or {}
            for provider, data in enrichment.items():
                if not isinstance(data, dict):
                    continue
                extracted = data.get("extracted", {})
                if isinstance(extracted, dict) and extracted:
                    parts = [f"{k}={v}" for k, v in list(extracted.items())[:5]]
                    line += f" [{provider}: {', '.join(parts)}]"
            sections.append(line)

    # Detection rule
    if detection_rule:
        sections.append("\n# Detection Rule")
        sections.append(f"name: {detection_rule.get('name', 'Unknown')}")
        for key in ("mitre_tactics", "mitre_techniques"):
            val = detection_rule.get(key)
            if val:
                sections.append(f"{key}: {', '.join(val)}")
        doc = detection_rule.get("documentation", "")
        if doc:
            sections.append(f"documentation:\n{doc[:3000]}")

    # Context documents
    if context_docs:
        sections.append(f"\n# Context Documents ({len(context_docs)})")
        for doc in context_docs:
            sections.append(f"\n## {doc.get('title', 'Untitled')} ({doc.get('document_type', '')})")
            content = doc.get("content", "")
            if content:
                sections.append(content[:2000])

    # Available workflows
    active_wfs = [wf for wf in workflows if wf.get("is_active") or wf.get("state") == "active"]
    if active_wfs:
        sections.append(f"\n# Available Workflows ({len(active_wfs)})")
        for wf in active_wfs:
            sections.append(
                f"- {wf.get('name', '?')} (uuid: {wf.get('uuid', '?')})"
                f" types={wf.get('indicator_types', [])} risk={wf.get('risk_level', '?')}"
                f" approval={wf.get('approval_mode', 'never')}"
            )
            doc = wf.get("documentation", "")
            if doc:
                sections.append(f"  doc: {doc[:200]}")

    return "\n".join(sections)


# ---------------------------------------------------------------------------
# Investigation engine
# ---------------------------------------------------------------------------


def extract_confidence(text: str) -> str:
    """Extract confidence level from the LLM's response."""
    # Look in the Confidence section first
    lower = text.lower()
    conf_idx = lower.find("## confidence")
    if conf_idx >= 0:
        section = lower[conf_idx : conf_idx + 200]
        if "high" in section:
            return "high"
        if "medium" in section:
            return "medium"
        if "low" in section:
            return "low"
    # Fallback: look anywhere
    if "high confidence" in lower:
        return "high"
    if "medium confidence" in lower:
        return "medium"
    if "low confidence" in lower:
        return "low"
    return "medium"


def extract_section(text: str, heading: str) -> str:
    """Extract a markdown section from the response."""
    idx = text.find(heading)
    if idx == -1:
        return ""
    start = text.find("\n", idx)
    if start == -1:
        return ""
    start += 1
    next_h = text.find("\n## ", start)
    section = text[start:next_h] if next_h != -1 else text[start:]
    return section.strip()


def extract_workflow_recommendations(text: str) -> list[dict]:
    """Extract structured EXECUTE lines from the Workflow Recommendation section."""
    import re

    section = extract_section(text, "## Workflow Recommendation")
    if not section or "none" in section.lower()[:50]:
        return []

    results = []
    for match in re.finditer(
        r"EXECUTE\s+"
        r"workflow_uuid=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s+"
        r"indicator_type=(\S+)\s+"
        r"indicator_value=(\S+)",
        section,
        re.IGNORECASE,
    ):
        results.append({
            "workflow_uuid": match.group(1),
            "indicator_type": match.group(2),
            "indicator_value": match.group(3),
        })

    # Fallback: try the old loose pattern if no structured lines found
    if not results:
        uuid_match = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", section
        )
        type_match = re.search(
            r"(?:indicator[_ ]?type|type)[:\s=]+['\"]?(\w+)['\"]?", section, re.IGNORECASE
        )
        value_match = re.search(
            r"(?:indicator[_ ]?value|value)[:\s=]+['\"]?([^\s'\"]+)['\"]?",
            section, re.IGNORECASE,
        )
        if uuid_match and type_match and value_match:
            results.append({
                "workflow_uuid": uuid_match.group(0),
                "indicator_type": type_match.group(1),
                "indicator_value": value_match.group(1),
            })

    return results


async def investigate_alert(
    source: RESTDataSource | MCPDataSource,
    llm: ClaudeProvider | OpenAIProvider,
    alert_uuid: str,
    alert_title: str,
    mode: str,
    execute_workflows: bool = False,
) -> InvestigationResult:
    """Run a full investigation on a single alert."""
    result = InvestigationResult(
        alert_uuid=alert_uuid,
        alert_title=alert_title,
        mode=mode,
        model=llm.name,
    )
    start = time.monotonic()

    try:
        # Fetch all context
        print("\n  Fetching alert detail ...")
        alert = await source.get_alert(alert_uuid)

        print("  Fetching context documents ...")
        context_docs = await source.get_context(alert_uuid)

        # Detection rule
        detection_rule = None
        # REST returns detection_rule_id or detection_rule nested object
        rule_ref = alert.get("detection_rule_id") or (alert.get("detection_rule") or {}).get("uuid")
        if rule_ref:
            print("  Fetching detection rule ...")
            detection_rule = await source.get_detection_rule(str(rule_ref))
        # MCP detail view may include detection_rule inline
        if not detection_rule and isinstance(alert.get("detection_rule"), dict):
            detection_rule = alert["detection_rule"]

        print("  Fetching workflows ...")
        workflows = await source.get_workflows()

        # Build prompt
        indicators = alert.get("indicators", [])
        print(
            f"  Context: {len(indicators)} indicators, "
            f"{len(context_docs)} docs, "
            f"{'1 rule' if detection_rule else 'no rule'}, "
            f"{len(workflows)} workflows"
        )

        prompt = build_prompt(alert, context_docs, detection_rule, workflows)
        user_message = f"Investigate this security alert and produce your finding.\n\n{prompt}"

        # Call LLM
        print(f"  Calling {llm.name} ...")
        llm_result = llm.analyze(SYSTEM_PROMPT, user_message)

        finding_text = llm_result["text"]
        result.input_tokens = llm_result["input_tokens"]
        result.output_tokens = llm_result["output_tokens"]
        result.finding_summary = finding_text
        result.confidence = extract_confidence(finding_text)
        result.recommended_action = extract_section(finding_text, "## Recommended Actions")

        print(
            f"  LLM response: {result.input_tokens:,} in / {result.output_tokens:,} out"
        )

        # Post finding
        print("  Posting finding ...")
        try:
            await source.post_finding(
                alert_uuid=alert_uuid,
                summary=finding_text,
                confidence=result.confidence,
                action=(
                    result.recommended_action[:500]
                    if result.recommended_action
                    else "Review finding."
                ),
            )
            result.finding_posted = True
            print("  Finding posted successfully")
        except Exception as exc:
            print(f"  WARNING: Failed to post finding: {exc}")

        # Workflow execution (if enabled and suggested)
        if execute_workflows:
            wf_recs = extract_workflow_recommendations(finding_text)
            if wf_recs:
                confidence_map = {"low": 0.3, "medium": 0.6, "high": 0.9}
                wf_uuids = []
                wf_statuses = []
                for wf_rec in wf_recs:
                    wf_uuid = wf_rec["workflow_uuid"]
                    wf_uuids.append(wf_uuid)
                    print(
                        f"  Executing workflow {wf_uuid} "
                        f"({wf_rec['indicator_type']}={wf_rec['indicator_value']}) ..."
                    )
                    try:
                        wf_result = await source.execute_workflow(
                            workflow_uuid=wf_uuid,
                            indicator_type=wf_rec["indicator_type"],
                            indicator_value=wf_rec["indicator_value"],
                            alert_uuid=alert_uuid,
                            reason=f"Automated investigation by {AGENT_NAME}",
                            confidence=confidence_map.get(result.confidence, 0.5),
                        )
                        status = wf_result.get("status", "unknown")
                        wf_statuses.append(status)
                        print(f"  Workflow {wf_uuid} status: {status}")
                    except Exception as exc:
                        wf_statuses.append(f"error: {exc}")
                        print(f"  WARNING: Workflow {wf_uuid} failed: {exc}")
                result.workflow_suggested = ", ".join(wf_uuids)
                result.workflow_status = ", ".join(wf_statuses)
            else:
                print("  No workflow recommended by analysis")

    except Exception as exc:
        result.error = str(exc)
        import traceback

        traceback.print_exc()

    result.duration_seconds = time.monotonic() - start
    return result


# ---------------------------------------------------------------------------
# Alert selection
# ---------------------------------------------------------------------------


def select_alert(alerts: list[dict], target_uuid: str | None = None) -> list[dict]:
    """Select alerts to investigate."""
    if target_uuid:
        for a in alerts:
            if a.get("uuid") == target_uuid:
                return [a]
        # If not found in list, return a stub — we'll fetch the detail anyway
        return [{"uuid": target_uuid, "title": "(specified by UUID)"}]

    # Pick enriched, high/critical, non-closed alerts
    candidates = []
    for a in alerts:
        is_enriched = a.get("is_enriched") or a.get("enrichment_status") == "Enriched"
        is_open = a.get("status") != "Closed"
        if is_enriched and is_open:
            candidates.append(a)

    if not candidates:
        # Fallback: any non-closed alert
        candidates = [a for a in alerts if a.get("status") != "Closed"]

    # Sort by severity (prefer Critical > High > Medium > Low)
    severity_order = {
        "Critical": 0, "High": 1, "Medium": 2,
        "Low": 3, "Informational": 4, "Pending": 5,
    }
    candidates.sort(key=lambda a: severity_order.get(a.get("severity", "Pending"), 5))

    return candidates


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run(args: argparse.Namespace) -> None:
    """Main investigation flow."""
    print("=" * 72)
    print("  Calseta Live Agent — Investigation")
    print("=" * 72)
    print(f"  Mode:  {args.mode}")
    print(f"  Model: {args.model}")
    if args.alert:
        print(f"  Alert: {args.alert}")
    print(f"  Execute workflows: {args.execute_workflows}")
    print("=" * 72)

    # Initialize LLM provider
    llm = _create_llm(args.model)

    if not CALSETA_API_KEY:
        print("ERROR: CALSETA_API_KEY not set")
        sys.exit(1)

    # Provision a short-lived agent-type API key
    print("\n  Creating agent API key ...")
    agent_key, agent_key_uuid = await _create_agent_api_key(CALSETA_API_KEY)
    print(f"  Agent key created: {agent_key[:8]}...")

    # Initialize data source using the agent key
    source: RESTDataSource | MCPDataSource
    if args.mode == "rest":
        print(f"  Connecting to REST API at {CALSETA_API_URL} ...")
        source = RESTDataSource(CALSETA_API_URL, agent_key)
    elif args.mode == "mcp":
        print(f"  Connecting to MCP server at {CALSETA_MCP_URL} ...")
        source = MCPDataSource(CALSETA_MCP_URL, agent_key)
        await source.connect()
    else:
        print(f"ERROR: Unknown mode '{args.mode}'. Use 'rest' or 'mcp'.")
        sys.exit(1)

    try:
        # List alerts
        print("\n  Listing alerts ...")
        alerts = await source.list_alerts()
        print(f"  Found {len(alerts)} alerts")

        for a in alerts[:10]:
            is_enr = a.get("is_enriched") or a.get("enrichment_status") == "Enriched"
            enriched = "enriched" if is_enr else "pending"
            print(
                f"    [{a.get('severity', '?'):>12}] [{a.get('status', '?'):>10}] "
                f"[{enriched:>8}] {a.get('title', '?')[:50]}"
            )

        # Select alerts to investigate
        candidates = select_alert(alerts, args.alert)
        if not candidates:
            print("\n  No alerts found to investigate.")
            return

        if not args.all and not args.alert:
            # Just pick the first (highest severity) one
            candidates = candidates[:1]

        print(f"\n  Will investigate {len(candidates)} alert(s)")

        # Run investigations
        results: list[InvestigationResult] = []
        for alert in candidates:
            alert_uuid = alert.get("uuid", "")
            alert_title = alert.get("title", "(unknown)")
            print(f"\n{'=' * 72}")
            print(f"  Investigating: {alert_title}")
            print(f"  UUID: {alert_uuid}")
            print(f"{'=' * 72}")

            result = await investigate_alert(
                source=source,
                llm=llm,
                alert_uuid=alert_uuid,
                alert_title=alert_title,
                mode=args.mode,
                execute_workflows=args.execute_workflows,
            )
            results.append(result)
            result.print_summary()

        # Final summary
        if len(results) > 1:
            print(f"\n{'=' * 72}")
            print(f"  Summary: {len(results)} investigations")
            print(f"{'=' * 72}")
            total_in = sum(r.input_tokens for r in results)
            total_out = sum(r.output_tokens for r in results)
            total_time = sum(r.duration_seconds for r in results)
            posted = sum(1 for r in results if r.finding_posted)
            errors = sum(1 for r in results if r.error)
            print(f"  Total tokens: {total_in:,} in / {total_out:,} out")
            print(f"  Total time: {total_time:.1f}s")
            print(f"  Findings posted: {posted}/{len(results)}")
            if errors:
                print(f"  Errors: {errors}")
            print(f"{'=' * 72}")

    finally:
        await source.close()
        print("\n  Revoking agent API key ...")
        await _revoke_agent_api_key(CALSETA_API_KEY, agent_key_uuid)


# ---------------------------------------------------------------------------
# Webhook registration mode (--register)
# ---------------------------------------------------------------------------


async def run_registered(args: argparse.Namespace) -> None:
    """
    Register as a webhook agent with Calseta, start a listener server,
    and investigate alerts as they arrive. Deregisters on exit.
    """
    import httpx

    agent_port = args.agent_port
    endpoint_url = f"http://host.docker.internal:{agent_port}/webhook"

    print("=" * 72)
    print("  Calseta Live Agent — Webhook Registration Mode")
    print("=" * 72)
    print(f"  Model:    {args.model}")
    print(f"  Port:     {agent_port}")
    print(f"  Endpoint: {endpoint_url}")
    severities = (
        [s.strip() for s in args.trigger_severities.split(",")]
        if args.trigger_severities
        else []
    )
    sources = (
        [s.strip() for s in args.trigger_sources.split(",")]
        if args.trigger_sources
        else []
    )
    if severities:
        print(f"  Trigger severities: {severities}")
    if sources:
        print(f"  Trigger sources: {sources}")
    print("=" * 72)

    if not CALSETA_API_KEY:
        print("ERROR: CALSETA_API_KEY not set")
        sys.exit(1)

    # Initialize LLM provider
    llm = _create_llm(args.model)

    # Provision a short-lived agent-type API key
    print("\n  Creating agent API key ...")
    agent_key, agent_key_uuid = await _create_agent_api_key(CALSETA_API_KEY)
    print(f"  Agent key created: {agent_key[:8]}...")

    # REST source for fetching alert details during investigation
    source = RESTDataSource(CALSETA_API_URL, agent_key)

    # Register agent with Calseta
    print("\n  Registering agent with Calseta ...")
    registration_payload = {
        "name": AGENT_NAME,
        "description": (
            "Live investigation agent — receives webhooks, "
            "analyzes with LLM, posts findings back"
        ),
        "endpoint_url": endpoint_url,
        "trigger_on_severities": severities,
        "trigger_on_sources": sources,
        "timeout_seconds": 120,
        "retry_count": 1,
        "is_active": True,
        "documentation": (
            "Automated SOC investigation agent. Receives alert "
            "webhooks from Calseta, fetches full context via REST "
            "API, calls an LLM for analysis, and posts findings "
            "back to the alert."
        ),
    }

    async with httpx.AsyncClient(
        timeout=30.0,
        headers={
            "Authorization": f"Bearer {agent_key}",
            "Content-Type": "application/json",
        },
    ) as client:
        # Check if agent already registered, update if so
        agent_uuid = None
        try:
            resp = await client.get(
                f"{CALSETA_API_URL}/v1/agents"
            )
            resp.raise_for_status()
            agents = resp.json().get("data", [])
            for agent in agents:
                if agent.get("name") == AGENT_NAME:
                    agent_uuid = agent["uuid"]
                    print(f"  Agent already registered: {agent_uuid}")
                    # Update it
                    resp = await client.patch(
                        f"{CALSETA_API_URL}/v1/agents/{agent_uuid}",
                        json=registration_payload,
                    )
                    resp.raise_for_status()
                    print("  Agent registration updated")
                    break
        except httpx.HTTPStatusError:
            pass

        if not agent_uuid:
            resp = await client.post(
                f"{CALSETA_API_URL}/v1/agents",
                json=registration_payload,
            )
            resp.raise_for_status()
            result = resp.json().get("data", {})
            agent_uuid = result.get("uuid")
            print(f"  Agent registered: {agent_uuid}")

    # Build the webhook handler
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def webhook_handler(request: Request) -> JSONResponse:
        """Handle incoming alert webhooks from Calseta."""
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse(
                {"error": "Invalid JSON"}, status_code=400
            )

        alert_data = payload.get("alert", {})
        alert_uuid_val = alert_data.get("uuid", "unknown")
        alert_title = alert_data.get("title", "unknown")
        is_test = payload.get("test", False)

        print(
            f"\n  Webhook received: {alert_title} "
            f"(uuid={alert_uuid_val}, test={is_test})"
        )

        if is_test:
            print("  Test webhook — acknowledging")
            return JSONResponse({
                "status": "received",
                "test": True,
            })

        # Run investigation in background
        try:
            inv_result = await investigate_alert(
                source=source,
                llm=llm,
                alert_uuid=alert_uuid_val,
                alert_title=alert_title,
                mode="webhook",
                execute_workflows=args.execute_workflows,
            )
            inv_result.print_summary()
        except Exception:
            print(f"  ERROR investigating alert: {tb.format_exc()}")

        return JSONResponse({
            "status": "received",
            "alert_uuid": alert_uuid_val,
        })

    async def health_handler(request: Request) -> JSONResponse:
        return JSONResponse({
            "status": "healthy",
            "agent": AGENT_NAME,
            "agent_uuid": agent_uuid,
        })

    app = Starlette(
        routes=[
            Route("/webhook", webhook_handler, methods=["POST"]),
            Route("/health", health_handler, methods=["GET"]),
        ],
    )

    # Run the server with cleanup on shutdown
    import uvicorn

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=agent_port,
        log_level="info",
    )
    server = uvicorn.Server(config)

    print(f"\n  Webhook listener: http://localhost:{agent_port}/webhook")
    print(f"  Health check:     http://localhost:{agent_port}/health")
    print("  Press Ctrl+C to stop and deregister\n")

    try:
        await server.serve()
    finally:
        # Deregister on shutdown
        print("\n  Deregistering agent ...")
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                headers={
                    "Authorization": f"Bearer {agent_key}",
                },
            ) as client:
                resp = await client.delete(
                    f"{CALSETA_API_URL}/v1/agents/{agent_uuid}"
                )
                if resp.status_code < 300:
                    print("  Agent deregistered successfully")
                else:
                    print(f"  Deregistration returned {resp.status_code}")
        except Exception as exc:
            print(f"  WARNING: Failed to deregister: {exc}")
        await source.close()
        # Revoke the agent API key (using the admin key)
        print("  Revoking agent API key ...")
        await _revoke_agent_api_key(CALSETA_API_KEY, agent_key_uuid)


def _create_llm(
    model: str,
) -> ClaudeProvider | OpenAIProvider | AzureOpenAIProvider:
    """Create an LLM provider based on the model flag."""
    if model == "claude":
        if not ANTHROPIC_API_KEY:
            print("ERROR: ANTHROPIC_API_KEY not set")
            sys.exit(1)
        return ClaudeProvider()
    elif model == "openai":
        if not OPENAI_API_KEY:
            print("ERROR: OPENAI_API_KEY not set")
            sys.exit(1)
        return OpenAIProvider()
    elif model == "azure":
        missing = []
        if not AZURE_OPENAI_API_KEY:
            missing.append("AZURE_OPENAI_API_KEY")
        if not AZURE_OPENAI_ENDPOINT:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not AZURE_OPENAI_DEPLOYMENT:
            missing.append("AZURE_OPENAI_DEPLOYMENT")
        if missing:
            print(f"ERROR: Missing env vars: {', '.join(missing)}")
            sys.exit(1)
        return AzureOpenAIProvider()
    else:
        print(
            f"ERROR: Unknown model '{model}'. "
            "Use 'claude', 'openai', or 'azure'."
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calseta Live Agent — End-to-end investigation test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Investigate one alert with Claude via REST
  python examples/agents/investigate_alert.py --mode rest --model claude

  # Investigate via MCP with OpenAI
  python examples/agents/investigate_alert.py --mode mcp --model openai

  # Target a specific alert
  python examples/agents/investigate_alert.py --alert <uuid>

  # Investigate all open alerts and execute workflows
  python examples/agents/investigate_alert.py --all --execute-workflows
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["rest", "mcp"],
        default="rest",
        help="Data source: 'rest' for REST API, 'mcp' for MCP server (default: rest)",
    )
    parser.add_argument(
        "--model",
        choices=["claude", "openai", "azure"],
        default="claude",
        help="LLM provider: 'claude', 'openai', or 'azure' (default: claude)",
    )
    parser.add_argument(
        "--alert",
        type=str,
        default=None,
        help="Investigate a specific alert by UUID",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Investigate all open enriched alerts (default: just the highest severity one)",
    )
    parser.add_argument(
        "--execute-workflows",
        action="store_true",
        help="Execute workflows recommended by the LLM analysis",
    )

    # Webhook registration mode
    parser.add_argument(
        "--register",
        action="store_true",
        help="Register as webhook agent and listen for alerts (push mode)",
    )
    parser.add_argument(
        "--agent-port",
        type=int,
        default=9000,
        help="Port for webhook listener (default: 9000)",
    )
    parser.add_argument(
        "--trigger-severities",
        type=str,
        default=None,
        help="Comma-separated severity filter (e.g. 'High,Critical')",
    )
    parser.add_argument(
        "--trigger-sources",
        type=str,
        default=None,
        help="Comma-separated source filter (e.g. 'sentinel,elastic')",
    )
    args = parser.parse_args()

    try:
        if args.register:
            asyncio.run(run_registered(args))
        else:
            asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
