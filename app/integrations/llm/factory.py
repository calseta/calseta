"""
LLM adapter factory — routes LLMIntegration rows to the correct adapter.

Usage:
    adapter = get_adapter(integration)
    response = await adapter.create_message(messages, tools, system=system_prompt)

The factory resolves ``api_key_secret_ref`` via :func:`resolve_secret_ref` before
constructing the adapter. Callers never deal with secret resolution directly.

S3 (2026-05-05) — fail-closed resolver:
    Only five prefixes are accepted:

        env:NAME            — read ``os.environ[NAME]`` after denylist check
        enc:<ciphertext>    — decrypt with ``Fernet(settings.ENCRYPTION_KEY)``
        vault:PATH          — Hashicorp Vault (backend must be configured)
        aws-sm:NAME         — AWS Secrets Manager (backend must be configured)
        azure-kv:NAME       — Azure Key Vault (backend must be configured)

    Anything else (including a literal API key value) raises
    :class:`InvalidSecretRef`. A literal-looking value will be rewritten to
    ``enc:<ciphertext>`` by the startup auto-migration in
    :mod:`app.auth.startup_migration`; rows with a literal that survive
    boot indicate a misconfigured ``ENCRYPTION_KEY`` and the resolver will
    refuse them.
"""

from __future__ import annotations

import os

import structlog

from app.db.models.llm_integration import LLMIntegration
from app.integrations.llm.base import LLMProviderAdapter
from app.secrets.denylist import is_denied

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvalidSecretRef(ValueError):
    """Raised when ``resolve_secret_ref`` is given a value that is not a
    well-formed reference, hits the global denylist, or routes to a
    backend that is not configured.

    The ``reason`` attribute is one of:
        ``"unknown_prefix"``     — value did not match any known prefix
        ``"empty"``              — value was empty / whitespace
        ``"denied"``             — env var name is on the global denylist
        ``"backend_unavailable"`` — vault/aws-sm/azure-kv prefix used but
                                     no backend is configured
        ``"decrypt_failed"``     — ``enc:`` payload could not be decrypted
    """

    def __init__(self, reason: str, message: str | None = None) -> None:
        self.reason = reason
        super().__init__(message or reason)


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------


_KNOWN_PREFIXES = ("env:", "enc:", "vault:", "aws-sm:", "azure-kv:")


def has_known_prefix(ref: str | None) -> bool:
    """Return True if ``ref`` starts with one of the five accepted prefixes.

    Used by the startup auto-migration to detect literal values that need
    to be re-encrypted.
    """
    if not ref:
        return False
    return any(ref.startswith(p) for p in _KNOWN_PREFIXES)


def resolve_secret_ref(ref: str | None) -> str:
    """Resolve a secret reference to a plaintext value.

    Args:
        ref: The reference string (must use a known prefix).

    Returns:
        The plaintext secret value. Empty string is returned only when the
        ref is ``None`` (no api key configured for this integration — e.g.
        ``claude_code`` subscription). For ``env:NAME`` where the env var
        is not set, an empty string is returned (caller decides whether
        that is fatal). All other failures raise :class:`InvalidSecretRef`.

    Raises:
        InvalidSecretRef: With a structured ``reason`` field. See class doc.
    """
    if ref is None:
        # No key configured (e.g. claude_code subscription). Adapter is
        # responsible for deciding whether that is acceptable.
        return ""

    if not ref or not ref.strip():
        raise InvalidSecretRef("empty", "Secret ref is empty")

    if ref.startswith("env:"):
        var_name = ref[4:]
        if not var_name:
            raise InvalidSecretRef("empty", "env: prefix with no variable name")
        if is_denied(var_name):
            raise InvalidSecretRef(
                "denied",
                f"Environment variable '{var_name}' is on the global denylist",
            )
        return os.environ.get(var_name, "")

    if ref.startswith("enc:"):
        # Lazy import to avoid forcing cryptography at module-load time.
        from app.auth.encryption import decrypt_value

        ciphertext = ref[4:]
        if not ciphertext:
            raise InvalidSecretRef("empty", "enc: prefix with no ciphertext")
        try:
            return decrypt_value(ciphertext)
        except Exception as exc:  # noqa: BLE001 — we re-raise as our own type
            raise InvalidSecretRef(
                "decrypt_failed",
                f"Failed to decrypt enc: payload — {type(exc).__name__}",
            ) from exc

    if ref.startswith("vault:"):
        return _resolve_via_external_backend("vault", ref[len("vault:"):])

    if ref.startswith("aws-sm:"):
        return _resolve_via_external_backend("aws-sm", ref[len("aws-sm:"):])

    if ref.startswith("azure-kv:"):
        return _resolve_via_external_backend("azure-kv", ref[len("azure-kv:"):])

    raise InvalidSecretRef(
        "unknown_prefix",
        (
            "Secret ref does not match any known prefix "
            "(env:, enc:, vault:, aws-sm:, azure-kv:). "
            "Literal values are not accepted; encrypt with Fernet "
            "and use the enc: prefix instead."
        ),
    )


