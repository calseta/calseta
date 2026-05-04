"""AgentService — write-path orchestration for agent registrations.

Responsibilities (Wave 5 / S13 scope):
    * Resolve ``capabilities.tools`` slugs to validated ``agent_tools.id``
      values and persist them as ``agent_registrations.tool_ids`` on every
      create/patch.
    * Hard-reject unknown slugs at the API boundary so operators get fast
      feedback (HTTP 422 ``UNKNOWN_TOOL_SLUG``). The lab seeder silently
      filters unknown slugs because lab specs may name aspirational tools;
      operator-driven writes do not enjoy that latitude.

Layered placement:
    Routes (``app/api/v1/agents.py``) → AgentService → AgentRepository.
    The service owns business logic (resolution + validation); the
    repository remains a thin DB adapter.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.db.models.agent_registration import AgentRegistration
from app.repositories.agent_repository import AgentRepository
from app.repositories.agent_tool_repository import AgentToolRepository
from app.schemas.agents import AgentRegistrationCreate, AgentRegistrationPatch

logger = structlog.get_logger(__name__)


class AgentService:
    """Write-path service for agent registrations.

    Read-path operations stay on ``AgentRepository`` directly — there is
    no business logic to add for reads. Routes are free to call the repo
    for GET handlers without going through this service.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._agent_repo = AgentRepository(db)
        self._tool_repo = AgentToolRepository(db)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create(
        self,
        data: AgentRegistrationCreate,
        auth_header_value_encrypted: str | None,
    ) -> AgentRegistration:
        """Create an agent. Validates and resolves capability tool slugs."""
        resolved_tool_ids = await self._resolve_capability_tool_ids(
            data.capabilities, fallback=data.tool_ids
        )
        if resolved_tool_ids is not None:
            # Pydantic models are immutable-by-default but assignment is allowed
            # unless ``model_config`` says otherwise. Use ``model_copy`` to be
            # safe against future hardening.
            data = data.model_copy(update={"tool_ids": resolved_tool_ids})
        return await self._agent_repo.create(data, auth_header_value_encrypted)

    async def patch(
        self,
        agent: AgentRegistration,
        body: AgentRegistrationPatch,
        updates: dict[str, Any],
    ) -> AgentRegistration:
        """Apply a patch. Resolves capability tool slugs if present.

        ``updates`` is the dict the route handler has already assembled
        (one entry per field the caller actually sent — pydantic ``None``
        sentinels filtered out by the route). The route passes it in so
        the service does not have to duplicate the field list.

        If ``body.capabilities`` is set with a ``tools`` key, we resolve
        the slugs and overwrite ``updates['tool_ids']`` with the result —
        capability-driven resolution wins over an explicit ``tool_ids``
        in the same patch. (Operators editing ``capabilities`` in the UI
        would be surprised if a stale ``tool_ids`` value silently
        overrode their declared capabilities.)
        """
        resolved_tool_ids = await self._resolve_capability_tool_ids(
            body.capabilities,
            fallback=body.tool_ids,
        )
        if resolved_tool_ids is not None:
            updates["tool_ids"] = resolved_tool_ids
        return await self._agent_repo.patch(agent, **updates)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _resolve_capability_tool_ids(
        self,
        capabilities: dict[str, Any] | None,
        *,
        fallback: list[str] | None,
    ) -> list[str] | None:
        """Resolve ``capabilities['tools']`` to validated tool IDs.

        Returns:
            * ``None`` when no resolution should happen (caller did not
              touch ``capabilities`` at all). The route should leave the
              existing ``tool_ids`` unchanged.
            * ``[]`` when ``capabilities`` is set but contains no tools.
              The route should overwrite ``tool_ids`` to ``[]`` so the
              database reflects the operator's stated intent.
            * a list of validated tool IDs otherwise.

        Raises:
            CalsetaException: 422 ``UNKNOWN_TOOL_SLUG`` if any slug in
                ``capabilities.tools`` does not exist in ``agent_tools``.

        ``fallback`` is the explicit ``tool_ids`` field the caller passed
        on the same request. It is only consulted when ``capabilities``
        is not provided — in that case there is nothing to resolve and we
        return ``None`` to preserve the route's existing behaviour
        (writing ``fallback`` directly).
        """
        if capabilities is None:
            return None
        if not isinstance(capabilities, dict):
            # Pydantic should already enforce this, but defensive — the
            # JSONB column will accept any JSON value and a buggy caller
            # could send a list/str.
            return None

        raw_tools = capabilities.get("tools")
        if raw_tools is None:
            # ``capabilities`` was set but ``tools`` was not — leave
            # tool_ids alone (return None). This lets operators edit
            # other capability fields without disturbing tools.
            #
            # Exception: if the caller also sent ``tool_ids`` explicitly,
            # honour that as the fallback by returning None and letting
            # the route write it.
            _ = fallback  # documentation aid; unused intentionally
            return None

        if not isinstance(raw_tools, list):
            raise CalsetaException(
                code="INVALID_CAPABILITIES",
                message=(
                    "capabilities.tools must be a list of tool slugs (strings); "
                    f"got {type(raw_tools).__name__}."
                ),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        # Coerce + de-duplicate while preserving order. Reject non-string
        # entries up front so the error message points at the bad input
        # rather than a downstream SQLAlchemy type error.
        seen: set[str] = set()
        slugs: list[str] = []
        for entry in raw_tools:
            if not isinstance(entry, str):
                raise CalsetaException(
                    code="INVALID_CAPABILITIES",
                    message=(
                        "capabilities.tools entries must be strings; "
                        f"got {type(entry).__name__}."
                    ),
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            if entry in seen:
                continue
            seen.add(entry)
            slugs.append(entry)

        if not slugs:
            return []

        existing_rows = await self._tool_repo.get_by_slugs(slugs)
        existing_ids = {row.id for row in existing_rows}
        unknown = [s for s in slugs if s not in existing_ids]
        if unknown:
            raise CalsetaException(
                code="UNKNOWN_TOOL_SLUG",
                message=(
                    "capabilities.tools references slugs that are not "
                    f"registered in agent_tools: {unknown}"
                ),
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                details={"unknown_slugs": list(unknown)},
            )

        # Preserve the operator's declared order — useful for UI display
        # and prompt construction.
        return [s for s in slugs if s in existing_ids]
