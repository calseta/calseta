#!/usr/bin/env python3
"""
Cost Projection Calculator.

Reads raw_metrics.csv from the case study results and produces:
  1. Terminal table with per-alert costs and projections at scale
  2. results/cost_projections.md with detailed analysis

Usage:
    python cost_projections.py

    # Custom results directory
    python cost_projections.py --results-dir ./results
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


CASE_STUDY_DIR = Path(__file__).parent
RESULTS_BASE_DIR = CASE_STUDY_DIR / "results"

# Engineering time estimates (hours) for building and maintaining the agent
NAIVE_ENG_HOURS_LOW = 40
NAIVE_ENG_HOURS_HIGH = 80
CALSETA_ENG_HOURS_LOW = 1
CALSETA_ENG_HOURS_HIGH = 2
ENG_HOURLY_RATE = 100  # USD

# Scale projection: alerts per day
SCALE_TIERS = [1, 10, 100, 1000]


def load_metrics(results_dir: Path) -> list[dict[str, Any]]:
    """Load raw_metrics.csv into a list of dicts."""
    csv_path = results_dir / "raw_metrics.csv"
    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found. Run the study first.")
        sys.exit(1)

    rows: list[dict[str, Any]] = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert numeric fields
            for key in [
                "input_tokens", "output_tokens", "total_tokens",
                "tool_calls", "external_api_calls",
            ]:
                row[key] = int(row.get(key, 0))
            for key in ["duration_seconds", "estimated_cost_usd"]:
                row[key] = float(row.get(key, 0))
            rows.append(row)
    return rows


def compute_averages(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Compute averages grouped by (model, approach)."""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        key = f"{row.get('model', 'unknown')}|{row['approach']}"
        groups[key].append(row)

    averages: dict[str, dict[str, float]] = {}
    for key, group_rows in groups.items():
        n = len(group_rows)
        averages[key] = {
            "input_tokens": sum(r["input_tokens"] for r in group_rows) / n,
            "output_tokens": sum(r["output_tokens"] for r in group_rows) / n,
            "total_tokens": sum(r["total_tokens"] for r in group_rows) / n,
            "tool_calls": sum(r["tool_calls"] for r in group_rows) / n,
            "external_api_calls": sum(r["external_api_calls"] for r in group_rows) / n,
            "duration_seconds": sum(r["duration_seconds"] for r in group_rows) / n,
            "cost_per_alert": sum(r["estimated_cost_usd"] for r in group_rows) / n,
            "count": n,
        }
    return averages


def print_terminal_table(averages: dict[str, dict[str, float]]) -> None:
    """Print summary tables to terminal."""
    print("\n" + "=" * 90)
    print("COST PROJECTIONS — Calseta Validation Case Study")
    print("=" * 90)

    # Per-alert cost table
    print("\n--- Per-Alert Cost (Observed Averages) ---\n")
    print(
        f"{'Model':<30} {'Approach':<10} {'Avg Input':>10} "
        f"{'Avg Output':>11} {'Avg Cost':>12} {'Runs':>6}"
    )
    print("-" * 85)

    for key in sorted(averages.keys()):
        model, approach = key.split("|")
        avg = averages[key]
        # Shorten model name for display
        model_short = model.split("-")[0] if "-" in model else model
        if "claude" in model.lower():
            model_short = "Claude Sonnet"
        elif "gpt" in model.lower():
            model_short = "GPT-4o"
        print(
            f"{model_short:<30} {approach:<10} "
            f"{avg['input_tokens']:>10,.0f} "
            f"{avg['output_tokens']:>11,.0f} "
            f"${avg['cost_per_alert']:>11.6f} "
            f"{avg['count']:>6.0f}"
        )

    # Monthly projections
    print("\n--- Monthly Cost Projections (LLM costs only) ---\n")
    print(
        f"{'Model':<20} {'Approach':<10} "
        + "".join(f"{t} alerts/day:>16" for t in SCALE_TIERS)
    )

    # Build header
    header = f"{'Model':<20} {'Approach':<10} "
    for tier in SCALE_TIERS:
        header += f"{'  ' + str(tier) + ' /day':>16}"
    print(header)
    print("-" * (30 + 16 * len(SCALE_TIERS)))

    for key in sorted(averages.keys()):
        model, approach = key.split("|")
        avg = averages[key]
        cost_per = avg["cost_per_alert"]

        model_short = model.split("-")[0]
        if "claude" in model.lower():
            model_short = "Claude Sonnet"
        elif "gpt" in model.lower():
            model_short = "GPT-4o"

        row_str = f"{model_short:<20} {approach:<10} "
        for tier in SCALE_TIERS:
            monthly = cost_per * tier * 30
            row_str += f"${monthly:>14.2f}"
        print(row_str)

    # Token reduction summary
    print("\n--- Token Reduction Summary ---\n")
    models_seen: set[str] = set()
    for key in averages:
        model, _ = key.split("|")
        models_seen.add(model)

    for model in sorted(models_seen):
        naive_key = f"{model}|naive"
        calseta_key = f"{model}|calseta"
        if naive_key not in averages or calseta_key not in averages:
            continue

        naive_avg = averages[naive_key]
        calseta_avg = averages[calseta_key]

        model_short = model
        if "claude" in model.lower():
            model_short = "Claude Sonnet"
        elif "gpt" in model.lower():
            model_short = "GPT-4o"

        input_reduction = (
            (1 - calseta_avg["input_tokens"] / naive_avg["input_tokens"]) * 100
            if naive_avg["input_tokens"] > 0 else 0
        )
        cost_reduction = (
            (1 - calseta_avg["cost_per_alert"] / naive_avg["cost_per_alert"]) * 100
            if naive_avg["cost_per_alert"] > 0 else 0
        )

        print(f"  {model_short}:")
        print(f"    Input token reduction:  {input_reduction:+.1f}%")
        print(f"    Cost reduction:         {cost_reduction:+.1f}%")
        print(
            f"    Naive avg cost/alert:   ${naive_avg['cost_per_alert']:.6f}"
        )
        print(
            f"    Calseta avg cost/alert: ${calseta_avg['cost_per_alert']:.6f}"
        )
        print()


