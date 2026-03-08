"""
Unit tests for MCP resources — read-only data retrieval.

The MCP server is a thin adapter over repositories and services. These tests
mock the DB/service layer and verify that each resource handler returns
correctly shaped JSON. No running database required.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared mock factories
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
_UUID_1 = uuid.uuid4()
_UUID_2 = uuid.uuid4()


def _mock_alert(
    *,
    alert_uuid: uuid.UUID | None = None,
    title: str = "Suspicious login",
    severity: str = "High",
    status: str = "Open",
    enrichment_status: str = "Pending",
    source_name: str = "sentinel",
    occurred_at: datetime = _NOW,
    ingested_at: datetime = _NOW,
    enriched_at: datetime | None = None,
    is_enriched: bool = False,
    tags: list[str] | None = None,
    close_classification: str | None = None,
    acknowledged_at: datetime | None = None,
    triaged_at: datetime | None = None,
    closed_at: datetime | None = None,
    detection_rule_id: int | None = None,
    agent_findings: list | None = None,
    id: int = 1,
) -> MagicMock:
    alert = MagicMock()
    alert.id = id
    alert.uuid = alert_uuid or _UUID_1
    alert.title = title
    alert.severity = severity
    alert.status = status
    alert.enrichment_status = enrichment_status
    alert.source_name = source_name
    alert.occurred_at = occurred_at
    alert.ingested_at = ingested_at
    alert.enriched_at = enriched_at
    alert.is_enriched = is_enriched
    alert.tags = tags or []
    alert.close_classification = close_classification
    alert.acknowledged_at = acknowledged_at
    alert.triaged_at = triaged_at
    alert.closed_at = closed_at
    alert.detection_rule_id = detection_rule_id
    alert.agent_findings = agent_findings
    alert.created_at = _NOW
    alert.updated_at = _NOW
    return alert


def _mock_indicator(
    *,
    ind_uuid: uuid.UUID | None = None,
    type: str = "ip",
    value: str = "1.2.3.4",
    malice: str = "Pending",
    is_enriched: bool = False,
    first_seen: datetime = _NOW,
    last_seen: datetime = _NOW,
    enrichment_results: dict | None = None,
) -> MagicMock:
    ind = MagicMock()
    ind.uuid = ind_uuid or uuid.uuid4()
    ind.type = type
    ind.value = value
    ind.malice = malice
    ind.is_enriched = is_enriched
    ind.first_seen = first_seen
    ind.last_seen = last_seen
    ind.enrichment_results = enrichment_results
    return ind


def _mock_detection_rule(
    *,
    rule_uuid: uuid.UUID | None = None,
    name: str = "Brute Force Login",
    source_rule_id: str | None = "rule-001",
    source_name: str | None = "sentinel",
    severity: str | None = "High",
    is_active: bool = True,
    mitre_tactics: list[str] | None = None,
    mitre_techniques: list[str] | None = None,
    mitre_subtechniques: list[str] | None = None,
    data_sources: list[str] | None = None,
    run_frequency: str | None = "5m",
    created_by: str | None = "cai_test",
    documentation: str | None = "Detects brute force login attempts.",
) -> MagicMock:
    rule = MagicMock()
    rule.id = 1
    rule.uuid = rule_uuid or uuid.uuid4()
    rule.name = name
    rule.source_rule_id = source_rule_id
    rule.source_name = source_name
    rule.severity = severity
    rule.is_active = is_active
    rule.mitre_tactics = mitre_tactics or ["Credential Access"]
    rule.mitre_techniques = mitre_techniques or ["T1110"]
    rule.mitre_subtechniques = mitre_subtechniques or []
    rule.data_sources = data_sources or ["windows_security"]
    rule.run_frequency = run_frequency
    rule.created_by = created_by
    rule.documentation = documentation
    rule.created_at = _NOW
    rule.updated_at = _NOW
    return rule


def _mock_context_document(
    *,
    doc_uuid: uuid.UUID | None = None,
    title: str = "Phishing Runbook",
    document_type: str = "runbook",
    is_global: bool = False,
    description: str | None = "Steps to handle phishing alerts.",
    content: str = "Step 1: Check sender...",
    tags: list[str] | None = None,
    targeting_rules: dict | None = None,
    version: int = 1,
) -> MagicMock:
    doc = MagicMock()
    doc.uuid = doc_uuid or uuid.uuid4()
    doc.title = title
    doc.document_type = document_type
    doc.is_global = is_global
    doc.description = description
    doc.content = content
    doc.tags = tags or []
    doc.targeting_rules = targeting_rules
    doc.version = version
    doc.created_at = _NOW
    doc.updated_at = _NOW
    return doc


def _mock_workflow(
    *,
    wf_uuid: uuid.UUID | None = None,
    name: str = "Block IP",
    workflow_type: str | None = "response",
    indicator_types: list[str] | None = None,
    code: str = "async def run(ctx): pass",
    code_version: int = 1,
    state: str = "active",
    timeout_seconds: int = 300,
    retry_count: int = 0,
    is_active: bool = True,
    is_system: bool = False,
    tags: list[str] | None = None,
    time_saved_minutes: int | None = 15,
    requires_approval: bool = True,
    approval_channel: str | None = "#soc-approvals",
    approval_timeout_seconds: int = 3600,
    risk_level: str = "medium",
    documentation: str | None = "Blocks a malicious IP in the firewall.",
) -> MagicMock:
    wf = MagicMock()
    wf.uuid = wf_uuid or uuid.uuid4()
    wf.name = name
    wf.workflow_type = workflow_type
    wf.indicator_types = indicator_types or ["ip"]
    wf.code = code
    wf.code_version = code_version
    wf.state = state
    wf.timeout_seconds = timeout_seconds
    wf.retry_count = retry_count
    wf.is_active = is_active
    wf.is_system = is_system
    wf.tags = tags or []
    wf.time_saved_minutes = time_saved_minutes
    wf.requires_approval = requires_approval
    wf.approval_channel = approval_channel
    wf.approval_timeout_seconds = approval_timeout_seconds
    wf.risk_level = risk_level
    wf.documentation = documentation
    wf.created_at = _NOW
    wf.updated_at = _NOW
    return wf


def _mock_activity_event(
    *,
    event_type: str = "alert_ingested",
    actor_type: str = "system",
    actor_key_prefix: str | None = None,
    references: dict | None = None,
) -> MagicMock:
    event = MagicMock()
    event.event_type = event_type
    event.actor_type = actor_type
    event.actor_key_prefix = actor_key_prefix
    event.references = references
    event.created_at = _NOW
    return event


# ---------------------------------------------------------------------------
# Helper: mock AsyncSessionLocal context manager
# ---------------------------------------------------------------------------

def _patch_session() -> tuple[type, AsyncMock]:
    """
    Return (patch_obj, mock_session) for patching AsyncSessionLocal.

    Usage:
        with _patch_session() as (patch_ctx, session):
            ...
    """
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    class _FakeCtx:
        async def __aenter__(self) -> AsyncMock:
            return mock_session
        async def __aexit__(self, *args: Any) -> None:
            pass

    return _FakeCtx, mock_session


# ===========================================================================
# Resource: calseta://alerts
# ===========================================================================


class TestListAlerts:
    async def test_returns_alert_list(self) -> None:
        """calseta://alerts returns a JSON list of recent alerts."""
        alert1 = _mock_alert(title="Alert 1")
        alert2 = _mock_alert(title="Alert 2", alert_uuid=_UUID_2)

        session_ctx, mock_session = _patch_session()

        mock_repo = MagicMock()
        mock_repo.list_alerts = AsyncMock(return_value=([alert1, alert2], 2))

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_repo),
        ):
            from app.mcp.resources.alerts import list_alerts
            result = await list_alerts()

        data = json.loads(result)
        assert "alerts" in data
        assert data["count"] == 2
        assert data["alerts"][0]["title"] == "Alert 1"
        assert data["alerts"][1]["title"] == "Alert 2"

    async def test_alert_list_fields_present(self) -> None:
        """Each alert in the list has all expected summary fields."""
        alert = _mock_alert()

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list_alerts = AsyncMock(return_value=([alert], 1))

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_repo),
        ):
            from app.mcp.resources.alerts import list_alerts
            result = await list_alerts()

        data = json.loads(result)
        item = data["alerts"][0]
        expected_keys = {
            "uuid", "title", "severity", "status", "source_name",
            "occurred_at", "is_enriched", "tags", "created_at",
        }
        assert expected_keys.issubset(set(item.keys()))

    async def test_empty_alerts_list(self) -> None:
        """Empty DB returns count=0 and empty list."""
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list_alerts = AsyncMock(return_value=([], 0))

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_repo),
        ):
            from app.mcp.resources.alerts import list_alerts
            result = await list_alerts()

        data = json.loads(result)
        assert data["count"] == 0
        assert data["alerts"] == []


