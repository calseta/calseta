"""Add issue labels, skills, and agent-skill assignments.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- issue_labels ---
    op.create_table(
        "issue_labels",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "uuid",
            sa.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("color", sa.Text(), nullable=False, server_default=sa.text("'#6b7280'")),
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
        sa.UniqueConstraint("name"),
    )

    # --- issue_label_assignments (M2M join) ---
    op.create_table(
        "issue_label_assignments",
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("label_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["issue_id"], ["agent_issues.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["label_id"], ["issue_labels.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("issue_id", "label_id"),
    )

    # --- skills ---
    op.create_table(
        "skills",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "uuid",
            sa.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_global",
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
        sa.UniqueConstraint("slug"),
    )

    # --- skill_files (file tree per skill) ---
    op.create_table(
        "skill_files",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "uuid",
            sa.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column(
            "is_entry",
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
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("skill_id", "path", name="uq_skill_files_skill_id_path"),
    )

    # --- agent_skill_assignments (M2M join) ---
    op.create_table(
        "agent_skill_assignments",
        sa.Column("agent_id", sa.BigInteger(), nullable=False),
        sa.Column("skill_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["agent_id"], ["agent_registrations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("agent_id", "skill_id"),
    )


def downgrade() -> None:
    op.drop_table("agent_skill_assignments")
    op.drop_table("skill_files")
    op.drop_table("skills")
    op.drop_table("issue_label_assignments")
    op.drop_table("issue_labels")
