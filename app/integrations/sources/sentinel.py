"""
Microsoft Sentinel source integration.

Normalizes Sentinel incident webhook payloads to the Calseta agent-native schema.
Sentinel sends the full incident JSON (same schema as the REST API GET response)
via Logic Apps automation rules.

Field mapping reference: docs/integrations/sentinel/api_notes.md
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime

import structlog

from app.config import settings
from app.integrations.sources.base import AlertSourceBase
from app.schemas.alert import AlertSeverity, CalsetaAlert
from app.schemas.indicators import IndicatorExtract, IndicatorType

logger = structlog.get_logger(__name__)

# Sentinel severity → Calseta severity
_SEVERITY_MAP: dict[str, AlertSeverity] = {
    "High": AlertSeverity.HIGH,
    "Medium": AlertSeverity.MEDIUM,
    "Low": AlertSeverity.LOW,
    "Informational": AlertSeverity.INFORMATIONAL,
    "None": AlertSeverity.INFORMATIONAL,
}


class SentinelSource(AlertSourceBase):
    """Alert source plugin for Microsoft Sentinel incident webhooks."""

    source_name = "sentinel"
    display_name = "Microsoft Sentinel"

    def validate_payload(self, raw: dict) -> bool:  # type: ignore[type-arg]
        """
        Return True if the payload looks like a Sentinel incident.
        Checks for the required top-level structure and properties sub-object.
        """
        try:
            props = raw.get("properties")
            if not isinstance(props, dict):
                return False
            return bool(props.get("title") or props.get("severity"))
        except Exception:
            return False

    def normalize(self, raw: dict) -> CalsetaAlert:  # type: ignore[type-arg]
        """Map Sentinel incident fields to CalsetaAlert."""
        props = raw.get("properties", {})

        title = props.get("title", "Untitled Sentinel Incident")

        raw_severity = props.get("severity", "None")
        severity = _SEVERITY_MAP.get(raw_severity, AlertSeverity.PENDING)

        # Prefer firstActivityTimeUtc (when attack occurred) over createdTimeUtc
        occurred_at_str = props.get("firstActivityTimeUtc") or props.get("createdTimeUtc")
        if occurred_at_str:
            try:
                occurred_at = datetime.fromisoformat(
                    occurred_at_str.replace("Z", "+00:00")
                )
            except ValueError:
                occurred_at = datetime.now().astimezone()
        else:
            occurred_at = datetime.now().astimezone()

        # Tags from labels
        tags: list[str] = []
        for label in props.get("labels", []):
            if isinstance(label, dict) and label.get("labelName"):
                tags.append(label["labelName"])

        return CalsetaAlert(
            title=title,
            severity=severity,
            occurred_at=occurred_at,
            source_name=self.source_name,
            tags=tags,
        )

    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]:  # type: ignore[type-arg]
        """
        Extract IOCs from the Sentinel Entities array.

        Entity types handled: ip, account, host, url, filehash.
        """
        indicators: list[IndicatorExtract] = []
        entities = raw.get("Entities", [])

        for entity in entities:
            if not isinstance(entity, dict):
                continue
            entity_type = (entity.get("Type") or entity.get("type") or "").lower()

            def _ind(itype: IndicatorType, val: str, field: str) -> None:
                indicators.append(IndicatorExtract(type=itype, value=val, source_field=field))

            if entity_type == "ip":
                address = entity.get("Address") or entity.get("address")
                if address:
                    _ind(IndicatorType.IP, address, "Entities.ip")

            elif entity_type == "account":
                # Build account as username@domain or just username
                name = entity.get("Name") or entity.get("name") or ""
                domain = entity.get("UPNSuffix") or entity.get("upnSuffix") or ""
                if name:
                    account_val = f"{name}@{domain}" if domain else name
                    _ind(IndicatorType.ACCOUNT, account_val, "Entities.account")

            elif entity_type == "host":
                hostname = entity.get("HostName") or entity.get("hostName") or ""
                dns_domain = entity.get("DnsDomain") or entity.get("dnsDomain") or ""
                if hostname:
                    fqdn = f"{hostname}.{dns_domain}" if dns_domain else hostname
                    _ind(IndicatorType.DOMAIN, fqdn, "Entities.host")

            elif entity_type == "url":
                url = entity.get("Url") or entity.get("url")
                if url:
                    _ind(IndicatorType.URL, url, "Entities.url")

            elif entity_type == "filehash":
                algorithm = (entity.get("Algorithm") or entity.get("algorithm") or "").upper()
                fh_value = entity.get("Value") or entity.get("value") or ""
                if fh_value:
                    _hash_type = {
                        "SHA256": IndicatorType.HASH_SHA256,
                        "SHA1": IndicatorType.HASH_SHA1,
                        "MD5": IndicatorType.HASH_MD5,
                    }.get(algorithm)
                    if _hash_type:
                        _ind(_hash_type, fh_value, "Entities.filehash")

        return indicators

    def extract_detection_rule_ref(self, raw: dict) -> str | None:  # type: ignore[type-arg]
        """
        Return the last UUID segment from the first relatedAnalyticRuleId ARM path.

        ARM path format: /subscriptions/{sub}/.../alertRules/{ruleId}
        We extract only the ruleId UUID as the detection_rule_ref.
        """
        props = raw.get("properties", {})
        rule_ids = props.get("relatedAnalyticRuleIds", [])
        if not rule_ids:
            return None
        # Take the first rule ID and extract the last path segment
        first = rule_ids[0]
        segments = first.rstrip("/").split("/")
        return segments[-1] if segments else None

    def verify_webhook_signature(self, headers: dict[str, str], raw_body: bytes) -> bool:
        """
        Verify HMAC-SHA256 signature sent in the X-Sentinel-Signature header.

        Returns True if secret is not configured (allows unconfigured deployments).
        Returns False if secret is set but signature is absent or invalid.
        """
        secret = settings.SENTINEL_WEBHOOK_SECRET
        if not secret:
            return True

        signature_header = (
            headers.get("X-Sentinel-Signature")
            or headers.get("x-sentinel-signature")
            or ""
        )
        if not signature_header:
            logger.warning("sentinel_webhook_missing_signature")
            return False

        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        # Strip optional "sha256=" prefix
        received = signature_header.removeprefix("sha256=")
        return hmac.compare_digest(expected, received)
