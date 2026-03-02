"""add alert deduplication columns and fingerprint index

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-01

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alerts",
        sa.Column(
            "duplicate_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "alerts",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_alerts_fingerprint_created_at",
        "alerts",
        ["fingerprint", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_fingerprint_created_at", table_name="alerts")
    op.drop_column("alerts", "last_seen_at")
    op.drop_column("alerts", "duplicate_count")
