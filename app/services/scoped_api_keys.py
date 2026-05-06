"""Mint short-lived ``cak_*`` API keys for managed agent runs (S3).

Each managed agent run gets its own API key with a 1-hour TTL and a
narrow scope set (``agents:write`` + ``alerts:write`` only). The key is
injected into the subprocess environment as ``CALSETA_API_KEY`` by
:mod:`app.runtime.env_builder`.

Why per-run keys (replacing the inherited platform master key):

* The supervisor process holds long-lived credentials. If those are
  inherited by the agent subprocess (which calls untrusted LLM output),
  any prompt-injection that exfiltrates env vars compromises the whole
  control plane.
* Scoped keys also give us a clean audit trail: every API call
  attributable to a specific ``run_uuid``.
* Auto-expiry means a leaked key is useful for at most one hour. We do
  not need to write a "revoke on run end" path — the auth backend
  rejects expired rows.

The minted key is stored bcrypt-hashed; the plaintext is returned once
to the caller (which immediately puts it into the subprocess env). The
plaintext is never logged.
"""

from __future__ import annotations

import secrets as stdlib_secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import bcrypt
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_api_key_repository import AgentAPIKeyRepository

logger = structlog.get_logger(__name__)

# Match agent_api_key_backend._KEY_PREFIX_LEN (16 chars of "cak_..." form).
_KEY_PREFIX_LEN = 16

# Scopes available to a per-run scoped key. Deliberately narrow: enough
# for an agent to post findings and update alerts, nothing else.
_DEFAULT_SCOPES: tuple[str, ...] = ("agents:write", "alerts:write")

# 1 hour. Confirmed in the S3 design decisions intake (2026-05-05).
DEFAULT_TTL_SECONDS = 3600


async def mint_run_api_key(
    db: AsyncSession,
    agent_id: int,
    run_uuid: UUID,
    *,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    scopes: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Create and persist a scoped, short-lived ``cak_*`` API key for a run.

    Args:
        db: Open async session. The new row is flushed but NOT committed —
            the caller's transaction must commit. (Matches the rest of the
            service layer's pattern.)
        agent_id: Internal integer id of the agent registration (FK target).
        run_uuid: Run UUID used for the key's display name (audit trail).
        ttl_seconds: Lifetime in seconds. Defaults to 3600 (1 hour).
        scopes: Override scopes. Defaults to ``["agents:write", "alerts:write"]``.

    Returns:
        The plaintext key (``cak_...``). Never logged. Caller is
        responsible for handing this off to the subprocess env.
    """
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")

    plain_key = "cak_" + stdlib_secrets.token_urlsafe(32)
    key_prefix = plain_key[:_KEY_PREFIX_LEN]
    key_hash = bcrypt.hashpw(plain_key.encode(), bcrypt.gensalt(rounds=12)).decode()
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)

    repo = AgentAPIKeyRepository(db)
    record = await repo.create(
        agent_id=agent_id,
        name=f"run-{run_uuid}",
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=list(scopes or _DEFAULT_SCOPES),
        expires_at=expires_at,
    )

    logger.info(
        "scoped_run_api_key_minted",
        agent_id=agent_id,
        run_uuid=str(run_uuid),
        key_uuid=str(record.uuid),
        key_prefix=key_prefix,
        expires_at=expires_at.isoformat(),
        ttl_seconds=ttl_seconds,
    )

    return plain_key
