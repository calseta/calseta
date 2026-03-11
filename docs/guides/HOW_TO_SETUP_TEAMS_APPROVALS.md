# How to Set Up Teams Approval Notifications

This guide walks through connecting Calseta to Microsoft Teams so that workflow approval requests are delivered as Adaptive Cards in a Teams channel. When an AI agent triggers a high-risk workflow, a card appears with full context — indicator details, risk level, agent reasoning, and confidence score.

---

## How It Works

```
Agent triggers workflow (trigger_source=agent)
    │
    ├─ Approval gate fires (workflow.approval_mode="always" or "agent_only")
    │       │
    │       ├─ Creates WorkflowApprovalRequest (status=pending)
    │       ├─ Enqueues notification task
    │       └─ Returns 202 {status: "pending_approval", approval_request_uuid, expires_at}
    │
    ├─ Worker sends Adaptive Card to Teams channel via incoming webhook
    │       └─ Card shows indicator, confidence, risk, agent reasoning
    │       └─ Card includes REST API endpoints for approve/reject
    │
    └─ Human approves or rejects via REST API
            └─ POST /v1/workflow-approvals/{uuid}/approve (or /reject)
            └─ If approved: worker executes workflow, posts result card to Teams
```

### Why No Interactive Buttons?

Teams incoming webhooks do not support interactive button callbacks. Interactive Adaptive Cards (with `Action.Submit`) require the Azure Bot Framework — a registered bot endpoint that Teams can POST action payloads to. This is architecturally similar to Slack's interactivity, but requires Azure AD app registration, a Bot Channel Registration, and a dedicated messaging endpoint.

This is planned for a future version. For v1, Teams cards are **informational** — they deliver full approval context to the channel, and approvers respond via the REST API (curl, Postman, a script, or a future UI).

If your team uses Teams and wants click-to-approve, see the "Future: Interactive Buttons" section at the end.

---

## Prerequisites

- A Microsoft Teams workspace where you can manage channel connectors
- Calseta running (API server + worker)

No tunnel is needed — Teams only needs outbound access to the webhook URL (Microsoft → Teams), and Calseta only needs outbound HTTP to post cards. There are no inbound callbacks from Teams.

---

## Step 1: Create a Teams Incoming Webhook

### Teams (New Experience / Workflows App)

Microsoft is migrating from Office 365 Connectors to the Workflows app. If your tenant has deprecated connectors:

1. Open the Teams channel where you want approval cards
2. Click the **+** tab → **Workflows**
3. Search for **"Post to a channel when a webhook request is received"**
4. Name it: `Calseta Approvals`
5. Select the target channel
6. Copy the webhook URL

### Teams (Classic Connectors — if still available)

1. Open the Teams channel
2. Click **⋯** → **Connectors** (or **Manage channel** → **Connectors**)
3. Find **Incoming Webhook** → **Configure**
4. Name: `Calseta Approvals`
5. Optionally upload an icon
6. Click **Create**
7. Copy the webhook URL

The URL looks like:
```
https://outlook.webhook.office.com/webhookb2/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx@yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy/IncomingWebhook/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

---

## Step 2: Configure Calseta

Add to your `.env`:

```bash
# Enable Teams notifications
APPROVAL_NOTIFIER=teams

# From Step 1: incoming webhook URL
TEAMS_WEBHOOK_URL=https://outlook.webhook.office.com/webhookb2/...

# Your Calseta instance URL (used in approval card instructions)
# In production, this is your public Calseta URL
# For local dev, localhost is fine (approvers will use curl locally)
CALSETA_BASE_URL=http://localhost:8000
```

Restart the API server and worker.

---

## Step 3: Prepare a Workflow for Testing

```bash
# List workflows
curl -s http://localhost:8000/v1/workflows \
  -H "Authorization: Bearer <your-api-key>" | jq '.data[] | {uuid, name, state, approval_mode}'

