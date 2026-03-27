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

import re
import time
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from app.schemas.enrichment import EnrichmentResult
from app.schemas.enrichment_providers import HttpStepDebug
from app.services.url_validation import validate_outbound_url

from .field_extractor import FieldExtractor
from .malice_evaluator import MaliceRuleEvaluator
from .template_resolver import TemplateResolver

logger = structlog.get_logger(__name__)

_SENSITIVE_HEADER_RE = re.compile(
    r"(authorization|api[_-]?key|apikey|token|secret|password|x-api-key)",
    re.IGNORECASE,
)
_MAX_DEBUG_BODY_SIZE = 50_000  # 50KB cap for response bodies in debug output


def _mask_value(value: str) -> str:
    """Mask a sensitive string: show first 4 + **** + last 4, or just **** if short."""
    if len(value) <= 8:
        return "****"
    return value[:4] + "****" + value[-4:]


def mask_sensitive_headers(
    headers: dict[str, str],
    auth_values: list[str],
) -> dict[str, str]:
    """Mask sensitive header values for debug output."""
    masked: dict[str, str] = {}
    for name, value in headers.items():
        if _SENSITIVE_HEADER_RE.search(name) or any(av and av in value for av in auth_values):
            masked[name] = _mask_value(value)
        else:
            masked[name] = value
    return masked


def mask_auth_values_in_url(url: str, auth_values: list[str]) -> str:
    """Mask auth values that appear in URL query params."""
    result = url
    for av in auth_values:
        if av and av in result:
            result = result.replace(av, _mask_value(av))
    return result


def _truncate_body(body: Any) -> Any:
    """Truncate response body if serialized form exceeds size cap."""
    import json as _json

    try:
        serialized = _json.dumps(body)
    except (TypeError, ValueError):
        return body
    if len(serialized) <= _MAX_DEBUG_BODY_SIZE:
        return body
    # Return truncated string representation with marker
    return {"_truncated": True, "_preview": serialized[:_MAX_DEBUG_BODY_SIZE]}


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
        capture_debug: bool = False,
    ) -> EnrichmentResult:
        """Execute the enrichment pipeline. Never raises — returns failure_result."""
        try:
            return await self._execute_inner(
                indicator_value, indicator_type, auth_config, capture_debug
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
        capture_debug: bool = False,
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
        debug_steps: list[HttpStepDebug] = []

        # Collect auth values for masking (flat list of all resolved credential values)
        auth_values = [str(v) for v in auth_config.values() if v] if capture_debug else []

        async with httpx.AsyncClient() as client:
            for i, step in enumerate(steps):
                step_name = step.get("name", f"step_{i}")
                is_optional = step.get("optional", False)

                # Determine URL: type-specific override for first step, or step URL
                if i == 0 and type_url:
                    url_template = type_url
                else:
                    url_template = step.get("url", "")

                url = resolver.resolve_url(url_template)

                # SSRF protection — block requests to private/internal addresses
                try:
                    validate_outbound_url(url)
                except ValueError as exc:
                    if is_optional:
                        logger.warning(
                            "enrichment_step_ssrf_blocked_optional",
                            provider=self._provider_name,
                            step=step_name,
                            url=url,
                            reason=str(exc),
                        )
                        continue
                    result = EnrichmentResult.failure_result(
                        self._provider_name,
                        f"Step '{step_name}' SSRF blocked: {exc}",
                    )
                    if capture_debug:
                        result.debug_steps = debug_steps
                    return result

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
                resolved_params = None
                if "query_params" in step:
                    resolved_params = resolver.resolve_value(step["query_params"])
                    request_kwargs["params"] = resolved_params

                # Handle body
                resolved_body = None
                if "json_body" in step:
                    resolved_body = resolver.resolve_value(step["json_body"])
                    request_kwargs["json"] = resolved_body
                elif "form_body" in step:
                    resolved_body = resolver.resolve_value(step["form_body"])
                    request_kwargs["data"] = resolved_body

                # Build debug step (before request)
                step_debug: HttpStepDebug | None = None
                if capture_debug:
                    masked_headers = mask_sensitive_headers(
                        {k: str(v) for k, v in headers.items()}, auth_values
                    )
                    masked_url = mask_auth_values_in_url(url, auth_values)
                    masked_params = None
                    if resolved_params:
                        masked_params = {
                            k: (
                                _mask_value(str(v))
                                if any(av and av in str(v) for av in auth_values)
                                else str(v)
                            )
                            for k, v in resolved_params.items()
                        }
                    step_debug = HttpStepDebug(
                        step_name=step_name,
                        step_index=i,
                        indicator_value=indicator_value,
                        request_method=method,
                        request_url=masked_url,
                        request_headers=masked_headers,
                        request_query_params=masked_params,
                        request_body=resolved_body,
                    )

                step_start = time.monotonic()
                try:
                    response = await client.request(**request_kwargs)
                except Exception as exc:
                    if capture_debug and step_debug:
                        step_debug.duration_ms = int((time.monotonic() - step_start) * 1000)
                        step_debug.error = str(exc)
                        debug_steps.append(step_debug)
                    if is_optional:
                        logger.warning(
                            "enrichment_step_optional_failed",
                            provider=self._provider_name,
                            step=step_name,
                            error=str(exc),
                        )
                        continue
                    result = EnrichmentResult.failure_result(
                        self._provider_name,
                        f"Step '{step_name}' failed: {exc}",
                    )
                    if capture_debug:
                        result.debug_steps = debug_steps
                    return result

                step_duration = int((time.monotonic() - step_start) * 1000)

                # Fill debug response info
                if capture_debug and step_debug:
                    step_debug.duration_ms = step_duration
                    step_debug.response_status_code = response.status_code
                    resp_headers = dict(response.headers)
                    step_debug.response_headers = mask_sensitive_headers(resp_headers, auth_values)
                    try:
                        resp_body = response.json()
                        step_debug.response_body = _truncate_body(resp_body)
                    except Exception:
                        step_debug.response_body = {"_raw_text": response.text[:2000]}
                    debug_steps.append(step_debug)

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
                        if capture_debug and step_debug:
                            step_debug.skipped = True
                        continue
                    result = EnrichmentResult.failure_result(
                        self._provider_name,
                        f"Step '{step_name}' returned HTTP {response.status_code}",
                    )
                    if capture_debug:
                        result.debug_steps = debug_steps
                    return result

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
            result = EnrichmentResult.success_result(
                provider_name=self._provider_name,
                extracted={"found": False, "malice": verdict},
                raw=raw_response,
                enriched_at=datetime.now(UTC),
            )
            if capture_debug:
                result.debug_steps = debug_steps
            return result

        # Extract fields
        extractor = FieldExtractor(self._field_extractions)
        extracted = extractor.extract(raw_response)

        # Evaluate malice
        evaluator = MaliceRuleEvaluator(self._malice_rules)
        verdict = evaluator.evaluate(raw_response)
        extracted["malice"] = verdict

        result = EnrichmentResult.success_result(
            provider_name=self._provider_name,
            extracted=extracted,
            raw=raw_response,
            enriched_at=datetime.now(UTC),
        )
        if capture_debug:
            result.debug_steps = debug_steps
        return result
