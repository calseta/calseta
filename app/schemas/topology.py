"""Agent topology API schemas — computed graph of agent fleet."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TopologyNodeStatus:
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    OFFLINE = "offline"


class TopologyNode(BaseModel):
    uuid: uuid.UUID
    name: str
    role: str | None
    agent_type: str
    status: str
    execution_mode: str
    capabilities: list[str]
    active_assignments: int
    max_concurrent_alerts: int
    budget_monthly_cents: int | None
    # S5: computed on read from ``cost_events`` (no longer a stored column).
    spent_monthly_cents: int = 0
    last_heartbeat_at: datetime | None


class TopologyEdge(BaseModel):
    from_uuid: uuid.UUID
    to_uuid: uuid.UUID
    edge_type: str  # "routes_to", "delegates_to", "capability"
    label: str | None = None


class TopologyGraph(BaseModel):
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    computed_at: datetime
