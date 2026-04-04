"""Knowledge Base API schemas."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- Type aliases ---

KBPageStatus = Literal["published", "draft", "archived"]
KBLinkType = Literal["reference", "source", "generated_from", "related"]
KBLinkedEntityType = Literal["alert", "issue", "page", "agent", "campaign"]

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-/]*[a-z0-9]$|^[a-z0-9]$")


# --- Request schemas ---


class KBPageCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=200)
    title: str = Field(..., min_length=1, max_length=500)
    body: str
    folder: str = "/"
    format: str = "markdown"
    status: KBPageStatus = "published"
    inject_scope: dict[str, Any] | None = None
    inject_priority: int = Field(default=0, ge=0, le=100)
    inject_pinned: bool = False
    sync_source: dict[str, Any] | None = None
    token_count: int | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        # Allow lowercase alphanumeric, hyphens, and forward slashes
        # Segments separated by '/' must each be non-empty
        if not v:
            raise ValueError("slug must not be empty")
        segments = v.split("/")
        for segment in segments:
            if not segment:
                raise ValueError(
                    "slug must not have empty path segments "
                    "(double slash or leading/trailing slash)"
                )
            if not re.match(r"^[a-z0-9][a-z0-9\-]*$|^[a-z0-9]$", segment):
                raise ValueError(
                    "slug segments must be lowercase alphanumeric and hyphens only"
                )
        return v


class KBPagePatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    body: str | None = None
    folder: str | None = None
    status: KBPageStatus | None = None
    inject_scope: dict[str, Any] | None = None
    inject_priority: int | None = Field(default=None, ge=0, le=100)
    inject_pinned: bool | None = None
    sync_source: dict[str, Any] | None = None
    token_count: int | None = None
    metadata: dict[str, Any] | None = None
    change_summary: str | None = None


# --- Response schemas ---


class KBPageRevisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    revision_number: int
    body: str
    change_summary: str | None
    author_operator: str | None
    sync_source_ref: str | None
    created_at: datetime


class KBPageLinkCreate(BaseModel):
    linked_entity_type: KBLinkedEntityType
    linked_entity_id: UUID
    link_type: KBLinkType


class KBPageLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    linked_entity_type: str
    linked_entity_id: UUID
    link_type: str
    created_at: datetime


class KBPageSummary(BaseModel):
    """For list responses — no body."""

    model_config = ConfigDict(from_attributes=True)

    uuid: UUID
    slug: str
    title: str
    folder: str
    format: str
    status: str
    inject_scope: dict[str, Any] | None
    inject_priority: int
    inject_pinned: bool
    sync_source: dict[str, Any] | None
    synced_at: datetime | None
    token_count: int | None
    latest_revision_number: int
    created_at: datetime
    updated_at: datetime


class KBPageResponse(KBPageSummary):
    """Full page response with body and extended fields."""

    body: str
    sync_last_hash: str | None
    metadata_: dict[str, Any] | None = Field(default=None, alias="metadata_")
    links: list[KBPageLinkResponse] = []

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class KBSearchResultItem(BaseModel):
    slug: str
    title: str
    folder: str
    summary: str  # first 200 chars of body
    inject_scope: dict[str, Any] | None
    sync_source: str | None  # type field from sync_source JSONB, or None
    relevance_score: float | None = None
    updated_at: datetime


class KBFolderNode(BaseModel):
    path: str
    name: str  # last segment of path
    page_count: int
    children: list[KBFolderNode] = []


class KBSyncResult(BaseModel):
    slug: str
    outcome: str  # updated|no_change|fetch_failed|config_invalid
    old_hash: str | None = None
    new_hash: str | None = None
    error_message: str | None = None
    revision_id: UUID | None = None


# Allow forward refs in KBFolderNode
KBFolderNode.model_rebuild()
