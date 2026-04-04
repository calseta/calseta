# Issues Service — CONTEXT.md

## What this component does
Manages the agent_issues lifecycle: creation, status transitions, atomic checkout for agent work-locking, comments, and agent assignment. Issues are non-alert work items (remediation, detection tuning, post-incident) that agents and operators create to track follow-up work.

## Interfaces
- Input: IssueCreate/IssuePatch schemas, UUIDs from callers
- Output: IssueResponse/IssueCommentResponse schemas
- FK targets: agent_registrations (assignee/creator), alerts (origin), heartbeat_runs (checkout lock), agent_routines (routine-created issues — future; routine_id stored as plain BigInteger until agent_routines table exists)

## Key design decisions
- Identifier generation (CAL-NNN) uses COUNT(*)+1 — not perfectly race-safe but acceptable for v1 issue volumes
- Atomic checkout uses raw SQL UPDATE ... WHERE checkout_run_id IS NULL RETURNING id — same pattern as alert_assignments
- Status side effects are enforced in the service layer, not the repository — repositories are dumb
- checkout_run_id is cleared on done/cancelled transitions automatically
- `routine_id` is stored as a plain BigInteger (no FK constraint) until the agent_routines table is introduced in a future phase

## Extension pattern
To add a new status: add to IssueStatus constants, add side-effect handling in issue_service.patch_issue(), update the status lifecycle comment.

## Common failure modes
- 409 on checkout: another agent already holds the lock — caller should back off
- 404 on agent_uuid resolution: agent was deleted or UUID is wrong
- Missing identifier uniqueness: CAL-NNN collision under high parallel creation load (v1 known limitation)

## Test coverage
- tests/unit/services/test_issue_service.py
- tests/integration/test_issues_api.py
