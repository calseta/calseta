"""Agent Control Plane Phase 5 — multi-agent invocations table.

New table: agent_invocations.
Tracks orchestrator→specialist delegation with status lifecycle,
input/output context, cost rollup, and timeout enforcement.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # agent_invocations
    # FKs: agent_registrations (parent + child), alerts, alert_assignments
    # ----------------------------------------------------------------
    op.create_table(
        "agent_invocations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("parent_agent_id", sa.BigInteger(), nullable=False),
        sa.Column("child_agent_id", sa.BigInteger(), nullable=True),
        sa.Column("alert_id", sa.BigInteger(), nullable=False),
        sa.Column("assignment_id", sa.BigInteger(), nullable=True),
        sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column("input_context", postgresql.JSONB(), nullable=True),
        sa.Column("output_schema", postgresql.JSONB(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cost_cents",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("300"),
        ),
        sa.Column("task_queue_id", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_agent_id"],
            ["agent_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["child_agent_id"],
            ["agent_registrations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["alert_assignments.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_agent_invocations_uuid"),
    )
    op.create_index("idx_agent_invocations_status", "agent_invocations", ["status"])
    op.create_index(
        "idx_agent_invocations_parent", "agent_invocations", ["parent_agent_id"]
    )
    op.create_index(
        "idx_agent_invocations_alert", "agent_invocations", ["alert_id"]
    )
    op.create_index(
        "idx_agent_invocations_queued",
        "agent_invocations",
        ["created_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    op.drop_index("idx_agent_invocations_queued", table_name="agent_invocations")
    op.drop_index("idx_agent_invocations_alert", table_name="agent_invocations")
    op.drop_index("idx_agent_invocations_parent", table_name="agent_invocations")
    op.drop_index("idx_agent_invocations_status", table_name="agent_invocations")
    op.drop_table("agent_invocations")
