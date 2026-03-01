# Microsoft Entra (Graph API) Notes

Source: Microsoft Graph API v1.0
References:
- https://learn.microsoft.com/en-us/graph/api/user-get
- https://learn.microsoft.com/en-us/graph/api/user-revokesigninsessions
- https://learn.microsoft.com/en-us/graph/api/user-update
- https://learn.microsoft.com/en-us/graph/api/authentication-list-methods

---

## Authentication

Microsoft Graph uses OAuth 2.0 client credentials flow for server-to-server (daemon) applications. No user login required.

### Token acquisition
```
POST https://login.microsoftonline.com/{ENTRA_TENANT_ID}/oauth2/v2.0/token
Content-Type: application/x-www-form-urlencoded

client_id={ENTRA_CLIENT_ID}
&client_secret={ENTRA_CLIENT_SECRET}
&scope=https://graph.microsoft.com/.default
&grant_type=client_credentials
```

Response:
```json
{
  "token_type": "Bearer",
  "expires_in": 3599,
  "access_token": "eyJ0eXAiOiJKV1Qi..."
}
```

Cache the token until `expires_in` seconds have elapsed (subtract 60s buffer). Re-acquire before expiry.

All Graph API requests:
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

Base URL: `https://graph.microsoft.com/v1.0/`

### Required app registration
In Azure Entra ID (formerly Azure AD): App registrations > New registration > Certificates & secrets > API permissions > Microsoft Graph > Application permissions (not delegated).

---

## Key Endpoints Used by Calseta AI

### Get user by ID or UPN
```
GET /v1.0/users/{id | userPrincipalName}
GET /v1.0/users/{id}?$select=id,displayName,userPrincipalName,mail,accountEnabled,signInSessionsValidFromDateTime,lastPasswordChangeDateTime,department,jobTitle,officeLocation,usageLocation
```

Default properties returned (no `$select` needed for these):
`businessPhones, displayName, givenName, id, jobTitle, mail, mobilePhone, officeLocation, preferredLanguage, surname, userPrincipalName`

Non-default properties require explicit `$select`.

### List users (search)
```
GET /v1.0/users?$filter=userPrincipalName eq 'jdoe@company.com'&$select=id,displayName,userPrincipalName,mail,accountEnabled
GET /v1.0/users?$search="displayName:John Doe"&ConsistencyLevel=eventual
```
Pagination: response includes `@odata.nextLink` URL. Follow it directly — do not construct manually.

---

## Request/Response Field Reference

### User object — field reference

Default response (partial, always returned):
```json
{
  "id": "87d349ed-44d7-43e1-9a83-5f2406dee5bd",
  "displayName": "John Doe",
  "givenName": "John",
  "surname": "Doe",
  "userPrincipalName": "jdoe@company.com",
  "mail": "jdoe@company.com",
  "jobTitle": "Security Analyst",
  "mobilePhone": "+1 425 555 0109",
  "officeLocation": "Building A",
  "businessPhones": ["+1 425 555 0100"],
  "preferredLanguage": "en-US"
}
```

Extended fields (require `$select`):

| Field | Type | Notes |
|---|---|---|
| `id` | string (UUID) | Entra object ID — use as reference |
| `userPrincipalName` | string | UPN (usually email format) — maps to Calseta `account` indicator value |
| `mail` | string | Primary SMTP email |
| `displayName` | string | Full display name |
| `givenName` | string | First name |
| `surname` | string | Last name |
| `jobTitle` | string | Job title |
| `department` | string | Department |
| `officeLocation` | string | Office location |
| `companyName` | string | Company name |
| `employeeId` | string | Employee ID |
| `employeeType` | string | `"Employee"`, `"Contractor"`, `"Vendor"`, `"Member"` |
| `accountEnabled` | boolean | Whether account can sign in (false = disabled) |
| `signInSessionsValidFromDateTime` | string (ISO 8601) | All tokens issued before this time are invalid (set by revokeSignInSessions) |
| `lastPasswordChangeDateTime` | string (ISO 8601) | Last password change time |
| `createdDateTime` | string (ISO 8601) | Account creation time |
| `usageLocation` | string | 2-letter country code for license assignment |
| `assignedLicenses` | array | `[{ disabledPlans: [], skuId: "uuid" }]` |
| `onPremisesSamAccountName` | string | Active Directory SAM account name (if hybrid) |
| `onPremisesUserPrincipalName` | string | AD UPN (if hybrid) |
| `onPremisesSyncEnabled` | boolean | Whether user is synced from AD |
| `onPremisesLastSyncDateTime` | string (ISO 8601) | Last AD sync time |
| `identities` | array | `[{ signInType, issuer, issuerAssignedId }]` — alternate sign-in identifiers |
| `proxyAddresses` | string[] | All email aliases |
| `memberOf` | array | Group memberships (requires separate call or `$expand=memberOf`) |

