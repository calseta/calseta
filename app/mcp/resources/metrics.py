"""
MCP resource for metrics summary.

Exposes the compact SOC health snapshot as an MCP resource:
  - calseta://metrics/summary — Last 30 days, fixed window, optimized for agent context injection
"""

from __future__ import annotations

import json

from app.db.session import AsyncSessionLocal
from app.mcp.server import mcp_server
from app.services.metrics import compute_metrics_summary


@mcp_server.resource("calseta://metrics/summary")
async def get_metrics_summary() -> str:
    """Compact SOC health snapshot — alerts, workflows, and approvals over the last 30 days."""
    async with AsyncSessionLocal() as session:
        summary = await compute_metrics_summary(session)

        # Serialize the Pydantic model to a JSON-compatible dict, then dump.
        # model_dump() handles nested models; mode="json" ensures datetimes
        # and other non-primitive types are serialized properly.
        return json.dumps(summary.model_dump(mode="json"))
