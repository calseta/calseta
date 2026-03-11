"""
AlertSourceBase — abstract base class for all alert source integrations.

Every source plugin (Sentinel, Elastic, Splunk, Generic) must subclass this
and implement the four abstract methods. The two non-abstract methods
(extract_detection_rule_ref, verify_webhook_signature) have safe defaults
that work out of the box without any source-specific logic.

Extension pattern:
    1. Create app/integrations/sources/{name}.py
    2. Subclass AlertSourceBase, set source_name and display_name class attrs
    3. Implement validate_payload, normalize, extract_indicators
    4. Optionally override extract_detection_rule_ref and verify_webhook_signature
    5. Import and register in app/integrations/sources/__init__.py

See docs/guides/HOW_TO_ADD_ALERT_SOURCE.md for the full walkthrough.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import structlog

from app.schemas.alert import CalsetaAlert
from app.schemas.indicators import IndicatorExtract

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SourcePluginExtraction:
    """Metadata describing a field extraction hardcoded in a source plugin."""

    field_path: str
    indicator_type: str
    description: str


class AlertSourceBase(ABC):
    """
    Abstract base class for Calseta alert source plugins.

    Each concrete subclass represents one alert source (SIEM / security tool).
    The source plugin is responsible for:
      - Validating that an incoming webhook payload is from this source
      - Normalizing the raw payload to the Calseta agent-native schema
      - Extracting indicators of compromise from the raw payload (Pass 1)
      - Optionally verifying HMAC webhook signatures
    """

    #: Unique lowercase identifier. Used in route paths: POST /v1/ingest/{source_name}
    source_name: str

    #: Human-readable name for display in API responses and logs.
    display_name: str

    @abstractmethod
    def validate_payload(self, raw: dict) -> bool:  # type: ignore[type-arg]
        """
        Return True if the raw payload looks like a valid alert from this source.

        Must not raise — catch all exceptions and return False.
        Called before normalize() to guard against malformed payloads.
        """
        ...

    @abstractmethod
    def normalize(self, raw: dict) -> CalsetaAlert:  # type: ignore[type-arg]
        """
        Map the raw source payload to the Calseta agent-native schema.

        Source-specific fields that do not map to CalsetaAlert are preserved
        in raw_payload by the ingest service layer — this method must not
        try to capture them.

        The returned CalsetaAlert must have source_name set to self.source_name.
        """
        ...

    @abstractmethod
    def extract_indicators(self, raw: dict) -> list[IndicatorExtract]:  # type: ignore[type-arg]
        """
        Extract indicators of compromise from the raw source payload (Pass 1).

        Returns a list of IndicatorExtract objects. Must not raise — return an
        empty list if extraction fails or yields no results.
        """
        ...

    def extract_detection_rule_ref(self, raw: dict) -> str | None:  # type: ignore[type-arg]
        """
        Return a source-specific detection rule identifier from the raw payload.

        The returned string is used to look up or auto-create a DetectionRule
        record and associate it with the ingested alert.

        Default implementation returns None (no rule association). Override
        in sources that provide rule references (e.g. Sentinel rule ID,
        Elastic kibana.alert.rule.uuid, Splunk saved search name).
        """
        return None

    def verify_webhook_signature(self, headers: dict[str, str], raw_body: bytes) -> bool:
        """
        Verify the HMAC signature on an incoming webhook request.

        Called before validate_payload(). If this returns False, the ingest
        endpoint returns 401 without parsing the payload.

        Default implementation returns True and logs a warning — safe for
        sources that do not implement signing, but leaves no security gap
        because callers can still configure secret-based verification.

        Override this method to implement HMAC-SHA256 verification using
        hmac.compare_digest() (never ==).
        """
        logger.warning(
            "webhook_signature_verification_not_implemented",
            source_name=self.source_name,
        )
        return True

    def documented_extractions(self) -> list[SourcePluginExtraction]:
        """
        Return metadata describing what this source plugin extracts in Pass 1.

        Override in each source to document the hardcoded extraction fields.
        Default returns an empty list.
        """
        return []
