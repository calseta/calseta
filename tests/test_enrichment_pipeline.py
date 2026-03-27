"""
Boundary tests for EnrichmentPipeline.run().

Tests the full pipeline with real internal components (FieldExtractor,
MaliceRuleEvaluator, TemplateResolver) and mock HTTP only. No source code
mocks of pipeline internals — httpx.AsyncClient is the only seam.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.schemas.enrichment import EnrichmentResult, EnrichmentStatus
from app.services.enrichment_pipeline import EnrichmentPipeline

# ---------------------------------------------------------------------------
# HTTP mock helpers (match pattern from test_enrichment_providers.py but
# adapted for engine's client.request() call path)
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, body: object, *, text: str = "") -> MagicMock:
    """Build a minimal fake httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.text = text or ""
    resp.headers = {}
    return resp


def _mock_async_client(*responses: MagicMock) -> MagicMock:
    """Return a mock httpx.AsyncClient CM whose .request() returns responses in order."""
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False

    if len(responses) == 1:
        mock_client.request.return_value = responses[0]
    else:
        mock_client.request.side_effect = list(responses)

    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls


def _mock_async_client_raising(exc: Exception) -> MagicMock:
    """Return a mock httpx.AsyncClient CM whose .request() raises."""
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    mock_client.request.side_effect = exc
    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls


# ---------------------------------------------------------------------------
# Reusable config builders
# ---------------------------------------------------------------------------

_SINGLE_STEP_HTTP_CONFIG = {
    "steps": [
        {
            "name": "lookup",
            "url": "https://api.example.com/v1/ip/{{indicator.value}}",
            "method": "GET",
            "headers": {"X-Api-Key": "{{auth.api_key}}"},
            "expected_status": [200],
            "not_found_status": [404],
            "timeout_seconds": 10,
        }
    ]
}

_SINGLE_STEP_FIELD_EXTRACTIONS = [
    {"source_path": "data.score", "target_key": "score", "value_type": "int", "is_active": True},
    {
        "source_path": "data.country",
        "target_key": "country",
        "value_type": "string",
        "is_active": True,
    },
    {
        "source_path": "data.reports",
        "target_key": "reports",
        "value_type": "int",
        "is_active": True,
    },
]

_SINGLE_STEP_MALICE_RULES = {
    "rules": [
        {"field": "data.score", "operator": ">=", "value": 75, "verdict": "Malicious"},
        {"field": "data.score", "operator": ">=", "value": 25, "verdict": "Suspicious"},
    ],
    "default_verdict": "Benign",
    "not_found_verdict": "Pending",
}


# ---------------------------------------------------------------------------
# a. Single-step provider (happy path)
# ---------------------------------------------------------------------------


class TestSingleStepHappyPath:
    async def test_success_with_extracted_and_malice(self) -> None:
        pipeline = EnrichmentPipeline(
            provider_name="test_provider",
            http_config=_SINGLE_STEP_HTTP_CONFIG,
            malice_rules=_SINGLE_STEP_MALICE_RULES,
            field_extractions=_SINGLE_STEP_FIELD_EXTRACTIONS,
        )
        body = {"data": {"score": 90, "country": "RU", "reports": 42}}

        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await pipeline.run("8.8.8.8", "ip", {"api_key": "test-key"})

        assert result.success is True
        assert result.status == EnrichmentStatus.SUCCESS
        assert result.extracted is not None
        assert result.extracted["score"] == 90
        assert result.extracted["country"] == "RU"
        assert result.extracted["reports"] == 42
        assert result.extracted["malice"] == "Malicious"
        assert result.raw == body
        assert result.enriched_at is not None


# ---------------------------------------------------------------------------
# b. Multi-step provider (template chaining)
# ---------------------------------------------------------------------------


