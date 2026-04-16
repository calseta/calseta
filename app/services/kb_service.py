"""KBService — business logic for the knowledge base and agent memory system.

Flow:
  1. create_page: validate slug uniqueness, persist with initial revision, update search vector.
  2. get_page / list_pages: read-only queries via repository.
  3. update_page: validate, apply changes, auto-create revision if body changed,
     update search vector.
  4. delete_page: archive (status='archived') by default. Hard delete only if force=True.
  5. search_pages: full-text search via tsvector.
  6. get_folders: derive folder hierarchy from distinct folder paths.
  7. link_page: create kb_page_link, validate entity type + link type combination.
  8. sync_page: fetch from external source, compare hash, update if changed.
  9. sync_all_pages: run sync for all pages with sync_source set.
  10. resolve_kb_context: return pages to inject into agent prompt (Layer 3).

Memory conventions:
  - Memory pages live in folder '/memory/agents/{agent_id}/' or '/memory/shared/'
  - inject_scope auto-set on save to target owning agent
  - Staleness: TTL from metadata.staleness_ttl_hours, hash from metadata.source_hash
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.db.models.kb_page import KnowledgeBasePage
from app.db.models.kb_page_link import KBPageLink
from app.db.models.kb_page_revision import KBPageRevision
from app.integrations.kb_sync.registry import get_sync_provider
from app.repositories.kb_repository import KBPageRepository
from app.schemas.kb import (
    KBFolderNode,
    KBPageCreate,
    KBPageLinkCreate,
    KBPageLinkResponse,
    KBPagePatch,
    KBPageResponse,
    KBPageRevisionResponse,
    KBPageSummary,
    KBSearchResultItem,
    KBSyncResult,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal response builders
# ---------------------------------------------------------------------------


def _build_page_response(page: KnowledgeBasePage) -> KBPageResponse:
    """Map a KnowledgeBasePage ORM object to KBPageResponse."""
    links = [_build_link_response(link) for link in (page.links or [])]
    return KBPageResponse(
        uuid=page.uuid,
        slug=page.slug,
        title=page.title,
        body=page.body,
        folder=page.folder,
        format=page.format,
        status=page.status,
        tags=page.tags,
        description=page.description,
        targeting_rules=page.targeting_rules,
        inject_scope=page.inject_scope,
        inject_priority=page.inject_priority,
        inject_pinned=page.inject_pinned,
        sync_source=page.sync_source,
        sync_last_hash=page.sync_last_hash,
        synced_at=page.synced_at,
        token_count=page.token_count,
        latest_revision_number=page.latest_revision_number,
        metadata_=page.metadata_,
        created_at=page.created_at,
        updated_at=page.updated_at,
        links=links,
    )


def _build_page_summary(page: KnowledgeBasePage) -> KBPageSummary:
    """Map a KnowledgeBasePage ORM object to KBPageSummary (no body)."""
    return KBPageSummary(
        uuid=page.uuid,
        slug=page.slug,
        title=page.title,
        folder=page.folder,
        format=page.format,
        status=page.status,
        tags=page.tags,
        description=page.description,
        targeting_rules=page.targeting_rules,
        inject_scope=page.inject_scope,
        inject_priority=page.inject_priority,
        inject_pinned=page.inject_pinned,
        sync_source=page.sync_source,
        synced_at=page.synced_at,
        token_count=page.token_count,
        latest_revision_number=page.latest_revision_number,
        created_at=page.created_at,
        updated_at=page.updated_at,
    )


def _build_revision_response(revision: KBPageRevision) -> KBPageRevisionResponse:
    """Map a KBPageRevision ORM object to KBPageRevisionResponse."""
    return KBPageRevisionResponse(
        uuid=revision.uuid,
        revision_number=revision.revision_number,
        body=revision.body,
        change_summary=revision.change_summary,
        author_operator=revision.author_operator,
        sync_source_ref=revision.sync_source_ref,
        created_at=revision.created_at,
    )


def _build_link_response(link: KBPageLink) -> KBPageLinkResponse:
    """Map a KBPageLink ORM object to KBPageLinkResponse."""
    return KBPageLinkResponse(
        uuid=link.uuid,
        linked_entity_type=link.linked_entity_type,
        linked_entity_id=link.linked_entity_id,  # type: ignore[arg-type]
        link_type=link.link_type,
        created_at=link.created_at,
    )


# ---------------------------------------------------------------------------
# Folder tree helpers
# ---------------------------------------------------------------------------


def _build_folder_tree(folders: list[tuple[str, int]]) -> list[KBFolderNode]:
    """Build a nested KBFolderNode tree from (folder_path, page_count) tuples.

    Paths use '/' as separator. The root '/' is collapsed — its children are
    returned as top-level nodes.
    """
    # Sort so parents always precede children
    folders_sorted = sorted(folders, key=lambda x: x[0])

    nodes: dict[str, KBFolderNode] = {}

    for path, count in folders_sorted:
        # Normalize: ensure leading slash, strip trailing slash unless root
        if not path.startswith("/"):
            path = "/" + path
        path = path.rstrip("/") or "/"

        name = path.rsplit("/", 1)[-1] or path
        node = KBFolderNode(path=path, name=name, page_count=count)
        nodes[path] = node

    # Wire up children
    roots: list[KBFolderNode] = []
    for path, node in sorted(nodes.items()):
        if path == "/":
            # root-level — children added below
            continue
        # Find parent
        parent_path = path.rsplit("/", 1)[0] or "/"
        if parent_path in nodes:
            nodes[parent_path].children.append(node)
        else:
            roots.append(node)

    # Add root's children as top-level if root exists
    if "/" in nodes:
        roots = nodes["/"].children + [n for n in roots if n not in nodes["/"].children]

    return sorted(roots, key=lambda n: n.path)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class KBService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = KBPageRepository(db)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_page(
        self,
        data: KBPageCreate,
        created_by_operator: str | None = None,
        created_by_agent_uuid: UUID | None = None,
    ) -> KBPageResponse:
        """Validate slug uniqueness, create page with initial revision, update search vector."""
        existing = await self._repo.get_by_slug(data.slug)
        if existing is not None:
            raise CalsetaException(
                status_code=409,
                code="slug_conflict",
                message=f"A KB page with slug '{data.slug}' already exists",
            )

        # Resolve agent UUID to int ID if provided
        created_by_agent_id: int | None = None
        if created_by_agent_uuid is not None:
            from app.repositories.agent_repository import AgentRepository

            agent_repo = AgentRepository(self._db)
            agent = await agent_repo.get_by_uuid(created_by_agent_uuid)
            if agent is None:
                raise CalsetaException(
                    status_code=404,
                    code="agent_not_found",
                    message=f"Agent '{created_by_agent_uuid}' not found",
                )
            created_by_agent_id = agent.id

        page = await self._repo.create_page(
            slug=data.slug,
            title=data.title,
            body=data.body,
            folder=data.folder,
            format=data.format,
            status=data.status,
            tags=data.tags,
            description=data.description,
            targeting_rules=data.targeting_rules,
            inject_scope=data.inject_scope,
            inject_priority=data.inject_priority,
            inject_pinned=data.inject_pinned,
            sync_source=data.sync_source,
            token_count=data.token_count,
            metadata=data.metadata,
            created_by_agent_id=created_by_agent_id,
            created_by_operator=created_by_operator,
        )
        await self._db.refresh(page, ["links"])

        logger.info("kb_page_created", slug=page.slug)
        return _build_page_response(page)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_page(self, slug: str) -> KBPageResponse:
        """Fetch a page by slug, raise 404 if missing or archived."""
        page = await self._repo.get_by_slug(slug)
        if page is None or page.status == "archived":
            raise CalsetaException(
                status_code=404,
                code="kb_page_not_found",
                message=f"KB page '{slug}' not found",
            )
        await self._db.refresh(page, ["links"])
        return _build_page_response(page)

    async def get_page_by_uuid(self, uuid: UUID) -> KBPageResponse:
        """Fetch a page by UUID, raise 404 if missing or archived."""
        page = await self._repo.get_by_uuid(uuid)
        if page is None or page.status == "archived":
            raise CalsetaException(
                status_code=404,
                code="kb_page_not_found",
                message="KB page not found",
            )
        await self._db.refresh(page, ["links"])
        return _build_page_response(page)

    async def update_page_by_uuid(
        self,
        uuid: UUID,
        patch: KBPagePatch,
        updated_by_operator: str | None = None,
    ) -> KBPageResponse:
        """Update a page looked up by UUID instead of slug."""
        page = await self._repo.get_by_uuid(uuid)
        if page is None or page.status == "archived":
            raise CalsetaException(
                status_code=404,
                code="kb_page_not_found",
                message="KB page not found",
            )
        return await self.update_page(
            slug=page.slug,
            patch=patch,
            updated_by_operator=updated_by_operator,
        )

    async def delete_page_by_uuid(self, uuid: UUID) -> None:
        """Archive a page looked up by UUID."""
        page = await self._repo.get_by_uuid(uuid)
        if page is None:
            raise CalsetaException(
                status_code=404,
                code="kb_page_not_found",
                message="KB page not found",
            )
        await self._repo.update_page(page, {"status": "archived"})
        logger.info("kb_page_deleted", uuid=str(uuid))

    async def list_pages(
        self,
        folder: str | None = None,
        status: str | None = None,
        inject_scope_filter: str | None = None,
        has_sync_source: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[KBPageSummary], int]:
        """List pages with optional filters. Returns (summaries, total)."""
        pages, total = await self._repo.list_pages(
            folder=folder,
            status=status,
            inject_scope_filter=inject_scope_filter,
            has_sync_source=has_sync_source,
            page=page,
            page_size=page_size,
        )
        return [_build_page_summary(p) for p in pages], total

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_page(
        self,
        slug: str,
        patch: KBPagePatch,
        updated_by_operator: str | None = None,
        updated_by_agent_uuid: UUID | None = None,
    ) -> KBPageResponse:
        """Apply a partial update. Auto-creates a revision if body changed."""
        page = await self._repo.get_by_slug(slug)
        if page is None:
            raise CalsetaException(
                status_code=404,
                code="kb_page_not_found",
                message=f"KB page '{slug}' not found",
            )

        # Resolve agent UUID to int ID if provided
        updated_by_agent_id: int | None = None
        if updated_by_agent_uuid is not None:
            from app.repositories.agent_repository import AgentRepository

            agent_repo = AgentRepository(self._db)
            agent = await agent_repo.get_by_uuid(updated_by_agent_uuid)
            if agent is not None:
                updated_by_agent_id = agent.id

        changes: dict[str, Any] = {}
        if patch.slug is not None and patch.slug != page.slug:
            existing = await self._repo.get_by_slug(patch.slug)
            if existing is not None:
                raise CalsetaException(
                    status_code=409,
                    code="slug_conflict",
                    message=f"A KB page with slug '{patch.slug}' already exists",
                )
            changes["slug"] = patch.slug
        if patch.title is not None:
            changes["title"] = patch.title
        if patch.body is not None:
            changes["body"] = patch.body
        if patch.folder is not None:
            changes["folder"] = patch.folder
        if patch.status is not None:
            _validate_kb_status(patch.status)
            changes["status"] = patch.status
        if patch.tags is not None:
            changes["tags"] = patch.tags
        if patch.description is not None:
            changes["description"] = patch.description
        if patch.targeting_rules is not None:
            changes["targeting_rules"] = patch.targeting_rules
        if patch.inject_scope is not None:
            changes["inject_scope"] = patch.inject_scope
        if patch.inject_priority is not None:
            changes["inject_priority"] = patch.inject_priority
        if patch.inject_pinned is not None:
            changes["inject_pinned"] = patch.inject_pinned
        if patch.sync_source is not None:
            changes["sync_source"] = patch.sync_source
        if patch.token_count is not None:
            changes["token_count"] = patch.token_count
        if patch.metadata is not None:
            changes["metadata_"] = patch.metadata

        updated = await self._repo.update_page(
            page,
            changes,
            author_agent_id=updated_by_agent_id,
            author_operator=updated_by_operator,
            change_summary=patch.change_summary,
        )
        await self._db.refresh(updated, ["links"])

        logger.info("kb_page_updated", slug=slug)
        return _build_page_response(updated)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_page(self, slug: str, force: bool = False) -> None:
        """Archive the page by default (status='archived'). Hard-delete if force=True."""
        page = await self._repo.get_by_slug(slug)
        if page is None:
            raise CalsetaException(
                status_code=404,
                code="kb_page_not_found",
                message=f"KB page '{slug}' not found",
            )

        if force:
            await self._db.delete(page)
            await self._db.flush()
            logger.info("kb_page_deleted", slug=slug, force=True)
        else:
            await self._repo.update_page(page, {"status": "archived"})
            logger.info("kb_page_archived", slug=slug)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search_pages(
        self,
        query: str,
        folder: str | None = None,
        status: str = "published",
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[KBSearchResultItem], int]:
        """Full-text search via PostgreSQL tsvector. Returns (results, total)."""
        pages, total = await self._repo.full_text_search(
            query=query,
            folder=folder,
            status=status,
            page=page,
            page_size=page_size,
        )
        results = [
            KBSearchResultItem(
                slug=p.slug,
                title=p.title,
                folder=p.folder,
                summary=p.body[:200] if p.body else "",
                inject_scope=p.inject_scope,
                sync_source=p.sync_source.get("type") if p.sync_source else None,
                updated_at=p.updated_at,
            )
            for p in pages
        ]
        return results, total

    # ------------------------------------------------------------------
    # Folders
    # ------------------------------------------------------------------

    async def get_folders(self) -> list[KBFolderNode]:
        """Derive folder hierarchy from distinct folder paths of published pages."""
        from sqlalchemy import func, select

        stmt = (
            select(KnowledgeBasePage.folder, func.count().label("cnt"))
            .where(KnowledgeBasePage.status == "published")
            .group_by(KnowledgeBasePage.folder)
        )
        result = await self._db.execute(stmt)
        rows = result.all()
        folder_counts = [(row.folder, row.cnt) for row in rows]
        return _build_folder_tree(folder_counts)

    # ------------------------------------------------------------------
    # Revisions
    # ------------------------------------------------------------------

    async def get_revisions(
        self,
        slug: str,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[KBPageRevisionResponse], int]:
        """Return paginated revision history for a page."""
        kb_page = await self._repo.get_by_slug(slug)
        if kb_page is None:
            raise CalsetaException(
                status_code=404,
                code="kb_page_not_found",
                message=f"KB page '{slug}' not found",
            )
        revisions, total = await self._repo.get_revisions(
            kb_page.id, page=page, page_size=page_size
        )
        return [_build_revision_response(r) for r in revisions], total

    async def get_revision(self, slug: str, revision_number: int) -> KBPageRevisionResponse:
        """Fetch a specific revision of a page."""
        kb_page = await self._repo.get_by_slug(slug)
        if kb_page is None:
            raise CalsetaException(
                status_code=404,
                code="kb_page_not_found",
                message=f"KB page '{slug}' not found",
            )
        revision = await self._repo.get_revision(kb_page.id, revision_number)
        if revision is None:
            raise CalsetaException(
                status_code=404,
                code="kb_revision_not_found",
                message=f"Revision {revision_number} not found for page '{slug}'",
            )
        return _build_revision_response(revision)

    # ------------------------------------------------------------------
    # Links
    # ------------------------------------------------------------------

    async def link_page(self, slug: str, link: KBPageLinkCreate) -> KBPageLinkResponse:
        """Create a link from a page to another entity."""
        kb_page = await self._repo.get_by_slug(slug)
        if kb_page is None:
            raise CalsetaException(
                status_code=404,
                code="kb_page_not_found",
                message=f"KB page '{slug}' not found",
            )

        try:
            db_link = await self._repo.create_link(
                page_id=kb_page.id,
                linked_entity_type=link.linked_entity_type,
                linked_entity_id=link.linked_entity_id,
                link_type=link.link_type,
            )
        except Exception as exc:
            # Unique constraint violation — duplicate link
            err_str = str(exc).lower()
            if "unique" in err_str or "duplicate" in err_str:
                raise CalsetaException(
                    status_code=409,
                    code="link_conflict",
                    message="A link to this entity already exists for this page",
                ) from exc
            raise

        logger.info(
            "kb_page_linked",
            slug=slug,
            entity_type=link.linked_entity_type,
            entity_id=str(link.linked_entity_id),
        )
        return _build_link_response(db_link)

    # ------------------------------------------------------------------
    # Sync
    # ------------------------------------------------------------------

    async def sync_page(
        self,
        slug: str,
        secret_resolver: object | None = None,
    ) -> KBSyncResult:
        """Fetch from the configured external sync_source and update if content changed."""
        page = await self._repo.get_by_slug(slug)
        if page is None:
            raise CalsetaException(
                status_code=404,
                code="kb_page_not_found",
                message=f"KB page '{slug}' not found",
            )
        if not page.sync_source:
            raise CalsetaException(
                status_code=400,
                code="not_syncable",
                message=f"KB page '{slug}' has no sync_source configured",
            )

        sync_type = page.sync_source.get("type", "")
        provider = get_sync_provider(sync_type)
        if provider is None:
            return KBSyncResult(
                slug=slug,
                outcome="config_invalid",
                error_message=f"Unknown sync provider type: '{sync_type}'",
            )

        validation_errors = provider.validate_config(page.sync_source)
        if validation_errors:
            return KBSyncResult(
                slug=slug,
                outcome="config_invalid",
                error_message="; ".join(validation_errors),
            )

        result = await provider.fetch(page.sync_source, secret_resolver)

        if result.outcome in ("fetch_failed", "config_invalid"):
            # Record sync error on the page without overwriting content
            await self._repo.update_page(page, {"status": "sync_error"})
            logger.warning(
                "kb_sync_failed",
                slug=slug,
                outcome=result.outcome,
                error=result.error_message,
            )
            return KBSyncResult(
                slug=slug,
                outcome=result.outcome,
                error_message=result.error_message,
            )

        # No content change
        if result.content_hash == page.sync_last_hash:
            await self._repo.update_page(page, {"synced_at": datetime.now(UTC)})
            logger.debug("kb_sync_no_change", slug=slug)
            return KBSyncResult(slug=slug, outcome="no_change")

        old_hash = page.sync_last_hash
        updated = await self._repo.update_page(
            page,
            {
                "body": result.content,
                "sync_last_hash": result.content_hash,
                "synced_at": datetime.now(UTC),
                "status": "published",
            },
            change_summary=f"Synced from {sync_type}",
            sync_source_ref=result.sync_source_ref,
        )

        logger.info(
            "kb_sync_updated",
            slug=slug,
            old_hash=old_hash,
            new_hash=result.content_hash,
            revision=updated.latest_revision_number,
        )
        return KBSyncResult(
            slug=slug,
            outcome="updated",
            old_hash=old_hash,
            new_hash=result.content_hash,
        )

    async def sync_all_pages(
        self,
        secret_resolver: object | None = None,
    ) -> list[KBSyncResult]:
        """Run sync_page for all pages that have a sync_source configured."""
        pages = await self._repo.get_pages_for_sync()
        results: list[KBSyncResult] = []
        for page in pages:
            try:
                result = await self.sync_page(page.slug, secret_resolver=secret_resolver)
                results.append(result)
            except CalsetaException as exc:
                results.append(
                    KBSyncResult(
                        slug=page.slug,
                        outcome="fetch_failed",
                        error_message=exc.message,
                    )
                )
            except Exception as exc:
                results.append(
                    KBSyncResult(
                        slug=page.slug,
                        outcome="fetch_failed",
                        error_message=str(exc),
                    )
                )
        return results

    # ------------------------------------------------------------------
    # Context injection (Layer 3)
    # ------------------------------------------------------------------

    async def resolve_kb_context(
        self,
        agent_uuid: str,
        agent_role: str | None,
        context_window_size: int = 200000,
        budget_pct: float = 0.15,
    ) -> list[KBPageResponse]:
        """Return published pages to inject into the agent prompt.

        Budget enforcement:
          - Pinned pages (inject_pinned=True) are always included regardless of budget.
          - Non-pinned pages are included in order (inject_priority DESC, updated_at DESC)
            until the token budget is exhausted.
          - Token estimate: page.token_count if set, else len(page.body) // 4.
        """
        pages = await self._repo.get_injectable_pages(agent_uuid, agent_role)
        budget = int(context_window_size * budget_pct)
        selected: list[KBPageResponse] = []
        total_tokens = 0

        for page in pages:
            token_estimate = (
                page.token_count if page.token_count is not None else len(page.body) // 4
            )
            if page.inject_pinned or total_tokens + token_estimate <= budget:
                await self._db.refresh(page, ["links"])
                selected.append(_build_page_response(page))
                if not page.inject_pinned:
                    total_tokens += token_estimate

        return selected


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------


_VALID_KB_STATUSES = {"published", "draft", "archived"}


def _validate_kb_status(status: str) -> None:
    if status not in _VALID_KB_STATUSES:
        raise CalsetaException(
            status_code=422,
            code="invalid_kb_status",
            message=(
                f"Invalid KB page status '{status}'. "
                f"Must be one of: {sorted(_VALID_KB_STATUSES)}"
            ),
        )
