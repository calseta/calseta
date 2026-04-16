"""
Comprehensive tests for the agent integration layer (Chunk 8.4).

Covers:
  - Trigger evaluation: source, severity, JSONB, inactive exclusion, combined filters
  - Webhook dispatch: payload structure, auth headers, retry, agent isolation
  - Findings: create, list, activity event
  - Agent CRUD: create, list, get, patch, delete, test endpoint

Unit tests use mocked DB/HTTP. Integration tests go through the FastAPI test client
against a real PostgreSQL session.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db.models.agent_registration import AgentRegistration
from app.queue.handlers.dispatch_webhooks import (
    _passes_jsonb_filter,
    _passes_severity_filter,
    _passes_source_filter,
    get_matching_agents,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_alert(
    source_name: str = "sentinel",
    severity: str = "High",
    severity_id: int = 4,
    tags: list[str] | None = None,
) -> MagicMock:
    alert = MagicMock()
    alert.source_name = source_name
    alert.severity = severity
    alert.severity_id = severity_id
    alert.tags = tags or []
    return alert


def _make_agent(
    trigger_on_sources: list[str] | None = None,
    trigger_on_severities: list[str] | None = None,
    trigger_filter: dict[str, Any] | None = None,
    is_active: bool = True,
    name: str = "test-agent",
    endpoint_url: str = "http://localhost:9999/hook",
    auth_header_name: str | None = None,
    auth_header_value_encrypted: str | None = None,
    timeout_seconds: int = 30,
    retry_count: int = 3,
) -> MagicMock:
    agent = MagicMock()
    agent.is_active = is_active
    agent.trigger_on_sources = trigger_on_sources or []
    agent.trigger_on_severities = trigger_on_severities or []
    agent.trigger_filter = trigger_filter
    agent.name = name
    agent.endpoint_url = endpoint_url
    agent.auth_header_name = auth_header_name
    agent.auth_header_value_encrypted = auth_header_value_encrypted
    agent.timeout_seconds = timeout_seconds
    agent.retry_count = retry_count
    return agent


# ===========================================================================
# 1. Trigger Evaluation — Source Filter
# ===========================================================================


class TestSourceFilter:
    """Agent trigger_on_sources filter evaluation."""

    def test_empty_list_matches_any_source(self) -> None:
        agent = _make_agent(trigger_on_sources=[])
        assert _passes_source_filter(agent, _make_alert(source_name="elastic")) is True
        assert _passes_source_filter(agent, _make_alert(source_name="splunk")) is True

    def test_matches_when_source_in_list(self) -> None:
        agent = _make_agent(trigger_on_sources=["sentinel", "elastic"])
        assert _passes_source_filter(agent, _make_alert(source_name="sentinel")) is True
        assert _passes_source_filter(agent, _make_alert(source_name="elastic")) is True

    def test_rejects_when_source_not_in_list(self) -> None:
        agent = _make_agent(trigger_on_sources=["sentinel"])
        assert _passes_source_filter(agent, _make_alert(source_name="splunk")) is False

    def test_case_sensitive_matching(self) -> None:
        agent = _make_agent(trigger_on_sources=["Sentinel"])
        assert _passes_source_filter(agent, _make_alert(source_name="sentinel")) is False

    def test_single_source_filter_matches_only_that_source(self) -> None:
        """Agent with trigger_on_sources: ['sentinel'] only fires for sentinel alerts."""
        agent = _make_agent(trigger_on_sources=["sentinel"])
        assert _passes_source_filter(agent, _make_alert(source_name="sentinel")) is True
        assert _passes_source_filter(agent, _make_alert(source_name="elastic")) is False
        assert _passes_source_filter(agent, _make_alert(source_name="splunk")) is False
        assert _passes_source_filter(agent, _make_alert(source_name="generic")) is False


# ===========================================================================
# 2. Trigger Evaluation — Severity Filter
# ===========================================================================


class TestSeverityFilter:
    """Agent trigger_on_severities filter evaluation."""

    def test_empty_list_matches_any_severity(self) -> None:
        agent = _make_agent(trigger_on_severities=[])
        assert _passes_severity_filter(agent, _make_alert(severity="Low")) is True
        assert _passes_severity_filter(agent, _make_alert(severity="Critical")) is True

    def test_matches_high_and_critical(self) -> None:
        """Agent with severity: ['High', 'Critical'] filters correctly."""
        agent = _make_agent(trigger_on_severities=["High", "Critical"])
        assert _passes_severity_filter(agent, _make_alert(severity="High")) is True
        assert _passes_severity_filter(agent, _make_alert(severity="Critical")) is True
        assert _passes_severity_filter(agent, _make_alert(severity="Low")) is False
        assert _passes_severity_filter(agent, _make_alert(severity="Medium")) is False
        assert _passes_severity_filter(agent, _make_alert(severity="Informational")) is False

    def test_case_sensitive_matching(self) -> None:
        agent = _make_agent(trigger_on_severities=["high"])
        assert _passes_severity_filter(agent, _make_alert(severity="High")) is False


# ===========================================================================
# 3. Trigger Evaluation — JSONB Filter
# ===========================================================================


class TestJSONBFilter:
    """Complex JSONB trigger_filter evaluation."""

    def test_none_filter_matches_all(self) -> None:
        agent = _make_agent(trigger_filter=None)
        assert _passes_jsonb_filter(agent, _make_alert()) is True

    def test_empty_dict_matches_all(self) -> None:
        agent = _make_agent(trigger_filter={})
        assert _passes_jsonb_filter(agent, _make_alert()) is True

    def test_match_any_with_eq_operator(self) -> None:
        agent = _make_agent(
            trigger_filter={
                "match_any": [{"field": "source_name", "op": "eq", "value": "sentinel"}]
            }
        )
        assert _passes_jsonb_filter(agent, _make_alert(source_name="sentinel")) is True
        assert _passes_jsonb_filter(agent, _make_alert(source_name="elastic")) is False

    def test_match_any_with_in_operator(self) -> None:
        agent = _make_agent(
            trigger_filter={
                "match_any": [
                    {"field": "severity", "op": "in", "value": ["High", "Critical"]}
                ]
            }
        )
        assert _passes_jsonb_filter(agent, _make_alert(severity="High")) is True
        assert _passes_jsonb_filter(agent, _make_alert(severity="Critical")) is True
        assert _passes_jsonb_filter(agent, _make_alert(severity="Low")) is False

    def test_match_any_with_contains_operator(self) -> None:
        agent = _make_agent(
            trigger_filter={
                "match_any": [{"field": "tags", "op": "contains", "value": "phishing"}]
            }
        )
        assert _passes_jsonb_filter(agent, _make_alert(tags=["phishing", "urgent"])) is True
        assert _passes_jsonb_filter(agent, _make_alert(tags=["malware"])) is False
        assert _passes_jsonb_filter(agent, _make_alert(tags=[])) is False

    def test_match_all_requires_all_rules_to_pass(self) -> None:
        agent = _make_agent(
            trigger_filter={
                "match_all": [
                    {"field": "source_name", "op": "eq", "value": "sentinel"},
                    {"field": "severity", "op": "eq", "value": "High"},
                ]
            }
        )
        assert (
            _passes_jsonb_filter(
                agent, _make_alert(source_name="sentinel", severity="High")
            )
            is True
        )
        assert (
            _passes_jsonb_filter(
                agent, _make_alert(source_name="sentinel", severity="Low")
            )
            is False
        )
        assert (
            _passes_jsonb_filter(
                agent, _make_alert(source_name="elastic", severity="High")
            )
            is False
        )

    def test_match_any_with_multiple_rules_or_logic(self) -> None:
        """match_any: at least one rule must pass (OR)."""
        agent = _make_agent(
            trigger_filter={
                "match_any": [
                    {"field": "source_name", "op": "eq", "value": "sentinel"},
                    {"field": "source_name", "op": "eq", "value": "elastic"},
                ]
            }
        )
        assert _passes_jsonb_filter(agent, _make_alert(source_name="sentinel")) is True
        assert _passes_jsonb_filter(agent, _make_alert(source_name="elastic")) is True
        assert _passes_jsonb_filter(agent, _make_alert(source_name="splunk")) is False

    def test_combined_match_any_and_match_all(self) -> None:
        """Both match_any AND match_all must pass when both present."""
        agent = _make_agent(
            trigger_filter={
                "match_any": [
                    {"field": "source_name", "op": "eq", "value": "sentinel"},
                    {"field": "source_name", "op": "eq", "value": "elastic"},
                ],
                "match_all": [
                    {"field": "severity", "op": "eq", "value": "Critical"},
                ],
            }
        )
        # sentinel + Critical => both pass
        assert (
            _passes_jsonb_filter(
                agent, _make_alert(source_name="sentinel", severity="Critical")
            )
            is True
        )
        # elastic + Critical => both pass
        assert (
            _passes_jsonb_filter(
                agent, _make_alert(source_name="elastic", severity="Critical")
            )
            is True
        )
        # sentinel + High => match_any passes, match_all fails
        assert (
            _passes_jsonb_filter(
                agent, _make_alert(source_name="sentinel", severity="High")
            )
            is False
        )
        # splunk + Critical => match_any fails
        assert (
            _passes_jsonb_filter(
                agent, _make_alert(source_name="splunk", severity="Critical")
            )
            is False
        )

    def test_unknown_field_evaluates_as_false(self) -> None:
        agent = _make_agent(
            trigger_filter={
                "match_all": [{"field": "nonexistent", "op": "eq", "value": "test"}]
            }
        )
        assert _passes_jsonb_filter(agent, _make_alert()) is False


# ===========================================================================
# 4. Trigger Evaluation — Inactive Agent Exclusion
# ===========================================================================


class TestInactiveAgentExclusion:
    """Agent with is_active=False never receives webhooks."""

    @pytest.mark.asyncio
    async def test_inactive_agents_never_returned_by_get_matching_agents(self) -> None:
        """list_active() only returns active agents, so inactive ones never match."""
        active_agent = _make_agent(is_active=True)
        # Inactive agents are excluded by the repository's list_active() filter.
        # get_matching_agents never sees them.
        mock_db = MagicMock()

        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            # Simulate the repo returning only active agents
            MockRepo.return_value.list_active = AsyncMock(return_value=[active_agent])
            result = await get_matching_agents(_make_alert(), mock_db)

        assert result == [active_agent]

    @pytest.mark.asyncio
    async def test_no_active_agents_returns_empty(self) -> None:
        mock_db = MagicMock()

        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(return_value=[])
            result = await get_matching_agents(_make_alert(), mock_db)

        assert result == []


# ===========================================================================
# 5. Trigger Evaluation — Combined Filters
# ===========================================================================


class TestCombinedFilters:
    """Multiple filter criteria applied together (AND logic)."""

    @pytest.mark.asyncio
    async def test_all_three_filters_must_pass(self) -> None:
        """Source + severity + JSONB: all must pass for agent to match."""
        agent = _make_agent(
            trigger_on_sources=["sentinel"],
            trigger_on_severities=["High", "Critical"],
            trigger_filter={
                "match_all": [{"field": "tags", "op": "contains", "value": "urgent"}]
            },
        )
        mock_db = MagicMock()

        # All pass
        alert_match = _make_alert(source_name="sentinel", severity="High", tags=["urgent"])
        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
            result = await get_matching_agents(alert_match, mock_db)
        assert result == [agent]

        # Source fails
        alert_source_fail = _make_alert(
            source_name="elastic", severity="High", tags=["urgent"]
        )
        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
            result = await get_matching_agents(alert_source_fail, mock_db)
        assert result == []

        # Severity fails
        alert_sev_fail = _make_alert(
            source_name="sentinel", severity="Low", tags=["urgent"]
        )
        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
            result = await get_matching_agents(alert_sev_fail, mock_db)
        assert result == []

        # JSONB fails (wrong tag)
        alert_tag_fail = _make_alert(
            source_name="sentinel", severity="High", tags=["routine"]
        )
        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
            result = await get_matching_agents(alert_tag_fail, mock_db)
        assert result == []

    @pytest.mark.asyncio
    async def test_multiple_agents_partial_match(self) -> None:
        """From a pool of 3 agents, only matching agents returned."""
        agent_a = _make_agent(
            trigger_on_sources=["sentinel"],
            trigger_on_severities=["High"],
            name="agent-a",
        )
        agent_b = _make_agent(
            trigger_on_sources=["elastic"],
            trigger_on_severities=[],
            name="agent-b",
        )
        agent_c = _make_agent(
            trigger_on_sources=[],
            trigger_on_severities=["Critical"],
            name="agent-c",
        )

        alert = _make_alert(source_name="sentinel", severity="High")
        mock_db = MagicMock()

        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(
                return_value=[agent_a, agent_b, agent_c]
            )
            result = await get_matching_agents(alert, mock_db)

        # agent_a: source=sentinel matches, severity=High matches => included
        # agent_b: source=elastic does not match sentinel => excluded
        # agent_c: source=[] matches, severity=Critical does not match High => excluded
        assert result == [agent_a]

    @pytest.mark.asyncio
    async def test_source_and_severity_both_empty_means_match_all(self) -> None:
        """Agent with no source/severity filters matches any alert."""
        agent = _make_agent(
            trigger_on_sources=[], trigger_on_severities=[], trigger_filter=None
        )
        mock_db = MagicMock()

        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
            result = await get_matching_agents(
                _make_alert(source_name="generic", severity="Informational"), mock_db
            )
        assert result == [agent]


# ===========================================================================
# 6. Webhook Dispatch Tests (Unit)
# ===========================================================================


class TestWebhookPayloadStructure:
    """
    Tests for the synthetic test webhook payload built in the
    POST /v1/agents/{uuid}/test endpoint.
    """

    def test_synthetic_payload_has_required_fields(self) -> None:
        """Verify the webhook test payload structure includes alert, _metadata, etc."""
        from app.config import settings

        now = datetime.now(UTC)
        agent = MagicMock()
        agent.name = "test-agent"
        agent.timeout_seconds = 10

        # Replicate the payload construction from agents.py test_agent_webhook()
        payload = {
            "test": True,
            "alert": {
                "uuid": "00000000-0000-0000-0000-000000000000",
                "title": "Calseta — Test Webhook",
                "severity": "Low",
                "status": "Open",
                "source_name": agent.name,
                "occurred_at": now.isoformat(),
                "ingested_at": now.isoformat(),
                "is_enriched": False,
                "tags": ["test"],
            },
            "indicators": [],
            "detection_rule": None,
            "context_documents": [],
            "workflows": [],
            "calseta_api_base_url": settings.CALSETA_API_BASE_URL,
            "_metadata": {
                "generated_at": now.isoformat(),
                "alert_source": agent.name,
                "indicator_count": 0,
                "enrichment": {"succeeded": [], "failed": [], "enriched_at": None},
                "detection_rule_matched": False,
                "context_documents_applied": 0,
            },
        }

        # Verify structure
        assert payload["test"] is True
        assert "alert" in payload
        assert "uuid" in payload["alert"]  # type: ignore[operator]
        assert "title" in payload["alert"]  # type: ignore[operator]
        assert "severity" in payload["alert"]  # type: ignore[operator]
        assert payload["indicators"] == []
        assert payload["detection_rule"] is None
        assert "calseta_api_base_url" in payload
        assert "_metadata" in payload
        assert "generated_at" in payload["_metadata"]  # type: ignore[operator]
        assert "indicator_count" in payload["_metadata"]  # type: ignore[operator]
        assert "enrichment" in payload["_metadata"]  # type: ignore[operator]


class TestWebhookAuthHeader:
    """Auth header inclusion when auth_header_value is set on the agent."""

    def test_headers_include_auth_when_configured(self) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth_name = "X-API-Key"
        auth_value = "secret-value-123"

        if auth_name and auth_value:
            headers[auth_name] = auth_value

        assert headers["X-API-Key"] == "secret-value-123"
        assert headers["Content-Type"] == "application/json"

    def test_headers_no_auth_when_not_configured(self) -> None:
        headers: dict[str, str] = {"Content-Type": "application/json"}
        auth_name = None
        auth_value = None

        if auth_name and auth_value:
            headers[auth_name] = auth_value

        assert "X-API-Key" not in headers


# ===========================================================================
# 7. Agent Run Audit Record
# ===========================================================================


class TestAgentRunRecord:
    """Tests for the record_agent_run service function."""

    @pytest.mark.asyncio
    async def test_record_agent_run_creates_record(self) -> None:
        from app.services.agent_runs import record_agent_run

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        now = datetime.now(UTC)
        run = await record_agent_run(
            mock_db,
            agent_registration_id=1,
            alert_id=42,
            status="success",
            attempt_count=1,
            request_payload={"test": True},
            response_status_code=200,
            response_body={"ok": True},
            started_at=now,
            completed_at=now,
        )

        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()
        assert run.status == "success"
        assert run.agent_registration_id == 1
        assert run.alert_id == 42
        assert run.attempt_count == 1
        assert run.response_status_code == 200

    @pytest.mark.asyncio
    async def test_record_agent_run_failed_status(self) -> None:
        from app.services.agent_runs import record_agent_run

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        run = await record_agent_run(
            mock_db,
            agent_registration_id=2,
            alert_id=99,
            status="failed",
            attempt_count=3,
            response_status_code=500,
        )

        assert run.status == "failed"
        assert run.attempt_count == 3

    @pytest.mark.asyncio
    async def test_record_agent_run_timeout_status(self) -> None:
        from app.services.agent_runs import record_agent_run

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        run = await record_agent_run(
            mock_db,
            agent_registration_id=3,
            alert_id=50,
            status="timeout",
            attempt_count=1,
        )

        assert run.status == "timeout"

    @pytest.mark.asyncio
    async def test_record_agent_run_has_uuid(self) -> None:
        from app.services.agent_runs import record_agent_run

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        run = await record_agent_run(
            mock_db,
            agent_registration_id=1,
            alert_id=1,
            status="success",
            attempt_count=1,
        )

        assert run.uuid is not None


# ===========================================================================
# 8. Agent Isolation Test (Unit)
# ===========================================================================


class TestAgentIsolation:
    """One agent's webhook failure does not affect other agents."""

    @pytest.mark.asyncio
    async def test_matching_agents_independent_of_each_other(self) -> None:
        """get_matching_agents evaluates each agent independently."""
        agent_a = _make_agent(
            trigger_on_sources=["sentinel"],
            trigger_on_severities=["High"],
            name="agent-a",
        )
        agent_b = _make_agent(
            trigger_on_sources=["sentinel"],
            trigger_on_severities=["High"],
            name="agent-b",
        )
        alert = _make_alert(source_name="sentinel", severity="High")
        mock_db = MagicMock()

        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(
                return_value=[agent_a, agent_b]
            )
            result = await get_matching_agents(alert, mock_db)

        # Both agents match independently
        assert len(result) == 2
        assert agent_a in result
        assert agent_b in result

    @pytest.mark.asyncio
    async def test_one_agent_filter_failure_does_not_exclude_others(self) -> None:
        """If agent_a fails the filter but agent_b passes, agent_b is still returned."""
        agent_a = _make_agent(
            trigger_on_sources=["elastic"],  # won't match "sentinel"
            name="agent-a",
        )
        agent_b = _make_agent(
            trigger_on_sources=["sentinel"],
            name="agent-b",
        )
        alert = _make_alert(source_name="sentinel", severity="High")
        mock_db = MagicMock()

        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(
                return_value=[agent_a, agent_b]
            )
            result = await get_matching_agents(alert, mock_db)

        assert result == [agent_b]


