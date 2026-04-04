"""KBPageRepository — CRUD and search operations for knowledge_base_pages, revisions, and links."""

from __future__ import annotations

import uuid as uuid_module
from uuid import UUID

from sqlalchemy import and_, func, or_, select, text

from app.db.models.kb_page import KnowledgeBasePage
from app.db.models.kb_page_link import KBPageLink
from app.db.models.kb_page_revision import KBPageRevision
from app.repositories.base import BaseRepository


class KBPageRepository(BaseRepository[KnowledgeBasePage]):
    model = KnowledgeBasePage

    # ----------------------------------------------------------------
    # Single-row lookups
    # ----------------------------------------------------------------

    async def get_by_slug(self, slug: str) -> KnowledgeBasePage | None:
        """Fetch a single page by slug."""
        result = await self._db.execute(
            select(KnowledgeBasePage).where(KnowledgeBasePage.slug == slug)
        )
        return result.scalar_one_or_none()  # type: ignore[return-value]

    # ----------------------------------------------------------------
    # List / filter
    # ----------------------------------------------------------------

    async def list_pages(
        self,
        folder: str | None = None,
        status: str | None = None,
        inject_scope_filter: str | None = None,
        has_sync_source: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[KnowledgeBasePage], int]:
        """Return (pages, total) with optional filters.

        inject_scope_filter values:
          'global'  — inject_scope->>'global' = 'true'
          'role'    — inject_scope ? 'roles'
          'agent'   — inject_scope ? 'agent_ids'
          'all'     — any non-NULL inject_scope
        """
        filters = []

        if folder is not None:
            # Match exact folder or any subfolder (prefix match)
            filters.append(
                or_(
                    KnowledgeBasePage.folder == folder,
                    KnowledgeBasePage.folder.like(folder.rstrip("/") + "/%"),
                )
            )

        if status is not None:
            filters.append(KnowledgeBasePage.status == status)

        if inject_scope_filter == "global":
            filters.append(text("inject_scope->>'global' = 'true'"))  # type: ignore[arg-type]
        elif inject_scope_filter == "role":
            filters.append(text("inject_scope ? 'roles'"))  # type: ignore[arg-type]
        elif inject_scope_filter == "agent":
            filters.append(text("inject_scope ? 'agent_ids'"))  # type: ignore[arg-type]
        elif inject_scope_filter == "all":
            filters.append(KnowledgeBasePage.inject_scope.is_not(None))

        if has_sync_source is True:
            filters.append(KnowledgeBasePage.sync_source.is_not(None))
        elif has_sync_source is False:
            filters.append(KnowledgeBasePage.sync_source.is_(None))

        return await self.paginate(
            *filters,
            order_by=KnowledgeBasePage.updated_at.desc(),
            page=page,
            page_size=page_size,
        )

    # ----------------------------------------------------------------
    # Full-text search
    # ----------------------------------------------------------------

    async def full_text_search(
        self,
        query: str,
        folder: str | None = None,
        status: str = "published",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[KnowledgeBasePage], int]:
        """Full-text search using PostgreSQL tsvector.

        Ranks results by ts_rank descending.
        """
        tsquery_expr = func.plainto_tsquery("english", query)

        base_conditions = [
            KnowledgeBasePage.search_vector.op("@@")(tsquery_expr),
            KnowledgeBasePage.status == status,
        ]
        if folder is not None:
            base_conditions.append(
                or_(
                    KnowledgeBasePage.folder == folder,
                    KnowledgeBasePage.folder.like(folder.rstrip("/") + "/%"),
                )
            )

        where_clause = and_(*base_conditions)

        count_stmt = (
            select(func.count())
            .select_from(KnowledgeBasePage)
            .where(where_clause)
        )
        total_result = await self._db.execute(count_stmt)
        total: int = total_result.scalar_one()

        rank_expr = func.ts_rank(KnowledgeBasePage.search_vector, tsquery_expr)

        stmt = (
            select(KnowledgeBasePage)
            .where(where_clause)
            .order_by(rank_expr.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    # ----------------------------------------------------------------
    # Create
    # ----------------------------------------------------------------

    async def create_page(
        self,
        slug: str,
        title: str,
        body: str,
        folder: str = "/",
        format: str = "markdown",
        status: str = "published",
        inject_scope: dict | None = None,
        inject_priority: int = 0,
        inject_pinned: bool = False,
        sync_source: dict | None = None,
        token_count: int | None = None,
        metadata: dict | None = None,
        created_by_agent_id: int | None = None,
        created_by_operator: str | None = None,
    ) -> KnowledgeBasePage:
        """Create a page + initial revision 1 and update search_vector."""
        page = KnowledgeBasePage(
            uuid=uuid_module.uuid4(),
            slug=slug,
            title=title,
            body=body,
            folder=folder,
            format=format,
            status=status,
            inject_scope=inject_scope,
            inject_priority=inject_priority,
            inject_pinned=inject_pinned,
            sync_source=sync_source,
            token_count=token_count,
            metadata_=metadata,
            created_by_agent_id=created_by_agent_id,
            created_by_operator=created_by_operator,
            updated_by_agent_id=created_by_agent_id,
            updated_by_operator=created_by_operator,
            latest_revision_number=1,
        )
        self._db.add(page)
        await self._db.flush()
        await self._db.refresh(page)

        # Create initial revision
        revision = KBPageRevision(
            uuid=uuid_module.uuid4(),
            page_id=page.id,
            revision_number=1,
            body=body,
            change_summary="Initial version",
            author_agent_id=created_by_agent_id,
            author_operator=created_by_operator,
        )
        self._db.add(revision)
        await self._db.flush()
        await self._db.refresh(revision)

        # Point latest_revision_id at the new revision
        page.latest_revision_id = revision.uuid
        await self._db.flush()

        # Update search vector
        await self.update_search_vector(page)
        await self._db.refresh(page)
        return page

    # ----------------------------------------------------------------
    # Update
    # ----------------------------------------------------------------

    async def update_page(
        self,
        page: KnowledgeBasePage,
        changes: dict,
        author_agent_id: int | None = None,
        author_operator: str | None = None,
        change_summary: str | None = None,
        sync_source_ref: str | None = None,
    ) -> KnowledgeBasePage:
        """Apply changes to a page.

        If body is in changes, creates a new revision and increments
        latest_revision_number. Always updates search_vector when title or body change.
        """
        body_changed = "body" in changes and changes["body"] != page.body
        title_changed = "title" in changes and changes["title"] != page.title

        # Apply field changes
        _UPDATABLE = frozenset({
            "title", "body", "folder", "status", "inject_scope",
            "inject_priority", "inject_pinned", "sync_source",
            "sync_last_hash", "synced_at", "token_count", "metadata_",
            "updated_by_agent_id", "updated_by_operator",
        })
        for key, value in changes.items():
            if key in _UPDATABLE:
                setattr(page, key, value)

        page.updated_by_agent_id = author_agent_id
        page.updated_by_operator = author_operator

        if body_changed:
            new_revision_number = page.latest_revision_number + 1
            revision = KBPageRevision(
                uuid=uuid_module.uuid4(),
                page_id=page.id,
                revision_number=new_revision_number,
                body=page.body,
                change_summary=change_summary,
                author_agent_id=author_agent_id,
                author_operator=author_operator,
                sync_source_ref=sync_source_ref,
            )
            self._db.add(revision)
            await self._db.flush()
            await self._db.refresh(revision)

            page.latest_revision_number = new_revision_number
            page.latest_revision_id = revision.uuid

        await self._db.flush()

        if body_changed or title_changed:
            await self.update_search_vector(page)

        await self._db.refresh(page)
        return page

    # ----------------------------------------------------------------
    # Revisions
    # ----------------------------------------------------------------

    async def get_revisions(
        self,
        page_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[KBPageRevision], int]:
        """Return (revisions, total) for the given page, newest first."""
        count_stmt = (
            select(func.count())
            .select_from(KBPageRevision)
            .where(KBPageRevision.page_id == page_id)
        )
        total_result = await self._db.execute(count_stmt)
        total: int = total_result.scalar_one()

        stmt = (
            select(KBPageRevision)
            .where(KBPageRevision.page_id == page_id)
            .order_by(KBPageRevision.revision_number.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_revision(
        self,
        page_id: int,
        revision_number: int,
    ) -> KBPageRevision | None:
        """Fetch a specific revision by page_id + revision_number."""
        result = await self._db.execute(
            select(KBPageRevision).where(
                KBPageRevision.page_id == page_id,
                KBPageRevision.revision_number == revision_number,
            )
        )
        return result.scalar_one_or_none()  # type: ignore[return-value]

    # ----------------------------------------------------------------
    # Links
    # ----------------------------------------------------------------

    async def create_link(
        self,
        page_id: int,
        linked_entity_type: str,
        linked_entity_id: UUID,
        link_type: str,
    ) -> KBPageLink:
        """Create a link from a page to another entity."""
        link = KBPageLink(
            uuid=uuid_module.uuid4(),
            page_id=page_id,
            linked_entity_type=linked_entity_type,
            linked_entity_id=linked_entity_id,
            link_type=link_type,
        )
        self._db.add(link)
        await self._db.flush()
        await self._db.refresh(link)
        return link

    async def list_links(self, page_id: int) -> list[KBPageLink]:
        """Return all links for the given page."""
        result = await self._db.execute(
            select(KBPageLink)
            .where(KBPageLink.page_id == page_id)
            .order_by(KBPageLink.created_at.asc())
        )
        return list(result.scalars().all())

    # ----------------------------------------------------------------
    # Injection queries
    # ----------------------------------------------------------------

    async def get_injectable_pages(
        self,
        agent_uuid: str,
        agent_role: str | None,
    ) -> list[KnowledgeBasePage]:
        """Return published pages whose inject_scope matches this agent.

        Matches:
          - inject_scope->>'global' = 'true'
          - inject_scope->'roles' contains agent_role (if provided)
          - inject_scope->'agent_ids' contains agent_uuid

        Ordered by: inject_pinned DESC, inject_priority DESC, updated_at DESC.
        """
        conditions = [
            KnowledgeBasePage.status == "published",
            KnowledgeBasePage.inject_scope.is_not(None),
        ]

        scope_conditions = [
            text("inject_scope->>'global' = 'true'"),
            text(f"inject_scope->'agent_ids' ? '{agent_uuid}'"),
        ]
        if agent_role:
            scope_conditions.append(
                text(f"inject_scope->'roles' ? '{agent_role}'")
            )

        stmt = (
            select(KnowledgeBasePage)
            .where(
                and_(
                    *conditions,
                    or_(*scope_conditions),
                )
            )
            .order_by(
                KnowledgeBasePage.inject_pinned.desc(),
                KnowledgeBasePage.inject_priority.desc(),
                KnowledgeBasePage.updated_at.desc(),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_pages_for_sync(self) -> list[KnowledgeBasePage]:
        """Return pages with sync_source configured in syncable states."""
        stmt = (
            select(KnowledgeBasePage)
            .where(
                and_(
                    KnowledgeBasePage.sync_source.is_not(None),
                    KnowledgeBasePage.status.in_(["published", "draft"]),
                )
            )
            .order_by(KnowledgeBasePage.synced_at.asc().nullsfirst())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    # ----------------------------------------------------------------
    # Search vector maintenance
    # ----------------------------------------------------------------

    async def update_search_vector(self, page: KnowledgeBasePage) -> None:
        """Recompute the tsvector for a page using PostgreSQL to_tsvector."""
        await self._db.execute(
            text(
                "UPDATE knowledge_base_pages "
                "SET search_vector = to_tsvector('english', :title || ' ' || :body) "
                "WHERE id = :id"
            ),
            {"id": page.id, "title": page.title, "body": page.body},
        )
