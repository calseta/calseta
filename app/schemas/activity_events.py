"""Activity event types and response schema."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict


class ActivityEventType(StrEnum):
    """
    All 12 activity event types. Shape of the `references` JSONB field
    is fixed per event type — see PRD Section 8.
    """

    # Alert events
    ALERT_INGESTED = "alert_ingested"
    ALERT_ENRICHMENT_COMPLETED = "alert_enrichment_completed"
    ALERT_STATUS_UPDATED = "alert_status_updated"
    ALERT_SEVERITY_UPDATED = "alert_severity_updated"
    ALERT_CLOSED = "alert_closed"
    ALERT_FINDING_ADDED = "alert_finding_added"
    ALERT_WORKFLOW_TRIGGERED = "alert_workflow_triggered"

    # Workflow events
    WORKFLOW_EXECUTED = "workflow_executed"
    WORKFLOW_APPROVAL_REQUESTED = "workflow_approval_requested"
    WORKFLOW_APPROVAL_RESPONDED = "workflow_approval_responded"

    # Detection rule events
    DETECTION_RULE_CREATED = "detection_rule_created"
    DETECTION_RULE_UPDATED = "detection_rule_updated"


class ActivityEventResponse(BaseModel):
    """Activity event as returned by GET /v1/alerts/{uuid}/activity."""

    model_config = ConfigDict(from_attributes=True)

    uuid: uuid.UUID
    event_type: ActivityEventType
    actor_type: str  # system | api | mcp
    actor_key_prefix: str | None
    alert_id: int | None
    workflow_id: int | None
    detection_rule_id: int | None
    references: dict[str, Any] | None
    created_at: datetime  # Event timestamp (no updated_at — append-only)
