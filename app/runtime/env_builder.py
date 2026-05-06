"""
Build the CALSETA_* environment variable dict for managed agent subprocesses.

Each managed agent gets a set of well-known environment variables injected
into its subprocess environment. These provide the agent with identity,
context, and API access without requiring it to parse configuration files
or discover service endpoints.

S3 (2026-05-05): the ``CALSETA_API_KEY`` injected here is **never** the
platform's master key inherited from ``os.environ``. It is always a
freshly-minted, short-lived ``cak_*`` key scoped to ``(agent_id, run_uuid)``
with a 1-hour TTL. See :mod:`app.services.scoped_api_keys`.

Usage:
    env = await build_agent_env(db, agent, context)
    # ... pass env to subprocess

    # Test/legacy path — supply api_key explicitly to skip the mint step:
    env = await build_agent_env(db, agent, context, api_key="explicit-key")
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models.agent_registration import AgentRegistration
    from app.runtime.models import RuntimeContext

logger = structlog.get_logger(__name__)


class CalsetaEnvVar(StrEnum):
    """Well-known environment variable names injected into agent subprocesses."""

    AGENT_ID = "CALSETA_AGENT_ID"
    AGENT_NAME = "CALSETA_AGENT_NAME"
    RUN_ID = "CALSETA_RUN_ID"
    TASK_KEY = "CALSETA_TASK_KEY"
    WAKE_REASON = "CALSETA_WAKE_REASON"
    API_URL = "CALSETA_API_URL"
    API_KEY = "CALSETA_API_KEY"
    ALERT_UUID = "CALSETA_ALERT_UUID"
    WORKSPACE_DIR = "CALSETA_WORKSPACE_DIR"


async def build_agent_env(
    db: AsyncSession,
    agent: AgentRegistration,
    context: RuntimeContext,
    *,
    api_key: str | None = None,
    ttl_seconds: int | None = None,
) -> dict[str, str]:
    """Build the full subprocess environment for a managed agent run.

    Starts from the parent process env, then *removes* any inherited
    ``CALSETA_API_KEY`` (defense-in-depth — the parent might be the worker
    process that holds the platform's master key) and injects a freshly
    minted scoped key for this specific run.

    Args:
        db: Async session used to persist the minted ``cak_*`` row.
        agent: The agent registration ORM object.
        context: Runtime context for the current run.
        api_key: Test/legacy override. When provided, no key is minted;
            the caller's value is used as-is. Production code should leave
            this ``None``.
        ttl_seconds: Override scoped-key TTL. Default is 3600s (1 hour).

    Returns:
        A new dict suitable for passing as ``env`` to subprocess calls.
        ``CALSETA_API_KEY`` is always present unless minting failed AND no
        override was supplied.
    """
    from app.services.scoped_api_keys import DEFAULT_TTL_SECONDS, mint_run_api_key

    workspace_dir = str(Path(settings.AGENT_FILES_DIR) / str(agent.uuid))

    env = dict(os.environ)
    # S3: never let the parent's master key leak into the subprocess.
    env.pop(CalsetaEnvVar.API_KEY, None)

    env[CalsetaEnvVar.AGENT_ID] = str(agent.uuid)
    env[CalsetaEnvVar.AGENT_NAME] = agent.name
    env[CalsetaEnvVar.TASK_KEY] = context.task_key
    env[CalsetaEnvVar.API_URL] = settings.CALSETA_API_BASE_URL
    env[CalsetaEnvVar.WORKSPACE_DIR] = workspace_dir

    if context.run_uuid is not None:
        env[CalsetaEnvVar.RUN_ID] = str(context.run_uuid)

    wake_reason = getattr(context, "wake_reason", None)
    if wake_reason is not None:
        env[CalsetaEnvVar.WAKE_REASON] = str(wake_reason)

    # Mint a scoped, short-lived API key unless the caller supplied one.
    minted = False
    if api_key is None and context.run_uuid is not None:
        api_key = await mint_run_api_key(
            db,
            agent_id=agent.id,
            run_uuid=context.run_uuid,
            ttl_seconds=ttl_seconds or DEFAULT_TTL_SECONDS,
        )
        minted = True

    if api_key is not None:
        env[CalsetaEnvVar.API_KEY] = api_key

    if context.alert_id is not None:
        env[CalsetaEnvVar.ALERT_UUID] = str(context.alert_id)

    logger.debug(
        "agent_env_built",
        agent_uuid=str(agent.uuid),
        task_key=context.task_key,
        has_api_key=api_key is not None,
        api_key_minted=minted,
        has_alert_id=context.alert_id is not None,
    )

    return env
