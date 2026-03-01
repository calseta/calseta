"""
Generic webhook source integration.

Accepts arbitrary JSON alert payloads with minimal required fields.
Designed as a catch-all for sources that don't have a dedicated plugin.

Required payload fields:
  - title (str): alert title

Optional fields:
  - severity (str): Pending/Informational/Low/Medium/High/Critical
  - occurred_at (str): ISO 8601 timestamp
  - tags (list[str]): arbitrary tags
  - indicators (list[dict]): explicit IOCs with {type, value} pairs
  - Any additional fields are preserved in raw_payload.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime

from app.integrations.sources.base import AlertSourceBase
from app.schemas.alert import AlertSeverity, CalsetaAlert
from app.schemas.indicators import IndicatorExtract, IndicatorType

_SEVERITY_MAP: dict[str, AlertSeverity] = {
    "critical": AlertSeverity.CRITICAL,
    "high": AlertSeverity.HIGH,
    "medium": AlertSeverity.MEDIUM,
    "low": AlertSeverity.LOW,
    "informational": AlertSeverity.INFORMATIONAL,
    "info": AlertSeverity.INFORMATIONAL,
    "pending": AlertSeverity.PENDING,
}

_INDICATOR_TYPE_MAP: dict[str, IndicatorType] = {
    "ip": IndicatorType.IP,
    "domain": IndicatorType.DOMAIN,
    "hash_md5": IndicatorType.HASH_MD5,
    "hash_sha1": IndicatorType.HASH_SHA1,
    "hash_sha256": IndicatorType.HASH_SHA256,
    "url": IndicatorType.URL,
    "email": IndicatorType.EMAIL,
    "account": IndicatorType.ACCOUNT,
}


class GenericSource(AlertSourceBase):
    """Alert source plugin for generic JSON webhook payloads."""

    source_name = "generic"
    display_name = "Generic Webhook"

    def validate_payload(self, raw: dict) -> bool:  # type: ignore[type-arg]
        """Return True if the payload has at least a title field."""
        try:
            return bool(raw.get("title"))
        except Exception:
            return False

    def normalize(self, raw: dict) -> CalsetaAlert:  # type: ignore[type-arg]
        """Map generic payload fields to CalsetaAlert."""
        title = str(raw.get("title", "Untitled Alert"))

        raw_severity = str(raw.get("severity", "")).lower()
        severity = _SEVERITY_MAP.get(raw_severity, AlertSeverity.PENDING)

        occurred_at = datetime.now(UTC)
        raw_time = raw.get("occurred_at")
        if raw_time:
            with suppress(ValueError, TypeError):
                occurred_at = datetime.fromisoformat(str(raw_time))

        tags = raw.get("tags", [])
        if not isinstance(tags, list):
            tags = []

        return CalsetaAlert(
            title=title,
            severity=severity,
            occurred_at=occurred_at,
            source_name=self.source_name,
            tags=[str(t) for t in tags],
        )

    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]:  # type: ignore[type-arg]
        """
        Extract IOCs from the payload.

        Supports two patterns:
          1. Explicit indicators list: [{"type": "ip", "value": "1.2.3.4"}, ...]
          2. Common top-level field names: src_ip, dest_ip, user, domain, url, etc.
        """
        indicators: list[IndicatorExtract] = []

        # Pattern 1: explicit indicators array
        raw_indicators = raw.get("indicators", [])
        if isinstance(raw_indicators, list):
            for item in raw_indicators:
                if not isinstance(item, dict):
                    continue
                itype_str = str(item.get("type", "")).lower()
                value = item.get("value")
                itype = _INDICATOR_TYPE_MAP.get(itype_str)
                if itype and isinstance(value, str) and value:
                    indicators.append(
                        IndicatorExtract(type=itype, value=value, source_field="indicators[]")
                    )

        # Pattern 2: common field names
        def _add(field: str, itype: IndicatorType) -> None:
            value = raw.get(field)
            if isinstance(value, str) and value:
                indicators.append(
                    IndicatorExtract(type=itype, value=value, source_field=field)
                )

        _add("src_ip", IndicatorType.IP)
        _add("dest_ip", IndicatorType.IP)
        _add("source_ip", IndicatorType.IP)
        _add("destination_ip", IndicatorType.IP)
        _add("ip", IndicatorType.IP)
        _add("domain", IndicatorType.DOMAIN)
        _add("hostname", IndicatorType.DOMAIN)
        _add("url", IndicatorType.URL)
        _add("user", IndicatorType.ACCOUNT)
        _add("username", IndicatorType.ACCOUNT)
        _add("email", IndicatorType.EMAIL)
        _add("md5", IndicatorType.HASH_MD5)
        _add("sha1", IndicatorType.HASH_SHA1)
        _add("sha256", IndicatorType.HASH_SHA256)
        _add("hash", IndicatorType.HASH_SHA256)

        return indicators

    def extract_detection_rule_ref(self, raw: dict) -> str | None:  # type: ignore[type-arg]
        """Return rule_id or rule_name if present in the payload."""
        return raw.get("rule_id") or raw.get("rule_name") or None
