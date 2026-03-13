"""
FieldExtractor — applies enrichment_field_extractions rules to extract fields
from raw enrichment provider responses into a structured `extracted` dict.

For single-step providers, source_path is applied directly to the response
(the step wrapper is transparent). For multi-step providers, source_path is
prefixed by step name: "user_lookup.profile.login".

Value type coercion:
  - "string" → str(value)
  - "int" → int(value)
  - "float" → float(value)
  - "bool" → bool(value)
  - "list" → value as-is (must already be list)
  - "dict" → value as-is (must already be dict)
  - "any" → value as-is
"""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _resolve_dot_path(obj: Any, path: str) -> Any:
    """Traverse a nested dict by dot-separated path. Returns _MISSING if not found."""
    current = obj
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return _MISSING
            current = current[segment]
        elif isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return current


class _MissingSentinel:
    """Sentinel for missing values (distinct from None)."""
    pass


_MISSING = _MissingSentinel()


def _coerce_value(value: Any, value_type: str) -> Any:
    """Coerce a value to the declared type. Returns None on failure."""
    if isinstance(value, _MissingSentinel):
        return None

    if value is None:
        return None

    try:
        if value_type == "string":
            return str(value)
        if value_type == "int":
            return int(value)
        if value_type == "float":
            return float(value)
        if value_type == "bool":
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)
        # list, dict, any — return as-is
        return value
    except (TypeError, ValueError):
        return None


class FieldExtractor:
    """Extracts fields from enrichment provider responses using configured rules."""

    def __init__(
        self,
        extractions: list[dict[str, Any]],
    ) -> None:
        """
        Args:
            extractions: List of extraction rules, each with:
                - source_path: dot-notation path in raw response
                - target_key: key name in extracted dict
                - value_type: type to coerce to ("string", "int", "bool", etc.)
                - is_active: whether this extraction is enabled
        """
        self._extractions = [e for e in extractions if e.get("is_active", True)]

    def extract(self, raw_response: dict[str, Any]) -> dict[str, Any]:
        """Apply all extraction rules to the raw response.

        Args:
            raw_response: The raw API response data. For multi-step providers,
                this is keyed by step name. For single-step, it's the direct
                response body.

        Returns:
            Dict of target_key → extracted value.
        """
        extracted: dict[str, Any] = {}

        for rule in self._extractions:
            source_path = rule["source_path"]
            target_key = rule["target_key"]
            value_type = rule.get("value_type", "any")

            raw_value = _resolve_dot_path(raw_response, source_path)
            coerced = _coerce_value(raw_value, value_type)

            if coerced is not None:
                extracted[target_key] = coerced

        return extracted
