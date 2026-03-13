"""Pydantic schemas for enrichment provider CRUD API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import JSONB_SIZE_MEDIUM, validate_jsonb_size


class EnrichmentProviderCreate(BaseModel):
    """Request body for POST /v1/enrichment-providers."""

    provider_name: str = Field(
        ..., min_length=1, max_length=100, pattern=r"^[a-z0-9_]+$"
    )
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    supported_indicator_types: list[str] = Field(..., min_length=1)
    http_config: dict[str, Any] = Field(...)
    auth_type: str = Field(default="no_auth")
    auth_config: dict[str, Any] | None = None
    default_cache_ttl_seconds: int = Field(default=3600, ge=0, le=86400)
    cache_ttl_by_type: dict[str, int] | None = None
    malice_rules: dict[str, Any] | None = None

    @field_validator("http_config")
    @classmethod
    def _validate_http_config_size(cls, v: dict[str, Any]) -> dict[str, Any]:
        return validate_jsonb_size(v, JSONB_SIZE_MEDIUM, "http_config")  # type: ignore[return-value]

    @field_validator("auth_config")
    @classmethod
    def _validate_auth_config_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_MEDIUM, "auth_config")  # type: ignore[return-value]

    @field_validator("malice_rules")
    @classmethod
    def _validate_malice_rules_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_MEDIUM, "malice_rules")  # type: ignore[return-value]


class EnrichmentProviderPatch(BaseModel):
    """Request body for PATCH /v1/enrichment-providers/{uuid}."""

    display_name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None
    supported_indicator_types: list[str] | None = None
    http_config: dict[str, Any] | None = None
    auth_type: str | None = None
    auth_config: dict[str, Any] | None = None
    default_cache_ttl_seconds: int | None = Field(None, ge=0, le=86400)
    cache_ttl_by_type: dict[str, int] | None = None
    malice_rules: dict[str, Any] | None = None

    @field_validator("http_config")
    @classmethod
    def _validate_http_config_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_MEDIUM, "http_config")  # type: ignore[return-value]

    @field_validator("auth_config")
    @classmethod
    def _validate_auth_config_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_MEDIUM, "auth_config")  # type: ignore[return-value]

    @field_validator("malice_rules")
    @classmethod
    def _validate_malice_rules_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_MEDIUM, "malice_rules")  # type: ignore[return-value]


class EnrichmentProviderResponse(BaseModel):
    """Response schema for enrichment provider endpoints."""

    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    provider_name: str
    display_name: str
    description: str | None = None
    is_builtin: bool
    is_active: bool
    supported_indicator_types: list[str]
    http_config: dict[str, Any]
    auth_type: str
    has_credentials: bool = False
    is_configured: bool = False
    env_var_mapping: dict[str, str] | None = None
    default_cache_ttl_seconds: int
    cache_ttl_by_type: dict[str, int] | None = None
    malice_rules: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class EnrichmentProviderTestRequest(BaseModel):
    """Request body for POST /v1/enrichment-providers/{uuid}/test."""

    indicator_type: str
    indicator_value: str


class HttpStepDebug(BaseModel):
    """Per-step HTTP request/response debug info for test results."""

    step_name: str
    step_index: int
    indicator_value: str | None = None
    # Request
    request_method: str
    request_url: str
    request_headers: dict[str, str]
    request_query_params: dict[str, str] | None = None
    request_body: Any | None = None
    # Response
    response_status_code: int | None = None
    response_headers: dict[str, str] | None = None
    response_body: Any | None = None
    # Meta
    duration_ms: int = 0
    error: str | None = None
    skipped: bool = False


class EnrichmentProviderTestResponse(BaseModel):
    """Response body for the test endpoint."""

    success: bool
    provider_name: str
    indicator_type: str
    indicator_value: str
    extracted: dict[str, Any] | None = None
    raw_response: dict[str, Any] | None = None
    error_message: str | None = None
    duration_ms: int = 0
    steps: list[HttpStepDebug] | None = None
