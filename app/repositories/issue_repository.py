"""IssueRepository — CRUD and atomic operations for agent_issues, labels, and comments."""

from __future__ import annotations

import uuid as uuid_module
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, text

from app.db.models.agent_issue import AgentIssue
from app.db.models.agent_issue_comment import AgentIssueComment
from app.db.models.issue_label import IssueLabel
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
        label_id: int | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AgentIssue], int]:
        """Return (issues, total) with optional filters."""
        from sqlalchemy import or_

        from app.db.models.agent_issue import issue_label_assignments

        base_stmt = select(AgentIssue)
        count_stmt = select(func.count()).select_from(AgentIssue)

        if status is not None:
            base_stmt = base_stmt.where(AgentIssue.status == status)
            count_stmt = count_stmt.where(AgentIssue.status == status)
        if priority is not None:
            base_stmt = base_stmt.where(AgentIssue.priority == priority)
            count_stmt = count_stmt.where(AgentIssue.priority == priority)
        if category is not None:
            base_stmt = base_stmt.where(AgentIssue.category == category)
            count_stmt = count_stmt.where(AgentIssue.category == category)
        if assignee_agent_id is not None:
            base_stmt = base_stmt.where(AgentIssue.assignee_agent_id == assignee_agent_id)
            count_stmt = count_stmt.where(AgentIssue.assignee_agent_id == assignee_agent_id)
        if alert_id is not None:
            base_stmt = base_stmt.where(AgentIssue.alert_id == alert_id)
            count_stmt = count_stmt.where(AgentIssue.alert_id == alert_id)
        if q is not None:
            search = f"%{q}%"
            ilike_filter = or_(
                AgentIssue.title.ilike(search),
                AgentIssue.description.ilike(search),
            )
            base_stmt = base_stmt.where(ilike_filter)
            count_stmt = count_stmt.where(ilike_filter)
        if label_id is not None:
            label_filter = AgentIssue.id.in_(
                select(issue_label_assignments.c.issue_id).where(
                    issue_label_assignments.c.label_id == label_id
                )
            )
            base_stmt = base_stmt.where(label_filter)
            count_stmt = count_stmt.where(label_filter)

        total_result = await self._db.execute(count_stmt)
        total: int = total_result.scalar_one()

        offset = (page - 1) * page_size
        base_stmt = base_stmt.order_by(AgentIssue.created_at.desc()).offset(offset).limit(page_size)
        result = await self._db.execute(base_stmt)
        return list(result.scalars().all()), total

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

    # --- Label operations ---

    async def list_labels(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueLabel], int]:
        """Return (labels, total) ordered by name."""
        count_stmt = select(func.count()).select_from(IssueLabel)
        total_result = await self._db.execute(count_stmt)
        total: int = total_result.scalar_one()

        stmt = (
            select(IssueLabel)
            .order_by(IssueLabel.name.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_label_by_uuid(self, label_uuid: UUID) -> IssueLabel | None:
        """Fetch a single label by UUID."""
        result = await self._db.execute(
            select(IssueLabel).where(IssueLabel.uuid == label_uuid)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def get_labels_by_uuids(self, label_uuids: list[UUID]) -> list[IssueLabel]:
        """Fetch multiple labels by UUID list."""
        if not label_uuids:
            return []
        result = await self._db.execute(
            select(IssueLabel).where(IssueLabel.uuid.in_(label_uuids))
        )
        return list(result.scalars().all())

    async def create_label(self, name: str, color: str) -> IssueLabel:
        """Create a new label row."""
        label = IssueLabel(
            uuid=uuid_module.uuid4(),
            name=name,
            color=color,
        )
        self._db.add(label)
        await self._db.flush()
        await self._db.refresh(label)
        return label

    async def delete_label(self, label: IssueLabel) -> None:
        """Delete a label row and flush."""
        await self._db.delete(label)
        await self._db.flush()

    async def sync_issue_labels(self, issue: AgentIssue, labels: list[IssueLabel]) -> None:
        """Replace the full set of labels assigned to an issue."""
        issue.labels = labels
        await self._db.flush()
        await self._db.refresh(issue, ["labels"])
