"""
MCP resource for on-demand indicator enrichment.

Exposes enrichment data as an MCP resource for AI agent consumption:
  - calseta://enrichments/{type}/{value}  — On-demand enrichment (cache-first)

When an agent reads this resource, the platform runs all configured enrichment
providers for the given indicator type+value and returns structured results.
Cache is checked first; live provider calls are made only for cache misses.
"""

from __future__ import annotations

import json
from datetime import datetime

import structlog
from mcp.server.fastmcp import Context

from app.cache.factory import get_cache_backend
from app.cache.keys import make_enrichment_key
from app.db.session import AsyncSessionLocal
from app.integrations.enrichment.registry import enrichment_registry
from app.mcp.scope import check_scope
from app.mcp.server import mcp_server
from app.schemas.indicators import IndicatorType
from app.services.enrichment import EnrichmentService

logger = structlog.get_logger(__name__)

# Valid indicator type values for error messages
_VALID_TYPES = sorted(t.value for t in IndicatorType)


def _json_serial(obj: object) -> str:
    """JSON serializer for objects not handled by default json encoder."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _validate_indicator_type(type_str: str) -> IndicatorType:
    """Validate and return the IndicatorType enum, or raise ValueError."""
    try:
        return IndicatorType(type_str)
    except ValueError:
        raise ValueError(
            f"Invalid indicator type: '{type_str}'. "
            f"Valid types are: {', '.join(_VALID_TYPES)}"
        ) from None


@mcp_server.resource("calseta://enrichments/{type}/{value}")
async def get_enrichment(type: str, value: str, ctx: Context) -> str:
    """Enrich an indicator on demand against all configured providers (cache-first)."""
    # Scope check before any work
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "enrichments:read")
        if scope_err:
            return scope_err

    indicator_type = _validate_indicator_type(type)

    if not value or not value.strip():
        raise ValueError("Indicator value must not be empty.")

    value = value.strip()

    # Check which providers support this type
    providers = enrichment_registry.list_for_type(indicator_type)
    if not providers:
        return json.dumps({
            "type": type,
            "value": value,
            "results": {},
            "provider_count": 0,
            "message": f"No configured providers support indicator type '{type}'.",
        })

    cache = get_cache_backend()

    # Pre-check cache to record which providers returned cached results.
    # The service re-checks the same in-memory cache — negligible overhead.
    cache_hit_names: set[str] = set()
    for provider in providers:
        cache_key = make_enrichment_key(
            provider.provider_name, str(indicator_type), value
        )
        if await cache.get(cache_key) is not None:
            cache_hit_names.add(provider.provider_name)

    async with AsyncSessionLocal() as session:
        service = EnrichmentService(session, cache)
        raw_results = await service.enrich_indicator(indicator_type, value)

    # Build response — mirrors POST /v1/enrichments structure but as plain dict
    results: dict[str, object] = {}
    for provider_name, result in raw_results.items():
        results[provider_name] = {
            "status": result.status,
            "success": result.success,
            "extracted": result.extracted,
            "enriched_at": result.enriched_at.isoformat() if result.enriched_at else None,
            "error_message": result.error_message,
            "cache_hit": provider_name in cache_hit_names,
        }

    payload = {
        "type": type,
        "value": value,
        "results": results,
        "provider_count": len(results),
    }

    return json.dumps(payload, default=_json_serial)
