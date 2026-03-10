"""
ApprovalNotifierBase — abstract base class for workflow approval notification channels.

Concrete implementations: NullApprovalNotifier, SlackApprovalNotifier (4.12),
TeamsApprovalNotifier (4.13).

Both methods must NEVER raise. Errors are logged internally; callers always
receive control back.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass
class ApprovalRequest:
    """
    All data needed by a notifier to send an approval message.

    Fields match the workflow_approval_requests DB row plus denormalized
    workflow metadata for richer notification messages.
    """

    approval_uuid: UUID
    workflow_name: str
    workflow_risk_level: str
    indicator_type: str
    indicator_value: str
    trigger_source: str
    reason: str
    confidence: float  # 0.0–1.0
    expires_at: datetime
    alert_uuid: UUID | None = None
    approval_channel: str | None = None
    decide_token: str | None = None
    execution_result: dict[str, Any] | None = field(default=None)


class ApprovalNotifierBase(ABC):
    """
    Abstract base class for workflow approval notification channels.

    Subclasses implement send_approval_request() and send_result_notification().
    Neither method should ever raise — all errors must be caught and logged.
    """

    notifier_name: str = "base"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if the notifier has the required credentials/config."""
        ...

    @abstractmethod
    async def send_approval_request(self, request: ApprovalRequest) -> str:
        """
        Send an approval request notification.

        Returns an external message ID (e.g. Slack ts) that can be used
        for thread replies in send_result_notification(). Returns an empty
        string if the notification could not be sent.

        Must never raise.
        """
        ...

    @abstractmethod
    async def send_result_notification(
        self,
        request: ApprovalRequest,
        approved: bool,
        responder_id: str | None,
    ) -> None:
        """
        Send a follow-up notification with the approval decision result.

        Must never raise.
        """
        ...
