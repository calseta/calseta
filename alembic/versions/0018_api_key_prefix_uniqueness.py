"""S17 — Drop unique constraint on api_keys.key_prefix; add lookup index.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-04

S17 hardening: API key prefixes are NOT guaranteed to be unique. Two keys
can collide on the first N plaintext characters; bcrypt hash is what
distinguishes them. The auth backend already uses iterate-and-bcrypt over
candidates, but the table-level UNIQUE constraint on ``key_prefix`` would
cause new key creation to fail outright when a collision happened.

Existing rows already have an 8-char prefix and are kept as-is — the
iterate-and-bcrypt flow handles 8-char prefixes too. New rows will use the
16-char prefix from ``app.auth.api_key_backend._KEY_PREFIX_LEN``. The
``key_prefix`` column is already ``TEXT`` so no length change is needed.

A non-unique B-tree index on ``key_prefix`` keeps the lookup fast.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The constraint was created without an explicit name — Postgres
    # auto-generates ``<table>_<column>_key`` for an inline UNIQUE.
    op.drop_constraint("api_keys_key_prefix_key", "api_keys", type_="unique")
    op.create_index(
        "idx_api_keys_key_prefix",
        "api_keys",
        ["key_prefix"],
    )


def downgrade() -> None:
    # Re-adding the unique constraint requires no duplicates exist; that's
    # the operator's responsibility before running ``downgrade``.
    op.drop_index("idx_api_keys_key_prefix", table_name="api_keys")
    op.create_unique_constraint(
        "api_keys_key_prefix_key", "api_keys", ["key_prefix"]
    )
