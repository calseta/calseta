"""Phase 6 — Knowledge Base and Memory data layer.

New tables: knowledge_base_pages, kb_page_revisions, kb_page_links.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----------------------------------------------------------------
    # knowledge_base_pages
    # FKs: agent_registrations (created_by, updated_by)
    # latest_revision_id is NOT a FK to avoid circular dep with kb_page_revisions
    # ----------------------------------------------------------------
    op.create_table(
        "knowledge_base_pages",
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
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("folder", sa.Text(), nullable=False, server_default=sa.text("'/'")),
        sa.Column("format", sa.Text(), nullable=False, server_default=sa.text("'markdown'")),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'published'")),
        sa.Column("inject_scope", postgresql.JSONB(), nullable=True),
        sa.Column(
            "inject_priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "inject_pinned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("sync_source", postgresql.JSONB(), nullable=True),
        sa.Column("sync_last_hash", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_agent_id", sa.BigInteger(), nullable=True),
        sa.Column("created_by_operator", sa.Text(), nullable=True),
        sa.Column("updated_by_agent_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_by_operator", sa.Text(), nullable=True),
        sa.Column("latest_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "latest_revision_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_agent_id"],
            ["agent_registrations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_agent_id"],
            ["agent_registrations.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_kb_pages_uuid"),
        sa.UniqueConstraint("slug", name="uq_kb_pages_slug"),
    )
    op.create_index(
        "ix_kb_pages_search_vector",
        "knowledge_base_pages",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index("ix_kb_pages_folder", "knowledge_base_pages", ["folder"])
    op.create_index("ix_kb_pages_status", "knowledge_base_pages", ["status"])

    # ----------------------------------------------------------------
    # kb_page_revisions
    # FKs: knowledge_base_pages (page_id), agent_registrations (author)
    # ----------------------------------------------------------------
    op.create_table(
        "kb_page_revisions",
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
        sa.Column("page_id", sa.BigInteger(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("author_agent_id", sa.BigInteger(), nullable=True),
        sa.Column("author_operator", sa.Text(), nullable=True),
        sa.Column("sync_source_ref", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["knowledge_base_pages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["author_agent_id"],
            ["agent_registrations.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_kb_page_revisions_uuid"),
        sa.UniqueConstraint(
            "page_id",
            "revision_number",
            name="uq_kb_page_revisions_page_revision",
        ),
    )
    op.create_index("ix_kb_page_revisions_page_id", "kb_page_revisions", ["page_id"])

    # ----------------------------------------------------------------
    # kb_page_links
    # FKs: knowledge_base_pages (page_id)
    # linked_entity_id is a UUID pointer — no FK (cross-entity polymorphic)
    # ----------------------------------------------------------------
    op.create_table(
        "kb_page_links",
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
        sa.Column("page_id", sa.BigInteger(), nullable=False),
        sa.Column("linked_entity_type", sa.Text(), nullable=False),
        sa.Column(
            "linked_entity_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("link_type", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["knowledge_base_pages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("uuid", name="uq_kb_page_links_uuid"),
        sa.UniqueConstraint(
            "page_id",
            "linked_entity_type",
            "linked_entity_id",
            name="uq_kb_page_links_page_entity",
        ),
    )
    op.create_index("ix_kb_page_links_page_id", "kb_page_links", ["page_id"])


def downgrade() -> None:
    op.drop_table("kb_page_links")
    op.drop_table("kb_page_revisions")
    op.drop_index("ix_kb_pages_status", table_name="knowledge_base_pages")
    op.drop_index("ix_kb_pages_folder", table_name="knowledge_base_pages")
    op.drop_index("ix_kb_pages_search_vector", table_name="knowledge_base_pages")
    op.drop_table("knowledge_base_pages")
