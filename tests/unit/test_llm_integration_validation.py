"""S6 — Pydantic validation for LLMIntegration model field.

Ensures that vendor model strings like "claude-sonnet-4-6" are accepted while
shell-flag-shaped values ("--evil"), whitespace, and out-of-charset characters
are rejected at the schema layer — before the value reaches a subprocess.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.llm_integrations import (
    LLMIntegrationCreate,
    LLMIntegrationPatch,
    LLMProvider,
)

# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestLLMIntegrationCreateModelField:
    def test_valid_model_slug_accepted(self) -> None:
        m = LLMIntegrationCreate(
            name="claude-prod",
            provider=LLMProvider.CLAUDE_CODE,
            model="claude-sonnet-4-6",
        )
        assert m.model == "claude-sonnet-4-6"

    def test_vendor_prefixed_model_accepted(self) -> None:
        m = LLMIntegrationCreate(
            name="anthro",
            provider=LLMProvider.ANTHROPIC,
            model="anthropic/claude-3.5-sonnet",
        )
        assert m.model == "anthropic/claude-3.5-sonnet"

    def test_bedrock_colon_model_accepted(self) -> None:
        m = LLMIntegrationCreate(
            name="bedrock",
            provider=LLMProvider.AWS_BEDROCK,
            model="us.anthropic:claude-3-sonnet",
        )
        assert m.model == "us.anthropic:claude-3-sonnet"

    def test_leading_dash_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc:
            LLMIntegrationCreate(
                name="bad",
                provider=LLMProvider.CLAUDE_CODE,
                model="--evil",
            )
        assert "model" in str(exc.value)

    def test_single_dash_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMIntegrationCreate(
                name="bad",
                provider=LLMProvider.CLAUDE_CODE,
                model="-flag",
            )

    def test_internal_whitespace_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMIntegrationCreate(
                name="bad",
                provider=LLMProvider.CLAUDE_CODE,
                model="claude sonnet 4 6",
            )

    def test_leading_whitespace_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMIntegrationCreate(
                name="bad",
                provider=LLMProvider.CLAUDE_CODE,
                model=" claude-sonnet-4-6",
            )

    def test_trailing_whitespace_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMIntegrationCreate(
                name="bad",
                provider=LLMProvider.CLAUDE_CODE,
                model="claude-sonnet-4-6 ",
            )

    def test_newline_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMIntegrationCreate(
                name="bad",
                provider=LLMProvider.CLAUDE_CODE,
                model="claude-sonnet-4-6\n--evil",
            )

    def test_shell_metacharacter_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMIntegrationCreate(
                name="bad",
                provider=LLMProvider.CLAUDE_CODE,
                model="claude;rm -rf /",
            )

    def test_pipe_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMIntegrationCreate(
                name="bad",
                provider=LLMProvider.CLAUDE_CODE,
                model="claude|whoami",
            )

    def test_dollar_rejected(self) -> None:
        with pytest.raises(ValidationError):
            LLMIntegrationCreate(
                name="bad",
                provider=LLMProvider.CLAUDE_CODE,
                model="claude$VAR",
            )

    def test_too_long_rejected(self) -> None:
        # 129 chars — over the 128 cap in the regex
        with pytest.raises(ValidationError):
            LLMIntegrationCreate(
                name="bad",
                provider=LLMProvider.CLAUDE_CODE,
                model="a" * 129,
            )

    def test_max_length_accepted(self) -> None:
        m = LLMIntegrationCreate(
            name="ok",
            provider=LLMProvider.CLAUDE_CODE,
            model="a" * 128,
        )
        assert len(m.model) == 128


# ---------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------


class TestLLMIntegrationPatchModelField:
    def test_none_allowed(self) -> None:
        # Patch with no model field at all — should not raise
        m = LLMIntegrationPatch(name="renamed")
        assert m.model is None

    def test_valid_model_accepted(self) -> None:
        m = LLMIntegrationPatch(model="claude-sonnet-4-6")
        assert m.model == "claude-sonnet-4-6"

    def test_leading_dash_rejected_on_patch(self) -> None:
        with pytest.raises(ValidationError):
            LLMIntegrationPatch(model="--evil")

    def test_whitespace_rejected_on_patch(self) -> None:
        with pytest.raises(ValidationError):
            LLMIntegrationPatch(model="claude sonnet")
