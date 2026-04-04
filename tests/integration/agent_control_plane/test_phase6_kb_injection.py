"""Integration tests — Phase 6 KB context injection (Layer 3 + Layer 6).

Covers:
- KBPageRepository.get_injectable_pages: global scope, role scope, agent_id scope
- Token budget cap: pages over budget are excluded (non-pinned)
- Pinned pages always included regardless of budget
- PromptBuilder layer 3 XML block structure
- PromptBuilder layer 6 memory block structure
- Empty result when no injectable pages exist
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.kb_page import KnowledgeBasePage
from tests.integration.agent_control_plane.conftest import _create_agent_with_key

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_kb_page(
    db: AsyncSession,
    *,
    title: str,
    slug: str,
    body: str,
    folder: str = "/docs/",
    inject_scope: dict | None = None,
    inject_pinned: bool = False,
    status: str = "published",
    token_count: int | None = None,
) -> KnowledgeBasePage:
    page = KnowledgeBasePage(
        title=title,
        slug=slug,
        body=body,
        folder=folder,
        status=status,
        inject_scope=inject_scope or {},
        inject_pinned=inject_pinned,
        token_count=token_count,
        latest_revision_number=1,
    )
    db.add(page)
    await db.flush()
    await db.refresh(page)
    return page


# ---------------------------------------------------------------------------
# KBPageRepository.get_injectable_pages
# ---------------------------------------------------------------------------


class TestGetInjectablePages:
    async def test_global_scope_returned_for_any_agent(
        self,
        db_session: AsyncSession,
    ) -> None:
        from app.repositories.kb_repository import KBPageRepository

        agent, _ = await _create_agent_with_key(db_session, name="inject-global-agent")
        await _insert_kb_page(
            db_session,
            title="Global Page",
            slug=f"global-inject-{agent.id}",
            body="Global KB content.",
            inject_scope={"global": True},
        )

        repo = KBPageRepository(db_session)
        pages = await repo.get_injectable_pages(
            agent_uuid=str(agent.uuid),
            agent_role=agent.role,
        )
        slugs = [p.slug for p in pages]
        assert f"global-inject-{agent.id}" in slugs

    async def test_role_scope_returned_for_matching_role(
        self,
        db_session: AsyncSession,
    ) -> None:
        from app.repositories.kb_repository import KBPageRepository

        agent, _ = await _create_agent_with_key(db_session, name="inject-role-agent")
        agent.role = "triage"
        await db_session.flush()

        await _insert_kb_page(
            db_session,
            title="Triage Page",
            slug=f"triage-inject-{agent.id}",
            body="Triage runbook content.",
            inject_scope={"roles": ["triage"]},
        )

        repo = KBPageRepository(db_session)
        pages = await repo.get_injectable_pages(
            agent_uuid=str(agent.uuid),
            agent_role="triage",
        )
        slugs = [p.slug for p in pages]
        assert f"triage-inject-{agent.id}" in slugs

    async def test_role_scope_not_returned_for_different_role(
        self,
        db_session: AsyncSession,
    ) -> None:
        from app.repositories.kb_repository import KBPageRepository

        agent, _ = await _create_agent_with_key(db_session, name="inject-wrong-role-agent")

        await _insert_kb_page(
            db_session,
            title="Analyst Only Page",
            slug=f"analyst-inject-{agent.id}",
            body="Only for analysts.",
            inject_scope={"roles": ["analyst"]},
        )

        repo = KBPageRepository(db_session)
        pages = await repo.get_injectable_pages(
            agent_uuid=str(agent.uuid),
            agent_role="triage",  # different role
        )
        slugs = [p.slug for p in pages]
        assert f"analyst-inject-{agent.id}" not in slugs

    async def test_agent_id_scope_returned_for_matching_agent(
        self,
        db_session: AsyncSession,
    ) -> None:
        from app.repositories.kb_repository import KBPageRepository

        agent, _ = await _create_agent_with_key(db_session, name="inject-agent-id-agent")

        await _insert_kb_page(
            db_session,
            title="Agent-Specific Page",
            slug=f"agent-id-inject-{agent.id}",
            body="Only for this specific agent.",
            inject_scope={"agent_ids": [str(agent.uuid)]},
        )

        repo = KBPageRepository(db_session)
        pages = await repo.get_injectable_pages(
            agent_uuid=str(agent.uuid),
            agent_role=agent.role,
        )
        slugs = [p.slug for p in pages]
        assert f"agent-id-inject-{agent.id}" in slugs

    async def test_draft_pages_not_injected(
        self,
        db_session: AsyncSession,
    ) -> None:
        from app.repositories.kb_repository import KBPageRepository

        agent, _ = await _create_agent_with_key(db_session, name="inject-draft-agent")

        await _insert_kb_page(
            db_session,
            title="Draft Page",
            slug=f"draft-inject-{agent.id}",
            body="Draft content should not be injected.",
            inject_scope={"global": True},
            status="draft",
        )

        repo = KBPageRepository(db_session)
        pages = await repo.get_injectable_pages(
            agent_uuid=str(agent.uuid),
            agent_role=agent.role,
        )
        slugs = [p.slug for p in pages]
        assert f"draft-inject-{agent.id}" not in slugs


# ---------------------------------------------------------------------------
# Token budget enforcement
# ---------------------------------------------------------------------------


class TestTokenBudget:
    async def test_non_pinned_page_excluded_over_budget(
        self,
        db_session: AsyncSession,
    ) -> None:
        """A non-pinned page that exceeds the remaining budget is skipped."""
        from app.runtime.prompt_builder import _KB_BUDGET_PCT, PromptBuilder

        agent, _ = await _create_agent_with_key(db_session, name="budget-limit-agent")

        # Two large pages that together exceed 15% of 10_000 token budget
        context_window = 10_000
        int(context_window * _KB_BUDGET_PCT)  # 1500 tokens
        big_body = "x " * 800  # ~400 tokens each (rough 4-chars-per-token)

        await _insert_kb_page(
            db_session,
            title="Big Page A",
            slug=f"budget-big-a-{agent.id}",
            body=big_body,
            inject_scope={"global": True},
            token_count=800,
        )
        await _insert_kb_page(
            db_session,
            title="Big Page B",
            slug=f"budget-big-b-{agent.id}",
            body=big_body,
            inject_scope={"global": True},
            token_count=800,
        )

        builder = PromptBuilder(db_session)
        layer3, tokens = await builder._build_layer3_kb(agent, context_window)

        # One page fits, second pushes over budget
        # Either only one is included, or the layer3 is empty if even one doesn't fit
        # The first page (800 tokens) fits within 1500 budget, the second (800 more) doesn't
        assert "budget-big-a" in layer3 or "budget-big-b" in layer3
        # Both shouldn't be present
        assert not ("budget-big-a" in layer3 and "budget-big-b" in layer3)

    async def test_pinned_page_always_included(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Pinned pages bypass token budget."""
        from app.runtime.prompt_builder import PromptBuilder

        agent, _ = await _create_agent_with_key(db_session, name="budget-pinned-agent")

        await _insert_kb_page(
            db_session,
            title="Pinned Critical Page",
            slug=f"pinned-critical-{agent.id}",
            body="Critical runbook that must always be injected.",
            inject_scope={"global": True},
            inject_pinned=True,
            token_count=5000,  # Massive — over budget
        )

        builder = PromptBuilder(db_session)
        layer3, _ = await builder._build_layer3_kb(agent, 10_000)

        assert f"pinned-critical-{agent.id}" in layer3

    async def test_empty_result_when_no_injectable_pages(
        self,
        db_session: AsyncSession,
    ) -> None:
        from app.runtime.prompt_builder import PromptBuilder

        agent, _ = await _create_agent_with_key(db_session, name="no-kb-agent")

        builder = PromptBuilder(db_session)
        layer3, tokens = await builder._build_layer3_kb(agent, 200_000)

        # No pages in DB for this agent = empty
        assert tokens == 0
        # layer3 is either empty string or doesn't mention pages for this agent
        # (other agents' pages may exist from other tests; we just verify no crash)


