"""
API key management routes.

All endpoints require `admin` scope. The full API key is returned only
once (on creation) and never stored in plain text.

Routes:
    GET    /v1/api-keys             — List all active API keys
    POST   /v1/api-keys             — Create a new API key (returns full key once)
    GET    /v1/api-keys/{uuid}      — Get a single API key by UUID
    PATCH  /v1/api-keys/{uuid}      — Update scopes, allowed_sources, or deactivate
    DELETE /v1/api-keys/{uuid}      — Deactivate an API key
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.repositories.api_key_repository import APIKeyRepository
from app.schemas.api_keys import APIKeyCreate, APIKeyCreated, APIKeyResponse, APIKeyUpdate
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/api-keys", tags=["api-keys"])

_AdminAuth = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]


@router.get("", response_model=PaginatedResponse[APIKeyResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_api_keys(
    request: Request,
    auth: _AdminAuth,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[APIKeyResponse]:
    repo = APIKeyRepository(db)
    keys, total = await repo.list_active(offset=pagination.offset, limit=pagination.page_size)
    return PaginatedResponse(
        data=[
            APIKeyResponse(
                uuid=k.uuid,
                name=k.name,
                key_prefix=k.key_prefix,
                scopes=list(k.scopes),
                key_type=k.key_type,
                is_active=k.is_active,
                created_at=k.created_at,
                expires_at=k.expires_at,
                last_used_at=k.last_used_at,
                allowed_sources=list(k.allowed_sources) if k.allowed_sources else None,
            )
            for k in keys
        ],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


@router.post("", response_model=DataResponse[APIKeyCreated], status_code=status.HTTP_201_CREATED)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_api_key(
    request: Request,
    auth: _AdminAuth,
    body: APIKeyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[APIKeyCreated]:
    repo = APIKeyRepository(db)
    record, plain_key = await repo.create(
        name=body.name,
        scopes=body.scopes,
        key_type=body.key_type,
        expires_at=body.expires_at,
        allowed_sources=body.allowed_sources,
    )
    return DataResponse(
        data=APIKeyCreated(
            uuid=record.uuid,
            name=record.name,
            key_prefix=record.key_prefix,
            key=plain_key,
            scopes=list(record.scopes),
            key_type=record.key_type,
            is_active=record.is_active,
            created_at=record.created_at,
            expires_at=record.expires_at,
            allowed_sources=list(record.allowed_sources) if record.allowed_sources else None,
        )
    )


@router.get("/{key_uuid}", response_model=DataResponse[APIKeyResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_api_key(
    request: Request,
    auth: _AdminAuth,
    key_uuid: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[APIKeyResponse]:
    repo = APIKeyRepository(db)
    record = await repo.get_by_uuid(str(key_uuid))
    if record is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="API key not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(
        data=APIKeyResponse(
            uuid=record.uuid,
            name=record.name,
            key_prefix=record.key_prefix,
            scopes=list(record.scopes),
            key_type=record.key_type,
            is_active=record.is_active,
            created_at=record.created_at,
            expires_at=record.expires_at,
            last_used_at=record.last_used_at,
            allowed_sources=list(record.allowed_sources) if record.allowed_sources else None,
        )
    )


@router.patch("/{key_uuid}", response_model=DataResponse[APIKeyResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def update_api_key(
    request: Request,
    auth: _AdminAuth,
    key_uuid: UUID,
    body: APIKeyUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[APIKeyResponse]:
    from app.repositories.api_key_repository import _UNSET

    repo = APIKeyRepository(db)

    kwargs: dict = {}
    if body.scopes is not None:
        kwargs["scopes"] = body.scopes
    if body.is_active is not None:
        kwargs["is_active"] = body.is_active
    # allowed_sources: distinguish between "not sent" and "sent as null"
    if "allowed_sources" in body.model_fields_set:
        kwargs["allowed_sources"] = body.allowed_sources
    else:
        kwargs["allowed_sources"] = _UNSET

    record = await repo.update(str(key_uuid), **kwargs)
    if record is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="API key not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(
        data=APIKeyResponse(
            uuid=record.uuid,
            name=record.name,
            key_prefix=record.key_prefix,
            scopes=list(record.scopes),
            key_type=record.key_type,
            is_active=record.is_active,
            created_at=record.created_at,
            expires_at=record.expires_at,
            last_used_at=record.last_used_at,
            allowed_sources=list(record.allowed_sources) if record.allowed_sources else None,
        )
    )


@router.delete("/{key_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_api_key(
    request: Request,
    auth: _AdminAuth,
    key_uuid: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = APIKeyRepository(db)
    found = await repo.deactivate(str(key_uuid))
    if not found:
        raise CalsetaException(
            code="NOT_FOUND",
            message="API key not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
