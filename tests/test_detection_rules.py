"""
Comprehensive tests for detection rule management and auto-association.

Covers:
  - DetectionRuleService unit tests
    - associate_detection_rule() — resolve or create + link
    - Empty/whitespace rule ref returns None
    - Existing rule lookup vs stub creation
  - DetectionRuleCreate/DetectionRulePatch schema validation
  - DetectionRuleResponse serialization
  - MITRE array field handling
  - Detection rule auto-association during alert ingestion
  - Source plugin extract_detection_rule_ref() integration

These are pure unit tests — no database or HTTP client required
(except where noted for service tests using mocked repos).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.sources.elastic import ElasticSource
from app.integrations.sources.generic import GenericSource
from app.integrations.sources.sentinel import SentinelSource
from app.integrations.sources.splunk import SplunkSource
from app.schemas.detection_rules import (
    DetectionRuleCreate,
    DetectionRulePatch,
    DetectionRuleResponse,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())  # type: ignore[no-any-return]


# =============================================================================
# Schema validation tests
# =============================================================================


class TestDetectionRuleCreateSchema:
    """DetectionRuleCreate Pydantic validation."""

    def test_minimal_valid(self) -> None:
        rule = DetectionRuleCreate(name="Test Rule")
        assert rule.name == "Test Rule"
        assert rule.is_active is True
        assert rule.mitre_tactics == []
        assert rule.mitre_techniques == []
        assert rule.mitre_subtechniques == []
        assert rule.data_sources == []
        assert rule.source_rule_id is None
        assert rule.source_name is None
        assert rule.severity is None
        assert rule.run_frequency is None
        assert rule.created_by is None
        assert rule.documentation is None

    def test_full_valid(self) -> None:
        rule = DetectionRuleCreate(
            name="Full Rule",
            source_rule_id="ext-123",
            source_name="sentinel",
            severity="High",
            is_active=True,
            mitre_tactics=["Execution", "DefenseEvasion"],
            mitre_techniques=["T1059", "T1027"],
            mitre_subtechniques=["T1059.001", "T1027.005"],
            data_sources=["process_creation", "network_flow"],
            run_frequency="5m",
            created_by="cai_test",
            documentation="Detects suspicious behavior",
        )
        assert rule.name == "Full Rule"
        assert rule.source_rule_id == "ext-123"
        assert len(rule.mitre_tactics) == 2
        assert "Execution" in rule.mitre_tactics
        assert len(rule.mitre_techniques) == 2
        assert "T1059" in rule.mitre_techniques
        assert len(rule.mitre_subtechniques) == 2
        assert "T1059.001" in rule.mitre_subtechniques
        assert len(rule.data_sources) == 2

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(Exception):
            DetectionRuleCreate(name="")

    def test_name_max_length(self) -> None:
        long_name = "a" * 500
        rule = DetectionRuleCreate(name=long_name)
        assert len(rule.name) == 500

    def test_name_too_long_rejected(self) -> None:
        with pytest.raises(Exception):
            DetectionRuleCreate(name="a" * 501)


class TestDetectionRulePatchSchema:
    """DetectionRulePatch Pydantic validation."""

    def test_all_none_is_valid(self) -> None:
        patch = DetectionRulePatch()
        assert patch.name is None
        assert patch.severity is None
        assert patch.is_active is None
        assert patch.mitre_tactics is None
        assert patch.mitre_techniques is None
        assert patch.mitre_subtechniques is None
        assert patch.data_sources is None
        assert patch.documentation is None

    def test_partial_update(self) -> None:
        patch = DetectionRulePatch(name="Updated Name", is_active=False)
        assert patch.name == "Updated Name"
        assert patch.is_active is False
        assert patch.severity is None

    def test_update_mitre_fields(self) -> None:
        patch = DetectionRulePatch(
            mitre_tactics=["Collection"],
            mitre_techniques=["T1114"],
            mitre_subtechniques=["T1114.001"],
        )
        assert patch.mitre_tactics == ["Collection"]
        assert patch.mitre_techniques == ["T1114"]
        assert patch.mitre_subtechniques == ["T1114.001"]

    def test_update_data_sources(self) -> None:
        patch = DetectionRulePatch(data_sources=["endpoint", "dns"])
        assert patch.data_sources == ["endpoint", "dns"]

    def test_update_documentation(self) -> None:
        patch = DetectionRulePatch(documentation="New docs")
        assert patch.documentation == "New docs"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(Exception):
            DetectionRulePatch(name="")

    def test_name_max_length(self) -> None:
        patch = DetectionRulePatch(name="a" * 500)
        assert len(patch.name) == 500  # type: ignore[arg-type]

    def test_exclude_none_for_partial_updates(self) -> None:
        """model_dump(exclude_none=True) should only include set fields."""
        patch = DetectionRulePatch(name="Updated")
        dumped = patch.model_dump(exclude_none=True)
        assert dumped == {"name": "Updated"}


class TestDetectionRuleResponseSchema:
    """DetectionRuleResponse serialization."""

    def test_from_mock_object(self) -> None:
        """Ensure model_validate(orm_object) works with from_attributes=True."""
        import uuid

        now = datetime.now(UTC)
        mock = MagicMock()
        mock.uuid = uuid.uuid4()
        mock.name = "Test Rule"
        mock.source_rule_id = "ext-123"
        mock.source_name = "sentinel"
        mock.severity = "High"
        mock.is_active = True
        mock.mitre_tactics = ["Execution"]
        mock.mitre_techniques = ["T1059"]
        mock.mitre_subtechniques = ["T1059.001"]
        mock.data_sources = ["process"]
        mock.run_frequency = "5m"
        mock.created_by = "cai_test"
        mock.documentation = "Some docs"
        mock.created_at = now
        mock.updated_at = now

        resp = DetectionRuleResponse.model_validate(mock)
        assert resp.name == "Test Rule"
        assert resp.source_rule_id == "ext-123"
        assert resp.mitre_tactics == ["Execution"]
        assert resp.mitre_techniques == ["T1059"]
        assert resp.mitre_subtechniques == ["T1059.001"]
        assert resp.data_sources == ["process"]
        assert resp.created_by == "cai_test"
        assert resp.documentation == "Some docs"

    def test_empty_mitre_arrays(self) -> None:
        import uuid

        now = datetime.now(UTC)
        mock = MagicMock()
        mock.uuid = uuid.uuid4()
        mock.name = "Bare Rule"
        mock.source_rule_id = None
        mock.source_name = None
        mock.severity = None
        mock.is_active = True
        mock.mitre_tactics = []
        mock.mitre_techniques = []
        mock.mitre_subtechniques = []
        mock.data_sources = []
        mock.run_frequency = None
        mock.created_by = None
        mock.documentation = None
        mock.created_at = now
        mock.updated_at = now

        resp = DetectionRuleResponse.model_validate(mock)
        assert resp.mitre_tactics == []
        assert resp.mitre_techniques == []
        assert resp.mitre_subtechniques == []
        assert resp.data_sources == []
        assert resp.source_rule_id is None
        assert resp.documentation is None


# =============================================================================
# DetectionRuleService unit tests (mocked dependencies)
# =============================================================================


class TestDetectionRuleServiceAssociate:
    """DetectionRuleService.associate_detection_rule() unit tests."""

    @pytest.mark.asyncio
    async def test_empty_rule_ref_returns_none(self) -> None:
        from app.services.detection_rules import DetectionRuleService

        mock_db = AsyncMock()
        svc = DetectionRuleService(mock_db)

        result = await svc.associate_detection_rule(
            MagicMock(), source_name="sentinel", source_rule_id=""
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_rule_ref_returns_none(self) -> None:
        from app.services.detection_rules import DetectionRuleService

        mock_db = AsyncMock()
        svc = DetectionRuleService(mock_db)

        result = await svc.associate_detection_rule(
            MagicMock(), source_name="sentinel", source_rule_id="   "
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_existing_rule_is_linked(self) -> None:
        from app.services.detection_rules import DetectionRuleService

        mock_db = AsyncMock()
        existing_rule = MagicMock()
        existing_rule.id = 42
        existing_rule.uuid = "rule-uuid"

        mock_alert = MagicMock()
        mock_alert.uuid = "alert-uuid"

        with patch(
            "app.services.detection_rules.DetectionRuleRepository"
        ) as MockRuleRepo, patch(
            "app.services.detection_rules.AlertRepository"
        ) as MockAlertRepo:
            MockRuleRepo.return_value.get_by_source_rule_id = AsyncMock(
                return_value=existing_rule
            )
            MockAlertRepo.return_value.set_detection_rule = AsyncMock()
            MockRuleRepo.return_value.create = AsyncMock()  # Should NOT be called

            svc = DetectionRuleService(mock_db)
            result = await svc.associate_detection_rule(
                mock_alert, source_name="sentinel", source_rule_id="rule-abc"
            )

        assert result is existing_rule
        MockAlertRepo.return_value.set_detection_rule.assert_called_once_with(
            mock_alert, 42
        )
        MockRuleRepo.return_value.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_stub_created_when_not_found(self) -> None:
        from app.services.detection_rules import DetectionRuleService

        mock_db = AsyncMock()
        new_rule = MagicMock()
        new_rule.id = 99
        new_rule.uuid = "new-rule-uuid"

        mock_alert = MagicMock()
        mock_alert.uuid = "alert-uuid"

        with patch(
            "app.services.detection_rules.DetectionRuleRepository"
        ) as MockRuleRepo, patch(
            "app.services.detection_rules.AlertRepository"
        ) as MockAlertRepo:
            MockRuleRepo.return_value.get_by_source_rule_id = AsyncMock(
                return_value=None
            )
            MockRuleRepo.return_value.create = AsyncMock(return_value=new_rule)
            MockAlertRepo.return_value.set_detection_rule = AsyncMock()

            svc = DetectionRuleService(mock_db)
            result = await svc.associate_detection_rule(
                mock_alert, source_name="elastic", source_rule_id="elastic-rule-123"
            )

        assert result is new_rule
        MockRuleRepo.return_value.create.assert_called_once()
        create_arg = MockRuleRepo.return_value.create.call_args[0][0]
        assert isinstance(create_arg, DetectionRuleCreate)
        assert create_arg.name == "elastic-rule-123"
        assert create_arg.source_rule_id == "elastic-rule-123"
        assert create_arg.source_name == "elastic"
        MockAlertRepo.return_value.set_detection_rule.assert_called_once_with(
            mock_alert, 99
        )


# =============================================================================
# Detection rule ref extraction from each source plugin
# =============================================================================


class TestDetectionRuleRefAllSources:
    """Verify extract_detection_rule_ref() returns expected refs for all sources."""

    def test_sentinel_extracts_rule_uuid(self) -> None:
        source = SentinelSource()
        payload = _load("sentinel_alert.json")
        ref = source.extract_detection_rule_ref(payload)
        assert ref == "rule-uuid-abc123"

    def test_elastic_extracts_rule_uuid(self) -> None:
        source = ElasticSource()
        payload = _load("elastic_alert.json")
        ref = source.extract_detection_rule_ref(payload)
        assert ref == "rule-uuid-elastic-abc"

    def test_splunk_extracts_rule_name(self) -> None:
        source = SplunkSource()
        payload = _load("splunk_alert.json")
        ref = source.extract_detection_rule_ref(payload)
        assert ref == "Brute Force Login Attempt"

    def test_generic_extracts_rule_id(self) -> None:
        source = GenericSource()
        ref = source.extract_detection_rule_ref({"rule_id": "GEN-001"})
        assert ref == "GEN-001"

    def test_generic_extracts_rule_name(self) -> None:
        source = GenericSource()
        ref = source.extract_detection_rule_ref({"rule_name": "Generic Rule"})
        assert ref == "Generic Rule"

    def test_all_return_none_when_missing(self) -> None:
        for source_cls in [SentinelSource, ElasticSource, SplunkSource, GenericSource]:
            source = source_cls()
            ref = source.extract_detection_rule_ref({})
            assert ref is None, f"{source_cls.__name__} should return None for empty payload"


# =============================================================================
# MITRE field validation
# =============================================================================


class TestMITREFields:
    """Verify MITRE array fields are handled correctly in schemas."""

    def test_create_with_mitre_fields(self) -> None:
        rule = DetectionRuleCreate(
            name="MITRE Rule",
            mitre_tactics=["InitialAccess", "Execution", "Persistence"],
            mitre_techniques=["T1566", "T1059", "T1053"],
            mitre_subtechniques=["T1566.001", "T1059.001", "T1053.005"],
        )
        assert len(rule.mitre_tactics) == 3
        assert "InitialAccess" in rule.mitre_tactics
        assert "Execution" in rule.mitre_tactics
        assert "Persistence" in rule.mitre_tactics
        assert len(rule.mitre_techniques) == 3
        assert len(rule.mitre_subtechniques) == 3

    def test_create_with_empty_mitre_fields(self) -> None:
        rule = DetectionRuleCreate(
            name="No MITRE",
            mitre_tactics=[],
            mitre_techniques=[],
            mitre_subtechniques=[],
        )
        assert rule.mitre_tactics == []
        assert rule.mitre_techniques == []
        assert rule.mitre_subtechniques == []

    def test_patch_mitre_fields(self) -> None:
        patch = DetectionRulePatch(
            mitre_tactics=["LateralMovement"],
            mitre_techniques=["T1021"],
        )
        dumped = patch.model_dump(exclude_none=True)
        assert dumped["mitre_tactics"] == ["LateralMovement"]
        assert dumped["mitre_techniques"] == ["T1021"]
        # Not set, should not appear
        assert "mitre_subtechniques" not in dumped

    def test_data_sources_array(self) -> None:
        rule = DetectionRuleCreate(
            name="Multi Source",
            data_sources=[
                "process_creation",
                "dns_resolution",
                "network_connection",
                "file_creation",
            ],
        )
        assert len(rule.data_sources) == 4
        assert "process_creation" in rule.data_sources


# =============================================================================
# AlertIngestionService detection rule integration (mocked)
# =============================================================================


class TestIngestionDetectionRuleAssociation:
    """
    Test that the ingest pipeline correctly calls associate_detection_rule
    when a source plugin returns a non-None rule ref.
    """

    @pytest.mark.asyncio
    async def test_ingest_calls_associate_when_rule_ref_present(self) -> None:
        """When source.extract_detection_rule_ref returns a value,
        the service should call associate_detection_rule."""
        from app.services.alert_ingestion import AlertIngestionService

        mock_db = AsyncMock()
        mock_queue = AsyncMock()
        mock_queue.enqueue.return_value = "task-id"

        # Create a mock source that returns a rule ref
        mock_source = MagicMock()
        mock_source.source_name = "sentinel"
        mock_source.normalize.return_value = MagicMock(
            title="Test Alert",
            severity=MagicMock(value="High"),
            occurred_at=datetime.now(UTC),
            source_name="sentinel",
            tags=[],
        )
        mock_source.extract_indicators.return_value = []
        mock_source.extract_detection_rule_ref.return_value = "rule-abc-123"

        mock_alert = MagicMock()
        mock_alert.id = 1
        mock_alert.uuid = "alert-uuid"

        with patch(
            "app.services.alert_ingestion.AlertRepository"
        ) as MockAlertRepo, patch(
            "app.services.alert_ingestion.DetectionRuleService"
        ) as MockRuleSvc, patch(
            "app.services.alert_ingestion.ActivityEventService"
        ), patch(
            "app.services.alert_ingestion.get_normalized_mappings",
            return_value=[],
        ), patch(
            "app.services.alert_ingestion.extract_for_fingerprint",
            return_value=[],
        ), patch(
            "app.services.alert_ingestion.generate_fingerprint",
            return_value="fp-hash",
        ):
            MockAlertRepo.return_value.find_duplicate = AsyncMock(return_value=None)
            MockAlertRepo.return_value.create = AsyncMock(return_value=mock_alert)
            MockRuleSvc.return_value.associate_detection_rule = AsyncMock()

            svc = AlertIngestionService(mock_db, mock_queue)
            result = await svc.ingest(mock_source, {"test": "payload"})

            MockRuleSvc.return_value.associate_detection_rule.assert_called_once_with(
                mock_alert,
                source_name="sentinel",
                source_rule_id="rule-abc-123",
            )

    @pytest.mark.asyncio
    async def test_ingest_skips_associate_when_no_rule_ref(self) -> None:
        """When source.extract_detection_rule_ref returns None,
        associate_detection_rule should NOT be called."""
        from app.services.alert_ingestion import AlertIngestionService

        mock_db = AsyncMock()
        mock_queue = AsyncMock()
        mock_queue.enqueue.return_value = "task-id"

        mock_source = MagicMock()
        mock_source.source_name = "generic"
        mock_source.normalize.return_value = MagicMock(
            title="No Rule Alert",
            severity=MagicMock(value="Low"),
            occurred_at=datetime.now(UTC),
            source_name="generic",
            tags=[],
        )
        mock_source.extract_indicators.return_value = []
        mock_source.extract_detection_rule_ref.return_value = None

        mock_alert = MagicMock()
        mock_alert.id = 2
        mock_alert.uuid = "alert-uuid-2"

        with patch(
            "app.services.alert_ingestion.AlertRepository"
        ) as MockAlertRepo, patch(
            "app.services.alert_ingestion.DetectionRuleService"
        ) as MockRuleSvc, patch(
            "app.services.alert_ingestion.ActivityEventService"
        ), patch(
            "app.services.alert_ingestion.get_normalized_mappings",
            return_value=[],
        ), patch(
            "app.services.alert_ingestion.extract_for_fingerprint",
            return_value=[],
        ), patch(
            "app.services.alert_ingestion.generate_fingerprint",
            return_value="fp-hash",
        ):
            MockAlertRepo.return_value.find_duplicate = AsyncMock(return_value=None)
            MockAlertRepo.return_value.create = AsyncMock(return_value=mock_alert)
            MockRuleSvc.return_value.associate_detection_rule = AsyncMock()

            svc = AlertIngestionService(mock_db, mock_queue)
            await svc.ingest(mock_source, {"test": "payload"})

            MockRuleSvc.return_value.associate_detection_rule.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_handles_association_error_gracefully(self) -> None:
        """If associate_detection_rule raises, ingest should still succeed."""
        from app.services.alert_ingestion import AlertIngestionService

        mock_db = AsyncMock()
        mock_queue = AsyncMock()
        mock_queue.enqueue.return_value = "task-id"

        mock_source = MagicMock()
        mock_source.source_name = "sentinel"
        mock_source.normalize.return_value = MagicMock(
            title="Error Alert",
            severity=MagicMock(value="High"),
            occurred_at=datetime.now(UTC),
            source_name="sentinel",
            tags=[],
        )
        mock_source.extract_indicators.return_value = []
        mock_source.extract_detection_rule_ref.return_value = "rule-xyz"

        mock_alert = MagicMock()
        mock_alert.id = 3
        mock_alert.uuid = "alert-uuid-3"

        with patch(
            "app.services.alert_ingestion.AlertRepository"
        ) as MockAlertRepo, patch(
            "app.services.alert_ingestion.DetectionRuleService"
        ) as MockRuleSvc, patch(
            "app.services.alert_ingestion.ActivityEventService"
        ), patch(
            "app.services.alert_ingestion.get_normalized_mappings",
            return_value=[],
        ), patch(
            "app.services.alert_ingestion.extract_for_fingerprint",
            return_value=[],
        ), patch(
            "app.services.alert_ingestion.generate_fingerprint",
            return_value="fp-hash",
        ):
            MockAlertRepo.return_value.find_duplicate = AsyncMock(return_value=None)
            MockAlertRepo.return_value.create = AsyncMock(return_value=mock_alert)
            # Simulate an error in association
            MockRuleSvc.return_value.associate_detection_rule = AsyncMock(
                side_effect=RuntimeError("DB error")
            )

            svc = AlertIngestionService(mock_db, mock_queue)
            # Should NOT raise — error is caught and logged
            result = await svc.ingest(mock_source, {"test": "payload"})
            assert result.alert is mock_alert
            assert result.is_duplicate is False


# =============================================================================
# Detection rule ref with realistic fixture payloads
# =============================================================================


class TestDetectionRuleRefWithFixtures:
    """
    End-to-end test: load fixture payload, call extract_detection_rule_ref,
    verify the returned value matches what the ingestion service would use
    to look up or create a DetectionRule.
    """

    def test_sentinel_fixture_rule_ref(self) -> None:
        source = SentinelSource()
        payload = _load("sentinel_alert.json")
        ref = source.extract_detection_rule_ref(payload)
        # The ARM path ends with "/alertRules/rule-uuid-abc123"
        assert ref is not None
        assert ref == "rule-uuid-abc123"

    def test_elastic_fixture_rule_ref(self) -> None:
        source = ElasticSource()
        payload = _load("elastic_alert.json")
        ref = source.extract_detection_rule_ref(payload)
        assert ref == "rule-uuid-elastic-abc"

    def test_splunk_fixture_rule_ref(self) -> None:
        source = SplunkSource()
        payload = _load("splunk_alert.json")
        ref = source.extract_detection_rule_ref(payload)
        # Splunk uses rule_name from result
        assert ref == "Brute Force Login Attempt"


# =============================================================================
# Sentinel ARM path parsing edge cases
# =============================================================================


class TestSentinelARMPathParsing:
    """Test various ARM path formats in relatedAnalyticRuleIds."""

    @pytest.fixture
    def source(self) -> SentinelSource:
        return SentinelSource()

    def test_simple_uuid(self, source: SentinelSource) -> None:
        payload = {
            "properties": {
                "relatedAnalyticRuleIds": [
                    "550e8400-e29b-41d4-a716-446655440000"
                ]
            }
        }
        assert source.extract_detection_rule_ref(payload) == "550e8400-e29b-41d4-a716-446655440000"

    def test_full_arm_path(self, source: SentinelSource) -> None:
        payload = {
            "properties": {
                "relatedAnalyticRuleIds": [
                    "/subscriptions/12345/resourceGroups/rg/providers/Microsoft.SecurityInsights/alertRules/my-rule-id"
                ]
            }
        }
        assert source.extract_detection_rule_ref(payload) == "my-rule-id"

    def test_trailing_slash_handled(self, source: SentinelSource) -> None:
        payload = {
            "properties": {
                "relatedAnalyticRuleIds": [
                    "/subs/a/alertRules/rule-123/"
                ]
            }
        }
        assert source.extract_detection_rule_ref(payload) == "rule-123"


# =============================================================================
# Splunk rule ref edge cases
# =============================================================================


class TestSplunkRuleRefEdgeCases:
    """Splunk extract_detection_rule_ref() edge cases."""

    @pytest.fixture
    def source(self) -> SplunkSource:
        return SplunkSource()

    def test_rule_name_preferred_over_search_name(self, source: SplunkSource) -> None:
        payload = {
            "result": {"rule_name": "ES Rule"},
            "search_name": "Saved Search",
            "sid": "1",
        }
        assert source.extract_detection_rule_ref(payload) == "ES Rule"

    def test_empty_rule_name_falls_to_search_name(self, source: SplunkSource) -> None:
        payload = {
            "result": {"rule_name": ""},
            "search_name": "Fallback Search",
            "sid": "1",
        }
        # Empty string is falsy, so should fall to search_name
        assert source.extract_detection_rule_ref(payload) == "Fallback Search"

    def test_no_result_object(self, source: SplunkSource) -> None:
        payload = {"search_name": "Only Search", "sid": "1"}
        assert source.extract_detection_rule_ref(payload) == "Only Search"

    def test_neither_field_present(self, source: SplunkSource) -> None:
        payload = {"result": {}, "sid": "1"}
        assert source.extract_detection_rule_ref(payload) is None


# =============================================================================
# Elastic rule ref edge cases
# =============================================================================


class TestElasticRuleRefEdgeCases:
    """Elastic extract_detection_rule_ref() edge cases."""

    @pytest.fixture
    def source(self) -> ElasticSource:
        return ElasticSource()

    def test_flat_format(self, source: ElasticSource) -> None:
        payload = {"kibana.alert.rule.uuid": "flat-uuid"}
        assert source.extract_detection_rule_ref(payload) == "flat-uuid"

    def test_nested_format(self, source: ElasticSource) -> None:
        payload = {"kibana": {"alert": {"rule": {"uuid": "nested-uuid"}}}}
        assert source.extract_detection_rule_ref(payload) == "nested-uuid"

    def test_missing_uuid(self, source: ElasticSource) -> None:
        payload = {"kibana.alert.rule.name": "Only name, no uuid"}
        assert source.extract_detection_rule_ref(payload) is None

    def test_numeric_uuid_converted_to_string(self, source: ElasticSource) -> None:
        payload = {"kibana.alert.rule.uuid": 12345}
        ref = source.extract_detection_rule_ref(payload)
        assert ref == "12345"


# =============================================================================
# Generic rule ref edge cases
# =============================================================================


class TestGenericRuleRefEdgeCases:
    """Generic extract_detection_rule_ref() edge cases."""

    @pytest.fixture
    def source(self) -> GenericSource:
        return GenericSource()

    def test_rule_id_present(self, source: GenericSource) -> None:
        assert source.extract_detection_rule_ref({"rule_id": "R-001"}) == "R-001"

    def test_rule_name_present(self, source: GenericSource) -> None:
        assert source.extract_detection_rule_ref({"rule_name": "My Rule"}) == "My Rule"

    def test_rule_id_preferred(self, source: GenericSource) -> None:
        payload = {"rule_id": "ID", "rule_name": "Name"}
        assert source.extract_detection_rule_ref(payload) == "ID"

    def test_empty_rule_id_falls_to_name(self, source: GenericSource) -> None:
        payload = {"rule_id": "", "rule_name": "Name"}
        assert source.extract_detection_rule_ref(payload) == "Name"

    def test_both_empty_returns_none(self, source: GenericSource) -> None:
        payload = {"rule_id": "", "rule_name": ""}
        assert source.extract_detection_rule_ref(payload) is None

    def test_neither_present_returns_none(self, source: GenericSource) -> None:
        assert source.extract_detection_rule_ref({}) is None

    def test_none_values_return_none(self, source: GenericSource) -> None:
        payload = {"rule_id": None, "rule_name": None}
        assert source.extract_detection_rule_ref(payload) is None


# =============================================================================
# AlertIngestionService deduplication with detection rules
# =============================================================================


class TestIngestionDeduplication:
    """
    Test that deduplication correctly short-circuits before detection rule
    association and enrichment enqueue.
    """

    @pytest.mark.asyncio
    async def test_duplicate_alert_skips_rule_association_and_queue(self) -> None:
        from app.services.alert_ingestion import AlertIngestionService

        mock_db = AsyncMock()
        mock_queue = AsyncMock()

        mock_source = MagicMock()
        mock_source.source_name = "generic"
        mock_source.normalize.return_value = MagicMock(
            title="Dup Alert",
            severity=MagicMock(value="Low"),
            occurred_at=datetime.now(UTC),
            source_name="generic",
            tags=[],
        )
        mock_source.extract_indicators.return_value = []
        mock_source.extract_detection_rule_ref.return_value = "some-rule"

        existing_alert = MagicMock()
        existing_alert.id = 10
        existing_alert.uuid = "existing-uuid"
        existing_alert.duplicate_count = 2

        with patch(
            "app.services.alert_ingestion.AlertRepository"
        ) as MockAlertRepo, patch(
            "app.services.alert_ingestion.DetectionRuleService"
        ) as MockRuleSvc, patch(
            "app.services.alert_ingestion.ActivityEventService"
        ), patch(
            "app.services.alert_ingestion.get_normalized_mappings",
            return_value=[],
        ), patch(
            "app.services.alert_ingestion.extract_for_fingerprint",
            return_value=[],
        ), patch(
            "app.services.alert_ingestion.generate_fingerprint",
            return_value="fp-hash",
        ):
            MockAlertRepo.return_value.find_duplicate = AsyncMock(
                return_value=existing_alert
            )
            MockAlertRepo.return_value.increment_duplicate = AsyncMock(
                return_value=existing_alert
            )
            MockAlertRepo.return_value.create = AsyncMock()

            svc = AlertIngestionService(mock_db, mock_queue)
            result = await svc.ingest(mock_source, {"title": "Dup Alert"})

            assert result.is_duplicate is True
            assert result.alert is existing_alert
            # Detection rule association should NOT be called for duplicates
            MockRuleSvc.return_value.associate_detection_rule.assert_not_called()
            # Alert create should NOT be called for duplicates
            MockAlertRepo.return_value.create.assert_not_called()
            # Queue should NOT be called for duplicates
            mock_queue.enqueue.assert_not_called()
