"""
Unit tests for MCP authentication — CalsetaTokenVerifier and check_scope.

These tests mock the DB layer and verify that the MCP auth module correctly
validates API keys, checks expiry, updates last_used_at, and enforces scopes.
No running database required.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import pytest

from app.mcp.auth import CalsetaTokenVerifier
from app.mcp.scope import check_scope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_api_key_record(
    *,
    plain_key: str | None = None,
    scopes: list[str] | None = None,
    expires_at: datetime | None = None,
    is_active: bool = True,
) -> tuple[str, MagicMock]:
    """Create a plain key and a matching mock APIKey DB record."""
    if plain_key is None:
        plain_key = "cai_" + secrets.token_urlsafe(32)
    key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt()).decode()

    record = MagicMock()
    record.id = 1
    record.key_prefix = plain_key[:8]
    record.key_hash = key_hash
    record.scopes = scopes or ["admin"]
    record.expires_at = expires_at
    record.is_active = is_active
    record.last_used_at = None
    return plain_key, record


def _mock_session(mock_repo_instance: MagicMock) -> AsyncMock:
    """Return a mock AsyncSession that auto-commits."""
    session = AsyncMock()
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# CalsetaTokenVerifier — verify_token()
# ---------------------------------------------------------------------------


class TestCalsetaTokenVerifier:
    """Tests for the MCP token verifier backed by Calseta API keys."""

    async def test_valid_key_returns_access_token(self) -> None:
        """A properly formatted, unexpired key returns an AccessToken."""
        plain_key, record = _make_api_key_record(scopes=["alerts:read", "alerts:write"])

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch("app.mcp.auth.AsyncSessionLocal") as mock_session_ctx,
            patch("app.mcp.auth.APIKeyRepository", return_value=mock_repo),
        ):
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            verifier = CalsetaTokenVerifier()
            token = await verifier.verify_token(plain_key)

        assert token is not None
        assert token.client_id == plain_key[:8]
        assert set(token.scopes) == {"alerts:read", "alerts:write"}
        assert token.token == plain_key

    async def test_invalid_format_no_cai_prefix(self) -> None:
        """Token not starting with 'cai_' is rejected immediately."""
        verifier = CalsetaTokenVerifier()
        token = await verifier.verify_token("sk_invalid_prefix_token")
        assert token is None

    async def test_invalid_format_too_short(self) -> None:
        """Token shorter than key prefix length is rejected."""
        verifier = CalsetaTokenVerifier()
        token = await verifier.verify_token("cai_xx")
        assert token is None

    async def test_empty_token_rejected(self) -> None:
        """Empty string token is rejected."""
        verifier = CalsetaTokenVerifier()
        token = await verifier.verify_token("")
        assert token is None

    async def test_key_not_found_in_db(self) -> None:
        """Token with valid format but no matching DB record returns None."""
        plain_key = "cai_" + secrets.token_urlsafe(32)

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=None)

        with (
            patch("app.mcp.auth.AsyncSessionLocal") as mock_session_ctx,
            patch("app.mcp.auth.APIKeyRepository", return_value=mock_repo),
        ):
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            verifier = CalsetaTokenVerifier()
            token = await verifier.verify_token(plain_key)

        assert token is None

    async def test_hash_mismatch_returns_none(self) -> None:
        """Token whose bcrypt hash does not match is rejected."""
        # Generate one key for the record, another for the token
        _, record = _make_api_key_record()
        wrong_key = "cai_" + secrets.token_urlsafe(32)

        # Override key_prefix to match wrong_key's prefix so DB lookup succeeds
        record.key_prefix = wrong_key[:8]

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        with (
            patch("app.mcp.auth.AsyncSessionLocal") as mock_session_ctx,
            patch("app.mcp.auth.APIKeyRepository", return_value=mock_repo),
        ):
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            verifier = CalsetaTokenVerifier()
            token = await verifier.verify_token(wrong_key)

        assert token is None

    async def test_expired_key_returns_none(self) -> None:
        """An expired API key is rejected even if the hash matches."""
        expired_at = datetime.now(UTC) - timedelta(hours=1)
        plain_key, record = _make_api_key_record(expires_at=expired_at)

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch("app.mcp.auth.AsyncSessionLocal") as mock_session_ctx,
            patch("app.mcp.auth.APIKeyRepository", return_value=mock_repo),
        ):
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            verifier = CalsetaTokenVerifier()
            token = await verifier.verify_token(plain_key)

        assert token is None

    async def test_future_expiry_allowed(self) -> None:
        """A key with a future expiry date is accepted."""
        future = datetime.now(UTC) + timedelta(days=30)
        plain_key, record = _make_api_key_record(expires_at=future)

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch("app.mcp.auth.AsyncSessionLocal") as mock_session_ctx,
            patch("app.mcp.auth.APIKeyRepository", return_value=mock_repo),
        ):
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            verifier = CalsetaTokenVerifier()
            token = await verifier.verify_token(plain_key)

        assert token is not None

    async def test_last_used_at_updated_on_success(self) -> None:
        """Successful auth updates the record's last_used_at timestamp."""
        plain_key, record = _make_api_key_record()

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        with (
            patch("app.mcp.auth.AsyncSessionLocal") as mock_session_ctx,
            patch("app.mcp.auth.APIKeyRepository", return_value=mock_repo),
        ):
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            verifier = CalsetaTokenVerifier()
            await verifier.verify_token(plain_key)

        # last_used_at should have been set
        assert record.last_used_at is not None
        assert isinstance(record.last_used_at, datetime)

    async def test_naive_expires_at_treated_as_utc(self) -> None:
        """A naive (no tzinfo) expires_at is treated as UTC for comparison."""
        # Create a key that expired 1 hour ago (naive datetime)
        expired_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        plain_key, record = _make_api_key_record(expires_at=expired_at)

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        with (
            patch("app.mcp.auth.AsyncSessionLocal") as mock_session_ctx,
            patch("app.mcp.auth.APIKeyRepository", return_value=mock_repo),
        ):
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            verifier = CalsetaTokenVerifier()
            token = await verifier.verify_token(plain_key)

        assert token is None


