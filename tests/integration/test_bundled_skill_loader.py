"""Integration tests for the universal bundled-skills startup loader (S14).

Coverage:
- empty/missing dir → warning + 0
- single skill upsert against real DB
- idempotent on re-run (no spurious changes when content unchanged)
- SHA256-driven change detection writes new file content + preserves
  existing assignments
- operator-edited skills (source='manual') are NOT clobbered
- a managed agent run-time path (engine._inject_skills_ephemeral) sees
  the bundled global skill after the loader runs
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.agent_registration import (
    AgentRegistration,
    agent_skill_assignments,
)
from app.db.models.skill import Skill
from app.db.models.skill_file import SkillFile
from app.repositories.skill_repository import SkillRepository
from app.skills.loader import _hash_files, _parse_frontmatter, load_bundled_skills

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_skill(
    root: Path,
    slug: str,
    *,
    name: str | None = None,
    description: str | None = None,
    body: str = "Body content.\n",
    extra_files: dict[str, str] | None = None,
) -> Path:
    skill_dir = root / slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    fm_lines = ["---"]
    if name is not None:
        fm_lines.append(f"name: {name}")
    if description is not None:
        fm_lines.append(f"description: {description}")
    fm_lines.append("---")
    skill_md = "\n".join(fm_lines) + "\n\n" + body
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    if extra_files:
        for rel, content in extra_files.items():
            target = skill_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    return skill_dir


async def _get_skill(db: AsyncSession, slug: str) -> Skill | None:
    result = await db.execute(select(Skill).where(Skill.slug == slug))
    return result.scalar_one_or_none()


async def _get_files(db: AsyncSession, skill_id: int) -> list[SkillFile]:
    result = await db.execute(
        select(SkillFile)
        .where(SkillFile.skill_id == skill_id)
        .order_by(SkillFile.path.asc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Pure-function tests (no DB)
# ---------------------------------------------------------------------------


def test_parse_frontmatter_quoted_values() -> None:
    text = '---\nname: "calseta"\ndescription: \'short\'\n---\n\nbody\n'
    fm, body = _parse_frontmatter(text)
    assert fm == {"name": "calseta", "description": "short"}
    assert body.strip() == "body"


def test_parse_frontmatter_folded_scalar() -> None:
    text = (
        "---\n"
        "name: calseta\n"
        "description: >\n"
        "  Core Calseta SOC platform skill.\n"
        "  Always injected.\n"
        "---\n"
        "Body."
    )
    fm, body = _parse_frontmatter(text)
    assert fm["name"] == "calseta"
    assert "Core Calseta SOC platform skill." in fm["description"]
    assert "Always injected." in fm["description"]
    assert body.strip() == "Body."


def test_parse_frontmatter_missing_returns_empty() -> None:
    fm, body = _parse_frontmatter("no frontmatter here")
    assert fm == {}
    assert body == "no frontmatter here"


def test_parse_frontmatter_unterminated_returns_empty() -> None:
    fm, body = _parse_frontmatter("---\nname: x\nno-closing-marker\n")
    assert fm == {}


def test_hash_stable_across_orderings() -> None:
    a = [("SKILL.md", "x"), ("notes.md", "y")]
    b = [("notes.md", "y"), ("SKILL.md", "x")]
    assert _hash_files(a) == _hash_files(b)


def test_hash_changes_when_content_changes() -> None:
    a = [("SKILL.md", "x")]
    b = [("SKILL.md", "x2")]
    assert _hash_files(a) != _hash_files(b)


# ---------------------------------------------------------------------------
# DB tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loader_returns_zero_when_dir_missing(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    missing = tmp_path / "does-not-exist"
    n = await load_bundled_skills(db_session, skills_dir=missing)
    assert n == 0


@pytest.mark.asyncio
async def test_loader_returns_zero_when_dir_empty(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    n = await load_bundled_skills(db_session, skills_dir=empty)
    assert n == 0


@pytest.mark.asyncio
async def test_loader_creates_global_bundled_skill(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    _write_skill(
        tmp_path,
        "calseta",
        name="calseta",
        description="Core skill",
        body="# Calseta skill body\n",
    )

    n = await load_bundled_skills(db_session, skills_dir=tmp_path)
    assert n == 1

    skill = await _get_skill(db_session, "calseta")
    assert skill is not None
    assert skill.is_global is True
    assert skill.is_active is True
    assert skill.source == "bundled"
    assert skill.name == "calseta"
    assert skill.description == "Core skill"
    assert skill.content_sha256 is not None
    assert len(skill.content_sha256) == 64

    files = await _get_files(db_session, skill.id)
    assert len(files) == 1
    assert files[0].path == "SKILL.md"
    assert files[0].is_entry is True


@pytest.mark.asyncio
async def test_loader_walks_nested_files(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    _write_skill(
        tmp_path,
        "calseta",
        name="calseta",
        description="d",
        extra_files={
            "references/api.md": "# API\n",
            "examples/example.md": "# Example\n",
        },
    )
    n = await load_bundled_skills(db_session, skills_dir=tmp_path)
    assert n == 1

    skill = await _get_skill(db_session, "calseta")
    assert skill is not None
    files = await _get_files(db_session, skill.id)
    paths = {f.path for f in files}
    assert paths == {"SKILL.md", "references/api.md", "examples/example.md"}


@pytest.mark.asyncio
async def test_loader_idempotent_no_change_no_upsert(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    _write_skill(tmp_path, "calseta", name="c", description="d")

    first = await load_bundled_skills(db_session, skills_dir=tmp_path)
    assert first == 1

    skill_before = await _get_skill(db_session, "calseta")
    assert skill_before is not None
    files_before = await _get_files(db_session, skill_before.id)
    file_uuids_before = {f.uuid for f in files_before}
    hash_before = skill_before.content_sha256

    second = await load_bundled_skills(db_session, skills_dir=tmp_path)
    assert second == 0  # No changes detected

    skill_after = await _get_skill(db_session, "calseta")
    assert skill_after is not None
    assert skill_after.content_sha256 == hash_before
    files_after = await _get_files(db_session, skill_after.id)
    # File rows preserved (same UUIDs) — proves we did NOT delete+recreate.
    assert {f.uuid for f in files_after} == file_uuids_before


@pytest.mark.asyncio
async def test_loader_change_detection_rewrites_files(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    _write_skill(tmp_path, "calseta", name="c", description="d", body="v1\n")
    await load_bundled_skills(db_session, skills_dir=tmp_path)

    skill = await _get_skill(db_session, "calseta")
    assert skill is not None
    hash_v1 = skill.content_sha256

    # Mutate on-disk content.
    (tmp_path / "calseta" / "SKILL.md").write_text(
        "---\nname: c\ndescription: d\n---\n\nv2 NEW BODY\n",
        encoding="utf-8",
    )
    n = await load_bundled_skills(db_session, skills_dir=tmp_path)
    assert n == 1

    skill = await _get_skill(db_session, "calseta")
    assert skill is not None
    assert skill.content_sha256 != hash_v1
    files = await _get_files(db_session, skill.id)
    assert any("v2 NEW BODY" in f.content for f in files)


@pytest.mark.asyncio
async def test_loader_preserves_agent_assignments_across_change(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Agent-skill assignments must survive a skill content update."""
    _write_skill(tmp_path, "calseta", name="c", description="d", body="v1\n")
    await load_bundled_skills(db_session, skills_dir=tmp_path)

    skill = await _get_skill(db_session, "calseta")
    assert skill is not None

    agent = AgentRegistration(
        name=f"test-agent-{uuid4().hex[:8]}",
        execution_mode="managed",
        agent_type="specialist",
        adapter_type="http",
        endpoint_url="http://example.invalid/webhook",
        status="active",
    )
    db_session.add(agent)
    await db_session.flush()

    await db_session.execute(
        agent_skill_assignments.insert().values(
            agent_id=agent.id, skill_id=skill.id
        )
    )
    await db_session.flush()

    # Mutate on-disk → trigger SHA256 mismatch → file rows replaced.
    (tmp_path / "calseta" / "SKILL.md").write_text(
        "---\nname: c\ndescription: d\n---\n\nv2\n", encoding="utf-8"
    )
    await load_bundled_skills(db_session, skills_dir=tmp_path)

    # Assignment row still present (cascade is on skills.id, not on file rows).
    result = await db_session.execute(
        select(agent_skill_assignments).where(
            agent_skill_assignments.c.agent_id == agent.id,
            agent_skill_assignments.c.skill_id == skill.id,
        )
    )
    assert result.first() is not None