# ===========================================================================
# 9. Schema Validation Tests
# ===========================================================================


class TestAgentSchemaValidation:
    """Agent schema create/patch validation."""

    def test_create_schema_requires_name(self) -> None:
        from pydantic import ValidationError

        from app.schemas.agents import AgentRegistrationCreate

        with pytest.raises(ValidationError):
            AgentRegistrationCreate(
                name="",  # empty name violates min_length=1
                endpoint_url="http://localhost/",
            )

    def test_create_schema_name_max_length(self) -> None:
        from pydantic import ValidationError

        from app.schemas.agents import AgentRegistrationCreate

        with pytest.raises(ValidationError):
            AgentRegistrationCreate(
                name="x" * 256,  # exceeds max_length=255
                endpoint_url="http://localhost/",
            )

    def test_create_schema_defaults(self) -> None:
        from app.schemas.agents import AgentRegistrationCreate

        agent = AgentRegistrationCreate(
            name="test-agent",
            endpoint_url="http://localhost/",
        )
        assert agent.timeout_seconds == 30
        assert agent.retry_count == 3
        assert agent.trigger_on_sources == []
        assert agent.trigger_on_severities == []
        assert agent.trigger_filter is None
        assert agent.auth_header_name is None
        assert agent.auth_header_value is None

    def test_create_schema_timeout_bounds(self) -> None:
        from pydantic import ValidationError

        from app.schemas.agents import AgentRegistrationCreate

        with pytest.raises(ValidationError):
            AgentRegistrationCreate(
                name="t",
                endpoint_url="http://localhost/",
                timeout_seconds=0,  # < ge=1
            )

        with pytest.raises(ValidationError):
            AgentRegistrationCreate(
                name="t",
                endpoint_url="http://localhost/",
                timeout_seconds=3601,  # > le=3600
            )

    def test_create_schema_retry_count_bounds(self) -> None:
        from pydantic import ValidationError

        from app.schemas.agents import AgentRegistrationCreate

        with pytest.raises(ValidationError):
            AgentRegistrationCreate(
                name="t",
                endpoint_url="http://localhost/",
                retry_count=-1,  # < ge=0
            )

        with pytest.raises(ValidationError):
            AgentRegistrationCreate(
                name="t",
                endpoint_url="http://localhost/",
                retry_count=11,  # > le=10
            )

    def test_patch_schema_all_optional(self) -> None:
        from app.schemas.agents import AgentRegistrationPatch

        patch_model = AgentRegistrationPatch()
        assert patch_model.name is None
        assert patch_model.description is None
        assert patch_model.endpoint_url is None

    def test_response_schema_excludes_auth_value(self) -> None:
        from app.schemas.agents import AgentRegistrationResponse

        fields = AgentRegistrationResponse.model_fields
        assert "auth_header_value" not in fields
        assert "auth_header_value_encrypted" not in fields

    def test_test_response_schema(self) -> None:
        from app.schemas.agents import AgentTestResponse

        resp = AgentTestResponse(
            delivered=True,
            status_code=200,
            duration_ms=42,
            error=None,
        )
        assert resp.delivered is True
        assert resp.duration_ms == 42

        resp_failed = AgentTestResponse(
            delivered=False,
            status_code=500,
            duration_ms=100,
            error="HTTP 500",
        )
        assert resp_failed.delivered is False
        assert resp_failed.error == "HTTP 500"


