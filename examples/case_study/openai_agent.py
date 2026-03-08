"""
OpenAI Agents — Cross-Provider Validation.

Mirrors the Anthropic naive and Calseta agents using OpenAI's GPT-4o model
and function-calling API. Validates that Calseta's token reduction holds
across LLM providers.

Supports both OpenAI direct and Azure OpenAI endpoints. For Azure, pass
azure_endpoint and api_version to the constructor, or set env vars
AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_DEPLOYMENT,
and optionally AZURE_OPENAI_API_VERSION.

Usage:
    from openai_agent import OpenAINaiveAgent, OpenAICalsetaAgent

    # Direct OpenAI
    naive = OpenAINaiveAgent(openai_api_key="sk-...", virustotal_api_key="...",
                             abuseipdb_api_key="...")

    # Azure OpenAI
    naive = OpenAINaiveAgent(openai_api_key="azure-key",
                             azure_endpoint="https://my.openai.azure.com",
                             model="my-gpt4o-deployment",
                             virustotal_api_key="...", abuseipdb_api_key="...")

Requires:
    pip install openai httpx
"""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx
import openai

from naive_agent import AgentMetrics


# ---------------------------------------------------------------------------
# Client factory — OpenAI direct vs Azure OpenAI
# ---------------------------------------------------------------------------

def _create_openai_client(
    api_key: str,
    azure_endpoint: str = "",
    api_version: str = "2024-10-21",
) -> openai.OpenAI:
    """
    Create an OpenAI client. If azure_endpoint is set, returns an
    AzureOpenAI client; otherwise returns a standard OpenAI client.
    """
    if azure_endpoint:
        from openai import AzureOpenAI
        return AzureOpenAI(
            api_key=api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )
    return openai.OpenAI(api_key=api_key)


# ---------------------------------------------------------------------------
# OpenAI tool definitions (function-calling format)
# ---------------------------------------------------------------------------

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_ip_virustotal",
            "description": (
                "Look up an IP address on VirusTotal to get reputation data, "
                "malicious detections, ASN info, and last analysis results."
            ),
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_hash_virustotal",
            "description": (
                "Look up a file hash (MD5, SHA1, or SHA256) on VirusTotal to get "
                "malware detection results, file metadata, and threat classification."
            ),
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_domain_virustotal",
            "description": (
                "Look up a domain on VirusTotal to get reputation, DNS records, "
                "WHOIS info, and malicious detections."
            ),
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_url_virustotal",
            "description": (
                "Look up a URL on VirusTotal to get scan results, redirects, "
                "and malicious detections."
            ),
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_ip_abuseipdb",
            "description": (
                "Look up an IP address on AbuseIPDB to get abuse confidence score, "
                "report count, country, ISP, and usage type."
            ),
            "parameters": {
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
    },
]


# ---------------------------------------------------------------------------
# OpenAI Naive Agent
# ---------------------------------------------------------------------------

class OpenAINaiveAgent:
    """
    Approach A agent using OpenAI GPT-4o: receives raw alert JSON, uses
    function calls to enrich indicators, and synthesizes a finding.
    """

    # GPT-4o pricing as of 2026-03 (per million tokens)
    INPUT_COST_PER_M = 2.50
    OUTPUT_COST_PER_M = 10.00

    def __init__(
        self,
        openai_api_key: str,
        virustotal_api_key: str = "",
        abuseipdb_api_key: str = "",
        model: str = "gpt-4o",
        azure_endpoint: str = "",
        api_version: str = "2024-10-21",
    ) -> None:
        self.client = _create_openai_client(
            api_key=openai_api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )
        self.vt_key = virustotal_api_key
        self.abuseipdb_key = abuseipdb_api_key
        self.model = model
        self.http = httpx.Client(timeout=30.0)

    # ------------------------------------------------------------------
    # External API calls
    # ------------------------------------------------------------------

    def _call_virustotal(self, endpoint: str) -> dict[str, Any]:
        if not self.vt_key:
            return {"error": "VirusTotal API key not configured"}
        resp = self.http.get(
            f"https://www.virustotal.com/api/v3/{endpoint}",
            headers={"x-apikey": self.vt_key},
        )
        resp.raise_for_status()
        return resp.json()

    def _call_abuseipdb(self, ip: str) -> dict[str, Any]:
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
        try:
            if tool_name == "lookup_ip_virustotal":
                result = self._call_virustotal(f"ip_addresses/{tool_input['ip_address']}")
            elif tool_name == "lookup_hash_virustotal":
                result = self._call_virustotal(f"files/{tool_input['file_hash']}")
            elif tool_name == "lookup_domain_virustotal":
                result = self._call_virustotal(f"domains/{tool_input['domain']}")
            elif tool_name == "lookup_url_virustotal":
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
        metrics = AgentMetrics()
        start = time.monotonic()

        user_message = (
            f"Investigate this {source_name} security alert. "
            f"Here is the complete raw alert payload:\n\n"
            f"```json\n{json.dumps(raw_alert, indent=2, default=str)}\n```"
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": user_message},
        ]

        max_iterations = 15
        for _ in range(max_iterations):
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                temperature=0,
                tools=OPENAI_TOOLS,
                messages=messages,
            )

            usage = response.usage
            if usage:
                metrics.input_tokens += usage.prompt_tokens
                metrics.output_tokens += usage.completion_tokens

            choice = response.choices[0]
            message = choice.message

            # Check for tool calls
            if message.tool_calls:
                # Add assistant message with tool calls
                messages.append(message.model_dump())

                for tool_call in message.tool_calls:
                    metrics.tool_calls += 1
                    metrics.external_api_calls += 1

                    tool_input = json.loads(tool_call.function.arguments)
                    result_str = self._execute_tool(
                        tool_call.function.name, tool_input
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_str,
                    })
            else:
                # No tool calls — extract final response
                metrics.finding = message.content or ""
                break

            if choice.finish_reason == "stop":
                metrics.finding = message.content or ""
                break

        metrics.duration_seconds = time.monotonic() - start
        metrics.total_tokens = metrics.input_tokens + metrics.output_tokens
        metrics.estimated_cost_usd = (
            (metrics.input_tokens / 1_000_000) * self.INPUT_COST_PER_M
            + (metrics.output_tokens / 1_000_000) * self.OUTPUT_COST_PER_M
        )

        return metrics

    def close(self) -> None:
        self.http.close()