class TestMultiStepProvider:
    async def test_step2_references_step1_response(self) -> None:
        http_config = {
            "steps": [
                {
                    "name": "auth_step",
                    "url": "https://login.example.com/oauth/token",
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "json_body": {
                        "client_id": "{{auth.client_id}}",
                        "client_secret": "{{auth.client_secret}}",
                    },
                    "expected_status": [200],
                    "timeout_seconds": 10,
                },
                {
                    "name": "lookup",
                    "url": "https://api.example.com/v1/users/{{indicator.value}}",
                    "method": "GET",
                    "headers": {
                        "Authorization": "Bearer {{steps.auth_step.response.access_token}}"
                    },
                    "expected_status": [200],
                    "not_found_status": [404],
                    "timeout_seconds": 10,
                },
            ]
        }
        field_extractions = [
            {
                "source_path": "lookup.display_name",
                "target_key": "display_name",
                "value_type": "string",
                "is_active": True,
            },
            {
                "source_path": "lookup.status",
                "target_key": "status",
                "value_type": "string",
                "is_active": True,
            },
        ]
        malice_rules = {"rules": [], "default_verdict": "Benign", "not_found_verdict": "Pending"}

        token_resp = _mock_response(200, {"access_token": "tok_abc123", "expires_in": 3600})
        user_resp = _mock_response(200, {"display_name": "Alice", "status": "ACTIVE"})

        with patch("httpx.AsyncClient", _mock_async_client(token_resp, user_resp)):
            result = await pipeline_run(
                http_config,
                field_extractions,
                malice_rules,
                "alice@example.com",
                "account",
                {"client_id": "cid", "client_secret": "csec"},
            )

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["display_name"] == "Alice"
        assert result.extracted["status"] == "ACTIVE"
        # Multi-step raw is keyed by step name
        assert result.raw is not None
        assert "auth_step" in result.raw
        assert "lookup" in result.raw
        assert result.raw["auth_step"]["access_token"] == "tok_abc123"


# ---------------------------------------------------------------------------
# c. Field extraction with type coercion
# ---------------------------------------------------------------------------


class TestFieldExtractionCoercion:
    async def test_int_float_bool_string_coercion(self) -> None:
        http_config = {
            "steps": [
                {
                    "name": "lookup",
                    "url": "https://api.example.com/check/{{indicator.value}}",
                    "method": "GET",
                    "headers": {},
                    "expected_status": [200],
                    "timeout_seconds": 10,
                }
            ]
        }
        field_extractions = [
            {"source_path": "count", "target_key": "count", "value_type": "int", "is_active": True},
            {
                "source_path": "score",
                "target_key": "score",
                "value_type": "float",
                "is_active": True,
            },
            {
                "source_path": "is_active",
                "target_key": "is_active",
                "value_type": "bool",
                "is_active": True,
            },
            {
                "source_path": "label",
                "target_key": "label",
                "value_type": "string",
                "is_active": True,
            },
            # String numeric should coerce to int
            {
                "source_path": "str_num",
                "target_key": "str_num_as_int",
                "value_type": "int",
                "is_active": True,
            },
            # Bool from string "true"
            {
                "source_path": "str_bool",
                "target_key": "str_bool_coerced",
                "value_type": "bool",
                "is_active": True,
            },
        ]

        body = {
            "count": "42",  # string -> int
            "score": "3.14",  # string -> float
            "is_active": 1,  # int -> bool
            "label": 12345,  # int -> string
            "str_num": "99",  # string -> int
            "str_bool": "true",  # string -> bool
        }

        pipeline = EnrichmentPipeline(
            provider_name="test_coerce",
            http_config=http_config,
            malice_rules=None,
            field_extractions=field_extractions,
        )

        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await pipeline.run("test", "ip", {})

        assert result.success is True
        assert result.extracted is not None
        ext = result.extracted
        assert ext["count"] == 42
        assert isinstance(ext["count"], int)
        assert ext["score"] == pytest.approx(3.14)
        assert isinstance(ext["score"], float)
        assert ext["is_active"] is True
        assert ext["label"] == "12345"
        assert isinstance(ext["label"], str)
        assert ext["str_num_as_int"] == 99
        assert ext["str_bool_coerced"] is True


# ---------------------------------------------------------------------------
# d. Malice rule evaluation — all 4 verdicts
# ---------------------------------------------------------------------------


