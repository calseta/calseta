"""Pydantic schemas for LLM integration management."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import JSONB_SIZE_SMALL, validate_jsonb_size


class LLMProvider(StrEnum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    OLLAMA = "ollama"
    CLAUDE_CODE = "claude_code"
    AWS_BEDROCK = "aws_bedrock"


class LLMIntegrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    provider: LLMProvider
    model: str = Field(..., min_length=1, max_length=255)
    api_key_ref: str | None = None
    base_url: str | None = None
    config: dict[str, Any] | None = None
    cost_per_1k_input_tokens_cents: int = Field(default=0, ge=0)
    cost_per_1k_output_tokens_cents: int = Field(default=0, ge=0)
    is_default: bool = False

    @field_validator("config")
    @classmethod
    def _validate_config_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_SMALL, "config")  # type: ignore[return-value]

    @model_validator(mode="after")
    def _validate_base_url_for_azure(self) -> LLMIntegrationCreate:
        if self.provider == LLMProvider.AZURE_OPENAI and not self.base_url:
            raise ValueError("base_url is required for azure_openai provider")
        return self


class LLMIntegrationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    provider: LLMProvider | None = None
    model: str | None = Field(default=None, min_length=1, max_length=255)
    api_key_ref: str | None = None
    base_url: str | None = None
    config: dict[str, Any] | None = None
    cost_per_1k_input_tokens_cents: int | None = Field(default=None, ge=0)
    cost_per_1k_output_tokens_cents: int | None = Field(default=None, ge=0)
    is_default: bool | None = None

    @field_validator("config")
    @classmethod
    def _validate_config_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        return validate_jsonb_size(v, JSONB_SIZE_SMALL, "config")  # type: ignore[return-value]


class LLMIntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    name: str
    provider: str
    model: str
    api_key_ref_set: bool
    base_url: str | None
    config: dict[str, Any] | None
    cost_per_1k_input_tokens_cents: int
    cost_per_1k_output_tokens_cents: int
    is_default: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm(cls, obj: Any) -> LLMIntegrationResponse:
        return cls(
            uuid=obj.uuid,
            name=obj.name,
            provider=obj.provider,
            model=obj.model,
            api_key_ref_set=obj.api_key_ref is not None,
            base_url=obj.base_url,
            config=obj.config,
            cost_per_1k_input_tokens_cents=obj.cost_per_1k_input_tokens_cents,
            cost_per_1k_output_tokens_cents=obj.cost_per_1k_output_tokens_cents,
            is_default=obj.is_default,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class LLMUsageResponse(BaseModel):
    llm_integration_uuid: uuid.UUID
    from_dt: datetime
    to_dt: datetime
    total_input_tokens: int
    total_output_tokens: int
    total_cost_cents: int
    event_count: int
    billing_types: dict[str, int]
