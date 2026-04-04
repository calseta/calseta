"""Secret reference resolver — parses ref strings and dispatches to the right provider."""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.secret import Secret
from app.secrets.env_var import EnvVarProvider
from app.secrets.local_encrypted import LocalEncryptedProvider


async def resolve_secret_ref(
    ref: str,
    db: AsyncSession,
) -> str | None:
    """Resolve a secret reference string.

    Ref formats:
      ``env:<VAR_NAME>``    — reads ``os.environ["VAR_NAME"]`` directly; no DB lookup.
      ``secret:<name>``     — looks up the named secret in the DB and dispatches
                              to the appropriate provider (local_encrypted or env_var).
      plain string          — returned as-is (literal value, not a reference).

    Returns None if the secret is not found or the env var is not set.
    """
    if ref.startswith("env:"):
        var_name = ref[4:]
        return os.environ.get(var_name)

    if ref.startswith("secret:"):
        secret_name = ref[7:]
        result = await db.execute(
            select(Secret).where(Secret.name == secret_name)
        )
        secret = result.scalar_one_or_none()
        if secret is None:
            return None

        if secret.provider == "env_var":
            provider: EnvVarProvider | LocalEncryptedProvider = EnvVarProvider(db)
        else:
            provider = LocalEncryptedProvider(db)

        return await provider.resolve(secret_name)

    # Plain string — literal value
    return ref
