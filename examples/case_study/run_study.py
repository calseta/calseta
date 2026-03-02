#!/usr/bin/env python3
"""
Validation Case Study Runner.

Runs both agents (Naive / Calseta) against all 5 fixture scenarios, 3 runs each
(30 total runs). Captures metrics and outputs raw results to results/raw_metrics.csv.

Prerequisites:
  - A running Calseta AI instance (docker compose up)
  - The 5 fixture alerts ingested into Calseta (see ingest_fixtures() helper)
  - ANTHROPIC_API_KEY set in environment or .env
  - VIRUSTOTAL_API_KEY and ABUSEIPDB_API_KEY set for naive agent enrichment
  - CALSETA_API_KEY set for the Calseta agent

Usage:
    # Ingest fixtures first, then run the study
    python run_study.py --ingest --run

    # Just run the study (fixtures already ingested)
    python run_study.py --run

    # Just ingest fixtures
    python run_study.py --ingest

Environment variables:
    ANTHROPIC_API_KEY       - Required for both agents
    VIRUSTOTAL_API_KEY      - Required for naive agent enrichment
    ABUSEIPDB_API_KEY       - Required for naive agent enrichment
    CALSETA_BASE_URL        - Calseta API URL (default: http://localhost:8000)
    CALSETA_API_KEY         - Calseta API key (cai_... format)
    CLAUDE_MODEL            - Model to use (default: claude-sonnet-4-20250514)
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
from naive_agent import NaiveAgent  # noqa: E402


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
        "VIRUSTOTAL_API_KEY",
        "ABUSEIPDB_API_KEY",
        "CALSETA_BASE_URL",
        "CALSETA_API_KEY",
        "CLAUDE_MODEL",
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

async def run_study(env: dict[str, str]) -> None:
    """Run the full study: both agents, all scenarios, multiple runs."""
    anthropic_key = env.get("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        print("ERROR: ANTHROPIC_API_KEY is required")
        sys.exit(1)

    vt_key = env.get("VIRUSTOTAL_API_KEY", "")
    abuseipdb_key = env.get("ABUSEIPDB_API_KEY", "")
    calseta_url = env.get("CALSETA_BASE_URL", "http://localhost:8000")
    calseta_key = env.get("CALSETA_API_KEY", "")
    model = env.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    runs_per = int(env.get("RUNS_PER_SCENARIO", "3"))

    # Load alert UUIDs (from previous ingest)
    uuids = load_uuids()

    # Initialize agents
    naive = NaiveAgent(
        anthropic_api_key=anthropic_key,
        virustotal_api_key=vt_key,
        abuseipdb_api_key=abuseipdb_key,
        model=model,
    )
    calseta = CalsetaAgent(
        anthropic_api_key=anthropic_key,
        calseta_base_url=calseta_url,
        calseta_api_key=calseta_key,
        model=model,
    )

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

    rows: list[dict[str, Any]] = []
    total_runs = len(SCENARIOS) * 2 * runs_per
    run_count = 0

    print(f"\n=== Running validation study ===")
    print(f"  Model: {model}")
    print(f"  Runs per scenario per approach: {runs_per}")
    print(f"  Total runs: {total_runs}")
    print()

    for scenario in SCENARIOS:
        fixture_path = FIXTURES_DIR / scenario["fixture"]
        with open(fixture_path) as f:
            raw_alert = json.load(f)

        alert_uuid = uuids.get(scenario["fixture"], "")

        print(f"--- {scenario['label']} ---")

        # Run naive agent
        for run_num in range(1, runs_per + 1):
            run_count += 1
            print(
                f"  [{run_count}/{total_runs}] Naive agent, run {run_num}... ",
                end="",
                flush=True,
            )

            try:
                metrics = await naive.investigate(raw_alert, scenario["source"])
                print(
                    f"OK ({metrics.input_tokens} in / "
                    f"{metrics.output_tokens} out / "
                    f"{metrics.duration_seconds:.1f}s)"
                )

                rows.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "scenario": scenario["label"],
                    "source": scenario["source"],
                    "approach": "naive",
                    "run_number": run_num,
                    "input_tokens": metrics.input_tokens,
                    "output_tokens": metrics.output_tokens,
                    "total_tokens": metrics.total_tokens,
                    "tool_calls": metrics.tool_calls,
                    "external_api_calls": metrics.external_api_calls,
                    "duration_seconds": metrics.duration_seconds,
                    "estimated_cost_usd": metrics.estimated_cost_usd,
                    "model": model,
                })

                # Save finding text
                finding_file = (
                    findings_dir
                    / f"{scenario['fixture'].replace('.json', '')}_naive_run{run_num}.txt"
                )
                with open(finding_file, "w") as f:
                    f.write(metrics.finding)

            except Exception as exc:
                print(f"FAILED ({exc})")

        # Run Calseta agent
        if not alert_uuid:
            print(f"  SKIPPING Calseta agent — no UUID for {scenario['fixture']}")
            continue

        for run_num in range(1, runs_per + 1):
            run_count += 1
            print(
                f"  [{run_count}/{total_runs}] Calseta agent, run {run_num}... ",
                end="",
                flush=True,
            )

            try:
                metrics = await calseta.investigate(alert_uuid)
                print(
                    f"OK ({metrics.input_tokens} in / "
                    f"{metrics.output_tokens} out / "
                    f"{metrics.duration_seconds:.1f}s)"
                )

                rows.append({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "scenario": scenario["label"],
                    "source": scenario["source"],
                    "approach": "calseta",
                    "run_number": run_num,
                    "input_tokens": metrics.input_tokens,
                    "output_tokens": metrics.output_tokens,
                    "total_tokens": metrics.total_tokens,
                    "tool_calls": metrics.tool_calls,
                    "external_api_calls": metrics.external_api_calls,
                    "duration_seconds": metrics.duration_seconds,
                    "estimated_cost_usd": metrics.estimated_cost_usd,
                    "model": model,
                })

                # Save finding text
                finding_file = (
                    findings_dir
                    / f"{scenario['fixture'].replace('.json', '')}_calseta_run{run_num}.txt"
                )
                with open(finding_file, "w") as f:
                    f.write(metrics.finding)

            except Exception as exc:
                print(f"FAILED ({exc})")

        print()

    # Write CSV
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n=== Study complete ===")
    print(f"  Results written to {csv_path}")
    print(f"  Findings written to {findings_dir}/")
    print(f"  Total runs completed: {len(rows)}/{total_runs}")

    # Print summary table
    _print_summary(rows)

    naive.close()
    calseta.close()


def _print_summary(rows: list[dict[str, Any]]) -> None:
    """Print a summary table comparing the two approaches."""
    from collections import defaultdict

    # Group by scenario and approach
    groups: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        groups[row["scenario"]][row["approach"]].append(row)

    print("\n=== Summary (averages across runs) ===\n")
    print(
        f"{'Scenario':<40} {'Approach':<10} {'Input Tok':>10} "
        f"{'Output Tok':>10} {'Total Tok':>10} {'Tools':>6} "
        f"{'API Calls':>10} {'Time (s)':>9} {'Cost ($)':>10}"
    )
    print("-" * 135)

    for scenario_label in dict.fromkeys(r["scenario"] for r in rows):
        for approach in ["naive", "calseta"]:
            runs = groups[scenario_label].get(approach, [])
            if not runs:
                continue
            n = len(runs)
            avg = lambda key: sum(r[key] for r in runs) / n  # noqa: E731
            print(
                f"{scenario_label:<40} {approach:<10} "
                f"{avg('input_tokens'):>10.0f} "
                f"{avg('output_tokens'):>10.0f} "
                f"{avg('total_tokens'):>10.0f} "
                f"{avg('tool_calls'):>6.1f} "
                f"{avg('external_api_calls'):>10.1f} "
                f"{avg('duration_seconds'):>9.1f} "
                f"{avg('estimated_cost_usd'):>10.6f}"
            )
        print()

    # Overall averages
    naive_rows = [r for r in rows if r["approach"] == "naive"]
    calseta_rows = [r for r in rows if r["approach"] == "calseta"]

    if naive_rows and calseta_rows:
        avg_naive_in = sum(r["input_tokens"] for r in naive_rows) / len(naive_rows)
        avg_calseta_in = sum(r["input_tokens"] for r in calseta_rows) / len(calseta_rows)
        avg_naive_total = sum(r["total_tokens"] for r in naive_rows) / len(naive_rows)
        avg_calseta_total = sum(r["total_tokens"] for r in calseta_rows) / len(
            calseta_rows
        )
        avg_naive_cost = sum(r["estimated_cost_usd"] for r in naive_rows) / len(
            naive_rows
        )
        avg_calseta_cost = sum(r["estimated_cost_usd"] for r in calseta_rows) / len(
            calseta_rows
        )

        if avg_naive_in > 0:
            input_reduction = (1 - avg_calseta_in / avg_naive_in) * 100
        else:
            input_reduction = 0

        if avg_naive_total > 0:
            total_reduction = (1 - avg_calseta_total / avg_naive_total) * 100
        else:
            total_reduction = 0

        if avg_naive_cost > 0:
            cost_reduction = (1 - avg_calseta_cost / avg_naive_cost) * 100
        else:
            cost_reduction = 0

        print("=== Overall ===")
        print(f"  Avg input tokens  — Naive: {avg_naive_in:.0f}, Calseta: {avg_calseta_in:.0f} ({input_reduction:+.1f}%)")
        print(f"  Avg total tokens  — Naive: {avg_naive_total:.0f}, Calseta: {avg_calseta_total:.0f} ({total_reduction:+.1f}%)")
        print(f"  Avg cost per alert — Naive: ${avg_naive_cost:.6f}, Calseta: ${avg_calseta_cost:.6f} ({cost_reduction:+.1f}%)")
        print(f"  Target: >=50% input token reduction. Result: {input_reduction:.1f}%")

        if input_reduction >= 50:
            print("  PASS: Input token reduction target met.")
        else:
            print("  FAIL: Input token reduction target NOT met.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calseta AI Validation Case Study Runner"
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
        asyncio.run(run_study(env))


if __name__ == "__main__":
    main()
