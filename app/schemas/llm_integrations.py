"""Pydantic schemas for LLM integration management."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import JSONB_SIZE_SMALL, validate_jsonb_size

# S6: model identifier whitelist — accepts vendor model strings like
# "claude-sonnet-4-6", "gpt-4o", "anthropic/claude-3.5", "us.anthropic:claude-3"
# Rejects leading "-" (so a value can never be confused with a CLI flag) and
# rejects whitespace / shell metacharacters that could affect downstream
# subprocess arg construction.
_MODEL_SLUG_RE = re.compile(r"^[A-Za-z0-9._:\-/]{1,128}$")


def _validate_model_slug(v: str | None) -> str | None:
    """Reject empty/None-or-whitespace, leading "-", and out-of-charset values."""
    if v is None:
        return v
    # Whitespace anywhere is invalid (catches " foo", "foo ", "foo\nbar")
    if v != v.strip() or any(ch.isspace() for ch in v):
        raise ValueError("model must not contain whitespace")
    if v.startswith("-"):
        raise ValueError("model must not start with '-'")
    if not _MODEL_SLUG_RE.fullmatch(v):
        raise ValueError(
            "model must match ^[A-Za-z0-9._:\\-/]{1,128}$ "
            "(letters, digits, '.', '_', ':', '-', '/')"
        )
    return v


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

    @field_validator("model")
    @classmethod
    def _validate_model(cls, v: str) -> str:
        # S6: adapter input validation — reject leading '-', whitespace, and
        # out-of-charset characters before the value reaches any subprocess.
        result = _validate_model_slug(v)
        assert result is not None  # required field, never None at this point
        return result

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

    @field_validator("model")
    @classmethod
    def _validate_model(cls, v: str | None) -> str | None:
        # S6: same regex on patch (None = not provided, keep existing value)
        return _validate_model_slug(v)


class LLMIntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
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
            id=obj.id,
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
