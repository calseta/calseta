"""
Pydantic schemas for API key management endpoints.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

API_KEY_TYPES = frozenset({"human", "agent"})


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable label")
    scopes: list[str] = Field(..., min_length=1, description="Granted scopes")
    key_type: str = Field("human", description="Key type: 'human' or 'agent'")
    expires_at: datetime | None = Field(None, description="Optional expiry (UTC ISO 8601)")
    allowed_sources: list[str] | None = Field(
        None, description="Restrict ingestion to these source names (null = unrestricted)"
    )

    @field_validator("key_type")
    @classmethod
    def _validate_key_type(cls, v: str) -> str:
        if v not in API_KEY_TYPES:
            raise ValueError(f"key_type must be one of: {sorted(API_KEY_TYPES)}")
        return v


class APIKeyCreated(BaseModel):
    """Returned only by POST /v1/api-keys. Contains the full plain-text key (shown once)."""

    uuid: UUID
    name: str
    key_prefix: str
    key: str = Field(..., description="Full API key — store securely, never shown again")
    scopes: list[str]
    key_type: str
    is_active: bool
    created_at: datetime
    expires_at: datetime | None
    allowed_sources: list[str] | None


class APIKeyUpdate(BaseModel):
    """PATCH /v1/api-keys/{uuid} — update mutable fields."""

    scopes: list[str] | None = Field(None, description="Replace scopes list")
    allowed_sources: list[str] | None = Field(
        None, description="Restrict to these sources (null = unrestricted)"
    )
    is_active: bool | None = Field(None, description="Set to false to revoke")


class APIKeyResponse(BaseModel):
    """All endpoints other than creation — full key is never included."""

    uuid: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    key_type: str
    is_active: bool
    created_at: datetime
    expires_at: datetime | None
    last_used_at: datetime | None
    allowed_sources: list[str] | None
