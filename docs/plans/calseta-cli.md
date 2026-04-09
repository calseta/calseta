# `calseta` CLI — Design Proposal

**Status:** Draft  
**Date:** 2026-04-04  
**Branch context:** `feat/calseta-v2`

---

## 1. CLI Scope and Non-Scope

### What the CLI Does

The `calseta` CLI is a terminal-native interface for SOC analysts, agent developers, and Calseta administrators to interact with a running Calseta instance. It solves the problem that the REST API requires curl and raw JSON while the MCP server requires a compatible client. Neither is ergonomic for a SOC analyst at a terminal.

**Primary user:** SOC analyst doing alert triage and investigation at the command line.  
**Secondary users:** Agent developer registering and debugging agents; administrator managing API keys.

**Problem the CLI solves that MCP alone does not:**

- MCP is consumed by AI clients, not humans. A SOC analyst cannot run `calseta://alerts` in a terminal.
- MCP has no concept of a "current session" or configured credentials. Each MCP client connection is anonymous from the CLI's perspective.
- `calseta investigate <uuid>` is the highest-value operation: it fetches alert context, formats a prompt, and launches `claude` with the Calseta MCP server pre-wired. MCP cannot bootstrap itself.
- `calseta setup` configures Claude Code to talk to a Calseta instance. This is a one-time human action; MCP cannot orchestrate it.

### What the CLI Explicitly Does Not Do

- Does not replace the REST API for programmatic agent use (that is `httpx` + `cai_*` keys).
- Does not run agents. It can trigger agent invocations but does not execute agent logic.
- Does not manage the Calseta server process (start/stop Docker). That is `make lab`.
- Does not manage database migrations (`alembic upgrade head` stays separate).
- Does not implement a full admin panel. API key management is limited to create/list/revoke for bootstrapping.

---

## 2. Command Structure

### Design Principles

- Verb-noun pattern throughout.
- Short-circuit defaults: `calseta alerts list` shows open enriched alerts first, no flags required.
- Every command that prints structured data supports `--json` and `--quiet`.
- UUIDs can be abbreviated to 8 characters when unambiguous (like Git short SHAs) — the CLI resolves them.

### Full Command Tree

```
calseta
├── login                                   # Prompt for URL + key, write ~/.calseta/config.toml
├── setup                                   # Write MCP config + CLAUDE.md for Claude Code
├── status                                  # Show connection status, instance version, queue depth
│
├── alerts
│   ├── list [flags]                        # List alerts with severity-aware table
│   ├── inspect <uuid>                      # Full alert detail: indicators, enrichments, findings
│   ├── findings list <uuid>                # List agent findings on an alert
│   ├── findings post <uuid>                # Post a manual finding (analyst note)
│   └── close <uuid>                        # Close alert with classification prompt
│
├── queue
│   ├── list [flags]                        # View unassigned enriched alert queue
│   ├── depth                               # Single integer output: how many alerts are waiting
│   └── dashboard                           # Live queue depth, agent counts, costs MTD
│
├── agents
│   ├── list [flags]                        # List registered agent registrations
│   ├── inspect <uuid>                      # Agent detail: capabilities, status, recent invocations
│   ├── register                            # Interactive wizard: create AgentRegistration + cak_* key
│   └── pause/resume/terminate <uuid>       # Lifecycle management
│
├── workflows
│   ├── list [flags]                        # Workflow catalog with approval mode
│   ├── inspect <uuid>                      # Full workflow with code and run history
│   └── run <uuid>                          # Execute workflow with required args prompt
│
├── kb
│   ├── search <query>                      # Full-text search across KB pages
│   ├── list [flags]                        # List KB pages by folder
│   └── show <slug>                         # Print KB page content
│
├── enrichments
│   └── lookup <type> <value>               # On-demand enrichment: ip, domain, hash, email, url
│
├── keys
│   ├── create                              # Create cai_* API key (prompted for scopes)
│   ├── list                                # List keys (prefix + scopes, never full key)
│   └── revoke <uuid>                       # Revoke a key
│
└── investigate <alert-uuid>               # POWER COMMAND: fetch context, launch claude
```

### Flag Conventions

All list commands share:
- `--status <value>` — filter by status (Open, Triaging, Escalated, Closed)
- `--severity <value>` — filter by severity (Critical, High, Medium, Low)
- `--source <name>` — filter by source name
- `--limit <n>` — max results (default 25)
- `--json` — output raw JSON instead of table
- `--quiet` — print only UUIDs, one per line (pipeline-friendly)

