"""
Elastic Security source integration.

Normalizes Elastic Security alert webhook payloads to the Calseta agent-native schema.
Elastic Kibana connectors send the alert `_source` as a flat JSON object where
field names use dot-notation (e.g. "kibana.alert.rule.name" is a flat string key,
not a nested JSON path).

Field mapping reference: docs/integrations/elastic/api_notes.md
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from typing import Any

import structlog

from app.config import settings
from app.integrations.sources.base import AlertSourceBase, SourcePluginExtraction
from app.schemas.alert import AlertSeverity, CalsetaAlert
from app.schemas.indicators import IndicatorExtract, IndicatorType

logger = structlog.get_logger(__name__)

# Elastic severity → Calseta severity (lowercase input)
_SEVERITY_MAP: dict[str, AlertSeverity] = {
    "critical": AlertSeverity.CRITICAL,
    "high": AlertSeverity.HIGH,
    "medium": AlertSeverity.MEDIUM,
    "low": AlertSeverity.LOW,
    "informational": AlertSeverity.INFORMATIONAL,
}


def _get(raw: dict[str, Any], *field_paths: str) -> Any:
    """
    Look up a field in an Elastic alert dict.

    Supports two formats:
    1. Flat dot-notation: {"kibana.alert.rule.name": "My Rule"} (Kibana webhook format)
    2. Nested JSON: {"kibana": {"alert": {"rule": {"name": "My Rule"}}}} (rare)

    Tries each field_path in order and returns the first non-None value found.
    """
    for path in field_paths:
        # 1. Flat dot-notation key (Kibana webhook format)
        value = raw.get(path)
        if value is not None:
            return value

        # 2. Nested traversal
        parts = path.split(".")
        obj: Any = raw
        for part in parts:
            if not isinstance(obj, dict):
                obj = None
                break
            obj = obj.get(part)
        if obj is not None:
            return obj

    return None


class ElasticSource(AlertSourceBase):
    """Alert source plugin for Elastic Security alert webhooks."""

    source_name = "elastic"
    display_name = "Elastic Security"

    def validate_payload(self, raw: dict) -> bool:  # type: ignore[type-arg]
        """Return True if the payload contains expected Elastic alert fields."""
        try:
            rule_name = _get(raw, "kibana.alert.rule.name")
            rule_uuid = _get(raw, "kibana.alert.rule.uuid")
            return bool(rule_name or rule_uuid)
        except Exception:
            return False

    def normalize(self, raw: dict) -> CalsetaAlert:  # type: ignore[type-arg]
        """Map Elastic alert fields to CalsetaAlert."""
        # Title: prefer rule name over reason
        title = (
            _get(raw, "kibana.alert.rule.name")
            or _get(raw, "kibana.alert.reason")
            or "Untitled Elastic Alert"
        )

        # Severity: alert-level override first, then rule-level
        raw_severity = (
            _get(raw, "kibana.alert.severity")
            or _get(raw, "kibana.alert.rule.severity")
            or ""
        )
        severity = _SEVERITY_MAP.get(str(raw_severity).lower(), AlertSeverity.PENDING)

        # occurred_at: kibana.alert.start (event time), fall back to @timestamp
        occurred_at_str = _get(raw, "kibana.alert.start") or _get(raw, "@timestamp")
        if occurred_at_str:
            try:
                occurred_at = datetime.fromisoformat(
                    str(occurred_at_str).replace("Z", "+00:00")
                )
            except ValueError:
                occurred_at = datetime.now().astimezone()
        else:
            occurred_at = datetime.now().astimezone()

        # Description: prefer rule description, fall back to reason
        description = (
            _get(raw, "kibana.alert.rule.description")
            or _get(raw, "kibana.alert.reason")
            or None
        )
        # If description equals title, prefer reason as description
        if description and description == str(title):
            description = _get(raw, "kibana.alert.reason") or None

        # Tags from rule tags
        tags: list[str] = []
        rule_tags = _get(raw, "kibana.alert.rule.tags")
        if isinstance(rule_tags, list):
            tags = [str(t) for t in rule_tags if t]

        return CalsetaAlert(
            title=str(title),
            severity=severity,
            occurred_at=occurred_at,
            source_name=self.source_name,
            description=str(description) if description else None,
            tags=tags,
        )

    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]:  # type: ignore[type-arg]
        """
        Extract IOCs from ECS fields in the Elastic alert.

        Handles: source.ip, destination.ip, destination.domain, dns.question.name,
        process.hash.sha256, file.hash.sha256, user.email, user.name,
        host.ip (array), url.full, threat.indicator.* fields.
        """
        indicators: list[IndicatorExtract] = []

        def _add_ip(value: Any, field: str) -> None:
            if isinstance(value, list):
                for v in value:
                    if isinstance(v, str) and v:
                        indicators.append(
                            IndicatorExtract(type=IndicatorType.IP, value=v, source_field=field)
                        )
            elif isinstance(value, str) and value:
                indicators.append(
                    IndicatorExtract(type=IndicatorType.IP, value=value, source_field=field)
                )

        def _add(itype: IndicatorType, field: str) -> None:
            value = _get(raw, field)
            if isinstance(value, str) and value:
                indicators.append(IndicatorExtract(type=itype, value=value, source_field=field))

        # IP indicators
        _add_ip(_get(raw, "source.ip"), "source.ip")
        _add_ip(_get(raw, "destination.ip"), "destination.ip")
        _add_ip(_get(raw, "host.ip"), "host.ip")
        _add_ip(_get(raw, "threat.indicator.ip"), "threat.indicator.ip")

        # Domain indicators
        _add(IndicatorType.DOMAIN, "destination.domain")
        _add(IndicatorType.DOMAIN, "dns.question.name")
        _add(IndicatorType.DOMAIN, "url.domain")
        _add(IndicatorType.DOMAIN, "threat.indicator.domain")

        # URL indicators
        _add(IndicatorType.URL, "url.full")

        # Hash indicators
        _add(IndicatorType.HASH_SHA256, "process.hash.sha256")
        _add(IndicatorType.HASH_SHA256, "file.hash.sha256")
        _add(IndicatorType.HASH_SHA256, "threat.indicator.file.hash.sha256")
        _add(IndicatorType.HASH_SHA1, "process.hash.sha1")
        _add(IndicatorType.HASH_SHA1, "file.hash.sha1")
        _add(IndicatorType.HASH_MD5, "process.hash.md5")
        _add(IndicatorType.HASH_MD5, "file.hash.md5")

        # Account indicators
        _add(IndicatorType.EMAIL, "user.email")
        _add(IndicatorType.ACCOUNT, "user.name")

        return indicators

    def extract_detection_rule_ref(self, raw: dict) -> str | None:  # type: ignore[type-arg]
        """Return the Elastic rule UUID from kibana.alert.rule.uuid."""
        value = _get(raw, "kibana.alert.rule.uuid")
        return str(value) if value else None

    def verify_webhook_signature(self, headers: dict[str, str], raw_body: bytes) -> bool:
        """
        Verify HMAC-SHA256 signature in the X-Elastic-Signature header.

        Returns True if secret is not configured.
        Returns False if secret is set but signature is absent or invalid.
        """
        secret = settings.ELASTIC_WEBHOOK_SECRET
        if not secret:
            return True

        signature_header = (
            headers.get("X-Elastic-Signature")
            or headers.get("x-elastic-signature")
            or ""
        )
        if not signature_header:
            logger.warning("elastic_webhook_missing_signature")
            return False

        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        received = signature_header.removeprefix("sha256=")
        return hmac.compare_digest(expected, received)

    def documented_extractions(self) -> list[SourcePluginExtraction]:
        _e = SourcePluginExtraction
        return [
            _e("source.ip", "ip", "Source IP (ECS)"),
            _e("destination.ip", "ip", "Destination IP (ECS)"),
            _e("host.ip", "ip", "Host IP (ECS, array)"),
            _e("threat.indicator.ip", "ip", "Threat indicator IP"),
            _e("destination.domain", "domain", "Destination domain"),
            _e("dns.question.name", "domain", "DNS query name"),
            _e("url.domain", "domain", "URL domain"),
            _e("threat.indicator.domain", "domain", "Threat indicator domain"),
            _e("url.full", "url", "Full URL (ECS)"),
            _e("process.hash.sha256", "hash_sha256", "Process SHA-256"),
            _e("file.hash.sha256", "hash_sha256", "File SHA-256"),
            _e("threat.indicator.file.hash.sha256", "hash_sha256", "Threat indicator file SHA-256"),
            _e("process.hash.sha1", "hash_sha1", "Process SHA-1"),
            _e("file.hash.sha1", "hash_sha1", "File SHA-1"),
            _e("process.hash.md5", "hash_md5", "Process MD5"),
            _e("file.hash.md5", "hash_md5", "File MD5"),
            _e("user.email", "email", "User email (ECS)"),
            _e("user.name", "account", "User name (ECS)"),
        ]
