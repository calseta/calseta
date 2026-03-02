"""add is_system column to alerts, detection_rules, context_documents, api_keys

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-02

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("alerts", "detection_rules", "context_documents", "api_keys"):
        op.add_column(
            table,
            sa.Column(
                "is_system",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    for table in ("api_keys", "context_documents", "detection_rules", "alerts"):
        op.drop_column(table, "is_system")
