"""ToolDispatcher — routes managed agent tool calls to the correct handler.

Architecture:
  - Looks up tool by id from DB
  - Enforces tier permissions (forbidden → error, requires_approval → error)
  - Validates ``tool_input`` for write-tier tools through a Pydantic model
    registered in ``app/schemas/tool_inputs.py`` (S2 — tool output validation gate)
  - Dispatches safe/managed tools to handler_ref implementations
  - handler_ref format: "calseta:<operation>" for built-in tools

Built-in handler stubs return structured results.

Error contract (S2):
  - The dispatcher never raises out of ``dispatch()`` for input/handler issues.
    All failures are mapped to a coarse error code in the response dict so the
    LLM cannot exfiltrate stack traces, entity IDs, or secrets via ``str(exc)``.
  - The five coarse codes are: ``internal_error``, ``invalid_input``,
    ``forbidden``, ``rate_limited``, ``not_found``. Tier and assignment errors
    still raise typed exceptions (preserving existing engine behaviour); the
    engine-side mapper translates those into coarse codes too.
  - One additional response-level code, ``alert_scope_violation``, is emitted
    when the LLM tries to mutate an alert other than the one bound to its
    ``RuntimeContext``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from pydantic import ValidationError

from app.schemas.tool_inputs import (
    TOOL_INPUT_MODELS,
    PostFindingInput,
    UpdateAlertStatusInput,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.agent_registration import AgentRegistration
    from app.db.models.agent_tool import AgentTool
    from app.runtime.models import RuntimeContext

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Coarse error codes (S2)
# ---------------------------------------------------------------------------


class ToolErrorCode:
    """Coarse error codes returned to the LLM. Never include ``str(exc)``."""

    INTERNAL_ERROR = "internal_error"
    INVALID_INPUT = "invalid_input"
    FORBIDDEN = "forbidden"
    RATE_LIMITED = "rate_limited"
    NOT_FOUND = "not_found"
    ALERT_SCOPE_VIOLATION = "alert_scope_violation"


def _error_response(code: str, *, hint: str | None = None) -> dict[str, Any]:
    """Build the canonical error envelope returned to the LLM.

    ``hint`` is a fixed, human-curated string describing the error class — it
    must NEVER include exception messages or runtime data.
    """
    out: dict[str, Any] = {"status": "error", "error_code": code}
    if hint is not None:
        out["error"] = hint
    return out


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ToolForbiddenError(Exception):
    """Raised when a tool has tier='forbidden'."""

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(f"Tool '{tool_id}' is forbidden for this agent.")


class ToolRequiresApprovalError(Exception):
    """Raised when a tool has tier='requires_approval' and no pre-approved context."""

    def __init__(self, tool_id: str, tool: AgentTool) -> None:
        self.tool_id = tool_id
        self.tool = tool
        super().__init__(
            f"Tool '{tool_id}' requires human approval before execution."
        )


class ToolNotFoundError(Exception):
    """Raised when the requested tool does not exist in the registry."""

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(f"Tool '{tool_id}' not found in registry.")


class ToolNotAssignedError(Exception):
    """Raised when the agent attempts to call a tool not in its tool_ids list."""

    def __init__(self, tool_id: str) -> None:
        self.tool_id = tool_id
        super().__init__(
            f"Tool '{tool_id}' is not assigned to this agent. "
            "Update agent.tool_ids to grant access."
        )


# Mapping from typed dispatcher exceptions to coarse error codes.
# Used by the engine layer (``app/runtime/engine.py``) when wrapping dispatch
# failures into tool_result envelopes.
EXCEPTION_TO_ERROR_CODE: dict[type[Exception], str] = {
    ToolForbiddenError: ToolErrorCode.FORBIDDEN,
    ToolRequiresApprovalError: ToolErrorCode.FORBIDDEN,
    ToolNotFoundError: ToolErrorCode.NOT_FOUND,
    ToolNotAssignedError: ToolErrorCode.FORBIDDEN,
}


def map_exception_to_error_code(exc: BaseException) -> str:
    """Return a coarse error code for an exception. Default = internal_error."""
    for exc_type, code in EXCEPTION_TO_ERROR_CODE.items():
        if isinstance(exc, exc_type):
            return code
    if isinstance(exc, ValidationError):
        return ToolErrorCode.INVALID_INPUT
    return ToolErrorCode.INTERNAL_ERROR


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


class ToolDispatcher:
    """Routes managed agent tool calls to the correct handler.

    Enforces tier permissions, agent tool assignment, AND input validation
    before dispatch. Services are injected via constructor — no global
    singletons.

    The optional ``context`` argument carries the active ``RuntimeContext``.
    Write-tier handlers that mutate alert state use ``context.alert_id`` as the
    canonical target; any ``alert_uuid`` in ``tool_input`` is cross-checked but
    never trusted as the write target.
    """

    def __init__(
        self,
        db: AsyncSession,
        agent: AgentRegistration,
        context: RuntimeContext | None = None,
    ) -> None:
        self._db = db
        self._agent = agent
        self._context = context

    async def dispatch(
        self,
        tool_id: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a tool call.

        Steps:
          1. Look up tool by id in the registry
          2. Verify the tool is in agent.tool_ids
          3. Enforce tier: forbidden → ToolForbiddenError
          4. Enforce tier: requires_approval → ToolRequiresApprovalError
          5. Validate ``tool_input`` against the registered Pydantic model
             (write-tier tools only — read-tier tools pass raw dicts through)
          6. Execute via handler_ref for safe/managed tools
          7. Return result dict

        Raises:
          ToolNotFoundError       — tool does not exist
          ToolNotAssignedError    — agent does not have this tool
          ToolForbiddenError      — tier is 'forbidden'
          ToolRequiresApprovalError — tier is 'requires_approval'

        Validation failures (Pydantic ValidationError) and handler exceptions
        are caught and returned as coarse-coded error envelopes — they never
        propagate out of ``dispatch()``.
        """
        from app.repositories.agent_tool_repository import AgentToolRepository

        repo = AgentToolRepository(self._db)
        tool = await repo.get_by_id(tool_id)
        if tool is None:
            raise ToolNotFoundError(tool_id)

        # Check agent is assigned this tool
        agent_tool_ids: list[str] = self._agent.tool_ids or []
        if tool_id not in agent_tool_ids:
            raise ToolNotAssignedError(tool_id)

        if not tool.is_active:
            raise ToolForbiddenError(tool_id)

        if tool.tier == "forbidden":
            raise ToolForbiddenError(tool_id)

        if tool.tier == "requires_approval":
            raise ToolRequiresApprovalError(tool_id, tool)

        # tier in ('safe', 'managed') — execute
        logger.info(
            "tool_dispatch",
            tool_id=tool_id,
            tier=tool.tier,
            handler_ref=tool.handler_ref,
            agent_id=self._agent.id,
        )
        return await self._execute_handler(tool, tool_input)

    async def _execute_handler(
        self,
        tool: AgentTool,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Route to the correct handler implementation based on handler_ref.

        Built-in handler_refs follow the pattern "calseta:<operation>".
        Each handler calls into the appropriate service layer.
        """
        handler_ref = tool.handler_ref

        if not handler_ref.startswith("calseta:"):
            logger.warning(
                "unknown_handler_ref",
                handler_ref=handler_ref,
                tool_id=tool.id,
            )
            return _error_response(
                ToolErrorCode.INTERNAL_ERROR,
                hint="Unknown handler reference for tool.",
            )

        operation = handler_ref.removeprefix("calseta:")
        handler = _BUILTIN_HANDLERS.get(operation)
        if handler is None:
            logger.warning(
                "unimplemented_builtin_handler",
                operation=operation,
                tool_id=tool.id,
            )
            return _error_response(
                ToolErrorCode.INTERNAL_ERROR,
                hint="Built-in handler not implemented.",
            )

        # --- S2: validate write-tier inputs through a Pydantic model ---
        input_model = TOOL_INPUT_MODELS.get(operation)
        validated_input: Any = tool_input
        if input_model is not None:
            try:
                validated_input = input_model.model_validate(tool_input)
            except ValidationError as exc:
                logger.info(
                    "tool_input_validation_failed",
                    tool_id=tool.id,
                    operation=operation,
                    error_count=len(exc.errors()),
                    agent_id=self._agent.id,
                )
                await self._emit_input_rejected_event(operation, exc)
                return _error_response(
                    ToolErrorCode.INVALID_INPUT,
                    hint=_summarize_validation_error(exc),
                )

        try:
            return await handler(  # type: ignore[no-any-return]
                self._db, self._agent, validated_input, self._context
            )
        except Exception as exc:
            logger.exception(
                "tool_handler_unhandled_exception",
                tool_id=tool.id,
                operation=operation,
                agent_id=self._agent.id,
            )
            return _error_response(
                map_exception_to_error_code(exc),
                hint="Tool handler failed; see server logs.",
            )

    async def _emit_input_rejected_event(
        self,
        operation: str,
        exc: ValidationError,
    ) -> None:
        """Best-effort audit event for input validation failures.

        Never raises — activity event writes are fire-and-forget.
        """
        try:
            from app.schemas.activity_events import ActivityEventType
            from app.services.activity_event import ActivityEventService

            alert_id = self._context.alert_id if self._context is not None else None
            service = ActivityEventService(self._db)
            await service.write(
                ActivityEventType.TOOL_INPUT_REJECTED,
                actor_type="system",
                alert_id=alert_id,
                references={
                    "tool_operation": operation,
                    "agent_id": self._agent.id,
                    "validation_error_count": len(exc.errors()),
                    # Capture only the field paths — never raw values from the LLM
                    "validation_error_fields": [
                        ".".join(str(p) for p in err.get("loc", ()))
                        for err in exc.errors()
                    ][:20],
                },
            )
        except Exception:
            logger.debug("tool_input_rejected_event_emit_failed", exc_info=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _summarize_validation_error(exc: ValidationError) -> str:
    """Return a stable, value-free summary of a Pydantic ValidationError.

    The summary lists the failing field paths and error types. We deliberately
    do NOT include the offending values — those originated from the LLM and
    must not be echoed back as content the model could be encouraged to retry
    verbatim with adversarial mutations.
    """
    parts: list[str] = []
    for err in exc.errors()[:10]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "(root)"
        parts.append(f"{loc}: {err.get('type', 'invalid')}")
    return "Input validation failed. Issues: " + "; ".join(parts)


# ---------------------------------------------------------------------------
# Built-in handler implementations
# ---------------------------------------------------------------------------
# Each handler now receives (db, agent, validated_input, context) and returns a
# dict. ``validated_input`` is either:
#   - A registered Pydantic model instance (for write-tier tools), OR
#   - The raw ``tool_input`` dict (for read-tier tools without a model).


async def _handle_get_alert(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: Any,
    context: RuntimeContext | None,
) -> dict[str, Any]:
    from uuid import UUID

    from app.repositories.alert_repository import AlertRepository

    raw = tool_input if isinstance(tool_input, dict) else {}
    alert_uuid_str = raw.get("alert_uuid", "")
    try:
        alert_uuid = UUID(str(alert_uuid_str))
    except ValueError:
        return _error_response(
            ToolErrorCode.INVALID_INPUT,
            hint="alert_uuid must be a valid UUID.",
        )

    repo = AlertRepository(db)
    alert = await repo.get_by_uuid(alert_uuid)
    if alert is None:
        return _error_response(ToolErrorCode.NOT_FOUND, hint="Alert not found.")

    return {
        "status": "ok",
        "data": {
            "uuid": str(alert.uuid),
            "title": alert.title,
            "severity": alert.severity,
            "status": alert.status,
            "source_name": alert.source_name,
            "description": alert.description,
            "occurred_at": alert.occurred_at.isoformat() if alert.occurred_at else None,
            "enrichment_status": alert.enrichment_status,
            "is_enriched": alert.is_enriched,
            "tags": alert.tags,
        },
    }


async def _handle_search_alerts(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: Any,
    context: RuntimeContext | None,
) -> dict[str, Any]:
    from app.repositories.alert_repository import AlertRepository

    raw = tool_input if isinstance(tool_input, dict) else {}
    repo = AlertRepository(db)
    try:
        limit = int(raw.get("limit", 20))
    except (TypeError, ValueError):
        limit = 20
    limit = min(max(limit, 1), 100)

    alerts, total = await repo.list_alerts(
        status=raw.get("status"),
        severity=raw.get("severity"),
        page=1,
        page_size=limit,
    )
    return {
        "status": "ok",
        "data": {
            "total": total,
            "alerts": [
                {
                    "uuid": str(a.uuid),
                    "title": a.title,
                    "severity": a.severity,
                    "status": a.status,
                    "source_name": a.source_name,
                    "occurred_at": a.occurred_at.isoformat() if a.occurred_at else None,
                    "is_enriched": a.is_enriched,
                }
                for a in alerts
            ],
        },
    }


async def _handle_get_enrichment(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: Any,
    context: RuntimeContext | None,
) -> dict[str, Any]:
    from app.repositories.indicator_repository import IndicatorRepository

    raw = tool_input if isinstance(tool_input, dict) else {}
    indicator_type = raw.get("indicator_type", "")
    value = raw.get("value", "")
    if not indicator_type or not value:
        return _error_response(
            ToolErrorCode.INVALID_INPUT,
            hint="indicator_type and value are required.",
        )

    repo = IndicatorRepository(db)
    indicator = await repo.get_by_type_and_value(indicator_type, str(value))
    if indicator is None:
        return {
            "status": "ok",
            "data": {
                "indicator_type": indicator_type,
                "value": value,
                "found": False,
                "enrichment_results": {},
            },
        }

    return {
        "status": "ok",
        "data": {
            "indicator_type": indicator.type,
            "value": indicator.value,
            "found": True,
            "malice": indicator.malice,
            "first_seen": indicator.first_seen.isoformat() if indicator.first_seen else None,
            "last_seen": indicator.last_seen.isoformat() if indicator.last_seen else None,
            "enrichment_results": indicator.enrichment_results or {},
        },
    }


async def _handle_post_finding(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: Any,
    context: RuntimeContext | None,
) -> dict[str, Any]:
    """Record a structured agent finding on the active alert.

    Validation guarantees (Pydantic):
      - classification is a canonical enum value
      - confidence ∈ [0, 1]
      - reasoning is non-empty and ≤ 4000 chars
      - extras are rejected — no smuggled fields reach the DB

    Scope guarantees (S2):
      - The target alert is always ``context.alert_id``. The LLM-provided
        ``alert_uuid`` is cross-checked; mismatch → ``alert_scope_violation``.
    """
    from datetime import UTC, datetime

    from app.repositories.alert_repository import AlertRepository

    assert isinstance(tool_input, PostFindingInput), (
        "post_finding handler expects validated PostFindingInput"
    )

    repo = AlertRepository(db)
    alert = await _resolve_scoped_alert(
        db=db,
        repo=repo,
        agent=agent,
        context=context,
        claimed_alert_uuid=tool_input.alert_uuid,
        operation="post_finding",
    )
    if isinstance(alert, dict):
        # Scope/lookup error — already a coarse-coded envelope.
        return alert

    finding = {
        "classification": tool_input.classification,
        "confidence": tool_input.confidence,
        "reasoning": tool_input.reasoning,
        "findings": tool_input.findings,
        "recorded_at": datetime.now(UTC).isoformat(),
        "agent_id": agent.id,
    }
    await repo.add_finding(alert, finding)
    await db.flush()

    return {
        "status": "ok",
        "data": {
            "alert_uuid": str(alert.uuid),
            "classification": finding["classification"],
            "confidence": finding["confidence"],
            "recorded": True,
        },
    }


async def _handle_update_alert_status(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: Any,
    context: RuntimeContext | None,
) -> dict[str, Any]:
    """Transition the active alert's status.

    Scope guarantees (S2):
      - The target alert is ALWAYS ``context.alert_id``. Any ``alert_uuid``
        from the LLM is cross-checked but never used to redirect the write.
    """
    from app.repositories.alert_repository import AlertRepository

    assert isinstance(tool_input, UpdateAlertStatusInput), (
        "update_alert_status handler expects validated UpdateAlertStatusInput"
    )

    repo = AlertRepository(db)
    alert = await _resolve_scoped_alert(
        db=db,
        repo=repo,
        agent=agent,
        context=context,
        claimed_alert_uuid=tool_input.alert_uuid,
        operation="update_alert_status",
    )
    if isinstance(alert, dict):
        return alert

    updated = await repo.patch(alert, status=tool_input.status)
    await db.flush()

    return {
        "status": "ok",
        "data": {
            "alert_uuid": str(updated.uuid),
            "status": updated.status,
        },
    }


async def _handle_get_detection_rule(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: Any,
    context: RuntimeContext | None,
) -> dict[str, Any]:
    from uuid import UUID

    from app.repositories.detection_rule_repository import DetectionRuleRepository

    raw = tool_input if isinstance(tool_input, dict) else {}
    rule_uuid_str = raw.get("rule_uuid", "")
    try:
        rule_uuid = UUID(str(rule_uuid_str))
    except ValueError:
        return _error_response(
            ToolErrorCode.INVALID_INPUT,
            hint="rule_uuid must be a valid UUID.",
        )

    repo = DetectionRuleRepository(db)
    rule = await repo.get_by_uuid(rule_uuid)
    if rule is None:
        return _error_response(
            ToolErrorCode.NOT_FOUND, hint="Detection rule not found."
        )

    return {
        "status": "ok",
        "data": {
            "uuid": str(rule.uuid),
            "name": rule.name,
            "documentation": rule.documentation,
            "mitre_tactics": rule.mitre_tactics,
            "mitre_techniques": rule.mitre_techniques,
            "mitre_subtechniques": rule.mitre_subtechniques,
            "data_sources": rule.data_sources,
            "severity": rule.severity,
        },
    }


async def _handle_execute_workflow(
    db: AsyncSession,
    agent: AgentRegistration,
    tool_input: Any,
    context: RuntimeContext | None,
) -> dict[str, Any]:
    # execute_workflow has tier=requires_approval, so this handler is never reached
    # via normal dispatch (ToolRequiresApprovalError is raised first).
    # Included for completeness if approval gating is bypassed in future.
    return {
        "status": "ok",
        "data": {},
    }


# ---------------------------------------------------------------------------
# Scope enforcement helpers
# ---------------------------------------------------------------------------


async def _resolve_scoped_alert(
    *,
    db: AsyncSession,
    repo: Any,
    agent: AgentRegistration,
    context: RuntimeContext | None,
    claimed_alert_uuid: Any,
    operation: str,
) -> Any:
    """Resolve the alert this tool call is allowed to mutate.

    Returns either the ``Alert`` ORM object, OR a coarse-coded error envelope
    (a dict). Callers must check ``isinstance(result, dict)``.

    Rules:
      - If ``context`` carries an ``alert_id``, that is the canonical target.
        The ``claimed_alert_uuid`` from the LLM must match the target's UUID;
        any mismatch is logged as ``tool.scope_violation`` and returned as
        ``alert_scope_violation`` without DB mutation.
      - If ``context.alert_id`` is unset (e.g. routine/issue work), fall back to
        looking up by ``claimed_alert_uuid``. This preserves backwards
        compatibility for tool calls outside an alert investigation.
    """
    # Path A: alert-bound investigation — ignore the LLM's UUID for the WRITE
    if context is not None and context.alert_id is not None:
        alert = await repo.get_by_id(context.alert_id)
        if alert is None:
            return _error_response(
                ToolErrorCode.NOT_FOUND, hint="Active alert no longer exists."
            )

        if str(alert.uuid) != str(claimed_alert_uuid):
            logger.warning(
                "tool_scope_violation",
                operation=operation,
                agent_id=agent.id,
                actual_alert_id=alert.id,
                # Do NOT log the claimed UUID at warning level — it is
                # attacker-controlled. Hash/length only.
                claimed_uuid_len=len(str(claimed_alert_uuid)),
            )
            await _emit_scope_violation_event(
                db=db,
                agent=agent,
                operation=operation,
                actual_alert_id=alert.id,
            )
            return _error_response(
                ToolErrorCode.ALERT_SCOPE_VIOLATION,
                hint=(
                    "Tool call targets a different alert than the active "
                    "investigation. The dispatcher refused to mutate. "
                    "Use only the alert_uuid from your run context."
                ),
            )
        return alert

    # Path B: no alert binding in context — fall back to UUID lookup
    from uuid import UUID

    try:
        target_uuid = UUID(str(claimed_alert_uuid))
    except (TypeError, ValueError):
        return _error_response(
            ToolErrorCode.INVALID_INPUT, hint="alert_uuid must be a valid UUID."
        )

    alert = await repo.get_by_uuid(target_uuid)
    if alert is None:
        return _error_response(ToolErrorCode.NOT_FOUND, hint="Alert not found.")
    return alert


async def _emit_scope_violation_event(
    *,
    db: AsyncSession,
    agent: AgentRegistration,
    operation: str,
    actual_alert_id: int,
) -> None:
    """Best-effort audit log for cross-alert tool calls. Never raises."""
    try:
        from app.schemas.activity_events import ActivityEventType
        from app.services.activity_event import ActivityEventService

        service = ActivityEventService(db)
        await service.write(
            ActivityEventType.TOOL_SCOPE_VIOLATION,
            actor_type="system",
            alert_id=actual_alert_id,
            references={
                "tool_operation": operation,
                "agent_id": agent.id,
                "reason": "claimed_alert_uuid_did_not_match_run_context",
            },
        )
    except Exception:
        logger.debug("scope_violation_event_emit_failed", exc_info=True)


# Registry mapping operation name → handler function
_BUILTIN_HANDLERS: dict[
    str,
    Any,
] = {
    "get_alert": _handle_get_alert,
    "search_alerts": _handle_search_alerts,
    "get_enrichment": _handle_get_enrichment,
    "post_finding": _handle_post_finding,
    "update_alert_status": _handle_update_alert_status,
    "get_detection_rule": _handle_get_detection_rule,
    "execute_workflow": _handle_execute_workflow,
}
