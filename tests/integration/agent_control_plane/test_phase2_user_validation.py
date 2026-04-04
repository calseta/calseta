"""
Integration tests for Phase 2 agent control plane — UserValidationTemplate and UserValidationRule.

Covers:
  - UserValidationTemplate DB model (direct row creation and queries)
  - UserValidationRule DB model (direct row creation and queries)
  - UserValidationRepository.get_active_rules() — priority ordering + is_active filter
  - UserValidationRepository.get_template_by_name()
  - UserValidationRepository.list_templates() — pagination
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_validation_rule import UserValidationRule
from app.db.models.user_validation_template import UserValidationTemplate
from app.repositories.user_validation_repository import UserValidationRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_template(
    repo: UserValidationRepository,
    *,
    name: str = "default-template",
    message_body: str = "Did you perform this action?",
    response_type: str = "confirm_deny",
) -> UserValidationTemplate:
    return await repo.create_template(
        name=name,
        message_body=message_body,
        response_type=response_type,
    )


async def _create_rule(
    repo: UserValidationRepository,
    *,
    name: str = "test-rule",
    priority: int = 0,
    is_active: bool = True,
    template_id: int | None = None,
) -> UserValidationRule:
    return await repo.create_rule(
        name=name,
        trigger_conditions={"severity": ["High", "Critical"]},
        user_field_path="raw_payload.actor.email",
        priority=priority,
        is_active=is_active,
        template_id=template_id,
    )


# ---------------------------------------------------------------------------
# TestUserValidationModels
# ---------------------------------------------------------------------------


class TestUserValidationModels:
    async def test_create_user_validation_template(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Create a UserValidationTemplate row — verify name, response_type, and UUID present."""
        repo = UserValidationRepository(db_session)
        template = await _create_template(
            repo,
            name="mfa-challenge",
            message_body="Was this login from you?",
            response_type="confirm_deny",
        )

        assert template.id is not None
        assert template.uuid is not None
        assert template.name == "mfa-challenge"
        assert template.response_type == "confirm_deny"
        assert template.message_body == "Was this login from you?"
        assert template.confirm_label is not None
        assert template.deny_label is not None

    async def test_create_user_validation_rule(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Create a UserValidationRule — verify JSONB trigger_conditions, default timeout_hours=4."""
        repo = UserValidationRepository(db_session)
        template = await _create_template(repo, name="rule-template")

        rule = await _create_rule(
            repo,
            name="high-severity-rule",
            priority=5,
            template_id=template.id,
        )

        assert rule.id is not None
        assert rule.uuid is not None
        assert rule.name == "high-severity-rule"
        assert rule.timeout_hours == 4  # default
        assert rule.is_active is True
        assert rule.priority == 5
        assert rule.trigger_conditions == {"severity": ["High", "Critical"]}
        assert rule.template_id == template.id

    async def test_active_rules_query_returns_sorted_by_priority(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_active_rules() returns active rules sorted by priority descending."""
        repo = UserValidationRepository(db_session)

        await _create_rule(repo, name="low-priority", priority=0)
        await _create_rule(repo, name="high-priority", priority=10)
        await _create_rule(repo, name="mid-priority", priority=5)

        rules = await repo.get_active_rules()

        # Must be at least the 3 we just created
        assert len(rules) >= 3

        # Extract the 3 we care about (by name), in the order they appear
        names_of_interest = {"low-priority", "high-priority", "mid-priority"}
        relevant = [r for r in rules if r.name in names_of_interest]
        assert len(relevant) == 3, f"Missing some rules from result: {[r.name for r in rules]}"

        priorities = [r.priority for r in relevant]
        assert priorities == sorted(priorities, reverse=True), (
            f"Rules not in descending priority order: {priorities}"
        )

    async def test_inactive_rule_not_returned(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_active_rules() excludes rules with is_active=False."""
        repo = UserValidationRepository(db_session)

        active_rule = await _create_rule(repo, name="active-unique-abc", is_active=True, priority=99)
        inactive_rule = await _create_rule(repo, name="inactive-unique-xyz", is_active=False, priority=99)

        rules = await repo.get_active_rules()
        rule_ids = {r.id for r in rules}

        assert active_rule.id in rule_ids, "Active rule should appear in get_active_rules()"
        assert inactive_rule.id not in rule_ids, "Inactive rule must not appear in get_active_rules()"


# ---------------------------------------------------------------------------
# TestUserValidationTemplateRepository
# ---------------------------------------------------------------------------


class TestUserValidationTemplateRepository:
    async def test_get_template_by_name_returns_correct_row(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_template_by_name() fetches the right row by unique name."""
        repo = UserValidationRepository(db_session)
        await _create_template(repo, name="named-template-alpha")

        result = await repo.get_template_by_name("named-template-alpha")

        assert result is not None
        assert result.name == "named-template-alpha"

    async def test_get_template_by_name_returns_none_for_missing(
        self,
        db_session: AsyncSession,
    ) -> None:
        """get_template_by_name() returns None when no row matches."""
        repo = UserValidationRepository(db_session)

        result = await repo.get_template_by_name("does-not-exist-99999")

        assert result is None

    async def test_list_templates_pagination(
        self,
        db_session: AsyncSession,
    ) -> None:
        """list_templates() returns (rows, total) and respects page_size."""
        repo = UserValidationRepository(db_session)

        # Seed 3 templates
        for i in range(3):
            await _create_template(repo, name=f"paginate-template-{i}")

        # Fetch page 1 with size 2
        page1, total = await repo.list_templates(page=1, page_size=2)

        assert total >= 3, f"Expected at least 3 total templates, got {total}"
        assert len(page1) == 2

        # Fetch page 2 — must have at least 1
        page2, _ = await repo.list_templates(page=2, page_size=2)
        assert len(page2) >= 1

        # No UUID overlap between pages
        uuids_p1 = {t.uuid for t in page1}
        uuids_p2 = {t.uuid for t in page2}
        assert uuids_p1.isdisjoint(uuids_p2), "Pages must not overlap"
