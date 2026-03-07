"""
Create an API key directly in the database.

This is the bootstrap command — use it to create the first admin key before
any authenticated API calls are possible.

Usage:
    python -m app.cli.create_api_key --name bootstrap-admin --scopes admin
    python -m app.cli.create_api_key --name sentinel-ingest \
        --scopes alerts:write --allowed-sources sentinel
    python -m app.cli.create_api_key --name read-only \
        --scopes alerts:read workflows:read

Docker:
    docker compose exec api python -m app.cli.create_api_key --name bootstrap-admin --scopes admin
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from app.db.session import AsyncSessionLocal
from app.logging_config import configure_logging
from app.repositories.api_key_repository import APIKeyRepository

configure_logging("cli")
logger = structlog.get_logger(__name__)

VALID_SCOPES = [
    "admin",
    "alerts:read",
    "alerts:write",
    "enrichments:read",
    "workflows:read",
    "workflows:write",
    "workflows:execute",
    "approvals:write",
    "agents:read",
    "agents:write",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Calseta API key.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m app.cli.create_api_key --name bootstrap-admin --scopes admin\n"
            "  python -m app.cli.create_api_key --name my-agent \\\n"
            "      --scopes alerts:read alerts:write enrichments:read\n"
            "  python -m app.cli.create_api_key --name sentinel-only \\\n"
            "      --scopes alerts:write --allowed-sources sentinel"
        ),
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Human-readable name for this API key (e.g. 'bootstrap-admin')",
    )
    parser.add_argument(
        "--scopes",
        nargs="+",
        required=True,
        help=f"Space-separated list of scopes. Valid: {', '.join(VALID_SCOPES)}",
    )
    parser.add_argument(
        "--allowed-sources",
        nargs="*",
        default=None,
        help=(
            "Restrict key to specific alert sources "
            "(e.g. sentinel elastic). Omit for unrestricted."
        ),
    )
    parser.add_argument(
        "--expires-at",
        default=None,
        help="Optional expiry in ISO 8601 format (e.g. 2026-12-31T23:59:59Z)",
    )
    return parser.parse_args()


async def _create_key(args: argparse.Namespace) -> None:
    # Validate scopes
    invalid = [s for s in args.scopes if s not in VALID_SCOPES]
    if invalid:
        print(f"Error: invalid scope(s): {', '.join(invalid)}", file=sys.stderr)
        print(f"Valid scopes: {', '.join(VALID_SCOPES)}", file=sys.stderr)
        sys.exit(1)

    # Parse optional expiry
    expires_at = None
    if args.expires_at:
        from datetime import datetime

        try:
            expires_at = datetime.fromisoformat(args.expires_at)
        except ValueError:
            print(f"Error: invalid expires_at format: {args.expires_at}", file=sys.stderr)
            print("Expected ISO 8601 (e.g. 2026-12-31T23:59:59Z)", file=sys.stderr)
            sys.exit(1)

    async with AsyncSessionLocal() as session:
        repo = APIKeyRepository(session)
        record, plain_key = await repo.create(
            name=args.name,
            scopes=args.scopes,
            expires_at=expires_at,
            allowed_sources=args.allowed_sources,
        )
        await session.commit()

    print()
    print("API key created successfully.")
    print()
    print(f"  Name:    {record.name}")
    print(f"  UUID:    {record.uuid}")
    print(f"  Prefix:  {record.key_prefix}")
    print(f"  Scopes:  {', '.join(record.scopes)}")
    if record.allowed_sources:
        print(f"  Sources: {', '.join(record.allowed_sources)}")
    if record.expires_at:
        print(f"  Expires: {record.expires_at.isoformat()}")
    print()
    print(f"  {plain_key}")
    print()
    print("Save this key now. It will not be shown again.")


def main() -> None:
    args = _parse_args()
    try:
        asyncio.run(_create_key(args))
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        logger.error("create_api_key_failed", error=str(exc))
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
