"""
Shared route utility functions for common endpoint patterns.

These helpers eliminate boilerplate in list and detail endpoints while keeping
auth, rate limiting, and entity-specific logic in the route handlers.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from starlette import status

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.repositories.base import BaseRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta


async def paginated_list[T](
    items: list[Any],
    total: int,
    schema: type[T],
    pagination: PaginationParams,
) -> PaginatedResponse[T]:
    """Build a PaginatedResponse from a pre-fetched (items, total) result.

    Usage::

        items, total = await repo.list_all(page=pagination.page, page_size=pagination.page_size)
        return await paginated_list(items, total, MySchema, pagination)
    """
    return PaginatedResponse(
        data=[schema.model_validate(item) for item in items],  # type: ignore[attr-defined]
        meta=PaginationMeta.from_total(
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        ),
    )


async def get_or_404(
    repo: BaseRepository[Any],
    uuid: UUID,
    entity_name: str = "Resource",
) -> Any:
    """Fetch an entity by UUID or raise a 404 CalsetaException.

    Returns the raw ORM model instance -- callers wrap in DataResponse
    or use the entity for further mutations (patch, delete).

    Usage::

        entity = await get_or_404(repo, some_uuid, "Detection rule")
        return DataResponse(data=MySchema.model_validate(entity))
    """
    entity = await repo.get_by_uuid(uuid)
    if entity is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"{entity_name} not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return entity


async def detail_response[T](
    repo: BaseRepository[Any],
    schema: type[T],
    uuid: UUID,
    entity_name: str = "Resource",
) -> DataResponse[T]:
    """Fetch an entity by UUID, validate into schema, wrap in DataResponse.

    Convenience for simple GET detail endpoints that just fetch and return.

    Usage::

        return await detail_response(repo, MySchema, some_uuid, "Detection rule")
    """
    entity = await get_or_404(repo, uuid, entity_name)
    return DataResponse(data=schema.model_validate(entity))  # type: ignore[attr-defined]
