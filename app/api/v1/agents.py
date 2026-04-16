"""
Agent registration management routes.

GET    /v1/agents                          — List all agent registrations (filterable)
POST   /v1/agents                          — Create an agent registration
GET    /v1/agents/{uuid}                   — Get one agent registration
PATCH  /v1/agents/{uuid}                   — Update an agent registration
DELETE /v1/agents/{uuid}                   — Delete an agent registration (204)
POST   /v1/agents/{uuid}/test              — Test webhook delivery
POST   /v1/agents/{uuid}/pause             — Pause an agent (status → paused)
POST   /v1/agents/{uuid}/resume            — Resume a paused agent (status → active)
POST   /v1/agents/{uuid}/terminate         — Terminate an agent (irreversible, status → terminated)
GET    /v1/agents/{uuid}/capabilities      — Return capabilities JSONB
POST   /v1/agents/{uuid}/keys              — Create a new agent API key (cak_*)
DELETE /v1/agents/{uuid}/keys/{key_id}     — Revoke an agent API key
"""

from __future__ import annotations

import os
import secrets
import time
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import bcrypt
import httpx
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.api.errors import CalsetaException
from app.api.pagination import PaginationParams
from app.auth.base import AuthContext
from app.auth.dependencies import require_scope
from app.auth.scopes import Scope
from app.config import settings
from app.db.session import get_db
from app.middleware.rate_limit import limiter
from app.repositories.agent_api_key_repository import AgentAPIKeyRepository
from app.repositories.agent_repository import AgentRepository
from app.schemas.agent_invocations import AgentCatalogEntry
from app.schemas.agents import (
    AgentBudgetUpdate,
    AgentKeyCreate,
    AgentKeyCreatedResponse,
    AgentPauseRequest,
    AgentRegistrationCreate,
    AgentRegistrationPatch,
    AgentRegistrationResponse,
    AgentTestResponse,
)
from app.schemas.common import DataResponse, PaginatedResponse, PaginationMeta
from app.services.url_validation import is_safe_outbound_url

router = APIRouter(prefix="/agents", tags=["agents"])

_Read = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_READ))]
_Write = Annotated[AuthContext, Depends(require_scope(Scope.AGENTS_WRITE))]

