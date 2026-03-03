"""Context document repository — all DB reads/writes for context_documents."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.context_document import ContextDocument

# Whitelist of columns that can be used for sorting
_SORT_COLUMNS: dict[str, str] = {
    "title": "title",
    "document_type": "document_type",
    "updated_at": "updated_at",
    "created_at": "created_at",
}


class ContextDocumentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        title: str,
        document_type: str,
        content: str,
        *,
        is_global: bool = False,
        description: str | None = None,
        tags: list[str] | None = None,
        targeting_rules: dict[str, Any] | None = None,
    ) -> ContextDocument:
        doc = ContextDocument(
            uuid=uuid.uuid4(),
            title=title,
            document_type=document_type,
            content=content,
            is_global=is_global,
            description=description,
            tags=tags or [],
            targeting_rules=targeting_rules,
            version=1,
        )
        self._db.add(doc)
        await self._db.flush()
        await self._db.refresh(doc)
        return doc

    async def get_by_uuid(self, doc_uuid: uuid.UUID) -> ContextDocument | None:
        result = await self._db.execute(
            select(ContextDocument).where(ContextDocument.uuid == doc_uuid)
        )
        return result.scalar_one_or_none()

    async def list_documents(
        self,
        *,
        document_type: list[str] | str | None = None,
        is_global: bool | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ContextDocument], int]:
        from sqlalchemy import func

        stmt = select(ContextDocument)
        count_stmt = select(func.count()).select_from(ContextDocument)

        if document_type is not None:
            vals = document_type if isinstance(document_type, list) else [document_type]
            stmt = stmt.where(ContextDocument.document_type.in_(vals))
            count_stmt = count_stmt.where(ContextDocument.document_type.in_(vals))
        if is_global is not None:
            stmt = stmt.where(ContextDocument.is_global == is_global)
            count_stmt = count_stmt.where(ContextDocument.is_global == is_global)

        total_result = await self._db.execute(count_stmt)
        total = total_result.scalar_one()

        # Dynamic sort
        order_clause = None
        if sort_by and sort_by in _SORT_COLUMNS:
            col = getattr(ContextDocument, _SORT_COLUMNS[sort_by])
            order_clause = col.asc() if sort_order == "asc" else col.desc()

        if order_clause is None:
            order_clause = ContextDocument.created_at.desc()

        offset = (page - 1) * page_size
        stmt = stmt.order_by(order_clause).offset(offset).limit(page_size)
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def list_all_for_targeting(self) -> list[ContextDocument]:
        """Return all non-deleted documents for targeting rule evaluation."""
        result = await self._db.execute(
            select(ContextDocument).order_by(
                ContextDocument.is_global.desc(),
                ContextDocument.document_type.asc(),
            )
        )
        return list(result.scalars().all())

    async def patch(
        self,
        doc: ContextDocument,
        *,
        title: str | None = None,
        document_type: str | None = None,
        is_global: bool | None = None,
        description: str | None = None,
        content: str | None = None,
        tags: list[str] | None = None,
        targeting_rules: dict[str, Any] | None = None,
    ) -> ContextDocument:
        if title is not None:
            doc.title = title
        if document_type is not None:
            doc.document_type = document_type
        if is_global is not None:
            doc.is_global = is_global
        if description is not None:
            doc.description = description
        if content is not None:
            doc.content = content
            doc.version = doc.version + 1
        if tags is not None:
            doc.tags = tags
        if targeting_rules is not None:
            doc.targeting_rules = targeting_rules
        await self._db.flush()
        await self._db.refresh(doc)
        return doc

    async def delete(self, doc: ContextDocument) -> None:
        await self._db.delete(doc)
        await self._db.flush()
