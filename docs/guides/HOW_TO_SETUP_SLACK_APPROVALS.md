# How to Set Up Slack Approval Notifications

This guide walks through connecting Calseta to Slack so that workflow approval requests are delivered as interactive messages. When an AI agent triggers a high-risk workflow, a Block Kit message with Approve/Reject buttons appears in your Slack channel. Clicking a button processes the decision immediately — no context-switching to a terminal or API client.

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
    ├─ Worker sends Block Kit message to Slack channel
    │       └─ Approve / Reject buttons (action_id: "approve:{uuid}" / "reject:{uuid}")
    │
    ├─ Human clicks button in Slack
    │       └─ Slack POSTs interactive payload to /v1/approvals/callback/slack
    │
    ├─ Callback handler validates signature, extracts decision
    │       └─ Calls process_approval_decision() → updates DB
    │
    └─ If approved: worker executes workflow, posts result in thread
```

---

## Prerequisites

- A Slack workspace where you have permission to install apps
- Calseta running locally (API server + worker)
- For local dev: a tunnel tool (ngrok or cloudflared) to expose localhost

---

## Step 1: Create a Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Name: `Calseta Approvals` (or whatever you prefer)
4. Pick your Slack workspace
5. Click **Create App**

### Add Bot Scopes

1. In the left sidebar: **OAuth & Permissions**
2. Scroll to **Scopes** → **Bot Token Scopes**
3. Add these scopes:

| Scope | Why |
|---|---|
| `chat:write` | Send approval messages and result notifications |
| `chat:write.public` | Post to channels the bot hasn't been invited to |
| `chat:write.customize` | Optional: allows custom bot name/icon per message |

4. Scroll up and click **Install to Workspace** → **Allow**
5. Copy the **Bot User OAuth Token** (`xoxb-...`) — you'll need this

### Get the Signing Secret

1. In the left sidebar: **Basic Information**
2. Under **App Credentials**, copy the **Signing Secret**
3. This is used to verify that incoming callbacks are genuinely from Slack (HMAC-SHA256)

---

## Step 2: Set Up a Tunnel (Local Dev Only)

Slack needs to reach your local Calseta instance to deliver button click events. In production, your Calseta API is already publicly reachable — skip this step.

### Option A: ngrok (recommended for quick testing)

```bash
# Install
brew install ngrok

# Start tunnel to your Calseta API
ngrok http 8000
```

Copy the HTTPS URL from the output (e.g., `https://abc123.ngrok-free.app`).

**Note:** Free ngrok URLs change every time you restart. You'll need to update the Slack interactivity URL each time (Step 3).

### Option B: Cloudflare Tunnel

```bash
# Install
brew install cloudflared

# Start tunnel
cloudflared tunnel --url http://localhost:8000
```

Copy the HTTPS URL from the output.

### Verify the Tunnel

```bash
curl https://<your-tunnel-url>/v1/health
# Should return: {"status": "ok"}
```

---

## Step 3: Enable Slack Interactivity

This tells Slack where to send button click payloads.

