"""Add agent_workspaces table and workspace_mode column to agent_registrations.

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- agent_workspaces --
    op.create_table(
        "agent_workspaces",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column(
            "uuid",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "agent_registration_id",
            sa.BigInteger(),
            sa.ForeignKey("agent_registrations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'generic'"),
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("directory_path", sa.Text(), nullable=True),
        sa.Column("git_remote_url", sa.Text(), nullable=True),
        sa.Column("git_branch", sa.Text(), nullable=True),
        sa.Column("git_last_commit_sha", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid"),
    )

    # -- Add workspace_mode to agent_registrations --
    op.add_column(
        "agent_registrations",
        sa.Column(
            "workspace_mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'none'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_registrations", "workspace_mode")
    op.drop_table("agent_workspaces")
