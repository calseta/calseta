"""
External LLM adapter registry.

Loads adapter classes from Python packages specified in the
CALSETA_EXTERNAL_ADAPTERS env var at startup. Format:
    module.path:ClassName,another.module:AnotherClass

External adapters must subclass LLMProviderAdapter and set
provider_name and display_name class attributes.
"""

from __future__ import annotations

import importlib
from typing import Any

import structlog

from app.integrations.llm.base import LLMProviderAdapter

logger = structlog.get_logger(__name__)

# Global registry: provider_name -> adapter class
_external_adapters: dict[str, type[LLMProviderAdapter]] = {}


def load_external_adapters(spec: str) -> None:
    """Parse spec string and import+register each adapter class.

    Args:
        spec: Comma-separated "module.path:ClassName" entries.
              Empty string is a no-op.
    """
    if not spec or not spec.strip():
        return

    for entry in spec.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            logger.error(
                "external_adapter_invalid_format",
                entry=entry,
                hint="Expected 'module.path:ClassName'",
            )
            continue
        module_path, class_name = entry.rsplit(":", 1)
        try:
            module = importlib.import_module(module_path)
            adapter_cls = getattr(module, class_name)
        except (ImportError, AttributeError) as exc:
            logger.error(
                "external_adapter_load_failed",
                entry=entry,
                error=str(exc),
            )
            continue

        if not (
            isinstance(adapter_cls, type)
            and issubclass(adapter_cls, LLMProviderAdapter)
        ):
            logger.error(
                "external_adapter_not_subclass",
                entry=entry,
                hint="Must subclass LLMProviderAdapter",
            )
            continue

        name = getattr(adapter_cls, "provider_name", None)
        if not name:
            # Derive from class name: GatewayAdapter -> gateway
            name = class_name.replace("Adapter", "").lower()
            adapter_cls.provider_name = name

        if name in _external_adapters:
            logger.warning(
                "external_adapter_duplicate",
                provider_name=name,
                entry=entry,
            )
            continue

        _external_adapters[name] = adapter_cls
        display = getattr(adapter_cls, "display_name", None) or name
        logger.info(
            "external_adapter_registered",
            provider_name=name,
            display_name=display,
            module=module_path,
        )


def get_external_adapter(
    provider_name: str, **kwargs: Any,
) -> LLMProviderAdapter | None:
    """Return an instance of a registered external adapter, or None."""
    cls = _external_adapters.get(provider_name)
    if cls is None:
        return None
    return cls(**kwargs)


def list_external_providers() -> list[dict[str, str | bool]]:
    """Return metadata for all registered external adapters."""
    result: list[dict[str, str | bool]] = []
    for name, cls in _external_adapters.items():
        result.append({
            "provider_name": name,
            "display_name": getattr(cls, "display_name", name)
            or name,
            "is_external": True,
        })
    return result


def clear_registry() -> None:
    """Clear all registered adapters. For testing only."""
    _external_adapters.clear()
