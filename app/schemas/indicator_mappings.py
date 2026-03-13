"""
Pydantic schemas for indicator field mapping management endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IndicatorFieldMappingCreate(BaseModel):
    source_name: str | None = Field(
        None,
        description=(
            "Restrict to a specific alert source (null = applies to all sources)"
        ),
    )
    field_path: str = Field(
        ...,
        description=(
            "Dot-notation path into extraction_target "
            "(e.g. 'src_ip' or 'okta.data.client.ipAddress')"
        ),
    )
    indicator_type: str = Field(
        ...,
        description=(
            "Indicator type: ip, domain, hash_md5, hash_sha1, "
            "hash_sha256, url, email, account"
        ),
    )
    extraction_target: str = Field(
        "normalized",
        description=(
            "'normalized' (against CalsetaAlert fields) "
            "or 'raw_payload' (against source raw data)"
        ),
    )
    is_active: bool = Field(True, description="Whether this mapping is active")
    description: str | None = Field(None, description="Human-readable description")


class IndicatorFieldMappingPatch(BaseModel):
    field_path: str | None = None
    indicator_type: str | None = None
    is_active: bool | None = None
    description: str | None = None


class IndicatorFieldMappingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    source_name: str | None
    field_path: str
    indicator_type: str
    extraction_target: str
    is_system: bool
    is_active: bool
    description: str | None
    created_at: datetime
    updated_at: datetime


# --- Test Extraction (dry-run) ---


class TestExtractionRequest(BaseModel):
    source_name: str
    raw_payload: dict[str, Any]


class TestExtractionIndicator(BaseModel):
    type: str
    value: str
    source_field: str | None = None


class TestExtractionPassResult(BaseModel):
    pass_name: str
    pass_label: str
    indicators: list[TestExtractionIndicator]
    error: str | None = None


class TestExtractionResponse(BaseModel):
    success: bool
    source_name: str
    passes: list[TestExtractionPassResult]
    deduplicated: list[TestExtractionIndicator]
    deduplicated_count: int
    normalization_preview: dict[str, Any] | None = None
    error_message: str | None = None
    duration_ms: int = 0
