"""MCP tools for agent memory (KB pages in /memory/ folders).

Tools:
  - save_memory      — Store a memory entry in the calling agent's memory folder (agents:write)
  - recall_memory    — Search this agent's memories by keyword (agents:read)
  - update_memory    — Update an existing memory entry (agents:write)
  - promote_memory   — Promote private memory to shared (agents:write)
  - list_memories    — List this agent's memory entries (agents:read)
"""

from __future__ import annotations

import json
import re
import uuid as _uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from mcp.server.fastmcp import Context
from sqlalchemy import select

from app.db.models.agent_api_key import AgentAPIKey
from app.db.models.agent_registration import AgentRegistration
from app.db.session import AsyncSessionLocal
from app.mcp.scope import _resolve_client_id, check_scope
from app.mcp.server import mcp_server

logger = structlog.get_logger(__name__)


def _json_serial(obj: object) -> str:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def _resolve_calling_agent(
    ctx: Context, session: object
) -> tuple[AgentRegistration, AgentAPIKey] | str:
    """Resolve the calling agent from the MCP context.

    Returns the (AgentRegistration, AgentAPIKey) pair, or a JSON error string.
    """
    from sqlalchemy.ext.asyncio import AsyncSession

    db: AsyncSession = session  # type: ignore[assignment]

    client_id = _resolve_client_id(ctx)
    if not client_id:
        return json.dumps({"error": "Cannot resolve agent identity from context."})

    key_result = await db.execute(
        select(AgentAPIKey).where(AgentAPIKey.key_prefix == client_id)
    )
    agent_key = key_result.scalar_one_or_none()
    if agent_key is None:
        return json.dumps({"error": "Agent API key not found."})

    agent_result = await db.execute(
        select(AgentRegistration).where(
            AgentRegistration.id == agent_key.agent_registration_id
        )
    )
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        return json.dumps({"error": "Agent registration not found."})

    return agent, agent_key


def _make_memory_slug(title: str, agent_id: int) -> str:
    """Generate a deterministic memory slug from title and agent_id."""
    base = re.sub(r"[^a-z0-9-]", "-", title.lower())
    base = re.sub(r"-+", "-", base).strip("-")[:60]
    if not base:
        base = "memory"
    return f"{base}-{agent_id}"


def _is_stale(page: Any) -> bool:
    """Return True if a memory page is past its TTL."""
    metadata = getattr(page, "metadata_", None) or {}
    ttl_hours = metadata.get("staleness_ttl_hours")
    if ttl_hours is None:
        return False
    updated_at = getattr(page, "updated_at", None)
    if updated_at is None:
        return False
    cutoff = updated_at + timedelta(hours=float(ttl_hours))  # type: ignore[arg-type]
    return bool(datetime.now(UTC) > cutoff)


