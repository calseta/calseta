"""
Pydantic schemas for the control plane dashboard endpoint (`GET /v1/dashboard`).

The dashboard returns three summary blocks: agent counts, queue depths, and
month-to-date cost totals. Previously the route returned an untyped ``dict``,
which let drift creep in (e.g. ``period_start`` typed as a free-form string on
the UI). These schemas pin the contract.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentCountsBlock(BaseModel):
    """Agent registration counts grouped by status."""

    by_status: dict[str, int] = Field(
        default_factory=dict,
        description="Map of agent status → count (e.g. 'active', 'paused').",
    )
    total: int = Field(0, description="Sum of counts across all statuses.")

    model_config = ConfigDict(extra="forbid")


class QueueBlock(BaseModel):
    """Snapshot of the alert queue."""

    available: int = Field(
        0,
        description="Number of enriched, unassigned alerts in Open or Triaging status.",
    )
    active_by_status: dict[str, int] = Field(
        default_factory=dict,
        description="Map of active assignment status → count (excludes released/resolved).",
    )

    model_config = ConfigDict(extra="forbid")


class CostsMTDBlock(BaseModel):
    """Month-to-date cost totals derived from the cost_events table."""

    total_cents: int = Field(0, description="Total cost month-to-date in integer cents.")
    total_usd: float = Field(0.0, description="Convenience USD value (total_cents / 100).")
    period_start: datetime = Field(
        ...,
        description="Start of the current month (UTC), inclusive lower bound for the sum.",
    )

    model_config = ConfigDict(extra="forbid")


class ControlPlaneDashboardResponse(BaseModel):
    """Top-level payload for `GET /v1/dashboard`."""

    agents: AgentCountsBlock
    queue: QueueBlock
    costs_mtd: CostsMTDBlock

    model_config = ConfigDict(extra="forbid")
