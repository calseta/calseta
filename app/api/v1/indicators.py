"""
Indicator routes.

GET   /v1/indicators/{uuid} — Get single indicator with full enrichment data (including raw)
PATCH /v1/indicators/{uuid} — Update indicator malice (analyst override or reset to enrichment)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.db.session import get_db
from app.repositories.indicator_repository import IndicatorRepository
from app.schemas.activity_events import ActivityEventType
from app.schemas.common import DataResponse
from app.schemas.indicators import IndicatorDetailResponse, IndicatorPatch
from app.services.activity_event import ActivityEventService

router = APIRouter(prefix="/indicators", tags=["indicators"])

_EnrichRead = Annotated[AuthContext, Depends(require_scope(Scope.ENRICHMENTS_READ))]
_AlertsWrite = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_WRITE))]


def _build_detail(indicator: object) -> IndicatorDetailResponse:
    from app.db.models.indicator import Indicator

    assert isinstance(indicator, Indicator)
    return IndicatorDetailResponse(
        uuid=str(indicator.uuid),
        type=indicator.type,  # type: ignore[arg-type]
        value=indicator.value,
        malice=indicator.malice,
        malice_source=indicator.malice_source,
        malice_overridden_at=indicator.malice_overridden_at,
        first_seen=indicator.first_seen,
        last_seen=indicator.last_seen,
        is_enriched=indicator.is_enriched,
        enrichment_results=indicator.enrichment_results,
        created_at=indicator.created_at,
        updated_at=indicator.updated_at,
    )


@router.get(
    "/{indicator_uuid}",
    response_model=DataResponse[IndicatorDetailResponse],
)
async def get_indicator(
    indicator_uuid: UUID,
    auth: _EnrichRead,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[IndicatorDetailResponse]:
    """
    Return a single indicator with full enrichment data including raw
    provider responses. Used for the indicator detail sheet drill-down.
    """
    repo = IndicatorRepository(db)
    indicator = await repo.get_by_uuid(str(indicator_uuid))
    if indicator is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Indicator not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return DataResponse(data=_build_detail(indicator))


@router.patch(
    "/{indicator_uuid}",
    response_model=DataResponse[IndicatorDetailResponse],
)
async def patch_indicator(
    indicator_uuid: UUID,
    body: IndicatorPatch,
    auth: _AlertsWrite,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[IndicatorDetailResponse]:
    """
    Update an indicator's malice verdict.

    Send `{"malice": "Malicious"}` to set an analyst override.
    Send `{"malice": null}` to reset to the enrichment-computed value.
    """
    repo = IndicatorRepository(db)
    activity_svc = ActivityEventService(db)

    indicator = await repo.get_by_uuid(str(indicator_uuid))
    if indicator is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Indicator not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    prev_malice = indicator.malice
    now = datetime.now(UTC)

    await repo.patch_malice(
        indicator,
        malice=body.malice.value if body.malice is not None else None,
        now=now,
    )

    # Write activity event (find an associated alert for the FK)
    from app.db.models.alert_indicator import AlertIndicator

    from sqlalchemy import select

    alert_link = await db.execute(
        select(AlertIndicator.alert_id)
        .where(AlertIndicator.indicator_id == indicator.id)
        .limit(1)
    )
    alert_id = alert_link.scalar_one_or_none()

    await activity_svc.write(
        ActivityEventType.INDICATOR_MALICE_UPDATED,
        actor_type="api",
        actor_key_prefix=auth.key_prefix,
        alert_id=alert_id,
        references={
            "from_malice": prev_malice,
            "to_malice": indicator.malice,
            "malice_source": indicator.malice_source,
            "indicator_type": indicator.type,
            "indicator_value": indicator.value,
        },
    )

    return DataResponse(data=_build_detail(indicator))
