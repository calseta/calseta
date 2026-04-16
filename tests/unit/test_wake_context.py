"""Unit tests for PromptBuilder._build_wake_context — C2: Wake Context Enhancement."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.runtime.models import RuntimeContext
from app.runtime.prompt_builder import PromptBuilder, _xml_escape


def _make_builder() -> PromptBuilder:
    """Create a PromptBuilder with a mock DB session."""
    db = AsyncMock()
    return PromptBuilder(db)


def _make_context(**overrides) -> RuntimeContext:
    """Create a RuntimeContext with sensible defaults."""
    defaults = {
        "agent_id": 1,
        "task_key": "alert:42",
        "heartbeat_run_id": 100,
        "alert_id": 42,
    }
    defaults.update(overrides)
    return RuntimeContext(**defaults)


class TestBuildWakeContext:
    """Tests for PromptBuilder._build_wake_context()."""

    def test_returns_empty_string_when_no_wake_reason(self) -> None:
        """No wake_reason -> empty string."""
        builder = _make_builder()
        ctx = _make_context(wake_reason=None)

        result = builder._build_wake_context(ctx)

        assert result == ""

    def test_comment_wake_reason_directive(self) -> None:
        """wake_reason='comment' -> XML with comment-specific directive."""
        builder = _make_builder()
        ctx = _make_context(wake_reason="comment")

        result = builder._build_wake_context(ctx)

        assert '<wake_context reason="comment">' in result
        assert "New analyst input since your last run" in result
        assert "</wake_context>" in result

    def test_retry_wake_reason_directive(self) -> None:
        """wake_reason='retry' -> XML with retry-specific directive."""
        builder = _make_builder()
        ctx = _make_context(wake_reason="retry")

        result = builder._build_wake_context(ctx)

        assert '<wake_context reason="retry">' in result
        assert "retry of a previous run that failed" in result
        assert "</wake_context>" in result

    def test_custom_wake_reason_directive(self) -> None:
        """Unknown wake_reason -> generic directive with escaped reason."""
        builder = _make_builder()
        ctx = _make_context(wake_reason="automation")

        result = builder._build_wake_context(ctx)

        assert '<wake_context reason="automation">' in result
        assert "Agent re-triggered: automation" in result

    def test_includes_comments_block(self) -> None:
        """wake_comments populated -> <comments> block with individual entries."""
        builder = _make_builder()
        ctx = _make_context(
            wake_reason="comment",
            wake_comments=[
                {
                    "content": "Check the 10.0.0.1 IP",
                    "author": "cai_analyst",
                    "timestamp": "2026-04-15T12:00:00",
                },
                {
                    "content": "Also check DNS logs",
                    "author": "cai_admin",
                    "timestamp": "2026-04-15T12:05:00",
                },
            ],
        )

        result = builder._build_wake_context(ctx)

        assert "<comments>" in result
        assert "</comments>" in result
        assert 'author="cai_analyst"' in result
        assert 'author="cai_admin"' in result
        assert "Check the 10.0.0.1 IP" in result
        assert "Also check DNS logs" in result

    def test_no_comments_block_when_wake_comments_is_none(self) -> None:
        """No wake_comments -> no <comments> tag in output."""
        builder = _make_builder()
        ctx = _make_context(wake_reason="retry", wake_comments=None)

        result = builder._build_wake_context(ctx)

        assert "<comments>" not in result

    def test_no_comments_block_when_wake_comments_is_empty(self) -> None:
        """Empty wake_comments list -> no <comments> tag in output."""
        builder = _make_builder()
        ctx = _make_context(wake_reason="comment", wake_comments=[])

        result = builder._build_wake_context(ctx)

        assert "<comments>" not in result

    def test_xml_escapes_special_characters_in_content(self) -> None:
        """Special XML chars in comment content are escaped."""
        builder = _make_builder()
        ctx = _make_context(
            wake_reason="comment",
            wake_comments=[
                {
                    "content": 'Alert title has <script> & "quotes"',
                    "author": "test",
                    "timestamp": "2026-04-15T12:00:00",
                },
            ],
        )

        result = builder._build_wake_context(ctx)

        # Content should be XML-escaped
        assert "&lt;script&gt;" in result
        assert "&amp;" in result
        assert "&quot;quotes&quot;" in result

    def test_xml_escapes_special_characters_in_author(self) -> None:
        """Special XML chars in author name are escaped."""
        builder = _make_builder()
        ctx = _make_context(
            wake_reason="comment",
            wake_comments=[
                {
                    "content": "test",
                    "author": '<admin>"user"',
                    "timestamp": "2026-04-15T12:00:00",
                },
            ],
        )

        result = builder._build_wake_context(ctx)

        assert 'author="&lt;admin&gt;&quot;user&quot;"' in result

    def test_xml_escapes_wake_reason_in_attribute(self) -> None:
        """Special chars in wake_reason itself are escaped in the attribute."""
        builder = _make_builder()
        ctx = _make_context(wake_reason='test<>&"reason')

        result = builder._build_wake_context(ctx)

        assert 'reason="test&lt;&gt;&amp;&quot;reason"' in result

    def test_comment_with_missing_fields_uses_defaults(self) -> None:
        """Comment dict missing 'author' or 'timestamp' uses defaults."""
        builder = _make_builder()
        ctx = _make_context(
            wake_reason="comment",
            wake_comments=[
                {"content": "bare comment"},  # No author, no timestamp
            ],
        )

        result = builder._build_wake_context(ctx)

        # Default author is "analyst", default timestamp is ""
        assert 'author="analyst"' in result
        assert "bare comment" in result


class TestWakeContextIntegrationWithLayer4:
    """Tests verifying wake context is prepended to alert context in layer 4."""

    async def test_wake_context_prepended_to_alert_block(self) -> None:
        """When wake_reason is set and alert exists, wake context comes first."""
        builder = _make_builder()
        ctx = _make_context(
            wake_reason="comment",
            wake_comments=[{"content": "Please check", "author": "analyst", "timestamp": "now"}],
        )

        # Mock the alert lookup
        mock_alert = MagicMock()
        mock_alert.uuid = "550e8400-e29b-41d4-a716-446655440000"
        mock_alert.title = "Test Alert"
        mock_alert.severity = "High"
        mock_alert.status = "Open"
        mock_alert.source_name = "elastic"
        mock_alert.description = "Test desc"
        mock_alert.occurred_at = None
        mock_alert.enrichment_status = "Pending"
        mock_alert.is_enriched = False
        mock_alert.tags = []
        mock_alert.detection_rule_id = None
        mock_alert.agent_findings = []

        with patch("app.repositories.alert_repository.AlertRepository") as MockAlertRepo:
            repo_instance = AsyncMock()
            repo_instance.get_by_id = AsyncMock(return_value=mock_alert)
            MockAlertRepo.return_value = repo_instance

            # Mock _load_alert_indicators
            with patch.object(builder, "_load_alert_indicators", new_callable=AsyncMock, return_value=[]):
                result = await builder._build_layer4_alert_context(ctx)

        assert result is not None
        # Wake context should come before alert_context
        wake_pos = result.index("<wake_context")
        alert_pos = result.index("<alert_context>")
        assert wake_pos < alert_pos

    async def test_no_wake_context_when_reason_is_none(self) -> None:
        """When wake_reason is None, layer 4 has only alert_context block."""
        builder = _make_builder()
        ctx = _make_context(wake_reason=None)

        mock_alert = MagicMock()
        mock_alert.uuid = "550e8400-e29b-41d4-a716-446655440000"
        mock_alert.title = "Test Alert"
        mock_alert.severity = "High"
        mock_alert.status = "Open"
        mock_alert.source_name = "elastic"
        mock_alert.description = "Test desc"
        mock_alert.occurred_at = None
        mock_alert.enrichment_status = "Pending"
        mock_alert.is_enriched = False
        mock_alert.tags = []
        mock_alert.detection_rule_id = None
        mock_alert.agent_findings = []

        with patch("app.repositories.alert_repository.AlertRepository") as MockAlertRepo:
            repo_instance = AsyncMock()
            repo_instance.get_by_id = AsyncMock(return_value=mock_alert)
            MockAlertRepo.return_value = repo_instance

            with patch.object(builder, "_load_alert_indicators", new_callable=AsyncMock, return_value=[]):
                result = await builder._build_layer4_alert_context(ctx)

        assert result is not None
        assert "<wake_context" not in result
        assert "<alert_context>" in result

    async def test_wake_context_returned_alone_when_no_alert(self) -> None:
        """When alert_id is None but wake_reason is set, only wake context returned."""
        builder = _make_builder()
        ctx = _make_context(alert_id=None, wake_reason="automation")

        result = await builder._build_layer4_alert_context(ctx)

        assert result is not None
        assert "<wake_context" in result
        assert "<alert_context>" not in result


class TestXmlEscapeHelper:
    """Tests for the _xml_escape utility function."""

    def test_escapes_ampersand(self) -> None:
        assert _xml_escape("foo & bar") == "foo &amp; bar"

    def test_escapes_quotes(self) -> None:
        assert _xml_escape('say "hello"') == "say &quot;hello&quot;"

    def test_escapes_angle_brackets(self) -> None:
        assert _xml_escape("<tag>") == "&lt;tag&gt;"

    def test_escapes_all_together(self) -> None:
        assert _xml_escape('<a & "b">') == "&lt;a &amp; &quot;b&quot;&gt;"

    def test_passthrough_safe_string(self) -> None:
        assert _xml_escape("hello world 123") == "hello world 123"
