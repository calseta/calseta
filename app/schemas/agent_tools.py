"""Pydantic schemas for the agent tool registry."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolTier(StrEnum):
    SAFE = "safe"
    MANAGED = "managed"
    REQUIRES_APPROVAL = "requires_approval"
    FORBIDDEN = "forbidden"


class ToolCategory(StrEnum):
    CALSETA_API = "calseta_api"
    MCP = "mcp"
    WORKFLOW = "workflow"
    INTEGRATION = "integration"


class AgentToolCreate(BaseModel):
    id: str  # tool identifier, e.g. "get_alert"
    display_name: str
    description: str
    documentation: str | None = None
    tier: ToolTier
    category: ToolCategory
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    handler_ref: str


class AgentToolPatch(BaseModel):
    display_name: str | None = None
    description: str | None = None
    documentation: str | None = None
    tier: ToolTier | None = None
    is_active: bool | None = None


class AgentToolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    description: str
    documentation: str | None
    tier: str
    category: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    handler_ref: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
