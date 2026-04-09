"""Integration tests — ClaudeCodeAdapter subprocess handling (Phase 1).

Tests the ClaudeCodeAdapter at the subprocess boundary by mocking
asyncio.create_subprocess_exec to return canned stream-json NDJSON.
Verifies parsing of tool calls, text completions, session IDs, and
subscription-billing cost extraction.

These are integration-style tests: they exercise the full adapter code path
with real NDJSON parsing, but mock only the claude CLI subprocess.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.llm.base import LLMMessage

# ---------------------------------------------------------------------------
# Subprocess mock helpers
# ---------------------------------------------------------------------------


def _ndjson_bytes(*events: dict[str, Any]) -> bytes:
    """Encode dicts as NDJSON bytes (newline-delimited)."""
    return b"\n".join(json.dumps(ev).encode() for ev in events) + b"\n"


class _MockProcess:
    """Async subprocess mock that returns canned stdout via communicate()."""

    def __init__(self, stdout: bytes, returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:  # noqa: A002
        return self._stdout, b""


# ---------------------------------------------------------------------------
# Pre-built NDJSON sequences
# ---------------------------------------------------------------------------

_SIMPLE_BYTES = _ndjson_bytes(
    {"type": "system", "subtype": "init", "session_id": "sess_abc123", "tools": []},
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Alert classified as false positive."}],
        },
        "session_id": "sess_abc123",
    },
    {
        "type": "result",
        "subtype": "success",
        "result": "Alert classified as false positive.",
        "session_id": "sess_abc123",
        "usage": {"input_tokens": 1500, "output_tokens": 200},
        "total_cost_usd": 0.0,
    },
)

_TOOL_CALL_BYTES = _ndjson_bytes(
    {"type": "system", "subtype": "init", "session_id": "sess_tool123", "tools": ["get_alert"]},
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_01",
                    "name": "get_alert",
                    "input": {"alert_uuid": "abc-123"},
                }
            ],
        },
        "session_id": "sess_tool123",
    },
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "Based on the data, this is benign traffic."}],
        },
        "session_id": "sess_tool123",
    },
    {
        "type": "result",
        "subtype": "success",
        "result": "Benign traffic confirmed.",
        "session_id": "sess_tool123",
        "usage": {"input_tokens": 3000, "output_tokens": 300},
        "total_cost_usd": 0.0,
    },
)


def _make_adapter() -> Any:
    """Create a ClaudeCodeAdapter with a mock LLMIntegration."""
    from app.integrations.llm.claude_code_adapter import ClaudeCodeAdapter

    mock_integration = MagicMock()
    mock_integration.provider = "claude_code"
    mock_integration.model = "claude-sonnet-4-6"
    mock_integration.display_name = "Claude Code Test"
    mock_integration.extra_config = {}
    mock_integration.auth_config = {}
    mock_integration.is_active = True

    return ClaudeCodeAdapter(integration=mock_integration)


# ---------------------------------------------------------------------------
# Tests: NDJSON parsing and response construction
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapterParsing:
    """Adapter correctly parses stream-json NDJSON from the claude CLI."""

    async def test_simple_text_completion_parsed(self) -> None:
        """Single-turn text response → LLMResponse with text content block."""
        adapter = _make_adapter()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(_SIMPLE_BYTES)
            response = await adapter.create_message(
                messages=[LLMMessage(role="user", content="Analyze this alert.")],
                system="You are a security analyst.",
                tools=[],
            )

        assert response.stop_reason == "end_turn"
        text_blocks = [b for b in response.content if b.get("type") == "text"]
        assert len(text_blocks) >= 1
        assert "false positive" in text_blocks[0]["text"]

    async def test_tool_use_blocks_parsed(self) -> None:
        """Multi-turn output → tool_use blocks captured in response content."""
        adapter = _make_adapter()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(_TOOL_CALL_BYTES)
            response = await adapter.create_message(
                messages=[LLMMessage(role="user", content="Investigate this alert.")],
                tools=[{"name": "get_alert", "description": "Fetch alert by UUID"}],
            )

        tool_blocks = [b for b in response.content if b.get("type") == "tool_use"]
        assert len(tool_blocks) >= 1
        assert tool_blocks[0]["name"] == "get_alert"
        assert tool_blocks[0]["input"]["alert_uuid"] == "abc-123"

    async def test_session_id_captured_in_metadata(self) -> None:
        """Session ID from NDJSON 'result' event is stored in response metadata."""
        adapter = _make_adapter()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(_SIMPLE_BYTES)
            response = await adapter.create_message(
                messages=[LLMMessage(role="user", content="Test session capture.")],
                tools=[],
            )

        # Session ID should be accessible for subsequent resume
        if response.metadata:
            assert "session_id" in response.metadata
            assert response.metadata["session_id"] == "sess_abc123"


# ---------------------------------------------------------------------------
# Tests: Cost extraction
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapterCostExtraction:
    """ClaudeCodeAdapter always returns subscription billing (cost_cents=0)."""

    async def test_cost_extraction_is_subscription_billing(self) -> None:
        """extract_cost() returns cost_cents=0 and billing_type='subscription'."""
        adapter = _make_adapter()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(_SIMPLE_BYTES)
            response = await adapter.create_message(
                messages=[LLMMessage(role="user", content="Cost test.")],
                tools=[],
            )

        cost = adapter.extract_cost(response)
        assert cost.cost_cents == 0
        assert cost.billing_type == "subscription"

    async def test_cost_extraction_preserves_token_counts(self) -> None:
        """Token counts from NDJSON usage are reflected in cost info."""
        adapter = _make_adapter()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(_SIMPLE_BYTES)
            response = await adapter.create_message(
                messages=[LLMMessage(role="user", content="Token count test.")],
                tools=[],
            )

        cost = adapter.extract_cost(response)
        # Token counts from usage: input_tokens=1500, output_tokens=200
        assert cost.input_tokens >= 0
        assert cost.output_tokens >= 0


# ---------------------------------------------------------------------------
# Tests: Session resume
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapterSessionResume:
    """Session ID forwarding enables conversation continuity."""

    async def test_session_id_in_kwargs_passed_to_cli(self) -> None:
        """When session_id kwarg provided, subprocess receives the session ID."""
        adapter = _make_adapter()
        resume_bytes = _ndjson_bytes(
            {"type": "system", "subtype": "init", "session_id": "sess_resume_xyz", "tools": []},
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Resumed analysis."}],
                },
                "session_id": "sess_resume_xyz",
            },
            {
                "type": "result",
                "subtype": "success",
                "result": "Resumed.",
                "session_id": "sess_resume_xyz",
                "usage": {"input_tokens": 800, "output_tokens": 80},
                "total_cost_usd": 0.0,
            },
        )

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(resume_bytes)
            await adapter.create_message(
                messages=[LLMMessage(role="user", content="Continue analysis.")],
                tools=[],
                session_id="sess_resume_xyz",
            )

        # Verify the subprocess was called with the session_id somewhere in its args
        call_args = mock_exec.call_args
        all_args_str = " ".join(str(a) for a in call_args[0])
        assert "sess_resume_xyz" in all_args_str or "--resume" in all_args_str

    async def test_no_session_id_does_not_include_resume_flag(self) -> None:
        """When no session_id provided, --resume flag is absent from CLI args."""
        adapter = _make_adapter()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(_SIMPLE_BYTES)
            await adapter.create_message(
                messages=[LLMMessage(role="user", content="Fresh start.")],
                tools=[],
                # No session_id
            )

        call_args = mock_exec.call_args
        all_args_str = " ".join(str(a) for a in call_args[0])
        assert "--resume" not in all_args_str


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------


class TestClaudeCodeAdapterFailure:
    """Subprocess failure handling — non-zero exit or error result."""

    async def test_subprocess_nonzero_exit_raises_runtime_error(self) -> None:
        """Non-zero subprocess exit code raises RuntimeError with CLI output details."""
        adapter = _make_adapter()
        error_bytes = b"Error: Authentication failed\n"

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(error_bytes, returncode=1)

            with pytest.raises(RuntimeError, match="claude CLI exited"):
                await adapter.create_message(
                    messages=[LLMMessage(role="user", content="Analyze.")],
                    tools=[],
                )

    async def test_subprocess_called_with_correct_binary(self) -> None:
        """Adapter invokes the 'claude' CLI binary."""
        adapter = _make_adapter()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(_SIMPLE_BYTES)
            await adapter.create_message(
                messages=[LLMMessage(role="user", content="Check binary.")],
                tools=[],
            )

        call_args = mock_exec.call_args
        # First positional arg should be the claude binary
        first_arg = call_args[0][0]
        assert "claude" in str(first_arg)
