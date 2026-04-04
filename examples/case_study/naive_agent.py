"""
Naive AI Agent — Approach A (Baseline).

Investigates a raw security alert WITHOUT Calseta. Represents the current
state-of-the-art for teams building security AI agents without purpose-built
infrastructure.

Flow:
  1. Raw alert JSON passed directly into the context window
  2. Agent uses tool calls to identify and extract indicators from unstructured payload
  3. Agent calls enrichment APIs directly (VirusTotal, AbuseIPDB) via tool calls
  4. Agent receives raw API responses and parses them itself
  5. Agent has no pre-loaded detection rule documentation or runbooks
  6. Agent synthesizes findings and produces a structured investigation summary

Usage:
    from naive_agent import NaiveAgent

    agent = NaiveAgent(anthropic_api_key="sk-...", virustotal_api_key="vt-...",
                       abuseipdb_api_key="ab-...")
    result = await agent.investigate(raw_alert_json, source_name="sentinel")

Requires:
    pip install anthropic httpx
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import anthropic
import httpx

# ---------------------------------------------------------------------------
# Metrics collection
# ---------------------------------------------------------------------------

@dataclass
class AgentMetrics:
    """Collects token usage, timing, and API call counts for a single run."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tool_calls: int = 0
    external_api_calls: int = 0
    duration_seconds: float = 0.0
    estimated_cost_usd: float = 0.0
    finding: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "external_api_calls": self.external_api_calls,
            "duration_seconds": round(self.duration_seconds, 2),
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "finding": self.finding,
        }


# ---------------------------------------------------------------------------
# Tool definitions for the naive agent
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "lookup_ip_virustotal",
        "description": (
            "Look up an IP address on VirusTotal to get reputation data, "
            "malicious detections, ASN info, and last analysis results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ip_address": {
                    "type": "string",
                    "description": "The IP address to look up",
                }
            },
            "required": ["ip_address"],
        },
    },
    {
        "name": "lookup_hash_virustotal",
        "description": (
            "Look up a file hash (MD5, SHA1, or SHA256) on VirusTotal to get "
            "malware detection results, file metadata, and threat classification."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file_hash": {
                    "type": "string",
                    "description": "The file hash to look up (MD5, SHA1, or SHA256)",
                }
            },
            "required": ["file_hash"],
        },
    },
    {
        "name": "lookup_domain_virustotal",
        "description": (
            "Look up a domain on VirusTotal to get reputation, DNS records, "
            "WHOIS info, and malicious detections."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "The domain name to look up",
                }
            },
            "required": ["domain"],
        },
    },
    {
        "name": "lookup_url_virustotal",
        "description": (
            "Look up a URL on VirusTotal to get scan results, redirects, "
            "and malicious detections."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to scan",
                }
            },
            "required": ["url"],
        },
    },
    {
        "name": "lookup_ip_abuseipdb",
        "description": (
            "Look up an IP address on AbuseIPDB to get abuse confidence score, "
            "report count, country, ISP, and usage type."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ip_address": {
                    "type": "string",
                    "description": "The IP address to look up",
                }
            },
            "required": ["ip_address"],
        },
    },
]


# ---------------------------------------------------------------------------
# Naive Agent
# ---------------------------------------------------------------------------

