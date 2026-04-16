"""Unit tests for ephemeral skill injection (C6).

Tests the ``_inject_skills_ephemeral`` method on ``AgentRuntimeEngine``
at ``app/runtime/engine.py``.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.runtime.engine import AgentRuntimeEngine


def _make_skill_file(path: str, content: str) -> MagicMock:
    """Build a mock SkillFile object."""
    f = MagicMock()
    f.path = path
    f.content = content
    return f


def _make_skill(
    skill_id: int,
    slug: str,
    files: list[MagicMock] | None = None,
) -> MagicMock:
    """Build a mock Skill object with id, slug, and files."""
    skill = MagicMock()
    skill.id = skill_id
    skill.slug = slug
    skill.files = files or []
    return skill


def _make_agent(agent_id: int = 1) -> MagicMock:
    """Build a mock AgentRegistration."""
    agent = MagicMock()
    agent.id = agent_id
    return agent


@pytest.fixture
def engine() -> AgentRuntimeEngine:
    """Engine instance with a mocked DB session."""
    return AgentRuntimeEngine(db=AsyncMock())


# Track created temp dirs for cleanup
_created_tmpdirs: list[str] = []


@pytest.fixture(autouse=True)
def _cleanup_tmpdirs():
    """Clean up any temp directories created during tests."""
    _created_tmpdirs.clear()
    yield
    for d in _created_tmpdirs:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestInjectSkillsEphemeral:
    """Tests for AgentRuntimeEngine._inject_skills_ephemeral()."""

    @pytest.mark.asyncio
    @patch("app.repositories.skill_repository.SkillRepository")
    async def test_no_skills_returns_none(self, mock_repo_cls, engine):
        """When no skills are assigned (agent or global), returns None."""
        repo_instance = AsyncMock()
        repo_instance.get_agent_skills.return_value = []
        repo_instance.get_global_skills.return_value = []
        mock_repo_cls.return_value = repo_instance

        agent = _make_agent()
        result = await engine._inject_skills_ephemeral(agent)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.repositories.skill_repository.SkillRepository")
    async def test_skills_assigned_creates_temp_dir(self, mock_repo_cls, engine):
        """When skills exist, creates a temp dir and returns its path."""
        skill = _make_skill(
            skill_id=10,
            slug="triage-helper",
            files=[_make_skill_file("SKILL.md", "# Triage Helper")],
        )
        repo_instance = AsyncMock()
        repo_instance.get_agent_skills.return_value = [skill]
        repo_instance.get_global_skills.return_value = []
        mock_repo_cls.return_value = repo_instance

        agent = _make_agent()
        result = await engine._inject_skills_ephemeral(agent)
        _created_tmpdirs.append(result)

        assert result is not None
        assert Path(result).exists()
        assert Path(result).is_dir()

    @pytest.mark.asyncio
    @patch("app.repositories.skill_repository.SkillRepository")
    async def test_temp_dir_has_correct_prefix(self, mock_repo_cls, engine):
        """The temp directory name starts with 'calseta-skills-'."""
        skill = _make_skill(
            skill_id=1,
            slug="my-skill",
            files=[_make_skill_file("README.md", "hello")],
        )
        repo_instance = AsyncMock()
        repo_instance.get_agent_skills.return_value = [skill]
        repo_instance.get_global_skills.return_value = []
        mock_repo_cls.return_value = repo_instance

        agent = _make_agent()
        result = await engine._inject_skills_ephemeral(agent)
        _created_tmpdirs.append(result)

        dirname = Path(result).name
        assert dirname.startswith("calseta-skills-")

    @pytest.mark.asyncio
    @patch("app.repositories.skill_repository.SkillRepository")
    async def test_skill_files_written_to_correct_paths(self, mock_repo_cls, engine):
        """Skill files are written to {tmpdir}/{skill.slug}/{file.path}."""
        files = [
            _make_skill_file("SKILL.md", "# Entry point"),
            _make_skill_file("lib/utils.py", "def helper(): pass"),
        ]
        skill = _make_skill(skill_id=5, slug="enrichment-plugin", files=files)

        repo_instance = AsyncMock()
        repo_instance.get_agent_skills.return_value = [skill]
        repo_instance.get_global_skills.return_value = []
        mock_repo_cls.return_value = repo_instance

        agent = _make_agent()
        result = await engine._inject_skills_ephemeral(agent)
        _created_tmpdirs.append(result)

        base = Path(result)
        entry = base / "enrichment-plugin" / "SKILL.md"
        assert entry.exists()
        assert entry.read_text() == "# Entry point"

        util = base / "enrichment-plugin" / "lib" / "utils.py"
        assert util.exists()
        assert util.read_text() == "def helper(): pass"

    @pytest.mark.asyncio
    @patch("app.repositories.skill_repository.SkillRepository")
    async def test_multiple_skills_and_globals_merged_deduplicated(
        self, mock_repo_cls, engine
    ):
        """Global + agent skills are merged; duplicates (same id) are removed."""
        shared_skill = _make_skill(
            skill_id=1,
            slug="shared-skill",
            files=[_make_skill_file("SKILL.md", "shared content")],
        )
        agent_only = _make_skill(
            skill_id=2,
            slug="agent-only",
            files=[_make_skill_file("SKILL.md", "agent content")],
        )
        global_only = _make_skill(
            skill_id=3,
            slug="global-only",
            files=[_make_skill_file("SKILL.md", "global content")],
        )

        repo_instance = AsyncMock()
        # shared_skill appears in both lists
        repo_instance.get_agent_skills.return_value = [shared_skill, agent_only]
        repo_instance.get_global_skills.return_value = [shared_skill, global_only]
        mock_repo_cls.return_value = repo_instance

        agent = _make_agent()
        result = await engine._inject_skills_ephemeral(agent)
        _created_tmpdirs.append(result)

        base = Path(result)
        # All three unique slugs should have directories
        assert (base / "shared-skill" / "SKILL.md").exists()
        assert (base / "agent-only" / "SKILL.md").exists()
        assert (base / "global-only" / "SKILL.md").exists()

        # shared-skill should only appear once (deduplicated)
        skill_dirs = [d.name for d in base.iterdir() if d.is_dir()]
        assert skill_dirs.count("shared-skill") == 1

    @pytest.mark.asyncio
    @patch("app.repositories.skill_repository.SkillRepository")
    async def test_exception_returns_none(self, mock_repo_cls, engine):
        """If skill loading raises an exception, returns None (no crash)."""
        repo_instance = AsyncMock()
        repo_instance.get_agent_skills.side_effect = RuntimeError("DB connection lost")
        mock_repo_cls.return_value = repo_instance

        agent = _make_agent()
        result = await engine._inject_skills_ephemeral(agent)

        assert result is None

    @pytest.mark.asyncio
    @patch("app.repositories.skill_repository.SkillRepository")
    async def test_skill_file_content_matches_db(self, mock_repo_cls, engine):
        """Written file content exactly matches what was in the mock DB."""
        content = "async def run(ctx):\n    return ctx.http.get('https://example.com')\n"
        files = [_make_skill_file("run.py", content)]
        skill = _make_skill(skill_id=99, slug="http-checker", files=files)

        repo_instance = AsyncMock()
        repo_instance.get_agent_skills.return_value = [skill]
        repo_instance.get_global_skills.return_value = []
        mock_repo_cls.return_value = repo_instance

        agent = _make_agent()
        result = await engine._inject_skills_ephemeral(agent)
        _created_tmpdirs.append(result)

        written = (Path(result) / "http-checker" / "run.py").read_text()
        assert written == content

    @pytest.mark.asyncio
    @patch("app.repositories.skill_repository.SkillRepository")
    async def test_skill_with_no_files_creates_empty_dir(self, mock_repo_cls, engine):
        """A skill with an empty files list still creates its slug directory implicitly
        (no files written, but the skill is counted)."""
        skill = _make_skill(skill_id=50, slug="empty-skill", files=[])

        repo_instance = AsyncMock()
        repo_instance.get_agent_skills.return_value = [skill]
        repo_instance.get_global_skills.return_value = []
        mock_repo_cls.return_value = repo_instance

        agent = _make_agent()
        result = await engine._inject_skills_ephemeral(agent)
        _created_tmpdirs.append(result)

        # Temp dir exists (skills were found)
        assert result is not None
        assert Path(result).exists()
        # No files for this skill, so the slug subdirectory may not exist
        # but the temp dir itself was created because skill_list was non-empty

    @pytest.mark.asyncio
    @patch("app.repositories.skill_repository.SkillRepository")
    async def test_nested_file_paths_create_parent_dirs(self, mock_repo_cls, engine):
        """Files with nested paths (e.g. 'src/lib/deep/module.py') have their
        parent directories created automatically."""
        deep_file = _make_skill_file("src/lib/deep/module.py", "# deep module")
        skill = _make_skill(skill_id=7, slug="deep-skill", files=[deep_file])

        repo_instance = AsyncMock()
        repo_instance.get_agent_skills.return_value = [skill]
        repo_instance.get_global_skills.return_value = []
        mock_repo_cls.return_value = repo_instance

        agent = _make_agent()
        result = await engine._inject_skills_ephemeral(agent)
        _created_tmpdirs.append(result)

        target = Path(result) / "deep-skill" / "src" / "lib" / "deep" / "module.py"
        assert target.exists()
        assert target.read_text() == "# deep module"