`calseta investigate` additional flags:
- `--no-mcp` — do not pre-wire MCP server; pass alert context as text prompt only
- `--dry-run` — print the prompt that would be sent without launching `claude`
- `--model <model-id>` — override the Claude model

---

## 3. Claude Code Integration Design

### `calseta setup` — Exact Behavior

1. Read config from `~/.calseta/config.toml` or `CALSETA_API_URL` + `CALSETA_API_KEY` env vars
2. Validate connectivity: `GET /v1/metrics/summary`
3. Write `.claude/settings.json` (project-level) with MCP server entry:

```json
{
  "mcpServers": {
    "calseta": {
      "type": "sse",
      "url": "<CALSETA_API_URL>/mcp/sse",
      "headers": {
        "Authorization": "Bearer <CALSETA_API_KEY>"
      }
    }
  }
}
```

4. Write `CLAUDE.md` in current working directory (see Section 3a below)
5. If either file already exists, merge/append with delimited markers — never clobber

### 3a. Generated CLAUDE.md (Full Draft)

```markdown
# Calseta — SOC Investigation Reference

This workspace is connected to a Calseta instance via MCP.
Calseta is a security data platform: it ingests alerts, enriches indicators,
and exposes context for AI-assisted investigation.

---

## MCP Tools Available

**`search_alerts`** — Find alerts matching filter criteria.
```json
search_alerts(status="Open", severity="Critical,High", page_size=20)
```
Valid status values: `Open`, `Triaging`, `Escalated`, `Closed`
Valid severity values: `Pending`, `Informational`, `Low`, `Medium`, `High`, `Critical`

**`post_alert_finding`** — Post an analysis finding to an alert.
```json
post_alert_finding(
  alert_uuid="<uuid>",
  summary="Detailed analysis...",
  confidence="high",
  agent_name="claude-code-analyst",
  recommended_action="Isolate host immediately."
)
```

**`update_alert_status`** — Update alert status.
```json
update_alert_status(alert_uuid="<uuid>", status="Closed",
  close_classification="True Positive - Suspicious Activity")
```

**`execute_workflow`** — Trigger a response workflow.
```json
execute_workflow(
  workflow_uuid="<uuid>",
  indicator_type="ip",
  indicator_value="1.2.3.4",
  alert_uuid="<uuid>",
  reason="Confirmed C2 beacon",
  confidence=0.9
)
```

**`enrich_indicator`** — On-demand enrichment for an IOC.
```json
enrich_indicator(indicator_type="ip", indicator_value="1.2.3.4")
```
Valid indicator types: `ip`, `domain`, `hash_md5`, `hash_sha256`, `hash_sha1`, `email`, `url`, `hostname`

**`search_detection_rules`** — Find rules by name, MITRE, or source.

---

## MCP Resources Available

| Resource URI | What it returns |
|---|---|
| `calseta://alerts` | Recent 50 alerts (compact) |
| `calseta://alerts/{uuid}` | Full alert with indicators + context |
| `calseta://alerts/{uuid}/context` | Context documents applicable to alert |
| `calseta://alerts/{uuid}/activity` | Activity log (newest first) |
| `calseta://workflows` | Workflow catalog |
| `calseta://workflows/{uuid}` | Full workflow with code |
| `calseta://detection-rules` | Rule catalog with MITRE mappings |
| `calseta://enrichments/{type}/{value}` | On-demand enrichment (cache-first) |
| `calseta://metrics/summary` | Last 30 days SOC health snapshot |

---

## Alert Data Model

```
Alert
├── uuid, title, severity, status, enrichment_status
├── source_name       — which SIEM produced this ("sentinel", "elastic", "splunk")
├── occurred_at       — when the event happened (source time)
├── malice            — worst malice of all indicators, or manual override
├── indicators[]      — extracted IOCs (type, value, malice, enrichment_results)
├── detection_rule    — matched rule with MITRE mappings
├── context_documents[] — applicable runbooks/SOPs
└── agent_findings[]  — analysis results from AI agents
```

## Enum Reference

```
AlertStatus:   Open | Triaging | Escalated | Closed
AlertSeverity: Pending | Informational | Low | Medium | High | Critical
MaliceLevel:   Pending | Benign | Suspicious | Malicious
FindingConfidence: low | medium | high
WorkflowApprovalMode: never | agent_only | always
```

## Common Investigation Patterns

