"""Add health monitoring tables: health_sources, health_metrics_config, health_metrics.

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-15
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -- health_sources --
    op.create_table(
        "health_sources",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column(
            "uuid",
            sa.UUID(),
            nullable=False,
            unique=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "config",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("auth_config_encrypted", sa.Text(), nullable=True),
        sa.Column(
            "polling_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
        ),
        sa.Column(
            "last_poll_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("last_poll_error", sa.Text(), nullable=True),
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
    )

    # -- health_metrics_config --
    op.create_table(
        "health_metrics_config",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column(
            "uuid",
            sa.UUID(),
            nullable=False,
            unique=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("health_source_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("namespace", sa.Text(), nullable=False),
        sa.Column("metric_name", sa.Text(), nullable=False),
        sa.Column(
            "dimensions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "statistic",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'Average'"),
        ),
        sa.Column(
            "unit",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'None'"),
        ),
        sa.Column(
            "category",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'custom'"),
        ),
        sa.Column(
            "card_size",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'wide'"),
        ),
        sa.Column("warning_threshold", sa.Float(), nullable=True),
        sa.Column("critical_threshold", sa.Float(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
        sa.ForeignKeyConstraint(
            ["health_source_id"],
            ["health_sources.id"],
            name="fk_health_metrics_config_source_id",
            ondelete="CASCADE",
        ),
    )

    # -- health_metrics (time-series) --
    op.create_table(
        "health_metrics",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("metric_config_id", sa.BigInteger(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_datapoints", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["metric_config_id"],
            ["health_metrics_config.id"],
            name="fk_health_metrics_config_id",
            ondelete="CASCADE",
        ),
    )

    # Index on (metric_config_id, timestamp) for time-range queries
    op.create_index(
        "ix_health_metrics_config_id_timestamp",
        "health_metrics",
        ["metric_config_id", "timestamp"],
    )


def downgrade() -> None:
    op.drop_table("health_metrics")
    op.drop_table("health_metrics_config")
    op.drop_table("health_sources")
