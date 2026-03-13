"""
Unit tests for authentication and authorization logic.

These tests do NOT require a running database — they exercise the auth
logic in isolation using mocked dependencies.
"""

from __future__ import annotations

import re
import secrets

import pytest

from app.auth.scopes import Scope

# ---------------------------------------------------------------------------
# Key format validation
# ---------------------------------------------------------------------------


class TestAPIKeyFormat:
    """Verify the key generation format contract."""

    def _generate_key(self) -> str:
        """Replicate the key generation in APIKeyRepository."""
        return "cai_" + secrets.token_urlsafe(32)

    def test_key_format_matches_spec(self) -> None:
        """Key must match cai_ + 32 urlsafe base64 chars pattern."""
        pattern = re.compile(r"^cai_[A-Za-z0-9_\-]{32,}$")
        for _ in range(20):
            key = self._generate_key()
            assert pattern.match(key), f"Key {key!r} does not match expected format"

    def test_key_prefix_is_first_8_chars(self) -> None:
        key = self._generate_key()
        prefix = key[:8]
        assert prefix.startswith("cai_")
        assert len(prefix) == 8

    def test_key_uniqueness(self) -> None:
        keys = {self._generate_key() for _ in range(100)}
        assert len(keys) == 100, "Duplicate keys generated"


# ---------------------------------------------------------------------------
# Scope enum
# ---------------------------------------------------------------------------


class TestScopes:
    def test_all_scopes_present(self) -> None:
        expected = {
            "alerts:read",
            "alerts:write",
            "enrichments:read",
            "workflows:read",
            "workflows:write",
            "workflows:execute",
            "approvals:write",
            "agents:read",
            "agents:write",
            "admin",
        }
        assert set(Scope) == expected

    def test_admin_scope_value(self) -> None:
        assert Scope.ADMIN == "admin"

    def test_scope_is_string(self) -> None:
        assert isinstance(Scope.ALERTS_READ, str)


# ---------------------------------------------------------------------------
# AuthContext
# ---------------------------------------------------------------------------


class TestAuthContext:
    def test_auth_context_fields(self) -> None:
        from app.auth.base import AuthContext

        ctx = AuthContext(key_prefix="cai_test", scopes=["alerts:read"], key_id=1)
        assert ctx.key_prefix == "cai_test"
        assert ctx.scopes == ["alerts:read"]
        assert ctx.key_id == 1
        assert ctx.allowed_sources is None

    def test_auth_context_with_allowed_sources(self) -> None:
        from app.auth.base import AuthContext

        ctx = AuthContext(
            key_prefix="cai_xxxx",
            scopes=["admin"],
            key_id=42,
            allowed_sources=["elastic", "sentinel"],
        )
        assert ctx.allowed_sources == ["elastic", "sentinel"]


# ---------------------------------------------------------------------------
# APIKeyAuthBackend — unit tests with mock repo
# ---------------------------------------------------------------------------


