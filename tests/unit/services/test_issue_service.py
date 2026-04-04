"""Unit tests for app/services/issue_service.py — no DB, no network."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.issues import (
    IssueCategory,
    IssueCommentCreate,
    IssueCreate,
    IssuePriority,
    IssueResponse,
    IssueStatus,
)

# ---------------------------------------------------------------------------
# Constant tests
# ---------------------------------------------------------------------------


def test_issue_status_constants() -> None:
    """IssueStatus.ALL contains all 7 statuses."""
    assert len(IssueStatus.ALL) == 7
    expected = {
        IssueStatus.BACKLOG,
        IssueStatus.TODO,
        IssueStatus.IN_PROGRESS,
        IssueStatus.IN_REVIEW,
        IssueStatus.DONE,
        IssueStatus.BLOCKED,
        IssueStatus.CANCELLED,
    }
    assert set(IssueStatus.ALL) == expected


def test_issue_priority_constants() -> None:
    """IssuePriority.ALL has 4 values."""
    assert len(IssuePriority.ALL) == 4
    expected = {
        IssuePriority.CRITICAL,
        IssuePriority.HIGH,
        IssuePriority.MEDIUM,
        IssuePriority.LOW,
    }
    assert set(IssuePriority.ALL) == expected


def test_issue_category_constants() -> None:
    """IssueCategory.ALL has 7 categories."""
    assert len(IssueCategory.ALL) == 7
    expected = {
        IssueCategory.REMEDIATION,
        IssueCategory.DETECTION_TUNING,
        IssueCategory.INVESTIGATION,
        IssueCategory.COMPLIANCE,
        IssueCategory.POST_INCIDENT,
        IssueCategory.MAINTENANCE,
        IssueCategory.CUSTOM,
    }
    assert set(IssueCategory.ALL) == expected


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


def test_issue_create_schema_valid() -> None:
    """IssueCreate with title only validates OK and uses defaults."""
    issue = IssueCreate(title="Investigate suspicious login")
    assert issue.title == "Investigate suspicious login"
    assert issue.status == "backlog"
    assert issue.priority == "medium"
    assert issue.category == "investigation"
    assert issue.description is None
    assert issue.assignee_agent_uuid is None
    assert issue.alert_uuid is None


def test_issue_create_schema_title_too_short() -> None:
    """Empty title raises ValidationError."""
    with pytest.raises(ValidationError):
        IssueCreate(title="")


def test_issue_response_from_attributes() -> None:
    """IssueResponse.model_validate works with all required fields as a dict."""
    now = datetime.now(UTC)
    data = {
        "uuid": uuid4(),
        "identifier": "ISS-001",
        "title": "Test issue",
        "description": "A test description",
        "status": "backlog",
        "priority": "medium",
        "category": "investigation",
        "assignee_operator": None,
        "created_by_operator": "analyst",
        "due_at": None,
        "started_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "resolution": None,
        "created_at": now,
        "updated_at": now,
    }
    response = IssueResponse.model_validate(data)
    assert response.identifier == "ISS-001"
    assert response.title == "Test issue"
    assert response.status == "backlog"
    assert response.priority == "medium"
    assert response.assignee_agent_uuid is None
    assert response.created_by_agent_uuid is None
    assert response.alert_uuid is None
    assert response.parent_uuid is None
    assert response.routine_uuid is None


def test_issue_comment_create_schema() -> None:
    """IssueCommentCreate validates body field."""
    comment = IssueCommentCreate(body="This is a comment")
    assert comment.body == "This is a comment"
    assert comment.author_operator is None


def test_issue_comment_create_empty_body_raises() -> None:
    """IssueCommentCreate with empty body raises ValidationError."""
    with pytest.raises(ValidationError):
        IssueCommentCreate(body="")


# ---------------------------------------------------------------------------
# Terminal status tests
# ---------------------------------------------------------------------------


def test_issue_status_terminal() -> None:
    """IssueStatus.TERMINAL contains done and cancelled only."""
    assert set(IssueStatus.TERMINAL) == {IssueStatus.DONE, IssueStatus.CANCELLED}
    assert len(IssueStatus.TERMINAL) == 2


def test_issue_status_terminal_not_in_active_statuses() -> None:
    """Terminal statuses are distinct from the non-terminal statuses."""
    non_terminal = [s for s in IssueStatus.ALL if s not in IssueStatus.TERMINAL]
    assert IssueStatus.DONE not in non_terminal
    assert IssueStatus.CANCELLED not in non_terminal
    assert len(non_terminal) == 5
