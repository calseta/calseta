---
name: chunk
description: Claim and work a chunk from PROJECT_PLAN.md. Use when starting work on a specific project plan chunk.
argument-hint: "<chunk-id> (e.g. 1.1, 2.3)"
allowed-tools: Read, Edit, Write, Glob, Grep, Bash
---

Work PROJECT_PLAN.md chunk **$ARGUMENTS**.

Follow the agent protocol exactly:

**Before writing any code:**
1. Read `PROJECT_PLAN.md` and find chunk $ARGUMENTS.
2. Verify every chunk listed in "Depends on" has status `complete`. If any are not complete, stop and report the blocker — do not proceed.
3. Read all linked PRD sections in full.
4. Review the output artifacts of every dependency chunk.
5. Update chunk $ARGUMENTS status from `pending` → `in_progress` and set Assigned Agent to your identifier.
6. Update the Progress Dashboard counts.

**While implementing:**
- Implement only what the chunk's scope specifies. No scope creep.
- If you discover missing requirements or improvements, record them in the completion log under Notes — do not implement them.

**When complete:**
1. Verify every acceptance criterion in the chunk is met. Do not mark complete if any criterion is unmet.
2. Update chunk $ARGUMENTS status to `complete`.
3. Append a completion log entry:
   ```
   - [AGENT_ID] [ISO-8601 timestamp]
     Built: <2–5 sentence description>
     Deviations: <spec deviations and rationale, or "none">
     Notes: <anything downstream chunks should know, or "none">
   ```
4. Update the Progress Dashboard counts.

**If blocked:**
1. Set status to `blocked`.
2. Append a log entry describing the blocker clearly.
3. Do not proceed further.
