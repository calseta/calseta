# Approval Notifications — Test Plan (Slack & Teams)

Testing the workflow approval gate with real Slack and Teams notifications.

---

## Current State

### What's Built

| Component | Status | Notes |
|---|---|---|
| `SlackApprovalNotifier` | Built | Sends Block Kit messages with Approve/Reject buttons |
| `POST /v1/approvals/callback/slack` | Built | Handles Slack interactive payloads, HMAC signature verification |
| `TeamsApprovalNotifier` | Built | Sends Adaptive Cards via incoming webhook |
| `POST /v1/approvals/callback/teams` | Stub | Returns info message (interactive buttons not supported) |
| REST approve/reject endpoints | Built | `POST /v1/workflow-approvals/{uuid}/approve\|reject` |
| `NullApprovalNotifier` | Built | No-op for REST-only testing |

### What's Missing

| Gap | Impact | Fix |
|---|---|---|
| **Slack: No public URL for callbacks** | Slack can send approval messages, but button clicks fail — Slack can't POST back to `localhost:8000` | Tunnel (ngrok/cloudflared) or deploy to a publicly reachable host |
| **Slack: No Slack App created** | Need a Slack App with bot token, interactivity URL, and signing secret | One-time setup in Slack API console |
| **Teams: `Action.OpenUrl` → browser GET** | Approve/Reject buttons open a URL in the browser, but the endpoints require POST — clicking does nothing useful | Replace with a simple Markdown link approach or accept REST-only for v1 |
| **Teams: No interactive callback support** | Teams incoming webhooks fundamentally cannot receive button callbacks (requires Azure Bot Framework) | v1 design decision: Teams approvers use REST API; card is informational |
| **`APPROVAL_DEFAULT_CHANNEL` not in Settings** | Minor: `slack_notifier.py` references it via `getattr` fallback, but it's not a declared config field | Add to `app/config.py` `Settings` class |

---

## Part 1: Slack Approval Testing

### 1.1 — Create a Slack App (one-time setup)

