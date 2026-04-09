"""Add heartbeat_interval_seconds to agent_registrations.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_registrations",
        sa.Column("heartbeat_interval_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_registrations", "heartbeat_interval_seconds")
