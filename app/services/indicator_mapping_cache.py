"""
In-memory cache for normalized indicator field mappings.

Loaded once at startup (after seed_system_mappings completes).
Stores lightweight frozen dataclasses that duck-type match what
_extract_normalized() expects — it reads .field_path and .indicator_type.

Thread-safe reads via threading.Lock for atomic swaps.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.indicator_field_mapping import IndicatorFieldMapping

logger = structlog.get_logger(__name__)

_lock = threading.Lock()
_mappings: list[CachedMapping] = []


@dataclass(frozen=True)
class CachedMapping:
    """Lightweight read-only mapping for fingerprint extraction."""

    field_path: str
    indicator_type: str
    source_name: str | None


async def load_normalized_mappings(db: AsyncSession) -> int:
    """
    Load all active normalized-target mappings into the in-memory cache.

    Called once at startup. Returns the count of cached mappings.
    """
    global _mappings

    result = await db.execute(
        select(IndicatorFieldMapping).where(
            IndicatorFieldMapping.is_active.is_(True),
            IndicatorFieldMapping.extraction_target == "normalized",
        )
    )
    rows = result.scalars().all()

    new_mappings = [
        CachedMapping(
            field_path=row.field_path,
            indicator_type=row.indicator_type,
            source_name=row.source_name,
        )
        for row in rows
    ]

    with _lock:
        _mappings = new_mappings

    count = len(new_mappings)
    logger.info("normalized_mapping_cache_loaded", count=count)
    return count


def get_normalized_mappings(source_name: str | None = None) -> list[CachedMapping]:
    """
    Return cached mappings applicable to the given source.

    Includes global mappings (source_name is None) and source-specific ones.
    Sync reader — safe to call from non-async code.
    """
    with _lock:
        snapshot = _mappings

    return [
        m
        for m in snapshot
        if m.source_name is None or m.source_name == source_name
    ]
