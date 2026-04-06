"""
Secrets management routes.

POST   /v1/secrets                        — Create a secret
GET    /v1/secrets                        — List secrets (paginated)
GET    /v1/secrets/{uuid}                 — Get secret details
DELETE /v1/secrets/{uuid}                 — Delete a secret (204)
POST   /v1/secrets/{uuid}/versions        — Rotate secret (create new version)
GET    /v1/secrets/{uuid}/versions        — List versions (metadata only, no values)
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
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
from app.repositories.secret_repository import SecretRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.secrets import SecretCreate, SecretResponse, SecretRotate, SecretVersionResponse
from app.services.secret_service import SecretService

router = APIRouter(prefix="/secrets", tags=["secrets"])

_Admin = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]
_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]


# ---------------------------------------------------------------------------
# POST /v1/secrets
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DataResponse[SecretResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_secret(
    request: Request,
    body: SecretCreate,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SecretResponse]:
    # Guard: ENCRYPTION_KEY required for local_encrypted provider
    if body.provider == "local_encrypted" and not settings.ENCRYPTION_KEY:
        raise CalsetaException(
            code="ENCRYPTION_NOT_CONFIGURED",
            message=(
                "ENCRYPTION_KEY is not set. Cannot store local_encrypted secrets. "
                "Set ENCRYPTION_KEY in your environment and restart the service."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Guard: unique name
    repo = SecretRepository(db)
    existing = await repo.get_by_name(body.name)
    if existing is not None:
        raise CalsetaException(
            code="CONFLICT",
            message=f"A secret with name '{body.name}' already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )

    svc = SecretService(db)
    try:
        secret, _ = await svc.create(body)
    except ValueError as exc:
        raise CalsetaException(
            code="ENCRYPTION_ERROR",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc
    except IntegrityError:
        raise CalsetaException(
            code="CONFLICT",
            message=f"A secret with name '{body.name}' already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )
    return DataResponse(data=SecretResponse.model_validate(secret))


# ---------------------------------------------------------------------------
# GET /v1/secrets
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[SecretResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_secrets(
    request: Request,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[SecretResponse]:
    repo = SecretRepository(db)
    secrets, total = await repo.list_all(page=pagination.page, page_size=pagination.page_size)
    return PaginatedResponse(
        data=[SecretResponse.model_validate(s) for s in secrets],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# GET /v1/secrets/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{secret_uuid}", response_model=DataResponse[SecretResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_secret(
    request: Request,
    secret_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SecretResponse]:
    repo = SecretRepository(db)
    secret = await repo.get_by_uuid(secret_uuid)
    if secret is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Secret not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=SecretResponse.model_validate(secret))


# ---------------------------------------------------------------------------
# DELETE /v1/secrets/{uuid}
# ---------------------------------------------------------------------------


@router.delete("/{secret_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_secret(
    request: Request,
    secret_uuid: UUID,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = SecretRepository(db)
    secret = await repo.get_by_uuid(secret_uuid)
    if secret is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Secret not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    svc = SecretService(db)
    await svc.delete(secret)


# ---------------------------------------------------------------------------
# POST /v1/secrets/{uuid}/versions  (rotate)
# ---------------------------------------------------------------------------


@router.post(
    "/{secret_uuid}/versions",
    response_model=DataResponse[SecretVersionResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def rotate_secret(
    request: Request,
    secret_uuid: UUID,
    body: SecretRotate,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SecretVersionResponse]:
    if not settings.ENCRYPTION_KEY:
        raise CalsetaException(
            code="ENCRYPTION_NOT_CONFIGURED",
            message=(
                "ENCRYPTION_KEY is not set. Cannot rotate secrets. "
                "Set ENCRYPTION_KEY in your environment and restart the service."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    repo = SecretRepository(db)
    secret = await repo.get_by_uuid(secret_uuid)
    if secret is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Secret not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    svc = SecretService(db)
    try:
        version = await svc.rotate(secret, body.value)
    except ValueError as exc:
        raise CalsetaException(
            code="INVALID_OPERATION",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    return DataResponse(data=SecretVersionResponse.model_validate(version))


# ---------------------------------------------------------------------------
# GET /v1/secrets/{uuid}/versions
# ---------------------------------------------------------------------------


@router.get(
    "/{secret_uuid}/versions",
    response_model=PaginatedResponse[SecretVersionResponse],
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_secret_versions(
    request: Request,
    secret_uuid: UUID,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[SecretVersionResponse]:
    repo = SecretRepository(db)
    secret = await repo.get_by_uuid(secret_uuid)
    if secret is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Secret not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    versions, total = await repo.list_versions(
        secret, page=pagination.page, page_size=pagination.page_size
    )
    return PaginatedResponse(
        data=[SecretVersionResponse.model_validate(v) for v in versions],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )
