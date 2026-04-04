"""AgentAPIKeyRepository — all DB operations for agent_api_keys table."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models.agent_api_key import AgentAPIKey
from app.repositories.base import BaseRepository


class AgentAPIKeyRepository(BaseRepository[AgentAPIKey]):
    model = AgentAPIKey

    async def create(
        self,
        agent_id: int,
        name: str,
        key_prefix: str,
        key_hash: str,
        scopes: list[str],
    ) -> AgentAPIKey:
        """Persist a new agent API key. Returns the created ORM object."""
        record = AgentAPIKey(
            uuid=uuid.uuid4(),
            agent_registration_id=agent_id,
            name=name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            scopes=scopes,
        )
        self._db.add(record)
        await self._db.flush()
        await self._db.refresh(record)
        return record

    async def get_by_prefix(self, key_prefix: str) -> AgentAPIKey | None:
        """Return the AgentAPIKey row whose key_prefix matches and is not revoked."""
        result = await self._db.execute(
            select(AgentAPIKey).where(
                AgentAPIKey.key_prefix == key_prefix,
                AgentAPIKey.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def list_for_agent(self, agent_id: int) -> list[AgentAPIKey]:
        """Return all keys for a given agent registration, ordered by created_at desc."""
        result = await self._db.execute(
            select(AgentAPIKey)
            .where(AgentAPIKey.agent_registration_id == agent_id)
            .order_by(AgentAPIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_uuid_for_agent(
        self, agent_id: int, key_uuid: uuid.UUID
    ) -> AgentAPIKey | None:
        """Return a specific key by UUID, scoped to a given agent."""
        result = await self._db.execute(
            select(AgentAPIKey).where(
                AgentAPIKey.uuid == key_uuid,
                AgentAPIKey.agent_registration_id == agent_id,
            )
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def revoke(self, key: AgentAPIKey) -> AgentAPIKey:
        """Set revoked_at to now on the key. Idempotent — safe to call multiple times."""
        if key.revoked_at is None:
            key.revoked_at = datetime.now(UTC)
            await self._db.flush()
            await self._db.refresh(key)
        return key
