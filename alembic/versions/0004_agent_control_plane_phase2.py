"""Agent Control Plane Phase 2 — actions system and user validation.

New tables: user_validation_templates, agent_actions, user_validation_rules.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # user_validation_templates (no FK deps — create first)
    # ----------------------------------------------------------------
    op.create_table(
        "user_validation_templates",
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("message_body", sa.Text(), nullable=False),
        sa.Column("response_type", sa.Text(), nullable=False),
        sa.Column("confirm_label", sa.Text(), nullable=True),
        sa.Column("deny_label", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_user_validation_templates_name"),
        sa.UniqueConstraint("uuid", name="uq_user_validation_templates_uuid"),
    )

    # ----------------------------------------------------------------
    # agent_actions (FKs: alerts, agent_registrations, alert_assignments,
    #                      workflow_approval_requests)
    # ----------------------------------------------------------------
    op.create_table(
        "agent_actions",
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
        sa.Column("alert_id", sa.BigInteger(), nullable=False),
        sa.Column("agent_registration_id", sa.BigInteger(), nullable=False),
        sa.Column("assignment_id", sa.BigInteger(), nullable=False),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("action_subtype", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'proposed'"),
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=True),
        sa.Column("approval_request_id", sa.BigInteger(), nullable=True),
        sa.Column("execution_result", postgresql.JSONB(), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["agent_registration_id"],
            ["agent_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_id"],
            ["alert_assignments.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["approval_request_id"],
            ["workflow_approval_requests.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_agent_actions_uuid"),
    )
    op.create_index("idx_agent_actions_status", "agent_actions", ["status"])
    op.create_index("idx_agent_actions_assignment", "agent_actions", ["assignment_id"])
    op.create_index(
        "idx_agent_actions_approval",
        "agent_actions",
        ["approval_request_id"],
        postgresql_where=sa.text("approval_request_id IS NOT NULL"),
    )

    # ----------------------------------------------------------------
    # user_validation_rules (FK: user_validation_templates)
    # ----------------------------------------------------------------
    op.create_table(
        "user_validation_rules",
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("trigger_conditions", postgresql.JSONB(), nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=True),
        sa.Column("user_field_path", sa.Text(), nullable=False),
        sa.Column(
            "timeout_hours",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("4"),
        ),
        sa.Column(
            "on_confirm",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'close_alert'"),
        ),
        sa.Column(
            "on_deny",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'escalate_alert'"),
        ),
        sa.Column(
            "on_timeout",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'escalate_alert'"),
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["user_validation_templates.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_user_validation_rules_uuid"),
    )
    op.create_index(
        "idx_user_validation_rules_active",
        "user_validation_rules",
        ["is_active", "priority"],
    )


def downgrade() -> None:
    op.drop_table("user_validation_rules")

    op.drop_index("idx_agent_actions_approval", table_name="agent_actions")
    op.drop_index("idx_agent_actions_assignment", table_name="agent_actions")
    op.drop_index("idx_agent_actions_status", table_name="agent_actions")
    op.drop_table("agent_actions")

    op.drop_table("user_validation_templates")