# ===========================================================================
# Resource: calseta://alerts/{uuid}
# ===========================================================================


class TestGetAlert:
    async def test_returns_full_alert_detail(self) -> None:
        """calseta://alerts/{uuid} returns full alert with indicators and context."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid, detection_rule_id=None)
        indicator = _mock_indicator()

        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_indicator_repo = MagicMock()
        mock_indicator_repo.list_for_alert = AsyncMock(return_value=[indicator])

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
            patch("app.mcp.resources.alerts.IndicatorRepository", return_value=mock_indicator_repo),
            patch(
                "app.mcp.resources.alerts.get_applicable_documents",
                new_callable=AsyncMock, return_value=[],
            ),
        ):
            from app.mcp.resources.alerts import get_alert
            result = await get_alert(str(alert_uuid))

        data = json.loads(result)
        assert data["uuid"] == str(alert_uuid)
        assert data["title"] == "Suspicious login"
        assert len(data["indicators"]) == 1
        assert data["indicators"][0]["value"] == "1.2.3.4"
        assert data["detection_rule"] is None
        assert data["context_documents"] == []

    async def test_alert_with_context_documents(self) -> None:
        """Alert detail includes applicable context documents."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid, detection_rule_id=None)
        doc = _mock_context_document()

        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_indicator_repo = MagicMock()
        mock_indicator_repo.list_for_alert = AsyncMock(return_value=[])

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
            patch("app.mcp.resources.alerts.IndicatorRepository", return_value=mock_indicator_repo),
            patch(
                "app.mcp.resources.alerts.get_applicable_documents",
                new_callable=AsyncMock, return_value=[doc],
            ),
        ):
            from app.mcp.resources.alerts import get_alert
            result = await get_alert(str(alert_uuid))

        data = json.loads(result)
        assert len(data["context_documents"]) == 1
        assert data["context_documents"][0]["title"] == "Phishing Runbook"

    async def test_alert_not_found_raises_value_error(self) -> None:
        """Unknown UUID raises ValueError."""
        alert_uuid = uuid.uuid4()

        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=None)

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
        ):
            from app.mcp.resources.alerts import get_alert
            with pytest.raises(ValueError, match="Alert not found"):
                await get_alert(str(alert_uuid))

    async def test_invalid_uuid_format_raises_value_error(self) -> None:
        """Invalid UUID string raises ValueError."""
        from app.mcp.resources.alerts import get_alert
        with pytest.raises(ValueError, match="Invalid UUID"):
            await get_alert("not-a-uuid")

    async def test_enrichment_results_raw_stripped(self) -> None:
        """Indicator enrichment_results in alert detail have 'raw' key stripped."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid, detection_rule_id=None)
        indicator = _mock_indicator(
            enrichment_results={
                "virustotal": {
                    "extracted": {"found": True},
                    "raw": {"huge": "data"},
                },
            },
        )

        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_indicator_repo = MagicMock()
        mock_indicator_repo.list_for_alert = AsyncMock(return_value=[indicator])

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
            patch("app.mcp.resources.alerts.IndicatorRepository", return_value=mock_indicator_repo),
            patch(
                "app.mcp.resources.alerts.get_applicable_documents",
                new_callable=AsyncMock, return_value=[],
            ),
        ):
            from app.mcp.resources.alerts import get_alert
            result = await get_alert(str(alert_uuid))

        data = json.loads(result)
        enrichment = data["indicators"][0]["enrichment_results"]
        assert "raw" not in enrichment["virustotal"]
        assert enrichment["virustotal"]["extracted"] == {"found": True}

    async def test_alert_detail_fields_present(self) -> None:
        """Alert detail includes all expected top-level fields."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid, detection_rule_id=None)

        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_indicator_repo = MagicMock()
        mock_indicator_repo.list_for_alert = AsyncMock(return_value=[])

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
            patch("app.mcp.resources.alerts.IndicatorRepository", return_value=mock_indicator_repo),
            patch(
                "app.mcp.resources.alerts.get_applicable_documents",
                new_callable=AsyncMock, return_value=[],
            ),
        ):
            from app.mcp.resources.alerts import get_alert
            result = await get_alert(str(alert_uuid))

        data = json.loads(result)
        expected_keys = {
            "uuid", "title", "severity", "status", "source_name",
            "occurred_at", "ingested_at", "enriched_at", "is_enriched",
            "close_classification", "acknowledged_at", "triaged_at",
            "closed_at", "tags", "indicators", "detection_rule",
            "context_documents", "agent_findings",
        }
        assert expected_keys.issubset(set(data.keys()))


