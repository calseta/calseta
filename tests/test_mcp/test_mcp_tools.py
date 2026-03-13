"""
Unit tests for MCP tools — write/execute operations.

These tests mock the DB/service layer and verify that each MCP tool handler
validates inputs, enforces scopes, and returns correctly shaped JSON results.
No running database required.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


def _mock_ctx(client_id: str = "cai_test") -> MagicMock:
    """Return a mock MCP Context with client_id."""
    ctx = MagicMock()
    ctx.client_id = client_id
    return ctx


def _mock_alert(
    *,
    alert_uuid: uuid.UUID | None = None,
    title: str = "Suspicious login",
    severity: str = "High",
    status: str = "Open",
    enrichment_status: str = "Pending",
    source_name: str = "sentinel",
    occurred_at: datetime | None = None,
    is_enriched: bool = False,
    tags: list[str] | None = None,
    id: int = 1,
    agent_findings: list | None = None,
) -> MagicMock:
    _now = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
    alert = MagicMock()
    alert.id = id
    alert.uuid = alert_uuid or uuid.uuid4()
    alert.title = title
    alert.severity = severity
    alert.status = status
    alert.enrichment_status = enrichment_status
    alert.source_name = source_name
    alert.occurred_at = occurred_at or _now
    alert.is_enriched = is_enriched
    alert.tags = tags or []
    alert.created_at = _now
    alert.agent_findings = agent_findings
    return alert


def _mock_workflow(
    *,
    wf_uuid: uuid.UUID | None = None,
    name: str = "Block IP",
    is_active: bool = True,
    state: str = "active",
    approval_mode: str = "never",
    code_version: int = 1,
    approval_timeout_seconds: int = 3600,
) -> MagicMock:
    wf = MagicMock()
    wf.id = 1
    wf.uuid = wf_uuid or uuid.uuid4()
    wf.name = name
    wf.is_active = is_active
    wf.state = state
    wf.approval_mode = approval_mode
    wf.code_version = code_version
    wf.approval_timeout_seconds = approval_timeout_seconds
    wf.approval_channel = "#soc-approvals"
    return wf


def _mock_workflow_run(
    *,
    run_uuid: uuid.UUID | None = None,
    status: str = "queued",
) -> MagicMock:
    run = MagicMock()
    run.id = 1
    run.uuid = run_uuid or uuid.uuid4()
    run.status = status
    return run


def _mock_approval_request(
    *,
    req_uuid: uuid.UUID | None = None,
    expires_at: datetime | None = None,
) -> MagicMock:
    req = MagicMock()
    req.id = 1
    req.uuid = req_uuid or uuid.uuid4()
    req.expires_at = expires_at or (_NOW + timedelta(hours=1))
    return req


def _patch_session() -> tuple[type, AsyncMock]:
    """Return a session context class and mock session for patching AsyncSessionLocal."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()

    class _FakeCtx:
        async def __aenter__(self) -> AsyncMock:
            return mock_session
        async def __aexit__(self, *args: Any) -> None:
            pass

    return _FakeCtx, mock_session


def _scope_pass() -> AsyncMock:
    """Return an AsyncMock for check_scope that always passes (returns None)."""
    return AsyncMock(return_value=None)


def _scope_fail(msg: str = "Insufficient scope.") -> AsyncMock:
    """Return an AsyncMock for check_scope that always fails."""
    return AsyncMock(return_value=json.dumps({"error": msg}))


# ===========================================================================
# Tool: search_alerts
# ===========================================================================


