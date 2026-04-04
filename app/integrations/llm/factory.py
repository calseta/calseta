"""
LLM adapter factory — routes LLMIntegration rows to the correct adapter.

Usage:
    adapter = get_adapter(integration)
    response = await adapter.create_message(messages, tools, system=system_prompt)

The factory resolves api_key_ref via resolve_secret_ref() before constructing
the adapter. Callers never deal with secret resolution directly.
"""

from __future__ import annotations

from app.db.models.llm_integration import LLMIntegration
from app.integrations.llm.base import LLMProviderAdapter


def resolve_secret_ref(ref: str | None) -> str:
    """
    Resolve a secret reference string to a plaintext value.

    Stub implementation — returns the ref unchanged (treated as a literal key value).
    The real secrets system (separate implementation) will replace this with
    lookups against the local_encrypted or env_var secret provider.

    Args:
        ref: Secret reference string (e.g. "env:ANTHROPIC_API_KEY" or a vault path).
             None returns an empty string.
    """
    if ref is None:
        return ""
    # Convention: "env:<VAR_NAME>" reads from environment
    if ref.startswith("env:"):
        import os
        var_name = ref[4:]
        return os.environ.get(var_name, "")
    # Literal value (for dev/testing) — return as-is
    return ref


def get_adapter(integration: LLMIntegration) -> LLMProviderAdapter:
    """
    Construct and return the correct LLMProviderAdapter for the given integration.

    Args:
        integration: An LLMIntegration ORM instance with provider, model,
                     api_key_ref, and base_url populated.

    Returns:
        A configured LLMProviderAdapter ready to call create_message().

    Raises:
        ValueError: If integration.provider is not a recognized value.
    """
    from app.schemas.llm_integrations import LLMProvider

    provider = integration.provider

    if provider == LLMProvider.ANTHROPIC:
        from app.integrations.llm.anthropic_adapter import AnthropicAdapter

        api_key = resolve_secret_ref(integration.api_key_ref)
        return AnthropicAdapter(integration=integration, api_key=api_key)

    if provider in (LLMProvider.OPENAI, LLMProvider.AZURE_OPENAI):
        from app.integrations.llm.openai_adapter import OpenAIAdapter

        api_key = resolve_secret_ref(integration.api_key_ref)
        return OpenAIAdapter(integration=integration, api_key=api_key)

    if provider == LLMProvider.CLAUDE_CODE:
        from app.integrations.llm.claude_code_adapter import ClaudeCodeAdapter

        return ClaudeCodeAdapter(integration=integration)

    if provider == LLMProvider.OLLAMA:
        # Ollama uses the OpenAI-compatible API; base_url points to the local server.
        from app.integrations.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(integration=integration, api_key="ollama")

    if provider == LLMProvider.AWS_BEDROCK:
        raise ValueError(
            f"Provider '{provider}' is not yet implemented. "
            "AWS Bedrock support is planned for a future release."
        )

    raise ValueError(
        f"Unknown LLM provider '{provider}'. "
        f"Valid values: anthropic, openai, azure_openai, ollama, claude_code, aws_bedrock"
    )