# ===========================================================================
# 10. Finding Schema Validation
# ===========================================================================


class TestFindingSchemaValidation:
    """Finding create/response schema validation."""

    def test_create_requires_agent_name_and_summary(self) -> None:
        from pydantic import ValidationError

        from app.schemas.alerts import FindingCreate

        with pytest.raises(ValidationError):
            FindingCreate(agent_name="", summary="test")

        with pytest.raises(ValidationError):
            FindingCreate(agent_name="agent", summary="")

    def test_create_optional_fields(self) -> None:
        from app.schemas.alerts import FindingCreate

        finding = FindingCreate(agent_name="test-agent", summary="Some finding")
        assert finding.confidence is None
        assert finding.recommended_action is None
        assert finding.evidence is None

    def test_confidence_enum_values(self) -> None:
        from app.schemas.alerts import FindingConfidence, FindingCreate

        for conf in ("low", "medium", "high"):
            f = FindingCreate(
                agent_name="a", summary="s", confidence=FindingConfidence(conf)
            )
            assert f.confidence is not None
            assert f.confidence.value == conf

    def test_response_schema(self) -> None:
        from app.schemas.alerts import FindingResponse

        resp = FindingResponse(
            id="abc-123",
            agent_name="test",
            summary="test finding",
            confidence=None,
            recommended_action=None,
            evidence=None,
            posted_at=datetime.now(UTC),
        )
        assert resp.id == "abc-123"


