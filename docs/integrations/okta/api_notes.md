# Okta API Notes

Source: Okta Management API
Reference: https://developer.okta.com/docs/api/openapi/okta-management/management/tag/User/

---

## Authentication

**API Token (service account — simplest for server-to-server):**
```
Authorization: SSWS {OKTA_API_TOKEN}
```

Tokens are created in Okta Admin Console: Security > API > Tokens > Create Token. Tokens are associated with a specific admin account and inherit that account's permissions.

**OAuth 2.0 Client Credentials (preferred for production):**
```
POST https://{OKTA_DOMAIN}/oauth2/v1/token
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&scope=okta.users.read okta.users.manage okta.sessions.manage
&client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
&client_assertion={signed_jwt}
```
Then use: `Authorization: Bearer {access_token}`

For Calseta AI v1, SSWS API token is the default (`OKTA_API_TOKEN` env var). OAuth 2.0 is supported via the same auth abstraction.

Base URL format: `https://{OKTA_DOMAIN}/api/v1/...`
`OKTA_DOMAIN` is the Okta organization domain, e.g. `company.okta.com` or `company.okta-emea.com`.

---

## Key Endpoints Used by Calseta AI

### Get user by ID or login
```
GET /api/v1/users/{userId}
GET /api/v1/users/{login}     (URL-encode email, e.g. jdoe%40company.com)
Authorization: SSWS {token}
```

### Search users
```
GET /api/v1/users?filter=profile.email eq "jdoe@company.com"&limit=1
GET /api/v1/users?search=profile.email eq "jdoe@company.com"
```
Use `search` parameter for full Okta expression language. Use `filter` for simple equality. `limit` max = 200.

Pagination: response includes `Link` header with `rel="next"` URL when more pages exist. Parse the `Link` header — do not construct `next` URL manually.

### List user's active sessions
```
GET /api/v1/users/{userId}/sessions
```

---

## Request/Response Field Reference

### User object

```json
{
  "id": "00u1abcdef234567890AB",
  "status": "ACTIVE",
  "created": "2023-01-15T09:00:00.000Z",
  "activated": "2023-01-15T09:01:00.000Z",
  "statusChanged": "2023-01-15T09:01:00.000Z",
  "lastLogin": "2024-01-15T08:30:00.000Z",
  "lastUpdated": "2024-01-14T10:00:00.000Z",
  "passwordChanged": "2024-01-01T00:00:00.000Z",
  "type": { "id": "oty1abc..." },
  "profile": {
    "login": "jdoe@company.com",
    "firstName": "John",
    "lastName": "Doe",
    "middleName": null,
    "honorificPrefix": null,
    "honorificSuffix": null,
    "email": "jdoe@company.com",
    "title": "Security Analyst",
    "displayName": "John Doe",
    "nickName": null,
    "profileUrl": null,
    "secondEmail": null,
    "mobilePhone": "+1-555-555-5555",
    "primaryPhone": null,
    "streetAddress": null,
    "city": null,
    "state": null,
    "zipCode": null,
    "countryCode": "US",
    "postalAddress": null,
    "preferredLanguage": "en",
    "locale": "en_US",
    "timezone": "America/Los_Angeles",
    "userType": "Employee",
    "employeeNumber": "12345",
    "costCenter": null,
    "organization": "IT",
    "division": "Security",
    "department": "SOC",
    "managerId": null,
    "manager": null
  },
  "credentials": {
    "password": {},
    "recovery_question": { "question": "What is the name of your first pet?" },
    "provider": { "type": "OKTA", "name": "OKTA" }
  },
  "_links": {
    "self": { "href": "https://company.okta.com/api/v1/users/00u1abc..." },
    "activate": { ... },
    "resetPassword": { ... },
    "expirePassword": { ... },
    "forgotPassword": { ... },
    "changePassword": { ... },
    "changeRecoveryQuestion": { ... }
  }
}
```

### Key user fields for Calseta AI

