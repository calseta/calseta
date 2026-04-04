"""Integration registry — maps action_subtypes to ActionIntegration implementations."""

from __future__ import annotations

import structlog

from app.integrations.actions.base import ActionIntegration
from app.integrations.actions.crowdstrike_integration import CrowdStrikeIntegration
from app.integrations.actions.entra_id_integration import EntraIDActionIntegration
from app.integrations.actions.generic_webhook import GenericWebhookIntegration
from app.integrations.actions.null_integration import NullActionIntegration
from app.integrations.actions.slack_integration import SlackActionIntegration

logger = structlog.get_logger()

# Module-level registry cache. None = not yet built.
# Cleared by reset_registry() in tests.
_REGISTRY: dict[str, ActionIntegration] | None = None


def get_integration_for_action(
    action_subtype: str,
    db: object | None = None,
) -> ActionIntegration:
    """
    Return the appropriate ActionIntegration for the given action_subtype.

    Falls back to NullActionIntegration if no specific integration handles it.

    ``db`` is accepted for forward-compatibility with integrations that require
    DB access (e.g. SlackUserValidationIntegration). The module-level registry
    caches stateless integration instances; DB-dependent integrations should be
    constructed directly by the caller when a DB session is available.
    """
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()

    integration = _REGISTRY.get(action_subtype)
    if integration is None:
        return NullActionIntegration()
    return integration


def reset_registry() -> None:
    """
    Clear the cached registry. Use in tests to force a clean rebuild.
    Not for use in production code.
    """
    global _REGISTRY
    _REGISTRY = None


def _build_registry() -> dict[str, ActionIntegration]:
    """
    Build the subtype → integration mapping from all configured integrations.

    Registration order matters for logging: last writer wins for any subtype
    that appears in multiple integrations' supported_actions(). In practice
    there is no overlap in the built-in set.
    """
    registry: dict[str, ActionIntegration] = {}

    # Slack — notification / escalation
    slack = SlackActionIntegration()
    if slack.is_configured():
        for subtype in slack.supported_actions():
            registry[subtype] = slack
        logger.info("action_integration_registered", integration="slack")
    else:
        logger.info(
            "action_integration_skipped",
            integration="slack",
            reason="SLACK_BOT_TOKEN not configured",
        )

    # CrowdStrike — endpoint containment
    crowdstrike = CrowdStrikeIntegration()
    if crowdstrike.is_configured():
        for subtype in crowdstrike.supported_actions():
            registry[subtype] = crowdstrike
        logger.info("action_integration_registered", integration="crowdstrike")
    else:
        logger.info(
            "action_integration_skipped",
            integration="crowdstrike",
            reason="CROWDSTRIKE_CLIENT_ID/SECRET not configured",
        )

    # Microsoft Entra ID — identity response
    entra = EntraIDActionIntegration()
    if entra.is_configured():
        for subtype in entra.supported_actions():
            registry[subtype] = entra
        logger.info("action_integration_registered", integration="entra_id")
    else:
        logger.info(
            "action_integration_skipped",
            integration="entra_id",
            reason="ENTRA_* vars not configured",
        )

    # Generic webhook — always registered; URL comes from action.payload at runtime
    webhook = GenericWebhookIntegration()
    for subtype in webhook.supported_actions():
        registry[subtype] = webhook
    logger.info("action_integration_registered", integration="generic_webhook")

    logger.info(
        "action_integration_registry_built",
        registered_subtypes=sorted(registry.keys()),
        total=len(registry),
    )
    return registry