class TestAPIKeyAuthBackend:
    """
    These tests mock the DB to test backend logic in isolation.
    Integration tests (requiring a real DB) live in tests/integration/.
    """

    def _make_request(self, auth_header: str | None = None) -> object:
        """Return a minimal mock request object."""
        from unittest.mock import MagicMock

        request = MagicMock()
        headers: dict[str, str] = {}
        if auth_header is not None:
            headers["Authorization"] = auth_header
        request.headers = headers
        return request

    @pytest.mark.asyncio
    async def test_missing_auth_header_raises_401(self) -> None:
        from unittest.mock import MagicMock

        from app.api.errors import CalsetaException
        from app.auth.api_key_backend import APIKeyAuthBackend

        db = MagicMock()
        backend = APIKeyAuthBackend(db)
        request = self._make_request(auth_header=None)

        with pytest.raises(CalsetaException) as exc_info:
            await backend.authenticate(request)  # type: ignore[arg-type]

        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_invalid_bearer_prefix_raises_401(self) -> None:
        from unittest.mock import MagicMock

        from app.api.errors import CalsetaException
        from app.auth.api_key_backend import APIKeyAuthBackend

        db = MagicMock()
        backend = APIKeyAuthBackend(db)
        request = self._make_request(auth_header="Token cai_bad")

        with pytest.raises(CalsetaException) as exc_info:
            await backend.authenticate(request)  # type: ignore[arg-type]

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_key_prefix_raises_401(self) -> None:
        """Key starting with wrong format raises 401."""
        from unittest.mock import MagicMock

        from app.api.errors import CalsetaException
        from app.auth.api_key_backend import APIKeyAuthBackend

        db = MagicMock()
        backend = APIKeyAuthBackend(db)
        request = self._make_request(auth_header="Bearer sk_notcai_12345")

        with pytest.raises(CalsetaException) as exc_info:
            await backend.authenticate(request)  # type: ignore[arg-type]

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_key_returns_auth_context(self) -> None:
        """A properly formatted key that matches DB returns AuthContext."""
        from unittest.mock import AsyncMock, MagicMock, patch

        import bcrypt

        from app.auth.api_key_backend import APIKeyAuthBackend

        plain_key = "cai_" + secrets.token_urlsafe(32)
        key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt()).decode()

        mock_record = MagicMock()
        mock_record.id = 1
        mock_record.key_hash = key_hash
        mock_record.scopes = ["alerts:read"]
        mock_record.allowed_sources = None
        mock_record.expires_at = None  # Not expired

        # Use AsyncMock for db so that db.flush() is awaitable
        from unittest.mock import AsyncMock as AsyncMockCls

        db = AsyncMockCls()

        with patch(
            "app.auth.api_key_backend.APIKeyRepository"
        ) as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_prefix = AsyncMock(return_value=mock_record)

            backend = APIKeyAuthBackend(db)
            request = self._make_request(auth_header=f"Bearer {plain_key}")
            ctx = await backend.authenticate(request)  # type: ignore[arg-type]

        assert ctx.key_prefix == plain_key[:8]
        assert ctx.scopes == ["alerts:read"]
        assert ctx.key_id == 1

    @pytest.mark.asyncio
    async def test_hash_mismatch_raises_401(self) -> None:
        """A key whose hash doesn't match returns 401."""
        from unittest.mock import AsyncMock, MagicMock, patch

        import bcrypt

        from app.api.errors import CalsetaException
        from app.auth.api_key_backend import APIKeyAuthBackend

        # Store hash of a DIFFERENT key
        other_key = "cai_" + secrets.token_urlsafe(32)
        key_hash = bcrypt.hashpw(other_key.encode(), bcrypt.gensalt()).decode()

        mock_record = MagicMock()
        mock_record.key_hash = key_hash
        mock_record.scopes = ["admin"]
        mock_record.allowed_sources = None

        db = MagicMock()
        plain_key = "cai_" + secrets.token_urlsafe(32)

        with patch("app.auth.api_key_backend.APIKeyRepository") as MockRepo:
            mock_repo = MockRepo.return_value
            mock_repo.get_by_prefix = AsyncMock(return_value=mock_record)

            backend = APIKeyAuthBackend(db)
            request = self._make_request(auth_header=f"Bearer {plain_key}")

            with pytest.raises(CalsetaException) as exc_info:
                await backend.authenticate(request)  # type: ignore[arg-type]

        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# require_scope dependency logic
# ---------------------------------------------------------------------------


class TestRequireScope:
    def _make_mock_request(self) -> object:
        from unittest.mock import MagicMock

        request = MagicMock()
        request.method = "GET"
        request.url.path = "/v1/test"
        request.headers = {}
        return request

    @pytest.mark.asyncio
    async def test_admin_passes_any_scope_check(self) -> None:
        from app.auth.base import AuthContext
        from app.auth.dependencies import require_scope

        ctx = AuthContext(key_prefix="cai_xxxx", scopes=["admin"], key_id=1)
        checker = require_scope(Scope.ALERTS_WRITE)
        result = await checker(self._make_mock_request(), ctx)  # type: ignore[call-arg]
        assert result is ctx

    @pytest.mark.asyncio
    async def test_correct_scope_passes(self) -> None:
        from app.auth.base import AuthContext
        from app.auth.dependencies import require_scope

        ctx = AuthContext(key_prefix="cai_xxxx", scopes=["alerts:read"], key_id=1)
        checker = require_scope(Scope.ALERTS_READ)
        result = await checker(self._make_mock_request(), ctx)  # type: ignore[call-arg]
        assert result is ctx

    @pytest.mark.asyncio
    async def test_wrong_scope_raises_403(self) -> None:
        from app.api.errors import CalsetaException
        from app.auth.base import AuthContext
        from app.auth.dependencies import require_scope

        ctx = AuthContext(key_prefix="cai_xxxx", scopes=["alerts:read"], key_id=1)
        checker = require_scope(Scope.ALERTS_WRITE)

        with pytest.raises(CalsetaException) as exc_info:
            await checker(self._make_mock_request(), ctx)  # type: ignore[call-arg]

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "FORBIDDEN"

    @pytest.mark.asyncio
    async def test_one_of_multiple_scopes_passes(self) -> None:
        """Scope OR logic — having any one of the required scopes is sufficient."""
        from app.auth.base import AuthContext
        from app.auth.dependencies import require_scope

        ctx = AuthContext(key_prefix="cai_xxxx", scopes=["workflows:read"], key_id=1)
        checker = require_scope(Scope.ALERTS_READ, Scope.WORKFLOWS_READ)
        result = await checker(self._make_mock_request(), ctx)  # type: ignore[call-arg]
        assert result is ctx
