"""
CRUD API for runtime-configurable enrichment providers.

Routes:
  GET    /v1/enrichment-providers              — List all providers
  POST   /v1/enrichment-providers              — Create custom provider
  GET    /v1/enrichment-providers/{uuid}        — Get provider detail
  PATCH  /v1/enrichment-providers/{uuid}        — Update provider
  DELETE /v1/enrichment-providers/{uuid}        — Delete non-builtin provider
  POST   /v1/enrichment-providers/{uuid}/test   — Live test with sample indicator
  POST   /v1/enrichment-providers/{uuid}/activate   — Activate provider
  POST   /v1/enrichment-providers/{uuid}/deactivate — Deactivate provider
"""

from __future__ import annotations

import json
import time
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.db.session import get_db
from app.integrations.enrichment.database_provider import DatabaseDrivenProvider
from app.integrations.enrichment.registry import enrichment_registry
from app.repositories.enrichment_field_extraction_repository import (
    EnrichmentFieldExtractionRepository,
)
from app.repositories.enrichment_provider_repository import (
    EnrichmentProviderRepository,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.enrichment_providers import (
    EnrichmentProviderCreate,
    EnrichmentProviderPatch,
    EnrichmentProviderResponse,
    EnrichmentProviderTestRequest,
    EnrichmentProviderTestResponse,
)
from app.schemas.indicators import IndicatorType

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/enrichment-providers", tags=["enrichment-providers"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.ENRICHMENTS_READ))]
_Admin = Annotated[AuthContext, Depends(require_scope(Scope.ADMIN))]


def _has_credentials(provider: object) -> bool:
    """Check if the provider has credentials configured (DB or env var)."""
    auth_config = getattr(provider, "auth_config", None)
    env_var_mapping = getattr(provider, "env_var_mapping", None)
    auth_type = getattr(provider, "auth_type", "no_auth")

    if auth_type == "no_auth":
        return True

    if auth_config and auth_config.get("_encrypted"):
        return True

    if env_var_mapping:
        import os

        return any(os.environ.get(v) for v in env_var_mapping.values())

    return False


def _is_provider_configured(provider: object) -> bool:
    """Check if the provider is both active and has credentials (or mock mode)."""
    is_active = getattr(provider, "is_active", False)
    if not is_active:
        return False

    # Mock mode: configured if mock_responses exist
    from app.config import settings

    mock_responses = getattr(provider, "mock_responses", None)
    if settings.ENRICHMENT_MOCK_MODE and mock_responses:
        return True

    return _has_credentials(provider)


def _to_response(provider: object) -> EnrichmentProviderResponse:
    resp = EnrichmentProviderResponse.model_validate(provider)
    resp.has_credentials = _has_credentials(provider)
    resp.is_configured = _is_provider_configured(provider)
    return resp


def _encrypt_auth_config(auth_config: dict | None) -> dict | None:
    """Encrypt auth_config for storage."""
    if not auth_config:
        return None
    from app.auth.encryption import encrypt_value

    plaintext = json.dumps(auth_config)
    encrypted = encrypt_value(plaintext)
    return {"_encrypted": encrypted}


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[EnrichmentProviderResponse])
async def list_enrichment_providers(
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    is_active: bool | None = Query(None),
    is_builtin: bool | None = Query(None),
) -> PaginatedResponse[EnrichmentProviderResponse]:
    repo = EnrichmentProviderRepository(db)
    providers, total = await repo.list(
        is_active=is_active,
        is_builtin=is_builtin,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[_to_response(p) for p in providers],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DataResponse[EnrichmentProviderResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_enrichment_provider(
    body: EnrichmentProviderCreate,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[EnrichmentProviderResponse]:
    repo = EnrichmentProviderRepository(db)

    # Check for duplicate name
    existing = await repo.get_by_name(body.provider_name)
    if existing is not None:
        raise CalsetaException(
            code="DUPLICATE_PROVIDER",
            message=f"Provider '{body.provider_name}' already exists.",
            status_code=status.HTTP_409_CONFLICT,
        )

    # Validate indicator types
    valid_types = {t.value for t in IndicatorType}
    for t in body.supported_indicator_types:
        if t not in valid_types:
            raise CalsetaException(
                code="VALIDATION_ERROR",
                message=f"Invalid indicator type: '{t}'",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

    # Encrypt auth_config if provided
    encrypted_auth = _encrypt_auth_config(body.auth_config)

    provider = await repo.create(
        provider_name=body.provider_name,
        display_name=body.display_name,
        description=body.description,
        is_builtin=False,
        is_active=True,
        supported_indicator_types=body.supported_indicator_types,
        http_config=body.http_config,
        auth_type=body.auth_type,
        auth_config=encrypted_auth,
        env_var_mapping=None,
        default_cache_ttl_seconds=body.default_cache_ttl_seconds,
        cache_ttl_by_type=body.cache_ttl_by_type,
        malice_rules=body.malice_rules,
    )

    # Reload registry to include the new provider
    await enrichment_registry.load_from_database(db)

    return DataResponse(data=_to_response(provider))


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


@router.get("/{provider_uuid}", response_model=DataResponse[EnrichmentProviderResponse])
async def get_enrichment_provider(
    provider_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[EnrichmentProviderResponse]:
    repo = EnrichmentProviderRepository(db)
    provider = await repo.get_by_uuid(provider_uuid)
    if provider is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Enrichment provider not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=_to_response(provider))


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------


@router.patch(
    "/{provider_uuid}", response_model=DataResponse[EnrichmentProviderResponse]
)
async def patch_enrichment_provider(
    provider_uuid: UUID,
    body: EnrichmentProviderPatch,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[EnrichmentProviderResponse]:
    repo = EnrichmentProviderRepository(db)
    provider = await repo.get_by_uuid(provider_uuid)
    if provider is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Enrichment provider not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    updates = body.model_dump(exclude_none=True)

    # Builtin providers: restrict editable fields
    if provider.is_builtin:
        allowed_builtin_fields = {
            "is_active",
            "auth_config",
            "description",
            "malice_rules",
            "default_cache_ttl_seconds",
            "cache_ttl_by_type",
        }
        disallowed = set(updates.keys()) - allowed_builtin_fields
        if disallowed:
            raise CalsetaException(
                code="BUILTIN_RESTRICTED",
                message=(
                    f"Cannot modify fields {sorted(disallowed)} on builtin providers. "
                    f"Allowed: {sorted(allowed_builtin_fields)}"
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    # Encrypt auth_config if being updated
    if "auth_config" in updates and updates["auth_config"] is not None:
        updates["auth_config"] = _encrypt_auth_config(updates["auth_config"])

    updated = await repo.patch(provider, updates)

    # Reload registry
    await enrichment_registry.load_from_database(db)

    return DataResponse(data=_to_response(updated))


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@router.delete("/{provider_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_enrichment_provider(
    provider_uuid: UUID,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = EnrichmentProviderRepository(db)
    provider = await repo.get_by_uuid(provider_uuid)
    if provider is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Enrichment provider not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if provider.is_builtin:
        raise CalsetaException(
            code="BUILTIN_RESTRICTED",
            message="Cannot delete builtin enrichment providers. Use deactivate instead.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Cascade delete all field extractions for this provider
    extraction_repo = EnrichmentFieldExtractionRepository(db)
    deleted_count = await extraction_repo.delete_by_provider(
        provider.provider_name
    )
    if deleted_count:
        logger.info(
            "enrichment_field_extractions_cascade_deleted",
            provider_name=provider.provider_name,
            count=deleted_count,
        )

    await repo.delete(provider)

    # Reload registry
    await enrichment_registry.load_from_database(db)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@router.post(
    "/{provider_uuid}/test",
    response_model=DataResponse[EnrichmentProviderTestResponse],
)
async def test_enrichment_provider(
    provider_uuid: UUID,
    body: EnrichmentProviderTestRequest,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[EnrichmentProviderTestResponse]:
    repo = EnrichmentProviderRepository(db)
    provider = await repo.get_by_uuid(provider_uuid)
    if provider is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Enrichment provider not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Validate indicator type
    try:
        itype = IndicatorType(body.indicator_type)
    except ValueError as exc:
        raise CalsetaException(
            code="VALIDATION_ERROR",
            message=f"Invalid indicator type: '{body.indicator_type}'",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from exc

    # Get the registered provider instance from the registry
    registered = enrichment_registry.get(provider.provider_name)
    if registered is None:
        raise CalsetaException(
            code="PROVIDER_NOT_LOADED",
            message="Provider is not loaded in the registry. Try restarting the server.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    start = time.monotonic()

    # Use debug-enabled enrichment if available (DatabaseDrivenProvider)
    if isinstance(registered, DatabaseDrivenProvider):
        result = await registered.enrich_with_debug(body.indicator_value, itype)
    else:
        result = await registered.enrich(body.indicator_value, itype)

    duration_ms = int((time.monotonic() - start) * 1000)

    return DataResponse(
        data=EnrichmentProviderTestResponse(
            success=result.success,
            provider_name=provider.provider_name,
            indicator_type=body.indicator_type,
            indicator_value=body.indicator_value,
            extracted=result.extracted,
            raw_response=result.raw,
            error_message=result.error_message,
            duration_ms=duration_ms,
            steps=result.debug_steps,
        )
    )


# ---------------------------------------------------------------------------
# Activate / Deactivate
# ---------------------------------------------------------------------------


@router.post(
    "/{provider_uuid}/activate",
    response_model=DataResponse[EnrichmentProviderResponse],
)
async def activate_enrichment_provider(
    provider_uuid: UUID,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[EnrichmentProviderResponse]:
    repo = EnrichmentProviderRepository(db)
    provider = await repo.get_by_uuid(provider_uuid)
    if provider is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Enrichment provider not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    updated = await repo.patch(provider, {"is_active": True})
    await enrichment_registry.load_from_database(db)
    return DataResponse(data=_to_response(updated))


@router.post(
    "/{provider_uuid}/deactivate",
    response_model=DataResponse[EnrichmentProviderResponse],
)
async def deactivate_enrichment_provider(
    provider_uuid: UUID,
    auth: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[EnrichmentProviderResponse]:
    repo = EnrichmentProviderRepository(db)
    provider = await repo.get_by_uuid(provider_uuid)
    if provider is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Enrichment provider not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    updated = await repo.patch(provider, {"is_active": False})
    await enrichment_registry.load_from_database(db)
    return DataResponse(data=_to_response(updated))
