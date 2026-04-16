"""
Tests for the context targeting system.

Covers:
  - Targeting rule evaluation: all operators (eq, in, contains, gte, lte)
  - match_any vs match_all logic
  - Mixed targeting rules (both match_any and match_all)
  - Global KB pages always included
  - get_applicable_documents service function (KB page targeting)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.context_targeting import (
    _evaluate_rule,
    _get_alert_field,
    evaluate_targeting_rules,
)

# ===========================================================================
# Helpers
# ===========================================================================


def _make_alert(
    source_name: str = "sentinel",
    severity: str = "High",
    tags: list[str] | None = None,
) -> MagicMock:
    """Create a fake alert object with the supported targeting fields."""
    alert = MagicMock()
    alert.source_name = source_name
    alert.severity = severity
    alert.tags = tags or []
    return alert


# ===========================================================================
# Unit: _get_alert_field
# ===========================================================================


class TestGetAlertField:
    def test_returns_source_name(self) -> None:
        alert = _make_alert(source_name="elastic")
        assert _get_alert_field(alert, "source_name") == "elastic"

    def test_returns_severity(self) -> None:
        alert = _make_alert(severity="Critical")
        assert _get_alert_field(alert, "severity") == "Critical"

    def test_returns_tags(self) -> None:
        alert = _make_alert(tags=["malware", "test"])
        result = _get_alert_field(alert, "tags")
        assert result == ["malware", "test"]

    def test_returns_none_for_unknown_field(self) -> None:
        alert = _make_alert()
        assert _get_alert_field(alert, "nonexistent") is None

    def test_returns_none_for_empty_string_field(self) -> None:
        alert = _make_alert()
        assert _get_alert_field(alert, "") is None


# ===========================================================================
# Unit: _evaluate_rule — operator: eq
# ===========================================================================


class TestEvaluateRuleEq:
    def test_eq_matches_string(self) -> None:
        alert = _make_alert(source_name="elastic")
        rule = {"field": "source_name", "op": "eq", "value": "elastic"}
        assert _evaluate_rule(alert, rule) is True

    def test_eq_no_match(self) -> None:
        alert = _make_alert(source_name="splunk")
        rule = {"field": "source_name", "op": "eq", "value": "sentinel"}
        assert _evaluate_rule(alert, rule) is False

    def test_eq_compares_as_strings(self) -> None:
        """Numeric rule values are cast to string for comparison."""
        alert = _make_alert(severity="5")
        assert _evaluate_rule(alert, {"field": "severity", "op": "eq", "value": 5}) is True

    def test_eq_severity(self) -> None:
        alert = _make_alert(severity="Critical")
        assert _evaluate_rule(alert, {"field": "severity", "op": "eq", "value": "Critical"}) is True


# ===========================================================================
# Unit: _evaluate_rule — operator: in
# ===========================================================================


class TestEvaluateRuleIn:
    def test_in_matches_when_value_in_list(self) -> None:
        alert = _make_alert(severity="High")
        rule = {"field": "severity", "op": "in", "value": ["High", "Critical"]}
        assert _evaluate_rule(alert, rule) is True

    def test_in_no_match_when_value_not_in_list(self) -> None:
        alert = _make_alert(severity="Low")
        rule = {"field": "severity", "op": "in", "value": ["High", "Critical"]}
        assert _evaluate_rule(alert, rule) is False

    def test_in_rule_value_not_list_returns_false(self) -> None:
        """The 'in' operator requires rule value to be a list."""
        alert = _make_alert(severity="High")
        rule = {"field": "severity", "op": "in", "value": "High"}
        assert _evaluate_rule(alert, rule) is False

    def test_in_empty_list_returns_false(self) -> None:
        alert = _make_alert(severity="High")
        rule = {"field": "severity", "op": "in", "value": []}
        assert _evaluate_rule(alert, rule) is False


# ===========================================================================
# Unit: _evaluate_rule — operator: contains
# ===========================================================================


class TestEvaluateRuleContains:
    def test_contains_matches_tag_present(self) -> None:
        alert = _make_alert(tags=["malware", "phishing"])
        rule = {"field": "tags", "op": "contains", "value": "malware"}
        assert _evaluate_rule(alert, rule) is True

    def test_contains_no_match_when_tag_absent(self) -> None:
        alert = _make_alert(tags=["phishing"])
        rule = {"field": "tags", "op": "contains", "value": "malware"}
        assert _evaluate_rule(alert, rule) is False

    def test_contains_on_non_list_field_returns_false(self) -> None:
        """The 'contains' operator requires alert field to be a list."""
        alert = _make_alert(severity="High")
        rule = {"field": "severity", "op": "contains", "value": "High"}
        assert _evaluate_rule(alert, rule) is False

    def test_contains_empty_tags(self) -> None:
        alert = _make_alert(tags=[])
        rule = {"field": "tags", "op": "contains", "value": "anything"}
        assert _evaluate_rule(alert, rule) is False


# ===========================================================================
# Unit: _evaluate_rule — operators: gte, lte
# ===========================================================================


class TestEvaluateRuleGteLte:
    """
    Note: The targeting system only supports fields in _FIELD_ACCESSORS:
    source_name, severity, tags. The gte/lte operators work via float()
    casting so they only make sense on numeric-like values. In practice
    severity is a string ("High"), so gte/lte on severity would compare
    float("High") which raises ValueError, caught and returns False.
    These tests verify that behavior.
    """

    def test_gte_on_string_severity_returns_false(self) -> None:
        """gte with a non-numeric string field value returns False (ValueError caught)."""
        alert = _make_alert(severity="High")
        rule = {"field": "severity", "op": "gte", "value": 3}
        assert _evaluate_rule(alert, rule) is False

    def test_lte_on_string_severity_returns_false(self) -> None:
        alert = _make_alert(severity="High")
        rule = {"field": "severity", "op": "lte", "value": 5}
        assert _evaluate_rule(alert, rule) is False

    def test_gte_on_tags_list_returns_false(self) -> None:
        """gte on a list field (tags) returns False via TypeError."""
        alert = _make_alert(tags=["malware"])
        rule = {"field": "tags", "op": "gte", "value": 3}
        assert _evaluate_rule(alert, rule) is False

    def test_lte_on_tags_list_returns_false(self) -> None:
        alert = _make_alert(tags=["malware"])
        rule = {"field": "tags", "op": "lte", "value": 3}
        assert _evaluate_rule(alert, rule) is False


# ===========================================================================
# Unit: _evaluate_rule — edge cases
# ===========================================================================


class TestEvaluateRuleEdgeCases:
    def test_missing_field_key_returns_false(self) -> None:
        alert = _make_alert()
        assert _evaluate_rule(alert, {"op": "eq", "value": "x"}) is False

    def test_missing_op_key_returns_false(self) -> None:
        alert = _make_alert()
        assert _evaluate_rule(alert, {"field": "severity", "value": "x"}) is False

    def test_unknown_field_returns_false(self) -> None:
        alert = _make_alert()
        rule = {"field": "nonexistent_field", "op": "eq", "value": "x"}
        assert _evaluate_rule(alert, rule) is False

    def test_unknown_op_returns_false(self) -> None:
        alert = _make_alert(severity="High")
        rule = {"field": "severity", "op": "not_an_op", "value": "High"}
        assert _evaluate_rule(alert, rule) is False


# ===========================================================================
# Unit: evaluate_targeting_rules — top-level logic
# ===========================================================================


class TestEvaluateTargetingRules:
    def test_none_rules_always_match(self) -> None:
        assert evaluate_targeting_rules(_make_alert(), None) is True

    def test_empty_dict_matches(self) -> None:
        assert evaluate_targeting_rules(_make_alert(), {}) is True

    def test_match_any_passes_when_any_true(self) -> None:
        alert = _make_alert(severity="Low", source_name="elastic")
        rules = {
            "match_any": [
                {"field": "severity", "op": "eq", "value": "Critical"},
                {"field": "source_name", "op": "eq", "value": "elastic"},
            ]
        }
        assert evaluate_targeting_rules(alert, rules) is True

    def test_match_any_fails_when_all_false(self) -> None:
        alert = _make_alert(severity="Low", source_name="splunk")
        rules = {
            "match_any": [
                {"field": "severity", "op": "eq", "value": "Critical"},
                {"field": "source_name", "op": "eq", "value": "elastic"},
            ]
        }
        assert evaluate_targeting_rules(alert, rules) is False

    def test_match_all_passes_when_all_true(self) -> None:
        alert = _make_alert(severity="High", source_name="sentinel")
        rules = {
            "match_all": [
                {"field": "severity", "op": "eq", "value": "High"},
                {"field": "source_name", "op": "eq", "value": "sentinel"},
            ]
        }
        assert evaluate_targeting_rules(alert, rules) is True

    def test_match_all_fails_when_any_false(self) -> None:
        alert = _make_alert(severity="Low", source_name="sentinel")
        rules = {
            "match_all": [
                {"field": "severity", "op": "eq", "value": "High"},
                {"field": "source_name", "op": "eq", "value": "sentinel"},
            ]
        }
        assert evaluate_targeting_rules(alert, rules) is False


# ===========================================================================
# Unit: mixed match_any + match_all (both must pass)
# ===========================================================================


class TestMixedTargetingRules:
    def test_both_match_any_and_match_all_must_pass(self) -> None:
        alert = _make_alert(severity="High", source_name="sentinel")
        rules = {
            "match_any": [
                {"field": "severity", "op": "eq", "value": "High"},
                {"field": "severity", "op": "eq", "value": "Critical"},
            ],
            "match_all": [
                {"field": "source_name", "op": "eq", "value": "sentinel"},
            ],
        }
        assert evaluate_targeting_rules(alert, rules) is True

    def test_mixed_fails_when_match_all_fails(self) -> None:
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

    def test_mixed_fails_when_match_any_fails(self) -> None:
        alert = _make_alert(severity="Low", source_name="sentinel")
        rules = {
            "match_any": [
                {"field": "severity", "op": "eq", "value": "Critical"},
            ],
            "match_all": [
                {"field": "source_name", "op": "eq", "value": "sentinel"},
            ],
        }
        assert evaluate_targeting_rules(alert, rules) is False

    def test_mixed_fails_when_both_fail(self) -> None:
        alert = _make_alert(severity="Low", source_name="splunk")
        rules = {
            "match_any": [
                {"field": "severity", "op": "eq", "value": "Critical"},
            ],
            "match_all": [
                {"field": "source_name", "op": "eq", "value": "sentinel"},
            ],
        }
        assert evaluate_targeting_rules(alert, rules) is False


# ===========================================================================
# Unit: get_applicable_documents
# ===========================================================================


class TestGetApplicableDocuments:
    """Test the service function that returns KB pages applicable to an alert."""

    @pytest.mark.asyncio
    async def test_global_pages_always_included(self) -> None:
        """Global pages (inject_scope.global=True) are always returned regardless of targeting rules."""
        from app.services.context_targeting import get_applicable_documents

        global_page = MagicMock()
        global_page.inject_scope = {"global": True}
        global_page.targeting_rules = None

        targeted_page = MagicMock()
        targeted_page.inject_scope = {}
        targeted_page.targeting_rules = {
            "match_any": [{"field": "severity", "op": "eq", "value": "Critical"}]
        }

        alert = _make_alert(severity="Low")  # Does NOT match targeted_page rules

        mock_repo = AsyncMock()
        mock_repo.list_all_for_alert_targeting.return_value = [global_page, targeted_page]

        mock_db = AsyncMock()

        with patch(
            "app.repositories.kb_repository.KBPageRepository",
            return_value=mock_repo,
        ):
            result = await get_applicable_documents(alert, mock_db)

        assert len(result) == 1
        assert result[0] is global_page

    @pytest.mark.asyncio
    async def test_targeted_pages_matched_by_rules(self) -> None:
        """Non-global pages are included only when targeting rules match."""
        from app.services.context_targeting import get_applicable_documents

        targeted_page = MagicMock()
        targeted_page.inject_scope = {}
        targeted_page.targeting_rules = {
            "match_any": [{"field": "severity", "op": "in", "value": ["High", "Critical"]}]
        }

        alert = _make_alert(severity="High")

        mock_repo = AsyncMock()
        mock_repo.list_all_for_alert_targeting.return_value = [targeted_page]

        mock_db = AsyncMock()

        with patch(
            "app.repositories.kb_repository.KBPageRepository",
            return_value=mock_repo,
        ):
            result = await get_applicable_documents(alert, mock_db)

        assert len(result) == 1
        assert result[0] is targeted_page

    @pytest.mark.asyncio
    async def test_global_pages_ordered_before_targeted(self) -> None:
        """Global pages come first, then targeted pages."""
        from app.services.context_targeting import get_applicable_documents

        global_page_1 = MagicMock()
        global_page_1.inject_scope = {"global": True}
        global_page_1.targeting_rules = None

        global_page_2 = MagicMock()
        global_page_2.inject_scope = {"global": True}
        global_page_2.targeting_rules = None

        targeted_page = MagicMock()
        targeted_page.inject_scope = {}
        targeted_page.targeting_rules = None  # None rules => always matches

        alert = _make_alert()

        mock_repo = AsyncMock()
        mock_repo.list_all_for_alert_targeting.return_value = [
            global_page_1,
            targeted_page,
            global_page_2,
        ]

        mock_db = AsyncMock()

        with patch(
            "app.repositories.kb_repository.KBPageRepository",
            return_value=mock_repo,
        ):
            result = await get_applicable_documents(alert, mock_db)

        # Global pages first, then targeted
        assert len(result) == 3
        assert result[0] is global_page_1
        assert result[1] is global_page_2
        assert result[2] is targeted_page

    @pytest.mark.asyncio
    async def test_no_pages_returns_empty_list(self) -> None:
        from app.services.context_targeting import get_applicable_documents

        alert = _make_alert()

        mock_repo = AsyncMock()
        mock_repo.list_all_for_alert_targeting.return_value = []

        mock_db = AsyncMock()

        with patch(
            "app.repositories.kb_repository.KBPageRepository",
            return_value=mock_repo,
        ):
            result = await get_applicable_documents(alert, mock_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_non_global_page_with_none_rules_is_included(self) -> None:
        """A non-global page with targeting_rules=None matches all alerts."""
        from app.services.context_targeting import get_applicable_documents

        page = MagicMock()
        page.inject_scope = {}
        page.targeting_rules = None

        alert = _make_alert()

        mock_repo = AsyncMock()
        mock_repo.list_all_for_alert_targeting.return_value = [page]

        mock_db = AsyncMock()

        with patch(
            "app.repositories.kb_repository.KBPageRepository",
            return_value=mock_repo,
        ):
            result = await get_applicable_documents(alert, mock_db)

        assert len(result) == 1
        assert result[0] is page


