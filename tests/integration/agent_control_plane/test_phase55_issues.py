"""Integration tests — Issue/Task System (Phase 5.5).

Verifies:
- Issue CRUD (create, read, update)
- Status transitions and their side effects
- Atomic checkout invariant: concurrent checkout requests, exactly one wins
- Comment CRUD
- Validation errors for invalid enum values
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_issue import AgentIssue
from app.db.models.heartbeat_run import HeartbeatRun
from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_issue(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    title: str = "Test Issue",
    status: str = "backlog",
    priority: str = "medium",
    category: str = "investigation",
) -> dict[str, Any]:
    """Create an issue via the API and return the response data dict."""
    resp = await client.post(
        "/v1/issues",
        json={
            "title": title,
            "status": status,
            "priority": priority,
            "category": category,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    data: dict[str, Any] = resp.json()["data"]
    return data


async def _create_heartbeat_run(db: AsyncSession, agent_id: int) -> HeartbeatRun:
    """Create a HeartbeatRun directly in the DB for use as checkout token."""
    run = HeartbeatRun(
        uuid=uuid4(),
        agent_registration_id=agent_id,
        source="scheduler",
        status="running",
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Issue CRUD
# ---------------------------------------------------------------------------


class TestIssueCreate:
    """POST /v1/issues — create issue."""

    async def test_create_issue_returns_201(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Successful issue creation returns 201 with identifier and defaults."""
        data = await _create_issue(test_client, admin_auth_headers, title="My First Issue")
        assert "uuid" in data
        assert "identifier" in data
        assert data["identifier"].startswith("CAL-")
        assert data["title"] == "My First Issue"
        assert data["status"] == "backlog"
        assert data["priority"] == "medium"
        assert data["category"] == "investigation"

    async def test_create_issue_with_all_fields(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Issue can be created with explicit status, priority, and category."""
        resp = await test_client.post(
            "/v1/issues",
            json={
                "title": "High Priority Remediation",
                "description": "Block the attacking IP on the firewall.",
                "status": "todo",
                "priority": "high",
                "category": "remediation",
                "assignee_operator": "jorge",
            },
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()["data"]
        assert data["status"] == "todo"
        assert data["priority"] == "high"
        assert data["category"] == "remediation"
        assert data["assignee_operator"] == "jorge"

    async def test_create_issue_invalid_status_returns_422(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Invalid status value → 422."""
        resp = await test_client.post(
            "/v1/issues",
            json={"title": "Bad Status Issue", "status": "not_a_status"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_create_issue_invalid_priority_returns_422(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Invalid priority value → 422."""
        resp = await test_client.post(
            "/v1/issues",
            json={"title": "Bad Priority Issue", "priority": "super_urgent"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_create_issue_invalid_category_returns_422(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Invalid category value → 422."""
        resp = await test_client.post(
            "/v1/issues",
            json={"title": "Bad Category Issue", "category": "imaginary_category"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text


class TestIssueRead:
    """GET /v1/issues and GET /v1/issues/{uuid}."""

    async def test_get_issue_returns_200(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Created issue can be retrieved by UUID."""
        issue = await _create_issue(test_client, admin_auth_headers, title="Readable Issue")
        resp = await test_client.get(
            f"/v1/issues/{issue['uuid']}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["uuid"] == issue["uuid"]
        assert data["title"] == "Readable Issue"

    async def test_get_nonexistent_issue_returns_404(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET with a random UUID → 404."""
        resp = await test_client.get(
            f"/v1/issues/{uuid4()}",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404, resp.text

    async def test_list_issues_returns_paginated(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """List endpoint returns a paginated response with created issues."""
        await _create_issue(test_client, admin_auth_headers, title="List Issue Alpha")
        await _create_issue(test_client, admin_auth_headers, title="List Issue Beta")

        resp = await test_client.get("/v1/issues", headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert body["meta"]["total"] >= 2


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------


class TestIssueStatusTransitions:
    """PATCH /v1/issues/{uuid} — status side effects."""

    async def test_transition_to_in_progress_sets_started_at(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Patching status to in_progress sets started_at timestamp."""
        issue = await _create_issue(test_client, admin_auth_headers, title="In-Progress Issue")
        assert issue["started_at"] is None

        resp = await test_client.patch(
            f"/v1/issues/{issue['uuid']}",
            json={"status": "in_progress"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()["data"]
        assert updated["status"] == "in_progress"
        assert updated["started_at"] is not None

    async def test_transition_to_done_sets_completed_at(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Patching status to done sets completed_at timestamp."""
        issue = await _create_issue(test_client, admin_auth_headers, title="Done Issue")

        resp = await test_client.patch(
            f"/v1/issues/{issue['uuid']}",
            json={"status": "done", "resolution": "Resolved by disabling account."},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()["data"]
        assert updated["status"] == "done"
        assert updated["completed_at"] is not None
        assert updated["resolution"] == "Resolved by disabling account."

    async def test_transition_to_cancelled_sets_cancelled_at(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Patching status to cancelled sets cancelled_at timestamp."""
        issue = await _create_issue(test_client, admin_auth_headers, title="Cancelled Issue")

        resp = await test_client.patch(
            f"/v1/issues/{issue['uuid']}",
            json={"status": "cancelled"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        updated = resp.json()["data"]
        assert updated["status"] == "cancelled"
        assert updated["cancelled_at"] is not None


# ---------------------------------------------------------------------------
# Atomic checkout invariant
# ---------------------------------------------------------------------------


class TestIssueAtomicCheckout:
    """POST /v1/issues/{uuid}/checkout — exactly one concurrent caller wins."""

    async def test_checkout_requires_existing_heartbeat_run(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Checkout with a non-existent heartbeat_run_uuid → 404."""
        issue = await _create_issue(test_client, admin_auth_headers, title="Checkout 404 Issue")

        resp = await test_client.post(
            f"/v1/issues/{issue['uuid']}/checkout",
            json={"heartbeat_run_uuid": str(uuid4())},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404, resp.text

    async def test_concurrent_checkout_exactly_one_wins(
        self,
        db_session: AsyncSession,
    ) -> None:
        """10 concurrent checkout requests → exactly 1 succeeds (200), 9 fail (409).

        Mirrors test_phase1_checkout.py exactly: uses agent API keys (cak_*) so
        the auth path does not call db.flush() during concurrent execution.
        All data is created sequentially first to warm the session connection.
        """
        from httpx import ASGITransport
        from httpx import AsyncClient as HttpxClient

        from app.db.session import get_db
        from app.main import app

        # -- Phase 1: set up all data sequentially (warms the session connection) --
        # Collect (agent_auth_headers, run_uuid) pairs
        checkout_headers: list[dict[str, str]] = []
        run_uuids: list[str] = []
        for i in range(10):
            agent, plain_key = await _create_agent_with_key(
                db_session, name=f"issue-checkout-concurrent-{i}"
            )
            run = await _create_heartbeat_run(db_session, agent.id)
            checkout_headers.append(auth_header(plain_key))
            run_uuids.append(str(run.uuid))

        # Create the issue directly in the DB
        issue_orm = AgentIssue(
            uuid=uuid4(),
            identifier=f"CAL-CONC-{uuid4().hex[:6].upper()}",
            title="Concurrent Checkout Issue",
            status="backlog",
            priority="medium",
            category="investigation",
        )
        db_session.add(issue_orm)
        await db_session.flush()
        issue_uuid = str(issue_orm.uuid)
        # Expire so no pending state when concurrent calls start
        db_session.expire_all()

        # -- Phase 2: override get_db and fire concurrent requests --
        async def _override_get_db() -> Any:
            yield db_session

        app.dependency_overrides[get_db] = _override_get_db

        try:
            async def attempt_checkout(headers: dict[str, str], run_uuid: str) -> int:
                _transport = ASGITransport(app=app)  # type: ignore[arg-type]
                async with HttpxClient(transport=_transport, base_url="http://test") as _c:
                    resp = await _c.post(
                        f"/v1/issues/{issue_uuid}/checkout",
                        json={"heartbeat_run_uuid": run_uuid},
                        headers=headers,
                    )
                    return resp.status_code

            results = await asyncio.gather(
                *[
                    attempt_checkout(h, r)
                    for h, r in zip(checkout_headers, run_uuids, strict=True)
                ]
            )
        finally:
            app.dependency_overrides.pop(get_db, None)

        successes = [r for r in results if r == 200]
        conflicts = [r for r in results if r == 409]

        assert len(successes) == 1, f"Expected exactly 1 success, got: {results}"
        assert len(conflicts) == 9, f"Expected 9 conflicts, got: {results}"

    async def test_checkout_on_terminal_issue_returns_409(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Checkout on a done/cancelled issue → 409."""
        agent, _ = await _create_agent_with_key(db_session, name="terminal-checkout-agent")
        run = await _create_heartbeat_run(db_session, agent.id)
        await db_session.flush()

        issue = await _create_issue(test_client, admin_auth_headers, title="Terminal Issue")
        # Move to done
        await test_client.patch(
            f"/v1/issues/{issue['uuid']}",
            json={"status": "done"},
            headers=admin_auth_headers,
        )

        resp = await test_client.post(
            f"/v1/issues/{issue['uuid']}/checkout",
            json={"heartbeat_run_uuid": str(run.uuid)},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409, resp.text

    async def test_release_checkout_clears_lock(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """After release, another checkout request succeeds."""
        agent, _ = await _create_agent_with_key(db_session, name="release-checkout-agent-a")
        run_a = await _create_heartbeat_run(db_session, agent.id)
        agent_b, _ = await _create_agent_with_key(db_session, name="release-checkout-agent-b")
        run_b = await _create_heartbeat_run(db_session, agent_b.id)
        await db_session.flush()

        issue = await _create_issue(test_client, admin_auth_headers, title="Release Checkout Issue")

        # First checkout — must succeed
        resp = await test_client.post(
            f"/v1/issues/{issue['uuid']}/checkout",
            json={"heartbeat_run_uuid": str(run_a.uuid)},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text

        # Release
        rel = await test_client.post(
            f"/v1/issues/{issue['uuid']}/release",
            headers=admin_auth_headers,
        )
        assert rel.status_code == 200, rel.text

        # Second agent can now check out
        resp2 = await test_client.post(
            f"/v1/issues/{issue['uuid']}/checkout",
            json={"heartbeat_run_uuid": str(run_b.uuid)},
            headers=admin_auth_headers,
        )
        assert resp2.status_code == 200, resp2.text


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


class TestIssueComments:
    """POST /v1/issues/{uuid}/comments and GET /v1/issues/{uuid}/comments."""

    async def test_add_comment_returns_201(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Adding a comment returns 201 with the comment body."""
        issue = await _create_issue(test_client, admin_auth_headers, title="Comment Issue")

        resp = await test_client.post(
            f"/v1/issues/{issue['uuid']}/comments",
            json={"body": "First comment on this issue."},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        comment = resp.json()["data"]
        assert comment["body"] == "First comment on this issue."
        assert "uuid" in comment

    async def test_list_comments_returns_added_comments(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Comments added to an issue appear in the list endpoint."""
        issue = await _create_issue(test_client, admin_auth_headers, title="Multi-Comment Issue")

        for i in range(3):
            await test_client.post(
                f"/v1/issues/{issue['uuid']}/comments",
                json={"body": f"Comment number {i}"},
                headers=admin_auth_headers,
            )

        resp = await test_client.get(
            f"/v1/issues/{issue['uuid']}/comments",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["meta"]["total"] == 3
        bodies = [c["body"] for c in body["data"]]
        assert "Comment number 0" in bodies
        assert "Comment number 2" in bodies

    async def test_add_empty_comment_returns_422(
        self,
        test_client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Empty comment body → 422 (min_length=1)."""
        issue = await _create_issue(test_client, admin_auth_headers, title="Empty Comment Issue")

        resp = await test_client.post(
            f"/v1/issues/{issue['uuid']}/comments",
            json={"body": ""},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text
