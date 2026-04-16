"""
Anthropic adapter — wraps the anthropic Python SDK.

Supports standard message creation and extended thinking (enable_thinking flag).
Cost is computed from cost_per_1k_* rates stored on the LLMIntegration row.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

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

_DEFAULT_MAX_TOKENS = 8096
_DEFAULT_THINKING_BUDGET = 5000


class AnthropicAdapter(LLMProviderAdapter):
    """
    LLM adapter for Anthropic's messages API.

    Requires the ``anthropic`` package (>=0.40.0). The api_key_ref on the
    LLMIntegration is resolved by the factory before this adapter is constructed.
    """

    def __init__(self, integration: LLMIntegration, api_key: str) -> None:
        try:
            import anthropic as _anthropic  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "The 'anthropic' package is required for AnthropicAdapter. "
                "Install it with: pip install anthropic"
            ) from exc

        self._integration = integration
        self._api_key = api_key
        self._model = integration.model

    def _client(self) -> Any:
        import anthropic

        return anthropic.AsyncAnthropic(api_key=self._api_key)

    def _enable_thinking(self) -> bool:
        if self._integration.config:
            return bool(self._integration.config.get("enable_thinking", False))
        return False

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
        import anthropic

        client = self._client()
        effective_max_tokens = (
            max_tokens
            or (self._integration.max_tokens if hasattr(self._integration, "max_tokens") else None)
            or _DEFAULT_MAX_TOKENS
        )

        api_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role != "system"
        ]

        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": effective_max_tokens,
            "messages": api_messages,
        }
        if system:
            create_kwargs["system"] = system
        if tools:
            create_kwargs["tools"] = tools

        if self._enable_thinking():
            thinking_budget = _DEFAULT_THINKING_BUDGET
            if self._integration.config:
                thinking_budget = int(
                    self._integration.config.get("thinking_budget_tokens", _DEFAULT_THINKING_BUDGET)
                )
            create_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": thinking_budget,
            }

        try:
            response = await client.messages.create(**create_kwargs)
        except anthropic.APIError as exc:
            raise RuntimeError(f"Anthropic API error: {exc}") from exc

        content_blocks: list[dict[str, Any]] = []
        for block in response.content:
            if hasattr(block, "model_dump"):
                content_blocks.append(block.model_dump())
            else:
                content_blocks.append({"type": getattr(block, "type", "unknown")})

        # Stream events via on_log callback if provided
        if on_log is not None:
            for block in content_blocks:
                block_type = block.get("type", "")
                if block_type == "text":
                    await on_log("assistant", block.get("text", ""))
                elif block_type == "tool_use":
                    await on_log("tool_call", f"{block.get('name', '')}({block.get('input', {})})")
                elif block_type == "thinking":
                    await on_log("thinking", block.get("thinking", ""))

        cost = self.extract_cost(
            LLMResponse(
                content=content_blocks,
                stop_reason=response.stop_reason or "end_turn",
                usage=CostInfo(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cost_cents=0,
                    billing_type="api",
                ),
                raw=response,
            )
        )

        return LLMResponse(
            content=content_blocks,
            stop_reason=response.stop_reason or "end_turn",
            usage=cost,
            raw=response,
        )

    def extract_cost(self, response: LLMResponse) -> CostInfo:
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost_per_1k_in = self._integration.cost_per_1k_input_tokens_cents
        cost_per_1k_out = self._integration.cost_per_1k_output_tokens_cents
        cost_cents = (
            (input_tokens * cost_per_1k_in // 1000)
            + (output_tokens * cost_per_1k_out // 1000)
        )
        return CostInfo(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_cents=cost_cents,
            billing_type="api",
        )

    async def test_environment(self) -> EnvironmentTestResult:
        try:
            client = self._client()
            # Use a minimal, cheap call to verify credentials
            await client.messages.create(
                model=self._model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return EnvironmentTestResult(ok=True, message="Anthropic API reachable.")
        except ImportError:
            return EnvironmentTestResult(ok=False, message="anthropic package not installed.")
        except Exception as exc:  # noqa: BLE001
            return EnvironmentTestResult(ok=False, message=str(exc))
