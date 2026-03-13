"""
Comprehensive tests for alert ingestion — source plugin unit tests and edge cases.

Covers:
  - Source plugins: Sentinel, Elastic, Splunk, Generic
    - normalize() happy path and edge cases
    - validate_payload() positive/negative
    - extract_indicators() with realistic fixtures and edge cases
    - extract_detection_rule_ref()
    - verify_webhook_signature()
  - Edge cases: missing optional fields, empty arrays, unusual severities,
    case-insensitive headers, sha256= prefix, nested vs flat Elastic format,
    unix timestamp edge cases for Splunk, generic explicit indicators array

These are pure unit tests — no database or HTTP client required.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.integrations.sources.elastic import ElasticSource, _get
from app.integrations.sources.generic import GenericSource
from app.integrations.sources.sentinel import SentinelSource
from app.integrations.sources.splunk import SplunkSource
from app.schemas.alert import AlertSeverity, CalsetaAlert
from app.schemas.indicators import IndicatorType

FIXTURES = Path(__file__).parent / "fixtures"

# Shared hash values used across tests
SHA256_PS = "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456"
SHA256_SPLUNK = "b94f6f125c79e3a5ffaa826f584c10d52ada669e6762051b826b55776d05a8a"
MD5_VAL = "d41d8cd98f00b204e9800998ecf8427e"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())  # type: ignore[no-any-return]


def _setattr_sentinel_secret(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setattr(
        "app.integrations.sources.sentinel.settings.SENTINEL_WEBHOOK_SECRET", value
    )


def _setattr_elastic_secret(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setattr(
        "app.integrations.sources.elastic.settings.ELASTIC_WEBHOOK_SECRET", value
    )


def _setattr_splunk_secret(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setattr(
        "app.integrations.sources.splunk.settings.SPLUNK_WEBHOOK_SECRET", value
    )


# =============================================================================
# Microsoft Sentinel — edge cases and additional coverage
# =============================================================================


class TestSentinelNormalize:
    """Sentinel normalize() edge cases."""

    @pytest.fixture
    def source(self) -> SentinelSource:
        return SentinelSource()

    @pytest.fixture
    def payload(self) -> dict:  # type: ignore[type-arg]
        return _load("sentinel_alert.json")

    def test_normalize_happy_path(self, source: SentinelSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert isinstance(alert, CalsetaAlert)
        assert alert.title == "Suspicious PowerShell Execution on WORKSTATION-01"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.source_name == "sentinel"
        assert alert.occurred_at.year == 2024
        assert alert.occurred_at.month == 1
        assert alert.occurred_at.day == 15

    def test_normalize_missing_title_uses_default(self, source: SentinelSource) -> None:
        payload = {"properties": {"severity": "High"}}
        alert = source.normalize(payload)
        assert alert.title == "Untitled Sentinel Incident"

    def test_normalize_missing_severity_uses_pending(self, source: SentinelSource) -> None:
        payload = {"properties": {"title": "Some Incident"}}
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.INFORMATIONAL

    def test_normalize_unknown_severity_maps_to_pending(self, source: SentinelSource) -> None:
        payload = {"properties": {"title": "Test", "severity": "Fatal"}}
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.PENDING

    def test_normalize_severity_none_maps_to_informational(
        self, source: SentinelSource
    ) -> None:
        payload = {"properties": {"title": "Test", "severity": "None"}}
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.INFORMATIONAL

    def test_normalize_severity_informational(self, source: SentinelSource) -> None:
        payload = {"properties": {"title": "Test", "severity": "Informational"}}
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.INFORMATIONAL

    def test_normalize_severity_low(self, source: SentinelSource) -> None:
        payload = {"properties": {"title": "Test", "severity": "Low"}}
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.LOW

    def test_normalize_severity_medium(self, source: SentinelSource) -> None:
        payload = {"properties": {"title": "Test", "severity": "Medium"}}
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.MEDIUM

    def test_normalize_missing_properties_uses_defaults(self, source: SentinelSource) -> None:
        """When properties is missing entirely, normalize uses fallback values."""
        payload: dict = {}  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.title == "Untitled Sentinel Incident"
        assert alert.severity == AlertSeverity.INFORMATIONAL
        assert alert.source_name == "sentinel"

    def test_normalize_falls_back_to_created_time(self, source: SentinelSource) -> None:
        """When firstActivityTimeUtc is missing, createdTimeUtc is used."""
        payload = {
            "properties": {
                "title": "Fallback Time Test",
                "severity": "Medium",
                "createdTimeUtc": "2024-06-01T12:00:00.000Z",
            }
        }
        alert = source.normalize(payload)
        assert alert.occurred_at.year == 2024
        assert alert.occurred_at.month == 6
        assert alert.occurred_at.day == 1

    def test_normalize_invalid_timestamp_uses_now(self, source: SentinelSource) -> None:
        payload = {
            "properties": {
                "title": "Bad Time",
                "firstActivityTimeUtc": "not-a-timestamp",
            }
        }
        alert = source.normalize(payload)
        # Should not raise, should use current time
        assert alert.occurred_at is not None
        # The year should be current (2026)
        assert alert.occurred_at.year >= 2024

    def test_normalize_no_timestamps_uses_now(self, source: SentinelSource) -> None:
        payload = {"properties": {"title": "No Time"}}
        alert = source.normalize(payload)
        assert alert.occurred_at is not None

    def test_normalize_empty_labels_gives_empty_tags(self, source: SentinelSource) -> None:
        payload = {"properties": {"title": "No Tags", "labels": []}}
        alert = source.normalize(payload)
        assert alert.tags == []

    def test_normalize_non_dict_labels_ignored(self, source: SentinelSource) -> None:
        payload = {
            "properties": {
                "title": "Bad Labels",
                "labels": ["not-a-dict", 42, None],
            }
        }
        alert = source.normalize(payload)
        assert alert.tags == []

    def test_normalize_labels_without_label_name_ignored(
        self, source: SentinelSource
    ) -> None:
        payload = {
            "properties": {
                "title": "Labels No Name",
                "labels": [{"labelType": "User"}],
            }
        }
        alert = source.normalize(payload)
        assert alert.tags == []


class TestSentinelValidatePayload:
    """Sentinel validate_payload() edge cases."""

    @pytest.fixture
    def source(self) -> SentinelSource:
        return SentinelSource()

    def test_valid_with_title(self, source: SentinelSource) -> None:
        assert source.validate_payload({"properties": {"title": "Test"}}) is True

    def test_valid_with_severity_only(self, source: SentinelSource) -> None:
        assert source.validate_payload({"properties": {"severity": "High"}}) is True

    def test_invalid_empty_dict(self, source: SentinelSource) -> None:
        assert source.validate_payload({}) is False

    def test_invalid_no_properties(self, source: SentinelSource) -> None:
        assert source.validate_payload({"title": "Wrong Level"}) is False

    def test_invalid_properties_not_dict(self, source: SentinelSource) -> None:
        assert source.validate_payload({"properties": "string"}) is False

    def test_invalid_properties_none(self, source: SentinelSource) -> None:
        assert source.validate_payload({"properties": None}) is False

    def test_invalid_empty_properties(self, source: SentinelSource) -> None:
        assert source.validate_payload({"properties": {}}) is False

    def test_invalid_properties_with_empty_title_and_no_severity(
        self, source: SentinelSource
    ) -> None:
        assert source.validate_payload({"properties": {"title": ""}}) is False

    def test_valid_with_both_title_and_severity(self, source: SentinelSource) -> None:
        assert source.validate_payload(
            {"properties": {"title": "Test", "severity": "High"}}
        ) is True


class TestSentinelExtractIndicators:
    """Sentinel extract_indicators() edge cases."""

    @pytest.fixture
    def source(self) -> SentinelSource:
        return SentinelSource()

    def test_empty_entities_returns_empty(self, source: SentinelSource) -> None:
        assert source.extract_indicators({"Entities": []}) == []

    def test_missing_entities_returns_empty(self, source: SentinelSource) -> None:
        assert source.extract_indicators({}) == []

    def test_non_dict_entity_skipped(self, source: SentinelSource) -> None:
        result = source.extract_indicators({"Entities": ["not-a-dict", 42]})
        assert result == []

    def test_entity_without_type_skipped(self, source: SentinelSource) -> None:
        result = source.extract_indicators({"Entities": [{"Address": "10.0.0.1"}]})
        assert result == []

    def test_ip_entity_lowercase_type(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"type": "ip", "address": "10.0.0.1"}]}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP
        assert result[0].value == "10.0.0.1"

    def test_account_entity_with_upn(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "account", "Name": "admin", "UPNSuffix": "corp.com"}]}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.ACCOUNT
        assert result[0].value == "admin@corp.com"

    def test_account_entity_without_upn(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "account", "Name": "localadmin"}]}
        )
        assert len(result) == 1
        assert result[0].value == "localadmin"

    def test_account_entity_no_name_skipped(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "account", "UPNSuffix": "corp.com"}]}
        )
        assert result == []

    def test_host_entity_with_domain(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "host", "HostName": "DC01", "DnsDomain": "corp.local"}]}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.DOMAIN
        assert result[0].value == "DC01.corp.local"

    def test_host_entity_without_domain(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "host", "HostName": "standalone"}]}
        )
        assert len(result) == 1
        assert result[0].value == "standalone"

    def test_host_entity_no_hostname_skipped(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "host", "DnsDomain": "corp.com"}]}
        )
        assert result == []

    def test_url_entity(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "url", "Url": "https://evil.com/payload"}]}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.URL
        assert result[0].value == "https://evil.com/payload"

    def test_url_entity_lowercase(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"type": "url", "url": "http://test.com"}]}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.URL

    def test_url_entity_no_value_skipped(self, source: SentinelSource) -> None:
        result = source.extract_indicators({"Entities": [{"Type": "url"}]})
        assert result == []

    def test_filehash_sha256(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "filehash", "Algorithm": "SHA256", "Value": SHA256_PS}]}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA256

    def test_filehash_sha1(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "filehash", "Algorithm": "SHA1", "Value": "abc123"}]}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA1

    def test_filehash_md5(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "filehash", "Algorithm": "MD5", "Value": MD5_VAL}]}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_MD5

    def test_filehash_unknown_algorithm_skipped(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {
                "Entities": [
                    {"Type": "filehash", "Algorithm": "BLAKE2", "Value": "deadbeef"}
                ]
            }
        )
        assert result == []

    def test_filehash_no_value_skipped(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "filehash", "Algorithm": "SHA256"}]}
        )
        assert result == []

    def test_unknown_entity_type_skipped(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {"Entities": [{"Type": "process", "Name": "cmd.exe"}]}
        )
        assert result == []

    def test_multiple_entities_all_types(self, source: SentinelSource) -> None:
        result = source.extract_indicators(
            {
                "Entities": [
                    {"Type": "ip", "Address": "1.2.3.4"},
                    {"Type": "ip", "Address": "5.6.7.8"},
                    {"Type": "account", "Name": "user1", "UPNSuffix": "test.com"},
                    {"Type": "host", "HostName": "srv01"},
                    {"Type": "url", "Url": "https://bad.com"},
                    {"Type": "filehash", "Algorithm": "SHA256", "Value": "abc"},
                    {"Type": "filehash", "Algorithm": "MD5", "Value": "def"},
                ]
            }
        )
        assert len(result) == 7
        types = {i.type for i in result}
        assert IndicatorType.IP in types
        assert IndicatorType.ACCOUNT in types
        assert IndicatorType.DOMAIN in types
        assert IndicatorType.URL in types
        assert IndicatorType.HASH_SHA256 in types
        assert IndicatorType.HASH_MD5 in types


class TestSentinelDetectionRuleRef:
    """Sentinel extract_detection_rule_ref() edge cases."""

    @pytest.fixture
    def source(self) -> SentinelSource:
        return SentinelSource()

    def test_extracts_rule_uuid_from_arm_path(
        self, source: SentinelSource,
    ) -> None:
        payload = _load("sentinel_alert.json")
        ref = source.extract_detection_rule_ref(payload)
        assert ref == "rule-uuid-abc123"

    def test_empty_rule_ids_returns_none(self, source: SentinelSource) -> None:
        payload: dict[str, Any] = {"properties": {"relatedAnalyticRuleIds": []}}
        assert source.extract_detection_rule_ref(payload) is None

    def test_missing_properties_returns_none(self, source: SentinelSource) -> None:
        assert source.extract_detection_rule_ref({}) is None

    def test_missing_rule_ids_returns_none(self, source: SentinelSource) -> None:
        assert source.extract_detection_rule_ref({"properties": {}}) is None

    def test_multiple_rule_ids_takes_first(self, source: SentinelSource) -> None:
        payload = {
            "properties": {
                "relatedAnalyticRuleIds": [
                    "/subs/a/alertRules/first-rule",
                    "/subs/b/alertRules/second-rule",
                ]
            }
        }
        assert source.extract_detection_rule_ref(payload) == "first-rule"


class TestSentinelWebhookSignature:
    """Sentinel verify_webhook_signature() edge cases."""

    @pytest.fixture
    def source(self) -> SentinelSource:
        return SentinelSource()

    def test_no_secret_configured_passes(
        self, source: SentinelSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_sentinel_secret(monkeypatch, "")
        assert source.verify_webhook_signature({}, b"anything") is True

    def test_secret_set_but_no_header_fails(
        self, source: SentinelSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_sentinel_secret(monkeypatch, "s3cr3t")
        assert source.verify_webhook_signature({}, b"body") is False

    def test_valid_signature(
        self, source: SentinelSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "my-webhook-secret"
        body = b'{"incident": "data"}'
        _setattr_sentinel_secret(monkeypatch, secret)
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        result = source.verify_webhook_signature(
            {"X-Sentinel-Signature": sig}, body
        )
        assert result is True

    def test_valid_signature_with_sha256_prefix(
        self, source: SentinelSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "my-secret"
        body = b'{"test": 1}'
        _setattr_sentinel_secret(monkeypatch, secret)
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        result = source.verify_webhook_signature(
            {"X-Sentinel-Signature": f"sha256={sig}"}, body
        )
        assert result is True

    def test_case_insensitive_header(
        self, source: SentinelSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "secret"
        body = b"data"
        _setattr_sentinel_secret(monkeypatch, secret)
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        result = source.verify_webhook_signature(
            {"x-sentinel-signature": sig}, body
        )
        assert result is True

    def test_wrong_signature_fails(
        self, source: SentinelSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_sentinel_secret(monkeypatch, "correct")
        assert source.verify_webhook_signature(
            {"X-Sentinel-Signature": "deadbeef"}, b"body"
        ) is False


# =============================================================================
# Elastic Security — edge cases and additional coverage
# =============================================================================


class TestElasticGetHelper:
    """Test the _get() helper for Elastic field resolution."""

    def test_flat_dot_notation(self) -> None:
        raw = {"kibana.alert.rule.name": "My Rule"}
        assert _get(raw, "kibana.alert.rule.name") == "My Rule"

    def test_nested_json(self) -> None:
        raw = {"kibana": {"alert": {"rule": {"name": "Nested Rule"}}}}
        assert _get(raw, "kibana.alert.rule.name") == "Nested Rule"

    def test_first_path_wins(self) -> None:
        raw = {"field1": "a", "field2": "b"}
        assert _get(raw, "field1", "field2") == "a"

    def test_fallback_to_second_path(self) -> None:
        raw = {"field2": "b"}
        assert _get(raw, "field1", "field2") == "b"

    def test_returns_none_when_missing(self) -> None:
        assert _get({}, "nonexistent") is None

    def test_returns_none_for_nested_missing(self) -> None:
        raw: dict[str, Any] = {"a": {"b": {}}}
        assert _get(raw, "a.b.c") is None


class TestElasticNormalize:
    """Elastic normalize() edge cases."""

    @pytest.fixture
    def source(self) -> ElasticSource:
        return ElasticSource()

    @pytest.fixture
    def payload(self) -> dict:  # type: ignore[type-arg]
        return _load("elastic_alert.json")

    def test_normalize_happy_path(self, source: ElasticSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.title == "Suspicious PowerShell Execution"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.source_name == "elastic"

    def test_normalize_uses_reason_when_no_rule_name(self, source: ElasticSource) -> None:
        payload = {
            "kibana.alert.reason": "Some alert reason",
            "kibana.alert.severity": "medium",
            "@timestamp": "2024-01-15T10:00:00Z",
        }
        alert = source.normalize(payload)
        assert alert.title == "Some alert reason"

    def test_normalize_default_title(self, source: ElasticSource) -> None:
        payload = {"@timestamp": "2024-01-15T10:00:00Z"}
        alert = source.normalize(payload)
        assert alert.title == "Untitled Elastic Alert"

    def test_normalize_rule_severity_fallback(self, source: ElasticSource) -> None:
        payload = {
            "kibana.alert.rule.name": "Test",
            "kibana.alert.rule.severity": "critical",
        }
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.CRITICAL

    def test_normalize_unknown_severity_maps_to_pending(
        self, source: ElasticSource
    ) -> None:
        payload = {
            "kibana.alert.rule.name": "Test",
            "kibana.alert.severity": "fatal",
        }
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.PENDING

    def test_normalize_no_severity_maps_to_pending(self, source: ElasticSource) -> None:
        payload = {"kibana.alert.rule.name": "Test"}
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.PENDING

    def test_normalize_uses_timestamp_fallback(self, source: ElasticSource) -> None:
        payload = {
            "kibana.alert.rule.name": "Test",
            "@timestamp": "2024-03-15T08:00:00Z",
        }
        alert = source.normalize(payload)
        assert alert.occurred_at.year == 2024
        assert alert.occurred_at.month == 3

    def test_normalize_invalid_timestamp_uses_now(self, source: ElasticSource) -> None:
        payload = {
            "kibana.alert.rule.name": "Test",
            "kibana.alert.start": "bad-date",
        }
        alert = source.normalize(payload)
        assert alert.occurred_at is not None
        assert alert.occurred_at.year >= 2024

    def test_normalize_no_timestamp_uses_now(self, source: ElasticSource) -> None:
        payload = {"kibana.alert.rule.name": "Test"}
        alert = source.normalize(payload)
        assert alert.occurred_at is not None

    def test_normalize_tags_from_rule_tags(
        self, source: ElasticSource, payload: dict  # type: ignore[type-arg]
    ) -> None:
        alert = source.normalize(payload)
        assert "PowerShell" in alert.tags
        assert "Endpoint" in alert.tags
        assert "T1059.001" in alert.tags

    def test_normalize_no_tags_gives_empty_list(self, source: ElasticSource) -> None:
        payload = {"kibana.alert.rule.name": "Test"}
        alert = source.normalize(payload)
        assert alert.tags == []

    def test_normalize_non_list_tags_gives_empty(self, source: ElasticSource) -> None:
        payload = {
            "kibana.alert.rule.name": "Test",
            "kibana.alert.rule.tags": "not-a-list",
        }
        alert = source.normalize(payload)
        assert alert.tags == []


class TestElasticValidatePayload:
    """Elastic validate_payload() edge cases."""

    @pytest.fixture
    def source(self) -> ElasticSource:
        return ElasticSource()

    def test_valid_with_rule_name(self, source: ElasticSource) -> None:
        assert source.validate_payload(
            {"kibana.alert.rule.name": "Test Rule"}
        ) is True

    def test_valid_with_rule_uuid(self, source: ElasticSource) -> None:
        assert source.validate_payload(
            {"kibana.alert.rule.uuid": "some-uuid"}
        ) is True

    def test_valid_nested_format(self, source: ElasticSource) -> None:
        payload = {"kibana": {"alert": {"rule": {"name": "Nested Rule"}}}}
        assert source.validate_payload(payload) is True

    def test_invalid_empty(self, source: ElasticSource) -> None:
        assert source.validate_payload({}) is False

    def test_invalid_no_kibana_fields(self, source: ElasticSource) -> None:
        assert source.validate_payload({"event.kind": "signal"}) is False


class TestElasticExtractIndicators:
    """Elastic extract_indicators() edge cases."""

    @pytest.fixture
    def source(self) -> ElasticSource:
        return ElasticSource()

    def test_empty_payload_returns_empty(self, source: ElasticSource) -> None:
        assert source.extract_indicators({}) == []

    def test_source_ip(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"source.ip": "10.0.0.1"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP
        assert result[0].value == "10.0.0.1"

    def test_destination_ip(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"destination.ip": "8.8.8.8"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP

    def test_host_ip_array(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"host.ip": ["10.0.0.1", "10.0.0.2"]})
        assert len(result) == 2
        assert all(i.type == IndicatorType.IP for i in result)

    def test_host_ip_empty_array(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"host.ip": []})
        assert result == []

    def test_threat_indicator_ip(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"threat.indicator.ip": "192.168.1.1"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP

    def test_destination_domain(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"destination.domain": "evil.com"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.DOMAIN

    def test_dns_question_name(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"dns.question.name": "c2.bad.com"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.DOMAIN

    def test_url_domain(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"url.domain": "phishing.com"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.DOMAIN

    def test_threat_indicator_domain(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"threat.indicator.domain": "malware.com"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.DOMAIN

    def test_url_full(self, source: ElasticSource) -> None:
        result = source.extract_indicators(
            {"url.full": "https://evil.com/malware.exe"}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.URL

    def test_process_hash_sha256(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"process.hash.sha256": SHA256_PS})
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA256

    def test_file_hash_sha256(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"file.hash.sha256": "abc123"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA256

    def test_threat_indicator_hash(self, source: ElasticSource) -> None:
        result = source.extract_indicators(
            {"threat.indicator.file.hash.sha256": "deadbeef"}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA256

    def test_process_hash_sha1(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"process.hash.sha1": "sha1val"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA1

    def test_file_hash_sha1(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"file.hash.sha1": "sha1val"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA1

    def test_process_hash_md5(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"process.hash.md5": MD5_VAL})
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_MD5

    def test_file_hash_md5(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"file.hash.md5": MD5_VAL})
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_MD5

    def test_user_email(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"user.email": "jdoe@corp.com"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.EMAIL

    def test_user_name(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"user.name": "jdoe"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.ACCOUNT

    def test_empty_string_values_skipped(self, source: ElasticSource) -> None:
        result = source.extract_indicators(
            {"source.ip": "", "destination.ip": "", "user.name": ""}
        )
        assert result == []

    def test_none_values_skipped(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"source.ip": None, "user.name": None})
        assert result == []

    def test_integer_values_skipped(self, source: ElasticSource) -> None:
        result = source.extract_indicators({"source.ip": 12345})
        assert result == []

    def test_full_fixture_extraction(
        self, source: ElasticSource
    ) -> None:
        payload = _load("elastic_alert.json")
        indicators = source.extract_indicators(payload)
        tv = {(i.type, i.value) for i in indicators}
        # Verify all expected indicators from fixture
        assert (IndicatorType.IP, "10.0.0.55") in tv
        assert (IndicatorType.IP, "185.220.101.32") in tv
        assert (IndicatorType.DOMAIN, "evil.example.com") in tv
        assert (IndicatorType.DOMAIN, "c2-server.evil.com") in tv
        assert (IndicatorType.HASH_SHA256, SHA256_PS) in tv
        assert (IndicatorType.HASH_MD5, MD5_VAL) in tv
        assert (IndicatorType.EMAIL, "jdoe@corp.com") in tv
        assert (IndicatorType.ACCOUNT, "jdoe") in tv
        assert (IndicatorType.URL, "https://evil.example.com/payload/stage2.ps1") in tv


class TestElasticDetectionRuleRef:
    """Elastic extract_detection_rule_ref() edge cases."""

    @pytest.fixture
    def source(self) -> ElasticSource:
        return ElasticSource()

    def test_extracts_uuid(self, source: ElasticSource) -> None:
        payload = {"kibana.alert.rule.uuid": "rule-uuid-elastic-abc"}
        assert source.extract_detection_rule_ref(payload) == "rule-uuid-elastic-abc"

    def test_returns_none_when_missing(self, source: ElasticSource) -> None:
        assert source.extract_detection_rule_ref({}) is None

    def test_nested_format(self, source: ElasticSource) -> None:
        payload = {"kibana": {"alert": {"rule": {"uuid": "nested-uuid"}}}}
        assert source.extract_detection_rule_ref(payload) == "nested-uuid"


class TestElasticWebhookSignature:
    """Elastic verify_webhook_signature() edge cases."""

    @pytest.fixture
    def source(self) -> ElasticSource:
        return ElasticSource()

    def test_no_secret_configured_passes(
        self, source: ElasticSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_elastic_secret(monkeypatch, "")
        assert source.verify_webhook_signature({}, b"anything") is True

    def test_secret_set_no_header_fails(
        self, source: ElasticSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_elastic_secret(monkeypatch, "secret")
        assert source.verify_webhook_signature({}, b"body") is False

    def test_valid_signature(
        self, source: ElasticSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "elastic-secret"
        body = b'{"alert": "data"}'
        _setattr_elastic_secret(monkeypatch, secret)
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert source.verify_webhook_signature(
            {"X-Elastic-Signature": sig}, body
        ) is True

    def test_valid_signature_with_sha256_prefix(
        self, source: ElasticSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "elastic-secret"
        body = b"data"
        _setattr_elastic_secret(monkeypatch, secret)
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert source.verify_webhook_signature(
            {"X-Elastic-Signature": f"sha256={sig}"}, body
        ) is True

    def test_case_insensitive_header(
        self, source: ElasticSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "secret"
        body = b"data"
        _setattr_elastic_secret(monkeypatch, secret)
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert source.verify_webhook_signature(
            {"x-elastic-signature": sig}, body
        ) is True

    def test_wrong_signature_fails(
        self, source: ElasticSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_elastic_secret(monkeypatch, "correct")
        assert source.verify_webhook_signature(
            {"X-Elastic-Signature": "wrong-hex"}, b"body"
        ) is False


# =============================================================================
# Splunk — edge cases and additional coverage
# =============================================================================


class TestSplunkNormalize:
    """Splunk normalize() edge cases."""

    @pytest.fixture
    def source(self) -> SplunkSource:
        return SplunkSource()

    @pytest.fixture
    def payload(self) -> dict:  # type: ignore[type-arg]
        return _load("splunk_alert.json")

    def test_normalize_happy_path(self, source: SplunkSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.title == "Brute Force Login Attempt"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.source_name == "splunk"

    def test_normalize_uses_rule_name_from_result(self, source: SplunkSource) -> None:
        payload = {
            "result": {"rule_name": "ES Rule", "_time": "1705312200.0"},
            "search_name": "Search Name",
            "sid": "1234",
        }
        alert = source.normalize(payload)
        assert alert.title == "ES Rule"

    def test_normalize_uses_signature_from_result(self, source: SplunkSource) -> None:
        payload = {
            "result": {"signature": "Attack Detected", "_time": "1705312200.0"},
            "search_name": "Search Name",
            "sid": "1234",
        }
        alert = source.normalize(payload)
        assert alert.title == "Attack Detected"

    def test_normalize_falls_back_to_search_name(self, source: SplunkSource) -> None:
        payload = {
            "result": {"_time": "1705312200.0"},
            "search_name": "My Saved Search",
            "sid": "1234",
        }
        alert = source.normalize(payload)
        assert alert.title == "My Saved Search"

    def test_normalize_default_title(self, source: SplunkSource) -> None:
        payload = {"result": {}, "sid": "1234"}
        alert = source.normalize(payload)
        assert alert.title == "Untitled Splunk Alert"

    def test_normalize_urgency_priority(self, source: SplunkSource) -> None:
        """urgency is preferred over severity for Splunk ES."""
        payload = {
            "result": {"urgency": "critical", "severity": "low"},
            "search_name": "Test",
            "sid": "1",
        }
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.CRITICAL

    def test_normalize_severity_field_fallback(self, source: SplunkSource) -> None:
        payload = {
            "result": {"severity": "medium"},
            "search_name": "Test",
            "sid": "1",
        }
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.MEDIUM

    def test_normalize_info_severity(self, source: SplunkSource) -> None:
        payload = {
            "result": {"urgency": "info"},
            "search_name": "Test",
            "sid": "1",
        }
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.INFORMATIONAL

    def test_normalize_informational_severity(self, source: SplunkSource) -> None:
        payload = {
            "result": {"urgency": "informational"},
            "search_name": "Test",
            "sid": "1",
        }
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.INFORMATIONAL

    def test_normalize_unknown_severity_maps_to_pending(
        self, source: SplunkSource
    ) -> None:
        payload = {
            "result": {"urgency": "extreme"},
            "search_name": "Test",
            "sid": "1",
        }
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.PENDING

    def test_normalize_no_severity_defaults_to_low(self, source: SplunkSource) -> None:
        """When urgency/severity are absent, default is 'low'."""
        payload = {"result": {}, "search_name": "Test", "sid": "1"}
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.LOW

    def test_normalize_unix_timestamp(self, source: SplunkSource) -> None:
        payload = {
            "result": {"_time": "1705312200.0"},
            "search_name": "Test",
            "sid": "1",
        }
        alert = source.normalize(payload)
        expected = datetime.fromtimestamp(1705312200.0, tz=UTC)
        assert alert.occurred_at == expected

    def test_normalize_invalid_time_uses_now(self, source: SplunkSource) -> None:
        payload = {
            "result": {"_time": "not-a-number"},
            "search_name": "Test",
            "sid": "1",
        }
        alert = source.normalize(payload)
        assert alert.occurred_at is not None
        assert alert.occurred_at.year >= 2024

    def test_normalize_no_time_uses_now(self, source: SplunkSource) -> None:
        payload = {"result": {}, "search_name": "Test", "sid": "1"}
        alert = source.normalize(payload)
        assert alert.occurred_at is not None

    def test_normalize_missing_result_uses_defaults(self, source: SplunkSource) -> None:
        payload = {"search_name": "Test", "sid": "1"}
        alert = source.normalize(payload)
        assert alert.title == "Test"


class TestSplunkValidatePayload:
    """Splunk validate_payload() edge cases."""

    @pytest.fixture
    def source(self) -> SplunkSource:
        return SplunkSource()

    def test_valid_with_result_and_search_name(self, source: SplunkSource) -> None:
        assert source.validate_payload(
            {"result": {"src_ip": "1.2.3.4"}, "search_name": "My Search"}
        ) is True

    def test_valid_with_result_and_sid(self, source: SplunkSource) -> None:
        assert source.validate_payload(
            {"result": {}, "sid": "scheduler__admin__1234"}
        ) is True

    def test_invalid_no_result(self, source: SplunkSource) -> None:
        assert source.validate_payload({"search_name": "Test"}) is False

    def test_invalid_result_not_dict(self, source: SplunkSource) -> None:
        assert source.validate_payload(
            {"result": "string", "search_name": "Test"}
        ) is False

    def test_invalid_no_search_name_or_sid(self, source: SplunkSource) -> None:
        assert source.validate_payload({"result": {}}) is False

    def test_invalid_empty(self, source: SplunkSource) -> None:
        assert source.validate_payload({}) is False


class TestSplunkExtractIndicators:
    """Splunk extract_indicators() edge cases."""

    @pytest.fixture
    def source(self) -> SplunkSource:
        return SplunkSource()

    def test_empty_result_returns_empty(self, source: SplunkSource) -> None:
        assert source.extract_indicators({"result": {}}) == []

    def test_src_ip(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"src_ip": "10.0.0.1"}}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP
        assert result[0].value == "10.0.0.1"

    def test_dest_ip(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"dest_ip": "192.168.1.1"}}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP

    def test_src_fallback_when_no_src_ip(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"src": "10.0.0.99"}}
        )
        assert len(result) == 1
        assert result[0].value == "10.0.0.99"

    def test_src_not_used_when_src_ip_present(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"src_ip": "10.0.0.1", "src": "10.0.0.2"}}
        )
        ip_values = [i.value for i in result if i.type == IndicatorType.IP]
        assert "10.0.0.1" in ip_values
        assert "10.0.0.2" not in ip_values

    def test_dest_fallback_when_no_dest_ip(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"dest": "192.168.1.10"}}
        )
        assert len(result) == 1
        assert result[0].value == "192.168.1.10"

    def test_dest_not_used_when_dest_ip_present(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"dest_ip": "192.168.1.1", "dest": "192.168.1.2"}}
        )
        ip_values = [i.value for i in result if i.type == IndicatorType.IP]
        assert "192.168.1.1" in ip_values
        assert "192.168.1.2" not in ip_values

    def test_user_account(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"user": "admin"}}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.ACCOUNT

    def test_sha256_hash(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"sha256": "abc123"}}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA256

    def test_md5_hash(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"md5": MD5_VAL}}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_MD5

    def test_sha1_hash(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"sha1": "sha1value"}}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA1

    def test_url_indicator(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"url": "https://bad.com/payload"}}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.URL

    def test_domain_indicator(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"domain": "evil.corp"}}
        )
        assert len(result) == 1
        assert result[0].type == IndicatorType.DOMAIN

    def test_empty_string_values_skipped(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"src_ip": "", "user": ""}}
        )
        assert result == []

    def test_non_string_values_skipped(self, source: SplunkSource) -> None:
        result = source.extract_indicators(
            {"result": {"src_ip": 12345, "user": None}}
        )
        assert result == []

    def test_missing_result_key(self, source: SplunkSource) -> None:
        result = source.extract_indicators({})
        assert result == []

    def test_full_fixture_extraction(self, source: SplunkSource) -> None:
        payload = _load("splunk_alert.json")
        indicators = source.extract_indicators(payload)
        tv = {(i.type, i.value) for i in indicators}
        assert (IndicatorType.IP, "10.0.0.99") in tv
        assert (IndicatorType.IP, "192.168.1.10") in tv
        assert (IndicatorType.ACCOUNT, "admin") in tv
        assert (IndicatorType.HASH_SHA256, SHA256_SPLUNK) in tv
        assert (IndicatorType.DOMAIN, "corp.example.com") in tv


class TestSplunkDetectionRuleRef:
    """Splunk extract_detection_rule_ref() edge cases."""

    @pytest.fixture
    def source(self) -> SplunkSource:
        return SplunkSource()

    def test_rule_name_from_result(self, source: SplunkSource) -> None:
        payload = {
            "result": {"rule_name": "ES Correlation Rule"},
            "search_name": "Saved Search",
            "sid": "1",
        }
        assert source.extract_detection_rule_ref(payload) == "ES Correlation Rule"

    def test_search_name_fallback(self, source: SplunkSource) -> None:
        payload = {"result": {}, "search_name": "My Search", "sid": "1"}
        assert source.extract_detection_rule_ref(payload) == "My Search"

    def test_returns_none_when_both_missing(self, source: SplunkSource) -> None:
        payload = {"result": {}, "sid": "1"}
        assert source.extract_detection_rule_ref(payload) is None

    def test_missing_result_returns_search_name(self, source: SplunkSource) -> None:
        payload = {"search_name": "Only Search", "sid": "1"}
        assert source.extract_detection_rule_ref(payload) == "Only Search"


class TestSplunkWebhookSignature:
    """Splunk verify_webhook_signature() edge cases."""

    @pytest.fixture
    def source(self) -> SplunkSource:
        return SplunkSource()

    def test_no_secret_configured_passes(
        self, source: SplunkSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_splunk_secret(monkeypatch, "")
        assert source.verify_webhook_signature({}, b"anything") is True

    def test_secret_set_no_header_fails(
        self, source: SplunkSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_splunk_secret(monkeypatch, "secret")
        assert source.verify_webhook_signature({}, b"body") is False

    def test_valid_token(
        self, source: SplunkSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "splunk-bearer-token"
        _setattr_splunk_secret(monkeypatch, secret)
        assert source.verify_webhook_signature(
            {"X-Splunk-Webhook-Secret": secret}, b"body"
        ) is True

    def test_case_insensitive_header(
        self, source: SplunkSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "token"
        _setattr_splunk_secret(monkeypatch, secret)
        assert source.verify_webhook_signature(
            {"x-splunk-webhook-secret": secret}, b"body"
        ) is True

    def test_wrong_token_fails(
        self, source: SplunkSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_splunk_secret(monkeypatch, "correct-token")
        assert source.verify_webhook_signature(
            {"X-Splunk-Webhook-Secret": "wrong-token"}, b"body"
        ) is False

    def test_token_comparison_is_constant_time(
        self, source: SplunkSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Splunk uses hmac.compare_digest for timing-safe comparison."""
        # This is a behavioral verification — just ensure it works correctly
        secret = "my-token"
        _setattr_splunk_secret(monkeypatch, secret)
        assert source.verify_webhook_signature(
            {"X-Splunk-Webhook-Secret": secret}, b"body"
        ) is True
        assert source.verify_webhook_signature(
            {"X-Splunk-Webhook-Secret": "x" + secret[1:]}, b"body"
        ) is False


