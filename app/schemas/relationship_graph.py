"""Schemas for the alert-indicator relationship graph endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class GraphAlertNode(BaseModel):
    """Compact alert node for the relationship graph."""

    model_config = ConfigDict(from_attributes=True)

    uuid: str
    title: str
    severity: str
    status: str
    source_name: str
    occurred_at: datetime
    tags: list[str]


class GraphIndicatorNode(BaseModel):
    """Indicator node with sibling alerts for the relationship graph."""

    model_config = ConfigDict(from_attributes=True)

    uuid: str
    type: str
    value: str
    malice: str
    first_seen: datetime
    last_seen: datetime
    is_enriched: bool
    enrichment_summary: dict[str, str]
    total_alert_count: int
    sibling_alerts: list[GraphAlertNode]


class AlertRelationshipGraph(BaseModel):
    """Complete graph data returned by the relationship-graph endpoint."""

    alert: GraphAlertNode
    indicators: list[GraphIndicatorNode]
