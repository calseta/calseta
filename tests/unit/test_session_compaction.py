"""Unit tests for session compaction handler (C4: Session Compaction).

Tests the ``compact_session`` function at ``app/services/session_compaction.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.integrations.llm.base import CostInfo, LLMResponse
from app.services.session_compaction import (
    _MAX_SUMMARY_CHARS,
    _serialize_messages_for_summary,
    compact_session,
)


def _make_session(messages: list | None = None, needs_compaction: bool = True) -> MagicMock:
    """Build a mock AgentTaskSession with controllable session_params."""
    session = MagicMock()
    session.id = 42
    params: dict = {}
    if messages is not None:
        params["messages"] = messages
    if needs_compaction:
        params["needs_compaction"] = True
    session.session_params = params
    return session


def _make_adapter(
    summary_text: str = "## Summary\nKey finding: malicious IP detected.",
    cost: CostInfo | None = None,
    raise_on_call: Exception | None = None,
) -> AsyncMock:
    """Build a mock LLMProviderAdapter whose create_message returns a canned LLMResponse."""
    adapter = AsyncMock()
    if raise_on_call is not None:
        adapter.create_message.side_effect = raise_on_call
    else:
        response = LLMResponse(
            content=[{"type": "text", "text": summary_text}],
            stop_reason="end_turn",
            usage=cost or CostInfo(input_tokens=500, output_tokens=200, cost_cents=3),
        )
        adapter.create_message.return_value = response
    return adapter


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompactSession:
    """Tests for compact_session()."""

    @pytest.mark.asyncio
    async def test_compaction_with_messages_returns_updated_params(self):
        """Non-empty messages: LLM called, session_params updated correctly."""
        messages = [
            {"role": "user", "content": "Investigate alert 123"},
            {"role": "assistant", "content": "Looking into it..."},
        ]
        session = _make_session(messages=messages)
        adapter = _make_adapter(summary_text="## Handoff\nAlert 123 triaged.")

        result = await compact_session(session, adapter)

        assert result["compacted"] is True
        params = result["session_params"]
        assert params["session_handoff_markdown"] == "## Handoff\nAlert 123 triaged."
        assert "messages" not in params
        assert params["needs_compaction"] is False
        assert "compacted_at" in params
        assert result["cost"] is not None
        assert result["cost"].input_tokens == 500

    @pytest.mark.asyncio
    async def test_compaction_empty_messages_returns_immediately(self):
        """Empty messages list: no LLM call, compacted=False."""
        session = _make_session(messages=[])
        adapter = _make_adapter()

        result = await compact_session(session, adapter)

        assert result["compacted"] is False
        assert result["cost"] is None
        adapter.create_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_compaction_no_messages_key_returns_immediately(self):
        """No 'messages' key at all: no LLM call, compacted=False."""
        session = MagicMock()
        session.id = 1
        session.session_params = {"needs_compaction": True}

        adapter = _make_adapter()
        result = await compact_session(session, adapter)

        assert result["compacted"] is False
        adapter.create_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_compaction_llm_failure_returns_compacted_false(self):
        """LLM call raises: compacted=False, original session_params unchanged."""
        messages = [{"role": "user", "content": "check alert"}]
        session = _make_session(messages=messages)
        adapter = _make_adapter(raise_on_call=RuntimeError("LLM unavailable"))

        result = await compact_session(session, adapter)

        assert result["compacted"] is False
        assert result["cost"] is None
        # Original messages should still be in the session_params
        assert result["session_params"].get("messages") == messages

    @pytest.mark.asyncio
    async def test_compaction_empty_summary_returns_compacted_false(self):
        """LLM returns empty text: compacted=False, cost still returned."""
        messages = [{"role": "user", "content": "check alert"}]
        session = _make_session(messages=messages)
        adapter = _make_adapter(summary_text="")

        result = await compact_session(session, adapter)

        assert result["compacted"] is False
        assert result["cost"] is not None  # Usage is still tracked
        # Messages should be untouched
        assert result["session_params"].get("messages") == messages

    @pytest.mark.asyncio
    async def test_summary_truncated_to_max_chars(self):
        """Summary exceeding _MAX_SUMMARY_CHARS is truncated."""
        long_summary = "A" * (_MAX_SUMMARY_CHARS + 5000)
        messages = [{"role": "user", "content": "investigate"}]
        session = _make_session(messages=messages)
        adapter = _make_adapter(summary_text=long_summary)

        result = await compact_session(session, adapter)

        assert result["compacted"] is True
        handoff = result["session_params"]["session_handoff_markdown"]
        assert len(handoff) == _MAX_SUMMARY_CHARS

    @pytest.mark.asyncio
    async def test_cost_info_returned_on_success(self):
        """Successful compaction returns the CostInfo from the LLM call."""
        cost = CostInfo(input_tokens=1200, output_tokens=400, cost_cents=8)
        messages = [{"role": "user", "content": "analyze"}]
        session = _make_session(messages=messages)
        adapter = _make_adapter(cost=cost)

        result = await compact_session(session, adapter)

        assert result["compacted"] is True
        assert result["cost"] is cost
        assert result["cost"].input_tokens == 1200
        assert result["cost"].output_tokens == 400
        assert result["cost"].cost_cents == 8

    @pytest.mark.asyncio
    async def test_compacted_at_is_iso_timestamp(self):
        """compacted_at in session_params is a valid ISO 8601 string."""
        from datetime import datetime

        messages = [{"role": "user", "content": "go"}]
        session = _make_session(messages=messages)
        adapter = _make_adapter()

        result = await compact_session(session, adapter)

        ts = result["session_params"]["compacted_at"]
        # Should parse without error
        parsed = datetime.fromisoformat(ts)
        assert parsed is not None


class TestSerializeMessagesForSummary:
    """Tests for _serialize_messages_for_summary()."""

    def test_text_content_string(self):
        """Simple string content is serialized as [role]: content."""
        messages = [{"role": "user", "content": "Hello agent"}]
        result = _serialize_messages_for_summary(messages)
        assert "[user]: Hello agent" in result

    def test_tool_use_block(self):
        """tool_use blocks serialize as [role/tool_use]: name(input_json)."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "search_alerts",
                        "input": {"query": "malware"},
                    }
                ],
            }
        ]
        result = _serialize_messages_for_summary(messages)
        assert "[assistant/tool_use]: search_alerts(" in result
        assert "malware" in result

    def test_tool_result_block(self):
        """tool_result blocks serialize as [role/tool_result]: content."""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "content": '{"found": 3}',
                    }
                ],
            }
        ]
        result = _serialize_messages_for_summary(messages)
        assert "[user/tool_result]:" in result
        assert '{"found": 3}' in result

    def test_text_block_in_list(self):
        """text blocks inside a content list serialize correctly."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I found the issue."},
                ],
            }
        ]
        result = _serialize_messages_for_summary(messages)
        assert "[assistant]: I found the issue." in result

    def test_mixed_blocks(self):
        """Multiple block types in one message are all serialized."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Calling tool..."},
                    {"type": "tool_use", "name": "enrich_indicator", "input": {"ip": "1.2.3.4"}},
                ],
            }
        ]
        result = _serialize_messages_for_summary(messages)
        assert "[assistant]: Calling tool..." in result
        assert "[assistant/tool_use]: enrich_indicator(" in result

    def test_empty_messages_returns_empty_string(self):
        """Empty list produces empty string."""
        assert _serialize_messages_for_summary([]) == ""

    def test_missing_role_defaults_to_unknown(self):
        """Message without a role key uses 'unknown'."""
        messages = [{"content": "orphan message"}]
        result = _serialize_messages_for_summary(messages)
        assert "[unknown]: orphan message" in result

    def test_long_string_content_is_truncated(self):
        """String content longer than 3000 chars is truncated."""
        long_text = "X" * 5000
        messages = [{"role": "user", "content": long_text}]
        result = _serialize_messages_for_summary(messages)
        # The content portion after "[user]: " should be at most 3000 chars
        content_part = result.split("[user]: ")[1]
        assert len(content_part) == 3000

    def test_tool_result_content_truncated(self):
        """tool_result content longer than 1000 chars is truncated."""
        long_content = "Y" * 2000
        messages = [
            {
                "role": "user",
                "content": [{"type": "tool_result", "content": long_content}],
            }
        ]
        result = _serialize_messages_for_summary(messages)
        # The str(content)[:1000] should produce 1000 Y's
        assert "Y" * 1000 in result
        assert "Y" * 1001 not in result
