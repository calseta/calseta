"""
Build the CALSETA_* environment variable dict for managed agent subprocesses.

Each managed agent gets a set of well-known environment variables injected
into its subprocess environment. These provide the agent with identity,
context, and API access without requiring it to parse configuration files
or discover service endpoints.

Usage (by the engine, in a future chunk):
    env = build_agent_env(agent, context, api_key=scoped_key)
    response = await adapter.create_message(..., env=env)
"""

from __future__ import annotations

import os
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from app.config import settings

if TYPE_CHECKING:
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


def build_agent_env(
    agent: AgentRegistration,
    context: RuntimeContext,
    *,
    api_key: str | None = None,
) -> dict[str, str]:
    """Build the full subprocess environment for a managed agent run.

    Inherits all current process env vars and overlays the CALSETA_*
    variables so the agent subprocess can identify itself and reach
    the Calseta API.

    Args:
        agent: The agent registration ORM object.
        context: Runtime context for the current run.
        api_key: Optional short-lived scoped API key (raw value).

    Returns:
        A new dict suitable for passing as ``env`` to subprocess calls.
    """
    workspace_dir = str(Path(settings.AGENT_FILES_DIR) / str(agent.uuid))

    env = dict(os.environ)

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

    if api_key is not None:
        env[CalsetaEnvVar.API_KEY] = api_key

    if context.alert_id is not None:
        env[CalsetaEnvVar.ALERT_UUID] = str(context.alert_id)

    logger.debug(
        "agent_env_built",
        agent_uuid=str(agent.uuid),
        task_key=context.task_key,
        has_api_key=api_key is not None,
        has_alert_id=context.alert_id is not None,
    )

    return env
