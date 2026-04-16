"""Create agent_run_events table for structured run event logging.

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_run_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "heartbeat_run_id",
            sa.BigInteger,
            sa.ForeignKey("heartbeat_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("stream", sa.Text, nullable=False),
        sa.Column(
            "level",
            sa.Text,
            nullable=False,
            server_default=sa.text("'info'"),
        ),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_agent_run_events_run_seq",
        "agent_run_events",
        ["heartbeat_run_id", "seq"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_run_events_run_seq", table_name="agent_run_events")
    op.drop_table("agent_run_events")