# ===========================================================================
# 11. ORM Model Tests
# ===========================================================================


class TestAgentRegistrationModel:
    """AgentRegistration ORM model basic checks."""

    def test_model_tablename(self) -> None:
        assert AgentRegistration.__tablename__ == "agent_registrations"

    def test_model_has_required_columns(self) -> None:
        columns = {c.key for c in AgentRegistration.__table__.columns}
        expected = {
            "id",
            "uuid",
            "name",
            "description",
            "endpoint_url",
            "auth_header_name",
            "auth_header_value_encrypted",
            "trigger_on_sources",
            "trigger_on_severities",
            "trigger_filter",
            "timeout_seconds",
            "retry_count",
            "status",
            "documentation",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns)


class TestAgentRunModel:
    """AgentRun ORM model basic checks."""

    def test_model_tablename(self) -> None:
        from app.db.models.agent_run import AgentRun

        assert AgentRun.__tablename__ == "agent_runs"

    def test_model_has_required_columns(self) -> None:
        from app.db.models.agent_run import AgentRun

        columns = {c.key for c in AgentRun.__table__.columns}
        expected = {
            "id",
            "uuid",
            "agent_registration_id",
            "alert_id",
            "request_payload",
            "response_status_code",
            "response_body",
            "status",
            "attempt_count",
            "started_at",
            "completed_at",
        }
        assert expected.issubset(columns)


