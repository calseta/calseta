"""Add auth field pair constraint on agent_registrations.

Ensures auth_header_name and auth_header_value_encrypted are either
both NULL or both NOT NULL — prevents orphaned auth state.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-11

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE agent_registrations
        ADD CONSTRAINT ck_agent_auth_header_pair
        CHECK (
            (auth_header_name IS NULL AND auth_header_value_encrypted IS NULL)
            OR (auth_header_name IS NOT NULL AND auth_header_value_encrypted IS NOT NULL)
        )
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE agent_registrations DROP CONSTRAINT IF EXISTS ck_agent_auth_header_pair"
    )
