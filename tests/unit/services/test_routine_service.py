"""Unit tests for app/services/routine_service.py — no DB, no network."""

from __future__ import annotations

import hashlib
import hmac
import time
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.routines import (
    ConcurrencyPolicy,
    RoutineCreate,
    RoutineInvokeRequest,
    RoutineRunStatus,
    RoutineStatus,
    TriggerCreate,
    TriggerKind,
)
from app.services.routine_service import _verify_webhook_signature


# ---------------------------------------------------------------------------
# Constant tests
# ---------------------------------------------------------------------------


def test_routine_status_constants() -> None:
    """RoutineStatus.ALL has 3 values."""
    assert len(RoutineStatus.ALL) == 3
    expected = {RoutineStatus.ACTIVE, RoutineStatus.PAUSED, RoutineStatus.COMPLETED}
    assert set(RoutineStatus.ALL) == expected


def test_trigger_kind_constants() -> None:
    """TriggerKind.ALL has 3 values."""
    assert len(TriggerKind.ALL) == 3
    expected = {TriggerKind.CRON, TriggerKind.WEBHOOK, TriggerKind.MANUAL}
    assert set(TriggerKind.ALL) == expected


def test_concurrency_policy_constants() -> None:
    """ConcurrencyPolicy.ALL has 3 values."""
    assert len(ConcurrencyPolicy.ALL) == 3
    expected = {
        ConcurrencyPolicy.SKIP_IF_ACTIVE,
        ConcurrencyPolicy.COALESCE_IF_ACTIVE,
        ConcurrencyPolicy.ALWAYS_RUN,
    }
    assert set(ConcurrencyPolicy.ALL) == expected


def test_routine_run_status_constants() -> None:
    """RoutineRunStatus.ALL has 6 values."""
    assert len(RoutineRunStatus.ALL) == 6
    expected = {
        RoutineRunStatus.RECEIVED,
        RoutineRunStatus.ENQUEUED,
        RoutineRunStatus.RUNNING,
        RoutineRunStatus.COMPLETED,
        RoutineRunStatus.SKIPPED,
        RoutineRunStatus.FAILED,
    }
    assert set(RoutineRunStatus.ALL) == expected


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


def test_routine_create_schema_valid() -> None:
    """RoutineCreate with required fields validates and uses defaults."""
    routine = RoutineCreate(
        name="Daily alert triage",
        agent_registration_uuid=uuid4(),
        task_template={"action": "triage_alerts"},
    )
    assert routine.name == "Daily alert triage"
    assert routine.concurrency_policy == "skip_if_active"
    assert routine.catch_up_policy == "skip_missed"
    assert routine.max_consecutive_failures == 3
    assert routine.triggers == []


def test_routine_create_schema_name_too_short() -> None:
    """RoutineCreate with empty name raises ValidationError."""
    with pytest.raises(ValidationError):
        RoutineCreate(
            name="",
            agent_registration_uuid=uuid4(),
            task_template={},
        )


def test_trigger_create_cron_valid() -> None:
    """TriggerCreate(kind='cron', cron_expression='0 8 * * *') validates."""
    trigger = TriggerCreate(kind="cron", cron_expression="0 8 * * *")
    assert trigger.kind == "cron"
    assert trigger.cron_expression == "0 8 * * *"
    assert trigger.timezone == "UTC"
    assert trigger.is_active is True


def test_trigger_create_webhook_kind() -> None:
    """TriggerCreate(kind='webhook') validates."""
    trigger = TriggerCreate(kind="webhook")
    assert trigger.kind == "webhook"
    assert trigger.cron_expression is None


def test_trigger_create_manual_kind() -> None:
    """TriggerCreate(kind='manual') validates."""
    trigger = TriggerCreate(kind="manual")
    assert trigger.kind == "manual"


def test_routine_invoke_schema() -> None:
    """RoutineInvokeRequest with payload validates."""
    req = RoutineInvokeRequest(payload={"alert_uuid": str(uuid4())})
    assert req.payload is not None
    assert "alert_uuid" in req.payload


def test_routine_invoke_schema_no_payload() -> None:
    """RoutineInvokeRequest with no payload validates (payload is optional)."""
    req = RoutineInvokeRequest()
    assert req.payload is None


# ---------------------------------------------------------------------------
# _verify_webhook_signature tests
# ---------------------------------------------------------------------------


def test_verify_webhook_signature_valid() -> None:
    """_verify_webhook_signature returns True with a correct HMAC-SHA256 signature."""
    secret = "test-webhook-secret"
    body = b'{"event": "alert.created", "uuid": "abc123"}'
    timestamp = str(int(time.time()))

    msg = f"{timestamp}.".encode() + body
    expected_hex = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    signature = f"sha256={expected_hex}"

    result = _verify_webhook_signature(secret, body, signature, timestamp)
    assert result is True


def test_verify_webhook_signature_wrong_secret() -> None:
    """_verify_webhook_signature returns False with a wrong secret."""
    secret = "correct-secret"
    wrong_secret = "wrong-secret"
    body = b'{"event": "alert.created"}'
    timestamp = str(int(time.time()))

    msg = f"{timestamp}.".encode() + body
    hex_digest = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    signature = f"sha256={hex_digest}"

    result = _verify_webhook_signature(wrong_secret, body, signature, timestamp)
    assert result is False


def test_verify_webhook_signature_tampered_body() -> None:
    """_verify_webhook_signature returns False when body is tampered after signing."""
    secret = "test-secret"
    original_body = b'{"event": "alert.created"}'
    tampered_body = b'{"event": "alert.deleted"}'
    timestamp = str(int(time.time()))

    msg = f"{timestamp}.".encode() + original_body
    hex_digest = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    signature = f"sha256={hex_digest}"

    result = _verify_webhook_signature(secret, tampered_body, signature, timestamp)
    assert result is False


def test_verify_webhook_signature_invalid_timestamp() -> None:
    """_verify_webhook_signature returns False for a non-numeric timestamp."""
    secret = "test-secret"
    body = b'{"event": "alert.created"}'

    result = _verify_webhook_signature(secret, body, "sha256=anything", "not-a-number")
    assert result is False


def test_verify_webhook_signature_wrong_format() -> None:
    """_verify_webhook_signature returns False when signature has wrong format."""
    secret = "test-secret"
    body = b'{"event": "alert.created"}'
    timestamp = str(int(time.time()))

    result = _verify_webhook_signature(secret, body, "wrong-format-signature", timestamp)
    assert result is False
