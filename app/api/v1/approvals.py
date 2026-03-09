"""
Approval callback endpoints (Chunks 4.12, 4.13).

POST /v1/approvals/callback/slack  — Slack interactive button callback
POST /v1/approvals/callback/teams  — Teams stub (interactive buttons not supported via webhook)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Annotated

from fastapi import APIRouter, Header, Request, Response, status

from app.config import settings

router = APIRouter(prefix="/approvals", tags=["approvals"])


# ---------------------------------------------------------------------------
# POST /v1/approvals/callback/slack
# ---------------------------------------------------------------------------


@router.post("/callback/slack", status_code=status.HTTP_200_OK)
async def slack_callback(
    request: Request,
    x_slack_signature: Annotated[str | None, Header()] = None,
    x_slack_request_timestamp: Annotated[str | None, Header()] = None,
) -> Response:
    """
    Receive Slack interactive button payloads.

    Validates the Slack signature, extracts the approval decision from the
    action_id, and calls process_approval_decision(). Returns 200 immediately
    (Slack requires < 3 seconds).

    Note: raw body is read first so that body bytes are cached before form
    parsing — this is required for correct HMAC signature validation against
    the raw request body.
    """
    import structlog

    from app.db.session import AsyncSessionLocal
    from app.workflows.approval import process_approval_decision

    log = structlog.get_logger(__name__)

    # Read and cache raw body before any form parsing (required for sig validation)
    raw_body = await request.body()

    # -- Signature validation --
    signing_secret = settings.SLACK_SIGNING_SECRET
    if signing_secret:
        ts = x_slack_request_timestamp or ""
        sig = x_slack_signature or ""

        # Reject stale requests (> 5 min old)
        try:
            if abs(time.time() - float(ts)) > 300:
                return Response(status_code=status.HTTP_403_FORBIDDEN, content="Request too old")
        except (ValueError, TypeError):
            return Response(status_code=status.HTTP_403_FORBIDDEN, content="Invalid timestamp")

        sig_base = f"v0:{ts}:{raw_body.decode()}"
        expected = "v0=" + hmac.new(
            signing_secret.encode(),
            sig_base.encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return Response(status_code=status.HTTP_403_FORBIDDEN, content="Invalid signature")

    # Parse payload from form data (body is already cached, so stream() yields _body)
    form_data = await request.form()
    payload: str | None = form_data.get("payload")  # type: ignore[assignment]

    if not payload:
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Missing payload")

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return Response(status_code=status.HTTP_400_BAD_REQUEST, content="Invalid JSON payload")

    # Extract action from Block Kit interactive payload
    actions = data.get("actions", [])
    if not actions:
        return Response(content="ok")

    action = actions[0]
    action_id: str = action.get("action_id", "")
    slack_user_id: str = data.get("user", {}).get("id", "")

    # action_id format: "approve:{uuid}" or "reject:{uuid}"
    if not action_id or ":" not in action_id:
        return Response(content="ok")

    decision, uuid_str = action_id.split(":", 1)
    approved = decision == "approve"

    try:
        from uuid import UUID

        approval_uuid = UUID(uuid_str)
    except ValueError:
        log.warning("slack_callback_invalid_uuid", action_id=action_id)
        return Response(content="ok")

    try:
        async with AsyncSessionLocal() as db:
            await process_approval_decision(
                approval_uuid=approval_uuid,
                approved=approved,
                responder_id=slack_user_id or None,
                db=db,
            )
            await db.commit()
    except ValueError as exc:
        log.warning("slack_callback_decision_failed", error=str(exc))

    # Fire-and-forget: update the original Slack message to replace buttons
    # with the decision text (prevents double-clicks and shows outcome inline)
    channel_id = data.get("channel", {}).get("id", "")
    message_ts = data.get("message", {}).get("ts", "")
    original_blocks = data.get("message", {}).get("blocks", [])
    bot_token = settings.SLACK_BOT_TOKEN

    if bot_token and channel_id and message_ts:
        try:
            import httpx

            outcome_icon = "\u2705" if approved else "\u274c"
            by_text = f" by <@{slack_user_id}>" if slack_user_id else ""
            decision_text = f"{outcome_icon} *{'Approved' if approved else 'Rejected'}*{by_text}"

            # Keep original blocks (header, fields, reason) but replace the actions block
            updated_blocks = [b for b in original_blocks if b.get("type") != "actions"]
            updated_blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": decision_text},
            })

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(
                    "https://slack.com/api/chat.update",
                    headers={
                        "Authorization": f"Bearer {bot_token}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "channel": channel_id,
                        "ts": message_ts,
                        "blocks": updated_blocks,
                    },
                )
        except Exception as exc:
            log.warning("slack_message_update_failed", error=str(exc))

    return Response(content="ok")


# ---------------------------------------------------------------------------
# POST /v1/approvals/callback/teams
# ---------------------------------------------------------------------------


@router.post("/callback/teams", status_code=status.HTTP_200_OK)
async def teams_callback() -> dict:
    """
    Teams interactive callback stub.

    Teams incoming webhooks do not support interactive button callbacks
    (that requires Azure Bot Framework, which is out of scope for v1).

    Approvers should use the REST API endpoints:
      POST /v1/workflow-approvals/{uuid}/approve
      POST /v1/workflow-approvals/{uuid}/reject
    """
    return {
        "message": (
            "Teams interactive callbacks are not supported via incoming webhooks in v1. "
            "Use the Calseta REST API to approve or reject: "
            "POST /v1/workflow-approvals/{uuid}/approve or /reject"
        )
    }