### Enrichment field extraction paths (Calseta `enrichment_field_extractions` seeding)

| `target_key` | `source_path` | Notes |
|---|---|---|
| `upn` | `userPrincipalName` | Primary identifier |
| `email` | `mail` | SMTP address |
| `display_name` | `displayName` | Full name |
| `given_name` | `givenName` | First name |
| `surname` | `surname` | Last name |
| `job_title` | `jobTitle` | Title |
| `department` | `department` | Department |
| `account_enabled` | `accountEnabled` | Boolean — false means disabled |
| `last_password_change` | `lastPasswordChangeDateTime` | ISO 8601 |
| `employee_id` | `employeeId` | HR employee ID |
| `employee_type` | `employeeType` | Employment type |
| `on_premises_sync` | `onPremisesSyncEnabled` | Hybrid AD sync status |

---

## Available Automation Endpoints (for pre-built workflows)

### Revoke all sign-in sessions
```
POST /v1.0/users/{id}/revokeSignInSessions
Authorization: Bearer {token}
```
Effect: Invalidates all refresh tokens and browser session cookies by setting `signInSessionsValidFromDateTime` to current time. Any app using an old refresh token gets an error and must re-authenticate. Returns `{ "value": true }`.

Required permissions: `User.RevokeSessions.All` (Application permission)

Note: Small delay (1–3 minutes) before all tokens are actually revoked globally. Does NOT affect external users (guest accounts sign in via home tenant).

### Disable account (block sign-in)
```
PATCH /v1.0/users/{id}
Authorization: Bearer {token}
Content-Type: application/json

{ "accountEnabled": false }
```
Effect: Immediately prevents new sign-ins. Existing sessions/tokens remain valid until they expire or are revoked. Combine with `revokeSignInSessions` for complete lockout.

Returns `204 No Content` on success.

Required permissions: `User.EnableDisableAccount.All` + `User.Read.All` (Application permissions)

### Re-enable account
```
PATCH /v1.0/users/{id}
{ "accountEnabled": true }
```
Returns `204 No Content`.

### Reset password (admin reset — forces password change on next login)
```
PATCH /v1.0/users/{id}
Authorization: Bearer {token}

{
  "passwordProfile": {
    "forceChangePasswordNextSignIn": true,
    "password": "{temporary_password}"
  }
}
```
Effect: Sets a temporary password and forces change at next login. The caller must generate a sufficiently complex temporary password meeting the tenant's password policy.

Required permissions: `User-PasswordProfile.ReadWrite.All` (Application permission)

Note: For cloud-only accounts this works immediately. For hybrid AD-synced accounts, the password change must propagate through AD Connect (sync delay of up to 30 minutes).

### List MFA authentication methods
```
GET /v1.0/users/{id}/authentication/methods
Authorization: Bearer {token}
```
Returns array of registered authentication methods:
```json
{
  "value": [
    {
      "@odata.type": "#microsoft.graph.microsoftAuthenticatorAuthenticationMethod",
      "id": "method-uuid",
      "displayName": "John's iPhone",
      "deviceTag": "...",
      "createdDateTime": "2024-01-01T00:00:00Z"
    },
    {
      "@odata.type": "#microsoft.graph.passwordAuthenticationMethod",
      "id": "method-uuid",
      "createdDateTime": "2024-01-01T00:00:00Z"
    },
    {
      "@odata.type": "#microsoft.graph.phoneAuthenticationMethod",
      "id": "method-uuid",
      "phoneType": "mobile",
      "phoneNumber": "+1 555 555 5555",
      "smsSignInState": "notSupported"
    },
    {
      "@odata.type": "#microsoft.graph.fido2AuthenticationMethod",
      "id": "method-uuid",
      "displayName": "Security Key",
      "aaGuid": "...",
      "model": "YubiKey 5",
      "createdDateTime": "2024-01-01T00:00:00Z"
    }
  ]
}
```

