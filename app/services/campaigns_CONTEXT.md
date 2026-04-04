# Campaigns Service — CONTEXT.md

## What this component does
Manages investigation campaigns — strategic objectives that group alerts, issues, and routines for goal tracking. Campaigns are optional containers (they don't affect execution) providing strategic visibility over operational work.

## Interfaces
- Input: CampaignCreate/CampaignPatch, CampaignItemCreate
- Output: CampaignResponse, CampaignMetrics
- FK targets: agent_registrations (owner_agent), campaign_items (polymorphic via item_uuid + item_type)

## Key design decisions
- Campaign items are stored as (item_type, item_uuid text) — polymorphic via text UUID, no FK constraint. This avoids complex FK chains across alerts/issues/routines.
- Metrics are always computed on-demand from linked items — never stored. current_value on the Campaign model is for user-provided measurements, not auto-computed.
- campaign_items uses AppendOnlyTimestampMixin (no updated_at) — items are linked/unlinked, not edited.

## Extension pattern
To add a new item_type: add to CampaignItemType constants, update validation in campaign_service.add_item().

## Common failure modes
- Invalid item_type: validated at API boundary, raises 422
- Duplicate items: not prevented at DB level — caller should check before adding

## Test coverage
- tests/unit/services/test_campaign_service.py
- tests/integration/test_campaigns_api.py
