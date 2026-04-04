# LLM Provider Adapters

## What This Component Does

The LLM adapter layer normalizes calls to different LLM provider APIs (Anthropic, OpenAI, Azure OpenAI, Claude CLI) into a single interface used by the agent runtime engine. Each adapter translates between the runtime's `LLMMessage`/`LLMResponse` types and the provider's native SDK. The factory (`factory.py`) resolves the correct adapter from an `LLMIntegration` DB row and handles `api_key_ref` resolution. Cost tracking (`CostInfo`) is always extracted from the provider response — never estimated.

## Interfaces

### LLMProviderAdapter ABC (`base.py`)

```python
class LLMProviderAdapter(ABC):
    async def create_message(
        self,
        messages: list[LLMMessage],   # conversation history
        tools: list[dict],             # tool definitions in Anthropic tool-use format
        system: str | None = None,     # system prompt
        max_tokens: int | None = None, # per-call override
        **kwargs,                      # provider-specific extras
    ) -> LLMResponse: ...

    def extract_cost(self, response: LLMResponse) -> CostInfo: ...
    
    async def test_environment(self) -> EnvironmentTestResult: ...
```

### Key data types (`base.py`)

```python
@dataclass
class LLMMessage:
    role: str           # "user", "assistant", "system"
    content: str | list[dict]  # string or Anthropic-style content blocks

@dataclass
class LLMResponse:
    content: list[dict]     # content blocks: {"type": "text"|"tool_use", ...}
    stop_reason: str        # "end_turn", "tool_use", "max_tokens"
    usage: CostInfo
    raw: Any                # raw provider response (for debugging)
    metadata: dict          # provider extras (e.g. session_id from claude_code)

@dataclass
class CostInfo:
    input_tokens: int
    output_tokens: int
    cost_cents: int
    billing_type: str       # "api" or "subscription"
```

### Factory (`factory.py`)

```python
def get_adapter(integration: LLMIntegration) -> LLMProviderAdapter
```

Dispatches by `integration.provider`. Resolves `api_key_ref` via `resolve_secret_ref()` before constructing the adapter. Callers (the runtime engine) never handle secret resolution.

### Tool format contract

All adapters accept tools in **Anthropic tool-use format**:
```json
{
  "name": "get_alert",
  "description": "...",
  "input_schema": {"type": "object", "properties": {...}}
}
```

`OpenAIAdapter` translates this to OpenAI function format internally. Callers always pass Anthropic format.

## Key Design Decisions

**Why Anthropic format as the canonical tool format?**
Most of Calseta's built-in tools were designed alongside Claude. Using Anthropic format as canonical avoids a translation layer in the runtime engine. Only `OpenAIAdapter` translates to provider-native format, keeping the translation isolated to the adapter.

**Why raw SDKs instead of a framework?**
The runtime engine needs exact token counts from every API call for cost tracking. LLM frameworks often abstract away usage metadata or make it hard to extract. Using SDKs directly (`anthropic`, `openai`) gives full control over the response object. The adapter is ~150 lines per provider — not complex enough to need a framework.

**ClaudeCodeAdapter subprocess model**
The `claude` CLI is invoked as a subprocess (`asyncio.create_subprocess_exec`). This is intentionally dev/demo only — it uses the developer's Claude.ai subscription, avoiding API key setup. The CLI emits NDJSON: `system` event (session_id), `assistant` events (content blocks), `result` event (usage + cost). Session continuity is via `--resume {session_id}`. **Not for production** — subscription billing is tracked separately and not counted toward `budget_monthly_cents` by default.

**Cost computation from `cost_per_1k_*` rates**
Adapters read `integration.cost_per_1k_input_tokens_cents` and `cost_per_1k_output_tokens_cents` from the `LLMIntegration` row to compute `cost_cents`. This means cost rates are set at integration creation time and can be updated without code changes. For `claude_code`, cost comes from the CLI's `total_cost_usd` field (converted to cents).

