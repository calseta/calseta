"""
MaliceRuleEvaluator — evaluates threshold rules from provider malice_rules config.

Rules are evaluated in order; first match wins. If no rule matches, the
default_verdict is returned. If the indicator was not found (HTTP 404 / not_found_status),
the not_found_verdict is returned.

Rule format (stored in enrichment_providers.malice_rules):
{
  "rules": [
    {"field": "data.abuseConfidenceScore", "operator": ">=", "value": 75, "verdict": "Malicious"},
    {"field": "data.abuseConfidenceScore", "operator": ">=", "value": 25, "verdict": "Suspicious"}
  ],
  "default_verdict": "Benign",
  "not_found_verdict": "Pending"
}

Operators: >, >=, <, <=, ==, !=, contains, in
"""

from __future__ import annotations

from typing import Any


def _resolve_dot_path(obj: Any, path: str) -> Any:
    """Traverse a nested dict by dot-separated path. Returns None if missing."""
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


def _evaluate_condition(actual: Any, operator: str, expected: Any) -> bool:
    """Evaluate a single comparison condition."""
    if actual is None:
        return False

    if operator == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        if isinstance(actual, (list, dict)):
            return expected in actual
        return False

    if operator == "in":
        if isinstance(expected, (list, tuple)):
            return actual in expected
        return False

    # Numeric / equality comparisons
    try:
        if operator == "==":
            return actual == expected
        if operator == "!=":
            return actual != expected

        # Coerce to float for numeric comparisons
        actual_num = float(actual)
        expected_num = float(expected)

        if operator == ">":
            return actual_num > expected_num
        if operator == ">=":
            return actual_num >= expected_num
        if operator == "<":
            return actual_num < expected_num
        if operator == "<=":
            return actual_num <= expected_num
    except (TypeError, ValueError):
        return False

    return False


class MaliceRuleEvaluator:
    """Evaluates malice rules against enrichment response data."""

    def __init__(self, malice_rules: dict[str, Any] | None) -> None:
        if malice_rules is None:
            self._rules: list[dict[str, Any]] = []
            self._default_verdict = "Pending"
            self._not_found_verdict = "Pending"
        else:
            self._rules = malice_rules.get("rules", [])
            self._default_verdict = malice_rules.get("default_verdict", "Pending")
            self._not_found_verdict = malice_rules.get("not_found_verdict", "Pending")

    def evaluate(
        self,
        response_data: dict[str, Any],
        *,
        not_found: bool = False,
    ) -> str:
        """Evaluate rules against the merged response data.

        Args:
            response_data: The combined response from all steps (keyed by step
                name for multi-step, or flat for single-step).
            not_found: If True, the indicator was not found (404 / not_found_status).

        Returns:
            Malice verdict string: Pending, Benign, Suspicious, or Malicious.
        """
        if not_found:
            return self._not_found_verdict

        if not self._rules:
            return self._default_verdict

        for rule in self._rules:
            field = rule.get("field", "")
            operator = rule.get("operator", "==")
            expected = rule.get("value")
            verdict = rule.get("verdict", self._default_verdict)

            actual = _resolve_dot_path(response_data, field)
            if _evaluate_condition(actual, operator, expected):
                return verdict

        return self._default_verdict