**Triage an open alert:**
1. Read `calseta://alerts` — scan for Critical/High, Enriched status
2. Read `calseta://alerts/{uuid}` for the most suspicious one
3. Call `enrich_indicator` for any Pending/Suspicious IOCs
4. Read `calseta://alerts/{uuid}/context` for applicable runbooks
5. Call `post_alert_finding` with your verdict
6. Call `update_alert_status` to close or escalate

**Check for prior activity:**
1. Read `calseta://alerts/{uuid}/activity` for past agent findings
2. Use `search_alerts` with shared indicator values to find related alerts

**Respond to confirmed threat:**
1. Read `calseta://workflows` — find workflows matching indicator types
2. Check `approval_mode`: `never` executes immediately, others go to approval queue
3. Call `execute_workflow` with indicator + reason + confidence
```

### `calseta investigate <uuid>` — Exact Behavior

1. Fetch in parallel: alert detail, context docs, active workflows
2. Build investigation prompt using `build_prompt()` pattern from `examples/agents/investigate_alert.py`
3. Prepend investigation directive instructing Claude to use MCP tools and post findings
4. Check for `claude` binary via `shutil.which("claude")` — fail with install instructions if absent
5. Launch: `claude --mcp-config .claude/settings.json -p "<prompt>"`
6. Fall back to clipboard copy if MCP config doesn't exist (suggest running `calseta setup`)

---

## 4. Output Format

**Default:** `rich` library tables with colored severity/status badges.

```
 SEV       STATUS     UUID      TITLE                             SOURCE    AGE
 CRITICAL  Open       a1b2c3d4  Malware Detected - LSASS Dump     sentinel  2h ago
 HIGH      Triaging   e5f6g7h8  Impossible Travel - john@corp     entra     47m ago
```

- `--json`: raw API response, pretty-printed, to stdout
- `--quiet`: UUIDs only, one per line — for shell pipelines
- Errors always to stderr, exit code 1

---

## 5. Configuration

**Priority order:** CLI flags > env vars (`CALSETA_API_URL`, `CALSETA_API_KEY`) > `~/.calseta/config.toml` > default (`http://localhost:8000`)

**`~/.calseta/config.toml`:**
```toml
[default]
api_url = "https://calseta.corp.example.com"
api_key = "cai_xxxxxxxxxxxxxxxxxxxx"

[staging]
api_url = "https://calseta-staging.corp.example.com"
api_key = "cai_yyyyyyyyyyyyyyyyyyyy"
```

Named profiles via `calseta --profile staging alerts list`.

---

## 6. Distribution

**Recommendation: `pip install calseta-cli`**

Rationale: Python is already present in most SOC environments. PyPI gives versioning, internal mirror support (Artifactory/Nexus), and air-gapped install via wheels. Standalone binary (PyInstaller) is 50–80 MB with notarization overhead. Homebrew is macOS-only.

Supplement with Docker: `docker run --rm -e CALSETA_API_KEY ghcr.io/calseta/cli:latest alerts list` for locked-down environments.

Package name: `calseta-cli` (reserve `calseta` for the future SDK).

---

## 7. Relationship to Agent SDK

Separate packages, shared transport layer. For MVP: include the HTTP client directly in `calseta-cli/client.py`. Extract to `calseta-sdk` only when an agent developer need is validated.

---

## 8. What Already Exists (Reusable)

