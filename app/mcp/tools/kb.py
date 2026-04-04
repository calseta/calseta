"""MCP tools for the Knowledge Base system.

Tools:
  - create_kb_page   — Create a new KB page (agents:write)
  - update_kb_page   — Update an existing KB page body (agents:write)
  - search_kb        — Full-text search KB pages (agents:read)
  - get_kb_page      — Read a KB page by slug (agents:read)
  - link_kb_page     — Link a KB page to an entity (agents:write)
"""

from __future__ import annotations

import json
import re
import uuid as _uuid
from datetime import datetime

import structlog
from mcp.server.fastmcp import Context

from app.db.session import AsyncSessionLocal
from app.mcp.scope import check_scope
from app.mcp.server import mcp_server

logger = structlog.get_logger(__name__)


def _json_serial(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _slug_from_title(title: str) -> str:
    """Generate a URL-friendly slug from a title string."""
    slug = re.sub(r"[^a-z0-9-]", "-", title.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")[:100]
    # Ensure the slug is non-empty after sanitization
    if not slug:
        slug = "page"
    return slug


@mcp_server.tool()
async def create_kb_page(
    title: str,
    body: str,
    ctx: Context,
    slug: str | None = None,
    folder: str = "/",
    inject_scope: str | None = None,
) -> str:
    """Create a new KB page. Tier: managed.

    Args:
        title: Page title.
        body: Markdown content.
        slug: URL-friendly identifier (auto-generated from title if not provided).
        folder: Folder path (e.g., "/runbooks", "/policies"). Default: "/".
        inject_scope: JSON string for injection targeting. Examples:
                      '{"global": true}', '{"roles": ["triage"]}'. Default: None.

    Returns: JSON with created page slug and uuid.
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        from app.schemas.kb import KBPageCreate
        from app.services.kb_service import KBService

        # Auto-generate slug from title if not provided
        resolved_slug = slug if slug else _slug_from_title(title)

        # Parse inject_scope from JSON string if provided
        parsed_inject_scope: dict | None = None
        if inject_scope:
            try:
                parsed_inject_scope = json.loads(inject_scope)
            except json.JSONDecodeError:
                return json.dumps({"error": f"Invalid inject_scope JSON: {inject_scope}"})

        try:
            data = KBPageCreate(
                slug=resolved_slug,
                title=title,
                body=body,
                folder=folder,
                inject_scope=parsed_inject_scope,
            )
        except Exception as exc:
            return json.dumps({"error": f"Invalid page data: {exc}"})

        try:
            svc = KBService(session)
            page = await svc.create_page(data=data)
            await session.commit()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "uuid": str(page.uuid),
            "slug": page.slug,
            "title": page.title,
            "folder": page.folder,
            "status": page.status,
            "created_at": page.created_at.isoformat(),
        }, default=_json_serial)


@mcp_server.tool()
async def update_kb_page(
    slug: str,
    body: str,
    ctx: Context,
    change_summary: str | None = None,
) -> str:
    """Update an existing KB page body. Tier: managed.

    Args:
        slug: The page slug to update.
        body: New markdown content (full replacement).
        change_summary: Optional description of what changed.

    Returns: JSON with updated page metadata.
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        from app.schemas.kb import KBPagePatch
        from app.services.kb_service import KBService

        patch = KBPagePatch(body=body, change_summary=change_summary)

        try:
            svc = KBService(session)
            page = await svc.update_page(slug=slug, patch=patch)
            await session.commit()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "uuid": str(page.uuid),
            "slug": page.slug,
            "title": page.title,
            "folder": page.folder,
            "latest_revision_number": page.latest_revision_number,
            "updated_at": page.updated_at.isoformat(),
        }, default=_json_serial)


@mcp_server.tool()
async def search_kb(
    query: str,
    ctx: Context,
    folder: str | None = None,
    page_size: int = 10,
) -> str:
    """Search KB pages by keyword. Tier: safe.

    Args:
        query: Search query (full-text keyword search).
        folder: Optional folder path prefix to restrict search.
        page_size: Number of results to return (max 20).

    Returns: JSON list of matching pages with title, slug, folder, and summary.
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:read")
        if scope_err:
            return scope_err

        from app.services.kb_service import KBService

        page_size = min(page_size, 20)

        try:
            svc = KBService(session)
            results, total = await svc.search_pages(
                query=query,
                folder=folder,
                page_size=page_size,
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "results": [
                {
                    "slug": r.slug,
                    "title": r.title,
                    "folder": r.folder,
                    "summary": r.summary,
                    "inject_scope": r.inject_scope,
                    "updated_at": r.updated_at.isoformat(),
                }
                for r in results
            ],
            "total": total,
        }, default=_json_serial)


@mcp_server.tool()
async def get_kb_page(
    slug: str,
    ctx: Context,
) -> str:
    """Read a KB page by slug. Tier: safe.

    Args:
        slug: The page slug to retrieve.

    Returns: JSON with full page content (title, body, folder, inject_scope, updated_at).
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:read")
        if scope_err:
            return scope_err

        from app.services.kb_service import KBService

        try:
            svc = KBService(session)
            page = await svc.get_page(slug)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "uuid": str(page.uuid),
            "slug": page.slug,
            "title": page.title,
            "body": page.body,
            "folder": page.folder,
            "inject_scope": page.inject_scope,
            "status": page.status,
            "latest_revision_number": page.latest_revision_number,
            "updated_at": page.updated_at.isoformat(),
        }, default=_json_serial)


@mcp_server.tool()
async def link_kb_page(
    slug: str,
    linked_entity_type: str,
    linked_entity_id: str,
    link_type: str,
    ctx: Context,
) -> str:
    """Link a KB page to an alert, issue, agent, or other entity. Tier: managed.

    Args:
        slug: The KB page slug.
        linked_entity_type: One of: alert, issue, page, agent, campaign.
        linked_entity_id: UUID of the linked entity.
        link_type: One of: reference, source, generated_from, related.

    Returns: JSON with created link details.
    """
    try:
        parsed_entity_id = _uuid.UUID(linked_entity_id)
    except ValueError:
        return json.dumps({"error": f"Invalid linked_entity_id: {linked_entity_id}"})

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        from app.schemas.kb import KBPageLinkCreate
        from app.services.kb_service import KBService

        try:
            link_data = KBPageLinkCreate(
                linked_entity_type=linked_entity_type,  # type: ignore[arg-type]
                linked_entity_id=parsed_entity_id,
                link_type=link_type,  # type: ignore[arg-type]
            )
        except Exception as exc:
            return json.dumps({"error": f"Invalid link data: {exc}"})

        try:
            svc = KBService(session)
            link = await svc.link_page(slug=slug, link=link_data)
            await session.commit()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "uuid": str(link.uuid),
            "slug": slug,
            "linked_entity_type": link.linked_entity_type,
            "linked_entity_id": str(link.linked_entity_id),
            "link_type": link.link_type,
            "created_at": link.created_at.isoformat(),
        }, default=_json_serial)
