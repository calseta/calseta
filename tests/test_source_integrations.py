"""Tests for Sentinel, Elastic, and Splunk source integrations."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.integrations.sources.elastic import ElasticSource
from app.integrations.sources.sentinel import SentinelSource
from app.integrations.sources.splunk import SplunkSource
from app.schemas.alert import AlertSeverity
from app.schemas.indicators import IndicatorType

FIXTURES = Path(__file__).parent / "fixtures"

# Shared hash values used across tests (long strings extracted for readability)
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


# ---------------------------------------------------------------------------
# Microsoft Sentinel
# ---------------------------------------------------------------------------

class TestSentinelSource:
    @pytest.fixture
    def source(self) -> SentinelSource:
        return SentinelSource()

    @pytest.fixture
    def payload(self) -> dict:  # type: ignore[type-arg]
        return _load("sentinel_alert.json")

    def test_source_name(self, source: SentinelSource) -> None:
        assert source.source_name == "sentinel"

    def test_validate_payload_valid(self, source: SentinelSource, payload: dict) -> None:  # type: ignore[type-arg]
        assert source.validate_payload(payload) is True

    def test_validate_payload_invalid(self, source: SentinelSource) -> None:
        assert source.validate_payload({}) is False
        assert source.validate_payload({"foo": "bar"}) is False

    def test_normalize_title(self, source: SentinelSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.title == "Suspicious PowerShell Execution on WORKSTATION-01"

    def test_normalize_severity(self, source: SentinelSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.HIGH

    def test_normalize_occurred_at_uses_first_activity(
        self, source: SentinelSource, payload: dict  # type: ignore[type-arg]
    ) -> None:
        alert = source.normalize(payload)
        # firstActivityTimeUtc: 2024-01-15T10:29:50.000Z
        assert alert.occurred_at.year == 2024
        assert alert.occurred_at.month == 1
        assert alert.occurred_at.day == 15
        assert alert.occurred_at.hour == 10
        assert alert.occurred_at.minute == 29

    def test_normalize_source_name(self, source: SentinelSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.source_name == "sentinel"

    def test_normalize_tags(self, source: SentinelSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert "powershell" in alert.tags
        assert "endpoint" in alert.tags

    def test_extract_indicators(self, source: SentinelSource, payload: dict) -> None:  # type: ignore[type-arg]
        indicators = source.extract_indicators(payload)
        tv = {(i.type, i.value) for i in indicators}
        assert (IndicatorType.IP, "10.0.0.55") in tv
        assert (IndicatorType.IP, "185.220.101.32") in tv
        assert (IndicatorType.ACCOUNT, "jdoe@corp.com") in tv
        assert (IndicatorType.DOMAIN, "WORKSTATION-01.corp.com") in tv
        assert (IndicatorType.HASH_SHA256, SHA256_PS) in tv
        assert (IndicatorType.HASH_MD5, MD5_VAL) in tv

    def test_extract_detection_rule_ref(self, source: SentinelSource, payload: dict) -> None:  # type: ignore[type-arg]
        ref = source.extract_detection_rule_ref(payload)
        assert ref == "rule-uuid-abc123"

    def test_extract_detection_rule_ref_none_when_missing(
        self, source: SentinelSource
    ) -> None:
        assert source.extract_detection_rule_ref({}) is None
        assert source.extract_detection_rule_ref({"properties": {}}) is None

    def test_verify_signature_true_when_no_secret(
        self, source: SentinelSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_sentinel_secret(monkeypatch, "")
        assert source.verify_webhook_signature({}, b"body") is True

    def test_verify_signature_false_when_header_missing(
        self, source: SentinelSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_sentinel_secret(monkeypatch, "mysecret")
        assert source.verify_webhook_signature({}, b"body") is False

    def test_verify_signature_valid(
        self, source: SentinelSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "mysecret"
        body = b'{"test": true}'
        _setattr_sentinel_secret(monkeypatch, secret)
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert source.verify_webhook_signature({"X-Sentinel-Signature": sig}, body) is True

    def test_verify_signature_invalid(
        self, source: SentinelSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_sentinel_secret(monkeypatch, "mysecret")
        assert source.verify_webhook_signature(
            {"X-Sentinel-Signature": "wrong-sig"}, b"body"
        ) is False


# ---------------------------------------------------------------------------
# Elastic Security
# ---------------------------------------------------------------------------

class TestElasticSource:
    @pytest.fixture
    def source(self) -> ElasticSource:
        return ElasticSource()

    @pytest.fixture
    def payload(self) -> dict:  # type: ignore[type-arg]
        return _load("elastic_alert.json")

    def test_source_name(self, source: ElasticSource) -> None:
        assert source.source_name == "elastic"

    def test_validate_payload_valid(self, source: ElasticSource, payload: dict) -> None:  # type: ignore[type-arg]
        assert source.validate_payload(payload) is True

    def test_validate_payload_invalid(self, source: ElasticSource) -> None:
        assert source.validate_payload({}) is False

    def test_normalize_title(self, source: ElasticSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.title == "Suspicious PowerShell Execution"

    def test_normalize_severity(self, source: ElasticSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.HIGH

    def test_normalize_occurred_at_uses_start(
        self, source: ElasticSource, payload: dict  # type: ignore[type-arg]
    ) -> None:
        alert = source.normalize(payload)
        # kibana.alert.start: 2024-01-15T10:29:50.000Z
        assert alert.occurred_at.year == 2024
        assert alert.occurred_at.minute == 29

    def test_normalize_source_name(self, source: ElasticSource, payload: dict) -> None:  # type: ignore[type-arg]
        assert source.normalize(payload).source_name == "elastic"

    def test_normalize_tags(self, source: ElasticSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert "PowerShell" in alert.tags

    def test_extract_indicators(self, source: ElasticSource, payload: dict) -> None:  # type: ignore[type-arg]
        indicators = source.extract_indicators(payload)
        tv = {(i.type, i.value) for i in indicators}
        assert (IndicatorType.IP, "10.0.0.55") in tv
        assert (IndicatorType.IP, "185.220.101.32") in tv
        assert (IndicatorType.DOMAIN, "evil.example.com") in tv
        assert (IndicatorType.DOMAIN, "c2-server.evil.com") in tv
        assert (IndicatorType.HASH_SHA256, SHA256_PS) in tv
        assert (IndicatorType.HASH_MD5, MD5_VAL) in tv
        assert (IndicatorType.EMAIL, "jdoe@corp.com") in tv
        assert (IndicatorType.ACCOUNT, "jdoe") in tv
        assert (IndicatorType.URL, "https://evil.example.com/payload/stage2.ps1") in tv

    def test_extract_detection_rule_ref(self, source: ElasticSource, payload: dict) -> None:  # type: ignore[type-arg]
        assert source.extract_detection_rule_ref(payload) == "rule-uuid-elastic-abc"

    def test_verify_signature_true_when_no_secret(
        self, source: ElasticSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_elastic_secret(monkeypatch, "")
        assert source.verify_webhook_signature({}, b"body") is True

    def test_verify_signature_valid(
        self, source: ElasticSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "elasticsecret"
        body = b'{"test": true}'
        _setattr_elastic_secret(monkeypatch, secret)
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert source.verify_webhook_signature({"X-Elastic-Signature": sig}, body) is True

    def test_verify_signature_invalid(
        self, source: ElasticSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_elastic_secret(monkeypatch, "secret")
        assert source.verify_webhook_signature(
            {"X-Elastic-Signature": "wrong"}, b"body"
        ) is False


# ---------------------------------------------------------------------------
# Splunk
# ---------------------------------------------------------------------------

class TestSplunkSource:
    @pytest.fixture
    def source(self) -> SplunkSource:
        return SplunkSource()

    @pytest.fixture
    def payload(self) -> dict:  # type: ignore[type-arg]
        return _load("splunk_alert.json")

    def test_source_name(self, source: SplunkSource) -> None:
        assert source.source_name == "splunk"

    def test_validate_payload_valid(self, source: SplunkSource, payload: dict) -> None:  # type: ignore[type-arg]
        assert source.validate_payload(payload) is True

    def test_validate_payload_invalid(self, source: SplunkSource) -> None:
        assert source.validate_payload({}) is False
        assert source.validate_payload({"result": {}}) is False

    def test_normalize_title(self, source: SplunkSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.title == "Brute Force Login Attempt"

    def test_normalize_severity(self, source: SplunkSource, payload: dict) -> None:  # type: ignore[type-arg]
        alert = source.normalize(payload)
        assert alert.severity == AlertSeverity.HIGH

    def test_normalize_occurred_at_from_unix_timestamp(
        self, source: SplunkSource, payload: dict  # type: ignore[type-arg]
    ) -> None:
        alert = source.normalize(payload)
        # _time: 1705312200.0 — verify UTC timestamp converts correctly
        expected = datetime.fromtimestamp(1705312200.0, tz=UTC)
        assert alert.occurred_at == expected

    def test_normalize_source_name(self, source: SplunkSource, payload: dict) -> None:  # type: ignore[type-arg]
        assert source.normalize(payload).source_name == "splunk"

    def test_extract_indicators(self, source: SplunkSource, payload: dict) -> None:  # type: ignore[type-arg]
        indicators = source.extract_indicators(payload)
        tv = {(i.type, i.value) for i in indicators}
        assert (IndicatorType.IP, "10.0.0.99") in tv
        assert (IndicatorType.IP, "192.168.1.10") in tv
        assert (IndicatorType.ACCOUNT, "admin") in tv
        assert (IndicatorType.HASH_SHA256, SHA256_SPLUNK) in tv
        assert (IndicatorType.DOMAIN, "corp.example.com") in tv

    def test_extract_detection_rule_ref(self, source: SplunkSource, payload: dict) -> None:  # type: ignore[type-arg]
        assert source.extract_detection_rule_ref(payload) == "Brute Force Login Attempt"

    def test_extract_detection_rule_ref_fallback_to_search_name(
        self, source: SplunkSource
    ) -> None:
        payload = {"result": {}, "search_name": "My Search", "sid": "1234"}
        assert source.extract_detection_rule_ref(payload) == "My Search"

    def test_verify_signature_true_when_no_secret(
        self, source: SplunkSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_splunk_secret(monkeypatch, "")
        assert source.verify_webhook_signature({}, b"body") is True

    def test_verify_signature_valid(
        self, source: SplunkSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        secret = "splunksecret"
        _setattr_splunk_secret(monkeypatch, secret)
        assert source.verify_webhook_signature(
            {"X-Splunk-Webhook-Secret": secret}, b"body"
        ) is True

    def test_verify_signature_invalid(
        self, source: SplunkSource, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _setattr_splunk_secret(monkeypatch, "correct")
        assert source.verify_webhook_signature(
            {"X-Splunk-Webhook-Secret": "wrong"}, b"body"
        ) is False
