"""
Alert API request/response schemas.

Separate from app/schemas/alert.py (CalsetaAlert = ingestion schema).
These are the HTTP-facing shapes for CRUD operations on alerts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.alert import AlertCloseClassification, AlertSeverity, AlertStatus, EnrichmentStatus
from app.schemas.common import JSONB_SIZE_SMALL, validate_jsonb_size
from app.schemas.detection_rules import DetectionRuleResponse
from app.schemas.kb import KBPageContextSummary
from app.schemas.indicators import EnrichedIndicator, MaliceLevel


class AlertMetadata(BaseModel):
    """
    Computed metadata block included in GET /v1/alerts/{uuid} responses.
    Generated at serialization time — no additional DB columns needed.
    """

    generated_at: datetime
    alert_source: str
    indicator_count: int
    enrichment: dict[str, Any]  # succeeded, failed, enriched_at
    detection_rule_matched: bool
    kb_pages_applied: int


class AlertResponse(BaseModel):
    """Full alert response — returned by GET /v1/alerts/{uuid}."""

    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    title: str
    description: str | None = None
    severity: AlertSeverity
    status: AlertStatus
    enrichment_status: EnrichmentStatus
    source_name: str
    occurred_at: datetime
    ingested_at: datetime
    enriched_at: datetime | None
    is_enriched: bool
    fingerprint: str | None
    duplicate_count: int = 0
    last_seen_at: datetime | None = None
    close_classification: AlertCloseClassification | None
    acknowledged_at: datetime | None
    triaged_at: datetime | None
    closed_at: datetime | None
    tags: list[str]
    detection_rule_id: int | None
    malice: str | None = None  # Computed: override > worst-of-indicators > "Pending"
    malice_override: str | None = None
    malice_override_source: str | None = None
    malice_override_at: datetime | None = None
    indicators: list[EnrichedIndicator] = Field(default_factory=list)
    detection_rule: DetectionRuleResponse | None = None
    kb_pages: list[KBPageContextSummary] = Field(default_factory=list)
    agent_findings: list[dict[str, Any]] | None = None
    created_at: datetime
    updated_at: datetime


class AlertSummary(BaseModel):
    """Compact alert for list views — GET /v1/alerts."""

    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    title: str
    description: str | None = None
    severity: AlertSeverity
    status: AlertStatus
    enrichment_status: EnrichmentStatus
    source_name: str
    occurred_at: datetime
    ingested_at: datetime
    is_enriched: bool
    duplicate_count: int = 0
    tags: list[str]
    close_classification: str | None = None
    closed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AlertPatch(BaseModel):
    """
    Patch request for updating an alert — PATCH /v1/alerts/{uuid}.
    All fields optional. If status=Closed, close_classification is required.
    """

    status: AlertStatus | None = None
    severity: AlertSeverity | None = None
    close_classification: AlertCloseClassification | None = None
    tags: list[str] | None = None
    malice_override: MaliceLevel | None = None
    reset_malice_override: bool = False


class FindingConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FindingCreate(BaseModel):
    """Agent finding posted to POST /v1/alerts/{uuid}/findings."""

    agent_name: str = Field(..., min_length=1, max_length=255)
    summary: str = Field(..., min_length=1, max_length=50_000)
    confidence: FindingConfidence | None = None
    recommended_action: str | None = None
    evidence: dict[str, Any] | None = None

    @field_validator("evidence")
    @classmethod
    def _validate_evidence_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_SMALL, "evidence")  # type: ignore[return-value]


class FindingResponse(BaseModel):
    """Response from POST /v1/alerts/{uuid}/findings and items in GET list."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_name: str
    summary: str
    confidence: FindingConfidence | None
    recommended_action: str | None
    evidence: dict[str, Any] | None
    posted_at: datetime
