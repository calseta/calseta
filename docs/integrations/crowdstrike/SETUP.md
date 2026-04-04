# CrowdStrike Falcon — Action Integration Setup

## What Calseta Does With This Integration

Calseta uses the CrowdStrike Falcon API to contain and release endpoints when an agent determines a host is compromised. Specifically:

- **isolate_host** — Network-isolates the endpoint (Falcon contain action). The host loses network connectivity except to the CrowdStrike cloud.
- **lift_containment** — Removes network isolation from a previously contained host.

These are high-consequence actions. Approval mode defaults to `"always"` — a human approval step is required before execution unless explicitly overridden.

---

## Required API Permissions (Least-Privilege)

Create a dedicated API client in the Falcon console with these scopes only:

| Scope | Permission Level | Why |
|-------|-----------------|-----|
| Hosts | Read | Resolves device IDs |
| Hosts | Write | Required for contain/lift actions |

No other scopes are required. Do not grant `Event streams`, `Detection`, or admin scopes.

---

## Credential Creation Steps

1. Log in to the [CrowdStrike Falcon console](https://falcon.crowdstrike.com).
2. Navigate to **Support & Resources → API Clients and Keys**.
3. Click **Create API client**.
4. Name: `Calseta Response Integration` (or your preferred name).
5. Under **API Scopes**, enable:
   - **Hosts** → Read + Write
6. Click **Create**.
7. Copy the **Client ID** and **Client Secret** — the secret is shown only once.
8. Note your **Base URL** (shown in the console, e.g. `https://api.crowdstrike.com` for US-1 or `https://api.eu-1.crowdstrike.com` for EU-1).

---

## Environment Variables

Add to your `.env` file (or secrets manager):

```
CROWDSTRIKE_CLIENT_ID=<your_client_id>
CROWDSTRIKE_CLIENT_SECRET=<your_client_secret>
CROWDSTRIKE_BASE_URL=https://api.crowdstrike.com   # omit for US-1 default
```

Supported base URLs by cloud:
- US-1: `https://api.crowdstrike.com`
- US-2: `https://api.us-2.crowdstrike.com`
- EU-1: `https://api.eu-1.crowdstrike.com`
- US-GOV-1: `https://api.laggar.gcw.crowdstrike.com`

---

## Authentication Flow

Calseta uses **OAuth2 client credentials** (no user login required):

```
POST /oauth2/token
Content-Type: application/x-www-form-urlencoded

client_id=<CLIENT_ID>&client_secret=<CLIENT_SECRET>
```

Returns a short-lived `access_token` (30-minute TTL). Calseta obtains a fresh token per action execution — no token caching at this time.

---

## Containment API

### Isolate a host

```
POST /devices/entities/devices-actions/v2?action_name=contain
Authorization: Bearer <token>
Content-Type: application/json

{"ids": ["<device_id>"]}
```

Expected response: HTTP 202 with resources array.

### Lift containment

```
POST /devices/entities/devices-actions/v2?action_name=lift_containment
Authorization: Bearer <token>
Content-Type: application/json

{"ids": ["<device_id>"]}
```

### Finding the device ID

The `device_id` (also called `device_id` or `host_id` in CrowdStrike docs) is the CrowdStrike-internal host identifier. Your agent should include this in `action.payload.device_id` when proposing the action. It can be retrieved from:

- CrowdStrike detection payload (`behaviors[].device.device_id`)
- Falcon console host detail URL (last path segment)
- `GET /devices/entities/devices/v2?ids=<hostname>` if resolving from hostname

---

## Rate Limits

CrowdStrike API rate limits vary by endpoint tier. The containment endpoints are not heavily rate-limited for typical SOC use — expect ~100 req/min per client. If you hit `HTTP 429`, back off and retry after the `X-RateLimit-RetryAfter` header value.

---

## Common Failure Modes

| Error | Cause | Fix |
|-------|-------|-----|
| `HTTP 401 on /oauth2/token` | Invalid client ID or secret | Verify credentials in Falcon console; regenerate if needed |
| `HTTP 403 on /devices/entities/devices-actions/v2` | API client missing Hosts Write scope | Edit the API client and add Hosts Write |
| `HTTP 404 for device ID` | Device not found or wrong base URL | Verify device_id; check CROWDSTRIKE_BASE_URL matches your CrowdStrike cloud |
| `HTTP 400 "invalid action_name"` | Typo in action_name parameter | Must be exactly `contain` or `lift_containment` |
| Token obtained but action fails | Device already in target state | Idempotent — already contained or already uncontained |

---

## Security Notes

- Store `CROWDSTRIKE_CLIENT_SECRET` in your secrets manager (Azure Key Vault, AWS Secrets Manager) — not in `.env` in production.
- Rotate the API client secret every 90 days.
- Calseta never stores the secret in the database — it is read from environment/secrets manager at startup.
- All containment actions require human approval by default (`approval_mode = "always"`). Do not lower this without understanding the blast radius.