# ---------------------------------------------------------------------------
# check_scope() — scope enforcement on tool/resource calls
# ---------------------------------------------------------------------------


class TestCheckScope:
    """Tests for the MCP scope enforcement helper."""

    def _make_ctx(self, client_id: str | None = "cai_test") -> MagicMock:
        """Return a mock MCP Context with the given client_id."""
        ctx = MagicMock()
        ctx.client_id = client_id
        return ctx

    async def test_missing_client_id_returns_error(self) -> None:
        """No client_id on context returns an auth error."""
        ctx = self._make_ctx(client_id=None)
        session = AsyncMock()

        result = await check_scope(ctx, session, "alerts:read")

        assert result is not None
        assert "Authentication required" in result

    async def test_unknown_key_prefix_returns_error(self) -> None:
        """client_id that matches no DB record returns error."""
        ctx = self._make_ctx()

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=None)

        with patch("app.mcp.scope.APIKeyRepository", return_value=mock_repo):
            result = await check_scope(ctx, AsyncMock(), "alerts:read")

        assert result is not None
        assert "Invalid API key" in result

    async def test_admin_scope_passes_any_check(self) -> None:
        """admin scope is a superscope -- passes every check."""
        ctx = self._make_ctx()

        record = MagicMock()
        record.scopes = ["admin"]

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        with patch("app.mcp.scope.APIKeyRepository", return_value=mock_repo):
            result = await check_scope(ctx, AsyncMock(), "workflows:execute")

        assert result is None

    async def test_correct_scope_passes(self) -> None:
        """Having the required scope returns None (pass)."""
        ctx = self._make_ctx()

        record = MagicMock()
        record.scopes = ["alerts:read", "alerts:write"]

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        with patch("app.mcp.scope.APIKeyRepository", return_value=mock_repo):
            result = await check_scope(ctx, AsyncMock(), "alerts:read")

        assert result is None

    async def test_wrong_scope_returns_error(self) -> None:
        """Having only different scopes returns an insufficiency error."""
        ctx = self._make_ctx()

        record = MagicMock()
        record.scopes = ["alerts:read"]

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        with patch("app.mcp.scope.APIKeyRepository", return_value=mock_repo):
            result = await check_scope(ctx, AsyncMock(), "workflows:execute")

        assert result is not None
        assert "Insufficient scope" in result
        assert "workflows:execute" in result

    async def test_one_of_multiple_scopes_passes(self) -> None:
        """Having any one of multiple required scopes passes (OR logic)."""
        ctx = self._make_ctx()

        record = MagicMock()
        record.scopes = ["workflows:read"]

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        with patch("app.mcp.scope.APIKeyRepository", return_value=mock_repo):
            result = await check_scope(ctx, AsyncMock(), "alerts:read", "workflows:read")

        assert result is None

    async def test_none_of_multiple_scopes_fails(self) -> None:
        """Having none of the required scopes returns error."""
        ctx = self._make_ctx()

        record = MagicMock()
        record.scopes = ["enrichments:read"]

        mock_repo = MagicMock()
        mock_repo.get_by_prefix = AsyncMock(return_value=record)

        with patch("app.mcp.scope.APIKeyRepository", return_value=mock_repo):
            result = await check_scope(ctx, AsyncMock(), "alerts:read", "workflows:read")

        assert result is not None
        assert "Insufficient scope" in result