# Enable approval on a workflow (always requires approval, regardless of trigger source)
curl -s -X PATCH http://localhost:8000/v1/workflows/<workflow-uuid> \
  -H "Authorization: Bearer <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "approval_mode": "always",
    "risk_level": "high",
    "approval_timeout_seconds": 3600
  }' | jq .
```

---

## Step 4: Trigger as an Agent

```bash
curl -s -X POST http://localhost:8000/v1/workflows/<workflow-uuid>/execute \
  -H "Authorization: Bearer <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "indicator_type": "account",
    "indicator_value": "jsmith@corp.com",
    "trigger_source": "agent",
    "reason": "Account logged in from 3 countries in 20 minutes — impossible travel detected",
    "confidence": 0.93
  }' | jq .
```

**Expected response:**
```json
{
  "data": {
    "status": "pending_approval",
    "approval_request_uuid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "expires_at": "2026-03-09T14:30:00+00:00"
  }
}
```

**In Teams:** An Adaptive Card appears in the configured channel with:
- Header: `[HIGH RISK] Workflow Approval Required`
- Workflow name
- Indicator, trigger source, confidence, risk level, expiry
- Agent's reasoning
- REST API instructions for approving or rejecting

---

## Step 5: Approve or Reject via REST

```bash
# Approve
curl -s -X POST http://localhost:8000/v1/workflow-approvals/<approval-uuid>/approve \
  -H "Authorization: Bearer <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"responder_id": "jorge"}' | jq .

# Or reject
curl -s -X POST http://localhost:8000/v1/workflow-approvals/<approval-uuid>/reject \
  -H "Authorization: Bearer <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"responder_id": "jorge", "reason": "Insufficient evidence"}' | jq .
```

After approval, the worker executes the workflow and posts a follow-up card to the Teams channel with the result.

---

## Troubleshooting

### Card not appearing in Teams

| Symptom | Cause | Fix |
|---|---|---|
| No card at all | `TEAMS_WEBHOOK_URL` not set or invalid | Check `.env`, restart server |
| Webhook returns 400 | Malformed card payload | Check Calseta worker logs for the full error |
| Webhook returns 403 | Webhook URL expired or connector removed | Re-create the webhook in Teams |
| Card appears but truncated | Card schema version mismatch | Ensure Teams supports Adaptive Card v1.4+ |

### Approval not working

| Symptom | Cause | Fix |
|---|---|---|
| 404 on approve endpoint | Wrong approval UUID | Copy UUID from the Teams card or list pending approvals |
| 409 `APPROVAL_EXPIRED` | Timeout elapsed | Trigger a new workflow execution |
| 409 `APPROVAL_ALREADY_DECIDED` | Already approved/rejected | Check status with `GET /v1/workflow-approvals/{uuid}` |

---

## Configuration Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `APPROVAL_NOTIFIER` | Yes | `none` | Set to `teams` to enable |
| `TEAMS_WEBHOOK_URL` | Yes | — | Incoming webhook URL for the Teams channel |
| `CALSETA_BASE_URL` | Recommended | `http://localhost:8000` | Used in card instructions for approve/reject URLs |
| `APPROVAL_DEFAULT_TIMEOUT_SECONDS` | No | `3600` | Approval request expiry (seconds) |

---

## Future: Interactive Buttons via Azure Bot Framework

True click-to-approve in Teams requires the Azure Bot Framework. The architecture would be:

1. **Register an Azure AD app** with Bot Channel Registration
2. **Create a messaging endpoint** in Calseta (e.g., `POST /v1/approvals/callback/teams/bot`)
3. **Use `Action.Submit`** in the Adaptive Card instead of text instructions
4. **Validate incoming requests** using the Bot Framework JWT token
5. **Process the action** the same way the Slack callback does — extract the decision, call `process_approval_decision()`

This is tracked for a future release. The REST-based flow in v1 is fully functional and does not block any agent workflows.
