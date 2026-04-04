"""Secret repository — all DB reads/writes for the secrets and secret_versions tables."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db.models.secret import Secret, SecretVersion
from app.repositories.base import BaseRepository
from app.schemas.secrets import SecretCreate


class SecretRepository(BaseRepository[Secret]):
    model = Secret

    async def create(self, data: SecretCreate) -> Secret:
        """Persist a new Secret row. Does NOT create the initial version — call
        ``create_version()`` separately after encrypting the value (if applicable).
        """
        secret = Secret(
            uuid=uuid.uuid4(),
            name=data.name,
            description=data.description,
            provider=data.provider,
            env_var_name=data.env_var_name,
            current_version=0,
            is_sensitive=True,
        )
        self._db.add(secret)
        await self._db.flush()
        await self._db.refresh(secret)
        return secret

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Secret], int]:
        """Return (secrets, total_count) ordered by created_at descending."""
        return await self.paginate(
            order_by=Secret.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    async def get_by_name(self, name: str) -> Secret | None:
        """Fetch a single secret by its unique name."""
        result = await self._db.execute(
            select(Secret).where(Secret.name == name)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def get_current_version(self, secret: Secret) -> SecretVersion | None:
        """Return the current (is_current=True) version for the given secret, or None."""
        result = await self._db.execute(
            select(SecretVersion).where(
                SecretVersion.secret_id == secret.id,
                SecretVersion.is_current.is_(True),
            )
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def list_versions(
        self,
        secret: Secret,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SecretVersion], int]:
        """Return (versions, total_count) for the given secret, newest first."""
        from sqlalchemy import func

        count_result = await self._db.execute(
            select(func.count()).select_from(SecretVersion).where(
                SecretVersion.secret_id == secret.id
            )
        )
        total: int = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await self._db.execute(
            select(SecretVersion)
            .where(SecretVersion.secret_id == secret.id)
            .order_by(SecretVersion.version.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def create_version(
        self,
        secret: Secret,
        encrypted_value: str | None,
    ) -> SecretVersion:
        """Create a new SecretVersion row and mark it current.

        Also marks the previous current version non-current and increments
        ``secret.current_version``.  The caller is responsible for flushing
        the transaction (or relying on the session autoflush).
        """
        # Retire the existing current version if any
        prev = await self.get_current_version(secret)
        if prev is not None:
            prev.is_current = False
            await self._db.flush()

        next_version_num = secret.current_version + 1
        version = SecretVersion(
            uuid=uuid.uuid4(),
            secret_id=secret.id,
            version=next_version_num,
            encrypted_value=encrypted_value,
            is_current=True,
        )
        self._db.add(version)
        secret.current_version = next_version_num
        await self._db.flush()
        await self._db.refresh(version)
        await self._db.refresh(secret)
        return version