class NaiveAgent:
    """
    Approach A agent: receives raw alert JSON, uses tool calls to enrich
    indicators, and synthesizes a finding — all within the LLM context window.
    """

    # Claude Sonnet pricing as of 2026-03 (per million tokens)
    INPUT_COST_PER_M = 3.00
    OUTPUT_COST_PER_M = 15.00

    def __init__(
        self,
        anthropic_api_key: str,
        virustotal_api_key: str = "",
        abuseipdb_api_key: str = "",
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.client = anthropic.Anthropic(api_key=anthropic_api_key)
        self.vt_key = virustotal_api_key
        self.abuseipdb_key = abuseipdb_api_key
        self.model = model
        self.http = httpx.Client(timeout=30.0)

    # ------------------------------------------------------------------
    # External API calls (executed when the LLM requests a tool call)
    # ------------------------------------------------------------------

    def _call_virustotal(self, endpoint: str) -> dict[str, Any]:
        """Make a VirusTotal v3 API request."""
        if not self.vt_key:
            return {"error": "VirusTotal API key not configured"}
        resp = self.http.get(
            f"https://www.virustotal.com/api/v3/{endpoint}",
            headers={"x-apikey": self.vt_key},
        )
        resp.raise_for_status()
        return resp.json()

    def _call_abuseipdb(self, ip: str) -> dict[str, Any]:
        """Make an AbuseIPDB v2 check request."""
        if not self.abuseipdb_key:
            return {"error": "AbuseIPDB API key not configured"}
        resp = self.http.get(
            "https://api.abuseipdb.com/api/v2/check",
            headers={
                "Key": self.abuseipdb_key,
                "Accept": "application/json",
            },
            params={"ipAddress": ip, "maxAgeInDays": "90", "verbose": "true"},
        )
        resp.raise_for_status()
        return resp.json()

    def _execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Execute a tool call and return the JSON string result."""
        try:
            if tool_name == "lookup_ip_virustotal":
                result = self._call_virustotal(f"ip_addresses/{tool_input['ip_address']}")
            elif tool_name == "lookup_hash_virustotal":
                result = self._call_virustotal(f"files/{tool_input['file_hash']}")
            elif tool_name == "lookup_domain_virustotal":
                result = self._call_virustotal(f"domains/{tool_input['domain']}")
            elif tool_name == "lookup_url_virustotal":
                # URL lookup requires base64url-encoded URL identifier
                import base64
                url_id = base64.urlsafe_b64encode(
                    tool_input["url"].encode()
                ).decode().rstrip("=")
                result = self._call_virustotal(f"urls/{url_id}")
            elif tool_name == "lookup_ip_abuseipdb":
                result = self._call_abuseipdb(tool_input["ip_address"])
            else:
                result = {"error": f"Unknown tool: {tool_name}"}
        except httpx.HTTPStatusError as exc:
            result = {"error": f"HTTP {exc.response.status_code}: {exc.response.text[:500]}"}
        except Exception as exc:
            result = {"error": str(exc)}

        return json.dumps(result, default=str)

    # ------------------------------------------------------------------
    # Core investigation loop
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        return (
            "You are a SOC analyst AI agent investigating a security alert. "
            "You have been given the raw alert payload from the source SIEM system.\n\n"
            "Your task:\n"
            "1. Analyze the raw alert JSON to identify the alert type and severity\n"
            "2. Extract all indicators of compromise (IPs, domains, hashes, URLs, accounts)\n"
            "3. Use the available tools to enrich each indicator with threat intelligence\n"
            "4. Synthesize your findings into a structured investigation summary\n\n"
            "Your investigation summary MUST include:\n"
            "- Alert classification and severity assessment\n"
            "- List of all indicators found with their enrichment results\n"
            "- Risk assessment for each indicator\n"
            "- Overall verdict (True Positive / False Positive / Needs Investigation)\n"
            "- Recommended next steps\n\n"
            "Be thorough — check every indicator you find. Do not skip enrichment steps."
        )

    async def investigate(
        self, raw_alert: dict[str, Any], source_name: str
    ) -> AgentMetrics:
        """
        Run a full investigation on a raw alert payload.

        Returns AgentMetrics with token counts, timing, and the finding text.
        """
        metrics = AgentMetrics()
        start = time.monotonic()

        # The entire raw alert goes into the context window — this is
        # deliberately inefficient and represents the naive approach.
        user_message = (
            f"Investigate this {source_name} security alert. "
            f"Here is the complete raw alert payload:\n\n"
            f"```json\n{json.dumps(raw_alert, indent=2, default=str)}\n```"
        )

        messages: list[dict[str, Any]] = [{"role": "user", "content": user_message}]

        # Agentic loop: keep calling the model until it stops requesting tools
        max_iterations = 15
        for _ in range(max_iterations):
            # Retry with backoff on rate limit errors
            response = None
            for attempt in range(5):
                try:
                    response = self.client.messages.create(
                        model=self.model,
                        max_tokens=4096,
                        temperature=0,
                        system=self._build_system_prompt(),
                        tools=TOOLS,
                        messages=messages,
                    )
                    break
                except anthropic.RateLimitError:
                    wait = 2 ** attempt * 5  # 5, 10, 20, 40, 80 seconds
                    print(f"[rate limited, waiting {wait}s]... ", end="", flush=True)
                    time.sleep(wait)
            if response is None:
                raise RuntimeError("Rate limited after 5 retries")

            # Accumulate token usage
            metrics.input_tokens += response.usage.input_tokens
            metrics.output_tokens += response.usage.output_tokens

            # Check if the model wants to use tools
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # Model is done — extract the final text response
                text_blocks = [b for b in response.content if b.type == "text"]
                metrics.finding = "\n".join(b.text for b in text_blocks)
                break

            # Process tool calls
            # Add the assistant's response to the conversation
            messages.append({"role": "assistant", "content": response.content})

            # Execute each tool call and add results
            tool_results = []
            for tool_block in tool_use_blocks:
                metrics.tool_calls += 1
                metrics.external_api_calls += 1

                result_str = self._execute_tool(tool_block.name, tool_block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": result_str,
                })

            messages.append({"role": "user", "content": tool_results})

            # If model indicates end_turn, break
            if response.stop_reason == "end_turn":
                text_blocks = [b for b in response.content if b.type == "text"]
                if text_blocks:
                    metrics.finding = "\n".join(b.text for b in text_blocks)
                break

        metrics.duration_seconds = time.monotonic() - start
        metrics.total_tokens = metrics.input_tokens + metrics.output_tokens
        metrics.estimated_cost_usd = (
            (metrics.input_tokens / 1_000_000) * self.INPUT_COST_PER_M
            + (metrics.output_tokens / 1_000_000) * self.OUTPUT_COST_PER_M
        )

        return metrics

    def close(self) -> None:
        """Close HTTP client."""
        self.http.close()