def generate_markdown_report(
    averages: dict[str, dict[str, float]], results_dir: Path
) -> None:
    """Generate results/cost_projections.md."""
    lines: list[str] = []
    lines.append("# Calseta Case Study — Cost Projections")
    lines.append("")
    lines.append(
        "Generated from observed metrics in `raw_metrics.csv`. "
        "All costs are LLM API costs only (no infrastructure)."
    )
    lines.append("")

    # Per-alert cost table
    lines.append("## Per-Alert Cost (Observed Averages)")
    lines.append("")
    lines.append(
        "| Model | Approach | Avg Input Tokens | Avg Output Tokens "
        "| Avg Total Tokens | Avg Tool Calls | Avg Cost ($) |"
    )
    lines.append("|---|---|---|---|---|---|---|")

    for key in sorted(averages.keys()):
        model, approach = key.split("|")
        avg = averages[key]
        model_short = model
        if "claude" in model.lower():
            model_short = "Claude Sonnet"
        elif "gpt" in model.lower():
            model_short = "GPT-4o"

        lines.append(
            f"| {model_short} | {approach} "
            f"| {avg['input_tokens']:,.0f} "
            f"| {avg['output_tokens']:,.0f} "
            f"| {avg['total_tokens']:,.0f} "
            f"| {avg['tool_calls']:.1f} "
            f"| ${avg['cost_per_alert']:.6f} |"
        )

    lines.append("")

    # Monthly projections
    lines.append("## Monthly Cost at Scale (LLM Only)")
    lines.append("")
    header = "| Model | Approach |"
    separator = "|---|---|"
    for tier in SCALE_TIERS:
        header += f" {tier} alerts/day |"
        separator += "---|"
    lines.append(header)
    lines.append(separator)

    for key in sorted(averages.keys()):
        model, approach = key.split("|")
        avg = averages[key]
        cost_per = avg["cost_per_alert"]

        model_short = model
        if "claude" in model.lower():
            model_short = "Claude Sonnet"
        elif "gpt" in model.lower():
            model_short = "GPT-4o"

        row = f"| {model_short} | {approach} |"
        for tier in SCALE_TIERS:
            monthly = cost_per * tier * 30
            row += f" ${monthly:,.2f} |"
        lines.append(row)

    lines.append("")

    # Engineering time comparison
    lines.append("## Engineering Time Comparison")
    lines.append("")
    lines.append(
        "Building an AI SOC agent requires different levels of engineering "
        "effort depending on the approach."
    )
    lines.append("")
    lines.append("| Component | Naive Agent | Calseta Agent |")
    lines.append("|---|---|---|")
    lines.append(
        f"| Tool definitions & API integration | "
        f"{NAIVE_ENG_HOURS_LOW}-{NAIVE_ENG_HOURS_HIGH} hrs | 0 hrs |"
    )
    lines.append(
        "| Enrichment pipeline (rate limits, caching, retry) | "
        "Included above | 0 hrs (platform handles) |"
    )
    lines.append(
        "| Prompt engineering for raw payloads | "
        "10-20 hrs | 0 hrs |"
    )
    lines.append(
        f"| Agent integration with Calseta REST API | "
        f"N/A | {CALSETA_ENG_HOURS_LOW}-{CALSETA_ENG_HOURS_HIGH} hrs |"
    )
    lines.append(
        f"| **Total estimated** | "
        f"**{NAIVE_ENG_HOURS_LOW}-{NAIVE_ENG_HOURS_HIGH} hrs** | "
        f"**{CALSETA_ENG_HOURS_LOW}-{CALSETA_ENG_HOURS_HIGH} hrs** |"
    )
    lines.append("")

    # Year 1 TCO
    lines.append("## Year 1 Total Cost of Ownership")
    lines.append("")
    lines.append(
        "Combines engineering time (one-time) + 12 months of LLM API costs."
    )
    lines.append("")

    # Build TCO table for each model
    models_seen: set[str] = set()
    for key in averages:
        model, _ = key.split("|")
        models_seen.add(model)

    tco_header = "| Component |"
    tco_sep = "|---|"
    for model in sorted(models_seen):
        model_short = model
        if "claude" in model.lower():
            model_short = "Claude Sonnet"
        elif "gpt" in model.lower():
            model_short = "GPT-4o"
        tco_header += f" {model_short} Naive | {model_short} Calseta |"
        tco_sep += "---|---|"
    lines.append(tco_header)
    lines.append(tco_sep)

    # Engineering cost row
    eng_row = "| Engineering (one-time) |"
    for model in sorted(models_seen):
        naive_eng = f"${NAIVE_ENG_HOURS_LOW * ENG_HOURLY_RATE:,}-${NAIVE_ENG_HOURS_HIGH * ENG_HOURLY_RATE:,}"
        calseta_eng = f"${CALSETA_ENG_HOURS_LOW * ENG_HOURLY_RATE:,}-${CALSETA_ENG_HOURS_HIGH * ENG_HOURLY_RATE:,}"
        eng_row += f" {naive_eng} | {calseta_eng} |"
    lines.append(eng_row)

    # LLM cost rows for each scale tier
    for tier in [10, 100]:
        llm_row = f"| LLM costs (12 mo, {tier} alerts/day) |"
        for model in sorted(models_seen):
            naive_key = f"{model}|naive"
            calseta_key = f"{model}|calseta"
            if naive_key in averages:
                naive_annual = averages[naive_key]["cost_per_alert"] * tier * 365
                llm_row += f" ${naive_annual:,.2f} |"
            else:
                llm_row += " — |"
            if calseta_key in averages:
                calseta_annual = averages[calseta_key]["cost_per_alert"] * tier * 365
                llm_row += f" ${calseta_annual:,.2f} |"
            else:
                llm_row += " — |"
        lines.append(llm_row)

    lines.append("")

    # Token reduction summary
    lines.append("## Token Reduction Summary")
    lines.append("")
    lines.append("| Model | Input Token Reduction | Cost Reduction |")
    lines.append("|---|---|---|")

    for model in sorted(models_seen):
        naive_key = f"{model}|naive"
        calseta_key = f"{model}|calseta"
        if naive_key not in averages or calseta_key not in averages:
            continue

        naive_avg = averages[naive_key]
        calseta_avg = averages[calseta_key]

        model_short = model
        if "claude" in model.lower():
            model_short = "Claude Sonnet"
        elif "gpt" in model.lower():
            model_short = "GPT-4o"

        input_reduction = (
            (1 - calseta_avg["input_tokens"] / naive_avg["input_tokens"]) * 100
            if naive_avg["input_tokens"] > 0 else 0
        )
        cost_reduction = (
            (1 - calseta_avg["cost_per_alert"] / naive_avg["cost_per_alert"]) * 100
            if naive_avg["cost_per_alert"] > 0 else 0
        )

        lines.append(
            f"| {model_short} | {input_reduction:+.1f}% | {cost_reduction:+.1f}% |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*These projections are based on observed metrics from the validation "
        "case study using synthetic alert fixtures. Production costs will vary "
        "based on alert complexity, payload size, and enrichment depth.*"
    )

    # Write file
    report_path = results_dir / "cost_projections.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n  Cost projections written to {report_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _resolve_study_dir(study_num: int) -> Path:
    """Resolve the results directory for a given study number."""
    return RESULTS_BASE_DIR / f"study_{study_num}"


def _latest_study_num() -> int:
    """Find the most recent study number (at least 1)."""
    num = 1
    while _resolve_study_dir(num + 1).exists():
        num += 1
    return num


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate cost projections from case study metrics"
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="Directory containing raw_metrics.csv (overrides --study)",
    )
    parser.add_argument(
        "--study",
        type=int,
        default=0,
        help="Study run number (default: most recent)",
    )
    args = parser.parse_args()

    # Resolve results directory
    if args.results_dir is not None:
        results_dir = args.results_dir
    elif args.study > 0:
        results_dir = _resolve_study_dir(args.study)
    else:
        results_dir = _resolve_study_dir(_latest_study_num())

    rows = load_metrics(results_dir)
    averages = compute_averages(rows)

    print_terminal_table(averages)
    generate_markdown_report(averages, results_dir)


if __name__ == "__main__":
    main()
