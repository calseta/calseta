"""
MCP server entry point.

Exposes Calseta data via the Model Context Protocol for AI agent consumption.
Runs as a standalone process on port 8001.

Resources:  calseta://alerts, calseta://alerts/{uuid}, etc.
Tools:      post_alert_finding, update_alert_status, execute_workflow, etc.

Chunk 1.1: stub that starts cleanly. Full MCP server implemented in Wave 7.
"""

from __future__ import annotations

import asyncio

from app.logging_config import configure_logging

configure_logging("mcp")

import structlog  # noqa: E402 (must be after configure_logging)

logger = structlog.get_logger(__name__)


async def main() -> None:
    """Start the Calseta MCP server."""
    logger.info("calseta_mcp_starting")
    # Full implementation in Wave 7 (chunk 7.1–7.5)
    logger.info("calseta_mcp_ready", note="stub — full implementation in Wave 7")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
