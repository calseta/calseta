"""
MCP resources for context documents.

Exposes context document data as MCP resources for AI agent consumption:
  - calseta://context-documents         — Document catalog (no content, token-efficient)
  - calseta://context-documents/{uuid}  — Full document with content and targeting rules
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import datetime

from mcp.server.fastmcp import Context

from app.db.session import AsyncSessionLocal
from app.mcp.scope import check_scope
from app.mcp.server import mcp_server
from app.repositories.context_document_repository import ContextDocumentRepository


def _json_serial(obj: object) -> str:
    """JSON serializer for objects not handled by default json encoder."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


@mcp_server.resource("calseta://context-documents")
async def list_context_documents(ctx: Context) -> str:
    """Context document catalog — title, type, description. No content (token efficiency)."""
    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "alerts:read")
        if scope_err:
            return scope_err

        repo = ContextDocumentRepository(session)
        docs, _total = await repo.list_documents(page=1, page_size=500)

        result = [
            {
                "uuid": str(doc.uuid),
                "title": doc.title,
                "document_type": doc.document_type,
                "is_global": doc.is_global,
                "description": doc.description,
                "tags": doc.tags,
                "version": doc.version,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
            }
            for doc in docs
        ]

        return json.dumps(
            {"context_documents": result, "count": len(result)},
            default=_json_serial,
        )


@mcp_server.resource("calseta://context-documents/{uuid}")
async def get_context_document(uuid: str, ctx: Context) -> str:
    """Full context document including content and targeting rules."""
    try:
        doc_uuid = _uuid.UUID(uuid)
    except ValueError as exc:
        raise ValueError(f"Invalid UUID: {uuid}") from exc

    async with AsyncSessionLocal() as session:
        scope_err = await check_scope(ctx, session, "alerts:read")
        if scope_err:
            return scope_err

        repo = ContextDocumentRepository(session)
        doc = await repo.get_by_uuid(doc_uuid)
        if doc is None:
            raise ValueError(f"Context document not found: {uuid}")

        result = {
            "uuid": str(doc.uuid),
            "title": doc.title,
            "document_type": doc.document_type,
            "is_global": doc.is_global,
            "description": doc.description,
            "content": doc.content,
            "tags": doc.tags,
            "targeting_rules": doc.targeting_rules,
            "version": doc.version,
            "created_at": doc.created_at.isoformat(),
            "updated_at": doc.updated_at.isoformat(),
        }

        return json.dumps(result, default=_json_serial)
