"""Source integration API schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceIntegrationCreate(BaseModel):
    source_name: str  # must match a registered source plugin
    display_name: str = Field(..., min_length=1, max_length=255)
    is_active: bool = True
    auth_type: str | None = None
    auth_config: dict[str, Any] | None = None  # encrypted before storage
    documentation: str | None = None


class SourceIntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    source_name: str
    display_name: str
    is_active: bool
    auth_type: str | None
    # auth_config is NEVER returned
    documentation: str | None
    created_at: datetime
    updated_at: datetime


class SourceIntegrationPatch(BaseModel):
    display_name: str | None = None
    is_active: bool | None = None
    auth_type: str | None = None
    auth_config: dict[str, Any] | None = None
    documentation: str | None = None
