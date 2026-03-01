"""Unit tests for context targeting rule evaluation engine (Chunk 4.2)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.context_targeting import evaluate_targeting_rules

# ---------------------------------------------------------------------------
# Helper: create a fake alert object
# ---------------------------------------------------------------------------


def _make_alert(
    source_name: str = "sentinel",
    severity: str = "High",
    severity_id: int = 4,
    tags: list[str] | None = None,
) -> MagicMock:
    alert = MagicMock()
    alert.source_name = source_name
    alert.severity = severity
    alert.severity_id = severity_id
    alert.tags = tags or []
    return alert


# ---------------------------------------------------------------------------
# None rules — always matches
# ---------------------------------------------------------------------------


def test_none_rules_always_match() -> None:
    alert = _make_alert()
    assert evaluate_targeting_rules(alert, None) is True


def test_empty_rules_dict_matches() -> None:
    alert = _make_alert()
    assert evaluate_targeting_rules(alert, {}) is True


# ---------------------------------------------------------------------------
# Operator: eq
# ---------------------------------------------------------------------------


def test_eq_source_name_matches() -> None:
    alert = _make_alert(source_name="elastic")
    rules = {"match_any": [{"field": "source_name", "op": "eq", "value": "elastic"}]}
    assert evaluate_targeting_rules(alert, rules) is True


def test_eq_source_name_no_match() -> None:
    alert = _make_alert(source_name="splunk")
    rules = {"match_any": [{"field": "source_name", "op": "eq", "value": "sentinel"}]}
    assert evaluate_targeting_rules(alert, rules) is False


def test_eq_severity_matches() -> None:
    alert = _make_alert(severity="Critical")
    rules = {"match_any": [{"field": "severity", "op": "eq", "value": "Critical"}]}
    assert evaluate_targeting_rules(alert, rules) is True


def test_eq_severity_id_matches() -> None:
    alert = _make_alert(severity_id=5)
    rules = {"match_all": [{"field": "severity_id", "op": "eq", "value": "5"}]}
    assert evaluate_targeting_rules(alert, rules) is True


# ---------------------------------------------------------------------------
# Operator: in
# ---------------------------------------------------------------------------


def test_in_operator_matches_when_value_in_list() -> None:
    alert = _make_alert(severity="High")
    rules = {
        "match_any": [{"field": "severity", "op": "in", "value": ["High", "Critical"]}]
    }
    assert evaluate_targeting_rules(alert, rules) is True


def test_in_operator_no_match_when_value_not_in_list() -> None:
    alert = _make_alert(severity="Low")
    rules = {
        "match_any": [{"field": "severity", "op": "in", "value": ["High", "Critical"]}]
    }
    assert evaluate_targeting_rules(alert, rules) is False


def test_in_operator_rule_value_not_list_returns_false() -> None:
    alert = _make_alert(severity="High")
    rules = {
        "match_any": [{"field": "severity", "op": "in", "value": "High"}]
    }
    assert evaluate_targeting_rules(alert, rules) is False


# ---------------------------------------------------------------------------
# Operator: contains
# ---------------------------------------------------------------------------


def test_contains_operator_matches_when_tag_present() -> None:
    alert = _make_alert(tags=["malware", "phishing"])
    rules = {"match_any": [{"field": "tags", "op": "contains", "value": "malware"}]}
    assert evaluate_targeting_rules(alert, rules) is True


def test_contains_operator_no_match_when_tag_absent() -> None:
    alert = _make_alert(tags=["phishing"])
    rules = {"match_any": [{"field": "tags", "op": "contains", "value": "malware"}]}
    assert evaluate_targeting_rules(alert, rules) is False


def test_contains_operator_on_non_list_field_returns_false() -> None:
    alert = _make_alert(severity="High")
    rules = {"match_any": [{"field": "severity", "op": "contains", "value": "High"}]}
    assert evaluate_targeting_rules(alert, rules) is False


# ---------------------------------------------------------------------------
# Operator: gte / lte
# ---------------------------------------------------------------------------


def test_gte_operator_matches() -> None:
    alert = _make_alert(severity_id=4)
    rules = {"match_all": [{"field": "severity_id", "op": "gte", "value": 3}]}
    assert evaluate_targeting_rules(alert, rules) is True


def test_gte_operator_no_match() -> None:
    alert = _make_alert(severity_id=2)
    rules = {"match_all": [{"field": "severity_id", "op": "gte", "value": 3}]}
    assert evaluate_targeting_rules(alert, rules) is False


def test_lte_operator_matches() -> None:
    alert = _make_alert(severity_id=2)
    rules = {"match_all": [{"field": "severity_id", "op": "lte", "value": 3}]}
    assert evaluate_targeting_rules(alert, rules) is True


def test_lte_operator_no_match() -> None:
    alert = _make_alert(severity_id=5)
    rules = {"match_all": [{"field": "severity_id", "op": "lte", "value": 3}]}
    assert evaluate_targeting_rules(alert, rules) is False


# ---------------------------------------------------------------------------
# Logic: match_any (OR) and match_all (AND)
# ---------------------------------------------------------------------------


def test_match_any_passes_when_any_rule_true() -> None:
    alert = _make_alert(severity="Low", source_name="elastic")
    rules = {
        "match_any": [
            {"field": "severity", "op": "eq", "value": "Critical"},
            {"field": "source_name", "op": "eq", "value": "elastic"},
        ]
    }
    assert evaluate_targeting_rules(alert, rules) is True


def test_match_any_fails_when_all_rules_false() -> None:
    alert = _make_alert(severity="Low", source_name="splunk")
    rules = {
        "match_any": [
            {"field": "severity", "op": "eq", "value": "Critical"},
            {"field": "source_name", "op": "eq", "value": "elastic"},
        ]
    }
    assert evaluate_targeting_rules(alert, rules) is False


def test_match_all_passes_when_all_rules_true() -> None:
    alert = _make_alert(severity="High", source_name="sentinel")
    rules = {
        "match_all": [
            {"field": "severity", "op": "eq", "value": "High"},
            {"field": "source_name", "op": "eq", "value": "sentinel"},
        ]
    }
    assert evaluate_targeting_rules(alert, rules) is True


def test_match_all_fails_when_any_rule_false() -> None:
    alert = _make_alert(severity="Low", source_name="sentinel")
    rules = {
        "match_all": [
            {"field": "severity", "op": "eq", "value": "High"},
            {"field": "source_name", "op": "eq", "value": "sentinel"},
        ]
    }
    assert evaluate_targeting_rules(alert, rules) is False


def test_mixed_match_any_and_match_all_both_must_pass() -> None:
    alert = _make_alert(severity="High", source_name="sentinel", severity_id=4)
    rules = {
        "match_any": [
            {"field": "severity", "op": "eq", "value": "High"},
        ],
        "match_all": [
            {"field": "source_name", "op": "eq", "value": "sentinel"},
        ],
    }
    assert evaluate_targeting_rules(alert, rules) is True


def test_mixed_mode_fails_when_match_all_fails() -> None:
    alert = _make_alert(severity="High", source_name="elastic")
    rules = {
        "match_any": [
            {"field": "severity", "op": "eq", "value": "High"},
        ],
        "match_all": [
            {"field": "source_name", "op": "eq", "value": "sentinel"},
        ],
    }
    assert evaluate_targeting_rules(alert, rules) is False


# ---------------------------------------------------------------------------
# Invalid / unknown fields
# ---------------------------------------------------------------------------


def test_unknown_field_evaluates_to_false() -> None:
    alert = _make_alert()
    rules = {"match_any": [{"field": "nonexistent_field", "op": "eq", "value": "x"}]}
    assert evaluate_targeting_rules(alert, rules) is False


def test_unknown_op_evaluates_to_false() -> None:
    alert = _make_alert(severity="High")
    rules = {"match_any": [{"field": "severity", "op": "not_an_op", "value": "High"}]}
    assert evaluate_targeting_rules(alert, rules) is False


def test_type_mismatch_on_numeric_op_returns_false() -> None:
    alert = _make_alert(tags=["malware"])  # tags is a list, not numeric
    rules = {"match_any": [{"field": "tags", "op": "gte", "value": 3}]}
    assert evaluate_targeting_rules(alert, rules) is False
