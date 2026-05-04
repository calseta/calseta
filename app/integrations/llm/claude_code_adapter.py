"""
Claude Code adapter — invokes the ``claude`` CLI as a subprocess.

This adapter is for use when the Calseta host has Claude Code installed and
authenticated. It sends the prompt via stdin and parses NDJSON output.

Billing type is "subscription" — no per-token cost is computed.

CLI invocation:
    claude --print - --output-format stream-json --verbose --model {model} [--resume {session_id}]

NDJSON event types parsed:
    system       → contains session_id
    assistant    → contains content blocks (text, tool_use)
    result       → contains stop_reason, usage stats, total_cost_usd
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import structlog

from app.integrations.llm.base import (
    CostInfo,
    EnvironmentTestResult,
    LLMMessage,
    LLMProviderAdapter,
    LLMResponse,
    OnLogCallback,
)

if TYPE_CHECKING:
    from app.db.models.llm_integration import LLMIntegration

logger = structlog.get_logger(__name__)

_CLAUDE_CLI = "claude"
_DEFAULT_MAX_TOKENS = 8096


class ClaudeCodeError(RuntimeError):
    """Structured error raised by ClaudeCodeAdapter on subprocess failures.

    Carries an ``error_code`` (matching ``RunErrorCode``) and the most useful
    diagnostic context — the most recent assistant text block from the NDJSON
    stream (if any) and a tail of stderr. Callers (e.g. the runtime engine)
    use ``error_code`` to populate ``HeartbeatRun.error_code`` and the
    short message (str(exc)) to populate ``HeartbeatRun.error`` — without
    dumping the raw CLI output into the user-visible error field.
    """

    def __init__(
        self,
        message: str,
        *,
        error_code: str,
        last_assistant: str | None = None,
        stderr_tail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.last_assistant = last_assistant
        self.stderr_tail = stderr_tail


# --- Error pattern dispatch ---------------------------------------------------
#
# Order matters: more specific patterns first. All checks operate on the
# concatenation of the most recent assistant text block + stderr tail so that
# we catch errors regardless of where the CLI surfaces them.

# Quota: case-sensitive substring "Credit balance is too low" OR case-
# insensitive "credit balance".
_QUOTA_PATTERNS_CI: tuple[str, ...] = ("credit balance",)
_RATE_LIMIT_PATTERNS_CI: tuple[str, ...] = ("rate limit", "too many requests")
_AUTH_PATTERNS_CI: tuple[str, ...] = (
    "authentication",
    "not logged in",
    "invalid api key",
)
_CLI_MISSING_PATTERNS_CI: tuple[str, ...] = ("command not found",)


def _classify_failure(text: str) -> tuple[str, str]:
    """Classify a failure-text blob into (error_code, short_human_message).

    The blob is the concatenation of the last assistant text block (if any)
    and a stderr tail. Matching is case-insensitive for all patterns.
    """
    haystack = text.lower()

    if any(p in haystack for p in _QUOTA_PATTERNS_CI):
        return ("llm_quota_exceeded", "LLM quota exceeded — credit balance is too low.")
    if any(p in haystack for p in _RATE_LIMIT_PATTERNS_CI):
        return ("llm_rate_limited", "LLM provider rate-limited the request.")
    if any(p in haystack for p in _AUTH_PATTERNS_CI):
        return ("llm_auth_failed", "LLM authentication failed.")
    if any(p in haystack for p in _CLI_MISSING_PATTERNS_CI):
        return ("llm_cli_missing", "Claude Code CLI not found on PATH.")
    return ("llm_provider_error", "Claude Code CLI returned a non-zero exit code.")


class ClaudeCodeAdapter(LLMProviderAdapter):
    """
    LLM adapter that drives the Claude Code CLI as a subprocess.

    The full prompt is serialized as a single user message and sent via stdin.
    Tool use is handled the same way: tool definitions and results are embedded
    in the message content and the CLI processes them using its built-in tool loop.

    session_id kwarg enables conversation resumption across calls:
        response = await adapter.create_message(..., session_id="abc123")
        next_session_id = response.metadata.get("session_id")
    """

    def __init__(self, integration: LLMIntegration) -> None:
        self._integration = integration
        self._model = integration.model

    def _build_cli_args(self, session_id: str | None = None) -> list[str]:
        args = [
            _CLAUDE_CLI,
            "--print", "-",
            "--output-format", "stream-json",
            "--verbose",
            "--model", self._model,
        ]
        if session_id:
            args.extend(["--resume", session_id])
        return args

    def _serialize_prompt(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]],
        system: str | None,
    ) -> str:
        """
        Serialize the conversation into a single stdin payload.

        The Claude Code CLI accepts the full conversation as its stdin input.
        We pass a JSON envelope so the CLI can reconstruct the conversation.
        """
        payload: dict[str, Any] = {
            "messages": [
                {"role": m.role, "content": m.content}
                for m in messages
            ],
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = tools
        return json.dumps(payload)

    async def create_message(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int | None = None,
        on_log: OnLogCallback | None = None,
        env: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        session_id: str | None = kwargs.get("session_id")
        cli_args = self._build_cli_args(session_id=session_id)
        stdin_payload = self._serialize_prompt(messages, tools, system)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cli_args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        except FileNotFoundError as exc:
            raise ClaudeCodeError(
                "Claude Code CLI not found. Ensure 'claude' is installed and on PATH.",
                error_code="llm_cli_missing",
                stderr_tail=str(exc),
            ) from exc

        # Write stdin and close to signal end of input
        assert proc.stdin is not None
        proc.stdin.write(stdin_payload.encode("utf-8"))
        await proc.stdin.drain()
        proc.stdin.close()
        await proc.stdin.wait_closed()

        # Stream stdout line-by-line for real-time output
        stdout_lines: list[str] = []
        assert proc.stdout is not None
        while True:
            line_bytes = await proc.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
            stdout_lines.append(line)
            if on_log is not None:
                stream, chunk = self._classify_line(line)
                await on_log(stream, chunk)

        # Collect any remaining stderr
        assert proc.stderr is not None
        stderr_bytes = await proc.stderr.read()
        await proc.wait()

        # Only forward stderr when the process actually failed — when
        # returncode == 0, sandbox-disabled noise and other harmless
        # warnings should not pollute the run log.
        if (
            on_log is not None
            and stderr_bytes
            and proc.returncode != 0
        ):
            await on_log("stderr", stderr_bytes.decode("utf-8", errors="replace"))

        if proc.returncode != 0:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")
            stderr_tail = stderr_text[-500:] if stderr_text else None

            # Parse already-collected NDJSON to recover the most recent
            # assistant text block — error details from the upstream API
            # (e.g. "Credit balance is too low") arrive there, not on stderr.
            raw_output = "\n".join(stdout_lines)
            last_assistant = self._extract_last_assistant_text(raw_output)

            blob = " ".join(filter(None, [last_assistant or "", stderr_text or ""]))
            error_code, human_msg = _classify_failure(blob)

            message = f"claude CLI exited with code {proc.returncode}: {human_msg}"
            logger.warning(
                "claude_code_subprocess_failed",
                returncode=proc.returncode,
                error_code=error_code,
                last_assistant=(last_assistant or "")[:200],
                stderr_tail=(stderr_tail or "")[:200],
            )
            raise ClaudeCodeError(
                message,
                error_code=error_code,
                last_assistant=last_assistant,
                stderr_tail=stderr_tail,
            )

        raw_output = "\n".join(stdout_lines)
        return self._parse_output(raw_output)

    @staticmethod
    def _extract_last_assistant_text(raw_output: str) -> str | None:
        """Return the most recent assistant text content from NDJSON, or None.

        Concatenates all text blocks within the most recent ``assistant``
        event. Tool-use blocks are skipped. Returns None when no assistant
        event is present (e.g. failure happened before the model produced
        any output).
        """
        last_text: str | None = None
        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "assistant":
                continue
            message = event.get("message", {})
            text_parts: list[str] = []
            for block in message.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    text = block.get("text", "")
                    if text:
                        text_parts.append(text)
            if text_parts:
                last_text = " ".join(text_parts)
        return last_text

    @staticmethod
    def _classify_line(line: str) -> tuple[str, str]:
        """Classify an NDJSON line into (stream, chunk) for on_log."""
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return ("stdout", line)

        event_type = event.get("type", "")
        if event_type == "assistant":
            message = event.get("message", {})
            text_parts = []
            for block in message.get("content", []):
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        text_parts.append(f"[tool_use: {block.get('name', '')}]")
            return ("assistant", " ".join(text_parts) if text_parts else line)
        if event_type == "result":
            return ("stdout", f"[result: stop_reason={event.get('stop_reason', 'unknown')}]")
        if event_type == "system":
            return ("stdout", f"[system: session_id={event.get('session_id', '')}]")
        return ("stdout", line)

    def _parse_output(self, raw_output: str) -> LLMResponse:
        """Parse NDJSON stream from claude CLI into an LLMResponse."""
        new_session_id: str | None = None
        content_blocks: list[dict[str, Any]] = []
        stop_reason = "end_turn"
        input_tokens = 0
        output_tokens = 0
        cost_usd: float = 0.0

        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("claude_code_non_json_line", line=line[:200])
                continue

            event_type = event.get("type")

            if event_type == "system":
                new_session_id = event.get("session_id")

            elif event_type == "assistant":
                message = event.get("message", {})
                for block in message.get("content", []):
                    if isinstance(block, dict):
                        content_blocks.append(block)

            elif event_type == "result":
                stop_reason = event.get("stop_reason", "end_turn")
                usage = event.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                output_tokens = usage.get("output_tokens", 0)
                cost_usd = event.get("total_cost_usd", 0.0)

        metadata: dict[str, Any] = {}
        if new_session_id:
            metadata["session_id"] = new_session_id

        # Convert USD to cents for the raw value; billing_type is subscription so
        # actual billing tracking uses cost_cents=0 (no per-call charge).
        cost_cents_approx = int(cost_usd * 100)

        usage = CostInfo(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_cents=cost_cents_approx,
            billing_type="subscription",
        )

        return LLMResponse(
            content=content_blocks,
            stop_reason=stop_reason,
            usage=usage,
            raw=raw_output,
            metadata=metadata,
        )

    def extract_cost(self, response: LLMResponse) -> CostInfo:
        # Subscription billing — cost tracked via claude CLI's own usage reporting,
        # not via per-token rates. Return 0 cost_cents.
        return CostInfo(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_cents=0,
            billing_type="subscription",
        )

    async def test_environment(self) -> EnvironmentTestResult:
        """Run ``claude auth status`` to verify the CLI is installed and authenticated."""
        try:
            proc = await asyncio.create_subprocess_exec(
                _CLAUDE_CLI, "auth", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await proc.communicate()
        except FileNotFoundError:
            return EnvironmentTestResult(
                ok=False,
                message="claude CLI not found on PATH. Install Claude Code first.",
            )
        except Exception as exc:  # noqa: BLE001
            return EnvironmentTestResult(ok=False, message=str(exc))

        if proc.returncode != 0:
            return EnvironmentTestResult(
                ok=False,
                message="claude CLI is not authenticated. Run 'claude login' first.",
            )

        try:
            status_data = json.loads(stdout_bytes.decode("utf-8", errors="replace"))
            email = status_data.get("email") or ""
            sub = status_data.get("subscriptionType") or ""
            if email:
                msg = f"Authenticated as {email}" + (f" ({sub})" if sub else "")
            else:
                msg = "Claude Code CLI authenticated" + (f" ({sub})" if sub else "") + "."
        except json.JSONDecodeError:
            msg = "Claude Code CLI authenticated."

        return EnvironmentTestResult(ok=True, message=msg)
