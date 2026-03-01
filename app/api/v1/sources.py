"""
Source integration management routes.

GET    /v1/sources            — List all source integrations
POST   /v1/sources            — Create a source integration
GET    /v1/sources/{uuid}     — Get one source integration
PATCH  /v1/sources/{uuid}     — Update a source integration
DELETE /v1/sources/{uuid}     — Delete a source integration (204)
"""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.repositories.source_repository import SourceRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.sources import (
    SourceIntegrationCreate,
    SourceIntegrationPatch,
    SourceIntegrationResponse,
)

router = APIRouter(prefix="/sources", tags=["sources"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_READ))]
_Admin = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]


def _encrypt_auth_config(auth_config: dict | None) -> dict | None:  # type: ignore[type-arg]
    """
    Serialize auth_config dict to JSON, encrypt the JSON string, and return
    {"_encrypted": "<ciphertext>"} for storage in the JSONB column.

    Raises CalsetaException(400) if auth_config is provided but ENCRYPTION_KEY
    is not configured.
    """
    if auth_config is None:
        return None
    if not settings.ENCRYPTION_KEY:
        raise CalsetaException(
            code="ENCRYPTION_NOT_CONFIGURED",
            message=(
                "ENCRYPTION_KEY must be set to store auth_config securely. "
                "Set ENCRYPTION_KEY in your environment and restart the service."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    from app.auth.encryption import encrypt_value

    ciphertext = encrypt_value(json.dumps(auth_config))
    return {"_encrypted": ciphertext}


# ---------------------------------------------------------------------------
# GET /v1/sources
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[SourceIntegrationResponse])
async def list_sources(
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[SourceIntegrationResponse]:
    repo = SourceRepository(db)
    integrations, total = await repo.list_all(
        page=pagination.page, page_size=pagination.page_size
    )
    return PaginatedResponse(
        data=[SourceIntegrationResponse.model_validate(i) for i in integrations],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# POST /v1/sources
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DataResponse[SourceIntegrationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_source(
    body: SourceIntegrationCreate,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SourceIntegrationResponse]:
    # Validate source_name against the plugin registry.
    from app.integrations.sources.registry import source_registry

    if source_registry.get(body.source_name) is None:
        raise CalsetaException(
            code="INVALID_SOURCE",
            message=(
                f"Unknown source plugin: {body.source_name!r}. "
                f"Registered sources: {[s.source_name for s in source_registry.list_all()]}"
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    auth_config_encrypted = _encrypt_auth_config(body.auth_config)

    repo = SourceRepository(db)
    integration = await repo.create(body, auth_config_encrypted)
    return DataResponse(data=SourceIntegrationResponse.model_validate(integration))


# ---------------------------------------------------------------------------
# GET /v1/sources/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{source_uuid}", response_model=DataResponse[SourceIntegrationResponse])
async def get_source(
    source_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SourceIntegrationResponse]:
    repo = SourceRepository(db)
    integration = await repo.get_by_uuid(source_uuid)
    if integration is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Source integration not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=SourceIntegrationResponse.model_validate(integration))


# ---------------------------------------------------------------------------
# PATCH /v1/sources/{uuid}
# ---------------------------------------------------------------------------


@router.patch("/{source_uuid}", response_model=DataResponse[SourceIntegrationResponse])
async def patch_source(
    source_uuid: UUID,
    body: SourceIntegrationPatch,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[SourceIntegrationResponse]:
    repo = SourceRepository(db)
    integration = await repo.get_by_uuid(source_uuid)
    if integration is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Source integration not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    updates: dict[str, object] = {}

    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.auth_type is not None:
        updates["auth_type"] = body.auth_type
    if body.auth_config is not None:
        updates["auth_config"] = _encrypt_auth_config(body.auth_config)
    if body.documentation is not None:
        updates["documentation"] = body.documentation

    updated = await repo.patch(integration, **updates)
    return DataResponse(data=SourceIntegrationResponse.model_validate(updated))


# ---------------------------------------------------------------------------
# DELETE /v1/sources/{uuid}
# ---------------------------------------------------------------------------


@router.delete("/{source_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_uuid: UUID,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = SourceRepository(db)
    integration = await repo.get_by_uuid(source_uuid)
    if integration is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Source integration not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await repo.delete(integration)