def _resolve_via_external_backend(backend: str, name: str) -> str:
    """Dispatch a vault/aws-sm/azure-kv lookup to its backend.

    These backends are not bundled with the core platform — they require
    cloud SDKs that self-hosters typically don't install. When the backend
    isn't configured, the resolver fails closed rather than falling back
    to ``os.environ`` (which would re-introduce the leak that the denylist
    is meant to prevent).
    """
    if not name:
        raise InvalidSecretRef("empty", f"{backend}: prefix with no name")

    from app.config import settings

    if backend == "azure-kv":
        if not settings.AZURE_KEY_VAULT_URL:
            raise InvalidSecretRef(
                "backend_unavailable",
                "azure-kv: prefix used but AZURE_KEY_VAULT_URL is not set",
            )
        # Implementation: lazy-import azure-identity + azure-keyvault-secrets
        # and look up by name. Kept as a structured raise until the cloud
        # secrets backend lands so we never silently fall through.
        raise InvalidSecretRef(
            "backend_unavailable",
            "azure-kv backend is not yet wired into the resolver",
        )

    if backend == "aws-sm":
        if not settings.AWS_SECRETS_MANAGER_SECRET_NAME:
            raise InvalidSecretRef(
                "backend_unavailable",
                "aws-sm: prefix used but AWS_SECRETS_MANAGER_SECRET_NAME is not set",
            )
        raise InvalidSecretRef(
            "backend_unavailable",
            "aws-sm backend is not yet wired into the resolver",
        )

    if backend == "vault":
        # No bundled config knob today; fail closed.
        raise InvalidSecretRef(
            "backend_unavailable",
            "vault backend is not configured",
        )

    raise InvalidSecretRef("unknown_prefix", f"Unknown backend '{backend}'")


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


def get_adapter(integration: LLMIntegration) -> LLMProviderAdapter:
    """
    Construct and return the correct LLMProviderAdapter for the given integration.

    Args:
        integration: An LLMIntegration ORM instance with provider, model,
                     api_key_secret_ref, and base_url populated.

    Returns:
        A configured LLMProviderAdapter ready to call create_message().

    Raises:
        ValueError: If integration.provider is not a recognized value.
        InvalidSecretRef: If the api_key_secret_ref is malformed or denied.
    """
    from app.schemas.llm_integrations import LLMProvider

    provider = integration.provider

    if provider == LLMProvider.ANTHROPIC:
        from app.integrations.llm.anthropic_adapter import AnthropicAdapter

        api_key = resolve_secret_ref(integration.api_key_secret_ref)
        return AnthropicAdapter(integration=integration, api_key=api_key)

    if provider in (LLMProvider.OPENAI, LLMProvider.AZURE_OPENAI):
        from app.integrations.llm.openai_adapter import OpenAIAdapter

        api_key = resolve_secret_ref(integration.api_key_secret_ref)
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

    # Check external adapter registry as a fallback
    from app.integrations.llm.adapter_registry import (
        get_external_adapter,
    )

    external = get_external_adapter(provider, integration=integration)
    if external is not None:
        return external

    raise ValueError(
        f"Unknown LLM provider '{provider}'. "
        "Valid built-in values: anthropic, openai, azure_openai, "
        "ollama, claude_code, aws_bedrock. "
        "External adapters can be registered via the "
        "'calseta.llm_adapters' entry-point group "
        "(see docs/security/external-adapters.md)."
    )