# ---------------------------------------------------------------------------
# OpenAI Calseta Agent
# ---------------------------------------------------------------------------

class OpenAICalsetaAgent:
    """
    Approach B agent using OpenAI GPT-4o: fetches structured data from
    Calseta's REST API, produces a finding in a single LLM call with
    zero tool calls.
    """

    INPUT_COST_PER_M = 2.50
    OUTPUT_COST_PER_M = 10.00

    def __init__(
        self,
        openai_api_key: str,
        calseta_base_url: str = "http://localhost:8000",
        calseta_api_key: str = "",
        model: str = "gpt-4o",
        azure_endpoint: str = "",
        api_version: str = "2024-10-21",
    ) -> None:
        self.client = _create_openai_client(
            api_key=openai_api_key,
            azure_endpoint=azure_endpoint,
            api_version=api_version,
        )
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
    # Calseta API helpers (same as CalsetaAgent)
    # ------------------------------------------------------------------

    def _get(self, path: str) -> dict[str, Any]:
        resp = self.http.get(f"{self.calseta_base_url}{path}")
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", body)

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self.http.post(
            f"{self.calseta_base_url}{path}",
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()
        return body.get("data", body)

    def _fetch_alert(self, uuid: str) -> dict[str, Any]:
        return self._get(f"/v1/alerts/{uuid}")

    def _fetch_context(self, uuid: str) -> list[dict[str, Any]]:
        result = self._get(f"/v1/alerts/{uuid}/context")
        if isinstance(result, list):
            return result
        return result.get("context_documents", [])

    def _fetch_detection_rule(self, rule_id: int | str) -> dict[str, Any] | None:
        try:
            return self._get(f"/v1/detection-rules/{rule_id}")
        except httpx.HTTPStatusError:
            return None

    def _post_finding(
        self, alert_uuid: str, summary: str, confidence: str, action: str
    ) -> dict[str, Any]:
        return self._post(
            f"/v1/alerts/{alert_uuid}/findings",
            {
                "agent_name": "openai_calseta_case_study_agent",
                "summary": summary,
                "confidence": confidence,
                "recommended_action": action,
            },
        )

    # ------------------------------------------------------------------
    # Prompt construction (same structure as CalsetaAgent)
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
        sections: list[str] = []

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

        if context_docs:
            sections.append("## Applicable Runbooks & SOPs")
            for doc in context_docs:
                sections.append(f"### {doc.get('title', 'Untitled')}")
                content = doc.get("content", "")
                if len(content) > 2000:
                    content = content[:2000] + "\n[... truncated for brevity]"
                sections.append(content)
                sections.append("")

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Core investigation
    # ------------------------------------------------------------------

    async def investigate(self, alert_uuid: str) -> AgentMetrics:
        metrics = AgentMetrics()
        start = time.monotonic()

        alert = self._fetch_alert(alert_uuid)
        context_docs = self._fetch_context(alert_uuid)

        detection_rule = None
        rule_id = alert.get("detection_rule_id")
        if rule_id:
            detection_rule = self._fetch_detection_rule(rule_id)

        alert_context = self._build_alert_context(alert, context_docs, detection_rule)

        user_message = (
            "Investigate this security alert and produce your finding.\n\n"
            f"{alert_context}"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            temperature=0,
            messages=[
                {"role": "system", "content": self._build_system_prompt()},
                {"role": "user", "content": user_message},
            ],
        )

        usage = response.usage
        if usage:
            metrics.input_tokens = usage.prompt_tokens
            metrics.output_tokens = usage.completion_tokens

        finding_text = response.choices[0].message.content or ""
        metrics.finding = finding_text

        try:
            self._post_finding(
                alert_uuid=alert_uuid,
                summary=finding_text[:50_000],
                confidence="medium",
                action="Review finding and take recommended actions.",
            )
        except Exception:
            pass

        metrics.duration_seconds = time.monotonic() - start
        metrics.total_tokens = metrics.input_tokens + metrics.output_tokens
        metrics.estimated_cost_usd = (
            (metrics.input_tokens / 1_000_000) * self.INPUT_COST_PER_M
            + (metrics.output_tokens / 1_000_000) * self.OUTPUT_COST_PER_M
        )

        metrics.tool_calls = 0
        metrics.external_api_calls = 0

        return metrics

    def close(self) -> None:
        self.http.close()
