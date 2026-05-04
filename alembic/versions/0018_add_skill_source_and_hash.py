"""Add ``source`` and ``content_sha256`` columns to skills.

Wave 5 / Chunk S14 — universal startup loader for ``app/skills/<slug>/``.

* ``source`` distinguishes operator-edited skills (``'manual'``) from skills
  managed by the bundled-skills loader (``'bundled'``). The loader only
  reconciles rows where ``source = 'bundled'`` so operator edits are safe.
* ``content_sha256`` stores the SHA256 over the concatenated file contents
  per bundled skill. The loader uses it for change detection — file rows
  are only re-written when the hash on disk differs from the DB.

Backfill: any existing ``skills`` row whose slug matches a directory under
``app/skills/`` is marked ``source='bundled'``; everything else stays
``'manual'``. Hashes are intentionally left NULL on backfill so the next
loader pass recomputes them.

NOTE on numbering: this migration is named by content, not by order. If a
sibling chunk (S15) lands first and grabs 0018, re-number this file to
the next free slot at merge time and update ``down_revision`` accordingly.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Slugs of bundled skills shipped in the repo at the time of this migration.
# Used only for backfill — the runtime loader re-discovers them at startup.
_BUNDLED_SLUGS_AT_MIGRATION_TIME = ("calseta",)


def upgrade() -> None:
    op.add_column(
        "skills",
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )
    op.add_column(
        "skills",
        sa.Column("content_sha256", sa.Text(), nullable=True),
    )

    # Backfill: mark known bundled slugs as 'bundled'.
    if _BUNDLED_SLUGS_AT_MIGRATION_TIME:
        op.execute(
            sa.text(
                "UPDATE skills SET source = 'bundled' "
                "WHERE slug = ANY(:slugs)"
            ).bindparams(
                sa.bindparam(
                    "slugs",
                    list(_BUNDLED_SLUGS_AT_MIGRATION_TIME),
                    type_=sa.ARRAY(sa.Text()),
                )
            )
        )


def downgrade() -> None:
    op.drop_column("skills", "content_sha256")
    op.drop_column("skills", "source")
