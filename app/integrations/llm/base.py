"""
LLM provider adapter base classes and shared data types.

All provider adapters implement LLMProviderAdapter. The factory in
factory.py routes LLMIntegration rows to the correct concrete adapter.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

# Callback type for streaming adapter output.
# Called with (stream, chunk) where stream is one of:
#   "stdout", "stderr", "assistant", "tool_call", "tool_result", "thinking", "finding"
# and chunk is the content string.
OnLogCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class CostInfo:
    """Token counts and cost computed from a single LLM API call."""

    input_tokens: int
    output_tokens: int
    cost_cents: int
    billing_type: str = "api"  # "api" or "subscription"


@dataclass
class LLMMessage:
    """A single message in a conversation turn."""

    role: str  # "user", "assistant", "system"
    content: str | list[dict[str, Any]]  # string or Anthropic-style content blocks


@dataclass
class LLMResponse:
    """Normalized response from any LLM provider."""

    content: list[dict[str, Any]]  # content blocks: {"type": "text", "text": "..."} etc.
    stop_reason: str  # "end_turn", "tool_use", "max_tokens"
    usage: CostInfo
    raw: Any = None  # raw provider response for debugging
    metadata: dict[str, Any] = field(default_factory=dict)  # provider-specific extras


@dataclass
class EnvironmentTestResult:
    """Result of a connectivity/auth pre-flight check."""

    ok: bool
    message: str


class LLMProviderAdapter(ABC):
    """
    Abstract base for all LLM provider adapters.

    Each concrete adapter wraps one provider SDK (Anthropic, OpenAI, etc.)
    and translates between the provider's native API and the normalized
    LLMMessage/LLMResponse types.

    Contract:
    - create_message() must never raise on provider errors; catch and re-raise
      as a structured exception with enough context for the caller to log it.
    - extract_cost() is called with the LLMResponse returned by create_message().
    - test_environment() should be safe to call without incurring API charges.
    """

    # Optional class attributes for external adapter identification.
    # Built-in adapters leave these unset; external adapters MUST set them.
    provider_name: str | None = None
    display_name: str | None = None

    @abstractmethod
    async def create_message(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]],
        system: str | None = None,
        max_tokens: int | None = None,
        on_log: OnLogCallback | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """
        Send a message to the provider and return the normalized response.

        Args:
            messages: Conversation history.
            tools: Tool definitions in Anthropic tool-use format.
            system: System prompt string.
            max_tokens: Override the default max_tokens for this call.
            on_log: Optional async callback for streaming output. Called with
                (stream, chunk) where stream is one of "stdout", "stderr",
                "assistant", "tool_call", "tool_result", "thinking", "finding"
                and chunk is the content string. When None, no streaming occurs.
            **kwargs: Provider-specific extras (e.g. session_id for claude_code).
        """

    @abstractmethod
    def extract_cost(self, response: LLMResponse) -> CostInfo:
        """
        Compute token counts and cost from a completed LLMResponse.

        Reads cost_per_1k rates from the integration config. Returns a CostInfo
        with cost_cents=0 for subscription-billed providers.
        """

    async def test_environment(self) -> EnvironmentTestResult:
        """
        Verify that the adapter can reach the provider.

        Default implementation returns OK without making a network call.
        Override for providers that require a real connectivity check (e.g. claude_code CLI).
        """
        return EnvironmentTestResult(ok=True, message="OK")
