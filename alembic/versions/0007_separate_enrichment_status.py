"""separate enrichment_status from alert status

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-04

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add enrichment_status column with default
    op.add_column(
        "alerts",
        sa.Column(
            "enrichment_status",
            sa.Text(),
            nullable=False,
            server_default="Pending",
        ),
    )

    # 2. Backfill existing rows based on current status values
    op.execute("""
        UPDATE alerts
        SET enrichment_status = CASE
            WHEN status = 'pending_enrichment' THEN 'Pending'
            WHEN status = 'enriched' THEN 'Enriched'
            WHEN is_enriched = true THEN 'Enriched'
            ELSE 'Pending'
        END
    """)

    # 3. Migrate status values: pending_enrichment and enriched → Open
    op.execute("""
        UPDATE alerts
        SET status = 'Open'
        WHERE status IN ('pending_enrichment', 'enriched')
    """)

    # 4. Change server_default for status column
    op.alter_column(
        "alerts",
        "status",
        server_default="Open",
    )


def downgrade() -> None:
    # Reverse: map back to old status values
    op.execute("""
        UPDATE alerts
        SET status = CASE
            WHEN enrichment_status = 'Pending' AND status = 'Open' THEN 'pending_enrichment'
            WHEN enrichment_status = 'Enriched' AND status = 'Open' THEN 'enriched'
            ELSE status
        END
    """)

    op.alter_column(
        "alerts",
        "status",
        server_default="pending_enrichment",
    )

    op.drop_column("alerts", "enrichment_status")