# ---------------------------------------------------------------------------
# PromptBuilder XML structure
# ---------------------------------------------------------------------------


class TestPromptBuilderXMLStructure:
    async def test_layer3_xml_contains_context_document_tags(
        self,
        db_session: AsyncSession,
    ) -> None:
        from app.runtime.prompt_builder import PromptBuilder

        agent, _ = await _create_agent_with_key(db_session, name="xml-structure-agent")

        await _insert_kb_page(
            db_session,
            title="XML Test Page",
            slug=f"xml-structure-{agent.id}",
            body="Test body for XML structure.",
            inject_scope={"global": True},
        )

        builder = PromptBuilder(db_session)
        layer3, _ = await builder._build_layer3_kb(agent, 200_000)

        assert "<context_document" in layer3
        assert "</context_document>" in layer3
        assert 'title="' in layer3
        assert 'slug="' in layer3

    async def test_layer6_memory_contains_agent_memory_tags(
        self,
        db_session: AsyncSession,
    ) -> None:
        from app.runtime.prompt_builder import PromptBuilder

        agent, _ = await _create_agent_with_key(db_session, name="mem-xml-agent")

        # Insert a memory page in the correct folder
        memory_page = KnowledgeBasePage(
            title="Test Memory Entry",
            slug=f"mem-entry-{agent.id}",
            body="Agent remembered this fact.",
            folder=f"/memory/agents/{agent.id}/",
            status="published",
            inject_scope={},
            inject_pinned=False,
            latest_revision_number=1,
        )
        db_session.add(memory_page)
        await db_session.flush()

        builder = PromptBuilder(db_session)
        memory_block = await builder._build_memory_block(agent, 200_000)

        assert "<agent_memory>" in memory_block
        assert "</agent_memory>" in memory_block
        assert "<memory " in memory_block
        assert "Test Memory Entry" in memory_block

    async def test_layer6_stale_memory_has_stale_prefix(
        self,
        db_session: AsyncSession,
    ) -> None:
        from app.runtime.prompt_builder import PromptBuilder

        agent, _ = await _create_agent_with_key(db_session, name="stale-mem-agent")

        # Insert a memory page with 24h TTL that is 100h old
        stale_page = KnowledgeBasePage(
            title="Stale Memory",
            slug=f"stale-mem-{agent.id}",
            body="This memory is stale.",
            folder=f"/memory/agents/{agent.id}/",
            status="published",
            inject_scope={},
            inject_pinned=False,
            latest_revision_number=1,
            metadata_={"staleness_ttl_hours": 24},
            updated_at=datetime.now(UTC) - timedelta(hours=100),
        )
        db_session.add(stale_page)
        await db_session.flush()

        builder = PromptBuilder(db_session)
        memory_block = await builder._build_memory_block(agent, 200_000)

        assert "[STALE" in memory_block
        assert "hours ago" in memory_block
