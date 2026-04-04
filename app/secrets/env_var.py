"""EnvVarProvider — resolves secrets from OS environment variables."""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.secret import Secret
from app.secrets.base import SecretsProviderBase


class EnvVarProvider(SecretsProviderBase):
    """Read-only provider that resolves secrets by reading OS environment variables.

    The ``env_var_name`` column on the ``secrets`` row specifies which environment
    variable holds the actual secret value.  No encrypted value is ever stored.

    ``store()`` is not supported — env var secrets are configured outside the
    platform (CI/CD secrets, docker-compose env, etc.).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(self, name: str) -> str | None:
        """Return the value of the environment variable named by ``secrets.env_var_name``.

        Returns None if the secret does not exist, has no ``env_var_name`` configured,
        or the environment variable is not set.
        """
        result = await self._db.execute(
            select(Secret).where(Secret.name == name)
        )
        secret = result.scalar_one_or_none()
        if secret is None or not secret.env_var_name:
            return None

        return os.environ.get(secret.env_var_name)

    async def store(self, name: str, value: str) -> None:  # noqa: ARG002
        """Not supported — env var secrets are read-only."""
        raise NotImplementedError(
            "EnvVarProvider is read-only. Set the environment variable directly "
            "in your deployment environment."
        )