1. Back in your Slack App settings: [https://api.slack.com/apps](https://api.slack.com/apps) → select your app
2. Left sidebar: **Interactivity & Shortcuts**
3. Toggle **Interactivity** to **ON**
4. Set the **Request URL**:

```
https://<your-tunnel-or-domain>/v1/approvals/callback/slack
```

For local dev with ngrok:
```
https://abc123.ngrok-free.app/v1/approvals/callback/slack
```

5. Click **Save Changes**

**Important:** If you restart ngrok and get a new URL, you must update this field.

---

## Step 4: Configure Calseta

Add these to your `.env` file:

```bash
# Enable Slack notifications
APPROVAL_NOTIFIER=slack

# From Step 1: Bot User OAuth Token
SLACK_BOT_TOKEN=xoxb-1234567890-1234567890123-abcdefghijklmnopqrstuvwx

# From Step 1: Signing Secret (recommended — validates callback signatures)
SLACK_SIGNING_SECRET=a1b2c3d4e5f6789012345678abcdef01

# Channel ID for approval messages (right-click channel → View channel details → copy ID)
# Per-workflow channels override this via workflow.approval_channel
APPROVAL_DEFAULT_CHANNEL=C0123456789
```

Restart the API server and worker to pick up the new config.

---

## Step 5: Prepare a Workflow for Testing

You need an active workflow with approval enabled.

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

Make sure the workflow `state` is `"active"`. If it's `"draft"`, activate it:
```bash
curl -s -X PATCH http://localhost:8000/v1/workflows/<workflow-uuid> \
  -H "Authorization: Bearer <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{"state": "active"}' | jq .
```

---

## Step 6: Trigger as an Agent

```bash
curl -s -X POST http://localhost:8000/v1/workflows/<workflow-uuid>/execute \
  -H "Authorization: Bearer <your-api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "indicator_type": "ip",
    "indicator_value": "203.0.113.50",
    "trigger_source": "agent",
    "reason": "Detected suspicious outbound traffic to known C2 infrastructure",
    "confidence": 0.87
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

**In Slack:** A message appears in `#security-approvals` with:
- Header: `[HIGH RISK] Workflow Approval: <workflow-name>`
- Indicator details, confidence, expiry
- Agent's reason
- Green **Approve** and red **Reject** buttons

---

## Step 7: Click Approve or Reject

Click a button in Slack. Behind the scenes:

1. Slack POSTs an interactive payload to your callback URL
2. Calseta validates the HMAC signature (if `SLACK_SIGNING_SECRET` is set)
3. Extracts the decision from `action_id` (e.g., `approve:xxxxxxxx-xxxx-...`)
4. Calls `process_approval_decision()`
5. Updates the original message — replaces buttons with the decision text
6. If approved: enqueues the workflow for execution
7. Posts a threaded reply with the execution result

**Verify the outcome:**
```bash
# Check approval status
curl -s http://localhost:8000/v1/workflow-approvals/<approval-uuid> \
  -H "Authorization: Bearer <your-api-key>" | jq '{status, responder_id, responded_at}'

# Check workflow run
curl -s http://localhost:8000/v1/workflows/<workflow-uuid>/runs \
  -H "Authorization: Bearer <your-api-key>" | jq '.data[0]'
```

---

## Troubleshooting

### Message not appearing in Slack

| Symptom | Cause | Fix |
|---|---|---|
| No message at all | `SLACK_BOT_TOKEN` not set or invalid | Check `.env`, restart server |
| `channel_not_found` error in logs | Channel name/ID is wrong | Use channel ID (e.g., `C0123456789`) instead of `#name` |
| `not_in_channel` error in logs | Bot not invited to private channel | Invite the bot: `/invite @Calseta Approvals` in the channel |

### Button clicks not working

| Symptom | Cause | Fix |
|---|---|---|
| Slack shows "This didn't work" | Callback URL unreachable | Check tunnel is running, URL matches Slack config |
| 403 in Calseta logs | Signature validation failed | Verify `SLACK_SIGNING_SECRET` matches the app's signing secret |
| 403 "Request too old" | Clock skew > 5 minutes | Check system clock; or the tunnel is too slow |
| Button works but nothing happens | `process_approval_decision` raised | Check Calseta worker logs for errors |

### Tunnel issues

| Symptom | Cause | Fix |
|---|---|---|
| ngrok URL changed | Restarted ngrok | Update the Request URL in Slack App settings |
| Timeout on callback | Calseta API not running | Verify `curl http://localhost:8000/v1/health` works |
| ERR_NGROK_6024 | Free tier concurrent limit | Stop other ngrok tunnels |

---

## Configuration Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `APPROVAL_NOTIFIER` | Yes | `none` | Set to `slack` to enable |
| `SLACK_BOT_TOKEN` | Yes | — | Bot User OAuth Token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Recommended | — | Validates callback authenticity |
| `APPROVAL_DEFAULT_CHANNEL` | Yes | — | Channel ID for approval messages (e.g. `C0123456789`) |
| `APPROVAL_DEFAULT_TIMEOUT_SECONDS` | No | `3600` | Approval request expiry (seconds) |

Per-workflow overrides:
- `workflow.approval_channel` — overrides `APPROVAL_DEFAULT_CHANNEL` for that workflow
- `workflow.approval_timeout_seconds` — overrides default timeout
- `workflow.risk_level` — displayed in the Slack message header

---

## Security Notes

- **Always set `SLACK_SIGNING_SECRET` in production.** Without it, anyone who knows the callback URL can forge approval decisions.
- The signing secret validates that payloads genuinely originated from Slack using HMAC-SHA256. Calseta uses `hmac.compare_digest()` for timing-safe comparison.
- Requests older than 5 minutes are rejected to prevent replay attacks.
- The Slack user ID of the person who clicked the button is recorded as `responder_id` on the approval request.
- Bot tokens and signing secrets should be treated as secrets — never commit them to version control.