Authentication method `@odata.type` values:
| Type | Method |
|---|---|
| `#microsoft.graph.microsoftAuthenticatorAuthenticationMethod` | Microsoft Authenticator app |
| `#microsoft.graph.passwordAuthenticationMethod` | Password (always present) |
| `#microsoft.graph.phoneAuthenticationMethod` | SMS / phone call |
| `#microsoft.graph.fido2AuthenticationMethod` | FIDO2 / hardware key |
| `#microsoft.graph.softwareOathAuthenticationMethod` | Third-party TOTP app |
| `#microsoft.graph.windowsHelloForBusinessAuthenticationMethod` | Windows Hello |
| `#microsoft.graph.emailAuthenticationMethod` | Email OTP |
| `#microsoft.graph.temporaryAccessPassAuthenticationMethod` | TAP |

Required permissions (app-only): `UserAuthenticationMethod.Read.All`

### Permission scope summary for pre-built workflows

| Action | Application Permission Required |
|---|---|
| Read user profile | `User.Read.All` |
| Disable account | `User.EnableDisableAccount.All` + `User.Read.All` |
| Revoke sessions | `User.RevokeSessions.All` |
| Reset password | `User-PasswordProfile.ReadWrite.All` |
| List MFA methods | `UserAuthenticationMethod.Read.All` |
| All of the above | Grant all 4 permissions to the service principal |

---

## Rate Limits

Microsoft Graph applies service-level throttling. Limits vary by service:

| Resource | Requests per second per app |
|---|---|
| User read (`GET /users/{id}`) | 300 |
| User write (`PATCH /users/{id}`) | 300 |
| revokeSignInSessions | 300 |
| Authentication methods (read) | 300 |
| User list (`GET /users`) | 300 |

Throttling response: `429 Too Many Requests`
Headers: `Retry-After` (seconds to wait), `x-ms-throttle-reason`

Graph also applies **global throttling** per tenant across all apps: if the tenant is generating too many API calls overall, Calseta AI may be throttled even below per-app limits.

---

## Known Quirks / Edge Cases

- **UPN vs mail vs id**: For user lookup from an alert, try `userPrincipalName` first (most common identifier in auth logs). If not found, try `mail` (may differ from UPN for guests). `id` is the most reliable but rarely appears in alert data.
- **Guest/B2B users**: `revokeSignInSessions` does NOT work for guest accounts — they authenticate via their home tenant. `accountEnabled: false` blocks the guest account in your tenant specifically.
- **Hybrid AD sync**: For `onPremisesSyncEnabled: true` users, `accountEnabled: false` written to Graph is overwritten on the next AD Connect sync cycle (default 30 min). For truly hybrid environments, the AD disable must happen in on-prem AD for it to stick.
- **`$select` is required for extended fields**: `accountEnabled`, `department`, `employeeId`, `lastPasswordChangeDateTime` are NOT returned by default. Always include `$select` in enrichment calls.
- **Password reset for hybrid users**: Writing `passwordProfile` to Graph for AD-synced users may be blocked by tenant configuration (`DirSyncEnabled` tenants often require password writeback to be configured in AD Connect).
- **`signInSessionsValidFromDateTime` race condition**: There is a 1–3 minute propagation delay after `revokeSignInSessions`. Existing access tokens (not refresh tokens) continue to work for their remaining lifetime (up to 1 hour). For immediate enforcement, disable the account in addition to revoking sessions.
- **MFA method array interpretation**: A user with only `passwordAuthenticationMethod` in the array has NO MFA enrolled — the password method is always present and does not indicate MFA. Count non-password methods to assess MFA enrollment.
- **`ConsistencyLevel: eventual` header**: Required for advanced `$filter` and `$search` queries on large directories. Without it, complex filters return `400 Bad Request`.
- **Token caching**: Access tokens are valid for ~1 hour. Cache and reuse them. Acquiring a new token per request will exhaust the token endpoint's own rate limits and add 200–500ms latency per call.
- **Application vs delegated permissions**: Calseta AI uses Application permissions (no user context). Some operations (like reading MFA methods for other users) require specific roles assigned to the service principal in Entra: Global Reader (for reading), Privileged Authentication Administrator (for modifying MFA methods).
