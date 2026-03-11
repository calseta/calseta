"""Agent registration API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import JSONB_SIZE_SMALL, validate_jsonb_size


class AgentRegistrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    endpoint_url: str
    auth_header_name: str | None = None
    auth_header_value: str | None = None  # plaintext; encrypted before storage
    trigger_on_sources: list[str] = Field(default_factory=list)
    trigger_on_severities: list[str] = Field(default_factory=list)
    trigger_filter: dict[str, Any] | None = None
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    retry_count: int = Field(default=3, ge=0, le=10)
    is_active: bool = True
    documentation: str | None = None

    @field_validator("trigger_filter")
    @classmethod
    def _validate_trigger_filter_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_SMALL, "trigger_filter")  # type: ignore[return-value]

    @model_validator(mode="after")
    def _validate_auth_header_pair(self) -> AgentRegistrationCreate:
        name_set = self.auth_header_name is not None
        value_set = self.auth_header_value is not None
        if name_set != value_set:
            raise ValueError(
                "auth_header_name and auth_header_value must both be provided or both be omitted"
            )
        return self


class AgentRegistrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    name: str
    description: str | None
    endpoint_url: str
    auth_header_name: str | None
    # auth_header_value is NEVER returned
    trigger_on_sources: list[str]
    trigger_on_severities: list[str]
    trigger_filter: dict[str, Any] | None
    timeout_seconds: int
    retry_count: int
    is_active: bool
    documentation: str | None
    created_at: datetime
    updated_at: datetime


class AgentRegistrationPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    endpoint_url: str | None = None
    auth_header_name: str | None = None
    auth_header_value: str | None = None
    trigger_on_sources: list[str] | None = None
    trigger_on_severities: list[str] | None = None
    trigger_filter: dict[str, Any] | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    retry_count: int | None = Field(default=None, ge=0, le=10)
    is_active: bool | None = None
    documentation: str | None = None

    @field_validator("trigger_filter")
    @classmethod
    def _validate_trigger_filter_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_SMALL, "trigger_filter")  # type: ignore[return-value]


class AgentTestResponse(BaseModel):
    delivered: bool
    status_code: int | None = None
    duration_ms: int
    error: str | None = None