class TestMaliceVerdicts:
    @pytest.fixture
    def pipeline_factory(self) -> Any:
        """Factory that creates a pipeline with given malice rules."""

        def _make(malice_rules: dict[str, Any] | None) -> EnrichmentPipeline:
            return EnrichmentPipeline(
                provider_name="test_malice",
                http_config={
                    "steps": [
                        {
                            "name": "lookup",
                            "url": "https://api.example.com/{{indicator.value}}",
                            "method": "GET",
                            "headers": {},
                            "expected_status": [200],
                            "not_found_status": [404],
                            "timeout_seconds": 10,
                        }
                    ]
                },
                malice_rules=malice_rules,
                field_extractions=[
                    {
                        "source_path": "score",
                        "target_key": "score",
                        "value_type": "int",
                        "is_active": True,
                    },
                ],
            )

        return _make

    async def test_malicious_verdict(self, pipeline_factory: Any) -> None:
        rules = {
            "rules": [{"field": "score", "operator": ">=", "value": 80, "verdict": "Malicious"}],
            "default_verdict": "Benign",
            "not_found_verdict": "Pending",
        }
        body = {"score": 95}
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await pipeline_factory(rules).run("1.2.3.4", "ip", {})
        assert result.extracted is not None
        assert result.extracted["malice"] == "Malicious"

    async def test_suspicious_verdict(self, pipeline_factory: Any) -> None:
        rules = {
            "rules": [
                {"field": "score", "operator": ">=", "value": 80, "verdict": "Malicious"},
                {"field": "score", "operator": ">=", "value": 25, "verdict": "Suspicious"},
            ],
            "default_verdict": "Benign",
            "not_found_verdict": "Pending",
        }
        body = {"score": 50}
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await pipeline_factory(rules).run("1.2.3.4", "ip", {})
        assert result.extracted is not None
        assert result.extracted["malice"] == "Suspicious"

    async def test_benign_verdict(self, pipeline_factory: Any) -> None:
        rules = {
            "rules": [
                {"field": "score", "operator": ">=", "value": 80, "verdict": "Malicious"},
            ],
            "default_verdict": "Benign",
            "not_found_verdict": "Pending",
        }
        body = {"score": 5}
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await pipeline_factory(rules).run("1.2.3.4", "ip", {})
        assert result.extracted is not None
        assert result.extracted["malice"] == "Benign"

    async def test_pending_verdict_no_rules(self, pipeline_factory: Any) -> None:
        """No malice_rules at all -> Pending."""
        body = {"score": 50}
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, body))):
            result = await pipeline_factory(None).run("1.2.3.4", "ip", {})
        assert result.extracted is not None
        assert result.extracted["malice"] == "Pending"


# ---------------------------------------------------------------------------
# e. 404/not-found handling
# ---------------------------------------------------------------------------


class TestNotFoundHandling:
    async def test_404_returns_not_found_verdict(self) -> None:
        pipeline = EnrichmentPipeline(
            provider_name="test_404",
            http_config=_SINGLE_STEP_HTTP_CONFIG,
            malice_rules=_SINGLE_STEP_MALICE_RULES,
            field_extractions=_SINGLE_STEP_FIELD_EXTRACTIONS,
        )
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(404, {}))):
            result = await pipeline.run("0.0.0.0", "ip", {"api_key": "k"})

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["found"] is False
        assert result.extracted is not None
        assert result.extracted["malice"] == "Pending"  # not_found_verdict


# ---------------------------------------------------------------------------
# f. SSRF rejection
# ---------------------------------------------------------------------------


class TestSSRFRejection:
    async def test_metadata_ip_blocked(self) -> None:
        """Pipeline rejects requests to AWS metadata endpoint."""
        http_config = {
            "steps": [
                {
                    "name": "evil",
                    "url": "http://169.254.169.254/latest/meta-data/",
                    "method": "GET",
                    "headers": {},
                    "expected_status": [200],
                    "timeout_seconds": 10,
                }
            ]
        }
        pipeline = EnrichmentPipeline(
            provider_name="test_ssrf",
            http_config=http_config,
            malice_rules=None,
            field_extractions=[],
        )
        # Should NOT make any HTTP call — patch to verify
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, {}))):
            result = await pipeline.run("test", "ip", {})

        assert result.success is False
        assert "SSRF" in (result.error_message or "")

    async def test_private_ip_blocked(self) -> None:
        """Pipeline rejects requests to private RFC1918 addresses."""
        http_config = {
            "steps": [
                {
                    "name": "evil",
                    "url": "http://10.0.0.1:8080/admin",
                    "method": "GET",
                    "headers": {},
                    "expected_status": [200],
                    "timeout_seconds": 10,
                }
            ]
        }
        pipeline = EnrichmentPipeline(
            provider_name="test_ssrf_private",
            http_config=http_config,
            malice_rules=None,
            field_extractions=[],
        )
        with patch("httpx.AsyncClient", _mock_async_client(_mock_response(200, {}))):
            result = await pipeline.run("test", "ip", {})

        assert result.success is False
        assert (
            "SSRF" in (result.error_message or "")
            or "blocked" in (result.error_message or "").lower()
        )