| Field | Type | Notes |
|---|---|---|
| `id` | string | Okta user ID (opaque, `00u` prefix) — use as reference |
| `status` | string (enum) | User lifecycle status — see enum below |
| `created` | string (ISO 8601) | When user was created |
| `activated` | string (ISO 8601) | When user was activated |
| `lastLogin` | string (ISO 8601) | Last successful login time |
| `lastUpdated` | string (ISO 8601) | Last profile update |
| `passwordChanged` | string (ISO 8601) | Last password change |
| `profile.login` | string | Username (usually email) — maps to Calseta `account` indicator value |
| `profile.email` | string | Primary email |
| `profile.firstName` | string | Given name |
| `profile.lastName` | string | Family name |
| `profile.displayName` | string | Full display name |
| `profile.mobilePhone` | string | Mobile phone |
| `profile.department` | string | Department |
| `profile.title` | string | Job title |
| `profile.organization` | string | Organization |
| `profile.manager` | string | Manager name |
| `profile.employeeNumber` | string | Employee ID |
| `profile.userType` | string | Custom type e.g. `"Employee"`, `"Contractor"` |

### User `status` enum

| Status | Meaning |
|---|---|
| `STAGED` | User created but not yet activated |
| `PROVISIONED` | Activated but password not set |
| `ACTIVE` | Normal active user |
| `RECOVERY` | In password recovery flow |
| `LOCKED_OUT` | Account locked due to failed logins |
| `PASSWORD_EXPIRED` | Password expired |
| `SUSPENDED` | Suspended by admin |
| `DEPROVISIONED` | Deactivated/deprovisioned |

### Enrichment field extraction paths (Calseta `enrichment_field_extractions` seeding)

| `target_key` | `source_path` | Notes |
|---|---|---|
| `status` | `status` | User lifecycle status |
| `login` | `profile.login` | Username |
| `email` | `profile.email` | Email address |
| `first_name` | `profile.firstName` | Given name |
| `last_name` | `profile.lastName` | Family name |
| `display_name` | `profile.displayName` | Full name |
| `title` | `profile.title` | Job title |
| `department` | `profile.department` | Department |
| `user_type` | `profile.userType` | Employee/Contractor/etc. |
| `last_login` | `lastLogin` | ISO 8601 |
| `password_changed` | `passwordChanged` | ISO 8601 |
| `employee_number` | `profile.employeeNumber` | Employee ID |

---

## Available Automation Endpoints (for pre-built workflows)

All lifecycle endpoints: `POST` with empty body (no request body needed). Returns `200 OK` on success with the updated user object, or `204 No Content` for session operations.

### Suspend user
```
POST /api/v1/users/{userId}/lifecycle/suspend
Authorization: SSWS {token}
```
Effect: Sets status to `SUSPENDED`. User cannot log in. Sessions remain valid until revoked. Reversible with unsuspend.

### Unsuspend user
```
POST /api/v1/users/{userId}/lifecycle/unsuspend
Authorization: SSWS {token}
```
Effect: Returns user to `ACTIVE` status.

### Reset password (send reset email)
```
POST /api/v1/users/{userId}/lifecycle/reset_password?sendEmail=true
Authorization: SSWS {token}
```
Effect: Sends password reset email to user. Returns `200 OK` with `{ resetPasswordUrl: "..." }` (link also valid for admin-driven reset without email if `sendEmail=false`).

Query parameter `sendEmail`:
- `true` — sends reset email to user (default for agent-driven workflows)
- `false` — returns reset URL for admin to share out-of-band

### Expire password (force change on next login)
```
POST /api/v1/users/{userId}/lifecycle/expire_password
Authorization: SSWS {token}
```
Effect: Marks password as expired. User must set new password at next login. Does NOT invalidate existing sessions.

### Revoke all user sessions
```
DELETE /api/v1/users/{userId}/sessions
Authorization: SSWS {token}
```
Effect: Immediately invalidates all active sessions for the user. User is logged out everywhere. Does NOT change user status or password. Returns `204 No Content`.

