"""
SSE event stream service — bridges PostgreSQL NOTIFY to SSE clients.

The worker process emits NOTIFY on ``calseta_run_events`` channel after
each event insert.  This service LISTENs on that channel and yields
events to the SSE endpoint.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

CHANNEL = "calseta_run_events"

# Postgres caps NOTIFY payloads at 8000 bytes. We leave headroom for the
# "{run_id}:{seq}:" prefix and any UTF-8 expansion; events whose serialized
# form exceeds this cap are sent as a compact stub and clients backfill via
# GET /v1/runs/{uuid}/events?after_seq=...
_MAX_NOTIFY_PAYLOAD_BYTES = 6000


async def listen_for_run_events(
    database_url: str,
    run_id: int,
    timeout: float = 300.0,
) -> AsyncGenerator[dict[str, Any], None]:
    """Yield run events via PostgreSQL LISTEN/NOTIFY.

    Each NOTIFY payload is ``{run_id}:{seq}:{event_json}``.
    We filter to only yield events matching our *run_id*.
    Stops after *timeout* seconds or when a terminal status event arrives.
    """
    try:
        import asyncpg  # type: ignore[import-untyped]
    except ImportError:
        logger.error("asyncpg required for SSE streaming")
        return

    # asyncpg needs a plain postgresql:// DSN, not the SQLAlchemy asyncpg variant
    dsn = database_url.replace(
        "postgresql+asyncpg", "postgresql"
    )
    conn = await asyncpg.connect(dsn)
    try:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def _on_notify(
            connection: Any,
            pid: int,
            channel: str,
            payload: str,
        ) -> None:
            try:
                parts = payload.split(":", 2)
                if len(parts) >= 3 and int(parts[0]) == run_id:
                    event = json.loads(parts[2])
                    event["seq"] = int(parts[1])
                    queue.put_nowait(event)
            except (ValueError, json.JSONDecodeError):
                pass

        await conn.add_listener(CHANNEL, _on_notify)

        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        queue.get(),
                        timeout=timeout,
                    )
                    yield event
                    # Stop on terminal status
                    if event.get("event_type") == "status_change":
                        p = event.get("payload") or {}
                        status = p.get("status", "")
                        if status in (
                            "succeeded",
                            "failed",
                            "cancelled",
                            "timed_out",
                        ):
                            return
                except TimeoutError:
                    return
        finally:
            await conn.remove_listener(CHANNEL, _on_notify)
    finally:
        await conn.close()


async def notify_run_event(
    db_session: Any,
    run_id: int,
    seq: int,
    event_data: dict[str, Any],
) -> None:
    """Emit a NOTIFY on the run events channel.

    Called by the engine after writing each event to the DB. Two safeguards:

    1.  Payload cap. Postgres rejects NOTIFY payloads ≥ 8000 bytes. Large LLM
        responses easily exceed that, so we replace oversized payloads with a
        compact stub ({event_type, stream, _truncated: true}). SSE clients can
        backfill the full event via GET /v1/runs/{uuid}/events?after_seq=...
    2.  Savepoint isolation. The pg_notify call shares the engine's session;
        without a SAVEPOINT, any failure here aborts the outer transaction
        and poisons the just-written agent_run_events INSERT plus every
        subsequent ORM access on this session. We wrap pg_notify in
        ``begin_nested()`` so a NOTIFY failure rolls back only the savepoint.
    """
    encoded_event = json.dumps(event_data, default=str)
    full_payload = f"{run_id}:{seq}:{encoded_event}"

    if len(full_payload.encode("utf-8")) > _MAX_NOTIFY_PAYLOAD_BYTES:
        stub = {
            "event_type": event_data.get("event_type"),
            "stream": event_data.get("stream"),
            "_truncated": True,
            "content_bytes": len(encoded_event),
        }
        full_payload = f"{run_id}:{seq}:{json.dumps(stub)}"

    from sqlalchemy import text

    savepoint = await db_session.begin_nested()
    try:
        await db_session.execute(
            text(f"SELECT pg_notify('{CHANNEL}', :payload)"),
            {"payload": full_payload},
        )
        await savepoint.commit()
    except Exception as exc:
        # NOTIFY failure is non-fatal — SSE clients still work via polling.
        # Rolling back the savepoint leaves the outer transaction healthy.
        try:
            await savepoint.rollback()
        except Exception:
            pass
        logger.debug("notify_run_event_failed", error=str(exc), seq=seq)
