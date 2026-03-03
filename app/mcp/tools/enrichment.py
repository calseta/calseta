"""
MCP tool for on-demand indicator enrichment.

Tool:
  - enrich_indicator — Enrich an indicator synchronously against all configured providers
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
from app.mcp.scope import _resolve_client_id, check_scope
from app.mcp.server import mcp_server
from app.repositories.indicator_repository import IndicatorRepository
from app.schemas.activity_events import ActivityEventType
from app.schemas.indicators import IndicatorType, MaliceLevel
from app.services.activity_event import ActivityEventService
from app.services.enrichment import EnrichmentService

logger = structlog.get_logger(__name__)

_VALID_TYPES = sorted(t.value for t in IndicatorType)


def _json_serial(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@mcp_server.tool()
async def enrich_indicator(
    type: str,
    value: str,
    ctx: Context,
) -> str:
    """Enrich an indicator against all configured providers (cache-first).

    Performs synchronous enrichment — results are returned inline rather than
    queued. Cached results are served immediately; only cache misses trigger
    live API calls to providers.

    Args:
        type: Indicator type. Valid values: "ip", "domain", "hash_md5",
              "hash_sha1", "hash_sha256", "url", "email", "account".
        value: The indicator value to enrich (e.g. "1.2.3.4", "evil.com").

    Returns:
        JSON with per-provider enrichment results including extracted fields,
        success status, and cache_hit indicator.
    """
    try:
        indicator_type = IndicatorType(type)
    except ValueError:
        return json.dumps({
            "error": f"Invalid indicator type '{type}'. Valid types: {_VALID_TYPES}"
        })

    if not value or not value.strip():
        return json.dumps({"error": "Indicator value must not be empty."})

    value = value.strip()

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

    # Pre-check cache to track cache_hit per provider
    cache_hit_names: set[str] = set()
    for provider in providers:
        cache_key = make_enrichment_key(
            provider.provider_name, str(indicator_type), value
        )
        if await cache.get(cache_key) is not None:
            cache_hit_names.add(provider.provider_name)

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "enrichments:read")
        if scope_err:
            return scope_err

        service = EnrichmentService(session, cache)
        raw_results = await service.enrich_indicator(indicator_type, value)

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

    return json.dumps({
        "type": type,
        "value": value,
        "results": results,
        "provider_count": len(results),
    }, default=_json_serial)


_VALID_MALICE = sorted(m.value for m in MaliceLevel)


@mcp_server.tool()
async def update_indicator_malice(
    indicator_uuid: str,
    ctx: Context,
    malice: str | None = None,
) -> str:
    """Set or reset the malice verdict on an indicator.

    When malice is provided, the indicator's malice is set to the given value
    (analyst override) and will not be changed by re-enrichment. When malice is
    null/omitted, the override is cleared and malice is recomputed from
    stored enrichment results.

    Args:
        indicator_uuid: UUID of the indicator to update.
        malice: Malice verdict to set. Valid values: "Pending", "Benign",
                "Suspicious", "Malicious". Pass null to reset to enrichment.

    Returns:
        JSON with the updated indicator UUID, malice, source, and timestamp.
    """
    import uuid as _uuid
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.db.models.alert_indicator import AlertIndicator

    try:
        _uuid.UUID(indicator_uuid)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {indicator_uuid}"})

    if malice is not None and malice not in _VALID_MALICE:
        return json.dumps({
            "error": f"Invalid malice '{malice}'. Must be one of: {_VALID_MALICE}"
        })

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "alerts:write")
        if scope_err:
            return scope_err

        repo = IndicatorRepository(session)
        indicator = await repo.get_by_uuid(indicator_uuid)
        if indicator is None:
            return json.dumps({"error": f"Indicator not found: {indicator_uuid}"})

        prev_malice = indicator.malice
        now = datetime.now(UTC)

        await repo.patch_malice(indicator, malice=malice, now=now)

        # Find an associated alert for the activity event FK
        alert_link = await session.execute(
            select(AlertIndicator.alert_id)
            .where(AlertIndicator.indicator_id == indicator.id)
            .limit(1)
        )
        alert_id = alert_link.scalar_one_or_none()

        activity_svc = ActivityEventService(session)
        await activity_svc.write(
            ActivityEventType.INDICATOR_MALICE_UPDATED,
            actor_type="mcp",
            actor_key_prefix=_resolve_client_id(ctx),
            alert_id=alert_id,
            references={
                "from_malice": prev_malice,
                "to_malice": indicator.malice,
                "malice_source": indicator.malice_source,
                "indicator_type": indicator.type,
                "indicator_value": indicator.value,
            },
        )

        await session.commit()

        return json.dumps({
            "indicator_uuid": indicator_uuid,
            "malice": indicator.malice,
            "malice_source": indicator.malice_source,
            "updated_at": now.isoformat(),
        })
