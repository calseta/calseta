"""
Standard API response envelopes and shared schema types.

All API responses use DataResponse[T] (single object) or PaginatedResponse[T] (list).
Errors use ErrorResponse. These are the only shapes that cross the HTTP boundary.
"""

from __future__ import annotations

import json
import math
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# JSONB size limits (bytes)
# ---------------------------------------------------------------------------
JSONB_SIZE_LARGE = 1_048_576  # 1 MB — raw_payload, large data blobs
JSONB_SIZE_MEDIUM = 262_144  # 256 KB — config objects (http_config, auth_config, etc.)
JSONB_SIZE_SMALL = 65_536  # 64 KB — small structured fields (trigger_filter, etc.)


def validate_jsonb_size(
    value: dict[str, Any] | list[Any] | None,
    max_bytes: int,
    field_name: str,
) -> dict[str, Any] | list[Any] | None:
    """
    Validate that a JSONB-bound value does not exceed the given size limit.

    Returns the value unchanged if valid; raises ValueError otherwise.
    Use in Pydantic field_validator or model_validator calls.
    """
    if value is None:
        return value
    serialized_size = len(json.dumps(value, separators=(",", ":")))
    if serialized_size > max_bytes:
        limit_label = _human_size(max_bytes)
        raise ValueError(
            f"{field_name} exceeds maximum size of {limit_label} "
            f"({serialized_size:,} bytes serialized)"
        )
    return value


def _human_size(n: int) -> str:
    """Return a human-friendly size label (e.g. '1 MB', '256 KB')."""
    if n >= 1_048_576 and n % 1_048_576 == 0:
        return f"{n // 1_048_576} MB"
    if n >= 1024 and n % 1024 == 0:
        return f"{n // 1024} KB"
    return f"{n:,} bytes"

T = TypeVar("T")


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def from_total(cls, total: int, page: int, page_size: int) -> PaginationMeta:
        total_pages = math.ceil(total / page_size) if page_size > 0 else 0
        return cls(total=total, page=page, page_size=page_size, total_pages=total_pages)


class DataResponse[T](BaseModel):
    """
    Single-object response envelope.

    Serializes as:
        {"data": {...}, "meta": {}}
    """

    data: T
    meta: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)


class PaginatedResponse[T](BaseModel):
    """
    List response envelope.

    Serializes as:
        {"data": [...], "meta": {"total": N, "page": N, "page_size": N, "total_pages": N}}
    """

    data: list[T]
    meta: PaginationMeta

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """
    Error response envelope.

    Serializes as:
        {"error": {"code": "...", "message": "...", "details": {}}}
    """

    error: ErrorDetail
