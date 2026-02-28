"""Enrichment provider result schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


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
