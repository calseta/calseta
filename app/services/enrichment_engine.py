"""
GenericHttpEnrichmentEngine — executes single or multi-step HTTP enrichment
configs and produces EnrichmentResult objects.

This is the core execution engine for database-driven enrichment providers.
It combines TemplateResolver, FieldExtractor, and MaliceRuleEvaluator to:

1. Resolve URL/header/body templates with indicator + auth + step context
2. Execute one or more HTTP steps sequentially
3. Extract fields from responses using enrichment_field_extractions rules
4. Evaluate malice rules against the response data
5. Return a standard EnrichmentResult

Single-step flow (VirusTotal, AbuseIPDB):
  - One HTTP call, field extraction against the response body

Multi-step flow (Okta, Entra):
  - Sequential HTTP calls; each step can reference previous step responses
  - Optional steps: if marked optional=True and fails, pipeline continues
  - Final response is merged from all step responses keyed by step name
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.schemas.enrichment import EnrichmentResult
from app.services.enrichment_template import TemplateResolver
from app.services.field_extractor import FieldExtractor
from app.services.malice_evaluator import MaliceRuleEvaluator

logger = structlog.get_logger(__name__)


class GenericHttpEnrichmentEngine:
    """Executes HTTP-based enrichment configs and returns EnrichmentResult."""

    def __init__(
        self,
        provider_name: str,
        http_config: dict[str, Any],
        malice_rules: dict[str, Any] | None,
        field_extractions: list[dict[str, Any]],
    ) -> None:
        self._provider_name = provider_name
        self._http_config = http_config
        self._malice_rules = malice_rules
        self._field_extractions = field_extractions

    async def execute(
        self,
        indicator_value: str,
        indicator_type: str,
        auth_config: dict[str, Any],
    ) -> EnrichmentResult:
        """Execute the enrichment pipeline. Never raises — returns failure_result."""
        try:
            return await self._execute_inner(
                indicator_value, indicator_type, auth_config
            )
        except Exception as exc:
            logger.exception(
                "enrichment_engine_error",
                provider=self._provider_name,
                indicator_type=indicator_type,
                value=indicator_value[:64],
            )
            return EnrichmentResult.failure_result(self._provider_name, str(exc))

    async def _execute_inner(
        self,
        indicator_value: str,
        indicator_type: str,
        auth_config: dict[str, Any],
    ) -> EnrichmentResult:
        steps = self._http_config.get("steps", [])
        if not steps:
            return EnrichmentResult.failure_result(
                self._provider_name, "No steps defined in http_config"
            )

        resolver = TemplateResolver(
            indicator_value=indicator_value,
            indicator_type=indicator_type,
            auth_config=auth_config,
        )

        # Resolve per-type URL override for the first step
        url_templates_by_type = self._http_config.get("url_templates_by_type", {})
        type_url = url_templates_by_type.get(indicator_type)

        step_responses: dict[str, dict[str, Any]] = {}
        not_found = False

        async with httpx.AsyncClient() as client:
            for i, step in enumerate(steps):
                step_name = step.get("name", f"step_{i}")
                is_optional = step.get("optional", False)

                # Determine URL: type-specific override for first step, or step URL
                if i == 0 and type_url:
                    url_template = type_url
                else:
                    url_template = step.get("url", "")

                url = resolver.resolve_string(url_template)
                method = step.get("method", "GET").upper()
                timeout = step.get("timeout_seconds", 30)

                # Resolve headers
                raw_headers = step.get("headers", {})
                headers = resolver.resolve_value(raw_headers)

                # Build request kwargs
                request_kwargs: dict[str, Any] = {
                    "method": method,
                    "url": url,
                    "headers": headers,
                    "timeout": float(timeout),
                }

                # Handle query parameters
                if "query_params" in step:
                    request_kwargs["params"] = resolver.resolve_value(step["query_params"])

                # Handle body
                if "json_body" in step:
                    request_kwargs["json"] = resolver.resolve_value(step["json_body"])
                elif "form_body" in step:
                    request_kwargs["data"] = resolver.resolve_value(step["form_body"])

                try:
                    response = await client.request(**request_kwargs)
                except Exception as exc:
                    if is_optional:
                        logger.warning(
                            "enrichment_step_optional_failed",
                            provider=self._provider_name,
                            step=step_name,
                            error=str(exc),
                        )
                        continue
                    return EnrichmentResult.failure_result(
                        self._provider_name,
                        f"Step '{step_name}' failed: {exc}",
                    )

                # Check not-found status
                not_found_statuses = step.get("not_found_status", [])
                if response.status_code in not_found_statuses:
                    not_found = True
                    step_responses[step_name] = {"status_code": response.status_code}
                    break

                # Check expected status
                expected_statuses = step.get("expected_status", [200])
                if response.status_code not in expected_statuses:
                    if is_optional:
                        logger.warning(
                            "enrichment_step_optional_bad_status",
                            provider=self._provider_name,
                            step=step_name,
                            status_code=response.status_code,
                        )
                        continue
                    return EnrichmentResult.failure_result(
                        self._provider_name,
                        f"Step '{step_name}' returned HTTP {response.status_code}",
                    )

                # Parse response
                try:
                    body = response.json()
                except Exception:
                    body = {"_raw_text": response.text[:2000]}

                step_responses[step_name] = body
                resolver.add_step_result(step_name, body)

        # Build raw response: single-step uses flat body, multi-step uses keyed
        if len(steps) == 1:
            first_step_name = steps[0].get("name", "step_0")
            raw_response = step_responses.get(first_step_name, {})
        else:
            raw_response = step_responses

        # Handle not-found case
        if not_found:
            evaluator = MaliceRuleEvaluator(self._malice_rules)
            verdict = evaluator.evaluate(raw_response, not_found=True)
            return EnrichmentResult.success_result(
                provider_name=self._provider_name,
                extracted={"found": False, "malice": verdict},
                raw=raw_response,
                enriched_at=datetime.now(UTC),
            )

        # Extract fields
        extractor = FieldExtractor(self._field_extractions)
        extracted = extractor.extract(raw_response)

        # Evaluate malice
        evaluator = MaliceRuleEvaluator(self._malice_rules)
        verdict = evaluator.evaluate(raw_response)
        extracted["malice"] = verdict

        return EnrichmentResult.success_result(
            provider_name=self._provider_name,
            extracted=extracted,
            raw=raw_response,
            enriched_at=datetime.now(UTC),
        )