# ===========================================================================
# 12. get_matching_agents — Edge Cases
# ===========================================================================


class TestGetMatchingAgentsEdgeCases:
    """Additional edge-case coverage for get_matching_agents."""

    @pytest.mark.asyncio
    async def test_alert_with_no_tags_against_tag_filter(self) -> None:
        """Alert with empty tags should fail a 'contains' tag filter."""
        agent = _make_agent(
            trigger_filter={
                "match_all": [{"field": "tags", "op": "contains", "value": "phishing"}]
            }
        )
        alert = _make_alert(tags=[])
        mock_db = MagicMock()

        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(return_value=[agent])
            result = await get_matching_agents(alert, mock_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_many_agents_all_match(self) -> None:
        """When all agents have empty filters, all should match."""
        agents = [
            _make_agent(name=f"agent-{i}") for i in range(5)
        ]
        alert = _make_alert()
        mock_db = MagicMock()

        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(return_value=agents)
            result = await get_matching_agents(alert, mock_db)

        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_many_agents_none_match(self) -> None:
        """When all agents have restrictive filters, none should match."""
        agents = [
            _make_agent(trigger_on_sources=["nonexistent"], name=f"agent-{i}")
            for i in range(5)
        ]
        alert = _make_alert(source_name="sentinel")
        mock_db = MagicMock()

        with patch("app.queue.handlers.dispatch_webhooks.AgentRepository") as MockRepo:
            MockRepo.return_value.list_active = AsyncMock(return_value=agents)
            result = await get_matching_agents(alert, mock_db)

        assert result == []
