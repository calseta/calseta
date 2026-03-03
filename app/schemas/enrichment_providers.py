"""Pydantic schemas for enrichment provider CRUD API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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


class EnrichmentProviderTestResponse(BaseModel):
    """Response body for the test endpoint."""

    success: bool
    provider_name: str
    indicator_type: str
    indicator_value: str
    extracted: dict[str, Any] | None = None
    error_message: str | None = None
    duration_ms: int = 0
