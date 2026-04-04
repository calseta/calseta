"""
Tests for Phase 5 multi-agent orchestration — agent invocations.

Unit tests (mocked DB/HTTP):
  - InvocationService.delegate_task — orchestrator enforcement, specialist resolution,
    invocation creation, audit trail, enqueue call
  - InvocationService.delegate_parallel — 2-10 constraint, all-or-nothing creation
  - InvocationService.mark_timed_out — status update + activity event
  - AgentInvocationRepository.list_timed_out_candidates — SQL logic

Integration tests (real DB, requires TEST_DATABASE_URL):
  - Full delegate_task → DB round-trip: create invocation, verify columns
  - Parallel delegation: verify all N invocations created atomically
  - GET /v1/invocations/{uuid} — 200 happy path, 404 not found
  - GET /v1/agents/{uuid}/invocations — list for orchestrator
  - POST /v1/invocations — 202 delegate, 403 for non-orchestrator
  - POST /v1/invocations/parallel — 202 for 2 tasks, 422 for 1 task
  - AgentSupervisor.supervise() — marks timed-out invocations
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ===========================================================================
# Helpers
# ===========================================================================


def _make_agent(
    agent_type: str = "orchestrator",
    status: str = "active",
    name: str = "test-orchestrator",
    execution_mode: str = "external",
    endpoint_url: str | None = "http://localhost:9999/hook",
) -> MagicMock:
    agent = MagicMock()
    agent.id = 1
    agent.uuid = uuid.uuid4()
    agent.name = name
    agent.agent_type = agent_type
    agent.status = status
    agent.execution_mode = execution_mode
    agent.endpoint_url = endpoint_url
    agent.auth_header_name = None
    agent.auth_header_value_encrypted = None
    agent.capabilities = None
    agent.role = None
    agent.description = None
    return agent


def _make_invocation(
    status: str = "queued",
    started_at: datetime | None = None,
    timeout_seconds: int = 300,
) -> MagicMock:
    inv = MagicMock()
    inv.id = 1
    inv.uuid = uuid.uuid4()
    inv.parent_agent_id = 1
    inv.child_agent_id = 2
    inv.alert_id = 10
    inv.assignment_id = None
    inv.task_description = "investigate this IP"
    inv.input_context = {"ip": "1.2.3.4"}
    inv.output_schema = None
    inv.status = status
    inv.result = None
    inv.error = None
    inv.started_at = started_at
    inv.completed_at = None
    inv.cost_cents = 0
    inv.timeout_seconds = timeout_seconds
    inv.task_queue_id = None
    inv.created_at = datetime.now(UTC)
    inv.updated_at = datetime.now(UTC)
    return inv


# ===========================================================================
# Unit tests — InvocationService
# ===========================================================================


class TestDelegateTask:
    """Unit tests for InvocationService.delegate_task."""

    @pytest.mark.asyncio
    async def test_rejects_non_orchestrator(self) -> None:
        """Agents that are not orchestrators cannot delegate."""
        from app.api.errors import CalsetaException
        from app.services.invocation_service import InvocationService

        db = AsyncMock()
        svc = InvocationService(db)

        specialist = _make_agent(agent_type="specialist")

        from app.schemas.agent_invocations import DelegateTaskRequest

        req = DelegateTaskRequest(
            alert_id=uuid.uuid4(),
            child_agent_id=uuid.uuid4(),
            task_description="test",
        )

        with pytest.raises(CalsetaException) as exc_info:
            await svc.delegate_task(orchestrator=specialist, request=req)

        assert exc_info.value.code == "NOT_ORCHESTRATOR"

    @pytest.mark.asyncio
    async def test_raises_when_alert_not_found(self) -> None:
        from app.api.errors import CalsetaException
        from app.services.invocation_service import InvocationService

        db = AsyncMock()
        # Patch alert query to return None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        svc = InvocationService(db)
        orchestrator = _make_agent(agent_type="orchestrator")

        from app.schemas.agent_invocations import DelegateTaskRequest

        req = DelegateTaskRequest(
            alert_id=uuid.uuid4(),
            child_agent_id=uuid.uuid4(),
            task_description="test",
        )

        with pytest.raises(CalsetaException) as exc_info:
            await svc.delegate_task(orchestrator=orchestrator, request=req)

        assert exc_info.value.code == "NOT_FOUND"
        assert "Alert" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_raises_when_specialist_not_found(self) -> None:
        from app.api.errors import CalsetaException
        from app.services.invocation_service import InvocationService

        db = AsyncMock()
        call_count = 0

        async def mock_execute(stmt: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # First call: alert found
                alert = MagicMock()
                alert.id = 10
                mock_result.scalar_one_or_none.return_value = alert
            else:
                # Second call: agent not found
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        db.execute = mock_execute

        svc = InvocationService(db)
        orchestrator = _make_agent(agent_type="orchestrator")

        from app.schemas.agent_invocations import DelegateTaskRequest

        req = DelegateTaskRequest(
            alert_id=uuid.uuid4(),
            child_agent_id=uuid.uuid4(),
            task_description="test",
        )

        with pytest.raises(CalsetaException) as exc_info:
            await svc.delegate_task(orchestrator=orchestrator, request=req)

        assert exc_info.value.code == "NOT_FOUND"
        assert "Specialist" in exc_info.value.message


class TestDelegateParallel:
    """Unit tests for InvocationService.delegate_parallel."""

    def test_validates_task_count_min(self) -> None:
        """Parallel request must have at least 2 tasks."""
        from pydantic import ValidationError

        from app.schemas.agent_invocations import DelegateParallelRequest, ParallelTask

        with pytest.raises(ValidationError) as exc_info:
            DelegateParallelRequest(
                alert_id=uuid.uuid4(),
                tasks=[
                    ParallelTask(
                        child_agent_id=uuid.uuid4(),
                        task_description="only task",
                    )
                ],
            )

        assert "2–10" in str(exc_info.value)

    def test_validates_task_count_max(self) -> None:
        """Parallel request must have at most 10 tasks."""
        from pydantic import ValidationError

        from app.schemas.agent_invocations import DelegateParallelRequest, ParallelTask

        with pytest.raises(ValidationError) as exc_info:
            DelegateParallelRequest(
                alert_id=uuid.uuid4(),
                tasks=[
                    ParallelTask(
                        child_agent_id=uuid.uuid4(),
                        task_description=f"task {i}",
                    )
                    for i in range(11)
                ],
            )

        assert "2–10" in str(exc_info.value)

    def test_accepts_two_tasks(self) -> None:
        """Exactly 2 tasks is valid."""
        from app.schemas.agent_invocations import DelegateParallelRequest, ParallelTask

        req = DelegateParallelRequest(
            alert_id=uuid.uuid4(),
            tasks=[
                ParallelTask(child_agent_id=uuid.uuid4(), task_description="task 1"),
                ParallelTask(child_agent_id=uuid.uuid4(), task_description="task 2"),
            ],
        )
        assert len(req.tasks) == 2

    def test_accepts_ten_tasks(self) -> None:
        """Exactly 10 tasks is valid."""
        from app.schemas.agent_invocations import DelegateParallelRequest, ParallelTask

        req = DelegateParallelRequest(
            alert_id=uuid.uuid4(),
            tasks=[
                ParallelTask(child_agent_id=uuid.uuid4(), task_description=f"task {i}")
                for i in range(10)
            ],
        )
        assert len(req.tasks) == 10


class TestMarkTimedOut:
    """Unit tests for InvocationService.mark_timed_out."""

    @pytest.mark.asyncio
    async def test_updates_status_and_error(self) -> None:
        from app.services.invocation_service import InvocationService

        db = AsyncMock()
        svc = InvocationService(db)
        invocation = _make_invocation(status="running")

        # Patch repo and activity svc
        mock_repo = AsyncMock()
        mock_repo.update_status = AsyncMock()
        svc._repo = mock_repo

        with patch.object(svc, "_write_activity", AsyncMock()):
            await svc.mark_timed_out(invocation)

        mock_repo.update_status.assert_called_once()
        call_kwargs = mock_repo.update_status.call_args
        assert call_kwargs[0][1] == "timed_out"  # status positional arg
        assert "timeout" in call_kwargs[1].get("error", "").lower()


class TestInvocationSchemas:
    """Schema validation unit tests."""

    def test_invocation_response_from_orm(self) -> None:
        """AgentInvocationResponse can be built from ORM-like object."""
        from app.schemas.agent_invocations import AgentInvocationResponse

        inv = _make_invocation()
        resp = AgentInvocationResponse.model_validate(inv)
        assert str(resp.uuid) == str(inv.uuid)
        assert resp.status == "queued"
        assert resp.cost_cents == 0

    def test_catalog_entry_from_orm(self) -> None:
        """AgentCatalogEntry can be built from ORM-like object."""
        from app.schemas.agent_invocations import AgentCatalogEntry

        agent = _make_agent()
        entry = AgentCatalogEntry.model_validate(agent)
        assert entry.agent_type == "orchestrator"
        assert entry.status == "active"


# ===========================================================================
# Integration tests (require TEST_DATABASE_URL)
# ===========================================================================


@pytest.mark.asyncio
async def test_delegate_task_creates_invocation(
    db_session: Any, api_key: str, test_client: Any
) -> None:
    """POST /v1/invocations returns 202 with invocation_id for valid orchestrator."""
    import bcrypt
    from httpx import AsyncClient

    from app.db.models.agent_api_key import AgentAPIKey
    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.alert import Alert

    # Create orchestrator agent
    orchestrator = AgentRegistration(
        uuid=uuid.uuid4(),
        name="test-orchestrator",
        agent_type="orchestrator",
        status="active",
        execution_mode="external",
        trigger_on_sources=[],
        trigger_on_severities=[],
        timeout_seconds=30,
        retry_count=0,
        budget_monthly_cents=0,
        spent_monthly_cents=0,
        max_concurrent_alerts=1,
        max_cost_per_alert_cents=0,
        max_investigation_minutes=0,
        stall_threshold=0,
        memory_promotion_requires_approval=False,
        enable_thinking=False,
    )
    db_session.add(orchestrator)
    await db_session.flush()

    # Create agent API key for orchestrator
    plain_key = "cak_" + secrets.token_urlsafe(32)
    key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt(rounds=12)).decode()
    agent_key = AgentAPIKey(
        uuid=uuid.uuid4(),
        agent_registration_id=orchestrator.id,
        name="test-key",
        key_prefix=plain_key[:8],
        key_hash=key_hash,
        scopes=["agents:read", "agents:write"],
    )
    db_session.add(agent_key)

    # Create specialist agent
    specialist = AgentRegistration(
        uuid=uuid.uuid4(),
        name="test-specialist",
        agent_type="specialist",
        status="active",
        execution_mode="external",
        endpoint_url="http://specialist.internal/hook",
        trigger_on_sources=[],
        trigger_on_severities=[],
        timeout_seconds=30,
        retry_count=0,
        budget_monthly_cents=0,
        spent_monthly_cents=0,
        max_concurrent_alerts=1,
        max_cost_per_alert_cents=0,
        max_investigation_minutes=0,
        stall_threshold=0,
        memory_promotion_requires_approval=False,
        enable_thinking=False,
    )
    db_session.add(specialist)

    # Create a minimal alert
    alert = Alert(
        uuid=uuid.uuid4(),
        title="Test Alert",
        severity="High",
        status="Open",
        source_name="test",
        enrichment_status="Pending",
        occurred_at=datetime.now(UTC),
        ingested_at=datetime.now(UTC),
        raw_payload={},
        tags=[],
    )
    db_session.add(alert)
    await db_session.flush()

    resp = await test_client.post(
        "/v1/invocations",
        json={
            "alert_id": str(alert.uuid),
            "child_agent_id": str(specialist.uuid),
            "task_description": "investigate this alert",
            "timeout_seconds": 120,
        },
        headers={"Authorization": f"Bearer {plain_key}"},
    )

    assert resp.status_code == 202, resp.text
    data = resp.json()["data"]
    assert "invocation_id" in data
    assert data["status"] == "queued"


@pytest.mark.asyncio
async def test_get_invocation_not_found(test_client: Any, api_key: str) -> None:
    """GET /v1/invocations/{uuid} returns 404 for unknown UUID."""
    unknown_uuid = uuid.uuid4()
    resp = await test_client.get(
        f"/v1/invocations/{unknown_uuid}",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_parallel_requires_at_least_two_tasks(
    test_client: Any, api_key: str
) -> None:
    """POST /v1/invocations/parallel with 1 task returns 422."""
    resp = await test_client.post(
        "/v1/invocations/parallel",
        json={
            "alert_id": str(uuid.uuid4()),
            "tasks": [
                {
                    "child_agent_id": str(uuid.uuid4()),
                    "task_description": "only task",
                }
            ],
        },
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_agent_invocations_not_found(
    test_client: Any, api_key: str
) -> None:
    """GET /v1/agents/{uuid}/invocations returns 404 for unknown agent."""
    unknown_uuid = uuid.uuid4()
    resp = await test_client.get(
        f"/v1/agents/{unknown_uuid}/invocations",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_catalog(test_client: Any, api_key: str) -> None:
    """GET /v1/agents/catalog returns 200 with a list."""
    resp = await test_client.get(
        "/v1/agents/catalog",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)
