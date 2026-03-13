"""
Notifier factory — resolves the configured ApprovalNotifier from settings.

Reads APPROVAL_NOTIFIER env var: "slack" | "teams" | "none" (default).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.config import Settings

from app.workflows.notifiers.base import ApprovalNotifierBase


def get_approval_notifier(cfg: Settings) -> ApprovalNotifierBase:
    """
    Return the configured ApprovalNotifierBase implementation.

    Defaults to NullApprovalNotifier when APPROVAL_NOTIFIER is "none"
    or not recognised.
    """
    name = (cfg.APPROVAL_NOTIFIER or "none").lower().strip()

    if name == "slack":
        from app.workflows.notifiers.slack_notifier import (
            SlackApprovalNotifier,  # type: ignore[import]
        )

        notifier: ApprovalNotifierBase = SlackApprovalNotifier(cfg)
        return notifier

    if name == "teams":
        from app.workflows.notifiers.teams_notifier import (
            TeamsApprovalNotifier,  # type: ignore[import]
        )

        notifier = TeamsApprovalNotifier(cfg)
        return notifier

    from app.workflows.notifiers.null_notifier import NullApprovalNotifier

    return NullApprovalNotifier()
