"""Shared pagination dependency for all list endpoints."""

from __future__ import annotations

from fastapi import Query


class PaginationParams:
    """
    FastAPI dependency for pagination parameters.

    Usage:
        @router.get("/items")
        async def list_items(pagination: PaginationParams = Depends()) -> ...:
            offset = pagination.offset
            limit = pagination.page_size
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number (1-indexed)"),
        page_size: int = Query(
            50, ge=1, le=500, description="Items per page (max 500)"
        ),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
