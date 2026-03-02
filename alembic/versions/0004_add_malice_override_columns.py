"""add malice override columns to indicators and alerts

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-02

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Indicators: track whether malice was set by enrichment or analyst
    op.add_column(
        "indicators",
        sa.Column(
            "malice_source",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'enrichment'"),
        ),
    )
    op.add_column(
        "indicators",
        sa.Column("malice_overridden_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Alerts: optional malice override (analyst verdict at alert level)
    op.add_column(
        "alerts",
        sa.Column("malice_override", sa.Text(), nullable=True),
    )
    op.add_column(
        "alerts",
        sa.Column("malice_override_source", sa.Text(), nullable=True),
    )
    op.add_column(
        "alerts",
        sa.Column("malice_override_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alerts", "malice_override_at")
    op.drop_column("alerts", "malice_override_source")
    op.drop_column("alerts", "malice_override")
    op.drop_column("indicators", "malice_overridden_at")
    op.drop_column("indicators", "malice_source")
