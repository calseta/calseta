"""Helper to create test alert rows directly in the DB for control plane tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.alert import Alert


async def create_enriched_alert(
    db: AsyncSession,
    *,
    title: str = "Test Enriched Alert",
    severity: str = "High",
    source_name: str = "generic",
    status: str = "Open",
    enrichment_status: str = "Enriched",
    tags: list[str] | None = None,
    raw_payload: dict[str, Any] | None = None,
) -> Alert:
    """
    Insert an alert row directly into the DB and return it.

    Bypasses ingest/enrichment pipeline so tests can control exactly what
    enrichment_status and status values are set — critical for queue tests
    that need 'Enriched' alerts without running the worker.
    """
    alert = Alert(
        title=title,
        severity=severity,
        source_name=source_name,
        status=status,
        enrichment_status=enrichment_status,
        occurred_at=datetime.now(UTC),
        tags=tags or ["test"],
        raw_payload=raw_payload or {"title": title, "severity": severity},
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return alert
