"""Detection rule API request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DetectionRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    source_rule_id: str | None = None
    source_name: str | None = None
    severity: str | None = None
    is_active: bool = True
    mitre_tactics: list[str] = Field(default_factory=list)
    mitre_techniques: list[str] = Field(default_factory=list)
    mitre_subtechniques: list[str] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    run_frequency: str | None = None
    created_by: str | None = None
    documentation: str | None = None


class DetectionRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    name: str
    source_rule_id: str | None
    source_name: str | None
    severity: str | None
    is_active: bool
    mitre_tactics: list[str]
    mitre_techniques: list[str]
    mitre_subtechniques: list[str]
    data_sources: list[str]
    run_frequency: str | None
    created_by: str | None
    documentation: str | None
    created_at: datetime
    updated_at: datetime


class DetectionRulePatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=500)
    severity: str | None = None
    is_active: bool | None = None
    mitre_tactics: list[str] | None = None
    mitre_techniques: list[str] | None = None
    mitre_subtechniques: list[str] | None = None
    data_sources: list[str] | None = None
    documentation: str | None = None
