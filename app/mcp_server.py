"""
MCP server entry point.

Exposes Calseta data via the Model Context Protocol for AI agent consumption.
Runs as a standalone process on port 8001 (configurable via MCP_PORT).

Resources:  calseta://alerts, calseta://alerts/{uuid}, etc.
Tools:      post_alert_finding, update_alert_status, execute_workflow, etc.

Started via: ``python -m app.mcp_server``
"""

from __future__ import annotations

import asyncio
import sys

from app.logging_config import configure_logging

configure_logging("mcp")

import structlog  # noqa: E402 (must be after configure_logging)

from app.config import settings  # noqa: E402

logger = structlog.get_logger(__name__)


async def _load_enrichment_registry() -> None:
    """Load enrichment providers from DB into the in-memory registry."""
    from app.db.session import AsyncSessionLocal
    from app.integrations.enrichment.registry import enrichment_registry

    try:
        async with AsyncSessionLocal() as db:
            await enrichment_registry.load_from_database(db)
    except Exception as exc:
        logger.warning(
            "enrichment_registry_load_skipped",
            error=str(exc),
            hint="Enrichment tools will not find any providers.",
        )


def main() -> None:
    """Start the Calseta MCP server."""
    logger.info(
        "calseta_mcp_starting",
        host=settings.MCP_HOST,
        port=settings.MCP_PORT,
    )

    try:
        # Import resource modules so @mcp_server.resource decorators register
        import app.mcp.resources.alerts  # noqa: E402, F401
        import app.mcp.resources.context_documents  # noqa: E402, F401
        import app.mcp.resources.detection_rules  # noqa: E402, F401
        import app.mcp.resources.enrichments  # noqa: E402, F401
        import app.mcp.resources.metrics  # noqa: E402, F401
        import app.mcp.resources.workflows  # noqa: E402, F401

        # Import tool modules so @mcp_server.tool decorators register
        import app.mcp.tools.actions  # noqa: E402, F401
        import app.mcp.tools.alerts  # noqa: E402, F401
        import app.mcp.tools.detection_rules  # noqa: E402, F401
        import app.mcp.tools.enrichment  # noqa: E402, F401
        import app.mcp.tools.issues  # noqa: E402, F401
        import app.mcp.tools.orchestration  # noqa: E402, F401
        import app.mcp.tools.workflows  # noqa: E402, F401

        # Load enrichment providers from DB before starting the server
        asyncio.run(_load_enrichment_registry())

        from app.mcp.server import mcp_server  # noqa: E402

        mcp_server.run(transport="sse")
    except OSError as exc:
        # Descriptive error if port is already in use (errno 48 / 98)
        logger.error(
            "calseta_mcp_startup_failed",
            error=str(exc),
            hint=f"Port {settings.MCP_PORT} may already be in use. "
            f"Set MCP_PORT to a different value or stop the conflicting process.",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
