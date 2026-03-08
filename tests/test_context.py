"""
Comprehensive tests for the context document system (Chunk 8.3).

Covers:
  - Targeting rule evaluation: all operators (eq, in, contains, gte, lte)
  - match_any vs match_all logic
  - Mixed targeting rules (both match_any and match_all)
  - Global documents always included
  - get_applicable_documents service function
  - Context document schema validation
  - GET /v1/alerts/{uuid}/context endpoint
  - Context document CRUD (create JSON, create multipart, read, update, delete)

This file tests context targeting at the unit level (no DB) and at the
integration level (via the FastAPI test client with a real DB session).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.services.context_targeting import (
    _evaluate_rule,
    _get_alert_field,
    evaluate_targeting_rules,
)

# ---------------------------------------------------------------------------
# Fixtures — mock_queue for integration tests that need a task queue
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_queue() -> AsyncGenerator[AsyncMock, None]:
    """
    Mock the task queue in both DI-injected and direct-import paths.

    Mirrors the same fixture in tests/integration/conftest.py.
    """
    from app.main import app
    from app.queue.dependencies import get_queue

    mock = AsyncMock()
    mock.enqueue.return_value = "mock-task-id"

    app.dependency_overrides[get_queue] = lambda: mock

    with patch("app.queue.factory.get_queue_backend", return_value=mock):
        yield mock

    app.dependency_overrides.pop(get_queue, None)


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
    """Test the service function that returns context documents for an alert."""

    @pytest.mark.asyncio
    async def test_global_documents_always_included(self) -> None:
        """Global documents (is_global=True) are always returned regardless of targeting rules."""
        from app.services.context_targeting import get_applicable_documents

        global_doc = MagicMock()
        global_doc.is_global = True
        global_doc.targeting_rules = None
        global_doc.document_type = "runbook"

        targeted_doc = MagicMock()
        targeted_doc.is_global = False
        targeted_doc.targeting_rules = {
            "match_any": [{"field": "severity", "op": "eq", "value": "Critical"}]
        }
        targeted_doc.document_type = "playbook"

        alert = _make_alert(severity="Low")  # Does NOT match targeted_doc rules

        mock_repo = AsyncMock()
        mock_repo.list_all_for_targeting.return_value = [global_doc, targeted_doc]

        mock_db = AsyncMock()

        with patch(
            "app.services.context_targeting.ContextDocumentRepository",
            return_value=mock_repo,
        ):
            result = await get_applicable_documents(alert, mock_db)

        assert len(result) == 1
        assert result[0] is global_doc

    @pytest.mark.asyncio
    async def test_targeted_documents_matched_by_rules(self) -> None:
        """Non-global documents are included only when targeting rules match."""
        from app.services.context_targeting import get_applicable_documents

        targeted_doc = MagicMock()
        targeted_doc.is_global = False
        targeted_doc.targeting_rules = {
            "match_any": [{"field": "severity", "op": "in", "value": ["High", "Critical"]}]
        }
        targeted_doc.document_type = "sop"

        alert = _make_alert(severity="High")

        mock_repo = AsyncMock()
        mock_repo.list_all_for_targeting.return_value = [targeted_doc]

        mock_db = AsyncMock()

        with patch(
            "app.services.context_targeting.ContextDocumentRepository",
            return_value=mock_repo,
        ):
            result = await get_applicable_documents(alert, mock_db)

        assert len(result) == 1
        assert result[0] is targeted_doc

    @pytest.mark.asyncio
    async def test_global_docs_ordered_before_targeted(self) -> None:
        """Global docs come first, then targeted docs, both sorted by document_type."""
        from app.services.context_targeting import get_applicable_documents

        global_sop = MagicMock()
        global_sop.is_global = True
        global_sop.targeting_rules = None
        global_sop.document_type = "sop"

        global_ir = MagicMock()
        global_ir.is_global = True
        global_ir.targeting_rules = None
        global_ir.document_type = "ir_plan"

        targeted_playbook = MagicMock()
        targeted_playbook.is_global = False
        targeted_playbook.targeting_rules = None  # None rules => always matches
        targeted_playbook.document_type = "playbook"

        alert = _make_alert()

        mock_repo = AsyncMock()
        mock_repo.list_all_for_targeting.return_value = [
            global_sop,
            targeted_playbook,
            global_ir,
        ]

        mock_db = AsyncMock()

        with patch(
            "app.services.context_targeting.ContextDocumentRepository",
            return_value=mock_repo,
        ):
            result = await get_applicable_documents(alert, mock_db)

        # Global docs first (sorted by type: ir_plan < sop), then targeted (playbook)
        assert result[0] is global_ir
        assert result[1] is global_sop
        assert result[2] is targeted_playbook

    @pytest.mark.asyncio
    async def test_no_documents_returns_empty_list(self) -> None:
        from app.services.context_targeting import get_applicable_documents

        alert = _make_alert()

        mock_repo = AsyncMock()
        mock_repo.list_all_for_targeting.return_value = []

        mock_db = AsyncMock()

        with patch(
            "app.services.context_targeting.ContextDocumentRepository",
            return_value=mock_repo,
        ):
            result = await get_applicable_documents(alert, mock_db)

        assert result == []

    @pytest.mark.asyncio
    async def test_non_global_doc_with_none_rules_is_included(self) -> None:
        """A non-global doc with targeting_rules=None matches all alerts."""
        from app.services.context_targeting import get_applicable_documents

        doc = MagicMock()
        doc.is_global = False
        doc.targeting_rules = None
        doc.document_type = "runbook"

        alert = _make_alert()

        mock_repo = AsyncMock()
        mock_repo.list_all_for_targeting.return_value = [doc]

        mock_db = AsyncMock()

        with patch(
            "app.services.context_targeting.ContextDocumentRepository",
            return_value=mock_repo,
        ):
            result = await get_applicable_documents(alert, mock_db)

        assert len(result) == 1
        assert result[0] is doc


# ===========================================================================
# Unit: Context document schema validation
# ===========================================================================


class TestContextDocumentSchemaValidation:
    def test_create_valid_json_body(self) -> None:
        from app.schemas.context_documents import ContextDocumentCreate

        body = ContextDocumentCreate(
            title="IR Plan",
            document_type="ir_plan",
            content="# Steps",
        )
        assert body.title == "IR Plan"
        assert body.document_type == "ir_plan"
        assert body.is_global is False
        assert body.tags == []
        assert body.targeting_rules is None

    def test_create_with_all_fields(self) -> None:
        from app.schemas.context_documents import ContextDocumentCreate

        body = ContextDocumentCreate(
            title="Full Doc",
            document_type="runbook",
            content="content",
            is_global=True,
            description="A runbook",
            tags=["tag1", "tag2"],
            targeting_rules={
                "match_any": [{"field": "severity", "op": "eq", "value": "High"}]
            },
        )
        assert body.is_global is True
        assert body.description == "A runbook"
        assert body.tags == ["tag1", "tag2"]
        assert body.targeting_rules is not None

    def test_create_invalid_document_type_raises(self) -> None:
        from app.schemas.context_documents import ContextDocumentCreate

        with pytest.raises(Exception, match="document_type"):
            ContextDocumentCreate(
                title="Test",
                document_type="invalid_type",
                content="content",
            )

    def test_create_invalid_targeting_rules_raises(self) -> None:
        from app.schemas.context_documents import ContextDocumentCreate

        with pytest.raises(ValueError):
            ContextDocumentCreate(
                title="Test",
                document_type="runbook",
                content="content",
                targeting_rules={"bad_key": []},
            )

    def test_patch_all_none_is_valid(self) -> None:
        from app.schemas.context_documents import ContextDocumentPatch

        body = ContextDocumentPatch()
        assert body.title is None
        assert body.content is None

    def test_patch_invalid_document_type_raises(self) -> None:
        from app.schemas.context_documents import ContextDocumentPatch

        with pytest.raises(Exception, match="document_type"):
            ContextDocumentPatch(document_type="not_valid")

    def test_all_document_types_accepted(self) -> None:
        from app.schemas.context_documents import ContextDocumentCreate

        for dtype in ("runbook", "ir_plan", "sop", "playbook", "detection_guide", "other"):
            body = ContextDocumentCreate(title="T", document_type=dtype, content="c")
            assert body.document_type == dtype

    def test_validate_targeting_rules_none_returns_empty(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        assert validate_targeting_rules(None) == []

    def test_validate_targeting_rules_not_dict(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        errors = validate_targeting_rules(["not", "dict"])  # type: ignore[arg-type]
        assert any("must be an object" in e for e in errors)

    def test_validate_targeting_rules_missing_both_keys(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        errors = validate_targeting_rules({})
        assert len(errors) > 0

    def test_validate_targeting_rules_unknown_key(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        errors = validate_targeting_rules({"match_any": [], "unknown_key": []})
        assert any("unknown keys" in e for e in errors)

    def test_validate_targeting_rules_missing_field_key(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        errors = validate_targeting_rules({"match_any": [{"op": "eq", "value": "x"}]})
        assert any("missing required key 'field'" in e for e in errors)

    def test_validate_targeting_rules_missing_op_key(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        errors = validate_targeting_rules({"match_any": [{"field": "severity", "value": "x"}]})
        assert any("missing required key 'op'" in e for e in errors)

    def test_validate_targeting_rules_missing_value_key(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        errors = validate_targeting_rules({"match_any": [{"field": "severity", "op": "eq"}]})
        assert any("missing required key 'value'" in e for e in errors)

    def test_validate_targeting_rules_invalid_field(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        errors = validate_targeting_rules(
            {"match_any": [{"field": "invalid_field", "op": "eq", "value": "x"}]}
        )
        assert any("not in" in e for e in errors)

    def test_validate_targeting_rules_invalid_op(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        errors = validate_targeting_rules(
            {"match_any": [{"field": "severity", "op": "not_an_op", "value": "x"}]}
        )
        assert any("not in" in e for e in errors)

    def test_validate_match_any_not_array(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        errors = validate_targeting_rules({"match_any": "not_array"})
        assert any("must be an array" in e for e in errors)

    def test_validate_match_all_not_array(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        errors = validate_targeting_rules({"match_all": {"not": "an_array"}})
        assert any("must be an array" in e for e in errors)

    def test_validate_combined_rules_valid(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        rules = {
            "match_any": [{"field": "severity", "op": "in", "value": ["High", "Critical"]}],
            "match_all": [{"field": "tags", "op": "contains", "value": "malware"}],
        }
        assert validate_targeting_rules(rules) == []

    def test_all_valid_ops_accepted(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        for op in ("eq", "in", "contains", "gte", "lte"):
            rules = {"match_any": [{"field": "severity", "op": op, "value": "x"}]}
            assert validate_targeting_rules(rules) == [], f"Op '{op}' should be valid"

    def test_all_valid_fields_accepted(self) -> None:
        from app.schemas.context_documents import validate_targeting_rules

        for field_name in ("source_name", "severity", "tags"):
            rules = {"match_any": [{"field": field_name, "op": "eq", "value": "x"}]}
            assert validate_targeting_rules(rules) == [], f"Field '{field_name}' should be valid"


# ===========================================================================
# Integration: Context document CRUD via API
# ===========================================================================


class TestContextDocumentCRUDIntegration:
    """
    These tests require a running DB (integration tests).
    They use the test_client and api_key fixtures from conftest.py.
    """

    @pytest.mark.asyncio
    async def test_create_json_returns_201(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Unit Test Runbook",
                "document_type": "runbook",
                "is_global": False,
                "content": "# Runbook\nStep 1",
                "tags": ["test"],
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Unit Test Runbook"
        assert data["document_type"] == "runbook"
        assert "uuid" in data
        assert "content" in data

    @pytest.mark.asyncio
    async def test_create_with_targeting_rules(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Targeted Doc",
                "document_type": "playbook",
                "is_global": False,
                "content": "Targeted content",
                "tags": [],
                "targeting_rules": {
                    "match_any": [
                        {"field": "severity", "op": "in", "value": ["High", "Critical"]}
                    ]
                },
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["targeting_rules"] is not None

    @pytest.mark.asyncio
    async def test_create_global_document(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Global SOP",
                "document_type": "sop",
                "is_global": True,
                "content": "Global content",
                "tags": [],
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["is_global"] is True

    @pytest.mark.asyncio
    async def test_create_multipart(
        self, test_client: Any, api_key: str
    ) -> None:
        """Upload via multipart/form-data with a text file."""
        resp = await test_client.post(
            "/v1/context-documents",
            data={
                "title": "Multipart Test",
                "document_type": "sop",
                "is_global": "false",
                "tags": "tag1,tag2",
            },
            files={"file": ("test.txt", b"# SOP Content\nDo this.", "text/plain")},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_get_by_uuid(
        self, test_client: Any, api_key: str
    ) -> None:
        # Create first
        create_resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Get Test",
                "document_type": "runbook",
                "content": "content",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        doc_uuid = create_resp.json()["data"]["uuid"]

        # Get
        resp = await test_client.get(
            f"/v1/context-documents/{doc_uuid}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["uuid"] == doc_uuid
        assert data["content"] == "content"

    @pytest.mark.asyncio
    async def test_get_404(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/context-documents/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_documents(
        self, test_client: Any, api_key: str
    ) -> None:
        # Create a doc first to ensure list is non-empty
        await test_client.post(
            "/v1/context-documents",
            json={
                "title": "List Test",
                "document_type": "runbook",
                "content": "content",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

        resp = await test_client.get(
            "/v1/context-documents",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_patch_title(
        self, test_client: Any, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Original",
                "document_type": "runbook",
                "content": "content",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        doc_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.patch(
            f"/v1/context-documents/{doc_uuid}",
            json={"title": "Updated Title"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_patch_content_increments_version(
        self, test_client: Any, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Version Test",
                "document_type": "runbook",
                "content": "v1",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        data = create_resp.json()["data"]
        doc_uuid = data["uuid"]
        original_version = data["version"]

        resp = await test_client.patch(
            f"/v1/context-documents/{doc_uuid}",
            json={"content": "v2"},
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["version"] == original_version + 1

    @pytest.mark.asyncio
    async def test_delete_204(
        self, test_client: Any, api_key: str
    ) -> None:
        create_resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Delete Test",
                "document_type": "runbook",
                "content": "content",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        doc_uuid = create_resp.json()["data"]["uuid"]

        resp = await test_client.delete(
            f"/v1/context-documents/{doc_uuid}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 204

        # Verify gone
        get_resp = await test_client.get(
            f"/v1/context-documents/{doc_uuid}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert get_resp.status_code == 404


# ===========================================================================
# Integration: GET /v1/alerts/{uuid}/context
# ===========================================================================


class TestAlertContextEndpointIntegration:
    """
    Tests for the alert-specific context endpoint.
    These require DB fixtures (test_client, api_key, mock_queue).
    """

    @pytest.mark.asyncio
    async def test_alert_context_returns_global_docs(
        self, test_client: Any, api_key: str, mock_queue: Any
    ) -> None:
        """A global document should appear in any alert's context response."""
        # Create a global context document
        doc_resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Global IR Plan",
                "document_type": "ir_plan",
                "is_global": True,
                "content": "# Global IR Plan",
                "tags": [],
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert doc_resp.status_code == 201

        # Create an alert
        alert_resp = await test_client.post(
            "/v1/alerts",
            json={
                "source_name": "generic",
                "payload": {
                    "title": "Context Test Alert",
                    "severity": "Low",
                    "occurred_at": "2026-01-15T10:00:00Z",
                    "tags": [],
                },
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert alert_resp.status_code == 202
        alert_uuid = alert_resp.json()["data"]["alert_uuid"]

        # Get alert context
        ctx_resp = await test_client.get(
            f"/v1/alerts/{alert_uuid}/context",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert ctx_resp.status_code == 200
        docs = ctx_resp.json()["data"]
        assert any(d["title"] == "Global IR Plan" for d in docs)

    @pytest.mark.asyncio
    async def test_alert_context_returns_matched_targeted_docs(
        self, test_client: Any, api_key: str, mock_queue: Any
    ) -> None:
        """A targeted document matching the alert's severity should be returned."""
        # Create a targeted context document for High severity
        doc_resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "High Severity Playbook",
                "document_type": "playbook",
                "is_global": False,
                "content": "# High severity steps",
                "tags": [],
                "targeting_rules": {
                    "match_any": [
                        {"field": "severity", "op": "eq", "value": "High"}
                    ]
                },
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert doc_resp.status_code == 201

        # Create a High severity alert
        alert_resp = await test_client.post(
            "/v1/alerts",
            json={
                "source_name": "generic",
                "payload": {
                    "title": "High Severity Alert",
                    "severity": "High",
                    "occurred_at": "2026-01-15T10:00:00Z",
                    "tags": [],
                },
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert alert_resp.status_code == 202
        alert_uuid = alert_resp.json()["data"]["alert_uuid"]

        ctx_resp = await test_client.get(
            f"/v1/alerts/{alert_uuid}/context",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert ctx_resp.status_code == 200
        docs = ctx_resp.json()["data"]
        assert any(d["title"] == "High Severity Playbook" for d in docs)

    @pytest.mark.asyncio
    async def test_alert_context_excludes_non_matching_targeted_docs(
        self, test_client: Any, api_key: str, mock_queue: Any
    ) -> None:
        """A targeted document that does NOT match should NOT be in the response."""
        # Create a targeted doc for Critical only
        doc_resp = await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Critical Only Playbook",
                "document_type": "playbook",
                "is_global": False,
                "content": "# Critical only",
                "tags": [],
                "targeting_rules": {
                    "match_any": [
                        {"field": "severity", "op": "eq", "value": "Critical"}
                    ]
                },
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert doc_resp.status_code == 201

        # Create a Low severity alert
        alert_resp = await test_client.post(
            "/v1/alerts",
            json={
                "source_name": "generic",
                "payload": {
                    "title": "Low Alert",
                    "severity": "Low",
                    "occurred_at": "2026-01-15T10:00:00Z",
                    "tags": [],
                },
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert alert_resp.status_code == 202
        alert_uuid = alert_resp.json()["data"]["alert_uuid"]

        ctx_resp = await test_client.get(
            f"/v1/alerts/{alert_uuid}/context",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert ctx_resp.status_code == 200
        docs = ctx_resp.json()["data"]
        assert not any(d["title"] == "Critical Only Playbook" for d in docs)

    @pytest.mark.asyncio
    async def test_alert_context_404_for_unknown_alert(
        self, test_client: Any, api_key: str
    ) -> None:
        resp = await test_client.get(
            "/v1/alerts/00000000-0000-0000-0000-000000000000/context",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 404


# ===========================================================================
# Integration: Context document filter endpoints
# ===========================================================================


class TestContextDocumentFilters:
    @pytest.mark.asyncio
    async def test_filter_by_document_type(
        self, test_client: Any, api_key: str
    ) -> None:
        # Create two docs of different types
        await test_client.post(
            "/v1/context-documents",
            json={
                "title": "SOP Filter Test",
                "document_type": "sop",
                "content": "sop content",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )
        await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Runbook Filter Test",
                "document_type": "runbook",
                "content": "runbook content",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

        resp = await test_client.get(
            "/v1/context-documents?document_type=sop",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        for doc in resp.json()["data"]:
            assert doc["document_type"] == "sop"

    @pytest.mark.asyncio
    async def test_filter_by_is_global(
        self, test_client: Any, api_key: str
    ) -> None:
        # Create a global doc
        await test_client.post(
            "/v1/context-documents",
            json={
                "title": "Global Filter Test",
                "document_type": "runbook",
                "is_global": True,
                "content": "global content",
            },
            headers={"Authorization": f"Bearer {api_key}"},
        )

        resp = await test_client.get(
            "/v1/context-documents?is_global=true",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        assert resp.status_code == 200
        for doc in resp.json()["data"]:
            assert doc["is_global"] is True