1. Go to https://api.slack.com/apps → **Create New App** → **From scratch**
2. Name: `Calseta Approvals` (or similar), pick your workspace
3. **OAuth & Permissions** → Add bot scopes:
   - `chat:write` (send messages)
   - `chat:write.public` (post to channels the bot hasn't joined)
4. **Install to Workspace** → copy the **Bot User OAuth Token** (`xoxb-...`)
5. **Basic Information** → copy the **Signing Secret**

### 1.2 — Expose Local Instance via Tunnel

For local testing, Slack needs to reach your callback URL.

**Option A: ngrok (simplest)**
```bash
# Install: brew install ngrok
ngrok http 8000
# Note the https URL, e.g. https://abc123.ngrok-free.app
```

**Option B: Cloudflare Tunnel**
```bash
# Install: brew install cloudflared
cloudflared tunnel --url http://localhost:8000
```

Copy the public HTTPS URL.

### 1.3 — Configure Slack Interactivity

1. Back in the Slack App settings → **Interactivity & Shortcuts** → toggle ON
2. Set **Request URL** to:
   ```
   https://<your-tunnel-url>/v1/approvals/callback/slack
   ```
3. Save changes

### 1.4 — Configure Calseta Environment

Add to your `.env`:
```bash
APPROVAL_NOTIFIER=slack
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
APPROVAL_DEFAULT_CHANNEL=C0123456789   # Channel ID (right-click channel → View channel details → copy ID)
```

Restart the API server and worker.

### 1.5 — End-to-End Test Steps

**Setup prerequisites:**
```bash
# 1. Create an API key (needs admin scope to create keys)
curl -s http://localhost:8000/v1/api-keys \
  -H "Authorization: Bearer <admin-key>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Agent", "scopes": ["alerts:read", "workflows:execute", "approvals:write"]}' | jq .

# Save the returned cai_... key

# 2. List workflows and find one (or create one)
curl -s http://localhost:8000/v1/workflows \
  -H "Authorization: Bearer <key>" | jq '.data[] | {uuid, name, state, approval_mode}'

# 3. Enable approval gate on a workflow (must be active)
curl -s -X PATCH http://localhost:8000/v1/workflows/<workflow-uuid> \
  -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" \
  -d '{"approval_mode": "always", "risk_level": "high", "approval_timeout_seconds": 3600}' | jq .
```

**Trigger as agent:**
```bash
curl -s -X POST http://localhost:8000/v1/workflows/<workflow-uuid>/execute \
  -H "Authorization: Bearer cai_<agent-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "indicator_type": "ip",
    "indicator_value": "203.0.113.50",
    "trigger_source": "agent",
    "reason": "Detected suspicious outbound traffic to known C2 infrastructure at 203.0.113.50",
    "confidence": 0.87
  }' | jq .
```

**Expected result:**
- API returns `202` with `status: "pending_approval"` and `approval_request_uuid`
- Slack channel receives a Block Kit message with:
  - `[HIGH RISK] Workflow Approval: <workflow-name>`
  - Indicator, confidence, expiry details
  - Agent's reason
  - Green **Approve** and red **Reject** buttons

**Test the button click:**
- Click **Approve** in Slack
- Slack POSTs to `https://<tunnel>/v1/approvals/callback/slack`
- The callback handler extracts `approve:<uuid>` from `action_id`
- Calls `process_approval_decision(approved=True, responder_id=<slack_user_id>)`
- Worker picks up `execute_approved_workflow_task` and runs the workflow
- Follow-up message appears in the Slack thread with execution result

**Verify:**
```bash
# Check approval request status
curl -s http://localhost:8000/v1/workflow-approvals/<approval-uuid> \
  -H "Authorization: Bearer <key>" | jq '{status, responder_id, responded_at, execution_result}'

# Check workflow runs
curl -s http://localhost:8000/v1/workflows/<workflow-uuid>/runs \
  -H "Authorization: Bearer <key>" | jq '.data[0] | {uuid, status, trigger_type, result_data}'
```

### 1.6 — Slack Test Matrix

| # | Scenario | Expected |
|---|---|---|
| 1 | Agent triggers workflow with `approval_mode="always"` | 202 + Slack message with buttons |
| 2 | Click **Approve** button in Slack | Approval processed, workflow executes, thread reply posted |
| 3 | Click **Reject** button in Slack | Rejection recorded, no execution, thread reply posted |
| 4 | Click button on already-decided request | 200 OK returned to Slack (error logged, no crash) |
| 5 | Click button on expired request | 200 OK returned to Slack (error logged, no crash) |
| 6 | Human triggers workflow with `approval_mode="agent_only"` | Bypasses gate, executes immediately |
| 7 | Agent triggers workflow with `approval_mode="never"` | No approval, executes immediately |
| 8 | Agent triggers without `reason` or `confidence` | 422 validation error |
| 9 | `SLACK_SIGNING_SECRET` set + tampered request | 403 Forbidden |
| 10 | `SLACK_SIGNING_SECRET` not set + any request | Signature check skipped (accepted) |
| 11 | Agent triggers workflow with `approval_mode="agent_only"` | 202 + Slack message with buttons |
| 12 | Human triggers workflow with `approval_mode="always"` | 202 + Slack message with buttons (approval required for all triggers) |

---

## Part 2: Teams Approval Testing

### Current Limitations (v1)

Teams incoming webhooks **cannot** receive interactive button callbacks. This is a fundamental Teams platform limitation — interactive cards require Azure Bot Framework registration, which is out of v1 scope.

**What works today:**
- Card is delivered to the Teams channel with approval details
- `Action.OpenUrl` buttons open the REST endpoint URLs in the browser

**What doesn't work:**
- Clicking Approve/Reject in Teams opens a GET request in the browser — but the endpoints are POST. The user sees a "Method Not Allowed" error or a blank page.

### 2.1 — Fix: Improve Teams Card UX for v1

Since interactive buttons aren't possible, the Teams card should be **informational** with clear instructions instead of misleading `Action.OpenUrl` buttons. Two options:

**Option A: Remove buttons, add copyable commands (recommended for v1)**

Replace the `Action.OpenUrl` actions with a text block containing curl commands or a link to the Calseta approval dashboard (future UI). The card becomes a notification-only card with:
```
To approve: POST /v1/workflow-approvals/{uuid}/approve
To reject:  POST /v1/workflow-approvals/{uuid}/reject

Use curl, Postman, or the Calseta CLI to submit your decision.
```

**Option B: Link to a lightweight approval page (future)**

Build a minimal `GET /v1/workflow-approvals/{uuid}/decide` HTML page that renders approve/reject buttons in the browser. The Teams `Action.OpenUrl` buttons link to this page. This is a small amount of extra work but gives Teams users a click-to-approve experience without Azure Bot Framework.

### 2.2 — Teams Test Setup

1. Create a Teams channel (or use existing)
2. Add an incoming webhook connector to the channel → copy the webhook URL
3. Add to `.env`:
   ```bash
   APPROVAL_NOTIFIER=teams
   TEAMS_WEBHOOK_URL=https://outlook.webhook.office.com/webhookb2/...
   CALSETA_BASE_URL=https://<your-public-url>   # or localhost for card-only test
   ```
4. Restart API server and worker

### 2.3 — Teams Test Steps

**Trigger as agent** (same curl as Slack test in 1.5).

**Expected result:**
- API returns `202` with `pending_approval`
- Teams channel receives an Adaptive Card with approval details
- Buttons are present but non-functional for POST actions (known limitation)

**Approve via REST:**
```bash
curl -s -X POST http://localhost:8000/v1/workflow-approvals/<approval-uuid>/approve \
  -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" \
  -d '{"responder_id": "jorge"}' | jq .
```

**Verify:** Follow-up Adaptive Card posted to Teams with execution result.

### 2.4 — Teams Test Matrix

| # | Scenario | Expected |
|---|---|---|
| 1 | Agent triggers workflow | 202 + Teams Adaptive Card delivered |
| 2 | Approve via REST API | Workflow executes, result card posted |
| 3 | Reject via REST API | Rejection recorded, result card posted |
| 4 | `TEAMS_WEBHOOK_URL` not set | `is_configured()` returns False, notification skipped |
| 5 | Webhook URL returns error | Error logged, approval request still created (approvers use REST) |

---

## Part 3: Implementation Tasks

### Priority 1: Required for Testing

- [ ] **Add `APPROVAL_DEFAULT_CHANNEL` to `app/config.py` Settings class** — currently referenced via `getattr` fallback only
- [ ] **Create Slack App** and configure interactivity URL
- [ ] **Set up tunnel** (ngrok or cloudflared) for local Slack callback testing

### Priority 2: Teams UX Fix

- [ ] **Update `TeamsApprovalNotifier._build_approval_card()`** — replace `Action.OpenUrl` buttons with informational text block containing REST API instructions (since OpenUrl does GET, not POST)

### Priority 3: Nice-to-Have (Future)

- [ ] **Lightweight approval HTML page** — `GET /v1/workflow-approvals/{uuid}/decide` renders a simple HTML page with Approve/Reject buttons (enables Teams click-to-approve)
- [ ] **Slack callback: update original message** — after decision, update the original Block Kit message to remove buttons and show the decision inline (prevents double-clicks)
- [ ] **Azure Bot Framework integration** — enable true Teams interactive buttons (v2 scope)

---

## Environment Variable Reference

| Variable | Required For | Example |
|---|---|---|
| `APPROVAL_NOTIFIER` | All | `slack`, `teams`, or `none` |
| `APPROVAL_DEFAULT_CHANNEL` | Slack | `C0123456789` |
| `SLACK_BOT_TOKEN` | Slack | `xoxb-1234-5678-abcdef` |
| `SLACK_SIGNING_SECRET` | Slack (recommended) | `a1b2c3d4e5f6...` |
| `TEAMS_WEBHOOK_URL` | Teams | `https://outlook.webhook.office.com/webhookb2/...` |
| `CALSETA_BASE_URL` | Teams | `https://calseta.example.com` |
| `APPROVAL_DEFAULT_TIMEOUT_SECONDS` | All | `3600` (default) |
