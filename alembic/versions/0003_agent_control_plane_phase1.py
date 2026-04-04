"""Agent Control Plane Phase 1 — new tables + agent_registrations extension.

New tables: llm_integrations, agent_api_keys, agent_tools, alert_assignments,
agent_task_sessions, heartbeat_runs, cost_events, secrets, secret_versions,
agent_instruction_files.

Alters agent_registrations: adds all control plane columns, migrates is_active → status.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # llm_integrations
    # ----------------------------------------------------------------
    op.create_table(
        "llm_integrations",
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
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("api_key_ref", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("config", postgresql.JSONB(), nullable=True),
        sa.Column(
            "cost_per_1k_input_tokens_cents",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "cost_per_1k_output_tokens_cents",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_llm_integrations_name"),
        sa.UniqueConstraint("uuid", name="uq_llm_integrations_uuid"),
    )
    op.create_index("idx_llm_integrations_name", "llm_integrations", ["name"])

    # ----------------------------------------------------------------
    # secrets
    # ----------------------------------------------------------------
    op.create_table(
        "secrets",
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
            "provider",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'local_encrypted'"),
        ),
        sa.Column("env_var_name", sa.Text(), nullable=True),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "is_sensitive",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_secrets_name"),
        sa.UniqueConstraint("uuid", name="uq_secrets_uuid"),
    )

    # ----------------------------------------------------------------
    # secret_versions
    # ----------------------------------------------------------------
    op.create_table(
        "secret_versions",
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
        sa.Column("secret_id", sa.BigInteger(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("encrypted_value", sa.Text(), nullable=True),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(
            ["secret_id"],
            ["secrets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_secret_versions_uuid"),
        sa.UniqueConstraint("secret_id", "version", name="uq_secret_versions_secret_version"),
    )

    # ----------------------------------------------------------------
    # agent_instruction_files
    # ----------------------------------------------------------------
    op.create_table(
        "agent_instruction_files",
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
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False, server_default=sa.text("'global'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("inject_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_agent_instruction_files_name"),
        sa.UniqueConstraint("uuid", name="uq_agent_instruction_files_uuid"),
    )

    # ----------------------------------------------------------------
    # agent_tools
    # ----------------------------------------------------------------
    op.create_table(
        "agent_tools",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("documentation", sa.Text(), nullable=True),
        sa.Column("tier", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("input_schema", postgresql.JSONB(), nullable=False),
        sa.Column("output_schema", postgresql.JSONB(), nullable=True),
        sa.Column("handler_ref", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
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
        sa.PrimaryKeyConstraint("id"),
    )

    # ----------------------------------------------------------------
    # ALTER agent_registrations — add control plane columns
    # ----------------------------------------------------------------

    # Step 1: add new control plane columns (nullable or with defaults)
    with op.batch_alter_table("agent_registrations") as batch_op:
        # Make endpoint_url nullable (managed agents don't need it)
        batch_op.alter_column("endpoint_url", nullable=True)

        # Status (replaces is_active)
        batch_op.add_column(
            sa.Column("status", sa.Text(), nullable=True)
        )

        # Identity & type
        batch_op.add_column(
            sa.Column(
                "execution_mode",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'external'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "agent_type",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'standalone'"),
            )
        )
        batch_op.add_column(sa.Column("role", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("capabilities", postgresql.JSONB(), nullable=True))

        # Adapter
        batch_op.add_column(
            sa.Column(
                "adapter_type",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'webhook'"),
            )
        )
        batch_op.add_column(sa.Column("adapter_config", postgresql.JSONB(), nullable=True))

        # Managed agent config
        batch_op.add_column(sa.Column("llm_integration_id", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("system_prompt", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("methodology", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "tool_ids",
                postgresql.ARRAY(sa.Text()),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("max_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "enable_thinking",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch_op.add_column(sa.Column("instruction_files", postgresql.JSONB(), nullable=True))

        # Orchestrator config
        batch_op.add_column(
            sa.Column(
                "sub_agent_ids",
                postgresql.ARRAY(sa.Text()),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("max_sub_agent_calls", sa.Integer(), nullable=True))

        # Budget
        batch_op.add_column(
            sa.Column(
                "budget_monthly_cents",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "spent_monthly_cents",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column("budget_period_start", sa.DateTime(timezone=True), nullable=True)
        )

        # Runtime
        batch_op.add_column(
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "max_concurrent_alerts",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "max_cost_per_alert_cents",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "max_investigation_minutes",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "stall_threshold",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "memory_promotion_requires_approval",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )

    # Step 2: migrate is_active → status
    op.execute("""
        UPDATE agent_registrations
        SET status = CASE WHEN is_active THEN 'active' ELSE 'paused' END
    """)

    # Step 3: make status NOT NULL now that it's populated
    op.execute(
        "ALTER TABLE agent_registrations ALTER COLUMN status SET NOT NULL"
    )

    # Step 4: add FK from agent_registrations.llm_integration_id → llm_integrations.id
    op.execute("""
        ALTER TABLE agent_registrations
        ADD CONSTRAINT fk_agent_reg_llm_integration
        FOREIGN KEY (llm_integration_id) REFERENCES llm_integrations(id) ON DELETE SET NULL
    """)

    # Step 5: drop is_active (data migrated to status)
    with op.batch_alter_table("agent_registrations") as batch_op:
        batch_op.drop_column("is_active")

    # Indexes on agent_registrations
    op.create_index("idx_agent_reg_status", "agent_registrations", ["status"])
    op.create_index("idx_agent_reg_type", "agent_registrations", ["agent_type"])
    op.create_index("idx_agent_reg_llm", "agent_registrations", ["llm_integration_id"])

    # ----------------------------------------------------------------
    # agent_api_keys
    # ----------------------------------------------------------------
    op.create_table(
        "agent_api_keys",
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
        sa.Column("agent_registration_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_registration_id"],
            ["agent_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_agent_api_keys_uuid"),
    )
    op.create_index("idx_agent_api_keys_prefix", "agent_api_keys", ["key_prefix"])
    op.create_index(
        "idx_agent_api_keys_agent", "agent_api_keys", ["agent_registration_id"]
    )

    # ----------------------------------------------------------------
    # heartbeat_runs
    # ----------------------------------------------------------------
    op.create_table(
        "heartbeat_runs",
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
        sa.Column("agent_registration_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'scheduler'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "alerts_processed", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "actions_proposed", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("context_snapshot", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_registration_id"],
            ["agent_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_heartbeat_runs_uuid"),
    )
    op.create_index(
        "idx_heartbeat_runs_agent",
        "heartbeat_runs",
        ["agent_registration_id", "started_at"],
    )

    # ----------------------------------------------------------------
    # alert_assignments
    # ----------------------------------------------------------------
    op.create_table(
        "alert_assignments",
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
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'assigned'")),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("resolution_type", sa.Text(), nullable=True),
        sa.Column("investigation_state", postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["agent_registration_id"],
            ["agent_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_alert_assignments_uuid"),
        sa.UniqueConstraint(
            "alert_id",
            "agent_registration_id",
            name="uq_alert_assignments_alert_agent",
        ),
    )
    op.create_index(
        "idx_alert_assignments_status", "alert_assignments", ["status"]
    )
    op.create_index(
        "idx_alert_assignments_alert", "alert_assignments", ["alert_id", "status"]
    )
    op.create_index(
        "idx_alert_assignments_agent",
        "alert_assignments",
        ["agent_registration_id", "status"],
    )

    # ----------------------------------------------------------------
    # cost_events
    # ----------------------------------------------------------------
    op.create_table(
        "cost_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_registration_id", sa.BigInteger(), nullable=False),
        sa.Column("llm_integration_id", sa.BigInteger(), nullable=True),
        sa.Column("alert_id", sa.BigInteger(), nullable=True),
        sa.Column("heartbeat_run_id", sa.BigInteger(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("cost_cents", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "billing_type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'api'"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
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
        sa.ForeignKeyConstraint(
            ["agent_registration_id"],
            ["agent_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["llm_integration_id"],
            ["llm_integrations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["heartbeat_run_id"],
            ["heartbeat_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_cost_events_agent", "cost_events", ["agent_registration_id", "occurred_at"]
    )
    op.create_index(
        "idx_cost_events_llm", "cost_events", ["llm_integration_id", "occurred_at"]
    )
    op.create_index("idx_cost_events_occurred", "cost_events", ["occurred_at"])

    # ----------------------------------------------------------------
    # agent_task_sessions
    # ----------------------------------------------------------------
    op.create_table(
        "agent_task_sessions",
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
        sa.Column("agent_registration_id", sa.BigInteger(), nullable=False),
        sa.Column("alert_id", sa.BigInteger(), nullable=True),
        sa.Column("task_key", sa.Text(), nullable=False),
        sa.Column(
            "session_params",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("session_display_id", sa.Text(), nullable=True),
        sa.Column(
            "total_input_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_output_tokens",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_cost_cents",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "heartbeat_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_run_id", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("compacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_registration_id"],
            ["agent_registrations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["last_run_id"],
            ["heartbeat_runs.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_agent_task_sessions_uuid"),
        sa.UniqueConstraint(
            "agent_registration_id",
            "task_key",
            name="uq_agent_task_sessions_agent_task",
        ),
    )
    op.create_index(
        "idx_agent_task_sessions_agent",
        "agent_task_sessions",
        ["agent_registration_id"],
    )


def downgrade() -> None:
    # Remove in reverse order of creation

    op.drop_table("agent_task_sessions")
    op.drop_table("cost_events")
    op.drop_table("alert_assignments")
    op.drop_table("heartbeat_runs")
    op.drop_table("agent_api_keys")

    # Restore agent_registrations (add is_active, drop new columns)
    op.execute(
        "ALTER TABLE agent_registrations ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
    )
    op.execute(
        "UPDATE agent_registrations SET is_active = (status = 'active')"
    )
    op.execute(
        "ALTER TABLE agent_registrations "
        "DROP CONSTRAINT IF EXISTS fk_agent_reg_llm_integration"
    )

    with op.batch_alter_table("agent_registrations") as batch_op:
        batch_op.drop_column("status")
        batch_op.drop_column("execution_mode")
        batch_op.drop_column("agent_type")
        batch_op.drop_column("role")
        batch_op.drop_column("capabilities")
        batch_op.drop_column("adapter_type")
        batch_op.drop_column("adapter_config")
        batch_op.drop_column("llm_integration_id")
        batch_op.drop_column("system_prompt")
        batch_op.drop_column("methodology")
        batch_op.drop_column("tool_ids")
        batch_op.drop_column("max_tokens")
        batch_op.drop_column("enable_thinking")
        batch_op.drop_column("instruction_files")
        batch_op.drop_column("sub_agent_ids")
        batch_op.drop_column("max_sub_agent_calls")
        batch_op.drop_column("budget_monthly_cents")
        batch_op.drop_column("spent_monthly_cents")
        batch_op.drop_column("budget_period_start")
        batch_op.drop_column("last_heartbeat_at")
        batch_op.drop_column("max_concurrent_alerts")
        batch_op.drop_column("max_cost_per_alert_cents")
        batch_op.drop_column("max_investigation_minutes")
        batch_op.drop_column("stall_threshold")
        batch_op.drop_column("memory_promotion_requires_approval")
        batch_op.alter_column("endpoint_url", nullable=False)

    op.drop_table("agent_tools")
    op.drop_table("agent_instruction_files")
    op.drop_table("secret_versions")
    op.drop_table("secrets")
    op.drop_table("llm_integrations")
