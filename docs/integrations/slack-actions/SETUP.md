# Slack — Action Integration Setup

## What Calseta Does With This Integration

Calseta uses the Slack Web API to send security notifications, post alert summaries, create incident channels, and send user validation DMs. Supported action subtypes:

- **send_alert** — Posts a formatted alert message to a Slack channel.
- **notify_oncall** — Posts an urgent-formatted message to a channel or DM (typically for on-call paging).
- **create_channel** — Creates a new Slack channel for incident response.
- **validate_user_activity** — Sends a DM to the affected user asking them to confirm or deny the security activity (requires `SlackUserValidationIntegration` with DB access).

Approval mode defaults to `"never"` for all Slack actions — these are notification-class actions that do not require human sign-off before execution.

Note: Calseta also uses `SLACK_BOT_TOKEN` for approval notifications (`SlackApprovalNotifier`). The action integration reuses the same token. One Slack app is sufficient for all Calseta Slack features.

---

## Required Bot Token Scopes (Least-Privilege)

| Scope | Why |
|-------|-----|
| `chat:write` | Post messages to channels and DMs |
| `channels:manage` | Create public channels |
| `groups:write` | Create private channels |
| `im:write` | Open DM channels for user validation |
| `users:read.email` | Look up users by email (user validation only) |

If you are only using `send_alert` / `notify_oncall`, only `chat:write` is required. Add the others when enabling user validation or incident channel creation.

---

## Creating a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App → From scratch**.
2. Name: `Calseta` (or your preferred name). Select your workspace.
3. Click **Create App**.

### Add OAuth Scopes

4. In the left sidebar, click **OAuth & Permissions**.
5. Scroll to **Scopes → Bot Token Scopes**.
6. Add the scopes from the table above.

### Install to Workspace

7. Scroll up on **OAuth & Permissions** and click **Install to Workspace**.
8. Review and click **Allow**.
9. Copy the **Bot User OAuth Token** (starts with `xoxb-`).

---

## Environment Variables

```
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_SIGNING_SECRET=your-signing-secret   # only needed for incoming webhooks/events
```

The `SLACK_SIGNING_SECRET` is only required if you are using Slack Events API for approval callbacks or user validation responses. For outbound-only messaging, only `SLACK_BOT_TOKEN` is needed.

---

## Inviting the Bot to Channels

The Calseta bot must be invited to any channel before it can post there:

```
/invite @Calseta
```

This applies to:
- Alert notification channels (`action.payload.channel`)
- Approval notification channels (`APPROVAL_DEFAULT_CHANNEL`)

For DMs, no invitation is needed — the bot can open DMs with any workspace member.

---

## Channel IDs vs Channel Names

Calseta always uses **channel IDs** (e.g. `C0123456789`), not channel names. Channel names can change; IDs are stable.

To find a channel ID:
1. Right-click the channel in Slack → **Copy link**.
2. The ID is the last segment of the URL: `https://app.slack.com/client/{workspace_id}/{channel_id}`.

Or use the Slack API:
```
GET https://slack.com/api/conversations.list
Authorization: Bearer xoxb-...
```

---

## User Validation Setup

For `validate_user_activity` actions, Calseta loads a `UserValidationTemplate` from the database by the name specified in `action.payload.template_name`. Create templates via:

```bash
curl -X POST http://localhost:8000/v1/user-validation-templates \
  -H "Authorization: Bearer cai_..." \
  -H "Content-Type: application/json" \
  -d '{
    "name": "default_activity_confirm",
    "message_body": "Hi! Our system detected the following activity:\n\n*Alert:* {{alert.title}}\n*Time:* {{alert.occurred_at}}\n\nWas this initiated by you?",
    "response_type": "confirm_deny",
    "confirm_label": "Yes, that was me",
    "deny_label": "No, that was not me"
  }'
```

Supported substitution tokens in `message_body`:
- `{{alert.title}}`
- `{{alert.severity}}`
- `{{alert.source_name}}`
- `{{alert.occurred_at}}`
- `{{alert.alert_uuid}}`
- `{{assignment_id}}`

If the template is not found or DB is unavailable, Calseta falls back to a default message.

---

## Rate Limits

Slack's Web API rate limits vary by method tier:

| Method | Tier | Limit |
|--------|------|-------|
| `chat.postMessage` | Tier 3 | ~50 req/min per channel |
| `conversations.create` | Tier 2 | ~20 req/min |
| `conversations.open` | Tier 3 | ~50 req/min |
| `users.lookupByEmail` | Tier 3 | ~50 req/min |

All 429 responses from Slack include `Retry-After` header. At normal SOC volumes, rate limits are not a concern.

---

## Common Failure Modes

| Error | Cause | Fix |
|-------|-------|-----|
| `not_authed` | `SLACK_BOT_TOKEN` is invalid or missing | Verify token in Slack app config; check env var |
| `channel_not_found` | Bot not in channel, or wrong channel ID | `/invite @Calseta` in the channel; verify channel ID |
| `is_archived` | Target channel is archived | Unarchive the channel or update the target channel |
| `users_not_found` (DM) | Slack user ID not in workspace | Verify user ID; check if user has left the workspace |
| `missing_scope` | Bot token missing required scope | Add scope in Slack app config → OAuth & Permissions → reinstall |
| `invalid_auth` | Token revoked or app uninstalled | Reinstall the app and copy the new `xoxb-` token |
| Template not rendered | Wrong token syntax in message_body | Use `{{alert.title}}` not `{alert.title}` or `$alert.title` |

---

## Security Notes

- Store `SLACK_BOT_TOKEN` in your secrets manager in production — not in `.env`.
- Use a dedicated Calseta Slack app rather than a personal token. Personal tokens expire; bot tokens are stable.
- Restrict the bot to specific channels using Slack's channel posting restrictions if your workspace requires it.
- The `SLACK_SIGNING_SECRET` is used to verify that incoming events/interactions are from Slack. Always verify request signatures before processing approval callbacks.
