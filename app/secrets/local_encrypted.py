"""LocalEncryptedProvider — Fernet-encrypted secrets stored in PostgreSQL."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.encryption import decrypt_value, encrypt_value
from app.db.models.secret import Secret, SecretVersion
from app.secrets.base import SecretsProviderBase


class LocalEncryptedProvider(SecretsProviderBase):
    """Resolves secrets by decrypting ciphertext stored in the secret_versions table.

    Each call to ``store()`` creates a new SecretVersion row and marks it
    current, incrementing ``secret.current_version``.  The previous version
    row is kept for audit purposes (rotate-and-keep semantics).
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def resolve(self, name: str) -> str | None:
        """Return decrypted plaintext for the current version of the named secret.

        Returns None if the secret does not exist, has no current version, or has
        no encrypted value stored (unexpected state — treat as not found).
        """
        result = await self._db.execute(
            select(Secret).where(Secret.name == name)
        )
        secret = result.scalar_one_or_none()
        if secret is None:
            return None

        version_result = await self._db.execute(
            select(SecretVersion)
            .where(
                SecretVersion.secret_id == secret.id,
                SecretVersion.is_current.is_(True),
            )
        )
        version = version_result.scalar_one_or_none()
        if version is None or version.encrypted_value is None:
            return None

        return decrypt_value(version.encrypted_value)

    async def store(self, name: str, value: str) -> None:
        """Encrypt ``value`` and persist it as the new current version.

        Looks up the secret by name (must already exist), marks previous
        current version as non-current, creates the new version, and
        increments ``secret.current_version``.

        Raises LookupError if no secret with ``name`` exists.
        """
        result = await self._db.execute(
            select(Secret).where(Secret.name == name)
        )
        secret = result.scalar_one_or_none()
        if secret is None:
            raise LookupError(f"Secret '{name}' not found.")

        # Mark previous current version as non-current
        prev_result = await self._db.execute(
            select(SecretVersion).where(
                SecretVersion.secret_id == secret.id,
                SecretVersion.is_current.is_(True),
            )
        )
        prev_version = prev_result.scalar_one_or_none()
        if prev_version is not None:
            prev_version.is_current = False
            await self._db.flush()

        encrypted = encrypt_value(value)
        next_version_num = secret.current_version + 1

        new_version = SecretVersion(
            uuid=uuid.uuid4(),
            secret_id=secret.id,
            version=next_version_num,
            encrypted_value=encrypted,
            is_current=True,
        )
        self._db.add(new_version)
        secret.current_version = next_version_num
        await self._db.flush()
        await self._db.refresh(secret)
        await self._db.refresh(new_version)
