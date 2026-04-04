"""Phase 5.5 — Issues, Routines, Campaigns.

New tables: agent_issues, agent_issue_comments, agent_routines,
routine_triggers, routine_runs, campaigns, campaign_items.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # agent_issues
    # FKs: agent_registrations (assignee, created_by), alerts, heartbeat_runs, self
    # ----------------------------------------------------------------
    op.create_table(
        "agent_issues",
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
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.BigInteger(), nullable=True),
        sa.Column("alert_id", sa.BigInteger(), nullable=True),
        sa.Column("routine_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'backlog'")),
        sa.Column("priority", sa.Text(), nullable=False, server_default=sa.text("'medium'")),
        sa.Column("category", sa.Text(), nullable=False, server_default=sa.text("'investigation'")),
        sa.Column("assignee_agent_id", sa.BigInteger(), nullable=True),
        sa.Column("assignee_operator", sa.Text(), nullable=True),
        sa.Column("created_by_agent_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by_operator", sa.Text(), nullable=True),
        sa.Column("checkout_run_id", sa.BigInteger(), nullable=True),
        sa.Column("execution_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["agent_issues.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["alert_id"],
            ["alerts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assignee_agent_id"],
            ["agent_registrations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_agent_id"],
            ["agent_registrations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["checkout_run_id"],
            ["heartbeat_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_agent_issues_uuid"),
        sa.UniqueConstraint("identifier", name="uq_agent_issues_identifier"),
    )
    op.create_index("idx_agent_issues_status", "agent_issues", ["status"])
    op.create_index("idx_agent_issues_assignee", "agent_issues", ["assignee_agent_id"])
    op.create_index("idx_agent_issues_alert", "agent_issues", ["alert_id"])

    # ----------------------------------------------------------------
    # agent_issue_comments
    # FKs: agent_issues, agent_registrations (author)
    # ----------------------------------------------------------------
    op.create_table(
        "agent_issue_comments",
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
        sa.Column("issue_id", sa.BigInteger(), nullable=False),
        sa.Column("author_agent_id", sa.BigInteger(), nullable=True),
        sa.Column("author_operator", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["issue_id"],
            ["agent_issues.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_agent_id"],
            ["agent_registrations.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_agent_issue_comments_uuid"),
    )
    op.create_index("idx_agent_issue_comments_issue", "agent_issue_comments", ["issue_id"])

    # ----------------------------------------------------------------
    # agent_routines
    # FKs: agent_registrations
    # ----------------------------------------------------------------
    op.create_table(
        "agent_routines",
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
        sa.Column("agent_registration_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
        sa.Column(
            "concurrency_policy",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'skip_if_active'"),
        ),
        sa.Column(
            "catch_up_policy",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'skip_missed'"),
        ),
        sa.Column("task_template", postgresql.JSONB(), nullable=False),
        sa.Column(
            "max_consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_registration_id"],
            ["agent_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_agent_routines_uuid"),
    )
    op.create_index("idx_agent_routines_agent", "agent_routines", ["agent_registration_id"])
    op.create_index("idx_agent_routines_status", "agent_routines", ["status"])

    # ----------------------------------------------------------------
    # routine_triggers
    # FKs: agent_routines
    # ----------------------------------------------------------------
    op.create_table(
        "routine_triggers",
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
        sa.Column("routine_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("cron_expression", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=True, server_default=sa.text("'UTC'")),
        sa.Column("webhook_public_id", sa.Text(), nullable=True),
        sa.Column("webhook_secret_hash", sa.Text(), nullable=True),
        sa.Column(
            "webhook_replay_window_sec",
            sa.Integer(),
            nullable=True,
            server_default=sa.text("300"),
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.ForeignKeyConstraint(
            ["routine_id"],
            ["agent_routines.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_routine_triggers_uuid"),
        sa.UniqueConstraint("webhook_public_id", name="uq_routine_triggers_webhook_public_id"),
    )
    op.create_index("idx_routine_triggers_routine", "routine_triggers", ["routine_id"])
    op.create_index(
        "idx_routine_triggers_webhook_public_id",
        "routine_triggers",
        ["webhook_public_id"],
        postgresql_where=sa.text("webhook_public_id IS NOT NULL"),
    )
    op.create_index(
        "idx_routine_triggers_next_run",
        "routine_triggers",
        ["next_run_at"],
        postgresql_where=sa.text("kind = 'cron' AND is_active = true AND next_run_at IS NOT NULL"),
    )

    # ----------------------------------------------------------------
    # routine_runs
    # FKs: agent_routines, routine_triggers, alerts, agent_issues, heartbeat_runs, self
    # ----------------------------------------------------------------
    op.create_table(
        "routine_runs",
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
        sa.Column("routine_id", sa.BigInteger(), nullable=False),
        sa.Column("trigger_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'received'")),
        sa.Column("trigger_payload", postgresql.JSONB(), nullable=True),
        sa.Column("linked_alert_id", sa.BigInteger(), nullable=True),
        sa.Column("linked_issue_id", sa.BigInteger(), nullable=True),
        sa.Column("heartbeat_run_id", sa.BigInteger(), nullable=True),
        sa.Column("coalesced_into_run_id", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["routine_id"],
            ["agent_routines.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trigger_id"],
            ["routine_triggers.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["linked_alert_id"],
            ["alerts.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["linked_issue_id"],
            ["agent_issues.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["heartbeat_run_id"],
            ["heartbeat_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["coalesced_into_run_id"],
            ["routine_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_routine_runs_uuid"),
    )
    op.create_index("idx_routine_runs_routine", "routine_runs", ["routine_id"])
    op.create_index("idx_routine_runs_status", "routine_runs", ["status"])

    # ----------------------------------------------------------------
    # campaigns
    # FKs: agent_registrations (owner)
    # ----------------------------------------------------------------
    op.create_table(
        "campaigns",
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
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("category", sa.Text(), nullable=False, server_default=sa.text("'custom'")),
        sa.Column("owner_agent_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_operator", sa.Text(), nullable=True),
        sa.Column("target_metric", sa.Text(), nullable=True),
        sa.Column("target_value", sa.Numeric(), nullable=True),
        sa.Column("current_value", sa.Numeric(), nullable=True),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_agent_id"],
            ["agent_registrations.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_campaigns_uuid"),
    )
    op.create_index("idx_campaigns_status", "campaigns", ["status"])
    op.create_index("idx_campaigns_owner_agent", "campaigns", ["owner_agent_id"])

    # ----------------------------------------------------------------
    # campaign_items
    # FKs: campaigns
    # ----------------------------------------------------------------
    op.create_table(
        "campaign_items",
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
        sa.Column("campaign_id", sa.BigInteger(), nullable=False),
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column("item_uuid", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["campaign_id"],
            ["campaigns.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_campaign_items_uuid"),
    )
    op.create_index("idx_campaign_items_campaign", "campaign_items", ["campaign_id"])
    op.create_index("idx_campaign_items_type", "campaign_items", ["item_type"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_index("idx_campaign_items_type", table_name="campaign_items")
    op.drop_index("idx_campaign_items_campaign", table_name="campaign_items")
    op.drop_table("campaign_items")

    op.drop_index("idx_campaigns_owner_agent", table_name="campaigns")
    op.drop_index("idx_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")

    op.drop_index("idx_routine_runs_status", table_name="routine_runs")
    op.drop_index("idx_routine_runs_routine", table_name="routine_runs")
    op.drop_table("routine_runs")

    op.drop_index("idx_routine_triggers_next_run", table_name="routine_triggers")
    op.drop_index("idx_routine_triggers_webhook_public_id", table_name="routine_triggers")
    op.drop_index("idx_routine_triggers_routine", table_name="routine_triggers")
    op.drop_table("routine_triggers")

    op.drop_index("idx_agent_routines_status", table_name="agent_routines")
    op.drop_index("idx_agent_routines_agent", table_name="agent_routines")
    op.drop_table("agent_routines")

    op.drop_index("idx_agent_issue_comments_issue", table_name="agent_issue_comments")
    op.drop_table("agent_issue_comments")

    op.drop_index("idx_agent_issues_alert", table_name="agent_issues")
    op.drop_index("idx_agent_issues_assignee", table_name="agent_issues")
    op.drop_index("idx_agent_issues_status", table_name="agent_issues")
    op.drop_table("agent_issues")
