"""Unit tests — ClaudeCodeAdapter structured error mapping (S12).

Covers ``ClaudeCodeError`` and ``_classify_failure`` dispatch:
  - Quota errors surfaced via assistant content ("Credit balance is too low")
  - Rate-limit / auth / generic provider errors via either channel
  - Stderr-only "command not found" mapped to llm_cli_missing
  - FileNotFoundError raises a structured ClaudeCodeError
  - Stderr warnings on a successful (returncode == 0) run are NOT logged
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.llm.base import LLMMessage
from app.integrations.llm.claude_code_adapter import (
    ClaudeCodeAdapter,
    ClaudeCodeError,
    _classify_failure,
)

# ---------------------------------------------------------------------------
# Mock subprocess plumbing (mirrors the integration-test helpers, kept local
# so this unit test doesn't depend on the integration test module).
# ---------------------------------------------------------------------------


def _ndjson_bytes(*events: dict[str, Any]) -> bytes:
    return b"\n".join(json.dumps(ev).encode() for ev in events) + b"\n"


class _MockStreamReader:
    def __init__(self, data: bytes) -> None:
        self._lines = data.split(b"\n")
        self._index = 0
        self._all = data

    async def readline(self) -> bytes:
        if self._index >= len(self._lines):
            return b""
        line = self._lines[self._index]
        self._index += 1
        if not line and self._index >= len(self._lines):
            return b""
        return line + b"\n"

    async def read(self) -> bytes:
        return self._all


class _MockStreamWriter:
    def write(self, data: bytes) -> None:
        pass

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        pass


class _MockProcess:
    def __init__(
        self,
        stdout: bytes,
        returncode: int = 0,
        stderr: bytes = b"",
    ) -> None:
        self.returncode = returncode
        self.stdin = _MockStreamWriter()
        self.stdout = _MockStreamReader(stdout)
        self.stderr = _MockStreamReader(stderr)

    async def wait(self) -> int:
        return self.returncode


def _make_adapter() -> ClaudeCodeAdapter:
    integration = MagicMock()
    integration.provider = "claude_code"
    integration.model = "claude-sonnet-4-6"
    integration.display_name = "Claude Code Test"
    integration.extra_config = {}
    integration.auth_config = {}
    integration.is_active = True
    return ClaudeCodeAdapter(integration=integration)


# ---------------------------------------------------------------------------
# Pure-function tests for _classify_failure
# ---------------------------------------------------------------------------


class TestClassifyFailure:
    def test_credit_balance_quota(self) -> None:
        code, msg = _classify_failure("Credit balance is too low")
        assert code == "llm_quota_exceeded"
        assert "credit balance" in msg.lower()

    def test_credit_balance_case_insensitive(self) -> None:
        code, _ = _classify_failure("CREDIT BALANCE depleted")
        assert code == "llm_quota_exceeded"

    def test_rate_limit(self) -> None:
        assert _classify_failure("Rate Limit hit")[0] == "llm_rate_limited"
        assert _classify_failure("HTTP 429 too many requests")[0] == (
            "llm_rate_limited"
        )

    def test_auth_failed(self) -> None:
        assert _classify_failure("Authentication failed")[0] == "llm_auth_failed"
        assert _classify_failure("you are not logged in")[0] == "llm_auth_failed"
        assert _classify_failure("Invalid API key")[0] == "llm_auth_failed"

    def test_cli_missing(self) -> None:
        assert _classify_failure("zsh: command not found: claude")[0] == (
            "llm_cli_missing"
        )

    def test_unknown_falls_back_to_provider_error(self) -> None:
        code, _ = _classify_failure("some weird unexpected failure")
        assert code == "llm_provider_error"

    def test_quota_takes_priority_over_rate_limit(self) -> None:
        # Realistic mixed message; quota is more specific.
        code, _ = _classify_failure(
            "Credit balance is too low. Rate limit also reset."
        )
        assert code == "llm_quota_exceeded"


# ---------------------------------------------------------------------------
# Adapter integration: end-to-end through create_message
# ---------------------------------------------------------------------------


_QUOTA_NDJSON = _ndjson_bytes(
    {"type": "system", "subtype": "init", "session_id": "sess_q1"},
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "API Error: Credit balance is too low. "
                        "Please top up your account."
                    ),
                }
            ],
        },
        "session_id": "sess_q1",
    },
)


_AUTH_NDJSON = _ndjson_bytes(
    {"type": "system", "subtype": "init", "session_id": "sess_a1"},
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Authentication failed: invalid token."}
            ],
        },
        "session_id": "sess_a1",
    },
)


class TestClaudeCodeErrorRaising:
    async def test_quota_in_assistant_content_maps_to_quota_exceeded(
        self,
    ) -> None:
        """Credit balance error in assistant content + exit 1 → llm_quota_exceeded.

        Acceptance criterion: adapter parses NDJSON before raising and
        preserves the most recent assistant text as ``last_assistant``.
        """
        adapter = _make_adapter()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(
                _QUOTA_NDJSON, returncode=1, stderr=b""
            )

            with pytest.raises(ClaudeCodeError) as exc_info:
                await adapter.create_message(
                    messages=[LLMMessage(role="user", content="hello")],
                    tools=[],
                )

        exc = exc_info.value
        assert exc.error_code == "llm_quota_exceeded"
        assert exc.last_assistant is not None
        assert "Credit balance is too low" in exc.last_assistant
        # Human-friendly message — no raw CLI dump
        assert "credit balance" in str(exc).lower()
        # Inherits RuntimeError so existing catch-Exception sites still work
        assert isinstance(exc, RuntimeError)

    async def test_auth_failure_in_assistant_content(self) -> None:
        adapter = _make_adapter()

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(_AUTH_NDJSON, returncode=1)

            with pytest.raises(ClaudeCodeError) as exc_info:
                await adapter.create_message(
                    messages=[LLMMessage(role="user", content="hi")],
                    tools=[],
                )

        assert exc_info.value.error_code == "llm_auth_failed"

    async def test_command_not_found_on_stderr_only(self) -> None:
        """No stdout, stderr says 'command not found' → llm_cli_missing."""
        adapter = _make_adapter()
        stderr = b"sh: 1: claude: command not found\n"

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(b"", returncode=127, stderr=stderr)

            with pytest.raises(ClaudeCodeError) as exc_info:
                await adapter.create_message(
                    messages=[LLMMessage(role="user", content="hi")],
                    tools=[],
                )

        exc = exc_info.value
        assert exc.error_code == "llm_cli_missing"
        assert exc.last_assistant is None  # nothing in stdout
        assert exc.stderr_tail is not None
        assert "command not found" in exc.stderr_tail

    async def test_filenotfound_maps_to_cli_missing(self) -> None:
        """Subprocess never spawns (binary missing) → llm_cli_missing."""
        adapter = _make_adapter()

        with (
            patch(
                "asyncio.create_subprocess_exec",
                new_callable=AsyncMock,
                side_effect=FileNotFoundError("[Errno 2] no such file"),
            ),
            pytest.raises(ClaudeCodeError) as exc_info,
        ):
            await adapter.create_message(
                messages=[LLMMessage(role="user", content="hi")],
                tools=[],
            )

        exc = exc_info.value
        assert exc.error_code == "llm_cli_missing"
        assert "not found" in str(exc).lower()

    async def test_generic_returncode_nonzero_falls_back_to_provider_error(
        self,
    ) -> None:
        adapter = _make_adapter()
        stderr = b"some weird unexpected failure\n"

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(b"", returncode=1, stderr=stderr)

            with pytest.raises(ClaudeCodeError) as exc_info:
                await adapter.create_message(
                    messages=[LLMMessage(role="user", content="hi")],
                    tools=[],
                )

        assert exc_info.value.error_code == "llm_provider_error"


_SUCCESS_NDJSON = _ndjson_bytes(
    {"type": "system", "subtype": "init", "session_id": "sess_s1"},
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "All good."}],
        },
        "session_id": "sess_s1",
    },
    {
        "type": "result",
        "subtype": "success",
        "result": "All good.",
        "session_id": "sess_s1",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "total_cost_usd": 0.0,
    },
)


class TestStderrIgnoredOnSuccess:
    async def test_stderr_warnings_not_forwarded_when_returncode_zero(
        self,
    ) -> None:
        """Success run with sandbox-disabled noise on stderr → on_log("stderr") never called."""
        adapter = _make_adapter()
        stderr_noise = b"Warning: sandbox disabled\n"

        on_log_calls: list[tuple[str, str]] = []

        async def _on_log(stream: str, chunk: str) -> None:
            on_log_calls.append((stream, chunk))

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _MockProcess(
                _SUCCESS_NDJSON, returncode=0, stderr=stderr_noise
            )
            await adapter.create_message(
                messages=[LLMMessage(role="user", content="hi")],
                tools=[],
                on_log=_on_log,
            )

        stderr_streams = [c for s, c in on_log_calls if s == "stderr"]
        assert stderr_streams == [], (
            f"Expected no stderr forwarded on success, got: {stderr_streams}"
        )
