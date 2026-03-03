"""add enrichment_providers table for runtime-configurable enrichment

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-02

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "enrichment_providers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "uuid",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("provider_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_builtin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "supported_indicator_types",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("http_config", postgresql.JSONB(), nullable=False),
        sa.Column(
            "auth_type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'no_auth'"),
        ),
        sa.Column("auth_config", postgresql.JSONB(), nullable=True),
        sa.Column("env_var_mapping", postgresql.JSONB(), nullable=True),
        sa.Column(
            "default_cache_ttl_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("3600"),
        ),
        sa.Column("cache_ttl_by_type", postgresql.JSONB(), nullable=True),
        sa.Column("malice_rules", postgresql.JSONB(), nullable=True),
        sa.Column("mock_responses", postgresql.JSONB(), nullable=True),
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
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("provider_name", name="uq_enrichment_provider_name"),
    )
    op.create_index(
        "ix_enrichment_providers_is_active",
        "enrichment_providers",
        ["is_active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_enrichment_providers_is_active",
        table_name="enrichment_providers",
    )
    op.drop_table("enrichment_providers")