# ===========================================================================
# Resource: calseta://alerts/{uuid}/context
# ===========================================================================


class TestGetAlertContext:
    async def test_returns_context_documents(self) -> None:
        """calseta://alerts/{uuid}/context returns applicable context documents."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid)
        doc = _mock_context_document(is_global=True)

        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=alert)

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
            patch(
                "app.mcp.resources.alerts.get_applicable_documents",
                new_callable=AsyncMock, return_value=[doc],
            ),
        ):
            from app.mcp.resources.alerts import get_alert_context
            result = await get_alert_context(str(alert_uuid))

        data = json.loads(result)
        assert data["count"] == 1
        assert data["context_documents"][0]["title"] == "Phishing Runbook"
        assert data["context_documents"][0]["is_global"] is True

    async def test_context_fields_present(self) -> None:
        """Each context document in the response has all expected fields."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid)
        doc = _mock_context_document()

        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=alert)

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
            patch(
                "app.mcp.resources.alerts.get_applicable_documents",
                new_callable=AsyncMock, return_value=[doc],
            ),
        ):
            from app.mcp.resources.alerts import get_alert_context
            result = await get_alert_context(str(alert_uuid))

        data = json.loads(result)
        item = data["context_documents"][0]
        expected_keys = {
            "uuid", "title", "document_type", "is_global",
            "description", "content", "tags",
        }
        assert expected_keys.issubset(set(item.keys()))

    async def test_alert_not_found_raises(self) -> None:
        alert_uuid = uuid.uuid4()
        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=None)

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
        ):
            from app.mcp.resources.alerts import get_alert_context
            with pytest.raises(ValueError, match="Alert not found"):
                await get_alert_context(str(alert_uuid))