class TestSearchAlerts:
    async def test_search_with_filters(self) -> None:
        """search_alerts returns matching alerts with pagination metadata."""
        alert = _mock_alert()
        alert.severity = "High"
        alert.source_name = "sentinel"
        alert.occurred_at = _NOW
        alert.is_enriched = False
        alert.tags = []
        alert.created_at = _NOW

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list_alerts = AsyncMock(return_value=([alert], 1))

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
        ):
            from app.mcp.tools.alerts import search_alerts
            result = await search_alerts(
                ctx=_mock_ctx(),
                status="Open",
                severity="High",
                source_name="sentinel",
            )

        data = json.loads(result)
        assert data["total"] == 1
        assert data["page"] == 1
        assert len(data["alerts"]) == 1

    async def test_search_with_time_range(self) -> None:
        """search_alerts accepts ISO 8601 from_time and to_time."""
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list_alerts = AsyncMock(return_value=([], 0))

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
        ):
            from app.mcp.tools.alerts import search_alerts
            result = await search_alerts(
                ctx=_mock_ctx(),
                from_time="2026-01-01T00:00:00+00:00",
                to_time="2026-03-01T00:00:00+00:00",
            )

        data = json.loads(result)
        assert data["total"] == 0

    async def test_search_invalid_from_time(self) -> None:
        """Invalid from_time returns error JSON, not an exception."""
        from app.mcp.tools.alerts import search_alerts
        result = await search_alerts(ctx=_mock_ctx(), from_time="not-a-date")
        data = json.loads(result)
        assert "error" in data
        assert "from_time" in data["error"]

    async def test_search_invalid_to_time(self) -> None:
        from app.mcp.tools.alerts import search_alerts
        result = await search_alerts(ctx=_mock_ctx(), to_time="not-a-date")
        data = json.loads(result)
        assert "error" in data
        assert "to_time" in data["error"]

    async def test_search_with_tags(self) -> None:
        """Comma-separated tags are parsed into a list."""
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list_alerts = AsyncMock(return_value=([], 0))

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
        ):
            from app.mcp.tools.alerts import search_alerts
            await search_alerts(ctx=_mock_ctx(), tags="phishing, credential-theft")

        # Verify tags were parsed and passed to the repo
        call_kwargs = mock_repo.list_alerts.call_args
        assert call_kwargs.kwargs.get("tags") == ["phishing", "credential-theft"]

    async def test_search_page_size_capped_at_100(self) -> None:
        """page_size is capped at 100 even if a larger value is requested."""
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.list_alerts = AsyncMock(return_value=([], 0))

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
        ):
            from app.mcp.tools.alerts import search_alerts
            result = await search_alerts(ctx=_mock_ctx(), page_size=500)

        data = json.loads(result)
        assert data["page_size"] == 100

    async def test_search_scope_check_fails(self) -> None:
        """Insufficient scope returns the scope error."""
        session_ctx, mock_session = _patch_session()

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch(
                "app.mcp.tools.alerts.check_scope",
                _scope_fail("Insufficient scope. Required: alerts:read"),
            ),
        ):
            from app.mcp.tools.alerts import search_alerts
            result = await search_alerts(ctx=_mock_ctx())

        data = json.loads(result)
        assert "Insufficient scope" in data["error"]


# ===========================================================================
# Tool: post_alert_finding
# ===========================================================================


class TestPostAlertFinding:
    async def test_post_finding_success(self) -> None:
        """Posting a finding returns finding_id and posted_at."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid)

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_repo.add_finding = AsyncMock(return_value=alert)

        mock_activity_svc = MagicMock()
        mock_activity_svc.write = AsyncMock()

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
            patch("app.mcp.tools.alerts.ActivityEventService", return_value=mock_activity_svc),
        ):
            from app.mcp.tools.alerts import post_alert_finding
            result = await post_alert_finding(
                alert_uuid=str(alert_uuid),
                summary="Found suspicious activity from known C2 infrastructure.",
                confidence="high",
                ctx=_mock_ctx(),
                agent_name="test-agent",
                recommended_action="Block the source IP.",
            )

        data = json.loads(result)
        assert "finding_id" in data
        assert data["alert_uuid"] == str(alert_uuid)
        assert "posted_at" in data

    async def test_post_finding_invalid_uuid(self) -> None:
        from app.mcp.tools.alerts import post_alert_finding
        result = await post_alert_finding(
            alert_uuid="not-a-uuid",
            summary="test",
            confidence="high",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "error" in data
        assert "Invalid UUID" in data["error"]

    async def test_post_finding_invalid_confidence(self) -> None:
        alert_uuid = uuid.uuid4()
        from app.mcp.tools.alerts import post_alert_finding
        result = await post_alert_finding(
            alert_uuid=str(alert_uuid),
            summary="test",
            confidence="super_high",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "error" in data
        assert "confidence" in data["error"].lower()

    async def test_post_finding_alert_not_found(self) -> None:
        alert_uuid = uuid.uuid4()
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=None)

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
        ):
            from app.mcp.tools.alerts import post_alert_finding
            result = await post_alert_finding(
                alert_uuid=str(alert_uuid),
                summary="test finding",
                confidence="high",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert "error" in data
        assert "Alert not found" in data["error"]

    async def test_post_finding_scope_failure(self) -> None:
        alert_uuid = uuid.uuid4()
        session_ctx, mock_session = _patch_session()

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_fail()),
        ):
            from app.mcp.tools.alerts import post_alert_finding
            result = await post_alert_finding(
                alert_uuid=str(alert_uuid),
                summary="test",
                confidence="high",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert "error" in data

    async def test_post_finding_writes_activity_event(self) -> None:
        """Posting a finding creates an activity event of type alert_finding_added."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid)

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_repo.add_finding = AsyncMock(return_value=alert)

        mock_activity_svc = MagicMock()
        mock_activity_svc.write = AsyncMock()

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
            patch("app.mcp.tools.alerts.ActivityEventService", return_value=mock_activity_svc),
        ):
            from app.mcp.tools.alerts import post_alert_finding
            await post_alert_finding(
                alert_uuid=str(alert_uuid),
                summary="test finding",
                confidence="medium",
                ctx=_mock_ctx(),
            )

        mock_activity_svc.write.assert_called_once()
        call_args = mock_activity_svc.write.call_args
        assert call_args.args[0].value == "alert_finding_added"
        assert call_args.kwargs["actor_type"] == "mcp"


