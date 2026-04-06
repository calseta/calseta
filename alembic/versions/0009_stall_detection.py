"""Add stall_detected to alert_assignments.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alert_assignments",
        sa.Column(
            "stall_detected",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("alert_assignments", "stall_detected")
