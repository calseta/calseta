"""
Indicator extraction service — 3-pass IOC extraction pipeline.

Pass 1: Source plugin extract_indicators(raw_payload) — source-specific, hardcoded
Pass 2: System normalized-field mappings against CalsetaAlert fields
       (extraction_target='normalized')
Pass 3: Custom per-source field mappings against raw_payload (extraction_target='raw_payload')

Results are merged and deduplicated by (type, value) before persistence.
Empty or whitespace-only values are discarded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert
from app.integrations.sources.base import AlertSourceBase
from app.repositories.indicator_mapping_repository import IndicatorMappingRepository
from app.repositories.indicator_repository import IndicatorRepository
from app.schemas.alert import CalsetaAlert
from app.schemas.indicators import IndicatorExtract, IndicatorType

logger = structlog.get_logger(__name__)


def _traverse(data: dict[str, Any], field_path: str) -> str | None:
    """
    Traverse a nested dict using dot-notation field_path.
    Returns the string value if found and non-empty, else None.

    Example: _traverse({"a": {"b": "val"}}, "a.b") → "val"
    """
    parts = field_path.split(".")
    obj: Any = data
    for part in parts:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    if isinstance(obj, str) and obj.strip():
        return obj.strip()
    return None


def _extract_normalized(
    normalized: CalsetaAlert,
    mappings: list[Any],
) -> list[IndicatorExtract]:
    """Pass 2: extract IOCs from CalsetaAlert normalized fields."""
    indicators: list[IndicatorExtract] = []
    normalized_dict = normalized.model_dump()

    for mapping in mappings:
        raw_value = normalized_dict.get(mapping.field_path)
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        try:
            itype = IndicatorType(mapping.indicator_type)
        except ValueError:
            logger.warning(
                "indicator_mapping_unknown_type",
                field_path=mapping.field_path,
                indicator_type=mapping.indicator_type,
            )
            continue
        indicators.append(
            IndicatorExtract(
                type=itype,
                value=raw_value.strip(),
                source_field=f"normalized.{mapping.field_path}",
            )
        )
    return indicators


def _extract_raw(
    raw_payload: dict[str, Any],
    mappings: list[Any],
) -> list[IndicatorExtract]:
    """Pass 3: extract IOCs from raw_payload using dot-notation field paths."""
    indicators: list[IndicatorExtract] = []

    for mapping in mappings:
        raw_value = _traverse(raw_payload, mapping.field_path)
        if not raw_value:
            continue
        try:
            itype = IndicatorType(mapping.indicator_type)
        except ValueError:
            logger.warning(
                "indicator_mapping_unknown_type",
                field_path=mapping.field_path,
                indicator_type=mapping.indicator_type,
            )
            continue
        indicators.append(
            IndicatorExtract(
                type=itype,
                value=raw_value,
                source_field=f"raw_payload.{mapping.field_path}",
            )
        )
    return indicators


def extract_for_fingerprint(
    source: AlertSourceBase,
    normalized: CalsetaAlert,
    raw_payload: dict[str, Any],
    cached_mappings: list[Any],
) -> list[IndicatorExtract]:
    """
    Run Pass 1 + Pass 2 extraction for fingerprint generation — no persistence.

    Each pass is wrapped in try/except — failures are logged, never raised.
    Returns the deduplicated list of IndicatorExtract objects.
    """
    # Pass 1: source plugin
    try:
        pass1 = source.extract_indicators(raw_payload)
    except Exception:
        logger.exception(
            "fingerprint_extraction_pass1_failed",
            source_name=normalized.source_name,
        )
        pass1 = []

    # Pass 2: normalized field mappings (using cached mappings)
    try:
        pass2 = _extract_normalized(normalized, cached_mappings)
    except Exception:
        logger.exception(
            "fingerprint_extraction_pass2_failed",
            source_name=normalized.source_name,
        )
        pass2 = []

    # Merge and deduplicate by (type, value)
    seen: set[tuple[str, str]] = set()
    unique: list[IndicatorExtract] = []
    for ind in [*pass1, *pass2]:
        key = (str(ind.type), ind.value.strip())
        if key[1] and key not in seen:
            seen.add(key)
            unique.append(ind)

    logger.debug(
        "fingerprint_extraction_summary",
        source_name=normalized.source_name,
        pass1=len(pass1),
        pass2=len(pass2),
        unique=len(unique),
    )
    return unique


class IndicatorExtractionService:
    def __init__(self, db: AsyncSession) -> None:
        self._indicator_repo = IndicatorRepository(db)
        self._mapping_repo = IndicatorMappingRepository(db)

    async def extract_and_persist(
        self,
        alert: Alert,
        normalized: CalsetaAlert,
        raw_payload: dict[str, Any],
        source: AlertSourceBase,
    ) -> int:
        """
        Run 3-pass extraction pipeline and persist results.

        Returns the count of unique indicators linked to the alert.
        Errors in individual passes are logged and skipped — never raised.
        """
        now = datetime.now(UTC)
        source_name = normalized.source_name

        # Pass 1: source plugin
        try:
            pass1 = source.extract_indicators(raw_payload)
        except Exception:
            logger.exception("indicator_extraction_pass1_failed", source_name=source_name)
            pass1 = []

        # Pass 2: normalized field mappings
        try:
            norm_mappings = await self._mapping_repo.get_active_for_extraction(
                source_name=source_name, extraction_target="normalized"
            )
            pass2 = _extract_normalized(normalized, norm_mappings)
        except Exception:
            logger.exception("indicator_extraction_pass2_failed", source_name=source_name)
            pass2 = []

        # Pass 3: raw_payload field mappings
        try:
            raw_mappings = await self._mapping_repo.get_active_for_extraction(
                source_name=source_name, extraction_target="raw_payload"
            )
            pass3 = _extract_raw(raw_payload, raw_mappings)
        except Exception:
            logger.exception("indicator_extraction_pass3_failed", source_name=source_name)
            pass3 = []

        # Merge and deduplicate by (type, value)
        seen: set[tuple[str, str]] = set()
        unique: list[IndicatorExtract] = []
        for ind in [*pass1, *pass2, *pass3]:
            key = (str(ind.type), ind.value.strip())
            if key[1] and key not in seen:
                seen.add(key)
                unique.append(ind)

        logger.debug(
            "indicator_extraction_summary",
            alert_uuid=str(alert.uuid),
            pass1=len(pass1),
            pass2=len(pass2),
            pass3=len(pass3),
            unique=len(unique),
        )

        # Persist each unique indicator and link to alert
        for ind in unique:
            try:
                indicator = await self._indicator_repo.upsert(
                    str(ind.type), ind.value.strip(), now
                )
                await self._indicator_repo.link_to_alert(indicator.id, alert.id)
            except Exception:
                logger.exception(
                    "indicator_persist_failed",
                    itype=str(ind.type),
                    value=ind.value[:64],
                )

        return len(unique)
