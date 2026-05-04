"""S6 — ToolDispatcher rejects invalid tool slugs from model output.

The model-generated `name` on a `tool_use` block is untrusted input. The
dispatcher must reject anything that doesn't match ^[a-z0-9_]{1,64}$ before
any DB lookup or path manipulation, surfacing error_code=invalid_tool_slug.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.integrations.tools.dispatcher import (
    InvalidToolSlugError,
    ToolDispatcher,
)


def _make_dispatcher() -> ToolDispatcher:
    db = MagicMock()
    agent = MagicMock()
    agent.id = 1
    agent.tool_ids = ["get_alert"]
    return ToolDispatcher(db=db, agent=agent)


class TestToolSlugValidation:
    async def test_path_traversal_rejected(self) -> None:
        dispatcher = _make_dispatcher()
        with pytest.raises(InvalidToolSlugError) as exc:
            await dispatcher.dispatch("../etc/passwd", {})
        assert exc.value.error_code == "invalid_tool_slug"

    async def test_uppercase_rejected(self) -> None:
        dispatcher = _make_dispatcher()
        with pytest.raises(InvalidToolSlugError):
            await dispatcher.dispatch("GetAlert", {})

    async def test_dash_rejected(self) -> None:
        # The slug regex deliberately disallows dashes (only [a-z0-9_]).
        dispatcher = _make_dispatcher()
        with pytest.raises(InvalidToolSlugError):
            await dispatcher.dispatch("get-alert", {})

    async def test_too_long_rejected(self) -> None:
        dispatcher = _make_dispatcher()
        with pytest.raises(InvalidToolSlugError):
            await dispatcher.dispatch("a" * 65, {})

    async def test_empty_rejected(self) -> None:
        dispatcher = _make_dispatcher()
        with pytest.raises(InvalidToolSlugError):
            await dispatcher.dispatch("", {})

    async def test_whitespace_rejected(self) -> None:
        dispatcher = _make_dispatcher()
        with pytest.raises(InvalidToolSlugError):
            await dispatcher.dispatch("get alert", {})

    async def test_shell_metachar_rejected(self) -> None:
        dispatcher = _make_dispatcher()
        with pytest.raises(InvalidToolSlugError):
            await dispatcher.dispatch("get_alert;rm", {})

    async def test_non_string_rejected(self) -> None:
        dispatcher = _make_dispatcher()
        with pytest.raises(InvalidToolSlugError):
            await dispatcher.dispatch(123, {})  # type: ignore[arg-type]

    async def test_valid_slug_does_not_raise_invalid_slug(self) -> None:
        """A valid slug should pass the slug check (it may then raise other
        errors like ToolNotFoundError because no real tool exists, but the
        slug-validation gate itself must not block it).
        """
        dispatcher = _make_dispatcher()
        # Must not raise InvalidToolSlugError — anything downstream is fine.
        try:
            await dispatcher.dispatch("get_alert", {})
        except InvalidToolSlugError:
            pytest.fail("Valid slug 'get_alert' should not raise InvalidToolSlugError")
        except Exception:
            # Downstream raises (e.g. ToolNotFoundError because the repo lookup
            # hits a MagicMock) are expected and not what this test is checking.
            pass
