"""
Unit tests for the 3-pass indicator extraction pipeline.

Pass 1: Source plugin extract_indicators(raw_payload) — source-specific, hardcoded
Pass 2: System normalized-field mappings against CalsetaAlert fields
         (extraction_target='normalized')
Pass 3: Custom per-source field mappings against raw_payload
         (extraction_target='raw_payload')

Tests cover:
  - Source plugin extraction for each source (Sentinel, Elastic, Splunk, Generic)
  - System normalized-field mappings (14 system mappings seeded at startup)
  - Custom per-source dot-notation field mappings against raw_payload
  - Array unwrapping (fields that contain arrays of values)
  - Deduplication across passes — same (type, value) pair found in multiple passes
  - Exception isolation — failure in Pass 1 must not block Pass 2+3
  - Seeder idempotency (running seed twice doesn't create duplicates)

Uses mocked DB sessions and in-memory objects — no real DB required for unit tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.sources.elastic import ElasticSource
from app.integrations.sources.generic import GenericSource
from app.integrations.sources.sentinel import SentinelSource
from app.integrations.sources.splunk import SplunkSource
from app.schemas.alert import AlertSeverity, CalsetaAlert
from app.schemas.indicators import IndicatorExtract, IndicatorType
from app.seed.indicator_mappings import _SYSTEM_MAPPINGS, seed_system_mappings
from app.services.indicator_extraction import (
    IndicatorExtractionService,
    _extract_normalized,
    _extract_raw,
    _traverse,
    extract_for_fingerprint,
)
from app.services.indicator_mapping_cache import CachedMapping

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Helper: lightweight mapping duck-type for _extract_normalized / _extract_raw
# ---------------------------------------------------------------------------


@dataclass
class FakeMapping:
    """Mimics IndicatorFieldMapping with field_path and indicator_type attributes."""

    field_path: str
    indicator_type: str
    source_name: str | None = None


# ---------------------------------------------------------------------------
# _traverse — dot-notation path traversal into nested dicts
# ---------------------------------------------------------------------------


class TestTraverse:
    def test_simple_key(self) -> None:
        assert _traverse({"src_ip": "1.2.3.4"}, "src_ip") == "1.2.3.4"

    def test_nested_key(self) -> None:
        data = {"a": {"b": {"c": "value"}}}
        assert _traverse(data, "a.b.c") == "value"

    def test_missing_key_returns_none(self) -> None:
        assert _traverse({"a": "b"}, "x.y.z") is None

    def test_non_dict_intermediate_returns_none(self) -> None:
        assert _traverse({"a": "string"}, "a.b.c") is None

    def test_empty_string_returns_none(self) -> None:
        assert _traverse({"a": ""}, "a") is None

    def test_whitespace_only_returns_none(self) -> None:
        assert _traverse({"a": "   "}, "a") is None

    def test_integer_value_returns_none(self) -> None:
        """_traverse only returns string values."""
        assert _traverse({"a": 42}, "a") is None

    def test_list_value_returns_none(self) -> None:
        """_traverse does not handle list values — those are handled by array unwrapping."""
        assert _traverse({"a": ["1.2.3.4"]}, "a") is None

    def test_deep_nesting(self) -> None:
        data = {"l1": {"l2": {"l3": {"l4": "deep"}}}}
        assert _traverse(data, "l1.l2.l3.l4") == "deep"

    def test_strips_whitespace(self) -> None:
        assert _traverse({"ip": "  1.2.3.4  "}, "ip") == "1.2.3.4"


# ---------------------------------------------------------------------------
# Pass 1: Source plugin extract_indicators()
# ---------------------------------------------------------------------------


class TestPass1Sentinel:
    @pytest.fixture
    def source(self) -> SentinelSource:
        return SentinelSource()

    @pytest.fixture
    def payload(self) -> dict[str, Any]:
        return _load("sentinel_alert.json")

    def test_extracts_ips(self, source: SentinelSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        ips = {i.value for i in indicators if i.type == IndicatorType.IP}
        assert "10.0.0.55" in ips
        assert "185.220.101.32" in ips

    def test_extracts_account(self, source: SentinelSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        accounts = {i.value for i in indicators if i.type == IndicatorType.ACCOUNT}
        assert "jdoe@corp.com" in accounts

    def test_extracts_host_as_domain(
        self, source: SentinelSource, payload: dict[str, Any]
    ) -> None:
        indicators = source.extract_indicators(payload)
        domains = {i.value for i in indicators if i.type == IndicatorType.DOMAIN}
        assert "WORKSTATION-01.corp.com" in domains

    def test_extracts_file_hashes(
        self, source: SentinelSource, payload: dict[str, Any]
    ) -> None:
        indicators = source.extract_indicators(payload)
        types_values = {(i.type, i.value) for i in indicators}
        assert (
            IndicatorType.HASH_SHA256,
            "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456",
        ) in types_values
        assert (
            IndicatorType.HASH_MD5,
            "d41d8cd98f00b204e9800998ecf8427e",
        ) in types_values

    def test_empty_entities_returns_empty(self, source: SentinelSource) -> None:
        assert source.extract_indicators({"Entities": []}) == []

    def test_missing_entities_returns_empty(self, source: SentinelSource) -> None:
        assert source.extract_indicators({}) == []

    def test_malformed_entity_skipped(self, source: SentinelSource) -> None:
        payload = {"Entities": ["not_a_dict", 42, None]}
        assert source.extract_indicators(payload) == []

    def test_unknown_entity_type_skipped(self, source: SentinelSource) -> None:
        payload = {"Entities": [{"Type": "registry", "Path": "HKLM\\..."}]}
        assert source.extract_indicators(payload) == []

    def test_empty_address_skipped(self, source: SentinelSource) -> None:
        payload = {"Entities": [{"Type": "ip", "Address": ""}]}
        assert source.extract_indicators(payload) == []

    def test_source_field_set(self, source: SentinelSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        assert all(i.source_field is not None for i in indicators)

    def test_url_entity(self, source: SentinelSource) -> None:
        payload = {"Entities": [{"Type": "url", "Url": "https://evil.com/malware.exe"}]}
        indicators = source.extract_indicators(payload)
        assert len(indicators) == 1
        assert indicators[0].type == IndicatorType.URL
        assert indicators[0].value == "https://evil.com/malware.exe"

    def test_filehash_unknown_algorithm_skipped(self, source: SentinelSource) -> None:
        payload = {"Entities": [{"Type": "filehash", "Algorithm": "CRC32", "Value": "abc123"}]}
        assert source.extract_indicators(payload) == []


class TestPass1Elastic:
    @pytest.fixture
    def source(self) -> ElasticSource:
        return ElasticSource()

    @pytest.fixture
    def payload(self) -> dict[str, Any]:
        return _load("elastic_alert.json")

    def test_extracts_source_and_dest_ips(
        self, source: ElasticSource, payload: dict[str, Any]
    ) -> None:
        indicators = source.extract_indicators(payload)
        ips = {i.value for i in indicators if i.type == IndicatorType.IP}
        assert "10.0.0.55" in ips
        assert "185.220.101.32" in ips

    def test_extracts_domains(self, source: ElasticSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        domains = {i.value for i in indicators if i.type == IndicatorType.DOMAIN}
        assert "evil.example.com" in domains
        assert "c2-server.evil.com" in domains

    def test_extracts_url(self, source: ElasticSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        urls = {i.value for i in indicators if i.type == IndicatorType.URL}
        assert "https://evil.example.com/payload/stage2.ps1" in urls

    def test_extracts_hashes(self, source: ElasticSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        hashes_256 = {i.value for i in indicators if i.type == IndicatorType.HASH_SHA256}
        hashes_md5 = {i.value for i in indicators if i.type == IndicatorType.HASH_MD5}
        assert "a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456" in hashes_256
        assert "d41d8cd98f00b204e9800998ecf8427e" in hashes_md5

    def test_extracts_user(self, source: ElasticSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        accounts = {i.value for i in indicators if i.type == IndicatorType.ACCOUNT}
        emails = {i.value for i in indicators if i.type == IndicatorType.EMAIL}
        assert "jdoe" in accounts
        assert "jdoe@corp.com" in emails

    def test_host_ip_array_unwrapping(self, source: ElasticSource) -> None:
        """host.ip is an array in the fixture — all elements should be extracted."""
        payload = {"host.ip": ["10.0.0.1", "10.0.0.2", "10.0.0.3"]}
        indicators = source.extract_indicators(payload)
        ips = {i.value for i in indicators if i.type == IndicatorType.IP}
        assert "10.0.0.1" in ips
        assert "10.0.0.2" in ips
        assert "10.0.0.3" in ips

    def test_empty_payload_returns_empty(self, source: ElasticSource) -> None:
        assert source.extract_indicators({}) == []

    def test_array_with_non_strings_filtered(self, source: ElasticSource) -> None:
        """Non-string values in an array field should be ignored."""
        payload = {"host.ip": [None, 42, "", "10.0.0.1"]}
        indicators = source.extract_indicators(payload)
        ips = {i.value for i in indicators if i.type == IndicatorType.IP}
        assert ips == {"10.0.0.1"}

    def test_threat_indicator_fields(self, source: ElasticSource) -> None:
        payload = {
            "threat.indicator.ip": "203.0.113.5",
            "threat.indicator.domain": "malware.bad.com",
            "threat.indicator.file.hash.sha256": "deadbeef" * 8,
        }
        indicators = source.extract_indicators(payload)
        types_values = {(i.type, i.value) for i in indicators}
        assert (IndicatorType.IP, "203.0.113.5") in types_values
        assert (IndicatorType.DOMAIN, "malware.bad.com") in types_values
        assert (IndicatorType.HASH_SHA256, "deadbeef" * 8) in types_values


class TestPass1Splunk:
    @pytest.fixture
    def source(self) -> SplunkSource:
        return SplunkSource()

    @pytest.fixture
    def payload(self) -> dict[str, Any]:
        return _load("splunk_alert.json")

    def test_extracts_ips(self, source: SplunkSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        ips = {i.value for i in indicators if i.type == IndicatorType.IP}
        assert "10.0.0.99" in ips
        assert "192.168.1.10" in ips

    def test_extracts_user(self, source: SplunkSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        accounts = {i.value for i in indicators if i.type == IndicatorType.ACCOUNT}
        assert "admin" in accounts

    def test_extracts_hash(self, source: SplunkSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        hashes = {i.value for i in indicators if i.type == IndicatorType.HASH_SHA256}
        assert "b94f6f125c79e3a5ffaa826f584c10d52ada669e6762051b826b55776d05a8a" in hashes

    def test_extracts_domain(self, source: SplunkSource, payload: dict[str, Any]) -> None:
        indicators = source.extract_indicators(payload)
        domains = {i.value for i in indicators if i.type == IndicatorType.DOMAIN}
        assert "corp.example.com" in domains

    def test_ip_fallback_uses_src_when_src_ip_absent(self, source: SplunkSource) -> None:
        """When src_ip is missing, fall back to src field."""
        payload = {"result": {"src": "10.0.0.5"}, "sid": "1234"}
        indicators = source.extract_indicators(payload)
        ips = {i.value for i in indicators if i.type == IndicatorType.IP}
        assert "10.0.0.5" in ips

    def test_ip_fallback_not_used_when_src_ip_present(self, source: SplunkSource) -> None:
        """When src_ip is present, src should not appear as a duplicate."""
        payload = {
            "result": {"src_ip": "10.0.0.1", "src": "10.0.0.1"},
            "sid": "1234",
        }
        indicators = source.extract_indicators(payload)
        ip_indicators = [i for i in indicators if i.type == IndicatorType.IP]
        # src_ip present means src should not be extracted — only src_ip
        ip_source_fields = [i.source_field for i in ip_indicators]
        assert "result.src_ip" in ip_source_fields
        # src should not be extracted since src_ip is present
        assert "result.src" not in ip_source_fields

    def test_empty_result_returns_empty(self, source: SplunkSource) -> None:
        payload = {"result": {}, "sid": "1234"}
        assert source.extract_indicators(payload) == []

    def test_missing_result_returns_empty(self, source: SplunkSource) -> None:
        assert source.extract_indicators({}) == []


class TestPass1Generic:
    @pytest.fixture
    def source(self) -> GenericSource:
        return GenericSource()

    def test_explicit_indicators_array(self, source: GenericSource) -> None:
        payload = {
            "title": "Test",
            "indicators": [
                {"type": "ip", "value": "1.2.3.4"},
                {"type": "domain", "value": "evil.com"},
            ],
        }
        indicators = source.extract_indicators(payload)
        types_values = {(i.type, i.value) for i in indicators}
        assert (IndicatorType.IP, "1.2.3.4") in types_values
        assert (IndicatorType.DOMAIN, "evil.com") in types_values

    def test_common_field_names(self, source: GenericSource) -> None:
        payload = {
            "title": "Test",
            "src_ip": "10.0.0.1",
            "domain": "example.com",
            "sha256": "a" * 64,
        }
        indicators = source.extract_indicators(payload)
        types_values = {(i.type, i.value) for i in indicators}
        assert (IndicatorType.IP, "10.0.0.1") in types_values
        assert (IndicatorType.DOMAIN, "example.com") in types_values
        assert (IndicatorType.HASH_SHA256, "a" * 64) in types_values

    def test_invalid_indicator_type_in_array_skipped(self, source: GenericSource) -> None:
        payload = {
            "title": "Test",
            "indicators": [
                {"type": "unknown_type", "value": "something"},
            ],
        }
        assert source.extract_indicators(payload) == []

    def test_non_dict_items_in_indicators_skipped(self, source: GenericSource) -> None:
        payload = {
            "title": "Test",
            "indicators": ["not_a_dict", 42],
        }
        assert source.extract_indicators(payload) == []

    def test_empty_value_skipped(self, source: GenericSource) -> None:
        payload = {
            "title": "Test",
            "src_ip": "",
            "indicators": [{"type": "ip", "value": ""}],
        }
        assert source.extract_indicators(payload) == []


# ---------------------------------------------------------------------------
# Pass 2: _extract_normalized — system normalized-field mappings
# ---------------------------------------------------------------------------


class TestPass2ExtractNormalized:
    def _make_alert(self, **kwargs: Any) -> CalsetaAlert:
        defaults: dict[str, Any] = {
            "title": "Test Alert",
            "severity": AlertSeverity.HIGH,
            "occurred_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "source_name": "sentinel",
        }
        defaults.update(kwargs)
        return CalsetaAlert(**defaults)

    def test_extracts_src_ip(self) -> None:
        alert = self._make_alert(src_ip="10.0.0.1")
        mappings = [FakeMapping(field_path="src_ip", indicator_type="ip")]
        result = _extract_normalized(alert, mappings)
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP
        assert result[0].value == "10.0.0.1"
        assert result[0].source_field == "normalized.src_ip"

    def test_extracts_dst_ip(self) -> None:
        alert = self._make_alert(dst_ip="192.168.1.1")
        mappings = [FakeMapping(field_path="dst_ip", indicator_type="ip")]
        result = _extract_normalized(alert, mappings)
        assert len(result) == 1
        assert result[0].value == "192.168.1.1"

    def test_extracts_domain_fields(self) -> None:
        alert = self._make_alert(
            src_hostname="host1.corp.com",
            dst_hostname="host2.corp.com",
            dns_query="evil.com",
            http_hostname="web.example.com",
        )
        mappings = [
            FakeMapping(field_path="src_hostname", indicator_type="domain"),
            FakeMapping(field_path="dst_hostname", indicator_type="domain"),
            FakeMapping(field_path="dns_query", indicator_type="domain"),
            FakeMapping(field_path="http_hostname", indicator_type="domain"),
        ]
        result = _extract_normalized(alert, mappings)
        values = {r.value for r in result}
        assert values == {"host1.corp.com", "host2.corp.com", "evil.com", "web.example.com"}

    def test_extracts_hash_fields(self) -> None:
        alert = self._make_alert(
            file_hash_md5="d41d8cd98f00b204e9800998ecf8427e",
            file_hash_sha1="da39a3ee5e6b4b0d3255bfef95601890afd80709",
            file_hash_sha256="e3b0c44298fc1c149afbf4c8996fb924" * 2,
        )
        mappings = [
            FakeMapping(field_path="file_hash_md5", indicator_type="hash_md5"),
            FakeMapping(field_path="file_hash_sha1", indicator_type="hash_sha1"),
            FakeMapping(field_path="file_hash_sha256", indicator_type="hash_sha256"),
        ]
        result = _extract_normalized(alert, mappings)
        types = {r.type for r in result}
        assert types == {IndicatorType.HASH_MD5, IndicatorType.HASH_SHA1, IndicatorType.HASH_SHA256}

    def test_extracts_email_fields(self) -> None:
        alert = self._make_alert(
            actor_email="user@corp.com",
            email_from="sender@evil.com",
            email_reply_to="reply@evil.com",
        )
        mappings = [
            FakeMapping(field_path="actor_email", indicator_type="email"),
            FakeMapping(field_path="email_from", indicator_type="email"),
            FakeMapping(field_path="email_reply_to", indicator_type="email"),
        ]
        result = _extract_normalized(alert, mappings)
        values = {r.value for r in result}
        assert values == {"user@corp.com", "sender@evil.com", "reply@evil.com"}

    def test_extracts_account_field(self) -> None:
        alert = self._make_alert(actor_username="admin")
        mappings = [FakeMapping(field_path="actor_username", indicator_type="account")]
        result = _extract_normalized(alert, mappings)
        assert len(result) == 1
        assert result[0].type == IndicatorType.ACCOUNT
        assert result[0].value == "admin"

    def test_extracts_url_field(self) -> None:
        alert = self._make_alert(http_url="https://evil.com/malware.exe")
        mappings = [FakeMapping(field_path="http_url", indicator_type="url")]
        result = _extract_normalized(alert, mappings)
        assert len(result) == 1
        assert result[0].type == IndicatorType.URL

    def test_none_field_skipped(self) -> None:
        """Normalized fields that are None should not produce indicators."""
        alert = self._make_alert()  # src_ip defaults to None
        mappings = [FakeMapping(field_path="src_ip", indicator_type="ip")]
        result = _extract_normalized(alert, mappings)
        assert result == []

    def test_empty_string_skipped(self) -> None:
        alert = self._make_alert(src_ip="")
        mappings = [FakeMapping(field_path="src_ip", indicator_type="ip")]
        result = _extract_normalized(alert, mappings)
        assert result == []

    def test_whitespace_only_skipped(self) -> None:
        alert = self._make_alert(src_ip="   ")
        mappings = [FakeMapping(field_path="src_ip", indicator_type="ip")]
        result = _extract_normalized(alert, mappings)
        assert result == []

    def test_unknown_indicator_type_skipped(self) -> None:
        alert = self._make_alert(src_ip="1.2.3.4")
        mappings = [FakeMapping(field_path="src_ip", indicator_type="unknown_type")]
        result = _extract_normalized(alert, mappings)
        assert result == []

    def test_no_mappings_returns_empty(self) -> None:
        alert = self._make_alert(src_ip="1.2.3.4")
        result = _extract_normalized(alert, [])
        assert result == []

    def test_all_14_system_mappings(self) -> None:
        """
        Verify all 14 system mappings can extract when all fields are populated.
        """
        alert = self._make_alert(
            src_ip="10.0.0.1",
            dst_ip="10.0.0.2",
            src_hostname="h1.com",
            dst_hostname="h2.com",
            file_hash_md5="d41d8cd98f00b204e9800998ecf8427e",
            file_hash_sha256="e3b0c44298fc1c149afbf4c8996fb924" * 2,
            file_hash_sha1="da39a3ee5e6b4b0d3255bfef95601890afd80709",
            actor_email="user@corp.com",
            actor_username="admin",
            dns_query="evil.com",
            http_url="https://evil.com/payload",
            http_hostname="evil.com",
            email_from="sender@evil.com",
            email_reply_to="reply@evil.com",
        )
        mappings = [
            FakeMapping(field_path=fp, indicator_type=it)
            for fp, it, _desc in _SYSTEM_MAPPINGS
        ]
        result = _extract_normalized(alert, mappings)
        assert len(result) == 14

    def test_strips_leading_trailing_whitespace(self) -> None:
        alert = self._make_alert(src_ip="  10.0.0.1  ")
        mappings = [FakeMapping(field_path="src_ip", indicator_type="ip")]
        result = _extract_normalized(alert, mappings)
        assert result[0].value == "10.0.0.1"


# ---------------------------------------------------------------------------
# Pass 3: _extract_raw — custom per-source field mappings against raw_payload
# ---------------------------------------------------------------------------


class TestPass3ExtractRaw:
    def test_simple_field_path(self) -> None:
        raw = {"data": {"client_ip": "1.2.3.4"}}
        mappings = [FakeMapping(field_path="data.client_ip", indicator_type="ip")]
        result = _extract_raw(raw, mappings)
        assert len(result) == 1
        assert result[0].type == IndicatorType.IP
        assert result[0].value == "1.2.3.4"
        assert result[0].source_field == "raw_payload.data.client_ip"

    def test_deep_nesting(self) -> None:
        raw = {"okta": {"data": {"client": {"ipAddress": "10.0.0.1"}}}}
        mappings = [
            FakeMapping(field_path="okta.data.client.ipAddress", indicator_type="ip")
        ]
        result = _extract_raw(raw, mappings)
        assert result[0].value == "10.0.0.1"

    def test_top_level_field(self) -> None:
        raw = {"custom_domain": "evil.com"}
        mappings = [FakeMapping(field_path="custom_domain", indicator_type="domain")]
        result = _extract_raw(raw, mappings)
        assert len(result) == 1
        assert result[0].value == "evil.com"

    def test_missing_path_returns_empty(self) -> None:
        raw = {"data": {"something": "else"}}
        mappings = [FakeMapping(field_path="data.missing_field", indicator_type="ip")]
        result = _extract_raw(raw, mappings)
        assert result == []

    def test_empty_string_value_skipped(self) -> None:
        raw = {"data": {"ip": ""}}
        mappings = [FakeMapping(field_path="data.ip", indicator_type="ip")]
        result = _extract_raw(raw, mappings)
        assert result == []

    def test_whitespace_only_value_skipped(self) -> None:
        raw = {"data": {"ip": "   "}}
        mappings = [FakeMapping(field_path="data.ip", indicator_type="ip")]
        result = _extract_raw(raw, mappings)
        assert result == []

    def test_unknown_indicator_type_skipped(self) -> None:
        raw = {"data": {"value": "something"}}
        mappings = [FakeMapping(field_path="data.value", indicator_type="nonexistent")]
        result = _extract_raw(raw, mappings)
        assert result == []

    def test_multiple_mappings(self) -> None:
        raw = {
            "src": "10.0.0.1",
            "dst": "10.0.0.2",
            "user_email": "admin@corp.com",
        }
        mappings = [
            FakeMapping(field_path="src", indicator_type="ip"),
            FakeMapping(field_path="dst", indicator_type="ip"),
            FakeMapping(field_path="user_email", indicator_type="email"),
        ]
        result = _extract_raw(raw, mappings)
        assert len(result) == 3

    def test_no_mappings_returns_empty(self) -> None:
        raw = {"data": {"ip": "1.2.3.4"}}
        result = _extract_raw(raw, [])
        assert result == []


# ---------------------------------------------------------------------------
# Deduplication across passes
# ---------------------------------------------------------------------------


class TestDeduplication:
    def _make_alert(self, **kwargs: Any) -> CalsetaAlert:
        defaults: dict[str, Any] = {
            "title": "Test Alert",
            "severity": AlertSeverity.HIGH,
            "occurred_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "source_name": "generic",
        }
        defaults.update(kwargs)
        return CalsetaAlert(**defaults)

    def test_same_ip_from_pass1_and_pass2_deduplicates(self) -> None:
        """
        When the same (type, value) is found in both Pass 1 (source plugin)
        and Pass 2 (normalized mappings), only one indicator should survive.
        """
        source = GenericSource()
        raw_payload = {"title": "Test", "src_ip": "10.0.0.1"}
        normalized = self._make_alert(src_ip="10.0.0.1")
        cached_mappings = [
            CachedMapping(field_path="src_ip", indicator_type="ip", source_name=None)
        ]

        result = extract_for_fingerprint(source, normalized, raw_payload, cached_mappings)

        ip_indicators = [
            i for i in result if i.type == IndicatorType.IP and i.value == "10.0.0.1"
        ]
        assert len(ip_indicators) == 1

    def test_different_ips_not_deduped(self) -> None:
        source = GenericSource()
        raw_payload = {"title": "Test", "src_ip": "10.0.0.1"}
        normalized = self._make_alert(dst_ip="10.0.0.2")
        cached_mappings = [
            CachedMapping(field_path="dst_ip", indicator_type="ip", source_name=None)
        ]

        result = extract_for_fingerprint(source, normalized, raw_payload, cached_mappings)

        ips = {i.value for i in result if i.type == IndicatorType.IP}
        assert "10.0.0.1" in ips
        assert "10.0.0.2" in ips

    def test_same_value_different_type_not_deduped(self) -> None:
        """An IP and an account with the same string value are different indicators."""
        source = GenericSource()
        raw_payload = {"title": "Test", "src_ip": "admin", "user": "admin"}
        normalized = self._make_alert()
        cached_mappings: list[CachedMapping] = []

        result = extract_for_fingerprint(source, normalized, raw_payload, cached_mappings)

        admin_indicators = [i for i in result if i.value == "admin"]
        types = {i.type for i in admin_indicators}
        # Both IP and ACCOUNT should be present since they are different types
        assert IndicatorType.IP in types
        assert IndicatorType.ACCOUNT in types

    def test_empty_values_filtered(self) -> None:
        """Whitespace-only values should be filtered during deduplication."""
        source = GenericSource()
        raw_payload = {"title": "Test"}
        normalized = self._make_alert()
        cached_mappings: list[CachedMapping] = []

        result = extract_for_fingerprint(source, normalized, raw_payload, cached_mappings)
        assert all(i.value.strip() for i in result)

    def test_deduplication_preserves_first_occurrence(self) -> None:
        """When the same (type, value) appears in multiple passes, first occurrence wins."""
        source = GenericSource()
        raw_payload = {"title": "Test", "src_ip": "10.0.0.1"}
        normalized = self._make_alert(src_ip="10.0.0.1")
        cached_mappings = [
            CachedMapping(field_path="src_ip", indicator_type="ip", source_name=None)
        ]

        result = extract_for_fingerprint(source, normalized, raw_payload, cached_mappings)

        ip_indicators = [i for i in result if i.value == "10.0.0.1"]
        assert len(ip_indicators) == 1
        # First occurrence comes from Pass 1 (source plugin)
        assert ip_indicators[0].source_field is not None


class TestDeduplicationAsync:
    """Async tests for 3-pass deduplication using extract_and_persist."""

    async def test_full_3pass_deduplication(self) -> None:
        source = GenericSource()
        raw_payload = {
            "title": "Test",
            "src_ip": "10.0.0.1",
            "custom_data": {"ip": "10.0.0.1"},
        }
        normalized = CalsetaAlert(
            title="Test",
            severity=AlertSeverity.HIGH,
            occurred_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            source_name="generic",
            src_ip="10.0.0.1",
        )

        mock_indicator = MagicMock()
        mock_indicator.id = 1

        norm_mapping = FakeMapping(field_path="src_ip", indicator_type="ip")
        raw_mapping = FakeMapping(field_path="custom_data.ip", indicator_type="ip")

        async def mock_get_active(
            source_name: str, extraction_target: str
        ) -> list[Any]:
            if extraction_target == "normalized":
                return [norm_mapping]
            return [raw_mapping]

        mock_db = AsyncMock()

        with (
            patch(
                "app.services.indicator_extraction.IndicatorMappingRepository"
            ) as MockMappingRepo,
            patch(
                "app.services.indicator_extraction.IndicatorRepository"
            ) as MockIndRepo,
        ):
            MockMappingRepo.return_value.get_active_for_extraction = AsyncMock(
                side_effect=mock_get_active
            )
            MockIndRepo.return_value.upsert = AsyncMock(return_value=mock_indicator)
            MockIndRepo.return_value.link_to_alert = AsyncMock()

            service = IndicatorExtractionService(mock_db)

            mock_alert = MagicMock()
            mock_alert.id = 42
            mock_alert.uuid = "test-uuid"

            count = await service.extract_and_persist(
                mock_alert, normalized, raw_payload, source
            )

            # Same IP found in all 3 passes — should be deduplicated to 1
            assert count == 1
            MockIndRepo.return_value.upsert.assert_awaited_once()
            MockIndRepo.return_value.link_to_alert.assert_awaited_once()

    async def test_distinct_indicators_across_passes(self) -> None:
        """Different indicators from different passes should all persist."""
        source = GenericSource()
        raw_payload = {
            "title": "Test",
            "src_ip": "10.0.0.1",
            "custom_data": {"domain": "evil.com"},
        }
        normalized = CalsetaAlert(
            title="Test",
            severity=AlertSeverity.HIGH,
            occurred_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            source_name="generic",
            dst_ip="10.0.0.2",
        )

        mock_indicator = MagicMock()
        mock_indicator.id = 1

        norm_mapping = FakeMapping(field_path="dst_ip", indicator_type="ip")
        raw_mapping = FakeMapping(field_path="custom_data.domain", indicator_type="domain")

        async def mock_get_active(
            source_name: str, extraction_target: str
        ) -> list[Any]:
            if extraction_target == "normalized":
                return [norm_mapping]
            return [raw_mapping]

        mock_db = AsyncMock()

        with (
            patch(
                "app.services.indicator_extraction.IndicatorMappingRepository"
            ) as MockMappingRepo,
            patch(
                "app.services.indicator_extraction.IndicatorRepository"
            ) as MockIndRepo,
        ):
            MockMappingRepo.return_value.get_active_for_extraction = AsyncMock(
                side_effect=mock_get_active
            )
            MockIndRepo.return_value.upsert = AsyncMock(return_value=mock_indicator)
            MockIndRepo.return_value.link_to_alert = AsyncMock()

            service = IndicatorExtractionService(mock_db)

            mock_alert = MagicMock()
            mock_alert.id = 42
            mock_alert.uuid = "test-uuid"

            count = await service.extract_and_persist(
                mock_alert, normalized, raw_payload, source
            )

            # Pass 1: src_ip=10.0.0.1, Pass 2: dst_ip=10.0.0.2, Pass 3: domain=evil.com
            assert count == 3


# ---------------------------------------------------------------------------
# Exception isolation — failure in one pass must not block other passes
# ---------------------------------------------------------------------------


class TestExceptionIsolation:
    async def test_pass1_failure_does_not_block_pass2_and_pass3(self) -> None:
        """If source plugin extract_indicators() raises, Pass 2 and Pass 3 still run."""

        class BrokenSource(GenericSource):
            def extract_indicators(
                self, raw: dict,  # type: ignore[type-arg]
            ) -> list[IndicatorExtract]:
                raise RuntimeError("Plugin crash")

        source = BrokenSource()
        raw_payload = {"title": "Test", "custom_data": {"ip": "10.0.0.5"}}
        normalized = CalsetaAlert(
            title="Test",
            severity=AlertSeverity.HIGH,
            occurred_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            source_name="generic",
            src_ip="10.0.0.1",
        )

        norm_mapping = FakeMapping(field_path="src_ip", indicator_type="ip")
        raw_mapping = FakeMapping(field_path="custom_data.ip", indicator_type="ip")

        async def mock_get_active(
            source_name: str, extraction_target: str
        ) -> list[Any]:
            if extraction_target == "normalized":
                return [norm_mapping]
            return [raw_mapping]

        mock_db = AsyncMock()
        mock_indicator = MagicMock()
        mock_indicator.id = 1

        with (
            patch(
                "app.services.indicator_extraction.IndicatorMappingRepository"
            ) as MockMappingRepo,
            patch(
                "app.services.indicator_extraction.IndicatorRepository"
            ) as MockIndRepo,
        ):
            MockMappingRepo.return_value.get_active_for_extraction = AsyncMock(
                side_effect=mock_get_active
            )
            MockIndRepo.return_value.upsert = AsyncMock(return_value=mock_indicator)
            MockIndRepo.return_value.link_to_alert = AsyncMock()

            service = IndicatorExtractionService(mock_db)
            mock_alert = MagicMock()
            mock_alert.id = 42
            mock_alert.uuid = "test-uuid"

            # Should NOT raise despite Pass 1 crash
            count = await service.extract_and_persist(
                mock_alert, normalized, raw_payload, source
            )

            # Pass 2: src_ip=10.0.0.1, Pass 3: custom_data.ip=10.0.0.5
            assert count == 2

    async def test_pass2_failure_does_not_block_pass1_and_pass3(self) -> None:
        """If Pass 2 mapping repo call raises, Pass 1 and Pass 3 still produce indicators."""
        source = GenericSource()
        raw_payload = {
            "title": "Test",
            "src_ip": "10.0.0.1",
            "custom_data": {"ip": "10.0.0.5"},
        }
        normalized = CalsetaAlert(
            title="Test",
            severity=AlertSeverity.HIGH,
            occurred_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            source_name="generic",
        )

        raw_mapping = FakeMapping(field_path="custom_data.ip", indicator_type="ip")
        call_count = 0

        async def mock_get_active(
            source_name: str, extraction_target: str
        ) -> list[Any]:
            nonlocal call_count
            call_count += 1
            if extraction_target == "normalized":
                raise RuntimeError("DB error")
            return [raw_mapping]

        mock_db = AsyncMock()
        mock_indicator = MagicMock()
        mock_indicator.id = 1

        with (
            patch(
                "app.services.indicator_extraction.IndicatorMappingRepository"
            ) as MockMappingRepo,
            patch(
                "app.services.indicator_extraction.IndicatorRepository"
            ) as MockIndRepo,
        ):
            MockMappingRepo.return_value.get_active_for_extraction = AsyncMock(
                side_effect=mock_get_active
            )
            MockIndRepo.return_value.upsert = AsyncMock(return_value=mock_indicator)
            MockIndRepo.return_value.link_to_alert = AsyncMock()

            service = IndicatorExtractionService(mock_db)
            mock_alert = MagicMock()
            mock_alert.id = 42
            mock_alert.uuid = "test-uuid"

            count = await service.extract_and_persist(
                mock_alert, normalized, raw_payload, source
            )

            # Pass 1: src_ip=10.0.0.1, Pass 3: custom_data.ip=10.0.0.5
            assert count == 2

    async def test_pass3_failure_does_not_block_pass1_and_pass2(self) -> None:
        """If Pass 3 mapping repo call raises, Pass 1 and Pass 2 still produce indicators."""
        source = GenericSource()
        raw_payload = {"title": "Test", "src_ip": "10.0.0.1"}
        normalized = CalsetaAlert(
            title="Test",
            severity=AlertSeverity.HIGH,
            occurred_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            source_name="generic",
            dst_ip="10.0.0.2",
        )

        norm_mapping = FakeMapping(field_path="dst_ip", indicator_type="ip")

        async def mock_get_active(
            source_name: str, extraction_target: str
        ) -> list[Any]:
            if extraction_target == "normalized":
                return [norm_mapping]
            raise RuntimeError("DB error on raw mappings")

        mock_db = AsyncMock()
        mock_indicator = MagicMock()
        mock_indicator.id = 1

        with (
            patch(
                "app.services.indicator_extraction.IndicatorMappingRepository"
            ) as MockMappingRepo,
            patch(
                "app.services.indicator_extraction.IndicatorRepository"
            ) as MockIndRepo,
        ):
            MockMappingRepo.return_value.get_active_for_extraction = AsyncMock(
                side_effect=mock_get_active
            )
            MockIndRepo.return_value.upsert = AsyncMock(return_value=mock_indicator)
            MockIndRepo.return_value.link_to_alert = AsyncMock()

            service = IndicatorExtractionService(mock_db)
            mock_alert = MagicMock()
            mock_alert.id = 42
            mock_alert.uuid = "test-uuid"

            count = await service.extract_and_persist(
                mock_alert, normalized, raw_payload, source
            )

            # Pass 1: src_ip=10.0.0.1, Pass 2: dst_ip=10.0.0.2
            assert count == 2

    async def test_all_passes_fail_returns_zero(self) -> None:
        """If all three passes fail, extract_and_persist should return 0, not raise."""

        class BrokenSource(GenericSource):
            def extract_indicators(
                self, raw: dict,  # type: ignore[type-arg]
            ) -> list[IndicatorExtract]:
                raise RuntimeError("Plugin crash")

        source = BrokenSource()
        raw_payload = {"title": "Test"}
        normalized = CalsetaAlert(
            title="Test",
            severity=AlertSeverity.HIGH,
            occurred_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            source_name="generic",
        )

        async def mock_get_active(
            source_name: str, extraction_target: str
        ) -> list[Any]:
            raise RuntimeError("DB error")

        mock_db = AsyncMock()

        with (
            patch(
                "app.services.indicator_extraction.IndicatorMappingRepository"
            ) as MockMappingRepo,
            patch(
                "app.services.indicator_extraction.IndicatorRepository"
            ) as MockIndRepo,
        ):
            MockMappingRepo.return_value.get_active_for_extraction = AsyncMock(
                side_effect=mock_get_active
            )

            service = IndicatorExtractionService(mock_db)
            mock_alert = MagicMock()
            mock_alert.id = 42
            mock_alert.uuid = "test-uuid"

            count = await service.extract_and_persist(
                mock_alert, normalized, raw_payload, source
            )

            assert count == 0
            MockIndRepo.return_value.upsert.assert_not_called()

    async def test_individual_persist_failure_does_not_block_others(self) -> None:
        """If persisting one indicator fails, others should still be persisted."""
        source = GenericSource()
        raw_payload = {
            "title": "Test",
            "src_ip": "10.0.0.1",
            "domain": "evil.com",
        }
        normalized = CalsetaAlert(
            title="Test",
            severity=AlertSeverity.HIGH,
            occurred_at=datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            source_name="generic",
        )

        mock_indicator = MagicMock()
        mock_indicator.id = 1
        upsert_call_count = 0

        async def mock_upsert(itype: str, value: str, now: datetime) -> MagicMock:
            nonlocal upsert_call_count
            upsert_call_count += 1
            if itype == "ip":
                raise RuntimeError("DB constraint error")
            return mock_indicator

        async def mock_get_active(
            source_name: str, extraction_target: str
        ) -> list[Any]:
            return []

        mock_db = AsyncMock()

        with (
            patch(
                "app.services.indicator_extraction.IndicatorMappingRepository"
            ) as MockMappingRepo,
            patch(
                "app.services.indicator_extraction.IndicatorRepository"
            ) as MockIndRepo,
        ):
            MockMappingRepo.return_value.get_active_for_extraction = AsyncMock(
                side_effect=mock_get_active
            )
            MockIndRepo.return_value.upsert = AsyncMock(side_effect=mock_upsert)
            MockIndRepo.return_value.link_to_alert = AsyncMock()

            service = IndicatorExtractionService(mock_db)
            mock_alert = MagicMock()
            mock_alert.id = 42
            mock_alert.uuid = "test-uuid"

            # Should not raise despite one persist failure
            count = await service.extract_and_persist(
                mock_alert, normalized, raw_payload, source
            )

            # Both indicators are unique, so count includes them both even if persist failed
            assert count == 2
            # upsert should have been called for both
            assert upsert_call_count == 2


# ---------------------------------------------------------------------------
# extract_for_fingerprint — Pass 1 + Pass 2 only (no DB, no persistence)
# ---------------------------------------------------------------------------


class TestExtractForFingerprint:
    def _make_alert(self, **kwargs: Any) -> CalsetaAlert:
        defaults: dict[str, Any] = {
            "title": "Test Alert",
            "severity": AlertSeverity.HIGH,
            "occurred_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC),
            "source_name": "generic",
        }
        defaults.update(kwargs)
        return CalsetaAlert(**defaults)

    def test_combines_pass1_and_pass2(self) -> None:
        source = GenericSource()
        raw_payload = {"title": "Test", "src_ip": "10.0.0.1"}
        normalized = self._make_alert(dst_ip="10.0.0.2")
        cached_mappings = [
            CachedMapping(field_path="dst_ip", indicator_type="ip", source_name=None)
        ]

        result = extract_for_fingerprint(source, normalized, raw_payload, cached_mappings)

        ips = {i.value for i in result if i.type == IndicatorType.IP}
        assert "10.0.0.1" in ips  # from Pass 1
        assert "10.0.0.2" in ips  # from Pass 2

    def test_pass1_exception_returns_pass2_only(self) -> None:
        class BrokenSource(GenericSource):
            def extract_indicators(
                self, raw: dict,  # type: ignore[type-arg]
            ) -> list[IndicatorExtract]:
                raise RuntimeError("Boom")

        source = BrokenSource()
        raw_payload = {"title": "Test"}
        normalized = self._make_alert(src_ip="10.0.0.1")
        cached_mappings = [
            CachedMapping(field_path="src_ip", indicator_type="ip", source_name=None)
        ]

        result = extract_for_fingerprint(source, normalized, raw_payload, cached_mappings)

        assert len(result) == 1
        assert result[0].value == "10.0.0.1"

    def test_pass2_exception_returns_pass1_only(self) -> None:
        source = GenericSource()
        raw_payload = {"title": "Test", "src_ip": "10.0.0.1"}
        normalized = self._make_alert()

        # Create a mapping object that raises when accessed
        bad_mapping = MagicMock()
        bad_mapping.field_path = property(lambda self: (_ for _ in ()).throw(RuntimeError("bad")))
        type(bad_mapping).field_path = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("bad"))
        )

        # Simpler approach: make _extract_normalized fail by passing a bad list
        with patch(
            "app.services.indicator_extraction._extract_normalized",
            side_effect=RuntimeError("Pass 2 crash"),
        ):
            result = extract_for_fingerprint(source, normalized, raw_payload, [])

        ips = {i.value for i in result if i.type == IndicatorType.IP}
        assert "10.0.0.1" in ips

    def test_no_indicators_returns_empty(self) -> None:
        source = GenericSource()
        raw_payload = {"title": "No indicators here"}
        normalized = self._make_alert()
        cached_mappings: list[CachedMapping] = []

        result = extract_for_fingerprint(source, normalized, raw_payload, cached_mappings)
        assert result == []

    def test_deduplication_in_fingerprint(self) -> None:
        source = GenericSource()
        raw_payload = {"title": "Test", "src_ip": "10.0.0.1"}
        normalized = self._make_alert(src_ip="10.0.0.1")
        cached_mappings = [
            CachedMapping(field_path="src_ip", indicator_type="ip", source_name=None)
        ]

        result = extract_for_fingerprint(source, normalized, raw_payload, cached_mappings)

        ip_indicators = [i for i in result if i.value == "10.0.0.1"]
        assert len(ip_indicators) == 1


# ---------------------------------------------------------------------------
# Seeder: seed_system_mappings
# ---------------------------------------------------------------------------


class TestSeedSystemMappings:
    def test_system_mappings_constant_has_14_entries(self) -> None:
        """PRD Section 7.12 specifies exactly 14 system normalized-field mappings."""
        assert len(_SYSTEM_MAPPINGS) == 14

    def test_system_mapping_fields_match_calseta_alert(self) -> None:
        """All system mapping field_paths should be valid CalsetaAlert fields."""
        alert_fields = set(CalsetaAlert.model_fields.keys())
        for field_path, _indicator_type, _desc in _SYSTEM_MAPPINGS:
            assert field_path in alert_fields, (
                f"System mapping field_path '{field_path}' is not a CalsetaAlert field"
            )

    def test_system_mapping_indicator_types_are_valid(self) -> None:
        """All system mapping indicator_types should be valid IndicatorType values."""
        valid_types = {str(t) for t in IndicatorType}
        for _field_path, indicator_type, _desc in _SYSTEM_MAPPINGS:
            assert indicator_type in valid_types, (
                f"System mapping indicator_type '{indicator_type}' is not a valid IndicatorType"
            )

    def test_system_mapping_types_match_fields(self) -> None:
        """Verify the type assignments make sense (e.g. src_ip -> ip, not domain)."""
        type_expectations = {
            "src_ip": "ip",
            "dst_ip": "ip",
            "src_hostname": "domain",
            "dst_hostname": "domain",
            "file_hash_md5": "hash_md5",
            "file_hash_sha256": "hash_sha256",
            "file_hash_sha1": "hash_sha1",
            "actor_email": "email",
            "actor_username": "account",
            "dns_query": "domain",
            "http_url": "url",
            "http_hostname": "domain",
            "email_from": "email",
            "email_reply_to": "email",
        }
        mapping_dict = {fp: it for fp, it, _desc in _SYSTEM_MAPPINGS}
        for field, expected_type in type_expectations.items():
            assert mapping_dict.get(field) == expected_type, (
                f"Expected {field} to map to {expected_type}, got {mapping_dict.get(field)}"
            )

    async def test_seed_idempotency(self) -> None:
        """Running seed twice should not create duplicate mappings."""
        mock_db = AsyncMock()

        # First run: no existing mappings -> all inserted
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        await seed_system_mappings(mock_db)

        # Should have called add() for each of the 14 mappings
        assert mock_db.add.call_count == 14
        mock_db.flush.assert_awaited_once()

    async def test_seed_skips_existing(self) -> None:
        """If mappings already exist, seed should not insert duplicates."""
        mock_db = AsyncMock()

        # Simulate all mappings already existing
        mock_existing = MagicMock()
        mock_existing.scalar_one_or_none.return_value = MagicMock()  # non-None = exists
        mock_db.execute.return_value = mock_existing

        await seed_system_mappings(mock_db)

        # No new mappings should be added
        mock_db.add.assert_not_called()
        # flush should not be called since inserted == 0
        mock_db.flush.assert_not_awaited()

    async def test_seed_partial_existing(self) -> None:
        """If some mappings exist and some don't, only new ones should be inserted."""
        mock_db = AsyncMock()

        call_count = 0

        async def mock_execute(stmt: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            # First 7 mappings already exist, last 7 are new
            if call_count <= 7:
                result.scalar_one_or_none.return_value = MagicMock()  # exists
            else:
                result.scalar_one_or_none.return_value = None  # doesn't exist
            return result

        mock_db.execute = AsyncMock(side_effect=mock_execute)

        await seed_system_mappings(mock_db)

        # Should have inserted only the 7 new mappings
        assert mock_db.add.call_count == 7
        mock_db.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# CachedMapping / indicator_mapping_cache
# ---------------------------------------------------------------------------


class TestIndicatorMappingCache:
    def test_get_normalized_mappings_filters_by_source(self) -> None:
        """get_normalized_mappings should return global + source-specific mappings."""
        from app.services.indicator_mapping_cache import _lock, get_normalized_mappings

        test_mappings = [
            CachedMapping(field_path="src_ip", indicator_type="ip", source_name=None),
            CachedMapping(field_path="custom", indicator_type="domain", source_name="sentinel"),
            CachedMapping(field_path="other", indicator_type="ip", source_name="elastic"),
        ]

        with _lock:
            # Temporarily replace global state
            import app.services.indicator_mapping_cache as cache_mod

            original = cache_mod._mappings
            cache_mod._mappings = test_mappings

        try:
            sentinel_mappings = get_normalized_mappings("sentinel")
            # Should include global (source_name=None) + sentinel-specific
            assert len(sentinel_mappings) == 2
            paths = {m.field_path for m in sentinel_mappings}
            assert "src_ip" in paths  # global
            assert "custom" in paths  # sentinel-specific
            assert "other" not in paths  # elastic-specific, should be excluded

            elastic_mappings = get_normalized_mappings("elastic")
            assert len(elastic_mappings) == 2
            paths = {m.field_path for m in elastic_mappings}
            assert "src_ip" in paths
            assert "other" in paths
            assert "custom" not in paths
        finally:
            with _lock:
                cache_mod._mappings = original

    def test_get_normalized_mappings_returns_all_global_when_no_source_specific(
        self,
    ) -> None:
        import app.services.indicator_mapping_cache as cache_mod
        from app.services.indicator_mapping_cache import _lock, get_normalized_mappings

        test_mappings = [
            CachedMapping(field_path="src_ip", indicator_type="ip", source_name=None),
            CachedMapping(field_path="dst_ip", indicator_type="ip", source_name=None),
        ]

        with _lock:
            original = cache_mod._mappings
            cache_mod._mappings = test_mappings

        try:
            result = get_normalized_mappings("splunk")
            assert len(result) == 2
        finally:
            with _lock:
                cache_mod._mappings = original