**OpenAI adapter handles both OpenAI and Azure OpenAI**
Azure OpenAI exposes an OpenAI-compatible API — only the `base_url` and `api_version` differ. Routing both through `OpenAIAdapter` avoids duplicating ~150 lines. The factory sets `base_url` from `integration.base_url` and reads `api_version` from `integration.config["api_version"]`.

## Extension Pattern

To add a new provider (e.g., Google Gemini):

1. Create `app/integrations/llm/gemini_adapter.py`:
```python
from app.integrations.llm.base import LLMProviderAdapter, LLMMessage, LLMResponse, CostInfo

class GeminiAdapter(LLMProviderAdapter):
    def __init__(self, integration: LLMIntegration, api_key: str) -> None:
        self.integration = integration
        self._client = ...  # google.generativeai or genai SDK
    
    async def create_message(self, messages, tools, system=None, max_tokens=None, **kwargs) -> LLMResponse:
        # Translate LLMMessage list to Gemini's Content format
        # Translate Anthropic tool format to Gemini FunctionDeclaration format
        # Call Gemini API
        # Map response back to LLMResponse + CostInfo
        ...
    
    def extract_cost(self, response: LLMResponse) -> CostInfo:
        # Read from response.raw.usage_metadata
        ...
```

2. Add `"google"` to `LLMProvider` enum in `app/schemas/llm_integrations.py`.

3. Add a branch in `app/integrations/llm/factory.py`:
```python
if provider == LLMProvider.GOOGLE:
    from app.integrations.llm.gemini_adapter import GeminiAdapter
    api_key = resolve_secret_ref(integration.api_key_ref)
    return GeminiAdapter(integration=integration, api_key=api_key)
```

4. Update `app/integrations/llm/__init__.py` to export the new adapter.

No DB migration needed — `llm_integrations.provider` is `TEXT`.

## Common Failure Modes

**`AnthropicAdapter` raises `AuthenticationError`**
`api_key_ref` resolved to an empty string or invalid key. Check: is `ANTHROPIC_API_KEY` set in the environment if using `env:ANTHROPIC_API_KEY`? Is the secret stored correctly if using `secret:anthropic`?

**`OpenAIAdapter` import fails with `ModuleNotFoundError: openai`**
`openai` SDK is not in required dependencies (lazy import). Install with `pip install openai`. For Azure OpenAI, also set `OPENAI_API_VERSION` or pass `api_version` in `llm_integrations.config`.

**`ClaudeCodeAdapter` subprocess times out**
`claude` CLI not installed, not logged in, or the model being invoked is rate-limited on the subscription plan. Run `claude auth status` to diagnose. The `test_environment()` method on the adapter will check and return a structured error.

**Cost computed as 0 for Anthropic calls**
`cost_per_1k_input_tokens_cents` and `cost_per_1k_output_tokens_cents` are 0 on the integration row. These are not auto-populated — operators must set them at registration time. Update via `PATCH /v1/llm-integrations/{id}`.

**Tool call returns unexpected format**
Tools must be passed in Anthropic format. If the LLM returns `tool_use` blocks but `content` is empty in the response, check that the tool `input_schema` is valid JSON Schema (the provider validates it). A malformed schema will cause the provider to return an error or skip tool use entirely.

## Test Coverage

```
tests/integration/agent_control_plane/test_phase1_llm_providers.py
  - Register integration, assert adapter construction
  - AnthropicAdapter: mocked SDK response → LLMResponse normalization + cost extraction
  - OpenAIAdapter: tool format translation (Anthropic → OpenAI), response normalization
  - ClaudeCodeAdapter: mocked subprocess → NDJSON parse → session_id round-trip
  - get_adapter() raises ValueError for unknown provider
  - test_environment() for each adapter
```

Mock strategy: `unittest.mock.patch` on `anthropic.AsyncAnthropic`, `openai.AsyncOpenAI`, and `asyncio.create_subprocess_exec`. Never call real LLM APIs in CI.
