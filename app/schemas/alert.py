"""
CalsetaAlert — the agent-native normalized alert schema.

This is the canonical Calseta representation of a security alert.
Source plugins normalize their raw payloads to this schema via normalize().
It is designed for AI agent consumption: readable field names, explicit types,
and structured enrichment context rather than raw API dumps.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlertStatus(StrEnum):
    """
    Alert workflow lifecycle status. Stored as TEXT with Pydantic validation.
    Do NOT use a Postgres ENUM type — TEXT with app-level validation is easier to migrate.

    Transition flow:
        pending_enrichment → enriched → Open → Triaging / Escalated → Closed
    """

    PENDING_ENRICHMENT = "pending_enrichment"
    ENRICHED = "enriched"
    OPEN = "Open"
    TRIAGING = "Triaging"
    ESCALATED = "Escalated"
    CLOSED = "Closed"


class AlertSeverity(StrEnum):
    """
    Alert severity levels. Stored as TEXT with Pydantic validation.
    Source plugins are responsible for mapping source-specific severity values to this enum.
    """

    PENDING = "Pending"
    INFORMATIONAL = "Informational"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class AlertCloseClassification(StrEnum):
    """
    Required when status transitions to Closed. Used for FP rate metrics and detection quality.
    Any value starting with 'False Positive' counts toward the false_positive_rate metric.
    """

    TRUE_POSITIVE = "True Positive - Suspicious Activity"
    BENIGN_POSITIVE = "Benign Positive - Suspicious but Expected"
    FALSE_POSITIVE_LOGIC = "False Positive - Incorrect Detection Logic"
    FALSE_POSITIVE_DATA = "False Positive - Inaccurate Data"
    UNDETERMINED = "Undetermined"
    DUPLICATE = "Duplicate"
    NOT_APPLICABLE = "Not Applicable"


class CalsetaAlert(BaseModel):
    """
    Calseta agent-native normalized alert schema.

    Returned by AlertSourceBase.normalize(). Stored as direct columns on the
    alerts table. Source-specific fields that don't map here are preserved
    in raw_payload by the ingest service layer (not by this schema).

    The 14 extractable fields (src_ip, dst_ip, etc.) are used by the
    Pass 2 indicator extraction pipeline. All are optional — not every alert
    source will have all of them.
    """

    model_config = ConfigDict(from_attributes=True)

    # Required normalized fields
    title: str
    severity: AlertSeverity
    occurred_at: datetime
    source_name: str

    # Optional normalized fields used by Pass 2 indicator extraction
    src_ip: str | None = None
    dst_ip: str | None = None
    src_hostname: str | None = None
    dst_hostname: str | None = None
    file_hash_md5: str | None = None
    file_hash_sha256: str | None = None
    file_hash_sha1: str | None = None
    actor_email: str | None = None
    actor_username: str | None = None
    dns_query: str | None = None
    http_url: str | None = None
    http_hostname: str | None = None
    email_from: str | None = None
    email_reply_to: str | None = None

    # Tags from source
    tags: list[str] = Field(default_factory=list)

    # Additional source context (free-form, not used for extraction)
    extra: dict[str, Any] = Field(default_factory=dict)