### Deactivate user (irreversible within session)
```
POST /api/v1/users/{userId}/lifecycle/deactivate
Authorization: SSWS {token}
```
Effect: Sets status to `DEPROVISIONED`. All sessions revoked. Requires reactivation flow to restore. Use with caution.

### Get user's active sessions
```
GET /api/v1/users/{userId}/sessions
Authorization: SSWS {token}
```
Returns array of session objects: `[{ id, login, expiresAt, status, lastFactorVerification, amr, idp, mfaActive, lastPasswordVerification }]`

### List user's enrolled MFA factors
```
GET /api/v1/users/{userId}/factors
Authorization: SSWS {token}
```
Returns array of factor objects: `[{ id, factorType, provider, status, created, lastUpdated, profile }]`

Factor types: `token:software:totp` (TOTP/Google Authenticator), `token:hardware` (YubiKey), `question` (security question), `sms`, `call`, `email`, `push` (Okta Verify), `web` (WebAuthn), `token` (HOTP)

---

## Rate Limits

Okta enforces rate limits per endpoint group. Limits are enforced per Okta org (not per API key).

| Endpoint group | Requests per minute |
|---|---|
| GET `/api/v1/users/{id}` | 600 |
| GET `/api/v1/users` (list/search) | 600 |
| POST lifecycle endpoints (`/lifecycle/*`) | 600 |
| DELETE `/api/v1/users/{id}/sessions` | 600 |
| GET `/api/v1/users/{id}/factors` | 600 |

Rate limit response: `429 Too Many Requests`
Response headers:
- `X-Rate-Limit-Limit` — limit for this endpoint
- `X-Rate-Limit-Remaining` — remaining requests this window
- `X-Rate-Limit-Reset` — Unix timestamp when limit resets
- `X-Okta-Request-Id` — request ID for Okta support

Okta also enforces **dynamic rate limits** that tighten when API usage spikes. Watch for 429s even when below stated limits.

---

## Known Quirks / Edge Cases

- **User lookup by email vs login**: In Okta, `profile.email` and `profile.login` can differ. For account indicators extracted from alerts (e.g. email from a phishing alert), try `search=profile.email eq "{email}"` first, then `profile.login eq "{email}"`. Handle not-found gracefully.
- **`id` format is opaque**: Okta user IDs (`00u...`) are not UUIDs. They are 20-character strings with `00u` prefix. Do not try to parse them.
- **Sessions vs password**: `DELETE /sessions` revokes active SSO sessions but does NOT change the password or require password reset. Combine with `reset_password` for full account lockdown.
- **Lifecycle endpoint ordering**: For full incident response: `suspend` → `DELETE /sessions` → `reset_password?sendEmail=false`. Do not do all three atomically — Okta may throttle. Insert brief delays or implement retry.
- **`sendEmail=false` on reset_password**: Returns a short-lived reset URL in the response. This URL expires in 1 hour. Log it to the workflow run output; do NOT store it in the database.
- **Deactivate vs Suspend**: `deactivate` sets `DEPROVISIONED` status — much harder to reverse (requires full reactivation flow). `suspend` is safer for incident response (easily reversed). Default pre-built workflow uses `suspend`, not `deactivate`.
- **Factor enrollment check**: `GET /api/v1/users/{id}/factors` returns enrolled factors, not available factors. An empty array means no MFA enrolled — this is a high-risk signal for agents to surface.
- **Group membership**: `GET /api/v1/users/{id}/groups` returns group memberships. Useful for privilege assessment in workflows but not needed for v1 enrichment.
- **Pagination on user search**: Results come back with `Link` headers. Parse `rel="next"` link, not a page number. Maximum `limit=200` per page.
- **Rate limit burst**: Okta allows short bursts above per-minute limits. Don't rely on this — design for steady-state within limits.
