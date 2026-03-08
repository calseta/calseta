"""
Calseta Agent — Approach B.

Investigates a security alert WITH Calseta. Demonstrates the platform's
value proposition: structured data, pre-computed enrichment, context documents,
and detection rule documentation — all delivered before the agent sees the alert.

Flow:
  1. Receives alert UUID (alert already ingested and enriched by Calseta)
  2. Fetches normalized alert via GET /v1/alerts/{uuid} (structured, token-efficient)
  3. Fetches context documents via GET /v1/alerts/{uuid}/context
  4. Fetches detection rule documentation if a rule is associated
  5. Builds a concise, structured prompt with all pre-computed data
  6. Asks Claude to analyze — typically zero tool calls needed
  7. Posts finding back via POST /v1/alerts/{uuid}/findings
  8. Returns the finding and metrics

Usage:
    from calseta_agent import CalsetaAgent

    agent = CalsetaAgent(
        anthropic_api_key="sk-...",
        calseta_base_url="http://localhost:8000",
        calseta_api_key="cai_...",
    )
    result = await agent.investigate(alert_uuid="f47ac10b-...")

Requires:
    pip install anthropic httpx
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
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
# Calseta Agent
# ---------------------------------------------------------------------------

class CalsetaAgent:
    """
    Approach B agent: receives an alert UUID, fetches structured data from
    Calseta's REST API, and produces a finding in a single LLM call with
    zero tool calls. All enrichment, normalization, and context resolution
    has already been done by the platform.
    """

    # Claude Sonnet pricing as of 2026-03 (per million tokens)
    INPUT_COST_PER_M = 3.00
    OUTPUT_COST_PER_M = 15.00

    def __init__(
        self,
        anthropic_api_key: str,
        calseta_base_url: str = "http://localhost:8000",
        calseta_api_key: str = "",
        model: str = "claude-sonnet-4-20250514",
    ) -> None:
        self.llm_client = anthropic.Anthropic(api_key=anthropic_api_key)
        self.model = model
        self.calseta_base_url = calseta_base_url.rstrip("/")
        self.http = httpx.Client(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {calseta_api_key}",
                "Content-Type": "application/json",
            },
        )

    # ------------------------------------------------------------------
    # Calseta API helpers
    # ------------------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any]:
        """GET request to Calseta API. Returns the 'data' key from the envelope."""
        resp = self.http.get(f"{self.calseta_base_url}{path}")
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", body)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST request to Calseta API."""
        resp = self.http.post(
            f"{self.calseta_base_url}{path}",
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", body)

    def _fetch_alert(self, uuid: str) -> dict[str, Any]:
        """Fetch the full normalized alert with indicators and enrichment."""
        return self._get(f"/v1/alerts/{uuid}")

    def _fetch_context(self, uuid: str) -> list[dict[str, Any]]:
        """Fetch context documents (runbooks, SOPs) applicable to this alert."""
        result = self._get(f"/v1/alerts/{uuid}/context")
        if isinstance(result, list):
            return result
        return result.get("context_documents", [])

    def _fetch_detection_rule(self, rule_id: int | str) -> dict[str, Any] | None:
        """Fetch detection rule documentation if a rule is associated."""
        try:
            return self._get(f"/v1/detection-rules/{rule_id}")
        except httpx.HTTPStatusError:
            return None

    def _post_finding(
        self, alert_uuid: str, summary: str, confidence: str, action: str
    ) -> dict[str, Any]:
        """Post the investigation finding back to Calseta."""
        return self._post(
            f"/v1/alerts/{alert_uuid}/findings",
            {
                "agent_name": "calseta_case_study_agent",
                "summary": summary,
                "confidence": confidence,
                "recommended_action": action,
            },
        )

    # ------------------------------------------------------------------
    # Prompt construction — concise, structured, token-efficient
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        return (
            "You are a SOC analyst AI agent investigating a security alert. "
            "You have been given a pre-structured alert payload from Calseta "
            "that includes:\n"
            "- The normalized alert with clean field names\n"
            "- All indicators of compromise, already extracted and enriched\n"
            "- Detection rule documentation explaining what triggered the alert\n"
            "- Applicable runbooks and SOPs for handling this alert type\n\n"
            "Your task: analyze the pre-structured data and produce an "
            "investigation summary.\n\n"
            "Your investigation summary MUST include:\n"
            "- Alert classification and severity assessment\n"
            "- Analysis of each enriched indicator and its risk level\n"
            "- Overall verdict (True Positive / False Positive / Needs Investigation)\n"
            "- Recommended next steps\n\n"
            "All enrichment has already been done for you — do NOT request "
            "additional lookups. Focus on analysis and synthesis."
        )

    def _build_alert_context(
        self,
        alert: dict[str, Any],
        context_docs: list[dict[str, Any]],
        detection_rule: dict[str, Any] | None,
    ) -> str:
        """
        Build a concise, structured prompt from the Calseta API responses.

        This is the key differentiator: instead of dumping a raw SIEM payload
        and raw enrichment API responses into the context window, we provide
        a clean, pre-processed summary that's optimized for LLM consumption.
        """
        sections: list[str] = []

        # 1. Alert summary (normalized fields only — no raw_payload)
        sections.append("## Alert Summary")
        sections.append(f"- Title: {alert.get('title', 'Unknown')}")
        sections.append(f"- Severity: {alert.get('severity', 'Unknown')}")
        sections.append(f"- Status: {alert.get('status', 'Unknown')}")
        sections.append(f"- Source: {alert.get('source_name', 'Unknown')}")
        sections.append(f"- Occurred: {alert.get('occurred_at', 'Unknown')}")
        sections.append(f"- Ingested: {alert.get('ingested_at', 'Unknown')}")

        tags = alert.get("tags", [])
        if tags:
            sections.append(f"- Tags: {', '.join(tags)}")
        sections.append("")

        # 2. Enriched indicators — already structured by Calseta
        indicators = alert.get("indicators", [])
        if indicators:
            sections.append("## Indicators of Compromise (Enriched)")
            for ind in indicators:
                sections.append(
                    f"### {ind.get('type', '?').upper()}: {ind.get('value', '?')}"
                )
                sections.append(f"- Malice verdict: {ind.get('malice', 'Pending')}")
                sections.append(
                    f"- First seen: {ind.get('first_seen', '?')} | "
                    f"Last seen: {ind.get('last_seen', '?')}"
                )

                enrichment = ind.get("enrichment_results") or {}
                for provider_name, provider_data in enrichment.items():
                    if not isinstance(provider_data, dict):
                        continue
                    extracted = provider_data.get("extracted", {})
                    if extracted:
                        sections.append(f"- {provider_name}:")
                        for key, val in extracted.items():
                            sections.append(f"  - {key}: {val}")
                sections.append("")

        # 3. Detection rule documentation
        if detection_rule:
            sections.append("## Detection Rule")
            sections.append(f"- Name: {detection_rule.get('name', 'Unknown')}")
            doc = detection_rule.get("documentation", "")
            if doc:
                sections.append(f"- Documentation:\n{doc}")
            mitre = detection_rule.get("mitre_tactics", [])
            if mitre:
                sections.append(f"- MITRE Tactics: {', '.join(mitre)}")
            sections.append("")

        # 4. Context documents (runbooks, SOPs)
        if context_docs:
            sections.append("## Applicable Runbooks & SOPs")
            for doc in context_docs:
                sections.append(f"### {doc.get('title', 'Untitled')}")
                content = doc.get("content", "")
                # Truncate very long documents to stay token-efficient
                if len(content) > 2000:
                    content = content[:2000] + "\n[... truncated for brevity]"
                sections.append(content)
                sections.append("")

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Core investigation
    # ------------------------------------------------------------------

    async def investigate(self, alert_uuid: str) -> AgentMetrics:
        """
        Run a full investigation on an alert that has already been processed
        by Calseta.

        Returns AgentMetrics with token counts, timing, and the finding text.
        """
        metrics = AgentMetrics()
        start = time.monotonic()

        # Fetch structured data from Calseta (these are REST calls, not LLM calls)
        alert = self._fetch_alert(alert_uuid)
        context_docs = self._fetch_context(alert_uuid)

        detection_rule = None
        rule_id = alert.get("detection_rule_id")
        if rule_id:
            detection_rule = self._fetch_detection_rule(rule_id)

        # Build the concise prompt — this is where the token savings happen
        alert_context = self._build_alert_context(alert, context_docs, detection_rule)

        user_message = (
            "Investigate this security alert and produce your finding.\n\n"
            f"{alert_context}"
        )

        # Single LLM call — no tool loop needed because all enrichment is done
        # Retry with backoff on rate limit errors
        response = None
        for attempt in range(5):
            try:
                response = self.llm_client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    temperature=0,
                    system=self._build_system_prompt(),
                    messages=[{"role": "user", "content": user_message}],
                )
                break
            except anthropic.RateLimitError:
                wait = 2 ** attempt * 5
                print(f"[rate limited, waiting {wait}s]... ", end="", flush=True)
                time.sleep(wait)
        if response is None:
            raise RuntimeError("Rate limited after 5 retries")

        metrics.input_tokens = response.usage.input_tokens
        metrics.output_tokens = response.usage.output_tokens

        # Extract finding text
        text_blocks = [b for b in response.content if b.type == "text"]
        finding_text = "\n".join(b.text for b in text_blocks)
        metrics.finding = finding_text

        # Post finding back to Calseta
        try:
            self._post_finding(
                alert_uuid=alert_uuid,
                summary=finding_text[:50_000],
                confidence="medium",
                action="Review finding and take recommended actions.",
            )
        except Exception:
            # Finding post failure should not break metrics collection
            pass

        metrics.duration_seconds = time.monotonic() - start
        metrics.total_tokens = metrics.input_tokens + metrics.output_tokens
        metrics.estimated_cost_usd = (
            (metrics.input_tokens / 1_000_000) * self.INPUT_COST_PER_M
            + (metrics.output_tokens / 1_000_000) * self.OUTPUT_COST_PER_M
        )

        # Calseta agent: zero tool calls, zero external API calls by the agent
        metrics.tool_calls = 0
        metrics.external_api_calls = 0

        return metrics

    def close(self) -> None:
        """Close HTTP client."""
        self.http.close()
