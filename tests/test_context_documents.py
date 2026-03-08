"""Unit tests for context document schemas and targeting rule validation."""

from __future__ import annotations

from typing import Any

import pytest

from app.schemas.context_documents import (
    ContextDocumentCreate,
    ContextDocumentPatch,
    validate_targeting_rules,
)

# ---------------------------------------------------------------------------
# validate_targeting_rules
# ---------------------------------------------------------------------------


def test_none_rules_are_valid() -> None:
    assert validate_targeting_rules(None) == []


def test_valid_match_any_rule() -> None:
    rules = {
        "match_any": [{"field": "severity", "op": "eq", "value": "High"}]
    }
    assert validate_targeting_rules(rules) == []


def test_valid_match_all_rule() -> None:
    rules = {
        "match_all": [{"field": "source_name", "op": "eq", "value": "sentinel"}]
    }
    assert validate_targeting_rules(rules) == []


def test_valid_combined_rules() -> None:
    rules = {
        "match_any": [{"field": "severity", "op": "in", "value": ["High", "Critical"]}],
        "match_all": [{"field": "tags", "op": "contains", "value": "malware"}],
    }
    assert validate_targeting_rules(rules) == []


def test_rules_not_dict_returns_error() -> None:
    errors = validate_targeting_rules(["not", "a", "dict"])  # type: ignore[arg-type]
    assert any("must be an object" in e for e in errors)


def test_rules_missing_both_keys_returns_error() -> None:
    errors = validate_targeting_rules({})
    assert any("match_any" in e or "match_all" in e for e in errors)


def test_rules_unknown_key_returns_error() -> None:
    rules: dict[str, Any] = {"match_any": [], "unknown_key": []}
    errors = validate_targeting_rules(rules)
    assert any("unknown keys" in e for e in errors)


def test_rule_missing_field_key_returns_error() -> None:
    rules = {"match_any": [{"op": "eq", "value": "High"}]}
    errors = validate_targeting_rules(rules)
    assert any("missing required key 'field'" in e for e in errors)


def test_rule_missing_op_key_returns_error() -> None:
    rules = {"match_any": [{"field": "severity", "value": "High"}]}
    errors = validate_targeting_rules(rules)
    assert any("missing required key 'op'" in e for e in errors)


def test_rule_missing_value_key_returns_error() -> None:
    rules = {"match_any": [{"field": "severity", "op": "eq"}]}
    errors = validate_targeting_rules(rules)
    assert any("missing required key 'value'" in e for e in errors)


def test_rule_invalid_field_returns_error() -> None:
    rules = {"match_any": [{"field": "invalid_field", "op": "eq", "value": "x"}]}
    errors = validate_targeting_rules(rules)
    assert any("not in" in e for e in errors)


def test_rule_invalid_op_returns_error() -> None:
    rules = {"match_any": [{"field": "severity", "op": "not_an_op", "value": "x"}]}
    errors = validate_targeting_rules(rules)
    assert any("not in" in e for e in errors)


def test_all_valid_fields_accepted() -> None:
    for field in ("source_name", "severity", "tags"):
        rules = {"match_any": [{"field": field, "op": "eq", "value": "x"}]}
        errors = validate_targeting_rules(rules)
        assert errors == [], f"Field '{field}' should be valid but got: {errors}"


def test_all_valid_ops_accepted() -> None:
    for op in ("eq", "in", "contains", "gte", "lte"):
        rules = {"match_any": [{"field": "severity", "op": op, "value": "x"}]}
        errors = validate_targeting_rules(rules)
        assert errors == [], f"Op '{op}' should be valid but got: {errors}"


def test_match_any_not_array_returns_error() -> None:
    rules = {"match_any": {"not": "an array"}}
    errors = validate_targeting_rules(rules)
    assert any("must be an array" in e for e in errors)


# ---------------------------------------------------------------------------
# ContextDocumentCreate schema
# ---------------------------------------------------------------------------


def test_create_valid_json_body() -> None:
    body = ContextDocumentCreate(
        title="IR Plan",
        document_type="ir_plan",
        content="# IR Plan\n\nSteps...",
    )
    assert body.title == "IR Plan"
    assert body.document_type == "ir_plan"
    assert body.is_global is False
    assert body.tags == []
    assert body.targeting_rules is None


def test_create_invalid_document_type_raises() -> None:
    with pytest.raises(Exception, match="document_type"):
        ContextDocumentCreate(
            title="Test",
            document_type="not_a_type",
            content="content",
        )


def test_create_invalid_targeting_rules_raises() -> None:
    with pytest.raises(ValueError):
        ContextDocumentCreate(
            title="Test",
            document_type="runbook",
            content="content",
            targeting_rules={"bad_key": []},
        )


def test_create_with_valid_targeting_rules() -> None:
    body = ContextDocumentCreate(
        title="Test",
        document_type="runbook",
        content="content",
        targeting_rules={
            "match_all": [{"field": "severity", "op": "eq", "value": "High"}]
        },
    )
    assert body.targeting_rules is not None


def test_all_document_types_accepted() -> None:
    for dtype in ("runbook", "ir_plan", "sop", "playbook", "detection_guide", "other"):
        body = ContextDocumentCreate(
            title="T",
            document_type=dtype,
            content="c",
        )
        assert body.document_type == dtype


# ---------------------------------------------------------------------------
# ContextDocumentPatch schema
# ---------------------------------------------------------------------------


def test_patch_all_none_is_valid() -> None:
    body = ContextDocumentPatch()
    assert body.title is None
    assert body.document_type is None
    assert body.content is None


def test_patch_invalid_document_type_raises() -> None:
    with pytest.raises(Exception, match="document_type"):
        ContextDocumentPatch(document_type="not_valid")


def test_patch_valid_document_type() -> None:
    body = ContextDocumentPatch(document_type="sop")
    assert body.document_type == "sop"
