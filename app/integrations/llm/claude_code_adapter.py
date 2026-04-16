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
)

if TYPE_CHECKING:
    from app.db.models.llm_integration import LLMIntegration

logger = structlog.get_logger(__name__)

_CLAUDE_CLI = "claude"
_DEFAULT_MAX_TOKENS = 8096


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
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"Claude Code CLI not found. Ensure 'claude' is installed and on PATH. ({exc})"
            ) from exc

        stdout_bytes, stderr_bytes = await proc.communicate(
            input=stdin_payload.encode("utf-8")
        )

        if proc.returncode != 0:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"claude CLI exited with code {proc.returncode}: {stderr_text[:500]}"
            )

        return self._parse_output(stdout_bytes.decode("utf-8", errors="replace"))

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
