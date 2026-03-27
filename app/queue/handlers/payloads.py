"""Typed Pydantic payload models for all registered task handlers.

Each model corresponds to the keyword arguments accepted by one task
function in ``app/queue/registry.py``. Using these models instead of
raw dicts gives static type checking and runtime validation at the
boundary between enqueue and execute.
"""

from __future__ import annotations

from pydantic import BaseModel


class EnrichAlertPayload(BaseModel):
    """Payload for the ``enrich_alert`` task (queue: enrichment)."""

    alert_id: int


class ExecuteWorkflowRunPayload(BaseModel):
    """Payload for the ``execute_workflow_run`` task (queue: workflows)."""

    workflow_run_id: int


class SendApprovalNotificationPayload(BaseModel):
    """Payload for the ``send_approval_notification_task`` task (queue: dispatch)."""

    approval_request_id: int


class ExecuteApprovedWorkflowPayload(BaseModel):
    """Payload for the ``execute_approved_workflow_task`` task (queue: workflows)."""

    approval_request_id: int


class DispatchAgentWebhooksPayload(BaseModel):
    """Payload for the ``dispatch_agent_webhooks`` task (queue: dispatch)."""

    alert_id: int


class DispatchSingleAgentWebhookPayload(BaseModel):
    """Payload for the ``dispatch_single_agent_webhook`` task (queue: dispatch)."""

    alert_id: int
    agent_id: int


class SandboxResetPayload(BaseModel):
    """Payload for the ``sandbox_reset`` periodic task (queue: default)."""

    timestamp: int
