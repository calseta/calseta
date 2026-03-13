"""
MCP authentication — validates API keys on MCP connections.

Implements the MCP SDK ``TokenVerifier`` protocol so the FastMCP server
rejects unauthenticated connections before any resource/tool handler runs.

The token presented by MCP clients is a Calseta API key (``cai_xxx``).
Validation logic mirrors ``APIKeyAuthBackend`` — bcrypt hash check, expiry
check, last_used_at update — but operates outside FastAPI DI because the
MCP server is a standalone process.
"""

from __future__ import annotations

from datetime import UTC, datetime

import bcrypt
import structlog
from mcp.server.auth.provider import AccessToken, TokenVerifier
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.repositories.api_key_repository import APIKeyRepository

logger = structlog.get_logger(__name__)

_KEY_PREFIX_LEN = 8


class CalsetaTokenVerifier(TokenVerifier):
    """
    MCP TokenVerifier backed by the Calseta API key store.

    On every MCP connection the SDK calls ``verify_token(token)`` with the
    bearer token from the client's auth header. We validate it against the
    same ``api_keys`` table used by the REST API.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        """
        Validate an API key and return an ``AccessToken`` on success.

        Returns ``None`` on any failure — the MCP SDK translates that into
        an authentication error for the client.
        """
        if not token.startswith("cai_") or len(token) < _KEY_PREFIX_LEN:
            logger.warning("mcp_auth_failure", reason="invalid_format")
            return None

        key_prefix = token[:_KEY_PREFIX_LEN]

        async with AsyncSessionLocal() as session:
            return await self._verify_with_session(session, token, key_prefix)

    async def _verify_with_session(
        self,
        session: AsyncSession,
        token: str,
        key_prefix: str,
    ) -> AccessToken | None:
        """Run the full verification pipeline within a DB session."""
        repo = APIKeyRepository(session)
        record = await repo.get_by_prefix(key_prefix)

        if record is None:
            logger.warning("mcp_auth_failure", reason="invalid_key", key_prefix=key_prefix)
            return None

        if not bcrypt.checkpw(token.encode(), record.key_hash.encode()):
            logger.warning("mcp_auth_failure", reason="invalid_key", key_prefix=key_prefix)
            return None

        # Expiry check
        if record.expires_at is not None:
            expires_at = record.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if datetime.now(UTC) > expires_at:
                logger.warning("mcp_auth_failure", reason="key_expired", key_prefix=key_prefix)
                return None

        # Update last_used_at
        record.last_used_at = datetime.now(UTC)
        await session.commit()

        logger.info("mcp_auth_success", key_prefix=key_prefix)

        return AccessToken(
            token=token,
            client_id=key_prefix,
            scopes=list(record.scopes),
        )