# ---------------------------------------------------------------------------
# g. Timeout handling
# ---------------------------------------------------------------------------


class TestTimeoutHandling:
    async def test_timeout_returns_failure(self) -> None:
        pipeline = EnrichmentPipeline(
            provider_name="test_timeout",
            http_config=_SINGLE_STEP_HTTP_CONFIG,
            malice_rules=_SINGLE_STEP_MALICE_RULES,
            field_extractions=_SINGLE_STEP_FIELD_EXTRACTIONS,
        )
        timeout_exc = httpx.ReadTimeout("Read timed out")
        with patch("httpx.AsyncClient", _mock_async_client_raising(timeout_exc)):
            result = await pipeline.run("8.8.8.8", "ip", {"api_key": "k"})

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert (
            "timed out" in (result.error_message or "").lower()
            or "timeout" in (result.error_message or "").lower()
        )

    async def test_connect_timeout_returns_failure(self) -> None:
        pipeline = EnrichmentPipeline(
            provider_name="test_timeout",
            http_config=_SINGLE_STEP_HTTP_CONFIG,
            malice_rules=_SINGLE_STEP_MALICE_RULES,
            field_extractions=_SINGLE_STEP_FIELD_EXTRACTIONS,
        )
        with patch(
            "httpx.AsyncClient",
            _mock_async_client_raising(httpx.ConnectTimeout("Connect timed out")),
        ):
            result = await pipeline.run("8.8.8.8", "ip", {"api_key": "k"})

        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED


# ---------------------------------------------------------------------------
# h. Optional step failure
# ---------------------------------------------------------------------------


class TestOptionalStepFailure:
    async def test_optional_step_failure_still_succeeds(self) -> None:
        http_config = {
            "steps": [
                {
                    "name": "primary",
                    "url": "https://api.example.com/v1/ip/{{indicator.value}}",
                    "method": "GET",
                    "headers": {},
                    "expected_status": [200],
                    "timeout_seconds": 10,
                },
                {
                    "name": "supplementary",
                    "url": "https://api.example.com/v1/ip/{{indicator.value}}/extra",
                    "method": "GET",
                    "headers": {},
                    "expected_status": [200],
                    "timeout_seconds": 10,
                    "optional": True,
                },
            ]
        }
        field_extractions = [
            {
                "source_path": "primary.score",
                "target_key": "score",
                "value_type": "int",
                "is_active": True,
            },
        ]

        primary_resp = _mock_response(200, {"score": 42})
        # Supplementary returns 500 (unexpected status, but optional)
        supplementary_resp = _mock_response(500, {"error": "internal"})

        with patch("httpx.AsyncClient", _mock_async_client(primary_resp, supplementary_resp)):
            pipeline = EnrichmentPipeline(
                provider_name="test_optional",
                http_config=http_config,
                malice_rules={
                    "rules": [],
                    "default_verdict": "Benign",
                    "not_found_verdict": "Pending",
                },
                field_extractions=field_extractions,
            )
            result = await pipeline.run("8.8.8.8", "ip", {})

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["score"] == 42

    async def test_optional_step_http_exception_still_succeeds(self) -> None:
        """Optional step raises a network error — pipeline still succeeds."""
        http_config = {
            "steps": [
                {
                    "name": "primary",
                    "url": "https://api.example.com/v1/ip/{{indicator.value}}",
                    "method": "GET",
                    "headers": {},
                    "expected_status": [200],
                    "timeout_seconds": 10,
                },
                {
                    "name": "supplementary",
                    "url": "https://api.example.com/v1/ip/{{indicator.value}}/extra",
                    "method": "GET",
                    "headers": {},
                    "expected_status": [200],
                    "timeout_seconds": 10,
                    "optional": True,
                },
            ]
        }
        field_extractions = [
            {
                "source_path": "primary.score",
                "target_key": "score",
                "value_type": "int",
                "is_active": True,
            },
        ]

        primary_resp = _mock_response(200, {"score": 77})

        # Build mock client where second .request() call raises
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False
        mock_client.request.side_effect = [primary_resp, httpx.ReadTimeout("timeout")]
        mock_cls = MagicMock(return_value=mock_client)

        with patch("httpx.AsyncClient", mock_cls):
            pipeline = EnrichmentPipeline(
                provider_name="test_optional_exc",
                http_config=http_config,
                malice_rules={
                    "rules": [],
                    "default_verdict": "Benign",
                    "not_found_verdict": "Pending",
                },
                field_extractions=field_extractions,
            )
            result = await pipeline.run("8.8.8.8", "ip", {})

        assert result.success is True
        assert result.extracted is not None
        assert result.extracted["score"] == 77