| File | What to reuse |
|---|---|
| `examples/agents/investigate_alert.py` | `RESTDataSource` class → `client.py`; `build_prompt()` → `investigate.py`; `select_alert()` → alerts sorting |
| `app/auth/scopes.py` | Scope enum values → `enums.py` (copy, don't import) |
| `app/schemas/alert.py` | Status/Severity/CloseClassification enum values |
| `app/mcp/CONTEXT.md` | Source material for generated CLAUDE.md tool reference |
| `app/api/v1/AGENTS.md` | Route map for constructing all CLI API calls |

---

## 9. MVP Scope — Sprint 1 (7 Commands)

| Priority | Command | Rationale |
|---|---|---|
| 1 | `calseta login` | Required before anything else. No dependencies. |
| 2 | `calseta status` | Validates connection. Instant feedback. |
| 3 | `calseta alerts list` | Most common analyst operation. Exercises output layer. |
| 4 | `calseta alerts inspect <uuid>` | Unlocks triage without a browser. |
| 5 | `calseta setup` | Claude Code integration hook. Writes MCP config + CLAUDE.md. |
| 6 | `calseta investigate <uuid>` | The anchor command. Validates the full loop. |
| 7 | `calseta enrichments lookup <type> <value>` | High-value standalone IOC check. |

**Deferred to Sprint 2:** queue commands, agents commands, workflows run, kb commands, keys commands, multi-profile support, Docker image.

### MVP Package Structure

```
cli/
├── pyproject.toml
├── README.md
└── calseta_cli/
    ├── __init__.py
    ├── main.py          # Typer app root
    ├── config.py        # Config loading: env > toml > default
    ├── client.py        # httpx client (adapted from RESTDataSource)
    ├── output.py        # rich tables, severity colors, --json/--quiet
    ├── enums.py         # AlertStatus, AlertSeverity, Scope (copied values)
    └── commands/
        ├── login.py
        ├── status.py
        ├── alerts.py
        ├── setup.py
        └── investigate.py
```

**Dependencies:**
```toml
dependencies = [
    "httpx>=0.28",
    "typer>=0.12",
    "rich>=13",
    "tomli>=2.0; python_version < '3.11'",
]
```

No `anthropic` SDK — the CLI calls the `claude` binary as a subprocess. No async at top level — use `httpx` sync client wrapped with `asyncio.run()` only where needed.

# Implementation prompt
implementation prompt:

  ---
  You are working in the Calseta codebase at
  /Users/jorgecastro/Library/Mobile Documents/com~apple
  ~CloudDocs/Desktop/Calseta/Dev/calseta on branch
  feat/calseta-v2.

  Your task: Implement the MVP sprint of the calseta
  CLI. 7 commands. No backend changes.

  Read this first — completely:
  - docs/plans/calseta-cli.md — the full design
  proposal. Follow it exactly. Do not invent structure.

  Then read these before writing any code:
  - examples/agents/investigate_alert.py — the
  RESTDataSource class and build_prompt() function are
  the foundation of client.py and investigate.py. Read
  carefully.
  - app/auth/scopes.py — copy the scope enum values
  into calseta_cli/enums.py
  - app/schemas/alert.py — copy AlertStatus,
  AlertSeverity, CloseClassification enum values
  - app/mcp/CONTEXT.md — source material for the
  generated CLAUDE.md tool reference
  - app/api/v1/AGENTS.md — route map for every API call
   you'll make

  ---
  What to build

  Create the cli/ directory in the repo root with this
  exact structure:

  cli/
  ├── pyproject.toml
  ├── README.md
  └── calseta_cli/
      ├── __init__.py
      ├── main.py
      ├── config.py
      ├── client.py
      ├── output.py
      ├── enums.py
      └── commands/
          ├── __init__.py
          ├── login.py
          ├── status.py
          ├── alerts.py
          ├── setup.py
          └── investigate.py

  ---
  Implementation spec per file

  pyproject.toml
  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"

  [project]
  name = "calseta-cli"
  version = "0.1.0"
  description = "Terminal interface and Claude Code
  integration for Calseta"
  requires-python = ">=3.12"
  dependencies = [
      "httpx>=0.28",
      "typer>=0.12",
      "rich>=13",
      "tomli>=2.0; python_version < '3.11'",
  ]

  [project.scripts]
  calseta = "calseta_cli.main:app"

  calseta_cli/enums.py
  Copy (do not import) the enum values from
  app/auth/scopes.py and app/schemas/alert.py:
  - AlertStatus, AlertSeverity,
  AlertCloseClassification, Scope
  These are referenced in flag validation and the keys
  create scopes multiselect.

  calseta_cli/config.py
  Handles config resolution in priority order: env vars
   > ~/.calseta/config.toml > default.
  @dataclass
  class CalsetaConfig:
      api_url: str
      api_key: str

  def load_config(profile: str = "default") ->
  CalsetaConfig:
      # 1. Check CALSETA_API_URL + CALSETA_API_KEY env
  vars
      # 2. Fall back to ~/.calseta/config.toml
  [profile] section
      # 3. Default api_url = "http://localhost:8000",
  api_key = ""
      ...

  def save_config(api_url: str, api_key: str, profile:
  str = "default") -> None:
      # Write/update ~/.calseta/config.toml
      ...
  Use tomllib (stdlib 3.11+) or tomli for reading. Use
  tomli-w for writing OR just format the TOML manually
  (it's simple enough).

  calseta_cli/client.py
  Adapt RESTDataSource from
  examples/agents/investigate_alert.py. Use httpx sync
  client. Methods needed for MVP:
  - get_metrics_summary() → GET /v1/metrics/summary
  - list_alerts(status, severity, source, limit, page)
  → GET /v1/alerts
  - get_alert(uuid) → GET /v1/alerts/{uuid}
  - get_alert_context(uuid) → GET
  /v1/alerts/{uuid}/context
  - list_workflows(page_size) → GET /v1/workflows
  - enrich_indicator(type, value) → POST
  /v1/enrichments/{type}/{value}

  Constructor takes CalsetaConfig. Raises
  CalsetaAPIError(status_code, message) on non-2xx.
  Never prints — returns data or raises.

  calseta_cli/output.py
  All rich rendering lives here. Nothing in command
  files imports rich directly.
  def print_alert_table(alerts: list[dict], quiet: bool
   = False, as_json: bool = False) -> None: ...
  def print_alert_detail(alert: dict) -> None: ...
  def print_enrichment(result: dict) -> None: ...
  def print_status(metrics: dict, config:
  CalsetaConfig) -> None: ...
  def severity_badge(severity: str) -> str: ...  #
  returns colored rich markup
  def status_badge(status: str) -> str: ...

  Severity colors: Critical=red bold, High=orange1,
  Medium=yellow, Low=blue, Informational=dim,
  Pending=dim italic.

  Alert table columns: SEV | STATUS | UUID[:8] |
  TITLE[:52] | SOURCE | AGE
  - AGE: human-readable relative time (2h ago, 47m ago,
   just now) computed from occurred_at
  - TITLE truncated to 52 chars with ellipsis if longer

  calseta_cli/main.py
  import typer
  from calseta_cli.commands import login, status,
  alerts, setup, investigate

  app = typer.Typer(name="calseta", help="Calseta SOC
  platform CLI")
  app.add_typer(alerts.app, name="alerts")
  app.command()(login.login)
  app.command()(status.status)
  app.command()(setup.setup)
  app.command()(investigate.investigate)

  Global option: --profile TEXT with default "default".
   Pass profile down via typer callback or context.

  calseta_cli/commands/login.py
  def login(
      url: str = typer.Option(None, prompt="Calseta
  URL", default="http://localhost:8000"),
      key: str = typer.Option(None, prompt="API key
  (cai_*)", hide_input=True),
      profile: str = typer.Option("default"),
  ):
      # Validate: GET /v1/metrics/summary with provided
   creds
      # On success: save_config(), print confirmation
      # On failure: print error, exit 1

  calseta_cli/commands/status.py
  def status(profile: str = "default"):
      config = load_config(profile)
      client = CalsetaClient(config)
      metrics = client.get_metrics_summary()
      output.print_status(metrics, config)

  calseta_cli/commands/alerts.py
  app = typer.Typer(help="Alert management")

  @app.command("list")
  def list_alerts(
      status: Optional[str] = typer.Option(None),
      severity: Optional[str] = typer.Option(None),
      source: Optional[str] = typer.Option(None),
      limit: int = typer.Option(25),
      json: bool = typer.Option(False, "--json"),
      quiet: bool = typer.Option(False, "--quiet"),
      profile: str = "default",
  ): ...

  @app.command("inspect")
  def inspect_alert(uuid: str, json: bool = False,
  profile: str = "default"): ...

  Default for list: --status Open,Triaging,Escalated
  (active alerts). Sort by severity descending (use
  SEVERITY_ORDER from enums).

  calseta_cli/commands/setup.py

  This is the most important command. Write it
  carefully.

  def setup(profile: str = "default"):
      config = load_config(profile)

      # 1. Validate connectivity
      client = CalsetaClient(config)
      try:
          metrics = client.get_metrics_summary()
      except CalsetaAPIError as e:
          typer.echo(f"Error: Cannot connect to Calseta
   at {config.api_url}", err=True)
          raise typer.Exit(1)

      # 2. Write .claude/settings.json (project-level,
  merge-safe)
      _write_mcp_config(config)

      # 3. Write CLAUDE.md (current dir, append-safe
  with markers)
      _write_claude_md(config)

      # 4. Print confirmation

  _write_mcp_config(config):
  - Read .claude/settings.json if it exists (may have
  other MCP servers)
  - Set data["mcpServers"]["calseta"] = { "type":
  "sse", "url": f"{config.api_url}/mcp/sse", "headers":
   {"Authorization": f"Bearer {config.api_key}"} }
  - Write back (create .claude/ dir if needed)

  _write_claude_md(config):
  - The full CLAUDE.md text is in
  docs/plans/calseta-cli.md section 3a — hardcode it as
   a string in this function
  - If CLAUDE.md does not exist: write it
  - If it exists and contains <!-- calseta-start -->
  marker: replace between markers
  - If it exists without markers: append the Calseta
  section with markers

  calseta_cli/commands/investigate.py

  def investigate(
      alert_uuid: str,
      no_mcp: bool = typer.Option(False, "--no-mcp"),
      dry_run: bool = typer.Option(False, "--dry-run"),
      model: Optional[str] = typer.Option(None,
  "--model"),
      profile: str = "default",
  ):
      config = load_config(profile)
      client = CalsetaClient(config)

      # 1. Fetch context in parallel (use
  concurrent.futures or sequential httpx calls)
      alert = client.get_alert(alert_uuid)
      context_docs =
  client.get_alert_context(alert_uuid)
      workflows = client.list_workflows(page_size=50)

      # 2. Build prompt — adapt build_prompt() from
  investigate_alert.py
      prompt = _build_investigation_prompt(alert,
  context_docs, workflows)

      # 3. Dry run: print and exit
      if dry_run:
          typer.echo(prompt)
          return

      # 4. Check for claude binary
      import shutil
      if not shutil.which("claude"):
          typer.echo("claude CLI not found. Install
  from https://claude.ai/download", err=True)
          # Copy to clipboard as fallback
          _copy_to_clipboard(prompt)
          typer.echo("Prompt copied to clipboard.")
          return

      # 5. Build claude command
      cmd = ["claude"]
      if not no_mcp and
  Path(".claude/settings.json").exists():
          cmd += ["--mcp-config",
  ".claude/settings.json"]
      elif not no_mcp:
          typer.echo("Warning: .claude/settings.json
  not found. Run `calseta setup` first.", err=True)
      if model:
          cmd += ["--model", model]
      cmd += ["-p", prompt]

      # 6. Launch
      import subprocess
      subprocess.run(cmd)

  _build_investigation_prompt(): adapt the
  format_alert_context() / build_prompt() pattern from
  investigate_alert.py. Include: alert header (title,
  severity, status, source, occurred_at), indicators
  table (type, value, malice, enrichment summary),
  detection rule (name, MITRE), context docs (title +
  first 200 chars), relevant workflows (name +
  description). Prepend the investigation directive
  from the design doc.

  _copy_to_clipboard(): try pbcopy (macOS), then xclip,
   then xsel, then print a warning that none are
  available.

  ---
  Commands that print tables must handle --json and
  --quiet

  - --json: import json;
  typer.echo(json.dumps(raw_api_response, indent=2))
  - --quiet: print only UUIDs, one per line
  - Default: rich table via output.py

  Error handling pattern

  try:
      result = client.some_call()
  except CalsetaAPIError as e:
      typer.echo(f"Error: {e.message}", err=True)
      typer.echo(f"  {e.method} {e.path} →
  {e.status_code}", err=True)
      raise typer.Exit(1)
  except httpx.ConnectError:
      typer.echo(f"Error: Cannot connect to
  {config.api_url}", err=True)
      typer.echo("  Is Calseta running? Try: make lab",
   err=True)
      raise typer.Exit(1)

  ---
  README.md

  Write a real README for cli/README.md:
  - What it is (one sentence)
  - Install: pip install calseta-cli (or pip install -e
   . from monorepo)
  - Quick start: login → setup → investigate
  - All 7 MVP commands with one-line descriptions and
  example invocations
  - Claude Code integration section: what calseta setup
   does, what the generated CLAUDE.md gives you
  - Pipeline examples: calseta alerts list --quiet
  --severity Critical | xargs -I{} calseta investigate
  {}

  ---
  After building

  1. Install locally and verify: cd cli && pip install
  -e . && calseta --help
  2. Verify all command help text works: calseta alerts
   --help, calseta investigate --help
  3. Run calseta login --url http://localhost:8000
  --key <test-key> against a running instance if
  available; if not, verify the config read/write logic
   manually
  4. cd cli && python -m pytest tests/ -v if you write
  tests; at minimum verify no import errors
  5. Commit: feat: calseta CLI MVP — login, status,
  alerts, setup, investigate, enrichments
  6. Report back: any API response shapes that differed
   from what the design doc assumed, anything deferred
  and why