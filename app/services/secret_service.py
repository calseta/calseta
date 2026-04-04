"""Secret service — business logic for secrets management."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.secret import Secret, SecretVersion
from app.repositories.secret_repository import SecretRepository
from app.schemas.secrets import SecretCreate
from app.secrets.env_var import EnvVarProvider
from app.secrets.local_encrypted import LocalEncryptedProvider


class SecretService:
    """Orchestrates secret creation, rotation, deletion, and resolution.

    This is the only layer that knows about both the repository (persistence)
    and the provider implementations (encryption / env lookup).  Route handlers
    receive a service instance via dependency injection.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = SecretRepository(db)

    async def create(self, data: SecretCreate) -> tuple[Secret, None]:
        """Create a secret and its initial version.

        For ``local_encrypted`` secrets, encrypts ``data.value`` and stores it
        in a SecretVersion row.  For ``env_var`` secrets, no version row is
        created (the value lives in the environment).

        Returns ``(secret, None)`` — plaintext is never stored or returned.
        """
        secret = await self._repo.create(data)

        if data.provider == "local_encrypted" and data.value is not None:
            from app.auth.encryption import encrypt_value

            encrypted = encrypt_value(data.value)
            await self._repo.create_version(secret, encrypted_value=encrypted)
        # env_var provider: no version row needed

        return secret, None

    async def rotate(self, secret: Secret, new_value: str) -> SecretVersion:
        """Create a new encrypted version and mark it current.

        Only valid for ``local_encrypted`` secrets.  Raises ``ValueError`` for
        ``env_var`` secrets (rotate the env var in the deployment environment).
        """
        if secret.provider != "local_encrypted":
            raise ValueError(
                "Cannot rotate an env_var secret via the API. "
                "Update the environment variable in your deployment environment."
            )

        from app.auth.encryption import encrypt_value

        encrypted = encrypt_value(new_value)
        return await self._repo.create_version(secret, encrypted_value=encrypted)

    async def delete(self, secret: Secret) -> None:
        """Delete the secret and all its versions (cascade handled by DB FK)."""
        await self._repo.delete(secret)

    async def resolve(self, name: str) -> str | None:
        """Resolve a secret by name using its configured provider.

        Returns None if the secret is not found or the value is unavailable.
        """
        secret = await self._repo.get_by_name(name)
        if secret is None:
            return None

        if secret.provider == "env_var":
            provider: EnvVarProvider | LocalEncryptedProvider = EnvVarProvider(self._db)
        else:
            provider = LocalEncryptedProvider(self._db)

        return await provider.resolve(name)
