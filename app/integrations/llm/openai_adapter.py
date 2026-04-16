"""
OpenAI adapter — wraps the openai Python SDK.

Supports standard OpenAI and Azure OpenAI (via base_url + api_key override).
The openai package is NOT a required dependency — import is lazy with a
helpful error message if the package is missing.

Cost is computed from cost_per_1k_* rates on the LLMIntegration row.
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

_DEFAULT_MAX_TOKENS = 4096


class OpenAIAdapter(LLMProviderAdapter):
    """
    LLM adapter for OpenAI's chat completions API.

    Also handles Azure OpenAI when ``integration.base_url`` is set — the
    Azure OpenAI endpoint is passed as ``base_url`` to the AsyncOpenAI client,
    which routes requests to the Azure deployment automatically.

    Requires the ``openai`` package (not a required dependency; lazy import).
    """

    def __init__(self, integration: LLMIntegration, api_key: str) -> None:
        self._integration = integration
        self._api_key = api_key
        self._model = integration.model
        self._base_url = integration.base_url

    def _client(self) -> Any:
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError(
                "The 'openai' package is required for OpenAIAdapter. "
                "Install it with: pip install openai"
            ) from exc

        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        return openai.AsyncOpenAI(**kwargs)

    def _to_openai_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert Anthropic tool format to OpenAI function-calling format."""
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        return openai_tools

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
        try:
            import openai
        except ImportError as exc:
            raise RuntimeError(
                "The 'openai' package is required for OpenAIAdapter. "
                "Install it with: pip install openai"
            ) from exc

        client = self._client()
        effective_max_tokens = max_tokens or _DEFAULT_MAX_TOKENS

        api_messages: list[dict[str, Any]] = []
        if system:
            api_messages.append({"role": "system", "content": system})

        for m in messages:
            if m.role == "system":
                # System messages folded into the leading system message above
                continue
            content = m.content if isinstance(m.content, str) else _flatten_content(m.content)
            api_messages.append({"role": m.role, "content": content})

        create_kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": effective_max_tokens,
            "messages": api_messages,
        }
        if tools:
            create_kwargs["tools"] = self._to_openai_tools(tools)
            create_kwargs["tool_choice"] = "auto"

        try:
            response = await client.chat.completions.create(**create_kwargs)
        except openai.APIError as exc:
            raise RuntimeError(f"OpenAI API error: {exc}") from exc

        choice = response.choices[0]
        content_blocks: list[dict[str, Any]] = []

        if choice.message.content:
            content_blocks.append({"type": "text", "text": choice.message.content})

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                import json

                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments or "{}"),
                })

        # Stream events via on_log callback if provided
        if on_log is not None:
            for block in content_blocks:
                block_type = block.get("type", "")
                if block_type == "text":
                    await on_log("assistant", block.get("text", ""))
                elif block_type == "tool_use":
                    await on_log("tool_call", f"{block.get('name', '')}({block.get('input', {})})")

        stop_reason = _map_finish_reason(choice.finish_reason)

        cost = self.extract_cost(
            LLMResponse(
                content=content_blocks,
                stop_reason=stop_reason,
                usage=CostInfo(
                    input_tokens=response.usage.prompt_tokens if response.usage else 0,
                    output_tokens=response.usage.completion_tokens if response.usage else 0,
                    cost_cents=0,
                    billing_type="api",
                ),
                raw=response,
            )
        )

        return LLMResponse(
            content=content_blocks,
            stop_reason=stop_reason,
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
            await client.models.list()
            return EnvironmentTestResult(ok=True, message="OpenAI API reachable.")
        except ImportError:
            return EnvironmentTestResult(ok=False, message="openai package not installed.")
        except Exception as exc:  # noqa: BLE001
            return EnvironmentTestResult(ok=False, message=str(exc))


def _flatten_content(content_blocks: list[dict[str, Any]]) -> str:
    """Flatten Anthropic-style content blocks to a plain string for OpenAI."""
    parts = []
    for block in content_blocks:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "tool_result":
            parts.append(str(block.get("content", "")))
    return "\n".join(parts)


def _map_finish_reason(reason: str | None) -> str:
    mapping = {
        "stop": "end_turn",
        "length": "max_tokens",
        "tool_calls": "tool_use",
        "content_filter": "end_turn",
    }
    return mapping.get(reason or "", "end_turn")
