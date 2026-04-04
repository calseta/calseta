"""Integration tests for routine scheduler — /v1/routines."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from httpx import AsyncClient

from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_routine(
    test_client: AsyncClient,
    api_key: str,
    agent_uuid: str,
    name: str = "Test Routine",
) -> dict[str, Any]:
    resp = await test_client.post(
        "/v1/routines",
        json={
            "name": name,
            "description": "Integration test routine",
            "agent_registration_uuid": agent_uuid,
            "concurrency_policy": "skip_if_active",
            "catch_up_policy": "skip_missed",
            "task_template": {"action": "scan", "scope": "all"},
            "max_consecutive_failures": 3,
            "triggers": [
                {
                    "kind": "cron",
                    "cron_expression": "0 * * * *",
                    "timezone": "UTC",
                    "is_active": True,
                }
            ],
        },
        headers=auth_header(api_key),
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


class TestCreateRoutine:
    async def test_create_routine(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        agent_uuid = sample_agent["uuid"]
        resp = await test_client.post(
            "/v1/routines",
            json={
                "name": "Hourly Alert Sweep",
                "description": "Sweeps for new alerts every hour",
                "agent_registration_uuid": agent_uuid,
                "concurrency_policy": "skip_if_active",
                "catch_up_policy": "skip_missed",
                "task_template": {"action": "sweep"},
                "max_consecutive_failures": 5,
                "triggers": [
                    {
                        "kind": "cron",
                        "cron_expression": "0 * * * *",
                        "timezone": "UTC",
                        "is_active": True,
                    }
                ],
            },
            headers=auth_header(api_key),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Hourly Alert Sweep"
        assert "uuid" in data
        assert data["status"] == "active"
        assert data["concurrency_policy"] == "skip_if_active"
        assert data["max_consecutive_failures"] == 5
        assert isinstance(data["triggers"], list)
        assert len(data["triggers"]) == 1
        assert data["triggers"][0]["kind"] == "cron"
        assert data["triggers"][0]["cron_expression"] == "0 * * * *"


class TestListRoutines:
    async def test_list_routines_empty(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        resp = await test_client.get("/v1/routines", headers=auth_header(api_key))
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert "total" in body["meta"]


class TestGetRoutine:
    async def test_get_routine_not_found(
        self, test_client: AsyncClient, api_key: str
    ) -> None:
        random_uuid = str(uuid4())
        resp = await test_client.get(
            f"/v1/routines/{random_uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 404

    async def test_get_routine(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        routine = await _create_routine(test_client, api_key, sample_agent["uuid"])
        routine_uuid = routine["uuid"]

        resp = await test_client.get(
            f"/v1/routines/{routine_uuid}",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["uuid"] == routine_uuid
        assert data["name"] == "Test Routine"
        assert isinstance(data["triggers"], list)
        assert "created_at" in data
        assert "updated_at" in data


class TestPatchRoutine:
    async def test_patch_routine(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        routine = await _create_routine(
            test_client, api_key, sample_agent["uuid"], name="Original Name"
        )
        routine_uuid = routine["uuid"]

        patch_resp = await test_client.patch(
            f"/v1/routines/{routine_uuid}",
            json={"name": "Updated Name", "description": "New description"},
            headers=auth_header(api_key),
        )
        assert patch_resp.status_code == 200
        data = patch_resp.json()["data"]
        assert data["name"] == "Updated Name"
        assert data["description"] == "New description"


class TestRoutineLifecycle:
    async def test_pause_resume_routine(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        routine = await _create_routine(test_client, api_key, sample_agent["uuid"])
        routine_uuid = routine["uuid"]
        assert routine["status"] == "active"

        # Pause
        pause_resp = await test_client.post(
            f"/v1/routines/{routine_uuid}/pause",
            headers=auth_header(api_key),
        )
        assert pause_resp.status_code == 200
        assert pause_resp.json()["data"]["status"] == "paused"

        # Resume
        resume_resp = await test_client.post(
            f"/v1/routines/{routine_uuid}/resume",
            headers=auth_header(api_key),
        )
        assert resume_resp.status_code == 200
        assert resume_resp.json()["data"]["status"] == "active"


class TestRoutineTriggers:
    async def test_add_trigger(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        routine = await _create_routine(test_client, api_key, sample_agent["uuid"])
        routine_uuid = routine["uuid"]

        trigger_resp = await test_client.post(
            f"/v1/routines/{routine_uuid}/triggers",
            json={
                "kind": "cron",
                "cron_expression": "30 6 * * 1",
                "timezone": "America/Chicago",
                "is_active": True,
            },
            headers=auth_header(api_key),
        )
        assert trigger_resp.status_code == 201
        data = trigger_resp.json()["data"]
        assert data["kind"] == "cron"
        assert data["cron_expression"] == "30 6 * * 1"
        assert data["timezone"] == "America/Chicago"
        assert "uuid" in data


class TestDeleteRoutine:
    async def test_delete_routine(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        routine = await _create_routine(
            test_client, api_key, sample_agent["uuid"], name="Delete Me"
        )
        routine_uuid = routine["uuid"]

        delete_resp = await test_client.delete(
            f"/v1/routines/{routine_uuid}",
            headers=auth_header(api_key),
        )
        assert delete_resp.status_code == 204

        # Verify it's gone
        get_resp = await test_client.get(
            f"/v1/routines/{routine_uuid}",
            headers=auth_header(api_key),
        )
        assert get_resp.status_code == 404


class TestRoutineRuns:
    async def test_list_runs_empty(
        self,
        test_client: AsyncClient,
        api_key: str,
        sample_agent: dict[str, Any],
    ) -> None:
        routine = await _create_routine(test_client, api_key, sample_agent["uuid"])
        routine_uuid = routine["uuid"]

        resp = await test_client.get(
            f"/v1/routines/{routine_uuid}/runs",
            headers=auth_header(api_key),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert body["meta"]["total"] == 0