# ===========================================================================
# Resource: calseta://alerts/{uuid}/activity
# ===========================================================================


class TestGetAlertActivity:
    async def test_returns_activity_events(self) -> None:
        """calseta://alerts/{uuid}/activity returns newest-first events."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid)
        event = _mock_activity_event(
            event_type="alert_ingested",
            actor_type="system",
            references={"source": "sentinel"},
        )

        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_activity_repo = MagicMock()
        mock_activity_repo.list_for_alert = AsyncMock(return_value=([event], 1))

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
            patch(
                "app.mcp.resources.alerts.ActivityEventRepository",
                return_value=mock_activity_repo,
            ),
        ):
            from app.mcp.resources.alerts import get_alert_activity
            result = await get_alert_activity(str(alert_uuid))

        data = json.loads(result)
        assert data["count"] == 1
        assert data["activity"][0]["event_type"] == "alert_ingested"
        assert data["activity"][0]["actor_type"] == "system"
        # References should be flattened into the entry
        assert data["activity"][0]["source"] == "sentinel"

    async def test_activity_event_without_references(self) -> None:
        """Events with no references still include core fields."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid)
        event = _mock_activity_event(references=None)

        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_activity_repo = MagicMock()
        mock_activity_repo.list_for_alert = AsyncMock(return_value=([event], 1))

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
            patch(
                "app.mcp.resources.alerts.ActivityEventRepository",
                return_value=mock_activity_repo,
            ),
        ):
            from app.mcp.resources.alerts import get_alert_activity
            result = await get_alert_activity(str(alert_uuid))

        data = json.loads(result)
        item = data["activity"][0]
        assert "event_type" in item
        assert "created_at" in item

    async def test_activity_alert_not_found(self) -> None:
        alert_uuid = uuid.uuid4()
        session_ctx, mock_session = _patch_session()
        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=None)

        with (
            patch("app.mcp.resources.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.alerts.AlertRepository", return_value=mock_alert_repo),
        ):
            from app.mcp.resources.alerts import get_alert_activity
            with pytest.raises(ValueError, match="Alert not found"):
                await get_alert_activity(str(alert_uuid))


