"""
Splunk source integration.

Normalizes Splunk alert webhook payloads to the Calseta agent-native schema.
Splunk sends a JSON envelope with a `result` object containing the alert data.

Two contexts:
  - Splunk Enterprise Security (ES): result includes rule_name, urgency, src_ip, etc.
  - Standard saved search: result contains arbitrary SPL column names.

Signature verification uses a bearer token in X-Splunk-Webhook-Secret header
(no built-in HMAC; see docs/integrations/splunk/api_notes.md).

Field mapping reference: docs/integrations/splunk/api_notes.md
"""

from __future__ import annotations

import hmac
from contextlib import suppress
from datetime import UTC, datetime

import structlog

from app.config import settings
from app.integrations.sources.base import AlertSourceBase, SourcePluginExtraction
from app.schemas.alert import AlertSeverity, CalsetaAlert
from app.schemas.indicators import IndicatorExtract, IndicatorType

logger = structlog.get_logger(__name__)

# Splunk urgency/severity → Calseta severity (lowercase input)
_SEVERITY_MAP: dict[str, AlertSeverity] = {
    "critical": AlertSeverity.CRITICAL,
    "high": AlertSeverity.HIGH,
    "medium": AlertSeverity.MEDIUM,
    "low": AlertSeverity.LOW,
    "informational": AlertSeverity.INFORMATIONAL,
    "info": AlertSeverity.INFORMATIONAL,
}


class SplunkSource(AlertSourceBase):
    """Alert source plugin for Splunk alert webhooks."""

    source_name = "splunk"
    display_name = "Splunk"

    def validate_payload(self, raw: dict) -> bool:  # type: ignore[type-arg]
        """
        Return True if the payload looks like a Splunk alert webhook.
        Requires the top-level `result` object and either search_name or sid.
        """
        try:
            return isinstance(raw.get("result"), dict) and bool(
                raw.get("search_name") or raw.get("sid")
            )
        except Exception:
            return False

    def normalize(self, raw: dict) -> CalsetaAlert:  # type: ignore[type-arg]
        """Map Splunk alert webhook fields to CalsetaAlert."""
        result = raw.get("result", {})

        # Title: prefer rule_name from result (ES), fall back to search_name envelope
        title = (
            result.get("rule_name")
            or result.get("signature")
            or raw.get("search_name")
            or "Untitled Splunk Alert"
        )

        # Severity: urgency is the primary field in ES; fall back to severity
        raw_severity = (
            result.get("urgency")
            or result.get("severity")
            or "low"
        )
        severity = _SEVERITY_MAP.get(str(raw_severity).lower(), AlertSeverity.PENDING)

        # occurred_at: _time is a Unix timestamp string in Splunk
        occurred_at = datetime.now(UTC)
        raw_time = result.get("_time")
        if raw_time:
            with suppress(ValueError, TypeError, OverflowError):
                occurred_at = datetime.fromtimestamp(float(raw_time), tz=UTC)

        description = result.get("signature") or result.get("search_name") or None
        # If description equals title, try _raw field
        if description and description == str(title):
            raw_log = result.get("_raw")
            if raw_log:
                description = str(raw_log)

        return CalsetaAlert(
            title=str(title),
            severity=severity,
            occurred_at=occurred_at,
            source_name=self.source_name,
            description=str(description) if description else None,
        )

    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]:  # type: ignore[type-arg]
        """
        Extract IOCs from Splunk result fields.

        Handles common Splunk ES notable event fields:
        src_ip, dest_ip, user, md5, sha256, sha1, url, domain.
        Also checks src/dest as IP fallbacks.
        """
        indicators: list[IndicatorExtract] = []
        result = raw.get("result", {})

        def _add(field: str, itype: IndicatorType) -> None:
            value = result.get(field)
            if isinstance(value, str) and value:
                indicators.append(
                    IndicatorExtract(type=itype, value=value, source_field=f"result.{field}")
                )

        _add("src_ip", IndicatorType.IP)
        _add("dest_ip", IndicatorType.IP)
        # Fallback IP fields if src_ip/dest_ip not present
        if not result.get("src_ip"):
            _add("src", IndicatorType.IP)
        if not result.get("dest_ip"):
            _add("dest", IndicatorType.IP)
        _add("user", IndicatorType.ACCOUNT)
        _add("sha256", IndicatorType.HASH_SHA256)
        _add("md5", IndicatorType.HASH_MD5)
        _add("sha1", IndicatorType.HASH_SHA1)
        _add("url", IndicatorType.URL)
        _add("domain", IndicatorType.DOMAIN)

        return indicators

    def extract_detection_rule_ref(self, raw: dict) -> str | None:  # type: ignore[type-arg]
        """
        Return the correlation rule name as the detection_rule_ref.

        In ES: result.rule_name is the correlation search name.
        In standard Splunk: use envelope search_name.
        """
        result = raw.get("result", {})
        return (
            result.get("rule_name")
            or raw.get("search_name")
            or None
        )

    def verify_webhook_signature(self, headers: dict[str, str], raw_body: bytes) -> bool:
        """
        Verify the bearer token in X-Splunk-Webhook-Secret header.

        Splunk does not support HMAC signing natively. The secret is compared
        directly against the header value using hmac.compare_digest() to prevent
        timing attacks.

        Returns True if secret is not configured.
        Returns False if secret is set but header is absent or token does not match.
        """
        secret = settings.SPLUNK_WEBHOOK_SECRET
        if not secret:
            return True

        token = (
            headers.get("X-Splunk-Webhook-Secret")
            or headers.get("x-splunk-webhook-secret")
            or ""
        )
        if not token:
            logger.warning("splunk_webhook_missing_signature")
            return False

        return hmac.compare_digest(secret.encode(), token.encode())

    def documented_extractions(self) -> list[SourcePluginExtraction]:
        return [
            SourcePluginExtraction("result.src_ip", "ip", "Source IP"),
            SourcePluginExtraction("result.dest_ip", "ip", "Destination IP"),
            SourcePluginExtraction("result.src", "ip", "Source (IP fallback)"),
            SourcePluginExtraction("result.dest", "ip", "Destination (IP fallback)"),
            SourcePluginExtraction("result.user", "account", "User account"),
            SourcePluginExtraction("result.sha256", "hash_sha256", "SHA-256 hash"),
            SourcePluginExtraction("result.md5", "hash_md5", "MD5 hash"),
            SourcePluginExtraction("result.sha1", "hash_sha1", "SHA-1 hash"),
            SourcePluginExtraction("result.url", "url", "URL"),
            SourcePluginExtraction("result.domain", "domain", "Domain"),
        ]
