"""Skills API schemas."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class SkillFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    path: str
    content: str
    is_entry: bool
    created_at: datetime
    updated_at: datetime


class SkillFileUpsert(BaseModel):
    path: str  # e.g. "references/playbook.md"
    content: str = ""


class SkillCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    is_global: bool = False
    # No content — SKILL.md entry file is auto-created on creation

    @field_validator("slug")
    @classmethod
    def slug_format(cls, v: str) -> str:
        if not _SLUG_RE.match(v):
            raise ValueError(
                "slug must be lowercase letters, digits, and hyphens only "
                "(e.g. 'triage-runbook')"
            )
        return v


class SkillPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None
    is_global: bool | None = None


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    slug: str
    name: str
    description: str | None
    is_active: bool
    is_global: bool
    files: list[SkillFileResponse] = []
    created_at: datetime
    updated_at: datetime


class AgentSkillSyncRequest(BaseModel):
    skill_uuids: list[UUID]