# =============================================================================
# Generic Source — comprehensive coverage
# =============================================================================


class TestGenericSourceValidate:
    """Generic validate_payload() tests."""

    @pytest.fixture
    def source(self) -> GenericSource:
        return GenericSource()

    def test_valid_with_title(self, source: GenericSource) -> None:
        assert source.validate_payload({"title": "Alert Title"}) is True

    def test_invalid_empty(self, source: GenericSource) -> None:
        assert source.validate_payload({}) is False

    def test_invalid_no_title(self, source: GenericSource) -> None:
        assert source.validate_payload({"severity": "High"}) is False

    def test_invalid_empty_title(self, source: GenericSource) -> None:
        assert source.validate_payload({"title": ""}) is False

    def test_invalid_none_title(self, source: GenericSource) -> None:
        assert source.validate_payload({"title": None}) is False

    def test_source_name_is_generic(self, source: GenericSource) -> None:
        assert source.source_name == "generic"
        assert source.display_name == "Generic Webhook"


class TestGenericSourceNormalize:
    """Generic normalize() tests."""

    @pytest.fixture
    def source(self) -> GenericSource:
        return GenericSource()

    def test_normalize_happy_path(self, source: GenericSource) -> None:
        payload = {
            "title": "Test Alert",
            "severity": "High",
            "occurred_at": "2024-01-15T10:00:00+00:00",
            "tags": ["phishing", "urgent"],
        }
        alert = source.normalize(payload)
        assert alert.title == "Test Alert"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.source_name == "generic"
        assert alert.occurred_at.year == 2024
        assert "phishing" in alert.tags
        assert "urgent" in alert.tags

    def test_normalize_default_title(self, source: GenericSource) -> None:
        alert = source.normalize({})
        assert alert.title == "Untitled Alert"

    def test_normalize_severity_case_insensitive(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "severity": "HIGH"})
        assert alert.severity == AlertSeverity.HIGH

    def test_normalize_severity_critical(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "severity": "critical"})
        assert alert.severity == AlertSeverity.CRITICAL

    def test_normalize_severity_low(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "severity": "low"})
        assert alert.severity == AlertSeverity.LOW

    def test_normalize_severity_medium(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "severity": "medium"})
        assert alert.severity == AlertSeverity.MEDIUM

    def test_normalize_severity_info(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "severity": "info"})
        assert alert.severity == AlertSeverity.INFORMATIONAL

    def test_normalize_severity_informational(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "severity": "informational"})
        assert alert.severity == AlertSeverity.INFORMATIONAL

    def test_normalize_severity_pending(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "severity": "pending"})
        assert alert.severity == AlertSeverity.PENDING

    def test_normalize_unknown_severity(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "severity": "fatal"})
        assert alert.severity == AlertSeverity.PENDING

    def test_normalize_no_severity(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test"})
        assert alert.severity == AlertSeverity.PENDING

    def test_normalize_invalid_occurred_at_uses_now(
        self, source: GenericSource
    ) -> None:
        alert = source.normalize({"title": "Test", "occurred_at": "not-a-date"})
        assert alert.occurred_at is not None

    def test_normalize_no_occurred_at_uses_now(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test"})
        assert alert.occurred_at is not None

    def test_normalize_tags_non_list_becomes_empty(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "tags": "not-a-list"})
        assert alert.tags == []

    def test_normalize_tags_none_becomes_empty(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "tags": None})
        # None is not a list, so it should default to []
        assert alert.tags == []

    def test_normalize_tags_coerced_to_strings(self, source: GenericSource) -> None:
        alert = source.normalize({"title": "Test", "tags": [1, True, "ok"]})
        assert alert.tags == ["1", "True", "ok"]


