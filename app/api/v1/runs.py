"""
Agent run endpoints — streaming, polling, and lifecycle.

GET  /v1/runs/{uuid}/events  — Paginated run events (HTTP polling)
GET  /v1/runs/{uuid}/stream  — SSE live event stream
POST /v1/runs/{uuid}/cancel  — Cancel a running agent (stub, B3 implements)
"""

from __future__ import annotations

import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.errors import CalsetaException
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.repositories.heartbeat_run_repository import (
    HeartbeatRunRepository,
)
from app.repositories.run_event_repository import RunEventRepository
from app.schemas.common import DataResponse

router = APIRouter(prefix="/runs", tags=["runs"])

_Read = Annotated[
    AuthContext, Depends(require_scope(Scope.AGENTS_READ))
]
_Write = Annotated[
    AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))
]


async def _get_run_or_404(
    run_uuid: UUID,
    db: AsyncSession,
) -> Any:
    """Load HeartbeatRun by UUID or raise 404."""
    repo = HeartbeatRunRepository(db)
    run = await repo.get_by_uuid(run_uuid)
    if run is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Run not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return run


def _serialize_event(e: Any) -> dict[str, Any]:
    """Serialize a single AgentRunEvent to a dict."""
    return {
        "seq": e.seq,
        "event_type": e.event_type,
        "stream": e.stream,
        "level": e.level,
        "content": e.content,
        "payload": e.payload,
        "created_at": (
            e.created_at.isoformat() if e.created_at else None
        ),
    }


# -------------------------------------------------------------------
# GET /v1/runs/{uuid}/events — HTTP polling
# -------------------------------------------------------------------


@router.get("/{run_uuid}/events")
@limiter.limit(
    f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute"
)
async def get_run_events(
    request: Request,
    run_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> DataResponse[list[dict[str, Any]]]:
    """Return paginated run events for polling clients."""
    run = await _get_run_or_404(run_uuid, db)
    repo = RunEventRepository(db)
    events = await repo.list_for_run(
        heartbeat_run_id=run.id,
        after_seq=after_seq,
        limit=limit,
    )
    return DataResponse(
        data=[_serialize_event(e) for e in events],
    )


# -------------------------------------------------------------------
# GET /v1/runs/{uuid}/stream — SSE
# -------------------------------------------------------------------

_TERMINAL_STATUSES = frozenset(
    {"succeeded", "failed", "cancelled", "timed_out"}
)


@router.get("/{run_uuid}/stream")
@limiter.limit(
    f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute"
)
async def stream_run_events(
    request: Request,
    run_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
    last_event_id: str | None = Header(
        default=None,
        alias="Last-Event-ID",
    ),
) -> StreamingResponse:
    """SSE endpoint for live run event streaming."""
    run = await _get_run_or_404(run_uuid, db)

    # If the run is already terminal, replay stored events then close
    if run.status in _TERMINAL_STATUSES:
        after_seq = int(last_event_id) if last_event_id else 0
        repo = RunEventRepository(db)
        events = await repo.list_for_run(
            heartbeat_run_id=run.id,
            after_seq=after_seq,
            limit=500,
        )

        async def _completed_stream() -> Any:
            for e in events:
                data = json.dumps(_serialize_event(e))
                yield f"id: {e.seq}\ndata: {data}\n\n"

        return StreamingResponse(
            _completed_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Live streaming via LISTEN/NOTIFY
    from app.services.run_event_stream import (
        listen_for_run_events,
    )

    database_url = settings.DATABASE_URL

    async def _live_stream() -> Any:
        async for event in listen_for_run_events(
            database_url=database_url,
            run_id=run.id,
        ):
            seq = event.get("seq", 0)
            data = json.dumps(event, default=str)
            yield f"id: {seq}\ndata: {data}\n\n"

    return StreamingResponse(
        _live_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# -------------------------------------------------------------------
# POST /v1/runs/{uuid}/cancel — stub (B3 implements)
# -------------------------------------------------------------------


@router.post(
    "/{run_uuid}/cancel",
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(
    f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute"
)
async def cancel_run_endpoint(
    request: Request,
    run_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[dict[str, str]]:
    """Request cancellation of a running agent."""
    from app.services.run_cancellation import cancel_run

    run = await _get_run_or_404(run_uuid, db)
    if run.status in _TERMINAL_STATUSES:
        raise CalsetaException(
            code="RUN_ALREADY_TERMINAL",
            message=(
                f"Run is already in terminal state: {run.status}"
            ),
            status_code=status.HTTP_409_CONFLICT,
        )
    await cancel_run(run, db)
    return DataResponse(
        data={"status": "cancelled", "run_uuid": str(run_uuid)},
    )
