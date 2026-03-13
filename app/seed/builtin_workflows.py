"""
Pre-built workflow seeder — inserts the 9 system workflows at startup.

Idempotent: matched by name + is_system=True. Running on a live DB with
existing rows is a no-op.

Workflow activation rules:
  - Okta workflows: is_active=True only when OKTA_DOMAIN and OKTA_API_TOKEN are set
  - Entra workflows: is_active=True only when ENTRA_TENANT_ID, ENTRA_CLIENT_ID,
    and ENTRA_CLIENT_SECRET are all set
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.config import Settings


@dataclass
class _WorkflowSpec:
    name: str
    code: str
    documentation: str
    risk_level: str
    requires_okta: bool = False
    requires_entra: bool = False


# ---------------------------------------------------------------------------
# Okta workflow code templates
# ---------------------------------------------------------------------------

_OKTA_REVOKE_SESSIONS_CODE = '''\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Revoke all active Okta sessions for the given account."""
    if ctx.integrations.okta is None:
        return WorkflowResult.fail("Okta integration is not configured")
    try:
        await ctx.integrations.okta.revoke_sessions(ctx.indicator.value)
        ctx.log.info("okta_sessions_revoked", account=ctx.indicator.value)
        return WorkflowResult.ok(
            f"All Okta sessions revoked for {ctx.indicator.value}",
            data={"account": ctx.indicator.value},
        )
    except Exception as exc:
        ctx.log.error("okta_revoke_sessions_failed", error=str(exc))
        return WorkflowResult.fail(f"Failed to revoke sessions: {exc}")
'''

_OKTA_SUSPEND_USER_CODE = '''\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Suspend the Okta account to prevent sign-in."""
    if ctx.integrations.okta is None:
        return WorkflowResult.fail("Okta integration is not configured")
    try:
        await ctx.integrations.okta.suspend_user(ctx.indicator.value)
        ctx.log.info("okta_user_suspended", account=ctx.indicator.value)
        return WorkflowResult.ok(
            f"Okta account suspended: {ctx.indicator.value}",
            data={"account": ctx.indicator.value},
        )
    except Exception as exc:
        ctx.log.error("okta_suspend_failed", error=str(exc))
        return WorkflowResult.fail(f"Failed to suspend account: {exc}")
'''

_OKTA_UNSUSPEND_USER_CODE = '''\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Unsuspend a previously suspended Okta account."""
    if ctx.integrations.okta is None:
        return WorkflowResult.fail("Okta integration is not configured")
    try:
        await ctx.integrations.okta.unsuspend_user(ctx.indicator.value)
        ctx.log.info("okta_user_unsuspended", account=ctx.indicator.value)
        return WorkflowResult.ok(
            f"Okta account unsuspended: {ctx.indicator.value}",
            data={"account": ctx.indicator.value},
        )
    except Exception as exc:
        ctx.log.error("okta_unsuspend_failed", error=str(exc))
        return WorkflowResult.fail(f"Failed to unsuspend account: {exc}")
'''

_OKTA_RESET_PASSWORD_CODE = '''\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Trigger a password reset email for the Okta account."""
    if ctx.integrations.okta is None:
        return WorkflowResult.fail("Okta integration is not configured")
    try:
        reset_url = await ctx.integrations.okta.reset_password(ctx.indicator.value)
        ctx.log.info("okta_password_reset_triggered", account=ctx.indicator.value)
        result_data = {"account": ctx.indicator.value}
        if reset_url:
            result_data["reset_url"] = reset_url
        return WorkflowResult.ok(
            f"Password reset triggered for {ctx.indicator.value}",
            data=result_data,
        )
    except Exception as exc:
        ctx.log.error("okta_reset_password_failed", error=str(exc))
        return WorkflowResult.fail(f"Failed to reset password: {exc}")
'''

_OKTA_EXPIRE_PASSWORD_CODE = '''\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Force the Okta account password to expire on next sign-in."""
    if ctx.integrations.okta is None:
        return WorkflowResult.fail("Okta integration is not configured")
    try:
        await ctx.integrations.okta.expire_password(ctx.indicator.value)
        ctx.log.info("okta_password_expired", account=ctx.indicator.value)
        return WorkflowResult.ok(
            f"Password expiry forced for {ctx.indicator.value}",
            data={"account": ctx.indicator.value},
        )
    except Exception as exc:
        ctx.log.error("okta_expire_password_failed", error=str(exc))
        return WorkflowResult.fail(f"Failed to force password expiry: {exc}")
