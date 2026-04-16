# Detection-as-Code Agent

**Date**: 2026-04-15
**Author**: Jorge Castro
**Status**: Draft
**Depends on**: [Agent Runtime Hardening](./2026-04-15-agent-runtime-hardening.md) (specifically chunk D4: Workspace Schema)

---

## Problem Statement

Detection engineering is a bottleneck in every SOC. The cycle is slow: alerts fire, analysts investigate, they notice patterns (high false positive rates, detection gaps, noisy rules), and eventually someone writes a ticket for the detection engineering team. Weeks later, a human writes a new Sigma/KQL/SPL rule, tests it against sample data, opens a PR against the detection repo, waits for review, merges, and deploys. Meanwhile, the same false positives keep firing and the same gaps keep existing.

Calseta already has the data to close this loop. The `alerts` table records every alert with its `detection_rule_id`, `close_classification`, and lifecycle timestamps. The `indicators` table has a global IOC corpus with enrichment results and malice verdicts. The `detection_rules` table catalogs every rule with MITRE mappings and metadata. This is everything a detection engineer needs to identify which rules are noisy, which attack techniques have no coverage, and what patterns appear in false positives vs. true positives.

The Detection-as-Code (DaC) agent automates this cycle:

1. **Analyze** -- query Calseta's alert corpus to find detection gaps, false positive patterns, and rule performance metrics
2. **Draft** -- generate new or updated detection rules in standard formats (Sigma, KQL, SPL)
3. **Propose** -- open pull requests against the customer's detection-as-code repository with the drafted rules
4. **Track** -- monitor PR lifecycle (review comments, requested changes, merge, deploy) and iterate

This is the first Calseta agent that **writes code and manages git branches**. It requires the workspace isolation infrastructure designed (schema only) in the runtime hardening PRD (chunk D4) and implemented in this PRD.

**How DaC agents run**: DaC agents are standard Calseta managed agents — they use the existing runtime engine, tool loop, session management, and trigger system. They run via:
- **Routines** (cron schedule) — e.g., weekly analysis runs using Calseta's existing routine trigger system
- **On-demand** — manual trigger via API or UI
- **PR comment wakeups** — GitHub/GitLab webhook → Calseta webhook endpoint → comment-driven re-trigger (depends on runtime hardening C1)

There is no separate execution path. The only difference is that DaC agents have `workspace_mode: "git_worktree"` and get additional git-related tools.

---

## Solution

When this ships, a detection engineer will be able to:

- **Register a DaC agent** that connects to their detection repository (GitHub, GitLab, Bitbucket, or any git remote accessible via HTTPS or SSH)
- **Configure an analysis schedule** -- the agent runs on a routine (e.g., weekly) or on-demand to analyze alert trends
- **Review agent-drafted detection rules** as standard GitHub/GitLab pull requests in their normal review workflow
- **Provide feedback via PR comments** -- the agent reads review comments and can revise its proposed rules
- **See detection coverage improvements** over time via Calseta metrics (which MITRE techniques went from uncovered to covered, false positive rate trends per rule)
- **Choose rule formats** -- Sigma for portability, or native formats (KQL, SPL) for direct deployment

### What the Agent Does NOT Do

- **Deploy rules to production SIEMs** -- the agent opens PRs. Deployment is the customer's CI/CD pipeline. Calseta never pushes rules directly to Sentinel/Splunk/Elastic.
- **Delete or disable existing rules** -- it can propose tuning changes (adding exclusions, adjusting thresholds) but never removes rules without human review.
- **Access the SIEM directly** -- all data comes from Calseta's normalized alert/indicator corpus. The agent does not query Sentinel/Splunk/Elastic APIs for raw log data.

---

## User Stories

### Analysis & Gap Detection

1. As a detection engineer, I want the agent to analyze the last N days (configurable, default 30) of alerts and rank detection rules by false positive rate so that I can prioritize tuning work.
2. As a detection engineer, I want the agent to identify MITRE ATT&CK techniques that have no detection coverage (no rules mapped to those techniques) so that I know where my blind spots are.
3. As a detection engineer, I want the agent to identify MITRE techniques that are mapped to rules but those rules have not fired in the analysis window so that I can distinguish between "covered but quiet" and "uncovered."
4. As a SOC manager, I want the agent to produce a detection health report showing: total rules, active rules, rules with >50% FP rate, techniques covered vs. uncovered, top 10 noisiest rules, and mean time from alert to close per rule so that I have a single view of detection posture.
5. As a detection engineer, I want the agent to correlate indicator enrichment results (malice verdicts from VirusTotal, AbuseIPDB) with alert close classifications to identify patterns like "all alerts with benign indicators are closed as false positives" so that I can build smarter exclusions.
6. As a detection engineer, I want to configure which MITRE framework version and which technique subset the agent should focus on (e.g., only Initial Access and Lateral Movement) so that analysis is scoped to relevant attack stages.
7. As a detection engineer, I want the agent to identify detection rules that fire frequently but are never actioned (closed without investigation) so that I can reduce alert fatigue.
8. As a SOC analyst, I want the agent to flag rules that consistently produce alerts on the same small set of indicators (same IP, same domain) so that I can add targeted allowlist entries.

### Rule Drafting

9. As a detection engineer, I want the agent to draft Sigma rules for identified detection gaps so that I get a portable, vendor-neutral starting point.
10. As a detection engineer, I want the agent to draft rules in native SIEM query languages (KQL for Sentinel, SPL for Splunk) when I specify the target platform so that rules can be deployed without translation.
11. As a detection engineer, I want the agent to include MITRE ATT&CK metadata (tactic, technique, sub-technique) in every drafted rule so that rules integrate with my ATT&CK coverage framework.
12. As a detection engineer, I want the agent to draft tuning modifications for existing high-FP rules (adding exclusion conditions, tightening thresholds) rather than only creating new rules so that existing detections improve.
13. As a detection engineer, I want the agent to include a rationale in each drafted rule (why this rule, what gap it fills, what data supported the decision) so that reviewers understand the agent's reasoning.
14. As a detection engineer, I want the agent to reference specific alert UUIDs and indicator values as evidence when proposing a rule so that I can validate its analysis.
15. As a detection engineer, I want the agent to respect my repository's rule naming conventions and directory structure (configurable) so that PRs don't require restructuring.

### Git & PR Workflow

16. As a detection engineer, I want to connect the DaC agent to my detection repository via HTTPS clone URL and a personal access token (or GitHub App installation) so that the agent can push branches and open PRs.
17. As a detection engineer, I want the agent to create one branch per analysis run (e.g., `calseta/dac-2026-04-15-weekly`) and open a PR against my configured base branch (e.g., `main`) so that each batch of proposals is a single reviewable unit.
18. As a detection engineer, I want the agent to write rule files to the correct path in my repo (configurable, e.g., `rules/sigma/` or `detections/`) so that PRs match my repo layout.
19. As a detection engineer, I want the PR description to include a summary of the agent's analysis, the rules proposed, MITRE coverage changes, and links back to relevant Calseta alerts so that reviewers have full context.
20. As a detection engineer, I want to review the PR and leave comments (e.g., "adjust the threshold for this rule" or "add an exclusion for our VPN range") and have the agent push follow-up commits addressing my feedback so that the review loop works like any other PR.
21. As a detection engineer, I want the agent to handle merge conflicts by rebasing its branch against the latest base branch before pushing so that PRs stay mergeable.
22. As a detection engineer, I want to see the PR URL in Calseta's UI (on the agent run detail page) so that I can navigate directly from the agent's output to the PR.
23. As a detection engineer, I want the agent to support GitLab merge requests with the same workflow (create branch, push, open MR, respond to comments) so that I'm not locked into GitHub.
24. As a detection engineer, I want the agent to support Bitbucket pull requests so that my team's git hosting choice doesn't prevent adoption.