# ===========================================================================
# Resource: calseta://detection-rules
# ===========================================================================


class TestListDetectionRules:
    async def test_returns_rule_list(self) -> None:
        rule = _mock_detection_rule()
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(return_value=([rule], 1))

        with (
            patch("app.mcp.resources.detection_rules.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.detection_rules.DetectionRuleRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.detection_rules import list_detection_rules
            result = await list_detection_rules()

        data = json.loads(result)
        assert data["count"] == 1
        assert data["detection_rules"][0]["name"] == "Brute Force Login"

    async def test_documentation_truncated(self) -> None:
        """Long documentation is truncated in list view."""
        long_doc = "A" * 300
        rule = _mock_detection_rule(documentation=long_doc)

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(return_value=([rule], 1))

        with (
            patch("app.mcp.resources.detection_rules.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.detection_rules.DetectionRuleRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.detection_rules import list_detection_rules
            result = await list_detection_rules()

        data = json.loads(result)
        summary = data["detection_rules"][0]["documentation_summary"]
        assert summary.endswith("...")
        assert len(summary) <= 204  # 200 + "..."

    async def test_short_documentation_not_truncated(self) -> None:
        """Short documentation is kept as-is."""
        short_doc = "Short rule doc."
        rule = _mock_detection_rule(documentation=short_doc)

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list = AsyncMock(return_value=([rule], 1))

        with (
            patch("app.mcp.resources.detection_rules.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.detection_rules.DetectionRuleRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.detection_rules import list_detection_rules
            result = await list_detection_rules()

        data = json.loads(result)
        assert data["detection_rules"][0]["documentation_summary"] == short_doc


# ===========================================================================
# Resource: calseta://detection-rules/{uuid}
# ===========================================================================


class TestGetDetectionRule:
    async def test_returns_full_rule(self) -> None:
        rule_uuid = uuid.uuid4()
        rule = _mock_detection_rule(rule_uuid=rule_uuid)

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=rule)

        with (
            patch("app.mcp.resources.detection_rules.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.detection_rules.DetectionRuleRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.detection_rules import get_detection_rule
            result = await get_detection_rule(str(rule_uuid))

        data = json.loads(result)
        assert data["uuid"] == str(rule_uuid)
        assert data["name"] == "Brute Force Login"
        # Full documentation not truncated
        assert data["documentation"] == "Detects brute force login attempts."

    async def test_full_rule_fields_present(self) -> None:
        rule_uuid = uuid.uuid4()
        rule = _mock_detection_rule(rule_uuid=rule_uuid)

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=rule)

        with (
            patch("app.mcp.resources.detection_rules.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.detection_rules.DetectionRuleRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.detection_rules import get_detection_rule
            result = await get_detection_rule(str(rule_uuid))

        data = json.loads(result)
        expected_keys = {
            "uuid", "name", "source_rule_id", "source_name", "severity",
            "is_active", "mitre_tactics", "mitre_techniques",
            "mitre_subtechniques", "data_sources", "run_frequency",
            "created_by", "documentation", "created_at", "updated_at",
        }
        assert expected_keys.issubset(set(data.keys()))

    async def test_rule_not_found_raises(self) -> None:
        rule_uuid = uuid.uuid4()
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=None)

        with (
            patch("app.mcp.resources.detection_rules.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.detection_rules.DetectionRuleRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.detection_rules import get_detection_rule
            with pytest.raises(ValueError, match="Detection rule not found"):
                await get_detection_rule(str(rule_uuid))


# ===========================================================================
# Resource: calseta://context-documents
# ===========================================================================


class TestListContextDocuments:
    async def test_returns_document_catalog(self) -> None:
        doc = _mock_context_document()

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list_documents = AsyncMock(return_value=([doc], 1))

        with (
            patch("app.mcp.resources.context_documents.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.context_documents.ContextDocumentRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.context_documents import list_context_documents
            result = await list_context_documents()

        data = json.loads(result)
        assert data["count"] == 1
        item = data["context_documents"][0]
        assert item["title"] == "Phishing Runbook"
        # List view should NOT include content (token efficiency)
        assert "content" not in item

    async def test_list_fields_present(self) -> None:
        doc = _mock_context_document()

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list_documents = AsyncMock(return_value=([doc], 1))

        with (
            patch("app.mcp.resources.context_documents.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.context_documents.ContextDocumentRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.context_documents import list_context_documents
            result = await list_context_documents()

        data = json.loads(result)
        item = data["context_documents"][0]
        expected_keys = {
            "uuid", "title", "document_type", "is_global",
            "description", "tags", "version", "created_at", "updated_at",
        }
        assert expected_keys.issubset(set(item.keys()))


# ===========================================================================
# Resource: calseta://context-documents/{uuid}
# ===========================================================================


class TestGetContextDocument:
    async def test_returns_full_document(self) -> None:
        doc_uuid = uuid.uuid4()
        doc = _mock_context_document(doc_uuid=doc_uuid)

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=doc)

        with (
            patch("app.mcp.resources.context_documents.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.context_documents.ContextDocumentRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.context_documents import get_context_document
            result = await get_context_document(str(doc_uuid))

        data = json.loads(result)
        assert data["uuid"] == str(doc_uuid)
        assert data["content"] == "Step 1: Check sender..."
        assert data["targeting_rules"] is None

    async def test_full_doc_fields_present(self) -> None:
        doc_uuid = uuid.uuid4()
        doc = _mock_context_document(doc_uuid=doc_uuid)

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=doc)

        with (
            patch("app.mcp.resources.context_documents.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.context_documents.ContextDocumentRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.context_documents import get_context_document
            result = await get_context_document(str(doc_uuid))

        data = json.loads(result)
        expected_keys = {
            "uuid", "title", "document_type", "is_global",
            "description", "content", "tags", "targeting_rules",
            "version", "created_at", "updated_at",
        }
        assert expected_keys.issubset(set(data.keys()))

    async def test_doc_not_found_raises(self) -> None:
        doc_uuid = uuid.uuid4()
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=None)

        with (
            patch("app.mcp.resources.context_documents.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.context_documents.ContextDocumentRepository",
                return_value=mock_repo,
            ),
        ):
            from app.mcp.resources.context_documents import get_context_document
            with pytest.raises(ValueError, match="Context document not found"):
                await get_context_document(str(doc_uuid))


# ===========================================================================
# Resource: calseta://workflows
# ===========================================================================


class TestListWorkflows:
    async def test_returns_workflow_catalog(self) -> None:
        wf = _mock_workflow()

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list_workflows = AsyncMock(return_value=([wf], 1))

        with (
            patch("app.mcp.resources.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.workflows.WorkflowRepository", return_value=mock_repo),
        ):
            from app.mcp.resources.workflows import list_workflows
            result = await list_workflows()

        data = json.loads(result)
        assert data["count"] == 1
        assert data["workflows"][0]["name"] == "Block IP"
        assert data["workflows"][0]["documentation"] == "Blocks a malicious IP in the firewall."

    async def test_workflow_list_fields_present(self) -> None:
        wf = _mock_workflow()
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list_workflows = AsyncMock(return_value=([wf], 1))

        with (
            patch("app.mcp.resources.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.workflows.WorkflowRepository", return_value=mock_repo),
        ):
            from app.mcp.resources.workflows import list_workflows
            result = await list_workflows()

        data = json.loads(result)
        item = data["workflows"][0]
        expected_keys = {
            "uuid", "name", "workflow_type", "indicator_types",
            "state", "code_version", "is_active", "is_system",
            "tags", "time_saved_minutes", "requires_approval",
            "risk_level", "documentation", "created_at", "updated_at",
        }
        assert expected_keys.issubset(set(item.keys()))


# ===========================================================================
# Resource: calseta://workflows/{uuid}
# ===========================================================================


class TestGetWorkflow:
    async def test_returns_full_workflow(self) -> None:
        wf_uuid = uuid.uuid4()
        wf = _mock_workflow(wf_uuid=wf_uuid)

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=wf)

        with (
            patch("app.mcp.resources.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.workflows.WorkflowRepository", return_value=mock_repo),
        ):
            from app.mcp.resources.workflows import get_workflow
            result = await get_workflow(str(wf_uuid))

        data = json.loads(result)
        assert data["uuid"] == str(wf_uuid)
        assert data["name"] == "Block IP"
        assert data["code"] == "async def run(ctx): pass"
        assert data["requires_approval"] is True

    async def test_full_workflow_fields_present(self) -> None:
        wf_uuid = uuid.uuid4()
        wf = _mock_workflow(wf_uuid=wf_uuid)
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=wf)

        with (
            patch("app.mcp.resources.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.workflows.WorkflowRepository", return_value=mock_repo),
        ):
            from app.mcp.resources.workflows import get_workflow
            result = await get_workflow(str(wf_uuid))

        data = json.loads(result)
        expected_keys = {
            "uuid", "name", "workflow_type", "indicator_types",
            "code", "code_version", "state", "timeout_seconds",
            "retry_count", "is_active", "is_system", "tags",
            "time_saved_minutes", "requires_approval",
            "approval_channel", "approval_timeout_seconds",
            "risk_level", "documentation", "created_at", "updated_at",
        }
        assert expected_keys.issubset(set(data.keys()))

    async def test_workflow_not_found_raises(self) -> None:
        wf_uuid = uuid.uuid4()
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=None)

        with (
            patch("app.mcp.resources.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.workflows.WorkflowRepository", return_value=mock_repo),
        ):
            from app.mcp.resources.workflows import get_workflow
            with pytest.raises(ValueError, match="Workflow not found"):
                await get_workflow(str(wf_uuid))


# ===========================================================================
# Resource: calseta://metrics/summary
# ===========================================================================


class TestGetMetricsSummary:
    async def test_returns_metrics_summary(self) -> None:
        from app.schemas.metrics import (
            MetricsSummaryAlerts,
            MetricsSummaryApprovals,
            MetricsSummaryResponse,
            MetricsSummaryWorkflows,
        )

        summary = MetricsSummaryResponse(
            period="last_30_days",
            alerts=MetricsSummaryAlerts(
                total=100,
                active=25,
                by_severity={"High": 10, "Critical": 5, "Medium": 10},
                false_positive_rate=0.05,
                mttd_seconds=120.0,
                mtta_seconds=300.0,
                mttt_seconds=600.0,
                mttc_seconds=1800.0,
            ),
            workflows=MetricsSummaryWorkflows(
                total_configured=5,
                executions=20,
                success_rate=0.95,
                estimated_time_saved_hours=10.0,
            ),
            approvals=MetricsSummaryApprovals(
                pending=2,
                approved_last_30_days=15,
                approval_rate=0.88,
                median_response_time_minutes=5.0,
            ),
        )

        session_ctx, mock_session = _patch_session()

        with (
            patch("app.mcp.resources.metrics.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.resources.metrics.compute_metrics_summary",
                new_callable=AsyncMock, return_value=summary,
            ),
        ):
            from app.mcp.resources.metrics import get_metrics_summary
            result = await get_metrics_summary()

        data = json.loads(result)
        assert data["period"] == "last_30_days"
        assert data["alerts"]["total"] == 100
        assert data["workflows"]["success_rate"] == 0.95
        assert data["approvals"]["pending"] == 2


# ===========================================================================
# Resource: calseta://enrichments/{type}/{value}
# ===========================================================================


class TestGetEnrichment:
    async def test_returns_enrichment_results(self) -> None:
        from app.schemas.enrichment import EnrichmentResult

        mock_result = EnrichmentResult.success_result(
            provider_name="virustotal",
            extracted={"found": True, "malice": "Malicious"},
            raw={},
            enriched_at=_NOW,
        )

        mock_provider = MagicMock()
        mock_provider.provider_name = "virustotal"
        mock_provider.is_configured.return_value = True

        session_ctx, mock_session = _patch_session()
        mock_service = MagicMock()
        mock_service.enrich_indicator = AsyncMock(
            return_value={"virustotal": mock_result}
        )

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)

        with (
            patch("app.mcp.resources.enrichments.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.enrichments.enrichment_registry") as mock_registry,
            patch("app.mcp.resources.enrichments.get_cache_backend", return_value=mock_cache),
            patch("app.mcp.resources.enrichments.EnrichmentService", return_value=mock_service),
        ):
            mock_registry.list_for_type.return_value = [mock_provider]

            from app.mcp.resources.enrichments import get_enrichment
            result = await get_enrichment("ip", "1.2.3.4")

        data = json.loads(result)
        assert data["type"] == "ip"
        assert data["value"] == "1.2.3.4"
        assert data["provider_count"] == 1
        assert data["results"]["virustotal"]["success"] is True

    async def test_invalid_indicator_type_raises(self) -> None:
        from app.mcp.resources.enrichments import get_enrichment
        with pytest.raises(ValueError, match="Invalid indicator type"):
            await get_enrichment("invalid_type", "1.2.3.4")

    async def test_empty_value_raises(self) -> None:
        from app.mcp.resources.enrichments import get_enrichment
        with pytest.raises(ValueError, match="must not be empty"):
            await get_enrichment("ip", "  ")

    async def test_no_providers_returns_empty(self) -> None:
        """When no providers support the type, return empty results with message."""
        session_ctx, mock_session = _patch_session()

        with (
            patch("app.mcp.resources.enrichments.enrichment_registry") as mock_registry,
        ):
            mock_registry.list_for_type.return_value = []

            from app.mcp.resources.enrichments import get_enrichment
            result = await get_enrichment("ip", "1.2.3.4")

        data = json.loads(result)
        assert data["provider_count"] == 0
        assert data["results"] == {}
        assert "No configured providers" in data["message"]

    async def test_cache_hit_flag_set(self) -> None:
        """When a result is in cache, cache_hit is True."""
        from app.schemas.enrichment import EnrichmentResult

        mock_result = EnrichmentResult.success_result(
            provider_name="virustotal",
            extracted={"found": True},
            raw={},
            enriched_at=_NOW,
        )

        mock_provider = MagicMock()
        mock_provider.provider_name = "virustotal"
        mock_provider.is_configured.return_value = True

        session_ctx, mock_session = _patch_session()
        mock_service = MagicMock()
        mock_service.enrich_indicator = AsyncMock(
            return_value={"virustotal": mock_result}
        )

        mock_cache = AsyncMock()
        # Simulate cache hit: return something for the cache key
        mock_cache.get = AsyncMock(return_value={"cached": True})

        with (
            patch("app.mcp.resources.enrichments.AsyncSessionLocal", session_ctx),
            patch("app.mcp.resources.enrichments.enrichment_registry") as mock_registry,
            patch("app.mcp.resources.enrichments.get_cache_backend", return_value=mock_cache),
            patch("app.mcp.resources.enrichments.EnrichmentService", return_value=mock_service),
        ):
            mock_registry.list_for_type.return_value = [mock_provider]

            from app.mcp.resources.enrichments import get_enrichment
            result = await get_enrichment("ip", "1.2.3.4")

        data = json.loads(result)
        assert data["results"]["virustotal"]["cache_hit"] is True
