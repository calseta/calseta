"""Extend workflow_approval_requests to support agent actions.

Makes workflow_id and trigger_agent_key_prefix nullable so that
WorkflowApprovalRequest rows can be created for agent actions
(which have no associated workflow).

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Make workflow_id nullable — agent actions don't have an associated workflow
    op.alter_column(
        "workflow_approval_requests",
        "workflow_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    # Make trigger_agent_key_prefix nullable — may be absent for system-initiated actions
    op.alter_column(
        "workflow_approval_requests",
        "trigger_agent_key_prefix",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    # Note: downgrade will fail if any rows have NULL workflow_id or
    # trigger_agent_key_prefix. Clean up those rows first if needed.
    op.alter_column(
        "workflow_approval_requests",
        "trigger_agent_key_prefix",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "workflow_approval_requests",
        "workflow_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
