"""Add runtime hardening columns to heartbeat_runs.

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "heartbeat_runs"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column("process_pid", sa.Integer(), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "process_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column("error_code", sa.Text(), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "log_store",
            sa.Text(),
            nullable=False,
            server_default="local_file",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column("log_ref", sa.Text(), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column("log_sha256", sa.Text(), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column("log_bytes", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column("stdout_excerpt", sa.Text(), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column("stderr_excerpt", sa.Text(), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "process_loss_retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column(
            "retry_of_run_id",
            sa.BigInteger(),
            nullable=True,
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column("invocation_source", sa.Text(), nullable=True),
    )
    op.create_foreign_key(
        "fk_heartbeat_runs_retry_of_run_id",
        _TABLE,
        _TABLE,
        ["retry_of_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_heartbeat_runs_retry_of_run_id",
        _TABLE,
        type_="foreignkey",
    )
    op.drop_column(_TABLE, "invocation_source")
    op.drop_column(_TABLE, "retry_of_run_id")
    op.drop_column(_TABLE, "process_loss_retry_count")
    op.drop_column(_TABLE, "stderr_excerpt")
    op.drop_column(_TABLE, "stdout_excerpt")
    op.drop_column(_TABLE, "log_bytes")
    op.drop_column(_TABLE, "log_sha256")
    op.drop_column(_TABLE, "log_ref")
    op.drop_column(_TABLE, "log_store")
    op.drop_column(_TABLE, "error_code")
    op.drop_column(_TABLE, "process_started_at")
    op.drop_column(_TABLE, "process_pid")