# ===========================================================================
# Tool: update_alert_status
# ===========================================================================


class TestUpdateAlertStatus:
    async def test_update_status_success(self) -> None:
        """Updating alert status returns the new status and previous status."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid, status="Open")

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_repo.patch = AsyncMock(return_value=alert)

        mock_activity_svc = MagicMock()
        mock_activity_svc.write = AsyncMock()

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
            patch("app.mcp.tools.alerts.ActivityEventService", return_value=mock_activity_svc),
        ):
            from app.mcp.tools.alerts import update_alert_status
            result = await update_alert_status(
                alert_uuid=str(alert_uuid),
                status="Triaging",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert data["status"] == "Triaging"
        assert data["previous_status"] == "Open"

    async def test_update_status_invalid_uuid(self) -> None:
        from app.mcp.tools.alerts import update_alert_status
        result = await update_alert_status(
            alert_uuid="bad-uuid",
            status="Open",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "Invalid UUID" in data["error"]

    async def test_update_status_invalid_status(self) -> None:
        alert_uuid = uuid.uuid4()
        from app.mcp.tools.alerts import update_alert_status
        result = await update_alert_status(
            alert_uuid=str(alert_uuid),
            status="InvalidStatus",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "Invalid status" in data["error"]

    async def test_close_requires_classification(self) -> None:
        """Setting status to Closed without close_classification returns error."""
        alert_uuid = uuid.uuid4()
        from app.mcp.tools.alerts import update_alert_status
        result = await update_alert_status(
            alert_uuid=str(alert_uuid),
            status="Closed",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "close_classification is required" in data["error"]

    async def test_close_with_classification_succeeds(self) -> None:
        """Closing an alert with a classification succeeds."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid, status="Triaging")

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_repo.patch = AsyncMock(return_value=alert)

        mock_activity_svc = MagicMock()
        mock_activity_svc.write = AsyncMock()

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
            patch("app.mcp.tools.alerts.ActivityEventService", return_value=mock_activity_svc),
        ):
            from app.mcp.tools.alerts import update_alert_status
            result = await update_alert_status(
                alert_uuid=str(alert_uuid),
                status="Closed",
                ctx=_mock_ctx(),
                close_classification="True Positive - Suspicious Activity",
            )

        data = json.loads(result)
        assert data["status"] == "Closed"

    async def test_close_writes_alert_closed_activity(self) -> None:
        """Closing an alert writes an alert_closed activity event (not alert_status_updated)."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid, status="Triaging")

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_repo.patch = AsyncMock(return_value=alert)

        mock_activity_svc = MagicMock()
        mock_activity_svc.write = AsyncMock()

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
            patch("app.mcp.tools.alerts.ActivityEventService", return_value=mock_activity_svc),
        ):
            from app.mcp.tools.alerts import update_alert_status
            await update_alert_status(
                alert_uuid=str(alert_uuid),
                status="Closed",
                ctx=_mock_ctx(),
                close_classification="True Positive - Suspicious Activity",
            )

        mock_activity_svc.write.assert_called_once()
        call_args = mock_activity_svc.write.call_args
        assert call_args.args[0].value == "alert_closed"

    async def test_non_close_writes_status_updated_activity(self) -> None:
        """Non-close status change writes alert_status_updated."""
        alert_uuid = uuid.uuid4()
        alert = _mock_alert(alert_uuid=alert_uuid, status="Open")

        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=alert)
        mock_repo.patch = AsyncMock(return_value=alert)

        mock_activity_svc = MagicMock()
        mock_activity_svc.write = AsyncMock()

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
            patch("app.mcp.tools.alerts.ActivityEventService", return_value=mock_activity_svc),
        ):
            from app.mcp.tools.alerts import update_alert_status
            await update_alert_status(
                alert_uuid=str(alert_uuid),
                status="Escalated",
                ctx=_mock_ctx(),
            )

        mock_activity_svc.write.assert_called_once()
        call_args = mock_activity_svc.write.call_args
        assert call_args.args[0].value == "alert_status_updated"

    async def test_update_alert_not_found(self) -> None:
        alert_uuid = uuid.uuid4()
        session_ctx, mock_session = _patch_session()
        mock_repo = MagicMock()
        mock_repo.get_by_uuid = AsyncMock(return_value=None)

        with (
            patch("app.mcp.tools.alerts.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.alerts.check_scope", _scope_pass()),
            patch("app.mcp.tools.alerts.AlertRepository", return_value=mock_repo),
        ):
            from app.mcp.tools.alerts import update_alert_status
            result = await update_alert_status(
                alert_uuid=str(alert_uuid),
                status="Open",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert "Alert not found" in data["error"]


# ===========================================================================
# Tool: enrich_indicator
# ===========================================================================


class TestEnrichIndicator:
    async def test_enrich_success(self) -> None:
        """enrich_indicator returns structured per-provider results."""
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
            patch("app.mcp.tools.enrichment.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.enrichment.check_scope", _scope_pass()),
            patch("app.mcp.tools.enrichment.enrichment_registry") as mock_registry,
            patch("app.mcp.tools.enrichment.get_cache_backend", return_value=mock_cache),
            patch("app.mcp.tools.enrichment.EnrichmentService", return_value=mock_service),
        ):
            mock_registry.list_for_type.return_value = [mock_provider]

            from app.mcp.tools.enrichment import enrich_indicator
            result = await enrich_indicator(
                type="ip",
                value="1.2.3.4",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert data["type"] == "ip"
        assert data["value"] == "1.2.3.4"
        assert data["provider_count"] == 1
        assert data["results"]["virustotal"]["success"] is True

    async def test_enrich_invalid_type(self) -> None:
        from app.mcp.tools.enrichment import enrich_indicator
        result = await enrich_indicator(
            type="invalid_type",
            value="1.2.3.4",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "error" in data
        assert "Invalid indicator type" in data["error"]

    async def test_enrich_empty_value(self) -> None:
        from app.mcp.tools.enrichment import enrich_indicator
        result = await enrich_indicator(
            type="ip",
            value="  ",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "error" in data
        assert "must not be empty" in data["error"]

    async def test_enrich_no_providers(self) -> None:
        """When no providers support the type, return empty results with message."""
        with patch("app.mcp.tools.enrichment.enrichment_registry") as mock_registry:
            mock_registry.list_for_type.return_value = []

            from app.mcp.tools.enrichment import enrich_indicator
            result = await enrich_indicator(
                type="ip",
                value="1.2.3.4",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert data["provider_count"] == 0
        assert "No configured providers" in data["message"]

    async def test_enrich_scope_failure(self) -> None:
        mock_provider = MagicMock()
        mock_provider.provider_name = "virustotal"

        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)

        session_ctx, mock_session = _patch_session()

        with (
            patch("app.mcp.tools.enrichment.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.enrichment.check_scope", _scope_fail()),
            patch("app.mcp.tools.enrichment.enrichment_registry") as mock_registry,
            patch("app.mcp.tools.enrichment.get_cache_backend", return_value=mock_cache),
        ):
            mock_registry.list_for_type.return_value = [mock_provider]

            from app.mcp.tools.enrichment import enrich_indicator
            result = await enrich_indicator(
                type="ip",
                value="1.2.3.4",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert "error" in data


# ===========================================================================
# Tool: search_detection_rules
# ===========================================================================


class TestSearchDetectionRules:
    async def test_search_by_name(self) -> None:
        """search_detection_rules filters by name substring."""
        mock_rule = MagicMock()
        mock_rule.uuid = uuid.uuid4()
        mock_rule.name = "Brute Force Login"
        mock_rule.source_name = "sentinel"
        mock_rule.severity = "High"
        mock_rule.is_active = True
        mock_rule.mitre_tactics = ["Credential Access"]
        mock_rule.mitre_techniques = ["T1110"]
        mock_rule.mitre_subtechniques = []
        mock_rule.documentation = "Short doc"
        mock_rule.created_at = _NOW

        session_ctx, mock_session = _patch_session()

        # Build mock scalars result
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_rule]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        mock_result.scalar_one.return_value = 1

        # Mock session.execute to return count then rules
        mock_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one=MagicMock(return_value=1)),  # count
            mock_result,  # rules
        ])

        with (
            patch("app.mcp.tools.detection_rules.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.detection_rules.check_scope", _scope_pass()),
        ):
            from app.mcp.tools.detection_rules import search_detection_rules
            result = await search_detection_rules(
                ctx=_mock_ctx(),
                name="Brute Force",
            )

        data = json.loads(result)
        assert data["total"] == 1
        assert data["detection_rules"][0]["name"] == "Brute Force Login"

    async def test_search_page_size_capped(self) -> None:
        """page_size is capped at 100."""
        session_ctx, mock_session = _patch_session()

        mock_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one=MagicMock(return_value=0)),
            MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))),
        ])

        with (
            patch("app.mcp.tools.detection_rules.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.detection_rules.check_scope", _scope_pass()),
        ):
            from app.mcp.tools.detection_rules import search_detection_rules
            result = await search_detection_rules(
                ctx=_mock_ctx(),
                page_size=500,
            )

        data = json.loads(result)
        assert data["page_size"] == 100

    async def test_search_scope_failure(self) -> None:
        session_ctx, mock_session = _patch_session()

        with (
            patch("app.mcp.tools.detection_rules.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.detection_rules.check_scope", _scope_fail()),
        ):
            from app.mcp.tools.detection_rules import search_detection_rules
            result = await search_detection_rules(ctx=_mock_ctx())

        data = json.loads(result)
        assert "error" in data

    async def test_search_documentation_truncated_in_results(self) -> None:
        """Long documentation is truncated in search results."""
        mock_rule = MagicMock()
        mock_rule.uuid = uuid.uuid4()
        mock_rule.name = "Test Rule"
        mock_rule.source_name = "elastic"
        mock_rule.severity = "Medium"
        mock_rule.is_active = True
        mock_rule.mitre_tactics = []
        mock_rule.mitre_techniques = []
        mock_rule.mitre_subtechniques = []
        mock_rule.documentation = "A" * 300
        mock_rule.created_at = _NOW

        session_ctx, mock_session = _patch_session()

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_rule]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        mock_session.execute = AsyncMock(side_effect=[
            MagicMock(scalar_one=MagicMock(return_value=1)),
            mock_result,
        ])

        with (
            patch("app.mcp.tools.detection_rules.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.detection_rules.check_scope", _scope_pass()),
        ):
            from app.mcp.tools.detection_rules import search_detection_rules
            result = await search_detection_rules(ctx=_mock_ctx())

        data = json.loads(result)
        doc = data["detection_rules"][0]["documentation"]
        assert doc.endswith("...")
        assert len(doc) <= 204


# ===========================================================================
# Tool: execute_workflow
# ===========================================================================


class TestExecuteWorkflow:
    async def test_execute_immediate_success(self) -> None:
        """Workflow without approval gate returns queued status with run_uuid."""
        wf_uuid = uuid.uuid4()
        wf = _mock_workflow(wf_uuid=wf_uuid, approval_mode="never")
        run = _mock_workflow_run()

        session_ctx, mock_session = _patch_session()
        mock_wf_repo = MagicMock()
        mock_wf_repo.get_by_uuid = AsyncMock(return_value=wf)
        mock_run_repo = MagicMock()
        mock_run_repo.create = AsyncMock(return_value=run)

        mock_queue = MagicMock()
        mock_queue.enqueue = AsyncMock(return_value="task-1")

        with (
            patch("app.mcp.tools.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.workflows.check_scope", _scope_pass()),
            patch("app.mcp.tools.workflows.WorkflowRepository", return_value=mock_wf_repo),
            patch("app.mcp.tools.workflows.WorkflowRunRepository", return_value=mock_run_repo),
            patch("app.queue.factory.get_queue_backend", return_value=mock_queue),
        ):
            from app.mcp.tools.workflows import execute_workflow
            result = await execute_workflow(
                workflow_uuid=str(wf_uuid),
                indicator_type="ip",
                indicator_value="1.2.3.4",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert data["status"] == "queued"
        assert "run_uuid" in data

    async def test_execute_invalid_workflow_uuid(self) -> None:
        from app.mcp.tools.workflows import execute_workflow
        result = await execute_workflow(
            workflow_uuid="not-valid",
            indicator_type="ip",
            indicator_value="1.2.3.4",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "Invalid workflow UUID" in data["error"]

    async def test_execute_invalid_indicator_type(self) -> None:
        wf_uuid = uuid.uuid4()
        from app.mcp.tools.workflows import execute_workflow
        result = await execute_workflow(
            workflow_uuid=str(wf_uuid),
            indicator_type="bogus",
            indicator_value="test",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "Invalid indicator_type" in data["error"]

    async def test_execute_invalid_alert_uuid(self) -> None:
        wf_uuid = uuid.uuid4()
        from app.mcp.tools.workflows import execute_workflow
        result = await execute_workflow(
            workflow_uuid=str(wf_uuid),
            indicator_type="ip",
            indicator_value="1.2.3.4",
            ctx=_mock_ctx(),
            alert_uuid="bad-uuid",
        )
        data = json.loads(result)
        assert "Invalid alert UUID" in data["error"]

    async def test_execute_workflow_not_found(self) -> None:
        wf_uuid = uuid.uuid4()
        session_ctx, mock_session = _patch_session()
        mock_wf_repo = MagicMock()
        mock_wf_repo.get_by_uuid = AsyncMock(return_value=None)

        with (
            patch("app.mcp.tools.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.workflows.check_scope", _scope_pass()),
            patch("app.mcp.tools.workflows.WorkflowRepository", return_value=mock_wf_repo),
        ):
            from app.mcp.tools.workflows import execute_workflow
            result = await execute_workflow(
                workflow_uuid=str(wf_uuid),
                indicator_type="ip",
                indicator_value="1.2.3.4",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert "Workflow not found" in data["error"]

    async def test_execute_inactive_workflow_rejected(self) -> None:
        """Inactive workflows cannot be executed."""
        wf_uuid = uuid.uuid4()
        wf = _mock_workflow(wf_uuid=wf_uuid, is_active=False, state="inactive")

        session_ctx, mock_session = _patch_session()
        mock_wf_repo = MagicMock()
        mock_wf_repo.get_by_uuid = AsyncMock(return_value=wf)

        with (
            patch("app.mcp.tools.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.workflows.check_scope", _scope_pass()),
            patch("app.mcp.tools.workflows.WorkflowRepository", return_value=mock_wf_repo),
        ):
            from app.mcp.tools.workflows import execute_workflow
            result = await execute_workflow(
                workflow_uuid=str(wf_uuid),
                indicator_type="ip",
                indicator_value="1.2.3.4",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert "inactive" in data["error"].lower() or "draft" in data["error"].lower()

    async def test_execute_draft_workflow_rejected(self) -> None:
        """Draft workflows cannot be executed."""
        wf_uuid = uuid.uuid4()
        wf = _mock_workflow(wf_uuid=wf_uuid, state="draft", is_active=True)

        session_ctx, mock_session = _patch_session()
        mock_wf_repo = MagicMock()
        mock_wf_repo.get_by_uuid = AsyncMock(return_value=wf)

        with (
            patch("app.mcp.tools.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.workflows.check_scope", _scope_pass()),
            patch("app.mcp.tools.workflows.WorkflowRepository", return_value=mock_wf_repo),
        ):
            from app.mcp.tools.workflows import execute_workflow
            result = await execute_workflow(
                workflow_uuid=str(wf_uuid),
                indicator_type="ip",
                indicator_value="1.2.3.4",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert "cannot be executed" in data["error"].lower()

    async def test_execute_approval_gate_without_reason(self) -> None:
        """Workflow requiring approval without reason returns error."""
        wf_uuid = uuid.uuid4()
        wf = _mock_workflow(wf_uuid=wf_uuid, approval_mode="always")

        session_ctx, mock_session = _patch_session()
        mock_wf_repo = MagicMock()
        mock_wf_repo.get_by_uuid = AsyncMock(return_value=wf)

        with (
            patch("app.mcp.tools.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.workflows.check_scope", _scope_pass()),
            patch("app.mcp.tools.workflows.WorkflowRepository", return_value=mock_wf_repo),
        ):
            from app.mcp.tools.workflows import execute_workflow
            result = await execute_workflow(
                workflow_uuid=str(wf_uuid),
                indicator_type="ip",
                indicator_value="1.2.3.4",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert "reason is required" in data["error"]

    async def test_execute_approval_gate_without_confidence(self) -> None:
        """Workflow requiring approval without confidence returns error."""
        wf_uuid = uuid.uuid4()
        wf = _mock_workflow(wf_uuid=wf_uuid, approval_mode="always")

        session_ctx, mock_session = _patch_session()
        mock_wf_repo = MagicMock()
        mock_wf_repo.get_by_uuid = AsyncMock(return_value=wf)

        with (
            patch("app.mcp.tools.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.workflows.check_scope", _scope_pass()),
            patch("app.mcp.tools.workflows.WorkflowRepository", return_value=mock_wf_repo),
        ):
            from app.mcp.tools.workflows import execute_workflow
            result = await execute_workflow(
                workflow_uuid=str(wf_uuid),
                indicator_type="ip",
                indicator_value="1.2.3.4",
                ctx=_mock_ctx(),
                reason="High confidence malicious IP",
            )

        data = json.loads(result)
        assert "confidence is required" in data["error"]

    async def test_execute_approval_gate_success(self) -> None:
        """Workflow with approval gate returns pending_approval status."""
        wf_uuid = uuid.uuid4()
        wf = _mock_workflow(wf_uuid=wf_uuid, approval_mode="always")
        approval_req = _mock_approval_request()

        session_ctx, mock_session = _patch_session()
        mock_wf_repo = MagicMock()
        mock_wf_repo.get_by_uuid = AsyncMock(return_value=wf)

        mock_notifier = MagicMock()
        mock_notifier.notifier_name = "none"

        mock_queue = MagicMock()
        mock_queue.enqueue = AsyncMock(return_value="task-1")

        with (
            patch("app.mcp.tools.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.workflows.check_scope", _scope_pass()),
            patch("app.mcp.tools.workflows.WorkflowRepository", return_value=mock_wf_repo),
            patch(
                "app.workflows.approval.create_approval_request",
                new_callable=AsyncMock, return_value=approval_req,
            ),
            patch(
                "app.workflows.notifiers.factory.get_approval_notifier",
                return_value=mock_notifier,
            ),
            patch("app.queue.factory.get_queue_backend", return_value=mock_queue),
            patch("app.config.settings"),
        ):
            from app.mcp.tools.workflows import execute_workflow
            result = await execute_workflow(
                workflow_uuid=str(wf_uuid),
                indicator_type="ip",
                indicator_value="1.2.3.4",
                ctx=_mock_ctx(),
                reason="Malicious IP detected",
                confidence=0.95,
            )

        data = json.loads(result)
        assert data["status"] == "pending_approval"
        assert "approval_request_uuid" in data
        assert "expires_at" in data

    async def test_execute_scope_failure(self) -> None:
        wf_uuid = uuid.uuid4()
        session_ctx, mock_session = _patch_session()

        with (
            patch("app.mcp.tools.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.workflows.check_scope", _scope_fail()),
            patch("app.mcp.tools.workflows.WorkflowRepository"),
        ):
            from app.mcp.tools.workflows import execute_workflow
            result = await execute_workflow(
                workflow_uuid=str(wf_uuid),
                indicator_type="ip",
                indicator_value="1.2.3.4",
                ctx=_mock_ctx(),
            )

        data = json.loads(result)
        assert "error" in data

    async def test_execute_with_alert_uuid(self) -> None:
        """execute_workflow resolves alert_uuid to alert_id in trigger_context."""
        wf_uuid = uuid.uuid4()
        alert_uuid = uuid.uuid4()
        wf = _mock_workflow(wf_uuid=wf_uuid, approval_mode="never")
        alert = _mock_alert(alert_uuid=alert_uuid)
        run = _mock_workflow_run()

        session_ctx, mock_session = _patch_session()
        mock_wf_repo = MagicMock()
        mock_wf_repo.get_by_uuid = AsyncMock(return_value=wf)
        mock_run_repo = MagicMock()
        mock_run_repo.create = AsyncMock(return_value=run)

        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=alert)

        mock_queue = MagicMock()
        mock_queue.enqueue = AsyncMock(return_value="task-1")

        with (
            patch("app.mcp.tools.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.workflows.check_scope", _scope_pass()),
            patch("app.mcp.tools.workflows.WorkflowRepository", return_value=mock_wf_repo),
            patch("app.mcp.tools.workflows.WorkflowRunRepository", return_value=mock_run_repo),
            patch(
                "app.repositories.alert_repository.AlertRepository",
                return_value=mock_alert_repo,
            ),
            patch("app.queue.factory.get_queue_backend", return_value=mock_queue),
        ):
            from app.mcp.tools.workflows import execute_workflow
            result = await execute_workflow(
                workflow_uuid=str(wf_uuid),
                indicator_type="ip",
                indicator_value="1.2.3.4",
                ctx=_mock_ctx(),
                alert_uuid=str(alert_uuid),
            )

        data = json.loads(result)
        assert data["status"] == "queued"

    async def test_execute_alert_not_found(self) -> None:
        """Alert UUID that doesn't exist returns error."""
        wf_uuid = uuid.uuid4()
        alert_uuid = uuid.uuid4()
        wf = _mock_workflow(wf_uuid=wf_uuid, approval_mode="never")

        session_ctx, mock_session = _patch_session()
        mock_wf_repo = MagicMock()
        mock_wf_repo.get_by_uuid = AsyncMock(return_value=wf)

        mock_alert_repo = MagicMock()
        mock_alert_repo.get_by_uuid = AsyncMock(return_value=None)

        with (
            patch("app.mcp.tools.workflows.AsyncSessionLocal", session_ctx),
            patch("app.mcp.tools.workflows.check_scope", _scope_pass()),
            patch("app.mcp.tools.workflows.WorkflowRepository", return_value=mock_wf_repo),
            patch(
                "app.repositories.alert_repository.AlertRepository",
                return_value=mock_alert_repo,
            ),
        ):
            from app.mcp.tools.workflows import execute_workflow
            result = await execute_workflow(
                workflow_uuid=str(wf_uuid),
                indicator_type="ip",
                indicator_value="1.2.3.4",
                ctx=_mock_ctx(),
                alert_uuid=str(alert_uuid),
            )

        data = json.loads(result)
        assert "Alert not found" in data["error"]


