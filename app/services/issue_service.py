"""IssueService — business logic for the agent issue/task system.

Flow:
  1. create_issue: validate enums, resolve UUIDs to int IDs, generate identifier, persist.
  2. get_issue / list_issues: read-only queries via repository.
  3. patch_issue: validate enums, apply status side effects, save.
  4. checkout_issue / release_checkout: atomic checkout lock for agent work-locking.
  5. add_comment / list_comments: comment thread management.
  6. list_agent_issues: issues assigned to a specific agent.

Status side effects (enforced here, not in repository):
  - in_progress → set started_at = now() if not already set
  - done        → set completed_at = now(), clear checkout_run_id
  - cancelled   → set cancelled_at = now(), clear checkout_run_id
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.errors import CalsetaException
from app.db.models.agent_issue import AgentIssue
from app.db.models.agent_issue_comment import AgentIssueComment
from app.repositories.agent_repository import AgentRepository
from app.repositories.alert_repository import AlertRepository
from app.repositories.heartbeat_run_repository import HeartbeatRunRepository
from app.repositories.issue_repository import IssueRepository
from app.schemas.issues import (
    IssueCategory,
    IssueCategoryDefCreate,
    IssueCategoryDefPatch,
    IssueCategoryDefResponse,
    IssueCommentCreate,
    IssueCommentResponse,
    IssueCreate,
    IssueLabelCreate,
    IssueLabelResponse,
    IssuePatch,
    IssuePriority,
    IssueResponse,
    IssueStatus,
)

logger = structlog.get_logger(__name__)


def _build_issue_response(issue: AgentIssue) -> IssueResponse:
    """Map an AgentIssue ORM object to IssueResponse, resolving FK UUIDs."""
    labels = [
        IssueLabelResponse.model_validate(lbl)
        for lbl in (issue.labels if issue.labels is not None else [])
    ]
    return IssueResponse(
        uuid=issue.uuid,
        identifier=issue.identifier,
        title=issue.title,
        description=issue.description,
        status=issue.status,
        priority=issue.priority,
        category=issue.category,
        assignee_operator=issue.assignee_operator,
        created_by_operator=issue.created_by_operator,
        due_at=issue.due_at,
        started_at=issue.started_at,
        completed_at=issue.completed_at,
        cancelled_at=issue.cancelled_at,
        resolution=issue.resolution,
        created_at=issue.created_at,
        updated_at=issue.updated_at,
        assignee_agent_uuid=issue.assignee_agent.uuid if issue.assignee_agent else None,
        created_by_agent_uuid=issue.created_by_agent.uuid if issue.created_by_agent else None,
        alert_uuid=issue.alert.uuid if issue.alert else None,
        parent_uuid=None,  # self-referential — not eagerly loaded; callers fetch separately
        routine_uuid=None,
        labels=labels,
    )


def _build_comment_response(comment: AgentIssueComment) -> IssueCommentResponse:
    """Map an AgentIssueComment ORM object to IssueCommentResponse."""
    return IssueCommentResponse(
        uuid=comment.uuid,
        body=comment.body,
        author_operator=comment.author_operator,
        author_agent_uuid=comment.author_agent.uuid if comment.author_agent else None,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
    )


class IssueService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = IssueRepository(db)

    async def create_issue(
        self,
        data: IssueCreate,
        created_by_operator: str | None = None,
        created_by_agent_uuid: UUID | None = None,
    ) -> IssueResponse:
        """Validate, resolve foreign keys, generate identifier, and create an issue."""
        # Validate enums
        if data.status not in IssueStatus.ALL:
            raise CalsetaException(
                status_code=422,
                code="invalid_status",
                message=f"Invalid status '{data.status}'. Must be one of: {IssueStatus.ALL}",
            )
        if data.priority not in IssuePriority.ALL:
            raise CalsetaException(
                status_code=422,
                code="invalid_priority",
                message=f"Invalid priority '{data.priority}'. Must be one of: {IssuePriority.ALL}",
            )
        # category is a free-text field — validated against user-defined issue_category_defs

        agent_repo = AgentRepository(self._db)

        # Resolve assignee agent UUID to int ID
        assignee_agent_id: int | None = None
        if data.assignee_agent_uuid is not None:
            assignee_agent = await agent_repo.get_by_uuid(data.assignee_agent_uuid)
            if assignee_agent is None:
                raise CalsetaException(
                    status_code=404,
                    code="agent_not_found",
                    message=f"Agent '{data.assignee_agent_uuid}' not found",
                )
            assignee_agent_id = assignee_agent.id

        # Resolve creator agent UUID to int ID
        created_by_agent_id: int | None = None
        if created_by_agent_uuid is not None:
            creator_agent = await agent_repo.get_by_uuid(created_by_agent_uuid)
            if creator_agent is not None:
                created_by_agent_id = creator_agent.id

        # Resolve alert UUID to int ID
        alert_id: int | None = None
        if data.alert_uuid is not None:
            alert_repo = AlertRepository(self._db)
            alert = await alert_repo.get_by_uuid(data.alert_uuid)
            if alert is None:
                raise CalsetaException(
                    status_code=404,
                    code="alert_not_found",
                    message=f"Alert '{data.alert_uuid}' not found",
                )
            alert_id = alert.id

        # Resolve parent UUID to int ID
        parent_id: int | None = None
        if data.parent_uuid is not None:
            parent = await self._repo.get_by_uuid(data.parent_uuid)
            if parent is None:
                raise CalsetaException(
                    status_code=404,
                    code="issue_not_found",
                    message=f"Parent issue '{data.parent_uuid}' not found",
                )
            parent_id = parent.id

        identifier = await self._repo.next_identifier()

        create_data: dict[str, Any] = {
            "title": data.title,
            "description": data.description,
            "status": data.status,
            "priority": data.priority,
            "category": data.category,
            "assignee_agent_id": assignee_agent_id,
            "assignee_operator": data.assignee_operator,
            "created_by_agent_id": created_by_agent_id,
            "created_by_operator": created_by_operator,
            "alert_id": alert_id,
            "parent_id": parent_id,
            "due_at": data.due_at,
            "metadata": data.metadata,
        }

        issue = await self._repo.create(create_data, identifier)
        await self._db.refresh(issue, ["assignee_agent", "created_by_agent", "alert"])

        # Resolve and assign labels if provided
        if data.label_uuids is not None:
            labels = await self._repo.get_labels_by_uuids(data.label_uuids)
            await self._repo.sync_issue_labels(issue, labels)

        logger.info("issue_created", issue_uuid=str(issue.uuid), identifier=identifier)
        return _build_issue_response(issue)

    async def get_issue(self, issue_uuid: UUID) -> IssueResponse:
        """Fetch an issue by UUID, raise 404 if missing."""
        issue = await self._repo.get_by_uuid(issue_uuid)
        if issue is None:
            raise CalsetaException(
                status_code=404,
                code="issue_not_found",
                message=f"Issue '{issue_uuid}' not found",
            )
        await self._db.refresh(issue, ["assignee_agent", "created_by_agent", "alert"])
        return _build_issue_response(issue)

    async def list_issues(
        self,
        status: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        assignee_agent_uuid: UUID | None = None,
        alert_uuid: UUID | None = None,
        label_uuid: UUID | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueResponse], int]:
        """List issues with optional filters."""
        assignee_agent_id: int | None = None
        if assignee_agent_uuid is not None:
            agent_repo = AgentRepository(self._db)
            agent = await agent_repo.get_by_uuid(assignee_agent_uuid)
            if agent is None:
                return [], 0
            assignee_agent_id = agent.id

        alert_id: int | None = None
        if alert_uuid is not None:
            alert_repo = AlertRepository(self._db)
            alert = await alert_repo.get_by_uuid(alert_uuid)
            if alert is None:
                return [], 0
            alert_id = alert.id

        label_id: int | None = None
        if label_uuid is not None:
            label = await self._repo.get_label_by_uuid(label_uuid)
            if label is None:
                return [], 0
            label_id = label.id

        issues, total = await self._repo.list_issues(
            status=status,
            priority=priority,
            category=category,
            assignee_agent_id=assignee_agent_id,
            alert_id=alert_id,
            label_id=label_id,
            q=q,
            page=page,
            page_size=page_size,
        )

        # Eagerly refresh relationships for each issue
        responses = []
        for issue in issues:
            await self._db.refresh(issue, ["assignee_agent", "created_by_agent", "alert"])
            responses.append(_build_issue_response(issue))

        return responses, total

    async def patch_issue(self, issue_uuid: UUID, patch_data: IssuePatch) -> IssueResponse:
        """Validate enums, apply status side effects, and save."""
        issue = await self._repo.get_by_uuid(issue_uuid)
        if issue is None:
            raise CalsetaException(
                status_code=404,
                code="issue_not_found",
                message=f"Issue '{issue_uuid}' not found",
            )

        updates: dict[str, Any] = {}

        if patch_data.title is not None:
            updates["title"] = patch_data.title
        if patch_data.description is not None:
            updates["description"] = patch_data.description
        if patch_data.priority is not None:
            if patch_data.priority not in IssuePriority.ALL:
                raise CalsetaException(
                    status_code=422,
                    code="invalid_priority",
                    message=f"Invalid priority '{patch_data.priority}'",
                )
            updates["priority"] = patch_data.priority
        if patch_data.category is not None:
            updates["category"] = patch_data.category
        if patch_data.assignee_operator is not None:
            updates["assignee_operator"] = patch_data.assignee_operator
        if patch_data.due_at is not None:
            updates["due_at"] = patch_data.due_at
        if patch_data.resolution is not None:
            updates["resolution"] = patch_data.resolution
        if patch_data.metadata is not None:
            updates["metadata_"] = patch_data.metadata

        # Resolve assignee agent if provided
        if patch_data.assignee_agent_uuid is not None:
            agent_repo = AgentRepository(self._db)
            agent = await agent_repo.get_by_uuid(patch_data.assignee_agent_uuid)
            if agent is None:
                raise CalsetaException(
                    status_code=404,
                    code="agent_not_found",
                    message=f"Agent '{patch_data.assignee_agent_uuid}' not found",
                )
            updates["assignee_agent_id"] = agent.id

        # Status transition with side effects
        if patch_data.status is not None:
            if patch_data.status not in IssueStatus.ALL:
                raise CalsetaException(
                    status_code=422,
                    code="invalid_status",
                    message=f"Invalid status '{patch_data.status}'",
                )
            updates["status"] = patch_data.status
            now = datetime.now(UTC)

            if patch_data.status == IssueStatus.IN_PROGRESS:
                if issue.started_at is None:
                    updates["started_at"] = now

            elif patch_data.status == IssueStatus.DONE:
                updates["completed_at"] = now
                updates["checkout_run_id"] = None
                updates["execution_locked_at"] = None

            elif patch_data.status == IssueStatus.CANCELLED:
                updates["cancelled_at"] = now
                updates["checkout_run_id"] = None
                updates["execution_locked_at"] = None

        issue = await self._repo.patch(issue, **updates)
        await self._db.refresh(issue, ["assignee_agent", "created_by_agent", "alert"])

        # Replace label set if provided
        if patch_data.label_uuids is not None:
            labels = await self._repo.get_labels_by_uuids(patch_data.label_uuids)
            await self._repo.sync_issue_labels(issue, labels)

        return _build_issue_response(issue)

    async def checkout_issue(
        self, issue_uuid: UUID, heartbeat_run_uuid: UUID
    ) -> IssueResponse:
        """Atomically lock an issue for an agent heartbeat run.

        Returns 409 if the issue is already checked out or in a terminal state.
        """
        issue = await self._repo.get_by_uuid(issue_uuid)
        if issue is None:
            raise CalsetaException(
                status_code=404,
                code="issue_not_found",
                message=f"Issue '{issue_uuid}' not found",
            )

        run_repo = HeartbeatRunRepository(self._db)
        run = await run_repo.get_by_uuid(heartbeat_run_uuid)
        if run is None:
            raise CalsetaException(
                status_code=404,
                code="heartbeat_run_not_found",
                message=f"HeartbeatRun '{heartbeat_run_uuid}' not found",
            )

        if issue.status in IssueStatus.TERMINAL:
            raise CalsetaException(
                status_code=409,
                code="issue_terminal",
                message=(
                    f"Issue '{issue_uuid}' is in terminal status "
                    f"'{issue.status}' and cannot be checked out"
                ),
            )

        checked_out = await self._repo.atomic_checkout(issue.id, run.id)
        if checked_out is None:
            raise CalsetaException(
                status_code=409,
                code="issue_checkout_conflict",
                message=f"Issue '{issue_uuid}' is already checked out by another run",
            )

        await self._db.refresh(checked_out, ["assignee_agent", "created_by_agent", "alert"])
        logger.info(
            "issue_checked_out",
            issue_uuid=str(issue_uuid),
            heartbeat_run_uuid=str(heartbeat_run_uuid),
        )
        return _build_issue_response(checked_out)

    async def release_checkout(self, issue_uuid: UUID) -> IssueResponse:
        """Release the checkout lock on an issue."""
        issue = await self._repo.get_by_uuid(issue_uuid)
        if issue is None:
            raise CalsetaException(
                status_code=404,
                code="issue_not_found",
                message=f"Issue '{issue_uuid}' not found",
            )

        issue = await self._repo.release_checkout(issue)
        await self._db.refresh(issue, ["assignee_agent", "created_by_agent", "alert"])
        logger.info("issue_checkout_released", issue_uuid=str(issue_uuid))
        return _build_issue_response(issue)

    async def add_comment(
        self,
        issue_uuid: UUID,
        data: IssueCommentCreate,
        author_agent_uuid: UUID | None = None,
    ) -> IssueCommentResponse:
        """Add a comment to an issue."""
        issue = await self._repo.get_by_uuid(issue_uuid)
        if issue is None:
            raise CalsetaException(
                status_code=404,
                code="issue_not_found",
                message=f"Issue '{issue_uuid}' not found",
            )

        author_agent_id: int | None = None
        if author_agent_uuid is not None:
            agent_repo = AgentRepository(self._db)
            agent = await agent_repo.get_by_uuid(author_agent_uuid)
            if agent is not None:
                author_agent_id = agent.id

        comment = await self._repo.create_comment(
            issue_id=issue.id,
            body=data.body,
            author_agent_id=author_agent_id,
            author_operator=data.author_operator,
        )
        await self._db.refresh(comment, ["author_agent"])
        return _build_comment_response(comment)

    async def list_comments(
        self,
        issue_uuid: UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueCommentResponse], int]:
        """List comments for an issue."""
        issue = await self._repo.get_by_uuid(issue_uuid)
        if issue is None:
            raise CalsetaException(
                status_code=404,
                code="issue_not_found",
                message=f"Issue '{issue_uuid}' not found",
            )

        comments, total = await self._repo.list_comments(
            issue_id=issue.id,
            page=page,
            page_size=page_size,
        )
        responses = []
        for comment in comments:
            await self._db.refresh(comment, ["author_agent"])
            responses.append(_build_comment_response(comment))
        return responses, total

    async def delete_issue(self, issue_uuid: UUID) -> None:
        """Delete an issue by UUID. Cascade handled by DB."""
        issue = await self._repo.get_by_uuid(issue_uuid)
        if issue is None:
            raise CalsetaException(
                status_code=404,
                code="issue_not_found",
                message=f"Issue '{issue_uuid}' not found",
            )
        await self._repo.delete(issue)
        logger.info("issue_deleted", issue_uuid=str(issue_uuid))

    # --- Label operations ---

    async def list_labels(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueLabelResponse], int]:
        """List all labels."""
        labels, total = await self._repo.list_labels(page=page, page_size=page_size)
        return [IssueLabelResponse.model_validate(lbl) for lbl in labels], total

    async def create_label(self, data: IssueLabelCreate) -> IssueLabelResponse:
        """Create a new label."""
        label = await self._repo.create_label(name=data.name, color=data.color)
        logger.info("label_created", label_uuid=str(label.uuid), name=label.name)
        return IssueLabelResponse.model_validate(label)

    async def delete_label(self, label_uuid: UUID) -> None:
        """Delete a label by UUID."""
        label = await self._repo.get_label_by_uuid(label_uuid)
        if label is None:
            raise CalsetaException(
                status_code=404,
                code="label_not_found",
                message=f"Label '{label_uuid}' not found",
            )
        await self._repo.delete_label(label)
        logger.info("label_deleted", label_uuid=str(label_uuid))

    # --- Category operations ---

    async def list_categories(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueCategoryDefResponse], int]:
        """List all issue categories."""
        categories, total = await self._repo.list_categories(page=page, page_size=page_size)
        return [IssueCategoryDefResponse.model_validate(cat) for cat in categories], total

    async def create_category(self, data: IssueCategoryDefCreate) -> IssueCategoryDefResponse:
        """Create a new category."""
        category = await self._repo.create_category(key=data.key, label=data.label)
        logger.info("category_created", category_uuid=str(category.uuid), key=category.key)
        return IssueCategoryDefResponse.model_validate(category)

    async def delete_category(self, category_uuid: UUID) -> None:
        """Delete a category by UUID. Raises 422 if is_system=True."""
        category = await self._repo.get_category_by_uuid(category_uuid)
        if category is None:
            raise CalsetaException(
                status_code=404,
                code="category_not_found",
                message=f"Category '{category_uuid}' not found",
            )
        if category.is_system:
            raise CalsetaException(
                status_code=422,
                code="SYSTEM_CATEGORY",
                message="System categories cannot be deleted",
            )
        await self._repo.delete_category(category)
        logger.info("category_deleted", category_uuid=str(category_uuid))

    async def patch_category(self, category_uuid: UUID, label: str) -> "IssueCategoryDefResponse":
        """Update a category label by UUID."""
        category = await self._repo.get_category_by_uuid(category_uuid)
        if category is None:
            raise CalsetaException(
                status_code=404,
                code="category_not_found",
                message=f"Category '{category_uuid}' not found",
            )
        category.label = label
        await self._db.flush()
        await self._db.refresh(category)
        logger.info("category_updated", category_uuid=str(category_uuid))
        return IssueCategoryDefResponse.model_validate(category)

    async def list_agent_issues(
        self,
        agent_uuid: UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[IssueResponse], int]:
        """List issues assigned to a specific agent."""
        agent_repo = AgentRepository(self._db)
        agent = await agent_repo.get_by_uuid(agent_uuid)
        if agent is None:
            raise CalsetaException(
                status_code=404,
                code="agent_not_found",
                message=f"Agent '{agent_uuid}' not found",
            )

        issues, total = await self._repo.list_for_agent(
            agent_id=agent.id,
            page=page,
            page_size=page_size,
        )
        responses = []
        for issue in issues:
            await self._db.refresh(issue, ["assignee_agent", "created_by_agent", "alert"])
            responses.append(_build_issue_response(issue))
        return responses, total