### Authentication & Security

25. As a platform engineer, I want git credentials (PAT, SSH key, GitHub App private key) stored encrypted in Calseta's secrets system (same as enrichment provider auth) so that credentials are not in plaintext.
26. As a platform engineer, I want the agent to use the minimum required git permissions (read repo contents, write branches, create PRs) so that a compromised token has limited blast radius.
27. As a platform engineer, I want the agent's git operations to happen in an isolated workspace (not the Calseta application directory) so that a malicious repo cannot affect the platform.
28. As a SOC manager, I want every git operation (clone, push, PR creation) logged as an activity event so that I have an audit trail of what the agent changed in external systems.

### Tracking & Metrics

29. As a SOC manager, I want to see a history of DaC agent runs with: analysis summary, rules proposed, PR URL, PR status (open/merged/closed), and MITRE coverage delta so that I can track detection improvement over time.
30. As a detection engineer, I want the agent to track which of its proposed rules were merged and which were rejected so that it can learn from reviewer feedback patterns.
31. As a SOC manager, I want a detection coverage metric that shows MITRE technique coverage before and after the DaC agent's contributions so that I can measure the agent's impact.
32. As a detection engineer, I want the agent to sync merged rules back to Calseta's `detection_rules` table so that the platform's detection catalog stays current.

### Configuration & Scheduling

33. As a detection engineer, I want to configure the agent with: repo URL, base branch, rules directory, rule format (sigma/kql/spl), analysis window (days), and MITRE focus areas so that the agent is tailored to my environment.
34. As a detection engineer, I want to run the agent on a cron schedule (e.g., weekly on Monday at 09:00 UTC) using Calseta's existing routine system so that detection improvements are continuous.
35. As a detection engineer, I want to trigger the agent on-demand with a specific focus (e.g., "analyze only Initial Access alerts from the last 7 days") so that I can direct the agent to urgent gaps.
36. As a SOC manager, I want the agent to respect the platform's cost budget controls so that detection analysis doesn't consume unbounded LLM tokens.

---

## Implementation Decisions

### Workspace Strategy: Git Worktree per Run

Each DaC agent run gets its own **git worktree** branching from a shared bare clone of the detection repository. This is the strategy that the runtime hardening PRD's `agent_workspaces` table was designed to support.

**Why git worktrees (not full clones or shared checkouts):**

| Strategy | Pros | Cons |
|----------|------|------|
| Full clone per run | Complete isolation | Slow (full history each time), wastes disk |
| Shared checkout, branches only | Fast, minimal disk | Concurrent runs on same repo collide; dirty state from one run leaks to next |
| **Git worktree per run** | Fast (shared object store), isolated working directory per run, native git feature | Requires bare/main clone to exist; worktree cleanup needed |

**Lifecycle:**

```
1. Agent registration → clone bare repo to {WORKSPACE_ROOT}/{agent_uuid}/repo.git
2. Agent run starts → create worktree: git worktree add {WORKSPACE_ROOT}/{agent_uuid}/runs/{run_uuid} -b calseta/dac-{date}-{short_uuid}
3. Agent works → write rules, commit, push
4. Agent run completes → worktree kept until PR is merged/closed (or configurable TTL)
5. PR merged/closed → git worktree remove, delete local branch
```

**WORKSPACE_ROOT** is `{CALSETA_DATA_DIR}/workspaces/` (default: `/data/calseta/workspaces/`). For containerized deployments, this directory must be on a persistent volume.

**Schema extension (builds on D4):**

The `agent_workspaces` table from the runtime hardening PRD gets additional columns:

| Column | Type | Description |
|--------|------|-------------|
| pr_url | TEXT | URL of the PR/MR created from this workspace |
| pr_number | INTEGER | PR/MR number in the hosting platform |
| pr_status | TEXT | `draft`, `open`, `changes_requested`, `approved`, `merged`, `closed` |
| pr_merged_at | TIMESTAMPTZ | When the PR was merged (null if not merged) |
| cleanup_after | TIMESTAMPTZ | When this worktree should be cleaned up |
| metadata | JSONB | Provider-specific metadata (GitHub PR ID, GitLab MR IID, etc.) |

### Git Integration: Provider-Agnostic Adapter

A `GitHostingProvider` abstract base class with concrete implementations for GitHub, GitLab, and Bitbucket. Same ports-and-adapters pattern as alert sources and enrichment providers.

```python
class GitHostingProvider(ABC):
    """Port for git hosting platform operations."""

    provider_name: str  # "github", "gitlab", "bitbucket"

    @abstractmethod
    async def create_pull_request(
        self,
        repo: str,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
    ) -> PullRequestResult: ...

    @abstractmethod
    async def get_pull_request(self, repo: str, pr_number: int) -> PullRequestInfo: ...

    @abstractmethod
    async def get_review_comments(self, repo: str, pr_number: int) -> list[ReviewComment]: ...

    @abstractmethod
    async def push_comment(self, repo: str, pr_number: int, body: str) -> None: ...

    @abstractmethod
    async def update_pull_request(
        self, repo: str, pr_number: int, *, title: str | None, body: str | None
    ) -> None: ...

    @abstractmethod
    def clone_url(self, repo: str) -> str: ...
```

**Authentication per provider:**

| Provider | Auth Method | Stored As |
|----------|-------------|-----------|
| GitHub | Personal Access Token (PAT) or GitHub App installation token | Encrypted in `agent_registration.adapter_config` JSONB |
| GitLab | Project Access Token or Personal Access Token | Encrypted in `agent_registration.adapter_config` JSONB |
| Bitbucket | App password or Repository Access Token | Encrypted in `agent_registration.adapter_config` JSONB |
| Self-hosted | PAT + custom API base URL | Encrypted in `agent_registration.adapter_config` JSONB |

All tokens are encrypted at rest using the same `ENCRYPTION_KEY` mechanism as enrichment provider auth configs. The `adapter_config` JSONB on AgentRegistration stores:

```json
{
  "git_provider": "github",
  "git_api_base": "https://api.github.com",
  "git_repo": "myorg/detections",
  "git_base_branch": "main",
  "git_token_encrypted": "...",
  "rules_directory": "rules/sigma",
  "rule_format": "sigma"
}
```

For self-hosted instances (GitHub Enterprise, GitLab CE/EE), the `git_api_base` field overrides the default API URL.

**Git CLI operations** (clone, worktree add/remove, add, commit, push) use `asyncio.create_subprocess_exec` with `git` — not a Python git library. The `git` binary is a required dependency (already present in the Docker image). Credentials are injected via `GIT_ASKPASS` or credential helper configuration, never passed as CLI arguments or URL components.