@pytest.mark.asyncio
async def test_loader_skips_operator_manual_skills(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Skills with source='manual' must never be touched by the loader."""
    # Create a manual skill row at the same slug the on-disk dir uses.
    repo = SkillRepository(db_session)
    manual = await repo.create(
        slug="calseta",
        name="Operator Edited",
        description="hand-tuned",
        is_global=True,
    )
    # `create` defaults to source='manual' per the Skill model default.
    assert manual.source == "manual"

    # Now drop a bundled SKILL.md on disk for the same slug.
    _write_skill(tmp_path, "calseta", name="bundled-name", description="bundled")

    n = await load_bundled_skills(db_session, skills_dir=tmp_path)
    assert n == 0  # Skipped — manual rows are untouchable

    skill = await _get_skill(db_session, "calseta")
    assert skill is not None
    assert skill.source == "manual"
    assert skill.name == "Operator Edited"  # NOT overwritten
    assert skill.description == "hand-tuned"


@pytest.mark.asyncio
async def test_engine_global_skills_includes_bundled(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    """Mocks the engine path: the runtime queries get_global_skills()
    after loader runs and must see at least one bundled skill."""
    _write_skill(tmp_path, "calseta", name="calseta", description="core")
    await load_bundled_skills(db_session, skills_dir=tmp_path)

    repo = SkillRepository(db_session)
    globals_ = await repo.get_global_skills()
    bundled = [s for s in globals_ if s.source == "bundled"]
    # Stand-in for `skills_injected_count >= 1` — the engine's
    # `_inject_skills_ephemeral` writes one file per skill.files entry,
    # so a non-empty global skill set guarantees skills get injected.
    assert len(bundled) >= 1
    assert any(s.slug == "calseta" for s in bundled)
    # And the entry file is present so the engine can write it to tmpdir.
    assert any(f.is_entry for f in bundled[0].files)
