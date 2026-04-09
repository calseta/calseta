"""SkillRepository — CRUD and agent-skill assignment operations."""

from __future__ import annotations

import uuid as uuid_module
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import agent_skill_assignments
from app.db.models.skill import Skill
from app.db.models.skill_file import SkillFile
from app.repositories.base import BaseRepository


class SkillRepository(BaseRepository[Skill]):
    model = Skill

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Skill], int]:
        """Return (skills, total) ordered by name."""
        count_stmt = select(func.count()).select_from(Skill)
        total_result = await self._db.execute(count_stmt)
        total: int = total_result.scalar_one()

        stmt = (
            select(Skill)
            .order_by(Skill.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_by_slug(self, slug: str) -> Skill | None:
        """Fetch a single skill by slug."""
        result = await self._db.execute(select(Skill).where(Skill.slug == slug))
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def get_by_uuids(self, skill_uuids: list[UUID]) -> list[Skill]:
        """Fetch multiple skills by UUID list."""
        if not skill_uuids:
            return []
        result = await self._db.execute(
            select(Skill).where(Skill.uuid.in_(skill_uuids))
        )
        return list(result.scalars().all())

    async def create(
        self,
        slug: str,
        name: str,
        description: str | None,
        is_global: bool = False,
    ) -> Skill:
        """Insert a new skill row and auto-create its SKILL.md entry file."""
        skill = Skill(
            uuid=uuid_module.uuid4(),
            slug=slug,
            name=name,
            description=description,
            is_active=True,
            is_global=is_global,
        )
        self._db.add(skill)
        await self._db.flush()

        # Auto-create the SKILL.md entry file
        entry_file = SkillFile(
            uuid=uuid_module.uuid4(),
            skill_id=skill.id,
            path="SKILL.md",
            content="",
            is_entry=True,
        )
        self._db.add(entry_file)
        await self._db.flush()
        await self._db.refresh(skill)
        return skill

    async def patch(self, skill: Skill, **kwargs: object) -> Skill:
        """Apply partial updates to a skill."""
        _UPDATABLE = frozenset({"name", "description", "is_active", "is_global"})
        for key, value in kwargs.items():
            if key not in _UPDATABLE:
                raise ValueError(f"Field '{key}' is not updatable via patch")
            setattr(skill, key, value)
        await self._db.flush()
        await self._db.refresh(skill)
        return skill

    # --- File management operations ---

    async def get_file_by_path(self, skill_id: int, path: str) -> SkillFile | None:
        """Fetch a skill file by (skill_id, path)."""
        result = await self._db.execute(
            select(SkillFile).where(
                SkillFile.skill_id == skill_id,
                SkillFile.path == path,
            )
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def get_file_by_uuid(self, file_uuid: UUID) -> SkillFile | None:
        """Fetch a skill file by UUID."""
        result = await self._db.execute(
            select(SkillFile).where(SkillFile.uuid == file_uuid)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def upsert_file(self, skill_id: int, path: str, content: str) -> SkillFile:
        """Insert or update a skill file by (skill_id, path).

        Sets is_entry=True automatically if path == "SKILL.md".
        """
        existing = await self.get_file_by_path(skill_id, path)
        if existing is not None:
            existing.content = content
            await self._db.flush()
            await self._db.refresh(existing)
            return existing

        skill_file = SkillFile(
            uuid=uuid_module.uuid4(),
            skill_id=skill_id,
            path=path,
            content=content,
            is_entry=(path == "SKILL.md"),
        )
        self._db.add(skill_file)
        await self._db.flush()
        await self._db.refresh(skill_file)
        return skill_file

    async def delete_file(self, file: SkillFile) -> None:
        """Delete a skill file. Raises ValueError if file is the entry point."""
        if file.is_entry:
            raise ValueError("Cannot delete the entry file (SKILL.md) of a skill.")
        await self._db.delete(file)
        await self._db.flush()

    # --- Agent-skill assignment operations ---

    async def get_agent_skills(self, agent_id: int) -> list[Skill]:
        """Return all active skills assigned to the given agent."""
        stmt = (
            select(Skill)
            .join(
                agent_skill_assignments,
                agent_skill_assignments.c.skill_id == Skill.id,
            )
            .where(
                agent_skill_assignments.c.agent_id == agent_id,
                Skill.is_active.is_(True),
            )
            .order_by(Skill.slug.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_global_skills(self) -> list[Skill]:
        """Return all active global skills (is_global=True, is_active=True)."""
        result = await self._db.execute(
            select(Skill)
            .where(Skill.is_global.is_(True), Skill.is_active.is_(True))
            .order_by(Skill.slug.asc())
        )
        return list(result.scalars().all())

    async def sync_agent_skills(self, agent_id: int, skill_ids: list[int]) -> None:
        """Atomically replace the full set of skills assigned to an agent.

        Deletes all existing assignments for agent_id, then inserts new ones.
        """
        # Delete existing assignments
        await self._db.execute(
            delete(agent_skill_assignments).where(
                agent_skill_assignments.c.agent_id == agent_id
            )
        )
        # Insert new assignments
        if skill_ids:
            await self._db.execute(
                agent_skill_assignments.insert(),
                [{"agent_id": agent_id, "skill_id": sid} for sid in skill_ids],
            )
        await self._db.flush()
