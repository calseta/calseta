"""
MCP server entry point.

Exposes Calseta data via the Model Context Protocol for AI agent consumption.
Runs as a standalone process on port 8001.

Resources:  calseta://alerts, calseta://alerts/{uuid}, etc.
Tools:      post_alert_finding, update_alert_status, execute_workflow, etc.

Chunk 1.1: stub that starts cleanly. Full MCP server implemented in Wave 7.
"""

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the Calseta MCP server."""
    logger.info("Calseta MCP server starting...")
    # Full implementation in Wave 7 (chunk 7.1–7.5)
    # Structlog configured in chunk 1.10
    logger.info("Calseta MCP server ready (stub — full implementation in Wave 7)")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
