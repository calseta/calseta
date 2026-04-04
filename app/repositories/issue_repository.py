"""IssueRepository — CRUD and atomic operations for agent_issues and agent_issue_comments."""

from __future__ import annotations

import uuid as uuid_module
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text

from app.db.models.agent_issue import AgentIssue
from app.db.models.agent_issue_comment import AgentIssueComment
from app.repositories.base import BaseRepository


class IssueRepository(BaseRepository[AgentIssue]):
    model = AgentIssue

    async def next_identifier(self) -> str:
        """Generate the next CAL-NNN identifier.

        Uses COUNT(*)+1 — not perfectly race-safe but acceptable for v1 issue volumes.
        """
        result = await self._db.execute(text("SELECT COUNT(*) FROM agent_issues"))
        count: int = result.scalar_one()
        return f"CAL-{count + 1:03d}"

    async def create(
        self,
        data: dict,
        identifier: str,
    ) -> AgentIssue:
        """Create a new issue row."""
        issue = AgentIssue(
            uuid=uuid_module.uuid4(),
            identifier=identifier,
            title=data["title"],
            description=data.get("description"),
            status=data.get("status", "backlog"),
            priority=data.get("priority", "medium"),
            category=data.get("category", "investigation"),
            assignee_agent_id=data.get("assignee_agent_id"),
            assignee_operator=data.get("assignee_operator"),
            created_by_agent_id=data.get("created_by_agent_id"),
            created_by_operator=data.get("created_by_operator"),
            alert_id=data.get("alert_id"),
            parent_id=data.get("parent_id"),
            due_at=data.get("due_at"),
            metadata_=data.get("metadata"),
        )
        self._db.add(issue)
        await self._db.flush()
        await self._db.refresh(issue)
        return issue

    async def patch(self, issue: AgentIssue, **kwargs: object) -> AgentIssue:
        """Apply partial updates to an issue."""
        _UPDATABLE = frozenset({
            "title", "description", "status", "priority", "category",
            "assignee_agent_id", "assignee_operator", "due_at", "resolution",
            "metadata_", "started_at", "completed_at", "cancelled_at",
            "checkout_run_id", "execution_locked_at",
        })
        for key, value in kwargs.items():
            if key not in _UPDATABLE:
                raise ValueError(f"Field '{key}' is not updatable via patch")
            setattr(issue, key, value)
        await self._db.flush()
        await self._db.refresh(issue)
        return issue

    async def atomic_checkout(
        self, issue_id: int, heartbeat_run_id: int
    ) -> AgentIssue | None:
        """Atomically set checkout_run_id + status=in_progress.

        Uses UPDATE ... WHERE checkout_run_id IS NULL RETURNING id.
        Returns the updated issue on success, None if already checked out.
        """
        now = datetime.now(UTC)
        stmt = text("""
            UPDATE agent_issues
            SET checkout_run_id = :run_id,
                execution_locked_at = :now,
                status = 'in_progress',
                updated_at = :now
            WHERE id = :issue_id
              AND checkout_run_id IS NULL
              AND status NOT IN ('done', 'cancelled')
            RETURNING id
        """)
        result = await self._db.execute(
            stmt,
            {
                "run_id": heartbeat_run_id,
                "now": now,
                "issue_id": issue_id,
            },
        )
        row = result.fetchone()
        if row is None:
            return None

        issue = await self.get_by_id(issue_id)
        return issue

    async def release_checkout(self, issue: AgentIssue) -> AgentIssue:
        """Clear checkout_run_id and execution_locked_at."""
        issue.checkout_run_id = None
        issue.execution_locked_at = None
        await self._db.flush()
        await self._db.refresh(issue)
        return issue

    async def list_issues(
        self,
        status: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        assignee_agent_id: int | None = None,
        alert_id: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentIssue], int]:
        """Return (issues, total) with optional filters."""
        filters = []
        if status is not None:
            filters.append(AgentIssue.status == status)
        if priority is not None:
            filters.append(AgentIssue.priority == priority)
        if category is not None:
            filters.append(AgentIssue.category == category)
        if assignee_agent_id is not None:
            filters.append(AgentIssue.assignee_agent_id == assignee_agent_id)
        if alert_id is not None:
            filters.append(AgentIssue.alert_id == alert_id)
        return await self.paginate(
            *filters,
            order_by=AgentIssue.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    async def list_for_agent(
        self,
        agent_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentIssue], int]:
        """Return (issues, total) assigned to the given agent."""
        return await self.paginate(
            AgentIssue.assignee_agent_id == agent_id,
            order_by=AgentIssue.created_at.desc(),
            page=page,
            page_size=page_size,
        )

    # --- Comment operations ---

    async def create_comment(
        self,
        issue_id: int,
        body: str,
        author_agent_id: int | None = None,
        author_operator: str | None = None,
    ) -> AgentIssueComment:
        """Create a comment on an issue."""
        comment = AgentIssueComment(
            uuid=uuid_module.uuid4(),
            issue_id=issue_id,
            body=body,
            author_agent_id=author_agent_id,
            author_operator=author_operator,
        )
        self._db.add(comment)
        await self._db.flush()
        await self._db.refresh(comment)
        return comment

    async def list_comments(
        self,
        issue_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentIssueComment], int]:
        """Return (comments, total) for the given issue."""
        from sqlalchemy import func

        count_stmt = (
            select(func.count())
            .select_from(AgentIssueComment)
            .where(AgentIssueComment.issue_id == issue_id)
        )
        total_result = await self._db.execute(count_stmt)
        total: int = total_result.scalar_one()

        stmt = (
            select(AgentIssueComment)
            .where(AgentIssueComment.issue_id == issue_id)
            .order_by(AgentIssueComment.created_at.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_comment_by_uuid(self, comment_uuid: UUID) -> AgentIssueComment | None:
        """Fetch a single comment by UUID."""
        result = await self._db.execute(
            select(AgentIssueComment).where(AgentIssueComment.uuid == comment_uuid)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]
