"""Enrichment provider result schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.indicators import IndicatorType


class EnrichmentStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"  # Provider not configured or indicator type not supported


class EnrichmentResult(BaseModel):
    """
    Result returned by an enrichment provider's enrich() method.
    Both success and failure cases are represented here — providers never raise.
    """

    model_config = ConfigDict(from_attributes=True)

    provider_name: str
    status: EnrichmentStatus
    success: bool

    # Populated on success
    extracted: dict[str, Any] | None = None  # Configured field subset (surfaced to agents)
    raw: dict[str, Any] | None = None  # Full API response (stored but not in agent payloads)
    enriched_at: datetime | None = None

    # Populated on failure
    error_message: str | None = None

    @classmethod
    def success_result(
        cls,
        provider_name: str,
        extracted: dict[str, Any],
        raw: dict[str, Any],
        enriched_at: datetime,
    ) -> EnrichmentResult:
        return cls(
            provider_name=provider_name,
            status=EnrichmentStatus.SUCCESS,
            success=True,
            extracted=extracted,
            raw=raw,
            enriched_at=enriched_at,
        )

    @classmethod
    def failure_result(cls, provider_name: str, error: str) -> EnrichmentResult:
        return cls(
            provider_name=provider_name,
            status=EnrichmentStatus.FAILED,
            success=False,
            error_message=error,
        )

    @classmethod
    def skipped_result(cls, provider_name: str, reason: str) -> EnrichmentResult:
        return cls(
            provider_name=provider_name,
            status=EnrichmentStatus.SKIPPED,
            success=False,
            error_message=reason,
        )


# ---------------------------------------------------------------------------
# On-demand enrichment endpoint schemas (POST /v1/enrichments)
# ---------------------------------------------------------------------------


class OnDemandEnrichmentRequest(BaseModel):
    """Request body for POST /v1/enrichments."""

    type: IndicatorType
    value: str


class OnDemandEnrichmentResult(BaseModel):
    """Per-provider result in the on-demand enrichment response."""

    status: EnrichmentStatus
    success: bool
    extracted: dict[str, Any] | None = None
    enriched_at: datetime | None = None
    error_message: str | None = None
    cache_hit: bool = False


class OnDemandEnrichmentResponse(BaseModel):
    """Response body for POST /v1/enrichments."""

    type: IndicatorType
    value: str
    results: dict[str, OnDemandEnrichmentResult]
    enriched_at: datetime


# ---------------------------------------------------------------------------
# Provider listing endpoint schema (GET /v1/enrichments/providers)
# ---------------------------------------------------------------------------


class EnrichmentProviderInfo(BaseModel):
    """Single provider entry for GET /v1/enrichments/providers."""

    provider_name: str
    display_name: str
    supported_types: list[IndicatorType]
    is_configured: bool
    cache_ttl_seconds: int
