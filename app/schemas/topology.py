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
    spent_monthly_cents: int
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
