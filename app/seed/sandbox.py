"""
Sandbox seeder orchestrator — seeds detection rules, context documents,
fixture alerts (with inline enrichment), and a public sandbox API key.

Called during startup when SANDBOX_MODE=true.
Idempotent: all sub-seeders check for existing data before inserting.
"""

from __future__ import annotations

import bcrypt
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.api_key import APIKey
from app.seed.sandbox_alerts import seed_sandbox_alerts
from app.seed.sandbox_context_documents import seed_sandbox_context_documents
from app.seed.sandbox_detection_rules import seed_sandbox_detection_rules

logger = structlog.get_logger(__name__)

# Well-known sandbox API key — public, read-only, never used in production.
# Prefix: "cai_sand" (first 8 chars of the full key).
_SANDBOX_API_KEY = "cai_sandbox_demo_key_not_for_production"
_SANDBOX_KEY_PREFIX = _SANDBOX_API_KEY[:8]
_SANDBOX_KEY_SCOPES = [
    "alerts:read",
    "enrichments:read",
    "workflows:read",
    "agents:read",
]

# Lab API key — full access for testing all functionality.
_LAB_API_KEY = "cai_lab_demo_full_access_key_not_for_prod"
_LAB_KEY_PREFIX = _LAB_API_KEY[:8]
_LAB_KEY_SCOPES = [
    "alerts:read",
    "alerts:write",
    "enrichments:read",
    "workflows:read",
    "workflows:execute",
    "approvals:write",
    "agents:read",
    "agents:write",
    "admin",
]


async def _seed_sandbox_api_key(db: AsyncSession) -> None:
    """Create the well-known sandbox API key if it doesn't exist."""
    existing = await db.execute(
        select(APIKey).where(
            APIKey.key_prefix == _SANDBOX_KEY_PREFIX,
            APIKey.is_system.is_(True),
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    key_hash = bcrypt.hashpw(_SANDBOX_API_KEY.encode(), bcrypt.gensalt(rounds=12)).decode()
    api_key = APIKey(
        name="Sandbox Demo Key (read-only)",
        key_prefix=_SANDBOX_KEY_PREFIX,
        key_hash=key_hash,
        scopes=_SANDBOX_KEY_SCOPES,
        is_active=True,
        is_system=True,
    )
    db.add(api_key)
    await db.flush()
    logger.info(
        "sandbox_api_key_seeded",
        key_prefix=_SANDBOX_KEY_PREFIX,
        scopes=_SANDBOX_KEY_SCOPES,
    )


async def _seed_lab_api_key(db: AsyncSession) -> None:
    """Create the lab API key (full access) if it doesn't exist."""
    existing = await db.execute(
        select(APIKey).where(
            APIKey.key_prefix == _LAB_KEY_PREFIX,
            APIKey.is_system.is_(True),
        )
    )
    if existing.scalar_one_or_none() is not None:
        return

    key_hash = bcrypt.hashpw(_LAB_API_KEY.encode(), bcrypt.gensalt(rounds=12)).decode()
    api_key = APIKey(
        name="Lab Demo Key (full access)",
        key_prefix=_LAB_KEY_PREFIX,
        key_hash=key_hash,
        scopes=_LAB_KEY_SCOPES,
        is_active=True,
        is_system=True,
    )
    db.add(api_key)
    await db.flush()
    logger.info(
        "lab_api_key_seeded",
        key_prefix=_LAB_KEY_PREFIX,
        scopes=_LAB_KEY_SCOPES,
    )


async def seed_sandbox(db: AsyncSession) -> None:
    """
    Run all sandbox seeders in order.

    Order matters:
      1. Detection rules (so alert ingestion can associate them)
      2. Context documents (so they're available for context matching)
      3. Alerts (ingested + enriched inline with mock providers)
      4. API keys (sandbox read-only + lab full-access)
    """
    logger.info("sandbox_seed_starting")

    await seed_sandbox_detection_rules(db)
    await seed_sandbox_context_documents(db)

    # Seed enrichment providers + field extractions, then load registry
    # so mock enrichment works during alert seeding.
    from app.seed.enrichment_providers import seed_builtin_providers

    await seed_builtin_providers(db)
    await db.flush()

    from app.integrations.enrichment.registry import enrichment_registry

    await enrichment_registry.load_from_database(db)

    await seed_sandbox_alerts(db)
    await _seed_sandbox_api_key(db)
    await _seed_lab_api_key(db)

    logger.info("sandbox_seed_complete")