'''

# ---------------------------------------------------------------------------
# Entra workflow code templates
# ---------------------------------------------------------------------------

_ENTRA_REVOKE_SESSIONS_CODE = '''\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Revoke all active sign-in sessions for the Entra ID account."""
    if ctx.integrations.entra is None:
        return WorkflowResult.fail("Microsoft Entra integration is not configured")
    try:
        await ctx.integrations.entra.revoke_sessions(ctx.indicator.value)
        ctx.log.info("entra_sessions_revoked", account=ctx.indicator.value)
        return WorkflowResult.ok(
            f"All Entra sign-in sessions revoked for {ctx.indicator.value}",
            data={"account": ctx.indicator.value},
        )
    except Exception as exc:
        ctx.log.error("entra_revoke_sessions_failed", error=str(exc))
        return WorkflowResult.fail(f"Failed to revoke sessions: {exc}")
'''

_ENTRA_DISABLE_ACCOUNT_CODE = '''\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Disable the Entra ID account to block all sign-ins."""
    if ctx.integrations.entra is None:
        return WorkflowResult.fail("Microsoft Entra integration is not configured")
    try:
        await ctx.integrations.entra.disable_account(ctx.indicator.value)
        ctx.log.info("entra_account_disabled", account=ctx.indicator.value)
        return WorkflowResult.ok(
            f"Entra account disabled: {ctx.indicator.value}",
            data={"account": ctx.indicator.value},
        )
    except Exception as exc:
        ctx.log.error("entra_disable_failed", error=str(exc))
        return WorkflowResult.fail(f"Failed to disable account: {exc}")
'''

_ENTRA_ENABLE_ACCOUNT_CODE = '''\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Re-enable a previously disabled Entra ID account."""
    if ctx.integrations.entra is None:
        return WorkflowResult.fail("Microsoft Entra integration is not configured")
    try:
        await ctx.integrations.entra.enable_account(ctx.indicator.value)
        ctx.log.info("entra_account_enabled", account=ctx.indicator.value)
        return WorkflowResult.ok(
            f"Entra account re-enabled: {ctx.indicator.value}",
            data={"account": ctx.indicator.value},
        )
    except Exception as exc:
        ctx.log.error("entra_enable_failed", error=str(exc))
        return WorkflowResult.fail(f"Failed to enable account: {exc}")
'''

_ENTRA_RESET_MFA_CODE = '''\
from app.workflows.context import WorkflowContext, WorkflowResult


async def run(ctx: WorkflowContext) -> WorkflowResult:
    """Force MFA re-registration for the Entra ID account."""
    if ctx.integrations.entra is None:
        return WorkflowResult.fail("Microsoft Entra integration is not configured")
    try:
        await ctx.integrations.entra.reset_mfa(ctx.indicator.value)
        ctx.log.info("entra_mfa_reset", account=ctx.indicator.value)
        return WorkflowResult.ok(
            f"MFA re-registration forced for {ctx.indicator.value}",
            data={"account": ctx.indicator.value},
        )
    except Exception as exc:
        ctx.log.error("entra_mfa_reset_failed", error=str(exc))
        return WorkflowResult.fail(f"Failed to force MFA re-registration: {exc}")
'''

# ---------------------------------------------------------------------------
# Workflow catalog (9 entries)
# ---------------------------------------------------------------------------

_WORKFLOWS: list[_WorkflowSpec] = [
    _WorkflowSpec(
        name="Okta — Revoke All Sessions",
        code=_OKTA_REVOKE_SESSIONS_CODE,
        documentation="""\
## Description
Revokes all active Okta sessions for the specified account indicator, \
immediately terminating any in-progress sessions across all devices and browsers.

## When to Use
Use when an account is suspected of compromise, unauthorized access is detected, \
or during incident containment after credential theft. This is a low-risk first \
response action that does not lock out the user permanently.

## Required Secrets
- `OKTA_DOMAIN` — your Okta organization URL (e.g., `company.okta.com`)
- `OKTA_API_TOKEN` — service account API token with session management permissions

## Expected Outcome
All active sessions for the account are invalidated within seconds. \
The user is forced to re-authenticate on next access. \
The workflow returns the account identifier in the result data.

## Error Cases
- Account not found in Okta: wrapped exception returned as failure
- Okta API rate limit exceeded: wrapped exception returned as failure
- Missing integration config: immediate failure before any API call
""",
        risk_level="low",
        requires_okta=True,
    ),
    _WorkflowSpec(
        name="Okta — Suspend User",
        code=_OKTA_SUSPEND_USER_CODE,
        documentation="""\
