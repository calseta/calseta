"""Add issue_category_defs table with system defaults.

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_SYSTEM_CATEGORIES = [
    ("remediation", "Remediation"),
    ("detection_tuning", "Detection Tuning"),
    ("investigation", "Investigation"),
    ("compliance", "Compliance"),
    ("post_incident", "Post Incident"),
    ("maintenance", "Maintenance"),
    ("custom", "Custom"),
]


def upgrade() -> None:
    op.create_table(
        "issue_category_defs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "uuid",
            sa.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("key"),
    )

    # Seed system defaults
    op.bulk_insert(
        sa.table(
            "issue_category_defs",
            sa.column("key", sa.Text),
            sa.column("label", sa.Text),
            sa.column("is_system", sa.Boolean),
        ),
        [
            {"key": key, "label": label, "is_system": True}
            for key, label in _SYSTEM_CATEGORIES
        ],
    )


def downgrade() -> None:
    op.drop_table("issue_category_defs")
