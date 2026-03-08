"""
Agent registration management routes.

GET    /v1/agents                  — List all agent registrations
POST   /v1/agents                  — Create an agent registration
GET    /v1/agents/{uuid}           — Get one agent registration
PATCH  /v1/agents/{uuid}           — Update an agent registration
DELETE /v1/agents/{uuid}           — Delete an agent registration (204)
POST   /v1/agents/{uuid}/test      — Test webhook delivery (stub, 501)
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.repositories.agent_repository import AgentRepository
from app.schemas.agents import (
    AgentRegistrationCreate,
    AgentRegistrationPatch,
    AgentRegistrationResponse,
    AgentTestResponse,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta

router = APIRouter(prefix="/agents", tags=["agents"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]


def _maybe_encrypt(plaintext: str) -> str:
    """
    Encrypt a plaintext auth header value using Fernet.
    Raises CalsetaException(400) if ENCRYPTION_KEY is not configured.
    """
    if not settings.ENCRYPTION_KEY:
        raise CalsetaException(
            code="ENCRYPTION_NOT_CONFIGURED",
            message=(
                "ENCRYPTION_KEY is not set. Cannot store auth_header_value securely. "
                "Set ENCRYPTION_KEY in your environment and restart the service."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    from app.auth.encryption import encrypt_value

    try:
        return encrypt_value(plaintext)
    except ValueError as exc:
        raise CalsetaException(
            code="ENCRYPTION_NOT_CONFIGURED",
            message=str(exc),
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc


# ---------------------------------------------------------------------------
# GET /v1/agents
# ---------------------------------------------------------------------------


@router.get("", response_model=PaginatedResponse[AgentRegistrationResponse])
async def list_agents(
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaginatedResponse[AgentRegistrationResponse]:
    repo = AgentRepository(db)
    agents, total = await repo.list_all(page=pagination.page, page_size=pagination.page_size)
    return PaginatedResponse(
        data=[AgentRegistrationResponse.model_validate(a) for a in agents],
        meta=PaginationMeta.from_total(
            total=total, page=pagination.page, page_size=pagination.page_size
        ),
    )


# ---------------------------------------------------------------------------
# POST /v1/agents
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=DataResponse[AgentRegistrationResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_agent(
    body: AgentRegistrationCreate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentRegistrationResponse]:
    auth_header_value_encrypted: str | None = None
    if body.auth_header_value is not None:
        auth_header_value_encrypted = _maybe_encrypt(body.auth_header_value)

    repo = AgentRepository(db)
    agent = await repo.create(body, auth_header_value_encrypted)
    return DataResponse(data=AgentRegistrationResponse.model_validate(agent))


# ---------------------------------------------------------------------------
# GET /v1/agents/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{agent_uuid}", response_model=DataResponse[AgentRegistrationResponse])
async def get_agent(
    agent_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentRegistrationResponse]:
    repo = AgentRepository(db)
    agent = await repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=AgentRegistrationResponse.model_validate(agent))


# ---------------------------------------------------------------------------
# PATCH /v1/agents/{uuid}
# ---------------------------------------------------------------------------


@router.patch("/{agent_uuid}", response_model=DataResponse[AgentRegistrationResponse])
async def patch_agent(
    agent_uuid: UUID,
    body: AgentRegistrationPatch,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentRegistrationResponse]:
    repo = AgentRepository(db)
    agent = await repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    updates: dict[str, object] = {}

    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.endpoint_url is not None:
        updates["endpoint_url"] = body.endpoint_url
    if body.auth_header_name is not None:
        updates["auth_header_name"] = body.auth_header_name
    if body.auth_header_value is not None:
        updates["auth_header_value_encrypted"] = _maybe_encrypt(body.auth_header_value)
    if body.trigger_on_sources is not None:
        updates["trigger_on_sources"] = body.trigger_on_sources
    if body.trigger_on_severities is not None:
        updates["trigger_on_severities"] = body.trigger_on_severities
    if body.trigger_filter is not None:
        updates["trigger_filter"] = body.trigger_filter
    if body.timeout_seconds is not None:
        updates["timeout_seconds"] = body.timeout_seconds
    if body.retry_count is not None:
        updates["retry_count"] = body.retry_count
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.documentation is not None:
        updates["documentation"] = body.documentation

    updated = await repo.patch(agent, **updates)
    return DataResponse(data=AgentRegistrationResponse.model_validate(updated))


# ---------------------------------------------------------------------------
# DELETE /v1/agents/{uuid}
# ---------------------------------------------------------------------------


@router.delete("/{agent_uuid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = AgentRepository(db)
    agent = await repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    await repo.delete(agent)


# ---------------------------------------------------------------------------
# POST /v1/agents/{uuid}/test
# ---------------------------------------------------------------------------


@router.post("/{agent_uuid}/test", response_model=DataResponse[AgentTestResponse])
async def test_agent_webhook(
    agent_uuid: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentTestResponse]:
    repo = AgentRepository(db)
    agent = await repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    now = datetime.now(UTC)
    synthetic_payload = {
        "test": True,
        "alert": {
            "uuid": "00000000-0000-0000-0000-000000000000",
            "title": "Calseta — Test Webhook",
            "severity": "Low",
            "status": "Open",
            "source_name": agent.name,
            "occurred_at": now.isoformat(),
            "ingested_at": now.isoformat(),
            "is_enriched": False,
            "tags": ["test"],
        },
        "indicators": [],
        "detection_rule": None,
        "context_documents": [],
        "workflows": [],
        "calseta_api_base_url": settings.CALSETA_API_BASE_URL,
        "_metadata": {
            "generated_at": now.isoformat(),
            "alert_source": agent.name,
            "indicator_count": 0,
            "enrichment": {"succeeded": [], "failed": [], "enriched_at": None},
            "detection_rule_matched": False,
            "context_documents_applied": 0,
        },
    }

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if agent.auth_header_name and agent.auth_header_value_encrypted:
        try:
            from app.auth.encryption import decrypt_value

            decrypted = decrypt_value(agent.auth_header_value_encrypted)
            headers[agent.auth_header_name] = decrypted
        except ValueError:
            pass  # No ENCRYPTION_KEY — send without auth header

    started = time.monotonic()
    delivered = False
    status_code: int | None = None
    error: str | None = None

    try:
        async with httpx.AsyncClient(timeout=float(agent.timeout_seconds)) as client:
            response = await client.post(
                agent.endpoint_url,
                json=synthetic_payload,
                headers=headers,
            )
        status_code = response.status_code
        delivered = response.is_success
        if not delivered:
            error = f"HTTP {status_code}"
    except httpx.TimeoutException as exc:
        error = f"Timeout: {exc}"
    except httpx.RequestError as exc:
        error = f"Connection error: {exc}"

    duration_ms = int((time.monotonic() - started) * 1000)

    return DataResponse(
        data=AgentTestResponse(
            delivered=delivered,
            status_code=status_code,
            duration_ms=duration_ms,
            error=error,
        )
    )
