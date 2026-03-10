"""
TemplateResolver — resolves {{namespace.field}} placeholders in enrichment
provider HTTP configs.

Supported namespaces:
  - indicator: {{indicator.value}}, {{indicator.type}}
  - auth: {{auth.api_key}}, {{auth.tenant_id}}, etc. (from decrypted auth_config)
  - steps: {{steps.<step_name>.response.<dot.path>}} (previous step results)

Supported filters:
  - urlencode: {{indicator.value | urlencode}}

Security: No Jinja2. Simple regex-based replacement with whitelisted namespaces.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")


def _resolve_dot_path(obj: Any, path: str) -> Any:
    """Traverse a nested dict/list by dot-separated path.

    Returns None if any segment is missing.
    """
    current = obj
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
        else:
            return None
        if current is None:
            return None
    return current


class TemplateResolver:
    """Resolves {{...}} placeholders in strings and nested structures."""

    def __init__(
        self,
        indicator_value: str,
        indicator_type: str,
        auth_config: dict[str, Any] | None = None,
        step_results: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._context: dict[str, Any] = {
            "indicator": {"value": indicator_value, "type": indicator_type},
            "auth": auth_config or {},
            "steps": step_results or {},
        }

    def resolve_string(self, template: str) -> str:
        """Resolve all placeholders in a single string."""

        def _replace(match: re.Match[str]) -> str:
            expr = match.group(1).strip()

            # Check for filter (only urlencode supported)
            raw_path = expr
            apply_urlencode = False
            if "|" in expr:
                parts = expr.split("|", 1)
                raw_path = parts[0].strip()
                filter_name = parts[1].strip()
                if filter_name == "urlencode":
                    apply_urlencode = True

            # Support shorthand: {{value}} → {{indicator.value}}, {{type}} → {{indicator.type}}
            if raw_path in ("value", "type"):
                raw_path = f"indicator.{raw_path}"

            # Validate namespace
            segments = raw_path.split(".", 1)
            namespace = segments[0]
            if namespace not in self._context:
                return match.group(0)  # Unknown namespace — leave as-is

            value = _resolve_dot_path(self._context, raw_path)
            if value is None:
                return ""

            result = str(value)
            if apply_urlencode:
                result = quote(result, safe="")
            return result

        return _PLACEHOLDER_RE.sub(_replace, template)

    def resolve_value(self, value: Any) -> Any:
        """Resolve placeholders in any value — string, dict, or list."""
        if isinstance(value, str):
            return self.resolve_string(value)
        if isinstance(value, dict):
            return {k: self.resolve_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve_value(item) for item in value]
        return value

    def add_step_result(self, step_name: str, response: dict[str, Any]) -> None:
        """Register a step's response for use in subsequent step templates."""
        self._context["steps"][step_name] = {"response": response}
