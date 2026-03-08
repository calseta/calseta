#!/usr/bin/env python3
"""
Validation Case Study Runner.

Runs agents (Naive / Calseta) against all 5 fixture scenarios, 3 runs each.
Supports both Anthropic (Claude) and OpenAI (GPT-4o) models.

Prerequisites:
  - A running Calseta instance (docker compose up)
  - The 5 fixture alerts ingested into Calseta (see ingest_fixtures() helper)
  - ANTHROPIC_API_KEY set for Claude agents
  - OPENAI_API_KEY set for OpenAI agents
  - VIRUSTOTAL_API_KEY and ABUSEIPDB_API_KEY set for naive agent enrichment
  - CALSETA_API_KEY set for the Calseta agents

Usage:
    # Ingest fixtures first, then run the study
    python run_study.py --ingest --run

    # Just run the study (fixtures already ingested)
    python run_study.py --run

    # Run with specific model provider
    python run_study.py --run --models claude
    python run_study.py --run --models openai
    python run_study.py --run --models all

    # Just ingest fixtures
    python run_study.py --ingest

Environment variables:
    ANTHROPIC_API_KEY       - Required for Claude agents
    OPENAI_API_KEY          - Required for OpenAI agents
    VIRUSTOTAL_API_KEY      - Required for naive agent enrichment
    ABUSEIPDB_API_KEY       - Required for naive agent enrichment
    CALSETA_BASE_URL        - Calseta API URL (default: http://localhost:8000)
    CALSETA_API_KEY         - Calseta API key (cai_... format)
    CLAUDE_MODEL            - Claude model (default: claude-sonnet-4-20250514)
    OPENAI_MODEL            - OpenAI model (default: gpt-4o)
    RUNS_PER_SCENARIO       - Number of runs per scenario (default: 3)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# Add the case_study directory to path for imports
CASE_STUDY_DIR = Path(__file__).parent
sys.path.insert(0, str(CASE_STUDY_DIR))

from calseta_agent import CalsetaAgent  # noqa: E402
from naive_agent import AgentMetrics, NaiveAgent  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FIXTURES_DIR = CASE_STUDY_DIR / "fixtures"
RESULTS_DIR = CASE_STUDY_DIR / "results"

# Fixture metadata: filename, source_name, scenario label
SCENARIOS = [
    {
        "fixture": "01_sentinel_brute_force_tor.json",
        "source": "sentinel",
        "label": "Sentinel: Brute Force from TOR",
        "description": "Account compromise via brute force from TOR exit node",
    },
    {
        "fixture": "02_elastic_malware_hash.json",
        "source": "elastic",
        "label": "Elastic: Known Malware Hash",
        "description": "Known malicious executable detected on endpoint",
    },
    {
        "fixture": "03_splunk_anomalous_data_transfer.json",
        "source": "splunk",
        "label": "Splunk: Anomalous Data Transfer",
        "description": "Anomalous outbound data exfiltration detected",
    },
    {
        "fixture": "04_sentinel_impossible_travel.json",
        "source": "sentinel",
        "label": "Sentinel: Impossible Travel",
        "description": "Impossible travel sign-in for privileged account",
    },
    {
        "fixture": "05_elastic_suspicious_powershell.json",
        "source": "elastic",
        "label": "Elastic: Suspicious PowerShell",
        "description": "Encoded PowerShell command with C2 beacon",
    },
]


def load_env() -> dict[str, str]:
    """Load environment variables, with .env file fallback."""
    env: dict[str, str] = {}

    # Try loading .env file from case_study directory or repo root
    for env_path in [CASE_STUDY_DIR / ".env", CASE_STUDY_DIR.parent.parent / ".env"]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        env[key.strip()] = val.strip().strip("\"'")

    # Environment variables override .env file
    for key in [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "VIRUSTOTAL_API_KEY",
        "ABUSEIPDB_API_KEY",
        "CALSETA_BASE_URL",
        "CALSETA_API_KEY",
        "CLAUDE_MODEL",
        "OPENAI_MODEL",
        "RUNS_PER_SCENARIO",
    ]:
        val = os.environ.get(key)
        if val:
            env[key] = val

    return env


# ---------------------------------------------------------------------------
# Fixture ingestion
# ---------------------------------------------------------------------------

def ingest_fixtures(
    base_url: str, api_key: str
) -> dict[str, str]:
    """
    Ingest all 5 fixture alerts into a running Calseta instance.

    Returns a mapping of fixture filename -> alert UUID.
    """
    print("\n=== Ingesting fixtures into Calseta ===\n")

    uuids: dict[str, str] = {}
    client = httpx.Client(
        timeout=30.0,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )

    for scenario in SCENARIOS:
        fixture_path = FIXTURES_DIR / scenario["fixture"]
        with open(fixture_path) as f:
            payload = json.load(f)

        source = scenario["source"]
        print(f"  Ingesting {scenario['label']}... ", end="", flush=True)

        try:
            resp = client.post(
                f"{base_url}/v1/ingest/{source}",
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

            # Extract UUID from response
            alert_uuid = data.get("data", {}).get("uuid") or data.get("uuid", "")
            uuids[scenario["fixture"]] = alert_uuid
            print(f"OK -> {alert_uuid}")

        except httpx.HTTPStatusError as exc:
            print(f"FAILED (HTTP {exc.response.status_code})")
            print(f"    Response: {exc.response.text[:200]}")
        except Exception as exc:
            print(f"FAILED ({exc})")

    client.close()

    # Save UUIDs for later use
    uuid_file = RESULTS_DIR / "alert_uuids.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(uuid_file, "w") as f:
        json.dump(uuids, f, indent=2)
    print(f"\n  Alert UUIDs saved to {uuid_file}")

    # Wait for enrichment to complete
    print("\n  Waiting 15 seconds for enrichment pipeline to complete...")
    import time
    time.sleep(15)

    return uuids


def load_uuids() -> dict[str, str]:
    """Load previously saved alert UUIDs."""
    uuid_file = RESULTS_DIR / "alert_uuids.json"
    if not uuid_file.exists():
        print(f"ERROR: {uuid_file} not found. Run with --ingest first.")
        sys.exit(1)
    with open(uuid_file) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Study execution
# ---------------------------------------------------------------------------

def _model_short_name(model: str) -> str:
    """Return a short display name for a model identifier."""
    if "claude" in model.lower():
        return "claude"
    if "gpt" in model.lower():
        return "gpt4o"
    return model.split("-")[0]


def _build_agents(
    env: dict[str, str], models_flag: str
) -> list[tuple[str, Any, str, str]]:
    """
    Build a list of (label, agent, approach, model_name) tuples based on
    the --models flag.

    Returns pairs of (naive, calseta) agents for each requested provider.
    """
    agents: list[tuple[str, Any, str, str]] = []

    vt_key = env.get("VIRUSTOTAL_API_KEY", "")
    abuseipdb_key = env.get("ABUSEIPDB_API_KEY", "")
    calseta_url = env.get("CALSETA_BASE_URL", "http://localhost:8000")
    calseta_key = env.get("CALSETA_API_KEY", "")

    run_claude = models_flag in ("claude", "all")
    run_openai = models_flag in ("openai", "all")

    if run_claude:
        anthropic_key = env.get("ANTHROPIC_API_KEY", "")
        if not anthropic_key:
            print("ERROR: ANTHROPIC_API_KEY is required for Claude models")
            sys.exit(1)
        claude_model = env.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

        agents.append((
            "naive",
            NaiveAgent(
                anthropic_api_key=anthropic_key,
                virustotal_api_key=vt_key,
                abuseipdb_api_key=abuseipdb_key,
                model=claude_model,
            ),
            "naive",
            claude_model,
        ))
        agents.append((
            "calseta",
            CalsetaAgent(
                anthropic_api_key=anthropic_key,
                calseta_base_url=calseta_url,
                calseta_api_key=calseta_key,
                model=claude_model,
            ),
            "calseta",
            claude_model,
        ))

    if run_openai:
        from openai_agent import OpenAICalsetaAgent, OpenAINaiveAgent  # noqa: E402

        openai_key = env.get("OPENAI_API_KEY", "")
        if not openai_key:
            print("ERROR: OPENAI_API_KEY is required for OpenAI models")
            sys.exit(1)
        openai_model = env.get("OPENAI_MODEL", "gpt-4o")

        agents.append((
            "naive",
            OpenAINaiveAgent(
                openai_api_key=openai_key,
                virustotal_api_key=vt_key,
                abuseipdb_api_key=abuseipdb_key,
                model=openai_model,
            ),
            "naive",
            openai_model,
        ))
        agents.append((
            "calseta",
            OpenAICalsetaAgent(
                openai_api_key=openai_key,
                calseta_base_url=calseta_url,
                calseta_api_key=calseta_key,
                model=openai_model,
            ),
            "calseta",
            openai_model,
        ))

    return agents


async def run_study(env: dict[str, str], models_flag: str = "claude") -> None:
    """Run the full study: all agents, all scenarios, multiple runs."""
    runs_per = int(env.get("RUNS_PER_SCENARIO", "3"))

    # Load alert UUIDs (from previous ingest)
    uuids = load_uuids()

    # Build agent list based on --models flag
    agents = _build_agents(env, models_flag)
    if not agents:
        print("ERROR: No agents configured. Check API keys and --models flag.")
        sys.exit(1)

    # Prepare results CSV
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "raw_metrics.csv"
    findings_dir = RESULTS_DIR / "findings"
    findings_dir.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "timestamp",
        "scenario",
        "source",
        "approach",
        "run_number",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "tool_calls",
        "external_api_calls",
        "duration_seconds",
        "estimated_cost_usd",
        "model",
    ]

    # Load existing rows if CSV exists (to support incremental runs)
    rows: list[dict[str, Any]] = []
    if csv_path.exists():
        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for existing_row in reader:
                for key in ["input_tokens", "output_tokens", "total_tokens",
                            "tool_calls", "external_api_calls", "run_number"]:
                    existing_row[key] = int(existing_row.get(key, 0))
                for key in ["duration_seconds", "estimated_cost_usd"]:
                    existing_row[key] = float(existing_row.get(key, 0))
                rows.append(existing_row)
        print(f"  Loaded {len(rows)} existing rows from {csv_path}")

    total_runs = len(SCENARIOS) * len(agents) * runs_per
    run_count = 0

    # Summarize what we're about to run
    model_names = sorted(set(model for _, _, _, model in agents))
    print(f"\n=== Running validation study ===")
    print(f"  Models: {', '.join(model_names)}")
    print(f"  Approaches: naive, calseta")
    print(f"  Runs per scenario per agent: {runs_per}")
    print(f"  Total runs: {total_runs}")
    print()

    new_rows: list[dict[str, Any]] = []

    for scenario in SCENARIOS:
        fixture_path = FIXTURES_DIR / scenario["fixture"]
        with open(fixture_path) as f:
            raw_alert = json.load(f)

        alert_uuid = uuids.get(scenario["fixture"], "")

        print(f"--- {scenario['label']} ---")

        for _label, agent, approach, model_name in agents:
            model_short = _model_short_name(model_name)

            # Skip calseta agents if no UUID available
            if approach == "calseta" and not alert_uuid:
                print(f"  SKIPPING {model_short} calseta — no UUID for {scenario['fixture']}")
                continue

            for run_num in range(1, runs_per + 1):
                run_count += 1
                print(
                    f"  [{run_count}/{total_runs}] {model_short} {approach}, "
                    f"run {run_num}... ",
                    end="",
                    flush=True,
                )

                try:
                    if approach == "naive":
                        metrics = await agent.investigate(raw_alert, scenario["source"])
                    else:
                        metrics = await agent.investigate(alert_uuid)

                    print(
                        f"OK ({metrics.input_tokens} in / "
                        f"{metrics.output_tokens} out / "
                        f"{metrics.duration_seconds:.1f}s)"
                    )

                    row = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "scenario": scenario["label"],
                        "source": scenario["source"],
                        "approach": approach,
                        "run_number": run_num,
                        "input_tokens": metrics.input_tokens,
                        "output_tokens": metrics.output_tokens,
                        "total_tokens": metrics.total_tokens,
                        "tool_calls": metrics.tool_calls,
                        "external_api_calls": metrics.external_api_calls,
                        "duration_seconds": metrics.duration_seconds,
                        "estimated_cost_usd": metrics.estimated_cost_usd,
                        "model": model_name,
                    }
                    new_rows.append(row)

                    # Save finding text with model in filename
                    fixture_stem = scenario["fixture"].replace(".json", "")
                    finding_file = (
                        findings_dir
                        / f"{fixture_stem}_{approach}_{model_short}_run{run_num}.txt"
                    )
                    with open(finding_file, "w") as f:
                        f.write(metrics.finding)

                except Exception as exc:
                    print(f"FAILED ({exc})")

        print()

    # Merge new rows with existing
    rows.extend(new_rows)

    # Write CSV
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n=== Study complete ===")
    print(f"  Results written to {csv_path}")
    print(f"  Findings written to {findings_dir}/")
    print(f"  New runs completed: {len(new_rows)}/{total_runs}")
    print(f"  Total rows in CSV: {len(rows)}")

    # Print summary table
    _print_summary(rows)

    # Close all agents
    for _, agent, _, _ in agents:
        agent.close()


def _print_summary(rows: list[dict[str, Any]]) -> None:
    """Print a summary table comparing approaches, grouped by model."""
    from collections import defaultdict

    # Group by model, scenario, and approach
    groups: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for row in rows:
        model = row.get("model", "unknown")
        groups[model][row["scenario"]][row["approach"]].append(row)

    print("\n=== Summary (averages across runs) ===\n")
    print(
        f"{'Model':<15} {'Scenario':<35} {'Approach':<10} {'Input Tok':>10} "
        f"{'Output Tok':>10} {'Total Tok':>10} {'Tools':>6} "
        f"{'API Calls':>10} {'Time (s)':>9} {'Cost ($)':>10}"
    )
    print("-" * 145)

    for model in sorted(groups.keys()):
        model_short = _model_short_name(model)
        for scenario_label in dict.fromkeys(
            r["scenario"] for r in rows if r.get("model") == model
        ):
            for approach in ["naive", "calseta"]:
                runs = groups[model][scenario_label].get(approach, [])
                if not runs:
                    continue
                n = len(runs)
                avg = lambda key: sum(r[key] for r in runs) / n  # noqa: E731
                print(
                    f"{model_short:<15} {scenario_label:<35} {approach:<10} "
                    f"{avg('input_tokens'):>10.0f} "
                    f"{avg('output_tokens'):>10.0f} "
                    f"{avg('total_tokens'):>10.0f} "
                    f"{avg('tool_calls'):>6.1f} "
                    f"{avg('external_api_calls'):>10.1f} "
                    f"{avg('duration_seconds'):>9.1f} "
                    f"{avg('estimated_cost_usd'):>10.6f}"
                )
            print()

    # Overall averages per model
    models = sorted(set(r.get("model", "unknown") for r in rows))
    for model in models:
        model_short = _model_short_name(model)
        naive_rows = [r for r in rows if r["approach"] == "naive" and r.get("model") == model]
        calseta_rows = [r for r in rows if r["approach"] == "calseta" and r.get("model") == model]

        if not naive_rows or not calseta_rows:
            continue

        avg_naive_in = sum(r["input_tokens"] for r in naive_rows) / len(naive_rows)
        avg_calseta_in = sum(r["input_tokens"] for r in calseta_rows) / len(calseta_rows)
        avg_naive_total = sum(r["total_tokens"] for r in naive_rows) / len(naive_rows)
        avg_calseta_total = sum(r["total_tokens"] for r in calseta_rows) / len(calseta_rows)
        avg_naive_cost = sum(r["estimated_cost_usd"] for r in naive_rows) / len(naive_rows)
        avg_calseta_cost = sum(r["estimated_cost_usd"] for r in calseta_rows) / len(calseta_rows)

        input_reduction = (1 - avg_calseta_in / avg_naive_in) * 100 if avg_naive_in > 0 else 0
        total_reduction = (1 - avg_calseta_total / avg_naive_total) * 100 if avg_naive_total > 0 else 0
        cost_reduction = (1 - avg_calseta_cost / avg_naive_cost) * 100 if avg_naive_cost > 0 else 0

        print(f"=== Overall — {model_short} ({model}) ===")
        print(f"  Avg input tokens  — Naive: {avg_naive_in:.0f}, Calseta: {avg_calseta_in:.0f} ({input_reduction:+.1f}%)")
        print(f"  Avg total tokens  — Naive: {avg_naive_total:.0f}, Calseta: {avg_calseta_total:.0f} ({total_reduction:+.1f}%)")
        print(f"  Avg cost per alert — Naive: ${avg_naive_cost:.6f}, Calseta: ${avg_calseta_cost:.6f} ({cost_reduction:+.1f}%)")
        print(f"  Target: >=50% input token reduction. Result: {input_reduction:.1f}%")

        if input_reduction >= 50:
            print("  PASS: Input token reduction target met.")
        else:
            print("  FAIL: Input token reduction target NOT met.")
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calseta Validation Case Study Runner"
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Ingest fixture alerts into a running Calseta instance",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run the validation study (requires fixtures to be ingested first)",
    )
    parser.add_argument(
        "--models",
        choices=["claude", "openai", "all"],
        default="claude",
        help="Which model provider(s) to run (default: claude)",
    )
    args = parser.parse_args()

    if not args.ingest and not args.run:
        parser.print_help()
        print("\nSpecify --ingest, --run, or both (--ingest --run).")
        sys.exit(1)

    env = load_env()

    if args.ingest:
        calseta_url = env.get("CALSETA_BASE_URL", "http://localhost:8000")
        calseta_key = env.get("CALSETA_API_KEY", "")
        if not calseta_key:
            print("ERROR: CALSETA_API_KEY is required for ingestion")
            sys.exit(1)
        ingest_fixtures(calseta_url, calseta_key)

    if args.run:
        asyncio.run(run_study(env, models_flag=args.models))


if __name__ == "__main__":
    main()
