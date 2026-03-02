"""Indicator types and IOC extraction schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class IndicatorType(StrEnum):
    """Supported indicator-of-compromise (IOC) types."""

    IP = "ip"
    DOMAIN = "domain"
    HASH_MD5 = "hash_md5"
    HASH_SHA1 = "hash_sha1"
    HASH_SHA256 = "hash_sha256"
    URL = "url"
    EMAIL = "email"
    ACCOUNT = "account"


class MaliceLevel(StrEnum):
    """Indicator malice verdict — shared validation enum."""

    PENDING = "Pending"
    BENIGN = "Benign"
    SUSPICIOUS = "Suspicious"
    MALICIOUS = "Malicious"


class IndicatorExtract(BaseModel):
    """
    Raw IOC extracted from an alert payload by a source plugin or field mapping.
    Not yet persisted — intermediate representation used by the extraction pipeline.
    """

    model_config = ConfigDict(from_attributes=True)

    type: IndicatorType
    value: str
    source_field: str | None = None  # Which field this was extracted from (for logging)


class EnrichedIndicator(BaseModel):
    """
    Full indicator as returned to API callers and MCP clients.
    Includes enrichment results and alert association metadata.
    """

    model_config = ConfigDict(from_attributes=True)

    uuid: str
    type: IndicatorType
    value: str
    first_seen: datetime
    last_seen: datetime
    is_enriched: bool
    malice: str  # Pending | Benign | Suspicious | Malicious
    malice_source: str | None = None  # enrichment | analyst
    malice_overridden_at: datetime | None = None
    enrichment_results: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class IndicatorAddItem(BaseModel):
    """Single indicator to add to an alert."""

    type: IndicatorType
    value: str = Field(min_length=1, max_length=2048)


class IndicatorAddRequest(BaseModel):
    """Request body for POST /v1/alerts/{uuid}/indicators."""

    indicators: list[IndicatorAddItem] = Field(min_length=1, max_length=100)


class IndicatorAddResponse(BaseModel):
    """Response for POST /v1/alerts/{uuid}/indicators."""

    added_count: int
    indicators: list[IndicatorResponse]
    enrich_requested: bool


class IndicatorResponse(BaseModel):
    """Indicator as returned by GET /v1/alerts/{uuid}/indicators."""

    model_config = ConfigDict(from_attributes=True)

    uuid: str
    type: IndicatorType
    value: str
    malice: str  # Pending | Benign | Suspicious | Malicious
    malice_source: str | None = None  # enrichment | analyst
    malice_overridden_at: datetime | None = None
    first_seen: datetime
    last_seen: datetime
    is_enriched: bool
    enrichment_results: dict[str, Any] | None = None  # raw excluded per provider
    created_at: datetime
    updated_at: datetime


class IndicatorDetailResponse(BaseModel):
    """Indicator with full enrichment data including raw provider responses."""

    model_config = ConfigDict(from_attributes=True)

    uuid: str
    type: IndicatorType
    value: str
    malice: str  # Pending | Benign | Suspicious | Malicious
    malice_source: str | None = None  # enrichment | analyst
    malice_overridden_at: datetime | None = None
    first_seen: datetime
    last_seen: datetime
    is_enriched: bool
    enrichment_results: dict[str, Any] | None = None  # includes raw per provider
    created_at: datetime
    updated_at: datetime


class IndicatorPatch(BaseModel):
    """Patch request for updating an indicator — PATCH /v1/indicators/{uuid}."""

    malice: MaliceLevel | None = None  # None = reset to enrichment-computed value