# ===========================================================================
# Error handling — shared across tools
# ===========================================================================


class TestToolErrorHandling:
    """Verify that tools return JSON error objects, never unhandled exceptions."""

    async def test_search_alerts_returns_json_on_bad_input(self) -> None:
        """Bad date inputs return JSON error, not Python exception."""
        from app.mcp.tools.alerts import search_alerts
        result = await search_alerts(ctx=_mock_ctx(), from_time="2026-99-99")
        data = json.loads(result)
        assert "error" in data

    async def test_post_finding_invalid_confidence_returns_json(self) -> None:
        """Invalid confidence returns JSON error, not exception."""
        from app.mcp.tools.alerts import post_alert_finding
        result = await post_alert_finding(
            alert_uuid=str(uuid.uuid4()),
            summary="test",
            confidence="extreme",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "error" in data

    async def test_update_status_invalid_returns_json(self) -> None:
        """Invalid status returns JSON error, not exception."""
        from app.mcp.tools.alerts import update_alert_status
        result = await update_alert_status(
            alert_uuid=str(uuid.uuid4()),
            status="NotAStatus",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "error" in data

    async def test_execute_workflow_bad_indicator_type_returns_json(self) -> None:
        """Invalid indicator type returns JSON error."""
        from app.mcp.tools.workflows import execute_workflow
        result = await execute_workflow(
            workflow_uuid=str(uuid.uuid4()),
            indicator_type="not_real",
            indicator_value="test",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "error" in data

    async def test_enrich_indicator_bad_type_returns_json(self) -> None:
        """Invalid indicator type returns JSON error."""
        from app.mcp.tools.enrichment import enrich_indicator
        result = await enrich_indicator(
            type="not_real",
            value="test",
            ctx=_mock_ctx(),
        )
        data = json.loads(result)
        assert "error" in data
