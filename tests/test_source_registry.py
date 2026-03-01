"""Tests for AlertSourceBase ABC and SourceRegistry."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.integrations.sources.base import AlertSourceBase
from app.integrations.sources.registry import SourceRegistry
from app.schemas.alert import AlertSeverity, CalsetaAlert
from app.schemas.indicators import IndicatorExtract, IndicatorType

# ---------------------------------------------------------------------------
# Minimal concrete source for testing
# ---------------------------------------------------------------------------

class _MockSource(AlertSourceBase):
    source_name = "mock"
    display_name = "Mock Source"

    def validate_payload(self, raw: dict) -> bool:
        return bool(raw.get("is_valid"))

    def normalize(self, raw: dict) -> CalsetaAlert:
        return CalsetaAlert(
            title=raw.get("title", "Test Alert"),
            severity=AlertSeverity.MEDIUM,
            occurred_at=datetime(2024, 1, 1, tzinfo=UTC),
            source_name=self.source_name,
        )

    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]:
        if ip := raw.get("src_ip"):
            return [IndicatorExtract(type=IndicatorType.IP, value=ip, source_field="src_ip")]
        return []


# ---------------------------------------------------------------------------
# AlertSourceBase tests
# ---------------------------------------------------------------------------

class TestAlertSourceBase:
    def test_direct_instantiation_raises(self) -> None:
        with pytest.raises(TypeError):
            AlertSourceBase()  # type: ignore[abstract]

    def test_extract_detection_rule_ref_default_returns_none(self) -> None:
        source = _MockSource()
        assert source.extract_detection_rule_ref({}) is None

    def test_verify_webhook_signature_default_returns_true(self) -> None:
        source = _MockSource()
        result = source.verify_webhook_signature(
            headers={"X-Hub-Signature": "invalid"},
            raw_body=b'{"test": true}',
        )
        assert result is True

    def test_validate_payload_returns_false_not_raises_on_bad_input(self) -> None:
        source = _MockSource()
        assert source.validate_payload({}) is False
        assert source.validate_payload({"is_valid": True}) is True

    def test_normalize_returns_calseta_alert(self) -> None:
        source = _MockSource()
        alert = source.normalize({"title": "SQL Injection Detected"})
        assert isinstance(alert, CalsetaAlert)
        assert alert.source_name == "mock"
        assert alert.severity == AlertSeverity.MEDIUM

    def test_extract_indicators_returns_empty_list_when_none(self) -> None:
        source = _MockSource()
        result = source.extract_indicators({})
        assert result == []

    def test_extract_indicators_returns_list_of_indicator_extract(self) -> None:
        source = _MockSource()
        result = source.extract_indicators({"src_ip": "1.2.3.4"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP
        assert result[0].value == "1.2.3.4"


# ---------------------------------------------------------------------------
# SourceRegistry tests
# ---------------------------------------------------------------------------

class TestSourceRegistry:
    def test_get_nonexistent_returns_none(self) -> None:
        registry = SourceRegistry()
        assert registry.get("nonexistent") is None

    def test_register_and_get(self) -> None:
        registry = SourceRegistry()
        source = _MockSource()
        registry.register(source)
        assert registry.get("mock") is source

    def test_list_all_returns_registered_sources(self) -> None:
        registry = SourceRegistry()
        source = _MockSource()
        registry.register(source)
        assert source in registry.list_all()

    def test_duplicate_source_name_raises_value_error(self) -> None:
        registry = SourceRegistry()
        registry.register(_MockSource())
        with pytest.raises(ValueError, match="mock.*already registered"):
            registry.register(_MockSource())

    def test_list_all_empty_registry(self) -> None:
        registry = SourceRegistry()
        assert registry.list_all() == []
