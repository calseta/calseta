"""
Standard API response envelopes and shared schema types.

All API responses use DataResponse[T] (single object) or PaginatedResponse[T] (list).
Errors use ErrorResponse. These are the only shapes that cross the HTTP boundary.
"""

from __future__ import annotations

import math
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field

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
