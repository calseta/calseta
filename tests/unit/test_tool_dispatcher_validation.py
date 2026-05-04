"""Unit tests for ToolDispatcher input validation + scope enforcement (S2).

Covers:
  - Pydantic input models (``app/schemas/tool_inputs.py``):
      * post_finding rejects non-canonical classification, out-of-range
        confidence, oversized reasoning, and any extra keys (XSS-classification
        rejection in particular).
      * update_alert_status rejects unknown status values and extras.
  - Dispatcher behaviour:
      * UUID-mismatch on update_alert_status → ``alert_scope_violation``,
        no DB mutation, scope event emitted.
      * UUID-mismatch on post_finding → same.
      * Validation errors return ``invalid_input`` with no ``str(exc)`` leak.
      * Handler exceptions return ``internal_error`` (not the raw message).
      * Coarse-code mapper handles dispatcher exception types.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.integrations.tools.dispatcher import (
    EXCEPTION_TO_ERROR_CODE,
    ToolDispatcher,
    ToolErrorCode,
    ToolForbiddenError,
    ToolNotAssignedError,
    ToolNotFoundError,
    map_exception_to_error_code,
)
from app.runtime.models import RuntimeContext
from app.schemas.tool_inputs import (
    MAX_REASONING_CHARS,
    POST_FINDING_CLASSIFICATIONS,
    PostFindingInput,
    UpdateAlertStatusInput,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _agent(agent_id: int = 7, tool_ids: list[str] | None = None) -> MagicMock:
    a = MagicMock()
    a.id = agent_id
    a.tool_ids = tool_ids if tool_ids is not None else [
        "post_finding",
        "update_alert_status",
        "get_alert",
    ]
    return a


def _tool(
    tool_id: str,
    *,
    tier: str = "managed",
    is_active: bool = True,
    handler_ref: str | None = None,
) -> MagicMock:
    t = MagicMock()
    t.id = tool_id
    t.tier = tier
    t.is_active = is_active
    t.handler_ref = handler_ref or f"calseta:{tool_id}"
    return t


def _alert(*, alert_id: int = 42, alert_uuid: UUID | None = None) -> MagicMock:
    a = MagicMock()
    a.id = alert_id
    a.uuid = alert_uuid or uuid4()
    a.status = "Open"
    return a


def _ctx(alert_id: int | None = 42) -> RuntimeContext:
    return RuntimeContext(
        agent_id=7,
        task_key=f"alert:{alert_id}" if alert_id else "routine:9",
        heartbeat_run_id=1,
        alert_id=alert_id,
    )


def _patch_repo(
    tool: MagicMock | None,
    alert_repo: MagicMock | None = None,
):
    """Context manager that patches AgentToolRepository + AlertRepository."""

    tool_repo_mock = MagicMock()
    tool_repo_mock.get_by_id = AsyncMock(return_value=tool)

    if alert_repo is None:
        alert_repo = MagicMock()
        alert_repo.get_by_id = AsyncMock(return_value=None)
        alert_repo.get_by_uuid = AsyncMock(return_value=None)

    return (
        patch(
            "app.repositories.agent_tool_repository.AgentToolRepository",
            return_value=tool_repo_mock,
        ),
        patch(
            "app.repositories.alert_repository.AlertRepository",
            return_value=alert_repo,
        ),
    )


# ---------------------------------------------------------------------------
# Pure schema tests
# ---------------------------------------------------------------------------


class TestPostFindingInputModel:
    def test_happy_path(self) -> None:
        model = PostFindingInput(
            alert_uuid=uuid4(),
            classification="benign",
            confidence=0.5,
            reasoning="A reason.",
        )
        assert model.classification == "benign"
        assert model.findings == []

    @pytest.mark.parametrize("classification", POST_FINDING_CLASSIFICATIONS)
    def test_each_canonical_classification_accepted(self, classification: str) -> None:
        PostFindingInput(
            alert_uuid=uuid4(),
            classification=classification,
            confidence=0.1,
            reasoning="ok",
        )

    def test_rejects_xss_classification(self) -> None:
        """Canonical XSS-style payload in classification must be rejected.

        This is the negative half of the S2 acceptance criterion: the LLM
        cannot smuggle arbitrary string content into a write field that lacks
        an enum gate.
        """
        with pytest.raises(ValidationError) as exc:
            PostFindingInput(
                alert_uuid=uuid4(),
                classification='<script>alert("xss")</script>',
                confidence=0.9,
                reasoning="trying to escalate",
            )
        # Error must reference classification — confirms enum gate fired
        assert any("classification" in ".".join(str(p) for p in e["loc"]) for e in exc.value.errors())

    def test_rejects_extra_keys(self) -> None:
        with pytest.raises(ValidationError):
            PostFindingInput.model_validate({
                "alert_uuid": str(uuid4()),
                "classification": "benign",
                "confidence": 0.5,
                "reasoning": "hi",
                "smuggled_field": "drop table alerts",
            })

    @pytest.mark.parametrize("bad_confidence", [-0.1, 1.1, 2.0, -1.0])
    def test_rejects_out_of_range_confidence(self, bad_confidence: float) -> None:
        with pytest.raises(ValidationError):
            PostFindingInput(
                alert_uuid=uuid4(),
                classification="benign",
                confidence=bad_confidence,
                reasoning="hi",
            )

    def test_reasoning_length_cap(self) -> None:
        too_long = "x" * (MAX_REASONING_CHARS + 1)
        with pytest.raises(ValidationError):
            PostFindingInput(
                alert_uuid=uuid4(),
                classification="benign",
                confidence=0.5,
                reasoning=too_long,
            )

    def test_reasoning_at_cap_accepted(self) -> None:
        ok = "x" * MAX_REASONING_CHARS
        model = PostFindingInput(
            alert_uuid=uuid4(),
            classification="benign",
            confidence=0.5,
            reasoning=ok,
        )
        assert len(model.reasoning) == MAX_REASONING_CHARS

    def test_rejects_empty_reasoning(self) -> None:
        with pytest.raises(ValidationError):
            PostFindingInput(
                alert_uuid=uuid4(),
                classification="benign",
                confidence=0.5,
                reasoning="",
            )

    def test_rejects_invalid_uuid(self) -> None:
        with pytest.raises(ValidationError):
            PostFindingInput.model_validate({
                "alert_uuid": "not-a-uuid",
                "classification": "benign",
                "confidence": 0.5,
                "reasoning": "hi",
            })


class TestUpdateAlertStatusInputModel:
    def test_happy_path(self) -> None:
        model = UpdateAlertStatusInput(
            alert_uuid=uuid4(),
            status="Triaging",  # type: ignore[arg-type]
        )
        assert model.status == "Triaging"

    def test_rejects_extras(self) -> None:
        with pytest.raises(ValidationError):
            UpdateAlertStatusInput.model_validate({
                "alert_uuid": str(uuid4()),
                "status": "Open",
                "side_effect": "delete from alerts",
            })

    def test_rejects_unknown_status(self) -> None:
        with pytest.raises(ValidationError):
            UpdateAlertStatusInput.model_validate({
                "alert_uuid": str(uuid4()),
                "status": "NotAStatus",
            })


# ---------------------------------------------------------------------------
# Dispatcher behaviour
# ---------------------------------------------------------------------------


class TestDispatcherInputValidation:
    """The dispatcher must surface validation errors as coarse codes, never
    let the raw exception message reach the LLM, and never invoke the
    handler when validation fails."""

    @pytest.fixture(autouse=True)
    def _no_activity_event_writes(self):
        """Activity event writes are best-effort and require a real DB session.
        Patch them out for unit tests."""
        with patch(
            "app.services.activity_event.ActivityEventService"
        ) as service_cls:
            service_cls.return_value.write = AsyncMock()
            yield

    async def test_post_finding_invalid_classification_returns_invalid_input(self) -> None:
        agent = _agent()
        tool = _tool("post_finding")
        ctx = _ctx(alert_id=42)

        tool_repo_patch, alert_repo_patch = _patch_repo(tool)

        # add_finding must NOT be called for a validation failure — assert by
        # building a strict alert repo and inspecting its call count after.
        alert_repo = MagicMock()
        alert_repo.get_by_id = AsyncMock()
        alert_repo.add_finding = AsyncMock()

        with (
            tool_repo_patch,
            patch(
                "app.repositories.alert_repository.AlertRepository",
                return_value=alert_repo,
            ),
        ):
            d = ToolDispatcher(db=AsyncMock(), agent=agent, context=ctx)
            result = await d.dispatch("post_finding", {
                "alert_uuid": str(uuid4()),
                "classification": "ESCALATE_NOW",  # not in enum
                "confidence": 0.9,
                "reasoning": "go",
            })

        assert result["status"] == "error"
        assert result["error_code"] == ToolErrorCode.INVALID_INPUT
        # Hint must not include raw exception text — only stable summary
        assert "ESCALATE_NOW" not in str(result)
        alert_repo.add_finding.assert_not_called()

    async def test_post_finding_xss_classification_no_db_mutation(self) -> None:
        """Acceptance criterion: XSS-classification rejection."""
        agent = _agent()
        tool = _tool("post_finding")
        ctx = _ctx(alert_id=42)

        tool_repo_patch, _ = _patch_repo(tool)

        alert_repo = MagicMock()
        alert_repo.get_by_id = AsyncMock()
        alert_repo.add_finding = AsyncMock()

        with (
            tool_repo_patch,
            patch(
                "app.repositories.alert_repository.AlertRepository",
                return_value=alert_repo,
            ),
        ):
            d = ToolDispatcher(db=AsyncMock(), agent=agent, context=ctx)
            result = await d.dispatch("post_finding", {
                "alert_uuid": str(uuid4()),
                "classification": '<script>alert(1)</script>',
                "confidence": 0.9,
                "reasoning": "x",
            })

        assert result["status"] == "error"
        assert result["error_code"] == ToolErrorCode.INVALID_INPUT
        alert_repo.add_finding.assert_not_called()
        alert_repo.get_by_id.assert_not_called()

    async def test_post_finding_extras_rejected(self) -> None:
        agent = _agent()
        tool = _tool("post_finding")
        ctx = _ctx(alert_id=42)

        tool_repo_patch, _ = _patch_repo(tool)

        alert_repo = MagicMock()
        alert_repo.get_by_id = AsyncMock()
        alert_repo.add_finding = AsyncMock()

        with (
            tool_repo_patch,
            patch(
                "app.repositories.alert_repository.AlertRepository",
                return_value=alert_repo,
            ),
        ):
            d = ToolDispatcher(db=AsyncMock(), agent=agent, context=ctx)
            result = await d.dispatch("post_finding", {
                "alert_uuid": str(uuid4()),
                "classification": "benign",
                "confidence": 0.1,
                "reasoning": "ok",
                "agent_id": 9999,  # extra
                "recorded_at": "2026-01-01T00:00:00Z",  # extra
            })

        assert result["error_code"] == ToolErrorCode.INVALID_INPUT
        alert_repo.add_finding.assert_not_called()

    async def test_post_finding_oversized_reasoning_rejected(self) -> None:
        agent = _agent()
        tool = _tool("post_finding")
        ctx = _ctx(alert_id=42)

        tool_repo_patch, _ = _patch_repo(tool)

        alert_repo = MagicMock()
        alert_repo.get_by_id = AsyncMock()
        alert_repo.add_finding = AsyncMock()

        with (
            tool_repo_patch,
            patch(
                "app.repositories.alert_repository.AlertRepository",
                return_value=alert_repo,
            ),
        ):
            d = ToolDispatcher(db=AsyncMock(), agent=agent, context=ctx)
            result = await d.dispatch("post_finding", {
                "alert_uuid": str(uuid4()),
                "classification": "benign",
                "confidence": 0.1,
                "reasoning": "x" * (MAX_REASONING_CHARS + 1),
            })

        assert result["error_code"] == ToolErrorCode.INVALID_INPUT
        alert_repo.add_finding.assert_not_called()


class TestDispatcherScopeEnforcement:
    """update_alert_status / post_finding must mutate ONLY context.alert_id."""

    @pytest.fixture(autouse=True)
    def _patch_activity_service(self):
        with patch(
            "app.services.activity_event.ActivityEventService"
        ) as service_cls:
            instance = MagicMock()
            instance.write = AsyncMock()
            service_cls.return_value = instance
            yield service_cls

    async def test_update_alert_status_uuid_mismatch_no_mutation(
        self, _patch_activity_service: MagicMock
    ) -> None:
        """Acceptance criterion: UUID-mismatch (no DB mutation)."""
        agent = _agent()
        tool = _tool("update_alert_status")
        actual_alert = _alert(alert_id=42, alert_uuid=uuid4())
        attacker_uuid = uuid4()
        assert attacker_uuid != actual_alert.uuid
        ctx = _ctx(alert_id=42)

        tool_repo_patch, _ = _patch_repo(tool)
        alert_repo = MagicMock()
        alert_repo.get_by_id = AsyncMock(return_value=actual_alert)
        alert_repo.patch = AsyncMock()

        with (
            tool_repo_patch,
            patch(
                "app.repositories.alert_repository.AlertRepository",
                return_value=alert_repo,
            ),
        ):
            d = ToolDispatcher(db=AsyncMock(), agent=agent, context=ctx)
            result = await d.dispatch("update_alert_status", {
                "alert_uuid": str(attacker_uuid),
                "status": "Closed",
            })

        assert result["status"] == "error"
        assert result["error_code"] == ToolErrorCode.ALERT_SCOPE_VIOLATION
        # No mutation on either path
        alert_repo.patch.assert_not_called()
        # Scope-violation activity event was written
        instance = _patch_activity_service.return_value
        assert instance.write.await_count == 1
        ev_args = instance.write.await_args
        # First positional arg is the event type enum
        from app.schemas.activity_events import ActivityEventType

        assert ev_args.args[0] == ActivityEventType.TOOL_SCOPE_VIOLATION
        # alert_id must point at the ACTUAL bound alert, not the claimed UUID
        assert ev_args.kwargs["alert_id"] == actual_alert.id

    async def test_post_finding_uuid_mismatch_no_mutation(
        self, _patch_activity_service: MagicMock
    ) -> None:
        agent = _agent()
        tool = _tool("post_finding")
        actual_alert = _alert(alert_id=42, alert_uuid=uuid4())
        ctx = _ctx(alert_id=42)

        tool_repo_patch, _ = _patch_repo(tool)
        alert_repo = MagicMock()
        alert_repo.get_by_id = AsyncMock(return_value=actual_alert)
        alert_repo.add_finding = AsyncMock()

        with (
            tool_repo_patch,
            patch(
                "app.repositories.alert_repository.AlertRepository",
                return_value=alert_repo,
            ),
        ):
            d = ToolDispatcher(db=AsyncMock(), agent=agent, context=ctx)
            result = await d.dispatch("post_finding", {
                "alert_uuid": str(uuid4()),  # wrong
                "classification": "true_positive",
                "confidence": 1.0,
                "reasoning": "Pwned the alert.",
            })

        assert result["error_code"] == ToolErrorCode.ALERT_SCOPE_VIOLATION
        alert_repo.add_finding.assert_not_called()

    async def test_update_alert_status_matching_uuid_writes_through(
        self, _patch_activity_service: MagicMock
    ) -> None:
        agent = _agent()
        tool = _tool("update_alert_status")
        actual_alert = _alert(alert_id=42, alert_uuid=uuid4())
        ctx = _ctx(alert_id=42)

        tool_repo_patch, _ = _patch_repo(tool)
        updated = MagicMock()
        updated.uuid = actual_alert.uuid
        updated.status = "Triaging"
        alert_repo = MagicMock()
        alert_repo.get_by_id = AsyncMock(return_value=actual_alert)
        alert_repo.patch = AsyncMock(return_value=updated)

        db = AsyncMock()
        with (
            tool_repo_patch,
            patch(
                "app.repositories.alert_repository.AlertRepository",
                return_value=alert_repo,
            ),
        ):
            d = ToolDispatcher(db=db, agent=agent, context=ctx)
            result = await d.dispatch("update_alert_status", {
                "alert_uuid": str(actual_alert.uuid),
                "status": "Triaging",
            })

        assert result["status"] == "ok"
        alert_repo.patch.assert_awaited_once()
        # The patch call must target the context-bound alert, not whatever the
        # LLM said. We pass the alert ORM object positionally.
        call = alert_repo.patch.await_args
        assert call.args[0] is actual_alert


class TestExceptionToErrorCodeMapper:
    def test_known_exceptions_mapped(self) -> None:
        assert (
            map_exception_to_error_code(ToolForbiddenError("x"))
            == ToolErrorCode.FORBIDDEN
        )
        assert (
            map_exception_to_error_code(ToolNotFoundError("x"))
            == ToolErrorCode.NOT_FOUND
        )
        assert (
            map_exception_to_error_code(ToolNotAssignedError("x"))
            == ToolErrorCode.FORBIDDEN
        )

    def test_validation_error_mapped(self) -> None:
        try:
            PostFindingInput.model_validate({})
        except ValidationError as exc:
            assert (
                map_exception_to_error_code(exc) == ToolErrorCode.INVALID_INPUT
            )
        else:  # pragma: no cover
            pytest.fail("PostFindingInput should reject empty dict")

    def test_unknown_exception_defaults_to_internal_error(self) -> None:
        assert (
            map_exception_to_error_code(RuntimeError("boom"))
            == ToolErrorCode.INTERNAL_ERROR
        )

    def test_registry_keys_are_dispatcher_exceptions(self) -> None:
        # Sanity: registry is internally consistent
        for exc_type, code in EXCEPTION_TO_ERROR_CODE.items():
            assert isinstance(exc_type, type) and issubclass(exc_type, Exception)
            assert isinstance(code, str)
