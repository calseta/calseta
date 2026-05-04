"""
External LLM adapter registry.

Two registration paths are supported, in this priority order:

1. **Recommended:** Python entry points in the
   ``calseta.llm_adapters`` group. Adapter packages declare them in
   their ``pyproject.toml``::

       [project.entry-points."calseta.llm_adapters"]
       gateway = "mycompany.llm_gateway:GatewayAdapter"

   These are discovered via :mod:`importlib.metadata` at startup and
   require the package to be installed in the same environment as
   Calseta. This means an attacker who only controls the operator's
   ``.env`` file (S10 threat model) cannot inject arbitrary code paths
   — they would also need package-install rights.

2. **Deprecated (back-compat):** the ``CALSETA_EXTERNAL_ADAPTERS`` env
   var, comma-separated ``module.path:ClassName`` entries. Still works,
   but emits ``external_adapter.module_path_deprecated`` warnings on
   every load. Operators should migrate to entry points.

External adapters must subclass :class:`LLMProviderAdapter` and set
``provider_name`` and ``display_name`` class attributes.

See ``docs/security/external-adapters.md`` for the full operator guide
and threat model.
"""

from __future__ import annotations

import importlib
from importlib.metadata import entry_points
from typing import Any

import structlog

from app.integrations.llm.base import LLMProviderAdapter

logger = structlog.get_logger(__name__)

# Entry-point group name. Packages register adapters under this group in
# their pyproject.toml: [project.entry-points."calseta.llm_adapters"]
ENTRY_POINT_GROUP = "calseta.llm_adapters"

# Global registry: provider_name -> adapter class
_external_adapters: dict[str, type[LLMProviderAdapter]] = {}


def load_external_adapters(spec: str = "") -> None:
    """Discover and register external LLM adapters.

    Loads adapters from two sources:

    1. ``importlib.metadata.entry_points(group="calseta.llm_adapters")``
       — the recommended path; discovered automatically from installed
       packages.
    2. ``spec`` — comma-separated ``module.path:ClassName`` entries
       (the deprecated ``CALSETA_EXTERNAL_ADAPTERS`` env var format).
       Kept for back-compat; emits a deprecation warning per entry.

    Both paths are tried; entry-point adapters are registered first so
    they win on duplicate ``provider_name`` collisions with module-path
    entries.

    Args:
        spec: Comma-separated ``module.path:ClassName`` entries from the
              ``CALSETA_EXTERNAL_ADAPTERS`` env var. Empty string skips
              the deprecated path entirely.
    """
    _load_from_entry_points()
    _load_from_module_paths(spec)


def _load_from_entry_points() -> None:
    """Discover adapters declared under the ``calseta.llm_adapters`` entry-point group."""
    try:
        eps = entry_points(group=ENTRY_POINT_GROUP)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(
            "external_adapter.entry_points_lookup_failed",
            error=str(exc),
        )
        return

    for ep in eps:
        try:
            adapter_cls = ep.load()
        except Exception as exc:
            logger.error(
                "external_adapter.entry_point_load_failed",
                entry_point=ep.name,
                value=ep.value,
                error=str(exc),
            )
            continue

        _register_adapter(
            adapter_cls,
            source="entry_point",
            entry_point_name=ep.name,
            entry_point_value=ep.value,
        )


def _load_from_module_paths(spec: str) -> None:
    """Parse the deprecated ``module:ClassName`` spec and register each adapter.

    Emits a per-entry deprecation warning so operators see it in logs.
    """
    if not spec or not spec.strip():
        return

    for raw_entry in spec.split(","):
        entry = raw_entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            logger.error(
                "external_adapter.invalid_format",
                entry=entry,
                hint="Expected 'module.path:ClassName'",
            )
            continue

        module_path, class_name = entry.rsplit(":", 1)

        logger.warning(
            "external_adapter.module_path_deprecated",
            entry=entry,
            module=module_path,
            class_name=class_name,
            hint=(
                "Module-path loading via CALSETA_EXTERNAL_ADAPTERS is "
                "deprecated. Migrate to a packaged entry point under "
                "the 'calseta.llm_adapters' group. See "
                "docs/security/external-adapters.md."
            ),
        )

        try:
            module = importlib.import_module(module_path)
            adapter_cls = getattr(module, class_name)
        except (ImportError, AttributeError) as exc:
            logger.error(
                "external_adapter.load_failed",
                entry=entry,
                error=str(exc),
            )
            continue

        _register_adapter(
            adapter_cls,
            source="module_path",
            module=module_path,
            class_name=class_name,
        )


def _register_adapter(
    adapter_cls: Any,
    *,
    source: str,
    **log_fields: Any,
) -> None:
    """Validate ``adapter_cls`` and add it to the global registry.

    Shared by both registration paths so validation is consistent.
    """
    if not (
        isinstance(adapter_cls, type)
        and issubclass(adapter_cls, LLMProviderAdapter)
    ):
        logger.error(
            "external_adapter.not_subclass",
            source=source,
            hint="Must subclass LLMProviderAdapter",
            **log_fields,
        )
        return

    name = getattr(adapter_cls, "provider_name", None)
    if not name:
        # Derive from class name: GatewayAdapter -> gateway
        derived = adapter_cls.__name__.replace("Adapter", "").lower()
        name = derived or adapter_cls.__name__.lower()
        adapter_cls.provider_name = name

    if name in _external_adapters:
        logger.warning(
            "external_adapter.duplicate",
            provider_name=name,
            source=source,
            **log_fields,
        )
        return

    _external_adapters[name] = adapter_cls
    display = getattr(adapter_cls, "display_name", None) or name
    logger.info(
        "external_adapter.registered",
        provider_name=name,
        display_name=display,
        source=source,
        **log_fields,
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