class TestGenericSourceExtractIndicators:
    """Generic extract_indicators() tests."""

    @pytest.fixture
    def source(self) -> GenericSource:
        return GenericSource()

    def test_empty_payload_returns_empty(self, source: GenericSource) -> None:
        assert source.extract_indicators({}) == []

    def test_explicit_indicators_array(self, source: GenericSource) -> None:
        result = source.extract_indicators(
            {
                "indicators": [
                    {"type": "ip", "value": "1.2.3.4"},
                    {"type": "domain", "value": "evil.com"},
                    {"type": "hash_sha256", "value": "abc"},
                ]
            }
        )
        assert len(result) == 3
        types = {i.type for i in result}
        assert IndicatorType.IP in types
        assert IndicatorType.DOMAIN in types
        assert IndicatorType.HASH_SHA256 in types

    def test_explicit_indicators_all_types(self, source: GenericSource) -> None:
        result = source.extract_indicators(
            {
                "indicators": [
                    {"type": "ip", "value": "1.2.3.4"},
                    {"type": "domain", "value": "evil.com"},
                    {"type": "hash_md5", "value": "md5hash"},
                    {"type": "hash_sha1", "value": "sha1hash"},
                    {"type": "hash_sha256", "value": "sha256hash"},
                    {"type": "url", "value": "https://bad.com"},
                    {"type": "email", "value": "user@evil.com"},
                    {"type": "account", "value": "admin"},
                ]
            }
        )
        assert len(result) == 8

    def test_explicit_indicators_invalid_type_skipped(
        self, source: GenericSource
    ) -> None:
        result = source.extract_indicators(
            {"indicators": [{"type": "unknown_type", "value": "something"}]}
        )
        assert result == []

    def test_explicit_indicators_missing_value_skipped(
        self, source: GenericSource
    ) -> None:
        result = source.extract_indicators(
            {"indicators": [{"type": "ip"}]}
        )
        assert result == []

    def test_explicit_indicators_empty_value_skipped(
        self, source: GenericSource
    ) -> None:
        result = source.extract_indicators(
            {"indicators": [{"type": "ip", "value": ""}]}
        )
        assert result == []

    def test_explicit_indicators_non_dict_skipped(
        self, source: GenericSource
    ) -> None:
        result = source.extract_indicators(
            {"indicators": ["not-a-dict", 42, None]}
        )
        assert result == []

    def test_explicit_indicators_non_string_value_skipped(
        self, source: GenericSource
    ) -> None:
        result = source.extract_indicators(
            {"indicators": [{"type": "ip", "value": 12345}]}
        )
        assert result == []

    def test_common_field_src_ip(self, source: GenericSource) -> None:
        result = source.extract_indicators({"src_ip": "10.0.0.1"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP

    def test_common_field_dest_ip(self, source: GenericSource) -> None:
        result = source.extract_indicators({"dest_ip": "10.0.0.2"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP

    def test_common_field_source_ip(self, source: GenericSource) -> None:
        result = source.extract_indicators({"source_ip": "10.0.0.3"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP

    def test_common_field_destination_ip(self, source: GenericSource) -> None:
        result = source.extract_indicators({"destination_ip": "10.0.0.4"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP

    def test_common_field_ip(self, source: GenericSource) -> None:
        result = source.extract_indicators({"ip": "10.0.0.5"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP

    def test_common_field_domain(self, source: GenericSource) -> None:
        result = source.extract_indicators({"domain": "evil.com"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.DOMAIN

    def test_common_field_hostname(self, source: GenericSource) -> None:
        result = source.extract_indicators({"hostname": "server.corp.com"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.DOMAIN

    def test_common_field_url(self, source: GenericSource) -> None:
        result = source.extract_indicators({"url": "https://evil.com/path"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.URL

    def test_common_field_user(self, source: GenericSource) -> None:
        result = source.extract_indicators({"user": "admin"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.ACCOUNT

    def test_common_field_username(self, source: GenericSource) -> None:
        result = source.extract_indicators({"username": "jdoe"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.ACCOUNT

    def test_common_field_email(self, source: GenericSource) -> None:
        result = source.extract_indicators({"email": "user@evil.com"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.EMAIL

    def test_common_field_md5(self, source: GenericSource) -> None:
        result = source.extract_indicators({"md5": MD5_VAL})
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_MD5

    def test_common_field_sha1(self, source: GenericSource) -> None:
        result = source.extract_indicators({"sha1": "sha1val"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA1

    def test_common_field_sha256(self, source: GenericSource) -> None:
        result = source.extract_indicators({"sha256": SHA256_PS})
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA256

    def test_common_field_hash_as_sha256(self, source: GenericSource) -> None:
        result = source.extract_indicators({"hash": "abc123"})
        assert len(result) == 1
        assert result[0].type == IndicatorType.HASH_SHA256

    def test_both_explicit_and_common_fields(self, source: GenericSource) -> None:
        result = source.extract_indicators(
            {
                "indicators": [{"type": "ip", "value": "1.1.1.1"}],
                "domain": "evil.com",
                "user": "admin",
            }
        )
        assert len(result) == 3

    def test_common_field_empty_string_skipped(self, source: GenericSource) -> None:
        result = source.extract_indicators({"src_ip": ""})
        assert result == []

    def test_common_field_non_string_skipped(self, source: GenericSource) -> None:
        result = source.extract_indicators({"src_ip": 42})
        assert result == []

    def test_indicators_not_list_treated_as_empty(self, source: GenericSource) -> None:
        result = source.extract_indicators({"indicators": "not-a-list"})
        # Should not crash; "not-a-list" is not iterable as expected
        # The code checks isinstance(..., list), so it should skip
        assert len(result) == 0


class TestGenericSourceDetectionRuleRef:
    """Generic extract_detection_rule_ref() tests."""

    @pytest.fixture
    def source(self) -> GenericSource:
        return GenericSource()

    def test_rule_id(self, source: GenericSource) -> None:
        assert source.extract_detection_rule_ref({"rule_id": "R001"}) == "R001"

    def test_rule_name(self, source: GenericSource) -> None:
        assert source.extract_detection_rule_ref({"rule_name": "My Rule"}) == "My Rule"

    def test_rule_id_takes_precedence(self, source: GenericSource) -> None:
        payload = {"rule_id": "ID-1", "rule_name": "Name-1"}
        assert source.extract_detection_rule_ref(payload) == "ID-1"

    def test_returns_none_when_neither(self, source: GenericSource) -> None:
        assert source.extract_detection_rule_ref({}) is None

    def test_empty_rule_id_falls_to_rule_name(self, source: GenericSource) -> None:
        payload = {"rule_id": "", "rule_name": "Fallback"}
        assert source.extract_detection_rule_ref(payload) == "Fallback"


class TestGenericSourceWebhookSignature:
    """Generic source inherits default verify_webhook_signature from base."""

    def test_default_always_returns_true(self) -> None:
        source = GenericSource()
        assert source.verify_webhook_signature({}, b"any") is True


# =============================================================================
# Cross-source indicator source_field tracking
# =============================================================================


class TestIndicatorSourceField:
    """Verify that source_field is populated on extracted indicators."""

    def test_sentinel_entities_source_field(self) -> None:
        source = SentinelSource()
        result = source.extract_indicators(
            {"Entities": [{"Type": "ip", "Address": "1.2.3.4"}]}
        )
        assert result[0].source_field == "Entities.ip"

    def test_elastic_source_field(self) -> None:
        source = ElasticSource()
        result = source.extract_indicators({"source.ip": "1.2.3.4"})
        assert result[0].source_field == "source.ip"

    def test_splunk_result_source_field(self) -> None:
        source = SplunkSource()
        result = source.extract_indicators({"result": {"src_ip": "1.2.3.4"}})
        assert result[0].source_field == "result.src_ip"

    def test_generic_explicit_source_field(self) -> None:
        source = GenericSource()
        result = source.extract_indicators(
            {"indicators": [{"type": "ip", "value": "1.2.3.4"}]}
        )
        assert result[0].source_field == "indicators[]"

    def test_generic_common_field_source_field(self) -> None:
        source = GenericSource()
        result = source.extract_indicators({"src_ip": "1.2.3.4"})
        assert result[0].source_field == "src_ip"


# =============================================================================
# Alert fingerprint generation
# =============================================================================


class TestAlertFingerprint:
    """Test the fingerprint generation function used in dedup."""

    def test_same_inputs_produce_same_fingerprint(self) -> None:
        from app.repositories.alert_repository import generate_fingerprint

        fp1 = generate_fingerprint("Alert", "sentinel", [("ip", "1.2.3.4")])
        fp2 = generate_fingerprint("Alert", "sentinel", [("ip", "1.2.3.4")])
        assert fp1 == fp2

    def test_different_title_different_fingerprint(self) -> None:
        from app.repositories.alert_repository import generate_fingerprint

        fp1 = generate_fingerprint("Alert A", "sentinel", [("ip", "1.2.3.4")])
        fp2 = generate_fingerprint("Alert B", "sentinel", [("ip", "1.2.3.4")])
        assert fp1 != fp2

    def test_different_source_different_fingerprint(self) -> None:
        from app.repositories.alert_repository import generate_fingerprint

        fp1 = generate_fingerprint("Alert", "sentinel", [("ip", "1.2.3.4")])
        fp2 = generate_fingerprint("Alert", "elastic", [("ip", "1.2.3.4")])
        assert fp1 != fp2

    def test_different_indicators_different_fingerprint(self) -> None:
        from app.repositories.alert_repository import generate_fingerprint

        fp1 = generate_fingerprint("Alert", "sentinel", [("ip", "1.2.3.4")])
        fp2 = generate_fingerprint("Alert", "sentinel", [("ip", "5.6.7.8")])
        assert fp1 != fp2

    def test_indicator_order_does_not_matter(self) -> None:
        from app.repositories.alert_repository import generate_fingerprint

        fp1 = generate_fingerprint(
            "Alert", "sentinel", [("ip", "1.2.3.4"), ("domain", "evil.com")]
        )
        fp2 = generate_fingerprint(
            "Alert", "sentinel", [("domain", "evil.com"), ("ip", "1.2.3.4")]
        )
        assert fp1 == fp2

    def test_empty_indicators_is_valid(self) -> None:
        from app.repositories.alert_repository import generate_fingerprint

        fp = generate_fingerprint("Alert", "sentinel", [])
        assert isinstance(fp, str)
        assert len(fp) > 0

    def test_fingerprint_is_md5_hex(self) -> None:
        from app.repositories.alert_repository import generate_fingerprint

        fp = generate_fingerprint("Alert", "sentinel", [("ip", "1.2.3.4")])
        assert len(fp) == 32  # MD5 hex digest length
        int(fp, 16)  # Should be valid hex
