"""Integration tests — Phase 6 Agent Persistent Memory.

Covers:
- Save memory (POST /v1/kb with /memory/agents/{id}/ folder)
- Recall memory (GET /v1/agents/{uuid}/memory)
- Update memory (PATCH /v1/memory/{uuid})
- Delete memory (DELETE /v1/memory/{uuid})
- Promote memory (POST /v1/memory/{uuid}/promote)
  — requires memory_promotion_requires_approval to be False
- Staleness TTL: _is_memory_stale returns True when TTL exceeded
- _xml_escape helper
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.agent_control_plane.conftest import _create_agent_with_key
from tests.integration.conftest import auth_header

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _save_memory_via_kb(
    client: AsyncClient,
    admin_key: str,
    folder: str,
    *,
    title: str = "Test Memory",
    body: str = "Memory content.",
    slug: str | None = None,
) -> dict[str, object]:
    """Create a memory entry via the KB API (admin key required)."""
    import time

    payload: dict[str, object] = {
        "title": title,
        "slug": slug or f"mem-{int(time.time() * 1000)}",
        "body": body,
        "folder": folder,
        "status": "published",
    }
    resp = await client.post(
        "/v1/kb",
        json=payload,
        headers=auth_header(admin_key),
    )
    assert resp.status_code == 201, resp.text
    result: dict[str, object] = resp.json()["data"]
    return result


# ---------------------------------------------------------------------------
# Save / Recall / Update / Delete
# ---------------------------------------------------------------------------


class TestMemorySaveRecall:
    async def test_save_memory_creates_in_agent_folder(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        scoped_api_key: Any,
    ) -> None:

        agent, _ = await _create_agent_with_key(db_session, name="mem-save-agent")
        admin_key: str = await scoped_api_key(["admin"])
        folder = f"/memory/agents/{agent.id}/"

        mem = await _save_memory_via_kb(
            test_client, admin_key, folder,
            title="Incident Context",
            body="We investigated IPs 1.2.3.4 and 5.6.7.8.",
        )
        assert mem["title"] == "Incident Context"
        assert str(mem["folder"]) == folder

    async def test_recall_returns_saved_memory(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        scoped_api_key: Any,
    ) -> None:
        agent, agent_key = await _create_agent_with_key(db_session, name="mem-recall-agent")
        admin_key: str = await scoped_api_key(["admin"])
        folder = f"/memory/agents/{agent.id}/"

        await _save_memory_via_kb(
            test_client, admin_key, folder,
            title="Recall Test",
            body="Remembered something important.",
            slug="recall-test-mem",
        )

        # Use admin key to list (agents:read would work too but admin is simpler)
        resp = await test_client.get(
            f"/v1/agents/{agent.uuid}/memory",
            headers=auth_header(admin_key),
        )
        assert resp.status_code == 200
        entries = resp.json()["data"]
        titles = [e["title"] for e in entries]
        assert "Recall Test" in titles

    async def test_update_memory(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        scoped_api_key: Any,
    ) -> None:
        agent, _ = await _create_agent_with_key(db_session, name="mem-update-agent")
        admin_key: str = await scoped_api_key(["admin"])
        folder = f"/memory/agents/{agent.id}/"

        mem = await _save_memory_via_kb(
            test_client, admin_key, folder,
            slug="update-test-mem",
            body="Original body.",
        )

        resp = await test_client.patch(
            f"/v1/memory/{mem['uuid']}",
            json={"body": "Updated body content."},
            headers=auth_header(admin_key),
        )
        assert resp.status_code == 200
        updated = resp.json()["data"]
        assert updated["body"] == "Updated body content."

    async def test_delete_memory(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        scoped_api_key: Any,
    ) -> None:
        agent, _ = await _create_agent_with_key(db_session, name="mem-delete-agent")
        admin_key: str = await scoped_api_key(["admin"])
        folder = f"/memory/agents/{agent.id}/"

        mem = await _save_memory_via_kb(
            test_client, admin_key, folder,
            slug="delete-test-mem",
        )

        resp = await test_client.delete(
            f"/v1/memory/{mem['uuid']}",
            headers=auth_header(admin_key),
        )
        assert resp.status_code == 204

        # Confirm entry is no longer in the list
        resp2 = await test_client.get(
            f"/v1/agents/{agent.uuid}/memory",
            headers=auth_header(admin_key),
        )
        slugs = [e["slug"] for e in resp2.json()["data"]]
        assert "delete-test-mem" not in slugs

    async def test_memory_stored_in_agent_folder(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        scoped_api_key: Any,
    ) -> None:
        agent, _ = await _create_agent_with_key(db_session, name="mem-folder-agent")
        admin_key: str = await scoped_api_key(["admin"])
        expected_folder = f"/memory/agents/{agent.id}/"

        mem = await _save_memory_via_kb(
            test_client, admin_key, expected_folder,
            body="Folder verification test.",
        )
        assert str(mem["folder"]) == expected_folder


# ---------------------------------------------------------------------------
# Promote memory
# ---------------------------------------------------------------------------


class TestMemoryPromotion:
    async def test_promote_moves_to_shared_folder(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        scoped_api_key: Any,
    ) -> None:
        agent, _ = await _create_agent_with_key(db_session, name="mem-promote-agent")
        # Ensure promotion does not require approval
        agent.memory_promotion_requires_approval = False
        await db_session.flush()

        admin_key: str = await scoped_api_key(["admin"])
        folder = f"/memory/agents/{agent.id}/"
        mem = await _save_memory_via_kb(
            test_client, admin_key, folder,
            slug="promote-test-mem",
            body="This insight should be shared.",
        )

        resp = await test_client.post(
            f"/v1/memory/{mem['uuid']}/promote",
            headers=auth_header(admin_key),
        )
        assert resp.status_code == 200
        promoted = resp.json()["data"]
        assert str(promoted.get("folder", "")) == "/memory/shared/"

    async def test_promote_returns_pending_when_approval_required(
        self,
        test_client: AsyncClient,
        db_session: AsyncSession,
        scoped_api_key: Any,
    ) -> None:
        agent, _ = await _create_agent_with_key(
            db_session, name="mem-promote-blocked-agent"
        )
        agent.memory_promotion_requires_approval = True
        await db_session.flush()

        admin_key: str = await scoped_api_key(["admin"])
        folder = f"/memory/agents/{agent.id}/"
        mem = await _save_memory_via_kb(
            test_client, admin_key, folder,
            slug="promote-blocked-mem",
            body="Should be pending.",
        )

        resp = await test_client.post(
            f"/v1/memory/{mem['uuid']}/promote",
            headers=auth_header(admin_key),
        )
        assert resp.status_code == 200
        body = resp.json()["data"]
        # Should indicate pending/requires approval
        assert "pending" in str(body).lower() or "approval" in str(body).lower()


# ---------------------------------------------------------------------------
# Staleness detection
# ---------------------------------------------------------------------------


class TestMemoryStaleness:
    def test_is_memory_stale_false_when_no_ttl(self) -> None:
        from app.runtime.prompt_builder import _is_memory_stale

        page = type("Page", (), {
            "metadata_": {},
            "updated_at": datetime.now(UTC) - timedelta(hours=200),
        })()
        assert _is_memory_stale(page, datetime.now(UTC)) is False

    def test_is_memory_stale_false_within_ttl(self) -> None:
        from app.runtime.prompt_builder import _is_memory_stale

        page = type("Page", (), {
            "metadata_": {"staleness_ttl_hours": 48},
            "updated_at": datetime.now(UTC) - timedelta(hours=10),
        })()
        assert _is_memory_stale(page, datetime.now(UTC)) is False

    def test_is_memory_stale_true_beyond_ttl(self) -> None:
        from app.runtime.prompt_builder import _is_memory_stale

        page = type("Page", (), {
            "metadata_": {"staleness_ttl_hours": 24},
            "updated_at": datetime.now(UTC) - timedelta(hours=100),
        })()
        assert _is_memory_stale(page, datetime.now(UTC)) is True

    def test_is_memory_stale_naive_datetime(self) -> None:
        from app.runtime.prompt_builder import _is_memory_stale

        # updated_at without tzinfo
        page = type("Page", (), {
            "metadata_": {"staleness_ttl_hours": 12},
            "updated_at": datetime.now() - timedelta(hours=50),
        })()
        assert _is_memory_stale(page, datetime.now(UTC)) is True


# ---------------------------------------------------------------------------
# _xml_escape helper
# ---------------------------------------------------------------------------


class TestXmlEscape:
    def test_escapes_ampersand(self) -> None:
        from app.runtime.prompt_builder import _xml_escape

        assert _xml_escape("a & b") == "a &amp; b"

    def test_escapes_quotes(self) -> None:
        from app.runtime.prompt_builder import _xml_escape

        assert _xml_escape('say "hi"') == "say &quot;hi&quot;"

    def test_escapes_angle_brackets(self) -> None:
        from app.runtime.prompt_builder import _xml_escape

        assert _xml_escape("<tag>") == "&lt;tag&gt;"

    def test_passthrough_clean_string(self) -> None:
        from app.runtime.prompt_builder import _xml_escape

        assert _xml_escape("clean string 123") == "clean string 123"