@mcp_server.tool()
async def save_memory(
    title: str,
    body: str,
    memory_type: str,
    ctx: Context,
    ttl_hours: int = 168,
    source_context: str | None = None,
) -> str:
    """Store a memory entry in this agent's private memory folder. Tier: managed.

    Args:
        title: Memory title (e.g., "User jsmith@corp.com Risk Profile").
        body: Markdown content of what to remember.
        memory_type: One of: entity_profile, codebase_map, investigation_summary,
                     pattern, preference.
        ttl_hours: Hours until this memory is considered stale (default: 168 = 7 days).
        source_context: Optional source hash for staleness tracking (e.g., git commit hash).

    Returns: JSON with created memory page slug and uuid.
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        agent_result = await _resolve_calling_agent(ctx, session)
        if isinstance(agent_result, str):
            return agent_result
        agent, _agent_key = agent_result

        from app.schemas.kb import KBPageCreate
        from app.services.kb_service import KBService

        slug = _make_memory_slug(title, agent.id)
        folder = f"/memory/agents/{agent.id}/"
        inject_scope: dict[str, Any] = {"agent_ids": [str(agent.uuid)]}
        metadata: dict[str, Any] = {
            "memory_type": memory_type,
            "staleness_ttl_hours": ttl_hours,
        }
        if source_context is not None:
            metadata["source_hash"] = source_context

        try:
            data = KBPageCreate(
                slug=slug,
                title=title,
                body=body,
                folder=folder,
                inject_scope=inject_scope,
                metadata=metadata,
            )
        except Exception as exc:
            return json.dumps({"error": f"Invalid memory data: {exc}"})

        try:
            svc = KBService(session)
            page = await svc.create_page(
                data=data,
                created_by_agent_uuid=agent.uuid,
            )
            await session.commit()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "uuid": str(page.uuid),
            "slug": page.slug,
            "title": page.title,
            "folder": page.folder,
            "memory_type": memory_type,
            "ttl_hours": ttl_hours,
            "created_at": page.created_at.isoformat(),
        }, default=_json_serial)


@mcp_server.tool()
async def recall_memory(
    query: str,
    ctx: Context,
    memory_type: str | None = None,
) -> str:
    """Search this agent's memory entries by keyword. Tier: safe.

    Args:
        query: Search query to find relevant memories.
        memory_type: Optional filter — one of: entity_profile, codebase_map,
                     investigation_summary, pattern, preference.

    Returns: JSON list of matching memory entries with title, body excerpt,
             staleness status, and updated_at.
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:read")
        if scope_err:
            return scope_err

        agent_result = await _resolve_calling_agent(ctx, session)
        if isinstance(agent_result, str):
            return agent_result
        agent, _agent_key = agent_result

        from app.services.kb_service import KBService

        folder = f"/memory/agents/{agent.id}/"

        try:
            svc = KBService(session)
            results, total = await svc.search_pages(
                query=query,
                folder=folder,
                page_size=20,
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        # Fetch full pages to check staleness and filter by memory_type
        from app.repositories.kb_repository import KBPageRepository

        repo = KBPageRepository(session)
        output = []
        for r in results:
            page = await repo.get_by_slug(r.slug)
            if page is None:
                continue
            page_metadata = getattr(page, "metadata_", None) or {}
            page_memory_type = page_metadata.get("memory_type")
            if memory_type is not None and page_memory_type != memory_type:
                continue
            stale = _is_stale(page)
            output.append({
                "slug": r.slug,
                "title": r.title,
                "summary": r.summary,
                "memory_type": page_memory_type,
                "is_stale": stale,
                "updated_at": r.updated_at.isoformat(),
            })

        return json.dumps({
            "memories": output,
            "total": len(output),
        }, default=_json_serial)


@mcp_server.tool()
async def update_memory(
    memory_slug: str,
    body: str,
    ctx: Context,
    change_summary: str | None = None,
    source_context: str | None = None,
) -> str:
    """Update an existing memory entry. Tier: managed.

    Args:
        memory_slug: Slug of the memory page to update.
        body: New markdown content.
        change_summary: What changed (e.g., "Updated after re-scan of codebase").
        source_context: New source hash for staleness tracking.

    Returns: JSON with updated memory metadata.
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        agent_result = await _resolve_calling_agent(ctx, session)
        if isinstance(agent_result, str):
            return agent_result
        agent, _agent_key = agent_result

        from app.repositories.kb_repository import KBPageRepository
        from app.schemas.kb import KBPagePatch
        from app.services.kb_service import KBService

        repo = KBPageRepository(session)
        page = await repo.get_by_slug(memory_slug)
        if page is None:
            return json.dumps({"error": f"Memory page '{memory_slug}' not found"})

        # Verify the calling agent owns this memory page
        expected_folder_prefix = f"/memory/agents/{agent.id}/"
        if not page.folder.startswith(expected_folder_prefix) and not page.folder.startswith(
            "/memory/shared/"
        ):
            return json.dumps({"error": "Access denied: memory page belongs to a different agent"})

        # Merge source_context into metadata if provided
        existing_metadata: dict[str, Any] = dict(getattr(page, "metadata_", None) or {})
        if source_context is not None:
            existing_metadata["source_hash"] = source_context

        patch = KBPagePatch(
            body=body,
            change_summary=change_summary,
            metadata=existing_metadata if existing_metadata else None,
        )

        try:
            svc = KBService(session)
            updated = await svc.update_page(
                slug=memory_slug,
                patch=patch,
                updated_by_agent_uuid=agent.uuid,
            )
            await session.commit()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        return json.dumps({
            "uuid": str(updated.uuid),
            "slug": updated.slug,
            "title": updated.title,
            "latest_revision_number": updated.latest_revision_number,
            "updated_at": updated.updated_at.isoformat(),
        }, default=_json_serial)


@mcp_server.tool()
async def promote_memory(
    memory_slug: str,
    ctx: Context,
    reason: str | None = None,
) -> str:
    """Promote a private memory to shared (visible to agents with same role). Tier: managed.

    Args:
        memory_slug: Slug of the memory page to promote.
        reason: Reason for promoting this memory (logged for audit).

    Returns: JSON with promotion result (status: promoted or pending_approval).
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:write")
        if scope_err:
            return scope_err

        agent_result = await _resolve_calling_agent(ctx, session)
        if isinstance(agent_result, str):
            return agent_result
        agent, _agent_key = agent_result

        from app.repositories.kb_repository import KBPageRepository
        from app.schemas.kb import KBPagePatch
        from app.services.kb_service import KBService

        repo = KBPageRepository(session)
        page = await repo.get_by_slug(memory_slug)
        if page is None:
            return json.dumps({"error": f"Memory page '{memory_slug}' not found"})

        expected_folder_prefix = f"/memory/agents/{agent.id}/"
        if not page.folder.startswith(expected_folder_prefix):
            return json.dumps({"error": "Access denied: can only promote your own memory pages"})

        if agent.memory_promotion_requires_approval:
            logger.info(
                "memory_promotion_pending_approval",
                slug=memory_slug,
                agent_id=agent.id,
                reason=reason,
            )
            return json.dumps({
                "status": "pending_approval",
                "message": "Memory promotion requires operator approval. Request has been logged.",
                "slug": memory_slug,
            })

        # Build inject_scope for shared memory
        if agent.role:
            new_inject_scope: dict[str, Any] = {"roles": [agent.role]}
        else:
            new_inject_scope = {"global": True}

        patch = KBPagePatch(
            folder="/memory/shared/",
            inject_scope=new_inject_scope,
            change_summary=(
                f"Promoted to shared by agent {agent.id}. "
                f"Reason: {reason or 'not specified'}"
            ),
        )

        try:
            svc = KBService(session)
            updated = await svc.update_page(
                slug=memory_slug,
                patch=patch,
                updated_by_agent_uuid=agent.uuid,
            )
            await session.commit()
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        logger.info(
            "memory_promoted_to_shared",
            slug=memory_slug,
            agent_id=agent.id,
            reason=reason,
        )
        return json.dumps({
            "status": "promoted",
            "slug": updated.slug,
            "folder": updated.folder,
            "inject_scope": updated.inject_scope,
            "updated_at": updated.updated_at.isoformat(),
        }, default=_json_serial)


@mcp_server.tool()
async def list_memories(
    ctx: Context,
    memory_type: str | None = None,
    include_stale: bool = False,
) -> str:
    """List this agent's memory entries. Tier: safe.

    Args:
        memory_type: Optional filter by memory type (entity_profile, codebase_map,
                     investigation_summary, pattern, preference).
        include_stale: Include stale memories in results (default: False).

    Returns: JSON list of memory entries with title, slug, memory_type, is_stale,
             and updated_at.
    """
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "agents:read")
        if scope_err:
            return scope_err

        agent_result = await _resolve_calling_agent(ctx, session)
        if isinstance(agent_result, str):
            return agent_result
        agent, _agent_key = agent_result

        from app.services.kb_service import KBService

        folder = f"/memory/agents/{agent.id}/"

        try:
            svc = KBService(session)
            pages, total = await svc.list_pages(
                folder=folder,
                page_size=200,
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)})

        from app.repositories.kb_repository import KBPageRepository

        repo = KBPageRepository(session)
        output = []
        for summary in pages:
            page = await repo.get_by_slug(summary.slug)
            if page is None:
                continue
            page_metadata = getattr(page, "metadata_", None) or {}
            page_memory_type = page_metadata.get("memory_type")

            if memory_type is not None and page_memory_type != memory_type:
                continue

            stale = _is_stale(page)
            if stale and not include_stale:
                continue

            output.append({
                "slug": summary.slug,
                "title": summary.title,
                "memory_type": page_memory_type,
                "is_stale": stale,
                "updated_at": summary.updated_at.isoformat(),
            })

        return json.dumps({
            "memories": output,
            "total": len(output),
        }, default=_json_serial)
