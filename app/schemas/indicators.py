"""Indicator types and IOC extraction schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


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
    enrichment_results: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
