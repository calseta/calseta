"""SkillRepository — CRUD and agent-skill assignment operations."""

from __future__ import annotations

import uuid as uuid_module
from uuid import UUID

from sqlalchemy import delete, func, select

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

    # --- Bundled-skill loader operations ---

    async def upsert_bundled_skill(
        self,
        *,
        slug: str,
        name: str,
        description: str | None,
        content_sha256: str,
    ) -> tuple[Skill, bool]:
        """Insert or update a global bundled skill (``source='bundled'``).

        Returns ``(skill, changed)`` where ``changed`` is True if the row was
        created OR if the stored ``content_sha256`` differs from the value
        passed in (callers should re-write SkillFile rows in that case).

        Operator-edited skills (``source='manual'``) are NEVER touched. If a
        manual row already exists with the same slug it is returned with
        ``changed=False`` so the loader will skip it.
        """
        existing = await self.get_by_slug(slug)
        if existing is not None:
            if existing.source != "bundled":
                # Operator owns this row — do not clobber.
                return existing, False
            changed = existing.content_sha256 != content_sha256
            # Always reconcile metadata for bundled rows so the YAML
            # frontmatter on disk stays the source of truth.
            existing.name = name
            existing.description = description
            existing.is_global = True
            existing.is_active = True
            if changed:
                existing.content_sha256 = content_sha256
            await self._db.flush()
            await self._db.refresh(existing)
            return existing, changed

        skill = Skill(
            uuid=uuid_module.uuid4(),
            slug=slug,
            name=name,
            description=description,
            is_active=True,
            is_global=True,
            source="bundled",
            content_sha256=content_sha256,
        )
        self._db.add(skill)
        await self._db.flush()
        await self._db.refresh(skill)
        return skill, True

    async def replace_bundled_files(
        self,
        skill_id: int,
        files: list[tuple[str, str]],
    ) -> None:
        """Replace ALL ``skill_files`` rows for a bundled skill.

        ``files`` is a list of ``(relative_path, content)`` tuples. The entry
        file (path == ``SKILL.md``) is auto-flagged ``is_entry=True``.

        Used only by the bundled-skills loader — drops every existing file row
        and inserts the on-disk set verbatim. Safe because callers gate this
        behind a SHA256 mismatch and because ``source='manual'`` rows never
        reach this method.
        """
        await self._db.execute(
            delete(SkillFile).where(SkillFile.skill_id == skill_id)
        )
        await self._db.flush()
        for path, content in files:
            self._db.add(
                SkillFile(
                    uuid=uuid_module.uuid4(),
                    skill_id=skill_id,
                    path=path,
                    content=content,
                    is_entry=(path == "SKILL.md"),
                )
            )
        await self._db.flush()

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

        Operator path: writing through this method flips the parent skill's
        ``source`` to ``'manual'`` and clears ``content_sha256``. After that
        the bundled-skills loader will skip the row forever, preserving the
        operator's edits across restarts.
        """
        # Promote the parent skill to 'manual' so the universal loader
        # never overwrites operator edits.
        skill_row = await self._db.get(Skill, skill_id)
        if skill_row is not None and skill_row.source != "manual":
            skill_row.source = "manual"
            skill_row.content_sha256 = None

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
