#!/usr/bin/env python3
"""
Finding Evaluator — Blind LLM Judge.

Reads the saved findings from both agents and scores them on three dimensions
using Claude as an independent judge. The judge receives findings in randomized
order without knowing which approach produced them (blind evaluation).

Scoring dimensions (each 0-10):
  - Completeness: Did the finding cover all indicators and relevant context?
  - Accuracy: Were the conclusions and risk assessments correct?
  - Actionability: Were the recommendations specific, useful, and operationally sound?

Usage:
    python evaluate_findings.py

    # Custom results directory
    python evaluate_findings.py --results-dir ./results

Environment variables:
    ANTHROPIC_API_KEY  - Required for the judge LLM
    CLAUDE_MODEL       - Model for evaluation (default: claude-sonnet-4-20250514)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CASE_STUDY_DIR = Path(__file__).parent
DEFAULT_RESULTS_DIR = CASE_STUDY_DIR / "results"
FIXTURES_DIR = CASE_STUDY_DIR / "fixtures"

SCENARIOS = [
    {
        "fixture": "01_sentinel_brute_force_tor",
        "label": "Sentinel: Brute Force from TOR",
        "expected_indicators": [
            "IP: 185.220.101.34 (TOR exit node)",
            "Account: j.martinez@contoso.com",
        ],
        "expected_conclusions": [
            "Source IP is a known TOR exit relay",
            "Brute force pattern: 47 failed + 1 successful auth",
            "High-risk: successful authentication after brute force from anonymization network",
            "Account may be compromised",
        ],
    },
    {
        "fixture": "02_elastic_malware_hash",
        "label": "Elastic: Known Malware Hash",
        "expected_indicators": [
            "SHA-256 hash of svchost_update.exe",
            "Source IP: 198.51.100.42",
            "User: admin",
        ],
        "expected_conclusions": [
            "File matches known Emotet banking trojan",
            "Executed from Temp directory via Outlook (email vector)",
            "Parent process is outlook.exe — likely phishing attachment",
            "Critical severity — active malware on endpoint",
        ],
    },
    {
        "fixture": "03_splunk_anomalous_data_transfer",
        "label": "Splunk: Anomalous Data Transfer",
        "expected_indicators": [
            "Source IP: 10.0.8.55 (internal)",
            "Destination IP: 45.33.32.156",
            "Domain: suspicious-cloud-sync.com",
            "User: svc_backup",
        ],
        "expected_conclusions": [
            "2GB+ data transfer to external IP",
            "Service account svc_backup performing suspicious transfer",
            "Destination domain is suspicious",
            "Data exfiltration risk — high volume outbound",
        ],
    },
    {
        "fixture": "04_sentinel_impossible_travel",
        "label": "Sentinel: Impossible Travel",
        "expected_indicators": [
            "Account: r.chen@contoso.com (Global Admin)",
            "IP: 91.234.56.78 (Moscow)",
            "IP: 203.0.113.25 (New York)",
        ],
        "expected_conclusions": [
            "32-minute gap between NY and Moscow sign-ins — impossible travel",
            "Account has Global Administrator privileges — high impact",
            "Moscow IP not previously associated with this user",
            "Likely credential compromise or token theft",
        ],
    },
    {
        "fixture": "05_elastic_suspicious_powershell",
        "label": "Elastic: Suspicious PowerShell",
        "expected_indicators": [
            "Domain: c2-relay.darkops.net (C2)",
            "Destination IP: 198.51.100.99",
            "URL: https://c2-relay.darkops.net/stager.ps1",
            "Hash of powershell.exe process",
        ],
        "expected_conclusions": [
            "Encoded PowerShell command — defense evasion technique",
            "Execution policy bypass + hidden window — automated malicious execution",
            "Downloads payload from C2 domain",
            "Running on DC01 (domain controller) — critical infrastructure compromise",
            "Running as SYSTEM — highest privilege",
        ],
    },
]


# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------

JUDGE_SYSTEM_PROMPT = """\
You are an expert SOC analyst evaluating investigation findings produced by
AI agents. You will receive:

