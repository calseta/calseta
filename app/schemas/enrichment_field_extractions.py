"""Pydantic schemas for enrichment field extraction CRUD API."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

VALID_VALUE_TYPES = {"string", "int", "float", "bool", "list", "dict", "any"}
VALID_INDICATOR_TYPES = {
    "ip",
    "domain",
    "hash_md5",
    "hash_sha1",
    "hash_sha256",
    "url",
    "email",
    "account",
}


class EnrichmentFieldExtractionCreate(BaseModel):
    """Request body for creating an enrichment field extraction."""

    provider_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Provider this extraction belongs to",
    )
    indicator_type: str = Field(
        ...,
        description=(
            "Indicator type: ip, domain, hash_md5, hash_sha1, "
            "hash_sha256, url, email, account"
        ),
    )
    source_path: str = Field(
        ...,
        min_length=1,
        description="Dot-notation path into the raw enrichment response",
    )
    target_key: str = Field(
        ...,
        min_length=1,
        description="Key in the extracted dict surfaced to agents",
    )
    value_type: str = Field(
        "string",
        description="One of: string, int, float, bool, list, dict, any",
    )
    description: str | None = Field(None, description="Human-readable description")

    @field_validator("indicator_type")
    @classmethod
    def validate_indicator_type(cls, v: str) -> str:
        if v not in VALID_INDICATOR_TYPES:
            raise ValueError(
                f"indicator_type must be one of: {', '.join(sorted(VALID_INDICATOR_TYPES))}"
            )
        return v

    @field_validator("value_type")
    @classmethod
    def validate_value_type(cls, v: str) -> str:
        if v not in VALID_VALUE_TYPES:
            raise ValueError(
                f"value_type must be one of: {', '.join(sorted(VALID_VALUE_TYPES))}"
            )
        return v


class EnrichmentFieldExtractionPatch(BaseModel):
    """Request body for PATCH /v1/enrichment-field-extractions/{uuid}."""

    source_path: str | None = None
    target_key: str | None = None
    value_type: str | None = None
    is_active: bool | None = None
    description: str | None = None

    @field_validator("value_type")
    @classmethod
    def validate_value_type(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_VALUE_TYPES:
            raise ValueError(
                f"value_type must be one of: {', '.join(sorted(VALID_VALUE_TYPES))}"
            )
        return v


class EnrichmentFieldExtractionResponse(BaseModel):
    """Response schema for enrichment field extraction endpoints."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    provider_name: str
    indicator_type: str
    source_path: str
    target_key: str
    value_type: str
    is_system: bool
    is_active: bool
    description: str | None
    created_at: datetime
    updated_at: datetime


class EnrichmentFieldExtractionBulkCreate(BaseModel):
    """Request body for bulk-creating enrichment field extractions."""

    extractions: list[EnrichmentFieldExtractionCreate] = Field(
        ..., min_length=1, max_length=100
    )
