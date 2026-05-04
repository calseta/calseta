"""Universal startup loader for bundled skills.

Walks ``BUNDLED_SKILLS_DIR`` (default ``app/skills``) and upserts every
subdirectory containing a ``SKILL.md`` into the ``skills`` table as a
global, ``source='bundled'`` skill.

Design notes
------------
* **Universal** — runs on every API boot, not only in lab/sandbox mode.
  The ``app/seed/sandbox_control_plane.py::_seed_bundled_skills`` lab
  seeder remains for assignment-wiring scenarios; this loader is the
  baseline so production deployments also get bundled skills.
* **Idempotent** — repeat startups never duplicate rows. A SHA256 over
  the concatenated file contents per skill drives change detection;
  identical content is a no-op past the cheap hash compare.
* **Operator-safe** — only rows with ``source='bundled'`` are touched.
  If an operator changes a skill via the UI the row's ``source`` is set
  to ``'manual'`` (by the API repository) and the loader will skip it
  forever.
* **Best-effort** — exceptions are caught at the call site (in
  ``app.main._on_startup``) and logged as ``app.bundled_skills_load_failed``
  so a missing ``app/skills/`` dir (e.g. minimal containers) cannot
  crash the API.

Frontmatter
-----------
Each ``SKILL.md`` may begin with a YAML frontmatter block delimited by
``---`` lines. Supported keys:

* ``name``        — display name; defaults to the slug
* ``description`` — short description; defaults to ``None``

If frontmatter is missing or malformed the body is treated as the full
file content (no name/description override) — the loader never raises.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.skill_repository import SkillRepository

logger = structlog.get_logger(__name__)


_DEFAULT_SKILLS_DIR = Path("app/skills")
# Files we never persist as SkillFile rows (Python plumbing, caches, etc.)
_SKIP_FILE_NAMES: frozenset[str] = frozenset({"__init__.py"})
_SKIP_DIR_NAMES: frozenset[str] = frozenset({"__pycache__", ".git"})


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a SKILL.md into (frontmatter dict, body).

    Tolerates any malformed input by returning ({}, text). Only string
    scalar values are extracted — list/dict YAML values are ignored to
    avoid pulling in PyYAML for a 2-key frontmatter.
    """
    if not text.startswith("---"):
        return {}, text
    # Split at most twice on lines starting with '---' to isolate the
    # frontmatter block.
    lines = text.splitlines(keepends=False)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
    if end_idx == -1:
        return {}, text

    fm: dict[str, str] = {}
    current_key: str | None = None
    current_parts: list[str] = []
    for raw in lines[1:end_idx]:
        if not raw.strip():
            continue
        # Folded scalar continuation (leading whitespace, no colon yet).
        if current_key is not None and raw.startswith((" ", "\t")):
            current_parts.append(raw.strip())
            continue
        if ":" not in raw:
            continue
        # Flush previous folded value before starting a new key.
        if current_key is not None:
            fm[current_key] = " ".join(current_parts).strip()
            current_key = None
            current_parts = []
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # Folded scalar marker — collect continuation lines.
        if value in (">", "|", ">-", "|-"):
            current_key = key
            current_parts = []
            continue
        # Strip surrounding quotes if present.
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        fm[key] = value
    if current_key is not None:
        fm[current_key] = " ".join(current_parts).strip()

    body = "\n".join(lines[end_idx + 1 :])
    return fm, body


def _discover_skill_dirs(skills_dir: Path) -> list[Path]:
    """Return every immediate child of ``skills_dir`` that contains SKILL.md."""
    if not skills_dir.is_dir():
        return []
    out: list[Path] = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name in _SKIP_DIR_NAMES or child.name.startswith("."):
            continue
        if (child / "SKILL.md").is_file():
            out.append(child)
    return out


def _collect_skill_files(skill_dir: Path) -> list[tuple[str, str]]:
    """Walk a skill directory and return ``[(relative_path, content), ...]``.

    Paths are POSIX-style relative to ``skill_dir`` so they round-trip into
    ``SkillFile.path`` exactly as the runtime engine expects when it
    re-materializes them under ``{tmpdir}/{slug}/{path}``.
    """
    files: list[tuple[str, str]] = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in _SKIP_FILE_NAMES:
            continue
        if any(part in _SKIP_DIR_NAMES for part in path.parts):
            continue
        rel = path.relative_to(skill_dir).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Binary file — skip rather than corrupt the row.
            logger.warning(
                "app.bundled_skills_skip_binary_file",
                skill_dir=str(skill_dir),
                file=rel,
            )
            continue
        files.append((rel, content))
    return files


def _hash_files(files: list[tuple[str, str]]) -> str:
    """SHA256 over the sorted (path, content) tuples."""
    h = hashlib.sha256()
    for path, content in sorted(files):
        h.update(path.encode("utf-8"))
        h.update(b"\0")
        h.update(content.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


async def load_bundled_skills(
    db: AsyncSession,
    *,
    skills_dir: Path = _DEFAULT_SKILLS_DIR,
) -> int:
    """Load every bundled skill under ``skills_dir`` into the database.

    Returns the number of skills that were created OR updated this pass
    (skills whose hash matched the DB are not counted).

    The function commits no transactions itself — the caller controls the
    session lifecycle. It only ``flush()``es so subsequent queries within
    the same transaction see the new rows.
    """
    skill_dirs = _discover_skill_dirs(skills_dir)
    if not skill_dirs:
        logger.warning(
            "app.bundled_skills_dir_empty",
            skills_dir=str(skills_dir),
            hint=(
                "No bundled skills found — production deployments expect "
                "at least 'calseta'. Check that app/skills/ shipped with "
                "the image."
            ),
        )
        return 0

    repo = SkillRepository(db)
    changed_count = 0
    skipped_manual = 0

    for skill_dir in skill_dirs:
        slug = skill_dir.name
        files = _collect_skill_files(skill_dir)
        if not files:
            continue

        # Frontmatter on SKILL.md drives display name / description.
        entry = next(
            ((p, c) for (p, c) in files if p == "SKILL.md"),
            None,
        )
        fm: dict[str, str] = {}
        if entry is not None:
            fm, _ = _parse_frontmatter(entry[1])
        name = fm.get("name") or slug
        description = fm.get("description") or None

        content_hash = _hash_files(files)

        skill, was_changed = await repo.upsert_bundled_skill(
            slug=slug,
            name=name,
            description=description,
            content_sha256=content_hash,
        )

        # The repo returns changed=False for operator-edited rows so we
        # never blow away their files.
        if skill.source != "bundled":
            skipped_manual += 1
            continue

        if was_changed:
            await repo.replace_bundled_files(skill.id, files)
            changed_count += 1
            logger.info(
                "app.bundled_skill_loaded",
                slug=slug,
                file_count=len(files),
                content_sha256=content_hash[:12],
            )

    logger.info(
        "app.bundled_skills_load_complete",
        skills_dir=str(skills_dir),
        discovered=len(skill_dirs),
        changed=changed_count,
        skipped_manual=skipped_manual,
    )
    return changed_count
