"""Detection rule effectiveness metrics response schema."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DetectionRuleMetricsResponse(BaseModel):
    detection_rule_uuid: uuid.UUID
    detection_rule_name: str
    period_from: datetime
    period_to: datetime
    total_alerts: int
    active_alerts: int
    alerts_by_status: dict[str, int]
    alerts_by_severity: dict[str, int]
    false_positive_rate: float
    true_positive_rate: float
    close_classifications: dict[str, int]
    alerts_over_time: list[dict[str, Any]]
    fp_over_time: list[dict[str, Any]]
    mtta_seconds: float | None
    mttc_seconds: float | None
    severity_distribution: dict[str, int]
    top_indicators: list[dict[str, Any]]
    alert_sources: dict[str, int]
