"""UserValidation repository — rules and templates for user validation actions."""

from __future__ import annotations

import uuid as uuid_module
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.db.models.user_validation_rule import UserValidationRule
from app.db.models.user_validation_template import UserValidationTemplate
from app.repositories.base import BaseRepository


class UserValidationRepository(BaseRepository[UserValidationRule]):
    """Repository covering both UserValidationRule and UserValidationTemplate.

    The generic type parameter is bound to UserValidationRule. Template operations
    are implemented as explicit methods since templates are a secondary entity
    managed through this same repository.
    """

    model = UserValidationRule

    async def get_active_rules(
        self,
        page: int = 1,
        page_size: int = 100,
    ) -> list[UserValidationRule]:
        """Return active rules ordered by priority descending."""
        rows, _ = await self.paginate(
            UserValidationRule.is_active.is_(True),
            order_by=UserValidationRule.priority.desc(),
            page=page,
            page_size=page_size,
        )
        return rows

    async def get_template_by_name(self, name: str) -> UserValidationTemplate | None:
        """Fetch a template by its unique name."""
        result = await self._db.execute(
            select(UserValidationTemplate).where(UserValidationTemplate.name == name)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def get_template_by_uuid(self, uuid: UUID) -> UserValidationTemplate | None:
        """Fetch a template by UUID."""
        result = await self._db.execute(
            select(UserValidationTemplate).where(UserValidationTemplate.uuid == uuid)
        )
        return result.scalar_one_or_none()  # type: ignore[no-any-return]

    async def list_templates(
        self,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[UserValidationTemplate], int]:
        """Return (templates, total) ordered by name."""
        from sqlalchemy import func

        count_result = await self._db.execute(
            select(func.count()).select_from(UserValidationTemplate)
        )
        total: int = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await self._db.execute(
            select(UserValidationTemplate)
            .order_by(UserValidationTemplate.name.asc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def create_rule(
        self,
        name: str,
        trigger_conditions: dict[str, Any],
        user_field_path: str,
        description: str | None = None,
        is_active: bool = True,
        template_id: int | None = None,
        timeout_hours: int = 4,
        on_confirm: str = "close_alert",
        on_deny: str = "escalate_alert",
        on_timeout: str = "escalate_alert",
        priority: int = 0,
    ) -> UserValidationRule:
        """Create a new user validation rule."""
        rule = UserValidationRule(
            uuid=uuid_module.uuid4(),
            name=name,
            description=description,
            is_active=is_active,
            trigger_conditions=trigger_conditions,
            template_id=template_id,
            user_field_path=user_field_path,
            timeout_hours=timeout_hours,
            on_confirm=on_confirm,
            on_deny=on_deny,
            on_timeout=on_timeout,
            priority=priority,
        )
        self._db.add(rule)
        await self._db.flush()
        await self._db.refresh(rule)
        return rule

    async def create_template(
        self,
        name: str,
        message_body: str,
        response_type: str,
        confirm_label: str | None = "Yes, that was me",
        deny_label: str | None = "No, that wasn't me",
    ) -> UserValidationTemplate:
        """Create a new user validation template."""
        template = UserValidationTemplate(
            uuid=uuid_module.uuid4(),
            name=name,
            message_body=message_body,
            response_type=response_type,
            confirm_label=confirm_label,
            deny_label=deny_label,
        )
        self._db.add(template)
        await self._db.flush()
        await self._db.refresh(template)
        return template
