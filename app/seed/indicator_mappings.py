"""
System indicator field mapping seeder.

Inserts the 14 standard CalsetaAlert → indicator type mappings at
application startup. Idempotent — re-running makes no DB writes if the
mappings are already present.

Called from app/main.py startup event:
    await seed_system_mappings(db)

Failures log a warning and do not crash the server — missing system
mappings degrade indicator extraction but don't block alert ingestion.

Design note:
    PRD Section 7.12 lists 14 CalsetaAlert normalized-field mappings.
    PROJECT_PLAN.md references 17 — the discrepancy is logged in
    DECISIONS.md. Implemented the authoritative 14 from the PRD.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.indicator_field_mapping import IndicatorFieldMapping

logger = structlog.get_logger(__name__)

# PRD §7.12 — CalsetaAlert → indicator type system mappings
# Each entry: (field_path, indicator_type, description)
_SYSTEM_MAPPINGS: list[tuple[str, str, str]] = [
    ("src_ip",         "ip",          "Source IP address"),
    ("dst_ip",         "ip",          "Destination IP address"),
    ("src_hostname",   "domain",      "Source hostname"),
    ("dst_hostname",   "domain",      "Destination hostname"),
    ("file_hash_md5",  "hash_md5",    "File hash, MD5"),
    ("file_hash_sha256", "hash_sha256", "File hash, SHA-256"),
    ("file_hash_sha1", "hash_sha1",   "File hash, SHA-1"),
    ("actor_email",    "email",       "Actor email address"),
    ("actor_username", "account",     "Actor username"),
    ("dns_query",      "domain",      "DNS query target"),
    ("http_url",       "url",         "Full URL string"),
    ("http_hostname",  "domain",      "URL hostname"),
    ("email_from",     "email",       "Email sender address"),
    ("email_reply_to", "email",       "Email reply-to address"),
]


async def seed_system_mappings(db: AsyncSession) -> None:
    """
    Idempotently insert all 14 system indicator field mappings.

    Uniqueness check: `(field_path, extraction_target)` — if a row with
    the same combination already exists, it is skipped (not updated).
    This means manual changes to descriptions or is_active on existing
    system rows are preserved across restarts.
    """
    inserted = 0

    for field_path, indicator_type, description in _SYSTEM_MAPPINGS:
        exists_result = await db.execute(
            select(IndicatorFieldMapping).where(
                IndicatorFieldMapping.field_path == field_path,
                IndicatorFieldMapping.extraction_target == "normalized",
            )
        )
        if exists_result.scalar_one_or_none() is not None:
            continue  # Already seeded — skip

        db.add(
            IndicatorFieldMapping(
                source_name=None,  # NULL = global / applies to all sources
                field_path=field_path,
                indicator_type=indicator_type,
                extraction_target="normalized",
                is_system=True,
                is_active=True,
                description=description,
            )
        )
        inserted += 1

    if inserted > 0:
        await db.flush()
        logger.info("indicator_mappings_seeded", count=inserted)
    else:
        logger.debug("indicator_mappings_already_seeded")
