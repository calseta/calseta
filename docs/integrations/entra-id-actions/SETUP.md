# Microsoft Entra ID — Action Integration Setup

## What Calseta Does With This Integration

Calseta uses the Microsoft Graph API to perform identity response actions when an agent determines a user account is compromised. Supported actions:

- **disable_user** — Sets `accountEnabled = false` on the user, preventing all sign-ins.
- **revoke_sessions** — Revokes all active refresh tokens and access tokens. The user is forced to re-authenticate.
- **force_mfa** — Deletes all non-password authentication methods (TOTP, phone, FIDO2, etc.), requiring the user to re-enroll MFA.

These are high-consequence, account-level actions. `bypass_confidence_override = True` is set — meaning the agent's confidence score is ignored and a human approval step is **always** required, regardless of confidence.

Note: Calseta already uses Entra ID for **enrichment** (looking up user details). The action integration reuses the same `ENTRA_*` environment variables. No separate credential setup is required if enrichment is already configured — but you must verify the application has the additional Graph API permissions listed below.

---

## Required API Permissions (Least-Privilege)

These are **Application permissions** (not Delegated) since Calseta runs as a background service with no signed-in user.

| Permission | Type | Why |
|-----------|------|-----|
| `User.ReadWrite.All` | Application | disable_user (PATCH accountEnabled), force_mfa (delete auth methods) |
| `Directory.ReadWrite.All` | Application | Required for revokeSignInSessions |

Prefer granting only `User.ReadWrite.All` first and verify `revoke_sessions` works in your tenant — some tenants require `Directory.ReadWrite.All` for that endpoint; others do not.

Do **not** grant `User.ManageIdentities.All` or global admin roles. The above two permissions are sufficient.

---

## Credential Creation Steps

If you have not already set up Entra enrichment credentials:

1. Sign in to the [Azure portal](https://portal.azure.com) as a Global Administrator or Privileged Role Administrator.
2. Navigate to **Microsoft Entra ID → App registrations**.
3. Click **New registration**.
   - Name: `Calseta`
   - Supported account types: **Accounts in this organizational directory only**
   - Redirect URI: leave blank
4. Click **Register**.
5. Copy the **Application (client) ID** and **Directory (tenant) ID** from the overview page.
6. Navigate to **Certificates & secrets → Client secrets → New client secret**.
   - Description: `Calseta production`
   - Expiry: 24 months (or per your rotation policy)
7. Copy the **Secret value** — shown only once.
8. Navigate to **API permissions → Add a permission → Microsoft Graph → Application permissions**.
9. Add: `User.ReadWrite.All` and optionally `Directory.ReadWrite.All`.
10. Click **Grant admin consent for {your tenant}** — required for application permissions.

---

## Environment Variables

```
ENTRA_TENANT_ID=<your_tenant_id>
ENTRA_CLIENT_ID=<your_app_client_id>
ENTRA_CLIENT_SECRET=<your_client_secret>
```

These are shared with the Entra enrichment provider. No additional variables required.

---

## Authentication Flow

Calseta uses **OAuth2 client credentials** (application identity, no user sign-in):

```
POST https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

client_id=<CLIENT_ID>&client_secret=<CLIENT_SECRET>
&scope=https://graph.microsoft.com/.default&grant_type=client_credentials
```

Returns an `access_token` with ~1-hour TTL. Calseta obtains a fresh token per action execution.

---

## Graph API Actions

### Disable user

```
PATCH https://graph.microsoft.com/v1.0/users/{user_id}
Authorization: Bearer <token>
Content-Type: application/json

{"accountEnabled": false}
```

`user_id` can be the Entra object ID (UUID) or the user principal name (UPN, e.g. `user@company.com`).

Expected response: HTTP 204 No Content.

### Revoke sign-in sessions

```
POST https://graph.microsoft.com/v1.0/users/{user_id}/revokeSignInSessions
Authorization: Bearer <token>
Content-Type: application/json
```

Expected response: HTTP 200 with `{"@odata.context": "...", "value": true}`.

### Force MFA re-enrollment

Calseta enumerates and deletes all authentication methods except password:

```
GET  https://graph.microsoft.com/v1.0/users/{user_id}/authentication/methods
DELETE https://graph.microsoft.com/v1.0/users/{user_id}/authentication/{methodType}/{methodId}
```

Supported method types deleted: `microsoftAuthenticatorMethods`, `phoneMethods`, `fido2Methods`, `windowsHelloForBusinessMethods`, `softwareOathMethods`, `temporaryAccessPassMethods`, `emailMethods`.

The password method (`#microsoft.graph.passwordAuthenticationMethod`) is never deleted.

---

## Finding User IDs

The `user_id` in `action.payload` should be the Entra object ID or UPN. Your agent can obtain this from:

- Entra enrichment results (`enrichment_results.entra.object_id`)
- Alert raw payload fields (e.g. `userPrincipalName` from Sentinel)
- `account` indicator type extracted from the alert

---

## Rate Limits

Microsoft Graph has tiered rate limits. For user management endpoints:
- ~200 requests per 10 seconds per app per tenant (typical)
- 429 responses include `Retry-After` header

Calseta does not batch requests — each action is one call. Rate limiting is not a concern at normal SOC volumes.

---

## Rollback

`disable_user` supports rollback: `EntraIDActionIntegration.rollback()` re-enables the account (`accountEnabled = true`). `revoke_sessions` and `force_mfa` do not have automatic rollback — session revocation expires naturally, and MFA re-enrollment requires the user to complete enrollment themselves.

---

## Common Failure Modes

| Error | Cause | Fix |
|-------|-------|-----|
| `HTTP 401 on token endpoint` | Invalid tenant ID, client ID, or secret | Verify all three `ENTRA_*` vars; check app registration in Azure portal |
| `HTTP 403 on PATCH /users` | Missing `User.ReadWrite.All` permission or no admin consent | Add permission + grant admin consent in Azure portal |
| `HTTP 403 on revokeSignInSessions` | May need `Directory.ReadWrite.All` | Add and consent that permission |
| `HTTP 404 for user_id` | User not found or wrong UPN | Verify user exists; try object ID instead of UPN |
| force_mfa deletes 0 methods | User has no MFA methods registered | Normal — nothing to delete; log as success |
| Token works but action returns 403 | App has wrong permission type (Delegated vs Application) | Verify you added Application permissions, not Delegated |

---

## Security Notes

- Store `ENTRA_CLIENT_SECRET` in your secrets manager — not in `.env` in production.
- Rotate the client secret before its expiry date. Set a calendar reminder.
- All three Entra action subtypes require human approval (`bypass_confidence_override = True`). This cannot be overridden by confidence score.
- Use a dedicated Entra app registration for Calseta rather than sharing credentials with other tools. This limits blast radius if the secret is compromised and makes audit logs unambiguous.
- Audit all account changes via Entra ID Sign-in logs and Audit logs (Entra portal → Monitoring).