1. The original alert context (what the alert was about)
2. A list of expected indicators and conclusions (ground truth)
3. A finding to evaluate

Score the finding on three dimensions, each on a 0-10 scale:

**Completeness (0-10):**
- Did the finding identify ALL indicators of compromise present in the alert?
- Did it cover the relevant enrichment data for each indicator?
- Were any important indicators or context missed?
- 10 = all indicators found and discussed; 0 = none found

**Accuracy (0-10):**
- Were the conclusions about each indicator correct?
- Was the risk assessment aligned with the ground truth?
- Were there any false claims or incorrect statements?
- 10 = all conclusions correct; 0 = completely wrong

**Actionability (0-10):**
- Were the recommended next steps specific and operationally useful?
- Could a SOC analyst follow the recommendations without additional research?
- Were recommendations prioritized by urgency?
- 10 = immediately actionable; 0 = vague or useless

Respond with ONLY a JSON object in this exact format:
{
    "completeness": <0-10>,
    "accuracy": <0-10>,
    "actionability": <0-10>,
    "completeness_notes": "<brief explanation>",
    "accuracy_notes": "<brief explanation>",
    "actionability_notes": "<brief explanation>"
}

Do NOT include any text outside the JSON object.
"""


def build_judge_prompt(
    scenario: dict[str, Any],
    finding: str,
) -> str:
    """Build the evaluation prompt for a single finding."""
    indicators = "\n".join(f"  - {i}" for i in scenario["expected_indicators"])
    conclusions = "\n".join(f"  - {c}" for c in scenario["expected_conclusions"])

    return (
        f"## Alert Context\n"
        f"Scenario: {scenario['label']}\n\n"
        f"## Expected Indicators (Ground Truth)\n{indicators}\n\n"
        f"## Expected Conclusions (Ground Truth)\n{conclusions}\n\n"
        f"## Finding to Evaluate\n{finding}\n"
    )


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def evaluate_findings(results_dir: Path, env: dict[str, str]) -> None:
    """Run blind evaluation on all saved findings."""
    anthropic_key = env.get("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        print("ERROR: ANTHROPIC_API_KEY is required")
        sys.exit(1)

    model = env.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    client = anthropic.Anthropic(api_key=anthropic_key)

    findings_dir = results_dir / "findings"
    if not findings_dir.exists():
        print(f"ERROR: {findings_dir} not found. Run the study first.")
        sys.exit(1)

    # Collect all finding files
    finding_files = sorted(findings_dir.glob("*.txt"))
    if not finding_files:
        print("ERROR: No finding files found. Run the study first.")
        sys.exit(1)

    print(f"\n=== Evaluating {len(finding_files)} findings ===")
    print(f"  Model: {model}")
    print(f"  Results dir: {results_dir}\n")

    # Build evaluation pairs (randomized for blind judging)
    eval_items: list[dict[str, Any]] = []
    for fpath in finding_files:
        fname = fpath.stem  # e.g., "01_sentinel_brute_force_tor_naive_run1"
        parts = fname.rsplit("_", 2)  # ["01_sentinel_brute_force_tor", "naive", "run1"]
        if len(parts) < 3:
            continue

        fixture_key = parts[0]
        approach = parts[1]
        run_label = parts[2]

        # Find matching scenario
        scenario = None
        for s in SCENARIOS:
            if s["fixture"] == fixture_key:
                scenario = s
                break
        if not scenario:
            continue

        with open(fpath) as f:
            finding_text = f.read()

        if not finding_text.strip():
            continue

        eval_items.append({
            "file": fpath.name,
            "fixture": fixture_key,
            "approach": approach,
            "run": run_label,
            "scenario": scenario,
            "finding": finding_text,
        })

    # Randomize order for blind evaluation
    random.shuffle(eval_items)

    # Evaluate each finding
    scores: list[dict[str, Any]] = []

    for i, item in enumerate(eval_items, 1):
        print(
            f"  [{i}/{len(eval_items)}] Evaluating {item['file']}... ",
            end="",
            flush=True,
        )

        prompt = build_judge_prompt(item["scenario"], item["finding"])

        try:
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                temperature=0,
                system=JUDGE_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = "".join(
                b.text for b in response.content if b.type == "text"
            )

            # Parse JSON response
            score_data = json.loads(response_text)

            scores.append({
                "file": item["file"],
                "scenario": item["scenario"]["label"],
                "approach": item["approach"],
                "run": item["run"],
                "completeness": score_data.get("completeness", 0),
                "accuracy": score_data.get("accuracy", 0),
                "actionability": score_data.get("actionability", 0),
                "completeness_notes": score_data.get("completeness_notes", ""),
                "accuracy_notes": score_data.get("accuracy_notes", ""),
                "actionability_notes": score_data.get("actionability_notes", ""),
            })

            print(
                f"OK (C:{score_data.get('completeness', '?')} "
                f"A:{score_data.get('accuracy', '?')} "
                f"R:{score_data.get('actionability', '?')})"
            )

        except json.JSONDecodeError:
            print("FAILED (invalid JSON from judge)")
        except Exception as exc:
            print(f"FAILED ({exc})")

    # Write scores CSV
    scores_path = results_dir / "quality_scores.csv"
    fieldnames = [
        "file",
        "scenario",
        "approach",
        "run",
        "completeness",
        "accuracy",
        "actionability",
        "completeness_notes",
        "accuracy_notes",
        "actionability_notes",
    ]

    with open(scores_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(scores)

    print(f"\n  Quality scores written to {scores_path}")

    # Print summary
    _print_quality_summary(scores)


def _print_quality_summary(scores: list[dict[str, Any]]) -> None:
    """Print quality score summary by approach."""
    from collections import defaultdict

    by_approach: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in scores:
        by_approach[s["approach"]].append(s)

    print("\n=== Quality Score Summary (averages) ===\n")
    print(
        f"{'Approach':<12} {'Completeness':>14} {'Accuracy':>10} "
        f"{'Actionability':>15} {'Overall':>10}"
    )
    print("-" * 65)

    for approach in ["naive", "calseta"]:
        items = by_approach.get(approach, [])
        if not items:
            continue
        n = len(items)
        avg_c = sum(s["completeness"] for s in items) / n
        avg_a = sum(s["accuracy"] for s in items) / n
        avg_r = sum(s["actionability"] for s in items) / n
        avg_overall = (avg_c + avg_a + avg_r) / 3

        print(
            f"{approach:<12} {avg_c:>14.1f} {avg_a:>10.1f} "
            f"{avg_r:>15.1f} {avg_overall:>10.1f}"
        )

    # Per-scenario breakdown
    by_scenario: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for s in scores:
        by_scenario[s["scenario"]][s["approach"]].append(s)

    print("\n=== Per-Scenario Breakdown ===\n")
    for scenario_label in dict.fromkeys(s["scenario"] for s in scores):
        print(f"  {scenario_label}:")
        for approach in ["naive", "calseta"]:
            items = by_scenario[scenario_label].get(approach, [])
            if not items:
                continue
            n = len(items)
            avg_c = sum(s["completeness"] for s in items) / n
            avg_a = sum(s["accuracy"] for s in items) / n
            avg_r = sum(s["actionability"] for s in items) / n
            print(
                f"    {approach:<10} — Completeness: {avg_c:.1f}, "
                f"Accuracy: {avg_a:.1f}, Actionability: {avg_r:.1f}"
            )
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_env() -> dict[str, str]:
    """Load environment variables."""
    env: dict[str, str] = {}
    for env_path in [CASE_STUDY_DIR / ".env", CASE_STUDY_DIR.parent.parent / ".env"]:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, val = line.partition("=")
                        env[key.strip()] = val.strip().strip("\"'")
    for key in ["ANTHROPIC_API_KEY", "CLAUDE_MODEL"]:
        val = os.environ.get(key)
        if val:
            env[key] = val
    return env


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate case study findings using blind LLM judge"
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=DEFAULT_RESULTS_DIR,
        help="Directory containing findings (default: results/)",
    )
    args = parser.parse_args()
    env = load_env()
    evaluate_findings(args.results_dir, env)


if __name__ == "__main__":
    main()
