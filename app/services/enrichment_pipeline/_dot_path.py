"""Shared dot-path resolution utility for the enrichment pipeline.

Traverses nested dicts/lists by dot-separated path strings. Used by
FieldExtractor, MaliceRuleEvaluator, and TemplateResolver.
"""

from __future__ import annotations

from typing import Any


class _MissingSentinel:
    """Sentinel for missing values (distinct from None)."""

    pass


MISSING = _MissingSentinel()


def resolve_dot_path(obj: Any, path: str, *, missing: Any = None) -> Any:
    """Traverse a nested dict/list by dot-separated path.

    Args:
        obj: Root object to traverse.
        path: Dot-separated path string (e.g. "data.attributes.score").
        missing: Value to return when the path is not found.
            Defaults to None. Pass ``MISSING`` to get the sentinel.

    Returns:
        The resolved value, or *missing* if any segment is absent.
    """
    current = obj
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return missing
            current = current[segment]
        elif isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return missing
        else:
            return missing
        if current is None:
            return missing
    return current