# ---------------------------------------------------------------------------
# i. Provider exception isolation
# ---------------------------------------------------------------------------


class TestExceptionIsolation:
    async def test_run_never_raises(self) -> None:
        """Even on completely unexpected errors, run() returns EnrichmentResult."""
        pipeline = EnrichmentPipeline(
            provider_name="test_crash",
            http_config=_SINGLE_STEP_HTTP_CONFIG,
            malice_rules=_SINGLE_STEP_MALICE_RULES,
            field_extractions=_SINGLE_STEP_FIELD_EXTRACTIONS,
        )
        # Patch to raise an unexpected RuntimeError
        with patch(
            "httpx.AsyncClient", _mock_async_client_raising(RuntimeError("catastrophic failure"))
        ):
            result = await pipeline.run("8.8.8.8", "ip", {"api_key": "k"})

        assert isinstance(result, EnrichmentResult)
        assert result.success is False
        assert result.status == EnrichmentStatus.FAILED
        assert "catastrophic failure" in (result.error_message or "")

    async def test_no_steps_defined(self) -> None:
        """Empty http_config returns failure, never raises."""
        pipeline = EnrichmentPipeline(
            provider_name="test_empty",
            http_config={"steps": []},
            malice_rules=None,
            field_extractions=[],
        )
        result = await pipeline.run("test", "ip", {})
        assert isinstance(result, EnrichmentResult)
        assert result.success is False
        assert "No steps" in (result.error_message or "")

    async def test_malformed_json_response(self) -> None:
        """Response that fails json() parsing is handled gracefully."""
        pipeline = EnrichmentPipeline(
            provider_name="test_bad_json",
            http_config=_SINGLE_STEP_HTTP_CONFIG,
            malice_rules=None,
            field_extractions=[],
        )
        bad_resp = MagicMock()
        bad_resp.status_code = 200
        bad_resp.json.side_effect = ValueError("Invalid JSON")
        bad_resp.text = "<html>Not JSON</html>"
        bad_resp.headers = {}

        with patch("httpx.AsyncClient", _mock_async_client(bad_resp)):
            result = await pipeline.run("8.8.8.8", "ip", {"api_key": "k"})

        assert isinstance(result, EnrichmentResult)
        assert result.success is True
        # Raw should contain the fallback text
        assert result.raw is not None
        assert "_raw_text" in result.raw


# ---------------------------------------------------------------------------
# Helper for multi-step tests
# ---------------------------------------------------------------------------


async def pipeline_run(
    http_config: dict,
    field_extractions: list,
    malice_rules: dict | None,
    indicator_value: str,
    indicator_type: str,
    auth_config: dict,
) -> EnrichmentResult:
    """Convenience wrapper to create and run a pipeline."""
    pipeline = EnrichmentPipeline(
        provider_name="test_multi",
        http_config=http_config,
        malice_rules=malice_rules,
        field_extractions=field_extractions,
    )
    return await pipeline.run(indicator_value, indicator_type, auth_config)
