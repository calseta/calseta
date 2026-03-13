"""
Schema unit tests — Chunk 1.3 acceptance criteria: minimum 8 tests.

Tests cover schema validation happy paths and key error cases for the
core Pydantic schemas defined in app/schemas/.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.activity_events import ActivityEventType
from app.schemas.alert import (
    AlertCloseClassification,
    AlertSeverity,
    AlertStatus,
    CalsetaAlert,
    EnrichmentStatus,
)
from app.schemas.common import (
    DataResponse,
    ErrorDetail,
    ErrorResponse,
    PaginatedResponse,
    PaginationMeta,
)
from app.schemas.indicators import IndicatorType

# ---------------------------------------------------------------------------
# CalsetaAlert
# ---------------------------------------------------------------------------

def test_calseta_alert_happy_path() -> None:
    """CalsetaAlert validates a complete Sentinel-style normalized alert."""
    alert = CalsetaAlert(
        title="Suspicious sign-in from unfamiliar location",
        severity=AlertSeverity.HIGH,
        occurred_at=datetime(2026, 2, 28, 12, 0, 0, tzinfo=UTC),
        source_name="sentinel",
        src_ip="185.220.101.45",
        actor_email="jdoe@example.com",
        tags=["identity", "brute-force"],
    )
    assert alert.title == "Suspicious sign-in from unfamiliar location"
    assert alert.severity == AlertSeverity.HIGH
    assert alert.source_name == "sentinel"
    assert alert.src_ip == "185.220.101.45"
    assert alert.severity == AlertSeverity.HIGH


def test_calseta_alert_missing_required_fields() -> None:
    """CalsetaAlert raises ValidationError when required fields are absent."""
    with pytest.raises(ValidationError) as exc_info:
        CalsetaAlert(  # type: ignore[call-arg]
            title="Missing occurred_at",
            severity=AlertSeverity.LOW,
            source_name="elastic",
            # occurred_at is missing
        )
    assert "occurred_at" in str(exc_info.value)


def test_calseta_alert_severity_value() -> None:
    """severity stores the correct AlertSeverity enum value."""
    alert = CalsetaAlert(
        title="Test",
        severity=AlertSeverity.CRITICAL,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_name="splunk",
    )
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.severity.value == "Critical"


def test_calseta_alert_severity_accepts_all_values() -> None:
    """All AlertSeverity enum values are accepted by CalsetaAlert."""
    for sev in AlertSeverity:
        alert = CalsetaAlert(
            title="Test",
            severity=sev,
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            source_name="splunk",
        )
        assert alert.severity == sev


# ---------------------------------------------------------------------------
# AlertStatus enum
# ---------------------------------------------------------------------------

def test_alert_status_all_four_values() -> None:
    """AlertStatus has exactly 4 investigation lifecycle values."""
    values = {s.value for s in AlertStatus}
    assert values == {
        "Open",
        "Triaging",
        "Escalated",
        "Closed",
    }


def test_enrichment_status_all_three_values() -> None:
    """EnrichmentStatus has exactly 3 system-managed values."""
    values = {s.value for s in EnrichmentStatus}
    assert values == {"Pending", "Enriched", "Failed"}


# ---------------------------------------------------------------------------
# AlertSeverity enum
# ---------------------------------------------------------------------------

def test_alert_severity_all_six_values() -> None:
    """AlertSeverity has exactly 6 values."""
    assert len(AlertSeverity) == 6
    values = {s.value for s in AlertSeverity}
    assert values == {"Pending", "Informational", "Low", "Medium", "High", "Critical"}


# ---------------------------------------------------------------------------
# IndicatorType enum
# ---------------------------------------------------------------------------

def test_indicator_type_all_eight_values() -> None:
    """IndicatorType has exactly 8 values from PRD Section 7.1."""
    values = {t.value for t in IndicatorType}
    assert values == {
        "ip", "domain", "hash_md5", "hash_sha1", "hash_sha256",
        "url", "email", "account",
    }


# ---------------------------------------------------------------------------
# DataResponse
# ---------------------------------------------------------------------------

def test_data_response_serializes_correctly() -> None:
    """DataResponse[T] serializes as {"data": ..., "meta": {}}."""
    response: DataResponse[dict[str, str]] = DataResponse(data={"key": "value"})
    dumped = response.model_dump()
    assert "data" in dumped
    assert "meta" in dumped
    assert dumped["data"] == {"key": "value"}
    assert dumped["meta"] == {}


# ---------------------------------------------------------------------------
# PaginatedResponse
# ---------------------------------------------------------------------------

def test_paginated_response_serializes_correctly() -> None:
    """PaginatedResponse[T] serializes with the correct meta structure."""
    meta = PaginationMeta.from_total(total=103, page=2, page_size=50)
    response: PaginatedResponse[str] = PaginatedResponse(
        data=["a", "b"],
        meta=meta,
    )
    dumped = response.model_dump()
    assert dumped["data"] == ["a", "b"]
    assert dumped["meta"]["total"] == 103
    assert dumped["meta"]["page"] == 2
    assert dumped["meta"]["page_size"] == 50
    assert dumped["meta"]["total_pages"] == 3


def test_pagination_meta_total_pages_calculation() -> None:
    """PaginationMeta.from_total correctly computes total_pages."""
    assert PaginationMeta.from_total(100, 1, 50).total_pages == 2
    assert PaginationMeta.from_total(101, 1, 50).total_pages == 3
    assert PaginationMeta.from_total(0, 1, 50).total_pages == 0
    assert PaginationMeta.from_total(1, 1, 1).total_pages == 1


# ---------------------------------------------------------------------------
# ErrorResponse
# ---------------------------------------------------------------------------

def test_error_response_serializes_correctly() -> None:
    """ErrorResponse serializes as {"error": {"code": ..., "message": ..., "details": {}}}."""
    response = ErrorResponse(
        error=ErrorDetail(code="ALERT_NOT_FOUND", message="Alert not found.")
    )
    dumped = response.model_dump()
    assert "error" in dumped
    assert dumped["error"]["code"] == "ALERT_NOT_FOUND"
    assert dumped["error"]["message"] == "Alert not found."
    assert dumped["error"]["details"] == {}


# ---------------------------------------------------------------------------
# ActivityEventType enum
# ---------------------------------------------------------------------------

def test_activity_event_type_all_twelve_values() -> None:
    """ActivityEventType has exactly 17 values (12 original + 5 added)."""
    assert len(ActivityEventType) == 17
    # Spot-check key values
    assert ActivityEventType.ALERT_INGESTED.value == "alert_ingested"
    assert ActivityEventType.WORKFLOW_APPROVAL_REQUESTED.value == "workflow_approval_requested"
    assert ActivityEventType.DETECTION_RULE_UPDATED.value == "detection_rule_updated"


# ---------------------------------------------------------------------------
# AlertCloseClassification
# ---------------------------------------------------------------------------

def test_false_positive_classifications_start_with_false_positive() -> None:
    """FP rate metric: any close_classification starting with 'False Positive' counts."""
    fp_values = [
        c.value for c in AlertCloseClassification
        if c.value.startswith("False Positive")
    ]
    assert len(fp_values) == 2
    assert "False Positive - Incorrect Detection Logic" in fp_values
    assert "False Positive - Inaccurate Data" in fp_values
