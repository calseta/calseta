"""Add tags, description, targeting_rules to knowledge_base_pages; drop context_documents.

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add new context-doc fields to knowledge_base_pages
    op.add_column(
        "knowledge_base_pages",
        sa.Column(
            "tags",
            sa.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "knowledge_base_pages",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "knowledge_base_pages",
        sa.Column("targeting_rules", postgresql.JSONB(), nullable=True),
    )

    # Drop context_documents — merged into KB pages
    op.drop_table("context_documents")


def downgrade() -> None:
    op.drop_column("knowledge_base_pages", "targeting_rules")
    op.drop_column("knowledge_base_pages", "description")
    op.drop_column("knowledge_base_pages", "tags")
