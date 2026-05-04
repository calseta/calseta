#!/usr/bin/env python3
"""One-shot data fix: backfill ``agent_registrations.tool_ids`` from
``agent_registrations.capabilities['tools']``.

Wave 5 / S13: prior to the AgentService write-path resolver, agents could
be persisted with ``capabilities.tools`` populated but ``tool_ids`` empty.
This script walks every agent row, resolves the slugs declared in
``capabilities.tools`` against ``agent_tools`` (matching by ``id`` — slug
== id per the lab seeder), and writes the intersection back to
``tool_ids``.

Behavior:
    * Idempotent — only writes when the resolved set differs from the
      stored set.
    * Tolerates aspirational/unknown slugs by skipping them with a
      summary warning. (The API path hard-rejects unknown slugs; the
      backfill is intentionally lenient because pre-existing rows may
      have been written before the resolver landed.)
    * Async: opens its own engine via ``settings.DATABASE_URL`` so it
      can be run as a one-shot from the host.

Usage::

    python scripts/backfill_tool_ids.py
    python scripts/backfill_tool_ids.py --dry-run

Exit codes::

    0 — success (rows updated and/or already correct)
    1 — DB connection failed or fatal error
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.db.models.agent_registration import AgentRegistration
from app.db.models.agent_tool import AgentTool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill agent_registrations.tool_ids from "
            "capabilities.tools by resolving slugs against agent_tools."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing to the database.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "Override the DATABASE_URL setting. Useful when running "
            "against a non-default DB (e.g. calseta_test)."
        ),
    )
    return parser.parse_args()


def _extract_capability_slugs(capabilities: Any) -> list[str]:
    """Return the de-duplicated string slugs from capabilities.tools.

    Defensive: capabilities is JSONB, so callers may have written
    anything. Non-list / non-string entries are silently ignored — the
    backfill should never crash on a single malformed row.
    """
    if not isinstance(capabilities, dict):
        return []
    raw = capabilities.get("tools")
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for entry in raw:
        if not isinstance(entry, str) or entry in seen:
            continue
        seen.add(entry)
        out.append(entry)
    return out


async def _load_known_tool_ids(db: AsyncSession) -> set[str]:
    """Return the set of agent_tools.id values currently in the DB."""
    result = await db.execute(select(AgentTool.id))
    return {row[0] for row in result.all()}


async def backfill(db: AsyncSession, dry_run: bool) -> dict[str, Any]:
    """Walk every agent registration and reconcile tool_ids.

    Caller is responsible for committing the session — the helper only
    flushes. Keeping commit at the call site lets tests run this against
    a SAVEPOINT-wrapped session without breaking the rollback contract.

    Returns a stats dict with keys:
        agents_total, agents_updated, agents_already_correct,
        agents_no_capabilities, unknown_slugs (list[str]).
    """
    known_tool_ids = await _load_known_tool_ids(db)

    result = await db.execute(
        select(AgentRegistration).order_by(AgentRegistration.id.asc())
    )
    agents = list(result.scalars().all())

    agents_updated = 0
    agents_already_correct = 0
    agents_no_capabilities = 0
    unknown_slugs_seen: set[str] = set()

    for agent in agents:
        slugs = _extract_capability_slugs(agent.capabilities)
        if not slugs:
            agents_no_capabilities += 1
            continue

        unknown_in_row = [s for s in slugs if s not in known_tool_ids]
        unknown_slugs_seen.update(unknown_in_row)
        # Preserve operator-declared order; drop unknowns silently.
        resolved = [s for s in slugs if s in known_tool_ids]

        current = list(agent.tool_ids or [])
        if current == resolved:
            agents_already_correct += 1
            continue

        if not dry_run:
            agent.tool_ids = resolved
            await db.flush()
        agents_updated += 1
        print(
            f"  {'[dry-run] ' if dry_run else ''}agent={agent.name!r} "
            f"uuid={agent.uuid} "
            f"old_tool_ids={current} -> new_tool_ids={resolved}"
        )

    return {
        "agents_total": len(agents),
        "agents_updated": agents_updated,
        "agents_already_correct": agents_already_correct,
        "agents_no_capabilities": agents_no_capabilities,
        "unknown_slugs": sorted(unknown_slugs_seen),
    }


async def main() -> int:
    args = parse_args()
    db_url = args.database_url or settings.DATABASE_URL
    if not db_url:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        return 1

    engine = create_async_engine(db_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    print("Calseta — backfill agent_registrations.tool_ids")
    print("=" * 60)
    print(f"DATABASE_URL: {db_url}")
    print(f"Mode:         {'DRY RUN' if args.dry_run else 'WRITE'}")
    print()

    try:
        async with session_factory() as session:
            stats = await backfill(session, dry_run=args.dry_run)
            if not args.dry_run:
                await session.commit()
    except Exception as exc:  # noqa: BLE001 — top-level CLI guard
        print(f"FATAL: {exc}", file=sys.stderr)
        await engine.dispose()
        return 1

    await engine.dispose()

    print()
    print("Summary")
    print("-" * 60)
    print(f"agents total:              {stats['agents_total']}")
    print(f"agents updated:            {stats['agents_updated']}")
    print(f"agents already correct:    {stats['agents_already_correct']}")
    print(f"agents w/o capabilities:   {stats['agents_no_capabilities']}")
    if stats["unknown_slugs"]:
        print(
            "unknown slugs (skipped):   "
            + ", ".join(stats["unknown_slugs"])
        )
        print(
            "  (these tool slugs appear in capabilities.tools but are not "
            "in agent_tools — they were dropped from tool_ids)"
        )
    else:
        print("unknown slugs:             (none)")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
