"""
Enrichment API routes.

Endpoints:
  POST /v1/enrichments  — on-demand synchronous enrichment (cache-first)

Provider listing is available at GET /v1/enrichment-providers (full CRUD).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.cache.base import CacheBackendBase
from app.cache.factory import get_cache_backend
from app.cache.keys import make_enrichment_key
from app.config import settings
from app.db.session import get_db
from app.integrations.enrichment.registry import enrichment_registry
from app.middleware.rate_limit import limiter
from app.schemas.common import DataResponse
from app.schemas.enrichment import (
    OnDemandEnrichmentRequest,
    OnDemandEnrichmentResponse,
    OnDemandEnrichmentResult,
)
from app.services.enrichment import EnrichmentService

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["enrichments"])


def _get_cache() -> CacheBackendBase:
    return get_cache_backend()


# ---------------------------------------------------------------------------
# POST /v1/enrichments — on-demand enrichment
# ---------------------------------------------------------------------------


@router.post(
    "/enrichments",
    response_model=DataResponse[OnDemandEnrichmentResponse],
    summary="Enrich an indicator on-demand",
)
@limiter.limit(f"{settings.RATE_LIMIT_ENRICHMENT_PER_MINUTE}/minute")
async def enrich_on_demand(
    request: Request,
    body: OnDemandEnrichmentRequest,
    auth: Annotated[object, Depends(require_scope(Scope.ENRICHMENTS_READ))],
    db: Annotated[AsyncSession, Depends(get_db)],
    cache: Annotated[CacheBackendBase, Depends(_get_cache)],
) -> DataResponse[OnDemandEnrichmentResponse]:
    """
    Synchronously enrich an indicator against all configured providers.

    Results are returned cache-first. Each provider entry in the response
    includes `cache_hit: true` when the result was served from cache rather
    than a live API call.
    """
    providers = enrichment_registry.list_for_type(body.type)
    if not providers:
        # No configured providers — return 200 with empty results rather than
        # erroring, so callers can handle gracefully.
        payload = OnDemandEnrichmentResponse(
            type=body.type,
            value=body.value,
            results={},
            enriched_at=datetime.now(UTC),
        )
        return DataResponse(data=payload)

    # Pre-check cache to record which providers already have a cached result.
    # The service will re-check the same in-memory cache — negligible overhead.
    cache_hit_names: set[str] = set()
    for provider in providers:
        cache_key = make_enrichment_key(
            provider.provider_name, str(body.type), body.value
        )
        if await cache.get(cache_key) is not None:
            cache_hit_names.add(provider.provider_name)

    service = EnrichmentService(db, cache)
    raw_results = await service.enrich_indicator(body.type, body.value)

    response_results: dict[str, OnDemandEnrichmentResult] = {}
    for provider_name, result in raw_results.items():
        response_results[provider_name] = OnDemandEnrichmentResult(
            status=result.status,
            success=result.success,
            extracted=result.extracted,
            enriched_at=result.enriched_at,
            error_message=result.error_message,
            cache_hit=provider_name in cache_hit_names,
        )

    payload = OnDemandEnrichmentResponse(
        type=body.type,
        value=body.value,
        results=response_results,
        enriched_at=datetime.now(UTC),
    )
    return DataResponse(data=payload)


