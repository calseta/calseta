"""Startup auto-migration of literal ``LLMIntegration.api_key_secret_ref`` rows.

Background (S3, 2026-05-05):
    Before this chunk, ``api_key_ref`` (now renamed to
    ``api_key_secret_ref``) was effectively a plaintext column. Self-hosters
    with existing rows that hold a literal API key value need those values
    migrated to the new ``enc:<ciphertext>`` form so that the hardened
    resolver in :mod:`app.integrations.llm.factory` can decrypt them.

Algorithm:
    1. Read every row in ``llm_integrations``.
    2. For each row whose ``api_key_secret_ref`` does NOT match a known
       prefix (``env:``, ``enc:``, ``vault:``, ``aws-sm:``, ``azure-kv:``),
       encrypt the literal with ``Fernet(settings.ENCRYPTION_KEY)`` and
       rewrite the column as ``enc:<ciphertext>``.
    3. Commit per row in its own transaction so a crash mid-loop leaves
       partially-migrated rows in a consistent state (any given row is
       either fully literal or fully encrypted, never half).

Idempotent: re-running on a row that already has a known prefix is a
no-op — the prefix check returns True and the row is skipped.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.encryption import encrypt_value
from app.db.models.llm_integration import LLMIntegration
from app.integrations.llm.factory import has_known_prefix

logger = structlog.get_logger(__name__)


async def migrate_literal_api_key_refs(db: AsyncSession) -> int:
    """Encrypt any ``llm_integrations.api_key_secret_ref`` that is still a literal.

    Returns:
        The number of rows that were rewritten this call. Zero on the
        steady state.
    """
    result = await db.execute(select(LLMIntegration))
    rows: list[LLMIntegration] = list(result.scalars().all())

    migrated_count = 0
    for row in rows:
        ref = row.api_key_secret_ref
        if ref is None or ref == "":
            # No key configured — nothing to migrate (e.g. claude_code
            # subscription rows).
            continue
        if has_known_prefix(ref):
            # Already in canonical form (env:/enc:/vault:/aws-sm:/azure-kv:).
            continue

        # Literal value: encrypt + rewrite. We DO NOT try to detect "looks
        # like a real key" — anything not matching a known prefix is by
        # definition a literal we need to migrate.
        try:
            ciphertext = encrypt_value(ref)
        except Exception as exc:  # noqa: BLE001
            # Most likely cause: ENCRYPTION_KEY not set. Without it we
            # cannot encrypt; leave the row as-is and log loudly. The
            # resolver will refuse to call the adapter on next read.
            logger.error(
                "secrets.literal_migration_failed",
                integration_id=row.id,
                integration_name=row.name,
                error=str(exc),
                hint=(
                    "Set ENCRYPTION_KEY and restart, or rewrite the row "
                    "manually to use env:/vault:/aws-sm:/azure-kv: prefix"
                ),
            )
            continue

        new_value = f"enc:{ciphertext}"
        row.api_key_secret_ref = new_value
        await db.commit()

        logger.info(
            "secrets.literal_migrated",
            integration_id=row.id,
            integration_name=row.name,
            new_prefix_8_chars=new_value[:8],
        )
        migrated_count += 1

    if migrated_count > 0:
        logger.info(
            "secrets.literal_migration_complete",
            migrated_count=migrated_count,
            scanned_rows=len(rows),
        )
    return migrated_count