## Description
Suspends the Okta account, blocking all sign-in attempts until the account \
is explicitly unsuspended.

## When to Use
Use during active incident response when a user account must be fully \
locked out — e.g., confirmed credential compromise, insider threat investigation, \
or compliance-required access freeze. More disruptive than session revocation.

## Required Secrets
- `OKTA_DOMAIN` — your Okta organization URL
- `OKTA_API_TOKEN` — service account API token with user lifecycle permissions

## Expected Outcome
Account status changes to `SUSPENDED`. The user cannot authenticate via any \
Okta-protected application. Reversible via the Okta — Unsuspend User workflow.

## Error Cases
- Account already suspended: may return idempotent success depending on Okta version
- Insufficient API token permissions: wrapped exception returned as failure
""",
        risk_level="high",
        requires_okta=True,
    ),
    _WorkflowSpec(
        name="Okta — Unsuspend User",
        code=_OKTA_UNSUSPEND_USER_CODE,
        documentation="""\
## Description
Restores a suspended Okta account to active status, re-enabling sign-in.

## When to Use
Use after an incident investigation concludes that the account suspension \
was precautionary and the account owner has been cleared, or during \
post-incident recovery.

## Required Secrets
- `OKTA_DOMAIN` — your Okta organization URL
- `OKTA_API_TOKEN` — service account API token with user lifecycle permissions

## Expected Outcome
Account status changes from `SUSPENDED` back to `ACTIVE`. \
The user can authenticate normally. Combine with a forced password reset \
for maximum security.

## Error Cases
- Account not in suspended state: may return error depending on Okta version
- Insufficient API token permissions: wrapped exception returned as failure
""",
        risk_level="medium",
        requires_okta=True,
    ),
    _WorkflowSpec(
        name="Okta — Reset Password",
        code=_OKTA_RESET_PASSWORD_CODE,
        documentation="""\
## Description
Triggers a password reset for the specified Okta account. \
Sends a reset email to the account's registered email address.

## When to Use
Use when credentials may have been exposed but account suspension is \
too disruptive, or as a follow-up action after session revocation to \
ensure the compromised credentials are invalidated.

## Required Secrets
- `OKTA_DOMAIN` — your Okta organization URL
- `OKTA_API_TOKEN` — service account API token with user lifecycle permissions

## Expected Outcome
The user receives a password reset email. Any existing password is \
invalidated. The result data may include a reset URL for admin-initiated flows.

## Error Cases
- Account deactivated: wrapped exception returned as failure
- Email delivery failure: handled by Okta; not surfaced to this workflow
""",
        risk_level="medium",
        requires_okta=True,
    ),
    _WorkflowSpec(
        name="Okta — Force Password Expiry",
        code=_OKTA_EXPIRE_PASSWORD_CODE,
        documentation="""\
## Description
Forces the Okta account password to expire, requiring the user to \
set a new password at next sign-in without sending a reset email.

## When to Use
Use for proactive credential hygiene enforcement after a potential \
exposure event, or when policy requires password rotation without \
interrupting an active session immediately.

## Required Secrets
- `OKTA_DOMAIN` — your Okta organization URL
- `OKTA_API_TOKEN` — service account API token with user lifecycle permissions

## Expected Outcome
Password expiry is set. The user can complete their current session but \
must change their password at next sign-in. Less disruptive than a \
full password reset.

## Error Cases
- Account deactivated or locked: wrapped exception returned as failure
""",
        risk_level="low",
        requires_okta=True,
    ),
    _WorkflowSpec(
        name="Entra — Revoke Sign-in Sessions",
        code=_ENTRA_REVOKE_SESSIONS_CODE,
        documentation="""\
## Description
Revokes all active Microsoft Entra ID (Azure AD) sign-in sessions for \
the specified account, invalidating refresh tokens and forcing re-authentication.

## When to Use
Use when an Entra account is suspected of compromise, when tokens may \
have been stolen, or as a first containment action during incident response.

## Required Secrets
- `ENTRA_TENANT_ID` — Azure AD tenant identifier
- `ENTRA_CLIENT_ID` — App registration client ID with User.ReadWrite.All
- `ENTRA_CLIENT_SECRET` — App registration client secret

## Expected Outcome
All refresh tokens for the account are invalidated within seconds. \
Access tokens remain valid until their natural expiry (typically 1 hour). \
The user must re-authenticate on next access.

