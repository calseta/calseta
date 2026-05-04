"""Bundled skills package.

The non-Python subdirectories of this package (e.g. ``calseta/``) hold
``SKILL.md`` files that ship with Calseta. They are loaded into the
``skills`` table at API startup by ``app.skills.loader.load_bundled_skills``.

Code lives here only so the loader is importable as ``app.skills.loader``;
the ``calseta/`` directory and any future bundled skills are pure content.
"""
