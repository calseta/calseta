"""
Context document management routes.

GET    /v1/context-documents            — Paginated list (no content field)
POST   /v1/context-documents            — Create document (JSON or multipart/form-data)
GET    /v1/context-documents/{uuid}     — Full document with content
PATCH  /v1/context-documents/{uuid}     — Partial update
DELETE /v1/context-documents/{uuid}     — Delete

POST supports two content types:
  application/json     → body must include "content" field
  multipart/form-data  → body must include "file" upload; other metadata as form fields

File upload converts the document to markdown via markitdown. Original file is not
persisted — only the converted markdown is stored.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.db.session import get_db
from app.repositories.context_document_repository import ContextDocumentRepository
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.schemas.context_documents import (
    DOCUMENT_TYPES,
    ContextDocumentCreate,
    ContextDocumentPatch,
    ContextDocumentResponse,
    ContextDocumentSummary,
    validate_targeting_rules,
)

router = APIRouter(prefix="/context-documents", tags=["context-documents"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.ALERTS_WRITE))]


def _to_summary(doc: object) -> ContextDocumentSummary:
    return ContextDocumentSummary.model_validate(doc)


def _to_response(doc: object) -> ContextDocumentResponse:
    return ContextDocumentResponse.model_validate(doc)


async def _convert_file_to_markdown(file_bytes: bytes, filename: str) -> str:
    """Convert uploaded file bytes to markdown. Raises CalsetaException on failure."""
    ext = Path(filename).suffix.lower() if filename else ""
    try:
        from markitdown import MarkItDown, StreamInfo

        md = MarkItDown()
        result = md.convert(
            io.BytesIO(file_bytes),
            stream_info=StreamInfo(extension=ext, filename=filename),
        )
        return result.text_content or ""
    except Exception as exc:
        raise CalsetaException(
            code="UNSUPPORTED_FORMAT",
            message=(
                f"Cannot convert uploaded file '{filename}' to markdown: {exc}. "
                "Supported formats: PDF, DOCX, PPTX, HTML, plain text, Markdown."
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from exc


async def _parse_create_from_form(request: Request) -> ContextDocumentCreate:
    """Parse a multipart/form-data request into ContextDocumentCreate."""
    form = await request.form()

    title = form.get("title")
    document_type = form.get("document_type")
    if not title or not document_type:
        raise CalsetaException(
            code="VALIDATION_ERROR",
            message="title and document_type are required form fields",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    is_global_raw = str(form.get("is_global", "false")).lower()
    is_global = is_global_raw in ("true", "1", "yes")

    description_raw = form.get("description")
    description = str(description_raw) if description_raw else None

    tags: list[str] = []
    tags_raw = form.get("tags")
    if tags_raw:
        raw_str = str(tags_raw).strip()
        # Try JSON array first, fall back to comma-separated string
        if raw_str.startswith("["):
            try:
                tags = json.loads(raw_str)
                if not isinstance(tags, list):
                    raise ValueError("tags must be an array")
            except (json.JSONDecodeError, ValueError) as exc:
                raise CalsetaException(
                    code="VALIDATION_ERROR",
                    message=f"tags field must be a JSON array or comma-separated string: {exc}",
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                ) from exc
        else:
            tags = [t.strip() for t in raw_str.split(",") if t.strip()]

    targeting_rules = None
    targeting_rules_raw = form.get("targeting_rules")
    if targeting_rules_raw:
        try:
            targeting_rules = json.loads(str(targeting_rules_raw))
        except json.JSONDecodeError as exc:
            raise CalsetaException(
                code="VALIDATION_ERROR",
                message=f"targeting_rules must be a JSON object: {exc}",
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            ) from exc
        errors = validate_targeting_rules(targeting_rules)
        if errors:
            raise CalsetaException(
                code="VALIDATION_ERROR",
                message="; ".join(errors),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

    file = form.get("file")
    if file is None or not hasattr(file, "read"):
        raise CalsetaException(
            code="VALIDATION_ERROR",
            message="file field is required for multipart/form-data uploads",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    file_bytes = await file.read()  # type: ignore[union-attr]
    filename = getattr(file, "filename", "upload") or "upload"
    content = await _convert_file_to_markdown(file_bytes, filename)

    return ContextDocumentCreate(
        title=str(title),
        document_type=str(document_type),
        is_global=is_global,
        description=description,
        content=content,
        tags=tags,
        targeting_rules=targeting_rules,
    )


# ---------------------------------------------------------------------------
# GET /v1/context-documents
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[ContextDocumentSummary])
async def list_context_documents(
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    document_type: str | None = Query(None),
    is_global: bool | None = Query(None),
) -> PaginatedResponse[ContextDocumentSummary]:
    repo = ContextDocumentRepository(db)
    docs, total = await repo.list_documents(
        document_type=document_type,
        is_global=is_global,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    return PaginatedResponse(
        data=[_to_summary(d) for d in docs],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# POST /v1/context-documents
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DataResponse[ContextDocumentResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_context_document(
    request: Request,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[ContextDocumentResponse]:
    """
    Create a context document.

    Accepts either:
    - `Content-Type: application/json` with body including `content` field
    - `Content-Type: multipart/form-data` with `file` upload and other metadata as form fields
    """
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        create_data = await _parse_create_from_form(request)
    else:
        body = await request.json()
        try:
            create_data = ContextDocumentCreate.model_validate(body)
        except Exception as exc:
            raise CalsetaException(
                code="VALIDATION_ERROR",
                message=str(exc),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            ) from exc

    # Validate document_type (already done by Pydantic validator on JSON path;
    # do it explicitly for the form path since we bypass Pydantic there)
    if create_data.document_type not in DOCUMENT_TYPES:
        raise CalsetaException(
            code="VALIDATION_ERROR",
            message=f"document_type must be one of: {sorted(DOCUMENT_TYPES)}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    repo = ContextDocumentRepository(db)
    doc = await repo.create(
        title=create_data.title,
        document_type=create_data.document_type,
        content=create_data.content,
        is_global=create_data.is_global,
        description=create_data.description,
        tags=create_data.tags,
        targeting_rules=create_data.targeting_rules,
    )
    return DataResponse(data=_to_response(doc))


# ---------------------------------------------------------------------------
# GET /v1/context-documents/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{doc_uuid}", response_model=DataResponse[ContextDocumentResponse])
async def get_context_document(
    doc_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[ContextDocumentResponse]:
    repo = ContextDocumentRepository(db)
    doc = await repo.get_by_uuid(doc_uuid)
    if doc is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Context document {doc_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=_to_response(doc))


# ---------------------------------------------------------------------------
# PATCH /v1/context-documents/{uuid}
# ---------------------------------------------------------------------------


@router.patch("/{doc_uuid}", response_model=DataResponse[ContextDocumentResponse])
async def patch_context_document(
    doc_uuid: UUID,
    body: ContextDocumentPatch,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[ContextDocumentResponse]:
    repo = ContextDocumentRepository(db)
    doc = await repo.get_by_uuid(doc_uuid)
    if doc is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Context document {doc_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    doc = await repo.patch(
        doc,
        title=body.title,
        document_type=body.document_type,
        is_global=body.is_global,
        description=body.description,
        content=body.content,
        tags=body.tags,
        targeting_rules=body.targeting_rules,
    )
    return DataResponse(data=_to_response(doc))


# ---------------------------------------------------------------------------
# DELETE /v1/context-documents/{uuid}
# ---------------------------------------------------------------------------


@router.delete("/{doc_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context_document(
    doc_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = ContextDocumentRepository(db)
    doc = await repo.get_by_uuid(doc_uuid)
    if doc is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message=f"Context document {doc_uuid} not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await repo.delete(doc)
