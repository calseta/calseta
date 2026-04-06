"""Drop campaigns and campaign_items tables.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop campaign_items first (FK → campaigns)
    op.drop_index("idx_campaign_items_type", table_name="campaign_items")
    op.drop_index("idx_campaign_items_campaign", table_name="campaign_items")
    op.drop_table("campaign_items")

    op.drop_index("idx_campaigns_owner_agent", table_name="campaigns")
    op.drop_index("idx_campaigns_status", table_name="campaigns")
    op.drop_table("campaigns")


def downgrade() -> None:
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