## Error Cases
- Account not found: wrapped exception returned as failure
- Insufficient app permissions: wrapped exception returned as failure
""",
        risk_level="low",
        requires_entra=True,
    ),
    _WorkflowSpec(
        name="Entra — Disable Account",
        code=_ENTRA_DISABLE_ACCOUNT_CODE,
        documentation="""\
## Description
Disables the Entra ID account by setting `accountEnabled = false`, \
blocking all sign-in attempts immediately.

## When to Use
Use during active incident response for confirmed account compromise, \
insider threat cases, or when an employee's access must be revoked \
pending investigation.

## Required Secrets
- `ENTRA_TENANT_ID` — Azure AD tenant identifier
- `ENTRA_CLIENT_ID` — App registration client ID with User.ReadWrite.All
- `ENTRA_CLIENT_SECRET` — App registration client secret

## Expected Outcome
Account `accountEnabled` property set to `false`. The user cannot \
sign in to any Azure/M365 resource. Reversible via Entra — Enable Account.

## Error Cases
- Account already disabled: idempotent; returns success
- Insufficient permissions: wrapped exception returned as failure
""",
        risk_level="high",
        requires_entra=True,
    ),
    _WorkflowSpec(
        name="Entra — Enable Account",
        code=_ENTRA_ENABLE_ACCOUNT_CODE,
        documentation="""\
## Description
Re-enables a previously disabled Entra ID account, restoring sign-in access.

## When to Use
Use after investigation concludes the account was disabled precautionarily \
and the user should regain access, or during post-incident recovery steps.

## Required Secrets
- `ENTRA_TENANT_ID` — Azure AD tenant identifier
- `ENTRA_CLIENT_ID` — App registration client ID with User.ReadWrite.All
- `ENTRA_CLIENT_SECRET` — App registration client secret

## Expected Outcome
Account `accountEnabled` set back to `true`. The user can authenticate \
to Azure/M365 resources. Recommend forcing a password reset in tandem.

## Error Cases
- Account not found: wrapped exception returned as failure
""",
        risk_level="medium",
        requires_entra=True,
    ),
    _WorkflowSpec(
        name="Entra — Force MFA Re-registration",
        code=_ENTRA_RESET_MFA_CODE,
        documentation="""\
## Description
Forces MFA re-registration for the Entra ID account by revoking all \
registered authentication methods, requiring the user to re-enroll MFA \
on next sign-in.

## When to Use
Use when MFA device compromise is suspected, when a user's phone has \
been lost/stolen, or as a security hygiene step after any identity \
incident.

## Required Secrets
- `ENTRA_TENANT_ID` — Azure AD tenant identifier
- `ENTRA_CLIENT_ID` — App registration client ID with UserAuthenticationMethod.ReadWrite.All
- `ENTRA_CLIENT_SECRET` — App registration client secret

## Expected Outcome
All registered MFA methods (authenticator apps, FIDO2 keys, phone numbers) \
are deleted. The user must complete MFA re-enrollment at next sign-in \
if MFA is enforced by Conditional Access policy.

## Error Cases
- Account has no registered methods: idempotent; returns success
- Insufficient permissions (requires UserAuthenticationMethod.ReadWrite.All): \
wrapped exception returned as failure
""",
        risk_level="high",
        requires_entra=True,
    ),
]


async def seed_builtin_workflows(db: AsyncSession, cfg: Settings) -> None:
    """
    Seed 9 pre-built system workflows into the DB.

    Safe to call on every startup — existing rows are skipped (idempotent).
    Activation state is determined by the presence of the required
    integration credentials in settings.
    """
    from app.repositories.workflow_repository import WorkflowRepository

    okta_active = bool(cfg.OKTA_DOMAIN and cfg.OKTA_API_TOKEN)
    entra_active = bool(cfg.ENTRA_TENANT_ID and cfg.ENTRA_CLIENT_ID and cfg.ENTRA_CLIENT_SECRET)

    repo = WorkflowRepository(db)

    for spec in _WORKFLOWS:
        if spec.requires_okta:
            is_active = okta_active
        elif spec.requires_entra:
            is_active = entra_active
        else:
            is_active = True

        await repo.upsert_system_workflow(
            name=spec.name,
            code=spec.code,
            documentation=spec.documentation,
            workflow_type="indicator",
            indicator_types=["account"],
            state="active",
            is_active=is_active,
            risk_level=spec.risk_level,
            approval_mode="always",
            timeout_seconds=60,
            retry_count=0,
        )
