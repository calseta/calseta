"""
Sandbox reset — wipe transient data, delete user-created config, re-seed fixtures.

Designed to run as a periodic procrastinate task (daily at midnight UTC).
Can also be called directly for manual resets.

Reset phases:
  1. Delete transient/audit data (all rows — these are always re-creatable)
  2. Delete all alerts + indicators (re-seeded in phase 4)
  3. Delete user-created config only (is_system=FALSE)
  4. Re-seed sandbox fixtures
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)

# Phase 1: Transient/audit tables — delete ALL rows
_PHASE1_TABLES = [
    "workflow_runs",
    "workflow_approval_requests",
    "workflow_code_versions",
    "agent_runs",
    "activity_events",
    "agent_registrations",
]

# Phase 2: Alert + indicator tables — delete ALL rows (order matters for FK constraints)
_PHASE2_TABLES = [
    "alert_indicators",
    "alerts",
    "indicators",
]

# Phase 3: Config tables — delete only user-created rows (is_system = FALSE)
_PHASE3_TABLES = [
    "detection_rules",
    "workflows",
    "api_keys",
]


async def reset_sandbox() -> dict[str, int]:
    """
    Reset the sandbox database and re-seed fixtures.

    Returns a dict of table_name → rows_deleted for logging/verification.
    """
    counts: dict[str, int] = {}

    async with AsyncSessionLocal() as db:
        logger.info("sandbox_reset_starting")

        # Phase 1: Delete all transient/audit data
        for table in _PHASE1_TABLES:
            result = await db.execute(text(f"DELETE FROM {table}"))  # noqa: S608
            counts[table] = result.rowcount  # type: ignore[attr-defined]

        # Phase 2: Delete all alerts + indicators
        for table in _PHASE2_TABLES:
            result = await db.execute(text(f"DELETE FROM {table}"))  # noqa: S608
            counts[table] = result.rowcount  # type: ignore[attr-defined]

        # Phase 3: Delete user-created config (is_system = FALSE)
        for table in _PHASE3_TABLES:
            result = await db.execute(
                text(f"DELETE FROM {table} WHERE is_system = FALSE")  # noqa: S608
            )
            counts[table] = result.rowcount  # type: ignore[attr-defined]

        await db.flush()

        logger.info(
            "sandbox_reset_phase_1_2_3_complete",
            deleted_counts=counts,
        )

        # Phase 4: Re-seed
        await _reseed(db)

        await db.commit()
        logger.info("sandbox_reset_complete", deleted_counts=counts)

    return counts


async def _reseed(db: AsyncSession) -> None:
    """Re-seed sandbox fixtures after reset."""
    from app.seed.sandbox import seed_sandbox

    await seed_sandbox(db)