### Rule Formats: Sigma-First, Native Optional

The agent produces rules in one or more formats based on configuration:

**Sigma (default):** Portable YAML format. Works with any SIEM via sigma-cli or pySigma backend converters. The agent writes Sigma rules following the [SigmaHQ specification](https://sigmahq.io/docs/basics/rules.html):

```yaml
title: Suspicious PowerShell Download Cradle
id: <uuid>
status: experimental
description: >
  Detects PowerShell download cradle patterns observed in 15 alerts
  over the last 30 days. 12 of 15 were classified True Positive.
  Generated by Calseta DaC agent on 2026-04-15.
references:
  - calseta://alerts?rule_name=PowerShell%20Execution&status=Closed
author: Calseta DaC Agent
date: 2026/04/15
tags:
  - attack.execution
  - attack.t1059.001
logsource:
  category: process_creation
  product: windows
detection:
  selection:
    CommandLine|contains|all:
      - 'powershell'
      - 'downloadstring'
  condition: selection
falsepositives:
  - Legitimate admin scripts (see Calseta FP analysis)
level: high
```

**KQL (for Sentinel):** When `rule_format=kql`, the agent produces a KQL query file plus a YAML metadata file (ARM template-compatible) for direct deployment via Sentinel CI/CD pipelines.

**SPL (for Splunk):** When `rule_format=spl`, the agent produces an SPL query file plus a `savedsearches.conf` stanza for deployment via Splunk's app packaging.

**Multi-format:** The agent can be configured to produce both Sigma and a native format in the same PR. The Sigma version goes to `rules/sigma/`, the native version goes to `rules/{platform}/`.

### Analysis Pipeline

The DaC agent's analysis phase executes as a series of Calseta tool calls (using the existing tool system), not raw SQL:

**Step 1 -- Rule Performance Analysis:**
- Call `search_alerts` with configurable time window
- Call `get_detection_metrics` (new tool) to get per-rule statistics: alert count, FP rate, mean time to close, distinct indicator count
- Rank rules by FP rate and alert volume

**Step 2 -- MITRE Coverage Analysis:**
- Call `get_detection_rules` to get all rules with their MITRE mappings
- Build a coverage matrix: technique -> [rules mapped, alerts in window, FP rate]
- Identify techniques with zero rules (gaps) and techniques with rules but zero alerts (quiet coverage)

**Step 3 -- Pattern Analysis:**
- For high-FP rules: call `get_alert` on a sample of FP-classified alerts to find common indicator/payload patterns
- For detection gaps: analyze indicators from recent alerts to find attack patterns not caught by existing rules
- Correlate indicator malice verdicts with alert classifications

**Step 4 -- Rule Drafting:**
- Generate rules based on identified gaps and tuning opportunities
- Include evidence references (alert UUIDs, indicator values, FP statistics)
- Follow configured format and naming conventions

**Step 5 -- PR Creation:**
- Create git branch, write rule files, commit, push
- Open PR with structured description (analysis summary, rules proposed, MITRE delta)
- Record PR URL in workspace metadata

### New Tools for the DaC Agent

These tools are added to the builtin tool registry. They are available to any agent but designed for detection analysis:

| Tool ID | Category | Tier | Description |
|---------|----------|------|-------------|
| `get_detection_metrics` | `calseta_api` | `safe` | Per-rule statistics: alert count, FP rate, MTTC, indicator overlap. Accepts time window. |
| `get_mitre_coverage` | `calseta_api` | `safe` | MITRE ATT&CK coverage matrix: technique -> rules, alert count, gap status. |
| `get_rule_fp_analysis` | `calseta_api` | `safe` | Deep FP analysis for a specific rule: common indicators, payloads, close reasons. |
| `git_write_file` | `workspace` | `managed` | Write a file to the agent's workspace. Used for creating rule files. |
| `git_commit` | `workspace` | `managed` | Stage and commit files in the agent's workspace. |
| `git_push` | `workspace` | `managed` | Push the current branch to the remote. |
| `git_create_pr` | `workspace` | `requires_approval` | Open a PR/MR against the configured base branch. Requires approval because it creates an external artifact. |
| `git_get_pr_comments` | `workspace` | `safe` | Read review comments on an open PR. |
| `git_push_revision` | `workspace` | `managed` | Push a follow-up commit to an existing PR branch (for addressing review feedback). |

**Tool tier rationale:**
- Analysis tools (`get_detection_metrics`, `get_mitre_coverage`, `get_rule_fp_analysis`) are `safe` -- read-only Calseta queries.
- File/commit/push tools are `managed` -- they modify the workspace but only affect the agent's isolated worktree.
- PR creation is `requires_approval` -- it creates a visible artifact in the customer's repository. The approval gate (from v1 workflow approval system) ensures a human signs off before the agent opens a PR.

### PR Review Loop

The DaC agent handles PR review feedback via comment-driven wakeups (from the runtime hardening PRD, chunk C1). The flow:

```
1. Agent opens PR → workspace recorded with pr_url, pr_number, pr_status='open'
2. Reviewer leaves comment on PR
3. Calseta webhook endpoint receives PR comment event (GitHub/GitLab webhook)
4. Webhook handler checks: does this PR belong to a DaC agent workspace?
5. If yes → enqueue new heartbeat run with:
   - invocation_source = 'comment'
   - context_snapshot.wake_comments = [reviewer comment]
   - context_snapshot.workspace_uuid = workspace UUID
6. Agent wakes up → reads PR comments → revises rules → pushes new commit
7. Agent posts a summary comment on the PR explaining what changed
```

This requires a new webhook endpoint: `POST /v1/webhooks/git/{provider}` that receives push/PR/comment events from GitHub/GitLab/Bitbucket and routes them to the appropriate agent.

### Detection Rule Sync-Back

When a PR opened by the DaC agent is merged, the agent needs to sync the new/updated rules back to Calseta's `detection_rules` table:

1. Webhook receives PR merge event
2. Agent is triggered with `invocation_source='comment'` (PR merged is treated as a comment event)
3. Agent reads the merged rule files, extracts metadata (name, MITRE mappings, severity)
4. Agent calls `sync_detection_rule` tool to upsert the rule in Calseta's `detection_rules` table
5. `detection_rules` row gets `source_rule_id` set to the file path in the repo, `created_by` set to `dac_agent:{agent_uuid}`

New tool:

| Tool ID | Category | Tier | Description |
|---------|----------|------|-------------|
| `sync_detection_rule` | `calseta_api` | `managed` | Create or update a detection rule in Calseta from a rule file. Used after PR merge to keep the catalog current. |

### Analysis Window Configuration

The analysis window is configured per agent via `adapter_config`:

```json
{
  "analysis_window_days": 30,
  "min_alerts_for_analysis": 10,
  "fp_rate_threshold": 0.5,
  "mitre_focus_tactics": ["initial-access", "lateral-movement", "execution"],
  "max_rules_per_run": 10,
  "include_quiet_coverage": true
}
```

- `analysis_window_days` -- how far back to look (default 30, max 365)
- `min_alerts_for_analysis` -- minimum alert count for a rule to be included in FP analysis (default 10)
- `fp_rate_threshold` -- FP rate above which a rule is flagged for tuning (default 0.5 = 50%)
- `mitre_focus_tactics` -- limit analysis to specific MITRE tactics (null = all)
- `max_rules_per_run` -- cap on rules proposed per run to keep PRs reviewable (default 10)
- `include_quiet_coverage` -- whether to report on rules that exist but haven't fired (default true)

### Agent Registration

The DaC agent is registered as a managed agent with `workspace_mode='git_worktree'`:

```json
{
  "name": "Detection-as-Code Agent",
  "execution_mode": "managed",
  "agent_type": "standalone",
  "adapter_type": "anthropic",
  "workspace_mode": "git_worktree",
  "adapter_config": {
    "git_provider": "github",
    "git_repo": "myorg/detections",
    "git_base_branch": "main",
    "git_token_encrypted": "...",
    "rules_directory": "rules/sigma",
    "rule_format": "sigma",
    "analysis_window_days": 30,
    "fp_rate_threshold": 0.5,
    "max_rules_per_run": 10
  },
  "tool_ids": [
    "search_alerts",
    "get_alert",
    "get_detection_metrics",
    "get_mitre_coverage",
    "get_rule_fp_analysis",
    "git_write_file",
    "git_commit",
    "git_push",
    "git_create_pr",
    "git_get_pr_comments",
    "git_push_revision",
    "sync_detection_rule"
  ],
  "system_prompt": "You are a detection engineering agent...",
  "budget_monthly_cents": 5000
}
```

---

## Testing Strategy

### Unit Tests

- **Detection metrics service**: mock alert/rule data, verify FP rate calculation, MITRE coverage matrix generation, quiet coverage identification
- **Rule generator**: mock analysis results, verify Sigma YAML output conforms to SigmaHQ schema, verify KQL/SPL output is syntactically valid
- **Git hosting adapters**: mock HTTP responses for GitHub/GitLab/Bitbucket APIs, verify PR creation, comment reading, branch operations
- **Workspace manager**: mock `git` subprocess calls, verify worktree lifecycle (create, use, cleanup), verify credential injection via `GIT_ASKPASS`
- **Webhook handler**: mock incoming GitHub/GitLab/Bitbucket webhook payloads, verify routing to correct agent workspace

### Integration Tests

- **End-to-end analysis**: seed alerts and detection rules, run the analysis pipeline, verify metrics are correct and MITRE gaps are identified
- **Rule file writing**: create a workspace, write a Sigma rule, verify file contents and YAML validity
- **Git operations**: use a local bare git repo (no network), test clone, worktree create, commit, push, worktree cleanup
- **PR webhook loop**: simulate PR comment webhook, verify agent is re-triggered with comment context, verify follow-up commit

### Test Patterns

- Git operations use a local bare repo (`git init --bare`) in a temp directory -- no external git hosting dependency
- HTTP calls to GitHub/GitLab/Bitbucket APIs are mocked via `httpx` transport mocking (same pattern as enrichment provider tests)
- Sigma rule validation uses `sigma-cli check` if available, otherwise structural YAML validation
- Follow existing patterns in `tests/integration/agent_control_plane/`

---

## Out of Scope

- **Direct SIEM deployment** -- the agent opens PRs, never pushes rules to Sentinel/Splunk/Elastic APIs. Deployment is the customer's CI/CD concern.
- **Log-level analysis** -- the agent works with Calseta's normalized alert corpus, not raw SIEM logs. It cannot write rules based on log fields not captured in alerts.
- **Sigma-to-native conversion** -- the agent does not run `sigma-cli convert`. If the customer wants native format, they configure `rule_format=kql|spl` and the agent drafts natively.
- **Rule testing against live data** -- dry-run validation (running a draft rule against historical logs) requires SIEM API access, which is out of scope. The agent validates rules structurally (valid YAML/KQL/SPL syntax) but does not test detection efficacy.
- **Multi-repo support** -- one DaC agent = one repository. Multiple repos require multiple agent registrations.
- **Git submodules or monorepo support** -- the agent works with a single repo root. Submodule navigation is not supported.
- **Branch protection override** -- if the base branch requires CI checks, the agent's PR must pass them. The agent does not bypass branch protection.
- **SSH key authentication** -- v1 supports HTTPS + PAT/App token only. SSH key support is a follow-up (requires `ssh-agent` management in containers).

---

## Open Questions

0. **Persistent volume for agent data**: `CALSETA_DATA_DIR` currently defaults to `/tmp/calseta` (wiped on container restart) and `AGENT_FILES_DIR` to `./data/agents` (not volume-mounted in docker-compose.yml). Git worktree clones live under `CALSETA_DATA_DIR/workspaces/` — these MUST survive container restarts. **Action required before DaC ships**: add a named volume (`calseta_data`) to docker-compose.yml mounted at `/data/calseta` for api/worker services. Update `CALSETA_DATA_DIR` default from `/tmp/calseta` to `/data/calseta`. Update `make lab` and deployment docs. For cloud: EFS (AWS ECS) or Azure Files (ACA). This is a prerequisite for this PRD, not a chunk within it — it should be a small standalone PR.

1. **PR approval mode**: Should `git_create_pr` always require human approval (tier=`requires_approval`), or should there be a "trusted" mode where the agent can open PRs without approval? Proposal: always require approval in v1 to build trust; re-evaluate after 3 months of usage data.

2. **Sigma rule validation**: Should the agent validate Sigma rules using `sigma-cli check` before committing? This requires `sigma-cli` as a dependency. Alternative: structural YAML validation only (check required fields, valid log source, valid detection section). Proposal: structural validation in v1, optional `sigma-cli` integration in v2.

3. **Concurrent analysis runs**: Can two DaC agent runs analyze the same time window simultaneously? The worktree isolation handles git conflicts, but the analysis results might overlap. Proposal: enforce single-run via `max_concurrent_alerts=1` on the agent registration.

4. **PR comment webhook setup**: Who configures the webhook on the git hosting side? The Calseta UI could provide the webhook URL and secret, but the user must manually add it to their repo settings. Alternative: for GitHub Apps, Calseta registers the webhook automatically. Proposal: manual setup with copy-paste URL in v1; auto-registration for GitHub App in v2.

5. **Rule de-duplication**: How does the agent avoid proposing rules that already exist in the repo? It reads the repo contents before drafting, but should it maintain a cache of known rules? Proposal: the agent reads the current repo contents at the start of each run and uses them as context for the LLM. No separate cache.

6. **Analysis scope for tuning vs. new rules**: Should the agent focus on tuning existing rules, creating new rules, or both? Some organizations want conservative agents that only tune, others want aggressive gap-fillers. Proposal: configurable `mode` field: `tune_only`, `create_only`, `both` (default).

7. **Cost estimation**: A full analysis run with rule drafting could consume significant LLM tokens (reading alert data, analyzing patterns, generating rules, formatting PRs). Should the agent estimate cost before running and require approval if above a threshold? Proposal: use the existing `max_cost_per_alert_cents` budget control, treating each DaC run as a "virtual alert" for budgeting purposes.

8. **Worktree cleanup policy**: How long to keep worktrees after PR merge/close? Options: immediate cleanup, configurable TTL, keep until disk pressure. Proposal: configurable `workspace_ttl_hours` (default 72 hours after PR close), with a periodic cleanup task.

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Agent produces invalid rules (bad syntax, wrong log source) | PR fails CI, wastes reviewer time | Structural validation before commit. Include validation errors in PR description if found. Never bypass repo CI. |
| Agent opens too many PRs, creating noise | Reviewer fatigue, loss of trust | `max_rules_per_run` caps PR size. Routine schedule (weekly) limits frequency. `requires_approval` gate on PR creation. |
| Git credentials leaked via logs or error messages | Token compromise | Credentials never in CLI args or URLs. `GIT_ASKPASS` helper. All git output sanitized before logging. Structured log fields exclude credential values. |
| Workspace disk exhaustion | Worker crashes, affects other agents | Periodic cleanup task. `WORKSPACE_MAX_DISK_MB` env var with enforcement. Worktree cleanup on PR merge. Alert if disk usage exceeds 80% of limit. |
| Agent analyzes stale data (alerts not yet enriched) | Incorrect FP analysis | Analysis tools filter to `enrichment_status='Enriched'` alerts only. Configurable `min_enrichment_age_hours` (default 24) to ensure enrichment has completed. |
| Concurrent runs create conflicting branches | Git push failures | Enforce `max_concurrent_alerts=1`. Branch names include run UUID for uniqueness. |
| Git hosting API rate limits | PR creation fails, comment reading fails | Exponential backoff on 429 responses. Cache PR data in workspace metadata to reduce API calls. |
| Malicious repo content executed during clone | RCE in Calseta worker | `git clone` with `--no-checkout` for bare repos. Worktrees only check out tracked files. No post-checkout hooks (`.git/hooks` are in the bare repo, not the worktree). `core.hooksPath=/dev/null` in git config for all operations. |

---

## Project Management

### Dependencies

This PRD depends on:
- **Runtime Hardening D4 (Workspace Schema)** -- the `agent_workspaces` table must exist before workspace manager can write to it
- **Runtime Hardening C1 (Comment-Driven Wakeups)** -- for PR review comment handling
- **Runtime Hardening C5 (CALSETA_* Environment Variables)** -- for workspace dir injection

All other runtime hardening chunks are beneficial but not blocking (streaming, cancellation, etc. improve the DX but aren't required for DaC to function).

### Overview

| Chunk | Wave | Status | Dependencies |
|-------|------|--------|-------------|
| E1: Detection metrics tools | 1 | pending | -- |
| E2: Git hosting provider adapter (ABC + GitHub) | 1 | pending | -- |
| E3: Workspace manager service | 1 | pending | D4 (runtime hardening) |
| E4: GitLab + Bitbucket adapters | 1 | pending | E2 |
| F1: Analysis pipeline (tool handlers) | 2 | pending | E1 |
| F2: Rule generator service | 2 | pending | -- |
| F3: Workspace tool handlers (git_write_file, git_commit, git_push) | 2 | pending | E3 |
| F4: PR creation tool handler | 2 | pending | E2, E3, F3 |
| G1: Git webhook endpoint | 3 | pending | E2 |
| G2: PR review comment wakeup handler | 3 | pending | G1, C1 (runtime hardening) |
| G3: Detection rule sync-back | 3 | pending | G1 |
| G4: DaC agent skill (system prompt + methodology) | 3 | pending | F1, F2, F4 |
| H1: Workspace cleanup periodic task | 4 | pending | E3 |
| H2: Detection coverage metrics API | 4 | pending | E1 |
| H3: DaC agent run detail UI | 4 | pending | G4 |
| H4: Integration tests | 4 | pending | G4 |

### Wave 1 -- Foundation (Adapters + Infrastructure)

#### Chunk E1: Detection Metrics Tools

- **What**: Implement three new builtin tools: `get_detection_metrics`, `get_mitre_coverage`, `get_rule_fp_analysis`. These are service-layer functions exposed as agent tools via the existing tool registry.
- **Why this wave**: Provides the analytical foundation all other chunks build on
- **Modules touched**: New `app/services/detection_analysis.py`, `app/seed/builtin_tools.py` (add tool definitions), `app/integrations/tools/dispatcher.py` (add handlers)
- **Depends on**: None
- **Produces**: Three queryable tools available to any managed agent
- **Acceptance criteria**:
  - [ ] `get_detection_metrics` accepts `window_days` (int) and returns per-rule stats: `rule_uuid`, `rule_name`, `alert_count`, `fp_count`, `fp_rate`, `tp_count`, `mean_time_to_close_seconds`, `distinct_indicators`, `mitre_techniques`
  - [ ] `get_mitre_coverage` returns: `covered_techniques` (list of techniques with at least one rule), `uncovered_techniques` (techniques in the ATT&CK matrix not mapped to any rule), `quiet_techniques` (covered but zero alerts in window)
  - [ ] `get_rule_fp_analysis` accepts `rule_uuid` and `window_days`, returns: common indicators across FP alerts, common payload patterns, suggested exclusions
  - [ ] All three tools registered in `BUILTIN_TOOLS` with correct schemas
  - [ ] All three tools have handler implementations in the dispatcher
  - [ ] Unit tests with seeded alert/rule data verify metric accuracy
- **Verification**: `pytest tests/ -k "detection_metrics or detection_analysis" --no-header -q`

#### Chunk E2: Git Hosting Provider Adapter (ABC + GitHub)

- **What**: Create the `GitHostingProvider` ABC and the GitHub implementation. HTTP calls via `httpx`. Supports personal access tokens and GitHub App installation tokens.
- **Why this wave**: Defines the extension point for all git hosting platforms
- **Modules touched**: New `app/integrations/git/base.py` (ABC), new `app/integrations/git/github.py`, new `app/integrations/git/factory.py`, `app/config.py` (no new env vars -- all config via adapter_config)
- **Depends on**: None
- **Produces**: Working GitHub PR creation, comment reading, update
- **Acceptance criteria**:
  - [ ] `GitHostingProvider` ABC with methods: `create_pull_request`, `get_pull_request`, `get_review_comments`, `push_comment`, `update_pull_request`, `clone_url`
  - [ ] `GitHubProvider` implements all methods using GitHub REST API v3
  - [ ] PAT auth: `Authorization: Bearer {token}` header
  - [ ] GitHub App auth: JWT generation from private key, installation token exchange
  - [ ] Custom API base URL for GitHub Enterprise (`git_api_base` in config)
  - [ ] `PullRequestResult` and `ReviewComment` dataclasses with provider-agnostic fields
  - [ ] All HTTP calls use `httpx.AsyncClient` with configurable timeout
  - [ ] Unit tests with mocked HTTP responses for all API operations
- **Verification**: `pytest tests/ -k "git_hosting or github_provider" --no-header -q`

#### Chunk E3: Workspace Manager Service

- **What**: Implement `WorkspaceManager` service that handles git worktree lifecycle: bare clone, worktree create, worktree remove, cleanup. Reads/writes `agent_workspaces` table.
- **Why this wave**: Infrastructure that all git operations depend on
- **Modules touched**: New `app/services/workspace_manager.py`, new `app/repositories/workspace_repository.py`, `app/db/models/agent_workspace.py` (extend with PR fields from this PRD)
- **Depends on**: D4 (runtime hardening -- `agent_workspaces` table must exist)
- **Produces**: `WorkspaceManager` with `provision(agent, run)`, `get_cwd(workspace)`, `cleanup(workspace)`, `cleanup_stale()`
- **Acceptance criteria**:
  - [ ] `provision(agent, run)` clones bare repo if not exists, creates worktree, returns workspace row with `cwd` set
  - [ ] Bare clone uses `git clone --bare --no-checkout` with credentials via `GIT_ASKPASS`
  - [ ] Worktree uses `git worktree add {path} -b {branch_name}` from the bare repo
  - [ ] Branch name format: `calseta/dac-{YYYY-MM-DD}-{short_uuid}`
  - [ ] `cleanup(workspace)` runs `git worktree remove` and deletes directory
  - [ ] `cleanup_stale()` finds workspaces with `cleanup_after < now()` and removes them
  - [ ] `agent_workspaces` table extended with: `pr_url`, `pr_number`, `pr_status`, `pr_merged_at`, `cleanup_after`, `metadata` columns (new migration)
  - [ ] Git hooks disabled via `core.hooksPath=/dev/null` for all operations (security)
  - [ ] All git subprocess calls sanitize output before logging (no credentials in logs)
  - [ ] Unit tests with local bare repo verify full lifecycle
- **Verification**: `pytest tests/ -k "workspace_manager" --no-header -q`

#### Chunk E4: GitLab + Bitbucket Adapters

- **What**: Implement `GitLabProvider` and `BitbucketProvider` classes extending `GitHostingProvider`.
- **Why this wave**: Completes provider coverage, independent of other chunks
- **Modules touched**: New `app/integrations/git/gitlab.py`, new `app/integrations/git/bitbucket.py`, `app/integrations/git/factory.py` (register)
- **Depends on**: E2 (ABC definition)
- **Produces**: Working GitLab MR and Bitbucket PR support
- **Acceptance criteria**:
  - [ ] `GitLabProvider` uses GitLab REST API v4 for merge requests
  - [ ] `GitLabProvider` supports custom API base URL for self-hosted GitLab
  - [ ] `BitbucketProvider` uses Bitbucket Cloud REST API 2.0 for pull requests
  - [ ] `BitbucketProvider` supports Bitbucket Server (Stash) via separate API base
  - [ ] Both providers implement all `GitHostingProvider` methods
  - [ ] Factory resolves provider from `adapter_config.git_provider` string
  - [ ] Unit tests with mocked HTTP responses for both providers
- **Verification**: `pytest tests/ -k "gitlab_provider or bitbucket_provider" --no-header -q`

### Wave 2 -- Core Agent Capabilities

#### Chunk F1: Analysis Pipeline (Tool Handlers)

- **What**: Implement the tool handler functions that back `get_detection_metrics`, `get_mitre_coverage`, and `get_rule_fp_analysis`. These execute actual database queries against alerts, detection_rules, and indicators tables.
- **Why this wave**: Needs tool definitions from E1
- **Modules touched**: `app/services/detection_analysis.py` (implement query logic), `app/integrations/tools/dispatcher.py` (wire handlers)
- **Depends on**: E1
- **Produces**: Fully functional analysis tools that return actionable data
- **Acceptance criteria**:
  - [ ] `get_detection_metrics` queries `alerts` JOIN `detection_rules` with time window filter, computes FP rate from `close_classification`, groups by rule
  - [ ] `get_mitre_coverage` uses a configurable ATT&CK technique list (embedded or configurable) and cross-references with `detection_rules.mitre_techniques`
  - [ ] `get_rule_fp_analysis` for a specific rule: loads FP-classified alerts, extracts common indicators via `alert_indicators` JOIN, identifies payload patterns in `raw_payload`
  - [ ] All queries filter to `enrichment_status='Enriched'` alerts by default (configurable)
  - [ ] Results are structured for LLM consumption (concise, labeled, no raw SQL dumps)
  - [ ] Integration tests with seeded data verify query accuracy
- **Verification**: `pytest tests/ -k "detection_analysis or analysis_pipeline" --no-header -q`

#### Chunk F2: Rule Generator Service

- **What**: Implement `RuleGeneratorService` that takes analysis results and produces rule file content in Sigma, KQL, or SPL format. This is a template/formatting service, not an LLM -- the LLM decides what rules to create, this service formats them.
- **Why this wave**: Independent of git operations
- **Modules touched**: New `app/services/rule_generator.py`
- **Depends on**: None
- **Produces**: `generate_sigma_rule(params) -> str`, `generate_kql_rule(params) -> str`, `generate_spl_rule(params) -> str`
- **Acceptance criteria**:
  - [ ] `generate_sigma_rule` produces valid Sigma YAML with all required fields (title, id, status, logsource, detection, level)
  - [ ] `generate_kql_rule` produces a `.kql` file with the query and a companion `.yaml` metadata file
  - [ ] `generate_spl_rule` produces a `.spl` file with the query and a `savedsearches.conf` stanza
  - [ ] All generators accept: title, description, MITRE tags, detection logic, false positive notes, references
  - [ ] Sigma output passes structural validation (required fields present, valid logsource category)
  - [ ] Generated rule IDs are deterministic UUIDs (based on rule content hash) to prevent duplicates
  - [ ] Unit tests for each format with known inputs/outputs
- **Verification**: `pytest tests/ -k "rule_generator" --no-header -q`

#### Chunk F3: Workspace Tool Handlers (git_write_file, git_commit, git_push)

- **What**: Implement tool handlers for `git_write_file`, `git_commit`, and `git_push`. These operate within the agent's provisioned workspace.
- **Why this wave**: Needs workspace manager (E3) for the working directory
- **Modules touched**: `app/integrations/tools/dispatcher.py` (add handlers), `app/services/workspace_manager.py` (add commit/push methods)
- **Depends on**: E3
- **Produces**: Tools that let an agent write files and push to a git remote
- **Acceptance criteria**:
  - [ ] `git_write_file` writes content to `{workspace_cwd}/{rules_directory}/{filename}` and returns the file path
  - [ ] `git_write_file` rejects paths that escape the workspace directory (path traversal protection)
  - [ ] `git_commit` runs `git add . && git commit -m "{message}"` in the workspace cwd
  - [ ] `git_commit` sets author to `Calseta DaC Agent <dac-agent@calseta.io>` (configurable)
  - [ ] `git_push` runs `git push -u origin {branch_name}` with credentials via `GIT_ASKPASS`
  - [ ] All git operations log structured events (activity_events)
  - [ ] Path traversal attempts raise `ToolForbiddenError`
  - [ ] Unit tests with local git repo verify write, commit, push
- **Verification**: `pytest tests/ -k "workspace_tool or git_write or git_commit or git_push" --no-header -q`

#### Chunk F4: PR Creation Tool Handler

- **What**: Implement `git_create_pr` tool handler. Creates a PR via the git hosting provider, records PR metadata in the workspace row.
- **Why this wave**: Needs git hosting adapter (E2) and workspace (E3) and git push (F3)
- **Modules touched**: `app/integrations/tools/dispatcher.py` (add handler), `app/services/workspace_manager.py` (update workspace with PR data)
- **Depends on**: E2, E3, F3
- **Produces**: Working PR creation from agent tool call
- **Acceptance criteria**:
  - [ ] `git_create_pr` calls `git_hosting_provider.create_pull_request()` with branch name, base branch, title, body
  - [ ] PR title includes analysis date and rule count (e.g., "DaC: 3 new Sigma rules (2026-04-15)")
  - [ ] PR body includes: analysis summary, per-rule description with evidence, MITRE coverage delta, link back to Calseta agent run
  - [ ] Workspace row updated with `pr_url`, `pr_number`, `pr_status='open'`
  - [ ] Tool requires approval (tier=`requires_approval`) -- approval must be granted before PR is created
  - [ ] Activity event emitted: `workspace.pr_created`
  - [ ] Unit test with mocked git hosting API verifies PR creation and workspace update
- **Verification**: `pytest tests/ -k "create_pr or pr_creation" --no-header -q`

### Wave 3 -- Review Loop & Automation

#### Chunk G1: Git Webhook Endpoint

- **What**: Create `POST /v1/webhooks/git/{provider}` endpoint that receives webhook events from GitHub, GitLab, and Bitbucket. Validates webhook signatures, routes events to the correct handler.
- **Why this wave**: Enables the review feedback loop
- **Modules touched**: New `app/api/v1/git_webhooks.py`, `app/api/v1/router.py` (include), new `app/services/git_webhook_service.py`
- **Depends on**: E2 (for provider-specific payload parsing)
- **Produces**: Webhook endpoint that receives and validates git platform events
- **Acceptance criteria**:
  - [ ] `POST /v1/webhooks/git/github` validates `X-Hub-Signature-256` header
  - [ ] `POST /v1/webhooks/git/gitlab` validates `X-Gitlab-Token` header
  - [ ] `POST /v1/webhooks/git/bitbucket` validates request signature
  - [ ] Events parsed: `pull_request.comment`, `pull_request.review`, `pull_request.merged`, `pull_request.closed`
  - [ ] Webhook matches incoming PR number to `agent_workspaces.pr_number` to find the owning agent
  - [ ] Unmatched webhooks return 200 (accepted but ignored -- don't retry)
  - [ ] Webhook secret per agent stored in `adapter_config.webhook_secret_encrypted`
  - [ ] Returns 202 Accepted within 200ms (all processing is async)
  - [ ] Rate limited: 60 requests per minute per provider endpoint
- **Verification**: `pytest tests/ -k "git_webhook" --no-header -q`

#### Chunk G2: PR Review Comment Wakeup Handler

- **What**: When a PR comment webhook is received for a DaC agent's workspace, enqueue a new heartbeat run with `invocation_source='comment'` and the reviewer's comment as wake context.
- **Why this wave**: Needs webhook endpoint (G1) and comment-driven wakeups (C1 from runtime hardening)
- **Modules touched**: `app/services/git_webhook_service.py` (event handler), `app/services/agent_dispatch.py` (enqueue wakeup)
- **Depends on**: G1, C1 (runtime hardening)
- **Produces**: Automatic agent re-trigger on PR review comments
- **Acceptance criteria**:
  - [ ] PR comment webhook triggers new heartbeat run for the workspace's agent
  - [ ] Wake context includes: reviewer name, comment body, file path (if inline comment), PR URL
  - [ ] Agent's workspace context is restored (same workspace cwd, same branch)
  - [ ] Rate limiting: max 1 re-trigger per PR per 10 minutes (prevents spam from rapid-fire comments)
  - [ ] Bot comments (from the DaC agent itself) do not trigger re-investigation (prevent loops)
  - [ ] Activity event emitted: `workspace.pr_comment_received`
- **Verification**: `pytest tests/ -k "pr_comment_wakeup or review_wakeup" --no-header -q`

#### Chunk G3: Detection Rule Sync-Back

- **What**: When a PR merge webhook is received, trigger the agent to read merged rule files and sync them back to `detection_rules` table.
- **Why this wave**: Needs webhook endpoint (G1)
- **Modules touched**: `app/services/git_webhook_service.py` (merge handler), `app/services/detection_rule_sync.py` (new), `app/seed/builtin_tools.py` (add `sync_detection_rule`)
- **Depends on**: G1
- **Produces**: Automatic detection_rules catalog update on PR merge
- **Acceptance criteria**:
  - [ ] PR merge event triggers agent wakeup with `wake_reason='pr_merged'`
  - [ ] Agent reads merged rule files from the workspace
  - [ ] `sync_detection_rule` tool upserts rule in `detection_rules`: name, source_rule_id (file path), severity, mitre_tactics, mitre_techniques, documentation, created_by
  - [ ] Existing rules matched by `source_rule_id` are updated (not duplicated)
  - [ ] New rules get `created_by='dac_agent:{agent_uuid}'`
  - [ ] Workspace status updated to `pr_status='merged'`, `pr_merged_at` set
  - [ ] Workspace scheduled for cleanup (`cleanup_after = now + ttl`)
  - [ ] Activity event emitted: `workspace.pr_merged`
- **Verification**: `pytest tests/ -k "rule_sync or detection_sync" --no-header -q`

#### Chunk G4: DaC Agent Skill (System Prompt + Methodology)

- **What**: Create the skill bundle for the DaC agent: system prompt template, methodology document, and example workflows. This is the "brain" that turns the analysis tools + git tools into a coherent detection engineering agent.
- **Why this wave**: Needs all tools and services to be functional
- **Modules touched**: New skill in `app/seed/skills/` or as a builtin skill configuration, `app/seed/builtin_tools.py` (seed the complete DaC tool set)
- **Depends on**: F1, F2, F4
- **Produces**: A reusable skill that any DaC agent can be configured with
- **Acceptance criteria**:
  - [ ] System prompt defines the agent's role, capabilities, constraints, and output format
  - [ ] Methodology document describes the 5-step analysis pipeline (metrics, coverage, patterns, drafting, PR)
  - [ ] System prompt instructs the agent to always include evidence (alert UUIDs, statistics) in rule rationale
  - [ ] System prompt instructs the agent to respect `max_rules_per_run` and format constraints
  - [ ] System prompt includes examples of good Sigma/KQL/SPL rules for few-shot learning
  - [ ] Methodology is structured so the agent follows it step-by-step (not free-form)
  - [ ] Sandbox test: run the agent with mock data and verify it produces a valid PR with rules
- **Verification**: Manual review + sandbox test with seeded data

### Wave 4 -- Polish & Hardening

#### Chunk H1: Workspace Cleanup Periodic Task

- **What**: Create a periodic task (registered with procrastinate) that runs daily and cleans up stale workspaces. Removes worktrees, deletes local branches, frees disk space.
- **Why this wave**: Operational necessity, independent of feature work
- **Modules touched**: New `app/tasks/workspace_cleanup.py`, `app/worker.py` (register task)
- **Depends on**: E3
- **Produces**: Automatic workspace garbage collection
- **Acceptance criteria**:
  - [ ] Task runs daily (configurable via `WORKSPACE_CLEANUP_INTERVAL_HOURS`, default 24)
  - [ ] Cleans up workspaces where `cleanup_after < now()` and `pr_status IN ('merged', 'closed')`
  - [ ] Also cleans up workspaces with no associated run (orphaned from failed provisioning)
  - [ ] Logs cleanup summary: workspaces removed, disk freed
  - [ ] Does not remove workspaces with active/open PRs
  - [ ] `WORKSPACE_MAX_DISK_MB` env var: if total workspace disk exceeds limit, clean up oldest merged workspaces first
  - [ ] Unit test with mock filesystem verifies cleanup logic
- **Verification**: `pytest tests/ -k "workspace_cleanup" --no-header -q`

#### Chunk H2: Detection Coverage Metrics API

- **What**: Extend the existing metrics API (`GET /v1/metrics/alerts`) with detection coverage data: MITRE technique coverage percentage, coverage trend over time (before/after DaC agent contributions), and per-agent contribution stats.
- **Why this wave**: Needs analysis tools (E1) and rule sync (G3) to have meaningful data
- **Modules touched**: `app/services/metrics.py` (add detection coverage queries), `app/schemas/metrics.py` (extend response), `app/api/v1/metrics.py` (new endpoint or extend existing)
- **Depends on**: E1
- **Produces**: Detection coverage metrics in the API
- **Acceptance criteria**:
  - [ ] New response section: `detection_coverage` with `total_mitre_techniques`, `covered_count`, `coverage_percentage`, `uncovered_techniques` (list)
  - [ ] Historical coverage: `coverage_trend` showing coverage percentage at monthly intervals
  - [ ] Per-agent contribution: `dac_agent_contributions` showing rules created, rules merged, FP rate impact per DaC agent
  - [ ] MCP resource: `calseta://metrics/detection-coverage` exposes the same data
  - [ ] Unit tests verify coverage calculation accuracy
- **Verification**: `pytest tests/ -k "detection_coverage_metrics" --no-header -q`

#### Chunk H3: DaC Agent Run Detail UI

- **What**: Add UI components for DaC agent visibility: workspace status on agent detail page, PR link and status badge, analysis summary in run transcript, detection coverage chart on dashboard.
- **Why this wave**: Needs all backend work to be functional
- **Modules touched**: `ui/src/pages/settings/agents/detail.tsx`, `ui/src/pages/dashboard/index.tsx`, new `ui/src/components/workspace-status.tsx`
- **Depends on**: G4
- **Produces**: Visual feedback for DaC agent operations
- **Acceptance criteria**:
  - [ ] Agent detail page shows workspace info: repo URL, base branch, current PR (if any) with link
  - [ ] PR status badge: draft (dim), open (teal), changes_requested (amber), merged (green), closed (red)
  - [ ] Run transcript panel shows analysis summary and rule proposals as structured cards
  - [ ] Dashboard detection coverage card: MITRE heatmap or percentage gauge
  - [ ] Workspace status section shows disk usage and cleanup schedule
- **Verification**: Manual UI review

#### Chunk H4: Integration Tests

- **What**: End-to-end integration tests for the full DaC pipeline: analysis -> drafting -> PR creation -> review comment -> revision -> merge -> sync-back.
- **Why this wave**: Needs all components functional
- **Modules touched**: New `tests/integration/dac_agent/`
- **Depends on**: G4
- **Produces**: Confidence that the full pipeline works
- **Acceptance criteria**:
  - [ ] Test seeds: 100 alerts across 5 detection rules, 3 rules with >50% FP rate, 2 MITRE gaps
  - [ ] Agent runs analysis, identifies FP rules and gaps
  - [ ] Agent drafts 3 Sigma rules and 2 tuning proposals
  - [ ] Agent creates branch, commits, pushes (to local bare repo)
  - [ ] Agent opens PR (mocked GitHub API)
  - [ ] Simulated review comment triggers re-run
  - [ ] Agent revises one rule based on comment
  - [ ] Simulated PR merge triggers sync-back
  - [ ] `detection_rules` table updated with new rules
  - [ ] Workspace cleaned up after TTL
  - [ ] All activity events emitted correctly
  - [ ] Cost tracking records all LLM calls
- **Verification**: `pytest tests/integration/dac_agent/ --no-header -q`

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKSPACE_ROOT` | `{CALSETA_DATA_DIR}/workspaces` | Root directory for agent workspaces. Must be on persistent volume in containers. |
| `WORKSPACE_MAX_DISK_MB` | `10240` (10GB) | Maximum disk usage for all workspaces combined. Cleanup triggered when exceeded. |
| `WORKSPACE_CLEANUP_INTERVAL_HOURS` | `24` | How often the workspace cleanup task runs. |
| `WORKSPACE_DEFAULT_TTL_HOURS` | `72` | Hours to keep a workspace after its PR is merged or closed. |
| `DAC_ANALYSIS_MIN_ENRICHMENT_AGE_HOURS` | `24` | Minimum age of alerts (since enrichment completion) before including in analysis. |

---

## New Database Objects

### Migration: Extend `agent_workspaces` Table

Adds columns to the `agent_workspaces` table created by runtime hardening D4:

```sql
ALTER TABLE agent_workspaces ADD COLUMN pr_url TEXT;
ALTER TABLE agent_workspaces ADD COLUMN pr_number INTEGER;
ALTER TABLE agent_workspaces ADD COLUMN pr_status TEXT DEFAULT 'none';
ALTER TABLE agent_workspaces ADD COLUMN pr_merged_at TIMESTAMPTZ;
ALTER TABLE agent_workspaces ADD COLUMN cleanup_after TIMESTAMPTZ;
ALTER TABLE agent_workspaces ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb;
```

Index on `(pr_status)` for cleanup queries. Index on `(agent_registration_id, pr_number)` for webhook matching.

### No New Tables

All other data is stored in existing tables:
- Agent configuration: `agent_registrations.adapter_config` JSONB
- Tool definitions: `agent_tools` table (via seed)
- Run data: `heartbeat_runs` table
- Audit trail: `activity_events` table
- Detection rules: `detection_rules` table (sync-back target)

---

## File Structure

```
app/
  integrations/
    git/
      __init__.py
      base.py                  # GitHostingProvider ABC
      github.py                # GitHub REST API v3
      gitlab.py                # GitLab REST API v4
      bitbucket.py             # Bitbucket Cloud + Server
      factory.py               # Provider resolution from adapter_config
  services/
    detection_analysis.py      # Detection metrics + FP analysis + MITRE coverage
    rule_generator.py          # Sigma/KQL/SPL rule formatting
    workspace_manager.py       # Git worktree lifecycle
    detection_rule_sync.py     # PR merge → detection_rules upsert
    git_webhook_service.py     # Webhook event routing
  repositories/
    workspace_repository.py    # agent_workspaces CRUD
  tasks/
    workspace_cleanup.py       # Periodic worktree garbage collection
  api/
    v1/
      git_webhooks.py          # POST /v1/webhooks/git/{provider}
tests/
  integration/
    dac_agent/
      test_analysis_pipeline.py
      test_workspace_lifecycle.py
      test_pr_workflow.py
      test_rule_sync.py
  unit/
    services/
      test_detection_analysis.py
      test_rule_generator.py
      test_workspace_manager.py
    integrations/
      git/
        test_github_provider.py
        test_gitlab_provider.py
        test_bitbucket_provider.py
```
