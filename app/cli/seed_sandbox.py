"""
Seed the database with sandbox fixture data (detection rules, context docs,
alerts with mock enrichment, and a public API key).

Requires ENRICHMENT_MOCK_MODE=true and SANDBOX_MODE=true in the environment.

Usage:
    python -m app.cli.seed_sandbox

Docker:
    docker compose exec api python -m app.cli.seed_sandbox
"""

from __future__ import annotations

import asyncio
import sys

import structlog

from app.logging_config import configure_logging

configure_logging("cli")
logger = structlog.get_logger(__name__)


async def _run() -> None:
    from app.config import settings
    from app.db.session import AsyncSessionLocal
    from app.seed.sandbox import seed_sandbox

    if not settings.SANDBOX_MODE:
        print("Error: SANDBOX_MODE must be set to true.", file=sys.stderr)
        sys.exit(1)
    if not settings.ENRICHMENT_MOCK_MODE:
        print("Error: ENRICHMENT_MOCK_MODE must be set to true.", file=sys.stderr)
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        await seed_sandbox(db)
        await db.commit()

    print()
    print("Sandbox data seeded successfully.")
    print()


def main() -> None:
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        logger.error("seed_sandbox_failed", error=str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