_KEY_PREFIX_LEN = 8


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
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_agents(
    request: Request,
    auth: _Read,
    pagination: Annotated[PaginationParams, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(None, alias="status"),
    agent_type: str | None = Query(None),
    role: str | None = Query(None),
) -> PaginatedResponse[AgentRegistrationResponse]:
    repo = AgentRepository(db)
    if status_filter is not None or agent_type is not None or role is not None:
        agents, total = await repo.list_filtered(
            status=status_filter,
            agent_type=agent_type,
            role=role,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    else:
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
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_agent(
    request: Request,
    body: AgentRegistrationCreate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentRegistrationResponse]:
    # SSRF protection — only validate endpoint_url when provided (managed agents may omit it)
    if body.endpoint_url is not None:
        safe, reason = is_safe_outbound_url(body.endpoint_url)
        if not safe:
            raise CalsetaException(
                code="INVALID_ENDPOINT_URL",
                message=f"endpoint_url blocked by SSRF protection: {reason}",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    auth_header_value_encrypted: str | None = None
    if body.auth_header_value is not None:
        auth_header_value_encrypted = _maybe_encrypt(body.auth_header_value)

    repo = AgentRepository(db)
    agent = await repo.create(body, auth_header_value_encrypted)

    # Create agent home directory: $CALSETA_DATA_DIR/agents/{agent.uuid}/
    agent_home = os.path.join(settings.CALSETA_DATA_DIR, "agents", str(agent.uuid))
    os.makedirs(agent_home, exist_ok=True)

    return DataResponse(data=AgentRegistrationResponse.model_validate(agent))


# ---------------------------------------------------------------------------
# GET /v1/agents/catalog
# ---------------------------------------------------------------------------
# MUST be registered before /{agent_uuid} — FastAPI matches routes in order
# and "catalog" would otherwise be parsed as a UUID parameter (→ 422).


@router.get("/catalog", response_model=DataResponse[list[AgentCatalogEntry]])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_agent_catalog(
    request: Request,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[list[AgentCatalogEntry]]:
    """Return all active specialist agents available for delegation.

    Used by orchestrators to discover sub-agents and inject their
    capabilities into LLM context before planning delegation.
    """
    from app.services.invocation_service import InvocationService

    svc = InvocationService(db)
    catalog = await svc.get_catalog()
    return DataResponse(data=catalog)


# ---------------------------------------------------------------------------
# GET /v1/agents/{uuid}
# ---------------------------------------------------------------------------


@router.get("/{agent_uuid}", response_model=DataResponse[AgentRegistrationResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_agent(
    request: Request,
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
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_agent(
    request: Request,
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

    # SSRF protection — reject private/internal endpoint URLs on update
    if body.endpoint_url is not None:
        safe, reason = is_safe_outbound_url(body.endpoint_url)
        if not safe:
            raise CalsetaException(
                code="INVALID_ENDPOINT_URL",
                message=f"endpoint_url blocked by SSRF protection: {reason}",
                status_code=status.HTTP_400_BAD_REQUEST,
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
    if body.documentation is not None:
        updates["documentation"] = body.documentation
    # --- Control plane fields ---
    if body.execution_mode is not None:
        updates["execution_mode"] = body.execution_mode
    if body.agent_type is not None:
        updates["agent_type"] = body.agent_type
    if body.role is not None:
        updates["role"] = body.role
    if body.capabilities is not None:
        updates["capabilities"] = body.capabilities
    if body.adapter_type is not None:
        updates["adapter_type"] = body.adapter_type
    if body.adapter_config is not None:
        updates["adapter_config"] = body.adapter_config
    if body.llm_integration_id is not None:
        updates["llm_integration_id"] = body.llm_integration_id
    if body.system_prompt is not None:
        updates["system_prompt"] = body.system_prompt
    if body.methodology is not None:
        updates["methodology"] = body.methodology
    if body.tool_ids is not None:
        updates["tool_ids"] = body.tool_ids
    if body.max_tokens is not None:
        updates["max_tokens"] = body.max_tokens
    if body.enable_thinking is not None:
        updates["enable_thinking"] = body.enable_thinking
    if body.instruction_files is not None:
        updates["instruction_files"] = body.instruction_files
    if body.sub_agent_ids is not None:
        updates["sub_agent_ids"] = body.sub_agent_ids
    if body.max_sub_agent_calls is not None:
        updates["max_sub_agent_calls"] = body.max_sub_agent_calls
    if body.budget_monthly_cents is not None:
        updates["budget_monthly_cents"] = body.budget_monthly_cents
    if body.max_concurrent_alerts is not None:
        updates["max_concurrent_alerts"] = body.max_concurrent_alerts
    if body.max_cost_per_alert_cents is not None:
        updates["max_cost_per_alert_cents"] = body.max_cost_per_alert_cents
    if body.max_investigation_minutes is not None:
        updates["max_investigation_minutes"] = body.max_investigation_minutes
    if body.stall_threshold is not None:
        updates["stall_threshold"] = body.stall_threshold
    if body.memory_promotion_requires_approval is not None:
        updates["memory_promotion_requires_approval"] = body.memory_promotion_requires_approval

    updated = await repo.patch(agent, **updates)
    return DataResponse(data=AgentRegistrationResponse.model_validate(updated))


# ---------------------------------------------------------------------------
# GET /v1/agents/{uuid}/files              — List agent instruction files
# GET /v1/agents/{uuid}/files/{file_path}  — Read an agent instruction file
# PUT /v1/agents/{uuid}/files/{file_path}  — Save an agent instruction file
# ---------------------------------------------------------------------------

_ALLOWED_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json"}


def _resolve_agent_file_path(agent_uuid: str, file_path: str) -> tuple[str, str]:
    """Return (base_dir, resolved_abs_path). Raises CalsetaException on traversal."""
    base_dir = os.path.realpath(os.path.join(settings.AGENT_FILES_DIR, agent_uuid))
    abs_path = os.path.realpath(os.path.join(base_dir, file_path))
    if not abs_path.startswith(base_dir + os.sep) and abs_path != base_dir:
        raise CalsetaException(status_code=400, code="INVALID_PATH", message="Invalid file path")
    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise CalsetaException(
            status_code=400,
            code="INVALID_EXTENSION",
            message=f"File extension not allowed. Allowed: {', '.join(_ALLOWED_EXTENSIONS)}",
        )
    return base_dir, abs_path


@router.get("/{uuid}/files")
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def list_agent_files(
    request: Request,
    uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[list[dict]]:
    repo = AgentRepository(db)
    agent = await repo.get_by_uuid(uuid)
    if agent is None:
        raise CalsetaException(status_code=404, code="NOT_FOUND", message="Agent not found")

    base_dir = os.path.realpath(os.path.join(settings.AGENT_FILES_DIR, str(uuid)))
    files: list[dict] = []
    if os.path.isdir(base_dir):
        for root, dirs, filenames in os.walk(base_dir):
            # Skip the skills/ subdirectory — managed by the runtime, not by users
            dirs[:] = [d for d in dirs if d != "skills"]
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in _ALLOWED_EXTENSIONS:
                    continue
                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, base_dir)
                with open(abs_path) as f:
                    content = f.read()
                files.append({"name": rel_path, "content": content})
    files.sort(key=lambda f: f["name"])
    return DataResponse(data=files)


@router.get("/{uuid}/files/{file_path:path}")
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_agent_file(
    request: Request,
    uuid: UUID,
    file_path: str,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[dict]:
    repo = AgentRepository(db)
    agent = await repo.get_by_uuid(uuid)
    if agent is None:
        raise CalsetaException(status_code=404, code="NOT_FOUND", message="Agent not found")

    _, abs_path = _resolve_agent_file_path(str(uuid), file_path)
    if not os.path.isfile(abs_path):
        raise CalsetaException(status_code=404, code="NOT_FOUND", message="File not found")

    with open(abs_path) as f:
        content = f.read()
    return DataResponse(data={"path": file_path, "content": content})


@router.put("/{uuid}/files/{file_path:path}")
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def save_agent_file(
    request: Request,
    uuid: UUID,
    file_path: str,
    body: dict,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[dict]:
    repo = AgentRepository(db)
    agent = await repo.get_by_uuid(uuid)
    if agent is None:
        raise CalsetaException(status_code=404, code="NOT_FOUND", message="Agent not found")

    base_dir, abs_path = _resolve_agent_file_path(str(uuid), file_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    content = body.get("content", "")
    with open(abs_path, "w") as f:
        f.write(content)
    return DataResponse(data={"path": file_path, "content": content})


# ---------------------------------------------------------------------------
# DELETE /v1/agents/{uuid}
# ---------------------------------------------------------------------------


@router.delete("/{agent_uuid}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def delete_agent(
    request: Request,
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
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def test_agent_webhook(
    request: Request,
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

    if agent.endpoint_url is None:
        raise CalsetaException(
            code="NO_ENDPOINT_URL",
            message=(
                "Agent has no endpoint_url configured. "
                "Managed agents cannot be tested via webhook."
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
        "workflows": [],
        "calseta_api_base_url": settings.CALSETA_API_BASE_URL,
        "_metadata": {
            "generated_at": now.isoformat(),
            "alert_source": agent.name,
            "indicator_count": 0,
            "enrichment": {"succeeded": [], "failed": [], "enriched_at": None},
            "detection_rule_matched": False,
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


# ---------------------------------------------------------------------------
# POST /v1/agents/{uuid}/pause
# ---------------------------------------------------------------------------


@router.post("/{agent_uuid}/pause", response_model=DataResponse[AgentRegistrationResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def pause_agent(
    request: Request,
    agent_uuid: UUID,
    body: AgentPauseRequest,
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
    if agent.status == "terminated":
        raise CalsetaException(
            code="AGENT_TERMINATED",
            message="Terminated agents cannot be paused.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    updated = await repo.patch(agent, status="paused")
    return DataResponse(data=AgentRegistrationResponse.model_validate(updated))


# ---------------------------------------------------------------------------
# POST /v1/agents/{uuid}/resume
# ---------------------------------------------------------------------------


@router.post("/{agent_uuid}/resume", response_model=DataResponse[AgentRegistrationResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def resume_agent(
    request: Request,
    agent_uuid: UUID,
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
    if agent.status != "paused":
        raise CalsetaException(
            code="AGENT_NOT_PAUSED",
            message=(
                f"Agent is not paused (current status: {agent.status}). "
                "Only paused agents can be resumed."
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    updated = await repo.patch(agent, status="active")
    return DataResponse(data=AgentRegistrationResponse.model_validate(updated))


# ---------------------------------------------------------------------------
# POST /v1/agents/{uuid}/terminate
# ---------------------------------------------------------------------------


@router.post("/{agent_uuid}/terminate", response_model=DataResponse[AgentRegistrationResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def terminate_agent(
    request: Request,
    agent_uuid: UUID,
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
    if agent.status == "terminated":
        # Idempotent — already terminated
        return DataResponse(data=AgentRegistrationResponse.model_validate(agent))
    updated = await repo.patch(agent, status="terminated")
    return DataResponse(data=AgentRegistrationResponse.model_validate(updated))


# ---------------------------------------------------------------------------
# GET /v1/agents/{uuid}/capabilities
# ---------------------------------------------------------------------------


@router.get("/{agent_uuid}/capabilities", response_model=DataResponse[dict])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def get_agent_capabilities(
    request: Request,
    agent_uuid: UUID,
    auth: _Read,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[dict]:
    repo = AgentRepository(db)
    agent = await repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return DataResponse(data=agent.capabilities or {})


# ---------------------------------------------------------------------------
# POST /v1/agents/{uuid}/keys
# ---------------------------------------------------------------------------


@router.post(
    "/{agent_uuid}/keys",
    response_model=DataResponse[AgentKeyCreatedResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def create_agent_key(
    request: Request,
    agent_uuid: UUID,
    body: AgentKeyCreate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentKeyCreatedResponse]:
    repo = AgentRepository(db)
    agent = await repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # Generate key with cak_ prefix (distinct from human cai_ keys)
    plain_key = "cak_" + secrets.token_urlsafe(32)
    key_prefix = plain_key[:_KEY_PREFIX_LEN]
    key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt(rounds=12)).decode()

    # Agents get a full scope set by default; callers can manage via PATCH if needed
    default_scopes = [
        Scope.ALERTS_READ,
        Scope.ALERTS_WRITE,
        Scope.WORKFLOWS_EXECUTE,
        Scope.ENRICHMENTS_READ,
        Scope.AGENTS_READ,
    ]

    key_repo = AgentAPIKeyRepository(db)
    record = await key_repo.create(
        agent_id=agent.id,
        name=body.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=[str(s) for s in default_scopes],
    )

    return DataResponse(
        data=AgentKeyCreatedResponse(
            uuid=record.uuid,
            name=record.name,
            key_prefix=record.key_prefix,
            scopes=list(record.scopes),
            last_used_at=record.last_used_at,
            revoked_at=record.revoked_at,
            created_at=record.created_at,
            key=plain_key,  # shown ONCE
        )
    )


# ---------------------------------------------------------------------------
# DELETE /v1/agents/{uuid}/keys/{key_id}
# ---------------------------------------------------------------------------


@router.delete("/{agent_uuid}/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def revoke_agent_key(
    request: Request,
    agent_uuid: UUID,
    key_id: UUID,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    agent_repo = AgentRepository(db)
    agent = await agent_repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    key_repo = AgentAPIKeyRepository(db)
    record = await key_repo.get_by_uuid_for_agent(agent.id, key_id)
    if record is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent API key not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    await key_repo.revoke(record)


# ---------------------------------------------------------------------------
# PATCH /v1/agents/{uuid}/budget
# ---------------------------------------------------------------------------


@router.patch("/{agent_uuid}/budget", response_model=DataResponse[AgentRegistrationResponse])
@limiter.limit(f"{settings.RATE_LIMIT_AUTHED_PER_MINUTE}/minute")
async def patch_agent_budget(
    request: Request,
    agent_uuid: UUID,
    body: AgentBudgetUpdate,
    auth: _Write,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DataResponse[AgentRegistrationResponse]:
    """Update agent monthly budget. Optionally resets spent_monthly_cents and period_start."""
    repo = AgentRepository(db)
    agent = await repo.get_by_uuid(agent_uuid)
    if agent is None:
        raise CalsetaException(
            code="NOT_FOUND",
            message="Agent not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    updates: dict[str, object] = {"budget_monthly_cents": body.budget_monthly_cents}

    if body.reset_spent:
        from app.services.cost_service import CostService

        svc = CostService(db)
        await svc.reset_monthly_budget(agent)
        # After reset, refresh agent and still apply budget_monthly_cents update
        await db.refresh(agent)

    updated = await repo.patch(agent, **updates)
    return DataResponse(data=AgentRegistrationResponse.model_validate(updated))
