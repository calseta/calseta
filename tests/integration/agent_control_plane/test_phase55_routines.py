"""Integration tests — Routine Scheduler (Phase 5.5).

Verifies:
- Routine CRUD (create, read, update, delete)
- Cron expression is stored and returned correctly
- Webhook trigger creation and HMAC-verified invocation
- Manual trigger endpoint
- Run history after invocation
- Auto-pause after N consecutive failures (via service-layer logic)
- Pause/resume lifecycle transitions
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.agent_control_plane.conftest import _create_agent_with_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_routine(
    client: AsyncClient,
    headers: dict[str, str],
    agent_uuid: str,
    *,
    name: str = "Test Routine",
    triggers: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a routine via the API. Returns the data dict."""
    body: dict[str, Any] = {
        "name": name,
        "agent_registration_uuid": agent_uuid,
        "task_template": {"action": "investigate", "priority": "medium"},
        "concurrency_policy": "skip_if_active",
        "catch_up_policy": "skip_missed",
        "max_consecutive_failures": 3,
        "triggers": triggers or [],
    }
    resp = await client.post("/v1/routines", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


def _compute_hmac_signature(secret: str, body: bytes, timestamp: str) -> str:
    """Produce the sha256=<hex> signature expected by the webhook endpoint."""
    msg = f"{timestamp}.".encode() + body
    digest = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


# ---------------------------------------------------------------------------
# Routine CRUD
# ---------------------------------------------------------------------------


class TestRoutineCRUD:
    """Create, read, update, delete routines."""

    async def test_create_routine_returns_201(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Creating a routine returns 201 with UUID and defaults."""
        agent, _ = await _create_agent_with_key(db_session, name="routine-create-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client, admin_auth_headers, str(agent.uuid), name="My First Routine"
        )
        assert "uuid" in routine
        assert routine["name"] == "My First Routine"
        assert routine["status"] == "active"
        assert routine["concurrency_policy"] == "skip_if_active"
        assert routine["catch_up_policy"] == "skip_missed"
        assert routine["max_consecutive_failures"] == 3
        assert routine["consecutive_failures"] == 0

    async def test_get_routine_returns_200(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Created routine is retrievable by UUID."""
        agent, _ = await _create_agent_with_key(db_session, name="routine-read-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client, admin_auth_headers, str(agent.uuid), name="Readable Routine"
        )
        resp = await test_client.get(
            f"/v1/routines/{routine['uuid']}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["uuid"] == routine["uuid"]

    async def test_get_nonexistent_routine_returns_404(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET on unknown UUID → 404."""
        resp = await test_client.get(
            f"/v1/routines/{uuid4()}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404, resp.text

    async def test_patch_routine_updates_name(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """PATCH updates name and returns updated routine."""
        agent, _ = await _create_agent_with_key(db_session, name="routine-patch-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client, admin_auth_headers, str(agent.uuid), name="Original Name"
        )
        resp = await test_client.patch(
            f"/v1/routines/{routine['uuid']}",
            json={"name": "Updated Name"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["name"] == "Updated Name"

    async def test_delete_routine_returns_204(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """DELETE returns 204 and the routine is gone."""
        agent, _ = await _create_agent_with_key(db_session, name="routine-delete-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client, admin_auth_headers, str(agent.uuid), name="Delete Me"
        )
        del_resp = await test_client.delete(
            f"/v1/routines/{routine['uuid']}",
            headers=admin_auth_headers,
        )
        assert del_resp.status_code == 204, del_resp.text

        get_resp = await test_client.get(
            f"/v1/routines/{routine['uuid']}",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 404, get_resp.text

    async def test_list_routines_returns_created_routines(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """List endpoint returns all routines for an agent."""
        agent, _ = await _create_agent_with_key(db_session, name="routine-list-agent")
        await db_session.flush()

        await _create_routine(test_client, admin_auth_headers, str(agent.uuid), name="Routine A")
        await _create_routine(test_client, admin_auth_headers, str(agent.uuid), name="Routine B")

        resp = await test_client.get(
            f"/v1/routines?agent_uuid={agent.uuid}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meta"]["total"] >= 2
        names = [r["name"] for r in body["data"]]
        assert "Routine A" in names
        assert "Routine B" in names


# ---------------------------------------------------------------------------
# Cron trigger
# ---------------------------------------------------------------------------


class TestCronTrigger:
    """Cron expressions are stored and returned in trigger responses."""

    async def test_create_routine_with_cron_trigger(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Routine created with a cron trigger has the expression in the response."""
        agent, _ = await _create_agent_with_key(db_session, name="cron-trigger-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client,
            admin_auth_headers,
            str(agent.uuid),
            name="Daily Cron Routine",
            triggers=[{"kind": "cron", "cron_expression": "0 6 * * *", "timezone": "UTC"}],
        )
        assert len(routine["triggers"]) == 1
        trigger = routine["triggers"][0]
        assert trigger["kind"] == "cron"
        assert trigger["cron_expression"] == "0 6 * * *"
        assert trigger["timezone"] == "UTC"

    async def test_add_cron_trigger_via_post(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Trigger added after routine creation appears in GET response."""
        agent, _ = await _create_agent_with_key(db_session, name="add-cron-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client, admin_auth_headers, str(agent.uuid), name="Triggerless Routine"
        )
        resp = await test_client.post(
            f"/v1/routines/{routine['uuid']}/triggers",
            json={"kind": "cron", "cron_expression": "*/15 * * * *"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        trigger = resp.json()["data"]
        assert trigger["cron_expression"] == "*/15 * * * *"


# ---------------------------------------------------------------------------
# Webhook trigger
# ---------------------------------------------------------------------------


class TestWebhookTrigger:
    """POST /v1/routines/{uuid}/triggers/{trigger_uuid}/webhook — HMAC verification."""

    async def test_webhook_trigger_no_secret_fires_without_signature(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Webhook trigger with no secret configured fires without a signature header."""
        agent, _ = await _create_agent_with_key(db_session, name="webhook-no-secret-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client,
            admin_auth_headers,
            str(agent.uuid),
            name="No-Secret Webhook Routine",
            triggers=[{"kind": "webhook"}],
        )
        trigger = routine["triggers"][0]

        resp = await test_client.post(
            f"/v1/routines/{routine['uuid']}/triggers/{trigger['uuid']}/webhook",
            content=b'{"event": "test"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 202, resp.text
        run = resp.json()["data"]
        assert run["status"] in ("enqueued", "received")
        assert run["source"] == "webhook"

    async def test_webhook_trigger_with_valid_hmac_succeeds(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Webhook with correct HMAC signature → 202."""
        from sqlalchemy import select

        from app.db.models.routine_trigger import RoutineTrigger

        agent, _ = await _create_agent_with_key(db_session, name="webhook-hmac-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client,
            admin_auth_headers,
            str(agent.uuid),
            name="HMAC Webhook Routine",
            triggers=[{"kind": "webhook"}],
        )
        trigger_data = routine["triggers"][0]

        # Inject a webhook secret directly into the trigger row
        secret = "test-webhook-secret-123"
        result = await db_session.execute(
            select(RoutineTrigger).where(
                RoutineTrigger.uuid == trigger_data["uuid"]
            )
        )
        trigger_row = result.scalar_one()
        trigger_row.webhook_secret_hash = secret
        await db_session.flush()

        body = b'{"event": "deploy_complete"}'
        timestamp = str(int(time.time()))
        signature = _compute_hmac_signature(secret, body, timestamp)

        resp = await test_client.post(
            f"/v1/routines/{routine['uuid']}/triggers/{trigger_data['uuid']}/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": signature,
                "X-Timestamp": timestamp,
            },
        )
        assert resp.status_code == 202, resp.text

    async def test_webhook_trigger_with_invalid_hmac_returns_401(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Webhook with wrong HMAC signature → 401."""
        from sqlalchemy import select

        from app.db.models.routine_trigger import RoutineTrigger

        agent, _ = await _create_agent_with_key(db_session, name="webhook-bad-hmac-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client,
            admin_auth_headers,
            str(agent.uuid),
            name="Bad HMAC Webhook Routine",
            triggers=[{"kind": "webhook"}],
        )
        trigger_data = routine["triggers"][0]

        # Inject a webhook secret
        result = await db_session.execute(
            select(RoutineTrigger).where(
                RoutineTrigger.uuid == trigger_data["uuid"]
            )
        )
        trigger_row = result.scalar_one()
        trigger_row.webhook_secret_hash = "correct-secret"
        await db_session.flush()

        body = b'{"event": "something"}'
        timestamp = str(int(time.time()))
        bad_signature = _compute_hmac_signature("wrong-secret", body, timestamp)

        resp = await test_client.post(
            f"/v1/routines/{routine['uuid']}/triggers/{trigger_data['uuid']}/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature": bad_signature,
                "X-Timestamp": timestamp,
            },
        )
        assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# Manual trigger
# ---------------------------------------------------------------------------


class TestManualTrigger:
    """POST /v1/routines/{uuid}/invoke — manual invocation."""

    async def test_manual_invoke_returns_202(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Manual invocation of an active routine → 202 with run record."""
        agent, _ = await _create_agent_with_key(db_session, name="manual-invoke-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client, admin_auth_headers, str(agent.uuid), name="Manually Invoked Routine"
        )
        resp = await test_client.post(
            f"/v1/routines/{routine['uuid']}/invoke",
            json={"payload": {"reason": "manual test"}},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 202, resp.text
        run = resp.json()["data"]
        assert run["status"] in ("enqueued", "received")
        assert run["source"] == "manual"


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------


class TestRoutineRunHistory:
    """GET /v1/routines/{uuid}/runs — run history."""

    async def test_runs_appear_in_history_after_invoke(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Manual invoke creates a run that appears in the run history list."""
        agent, _ = await _create_agent_with_key(db_session, name="run-history-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client, admin_auth_headers, str(agent.uuid), name="Run History Routine"
        )
        # Invoke twice
        await test_client.post(
            f"/v1/routines/{routine['uuid']}/invoke",
            json={},
            headers=admin_auth_headers,
        )
        await test_client.post(
            f"/v1/routines/{routine['uuid']}/invoke",
            json={},
            headers=admin_auth_headers,
        )

        resp = await test_client.get(
            f"/v1/routines/{routine['uuid']}/runs",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meta"]["total"] >= 2


# ---------------------------------------------------------------------------
# Pause / resume
# ---------------------------------------------------------------------------


class TestRoutinePauseResume:
    """POST /v1/routines/{uuid}/pause and POST /v1/routines/{uuid}/resume."""

    async def test_pause_active_routine(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Active routine can be paused → status becomes paused."""
        agent, _ = await _create_agent_with_key(db_session, name="pause-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client, admin_auth_headers, str(agent.uuid), name="Pausable Routine"
        )
        resp = await test_client.post(
            f"/v1/routines/{routine['uuid']}/pause",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "paused"

    async def test_resume_paused_routine(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Paused routine can be resumed → status becomes active."""
        agent, _ = await _create_agent_with_key(db_session, name="resume-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client, admin_auth_headers, str(agent.uuid), name="Resumable Routine"
        )
        # Pause first
        await test_client.post(
            f"/v1/routines/{routine['uuid']}/pause",
            headers=admin_auth_headers,
        )
        # Resume
        resp = await test_client.post(
            f"/v1/routines/{routine['uuid']}/resume",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["status"] == "active"

    async def test_pause_already_paused_returns_409(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Pausing an already-paused routine → 409 conflict."""
        agent, _ = await _create_agent_with_key(db_session, name="double-pause-agent")
        await db_session.flush()

        routine = await _create_routine(
            test_client, admin_auth_headers, str(agent.uuid), name="Already Paused"
        )
        await test_client.post(
            f"/v1/routines/{routine['uuid']}/pause",
            headers=admin_auth_headers,
        )
        resp = await test_client.post(
            f"/v1/routines/{routine['uuid']}/pause",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# Phase 5.5 exit-criteria gap: Routine auto-pause after N consecutive failures
# ---------------------------------------------------------------------------


class TestRoutineAutoPause:
    """Phase 5.5 exit criterion: a routine that fails N consecutive times
    transitions to paused status automatically.

    The consecutive_failures and max_consecutive_failures fields exist on the
    AgentRoutine model, but the auto-pause trigger is not yet wired in the
    service layer (noted as Phase 6+ in the CONTEXT.md).  Marked xfail.
    """

    @pytest.mark.xfail(
        strict=False,
        reason=(
            "Routine auto-pause on consecutive failures is not yet implemented.  "
            "agent_routines.consecutive_failures column exists but the evaluator "
            "task (evaluate_routine_triggers_task) does not increment it or check "
            "it against max_consecutive_failures to trigger auto-pause.  "
            "Tracked as Phase 6+ work in app/services/routines_CONTEXT.md."
        ),
    )
    async def test_routine_auto_pauses_after_consecutive_failures(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Routine with max_consecutive_failures=2 auto-pauses after 2 failed runs."""
        from app.db.models.agent_routine import AgentRoutine

        agent, _ = await _create_agent_with_key(db_session, name="auto-pause-agent")
        await db_session.flush()

        # Create a routine with a low failure threshold
        routine_data = await _create_routine(
            test_client,
            admin_auth_headers,
            str(agent.uuid),
            name="Auto-Pause Test Routine",
        )
        routine_uuid = routine_data["uuid"]

        # Manually set consecutive_failures to threshold - 1 (so next failure triggers pause)
        result = await db_session.execute(
            __import__("sqlalchemy").select(AgentRoutine).where(
                AgentRoutine.uuid == routine_uuid
            )
        )
        routine = result.scalar_one()
        routine.consecutive_failures = 2
        routine.max_consecutive_failures = 2
        await db_session.flush()
        await db_session.commit()

        # Simulate a failed run by incrementing consecutive_failures beyond threshold.
        # The evaluator task is supposed to detect this and auto-pause.
        # Since the evaluator is not yet implemented, trigger via a manual run endpoint
        # and observe if the routine transitions to paused.
        resp = await test_client.post(
            f"/v1/routines/{routine_uuid}/invoke",
            json={"reason": "Simulated failure trigger"},
            headers=admin_auth_headers,
        )
        # Whether this triggers auto-pause depends on the evaluator being hooked in
        assert resp.status_code in (200, 202), resp.text

        status_resp = await test_client.get(
            f"/v1/routines/{routine_uuid}",
            headers=admin_auth_headers,
        )
        assert status_resp.status_code == 200, status_resp.text
        assert status_resp.json()["data"]["status"] == "paused", (
            "Expected routine to auto-pause after max_consecutive_failures exceeded"
        )
