#!/usr/bin/env python3
"""
Finding Evaluator — Blind LLM Judge.

Reads the saved findings from both agents and scores them on three dimensions
using an LLM as an independent judge. Supports both Claude and OpenAI (including
Azure OpenAI) as the judge model. The judge receives findings in randomized
order without knowing which approach produced them (blind evaluation).

Scoring dimensions (each 0-10):
  - Completeness: Did the finding cover all indicators and relevant context?
  - Accuracy: Were the conclusions and risk assessments correct?
  - Actionability: Were the recommendations specific, useful, and operationally sound?

Usage:
    python evaluate_findings.py

    # Use OpenAI as judge
    python evaluate_findings.py --model openai

    # Evaluate a specific study
    python evaluate_findings.py --study 2

    # Custom results directory (overrides --study)
    python evaluate_findings.py --results-dir ./results/study_1

Environment variables:
    ANTHROPIC_API_KEY           - Required for Claude judge
    CLAUDE_MODEL                - Claude model (default: claude-sonnet-4-20250514)
    OPENAI_API_KEY              - Required for OpenAI judge (direct)
    OPENAI_MODEL                - OpenAI model (default: gpt-4o)
    AZURE_OPENAI_ENDPOINT       - Azure OpenAI endpoint (takes priority over direct)
    AZURE_OPENAI_API_KEY        - Azure OpenAI API key
    AZURE_OPENAI_DEPLOYMENT     - Azure deployment name
    AZURE_OPENAI_API_VERSION    - Azure API version (default: 2024-10-21)
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CASE_STUDY_DIR = Path(__file__).parent
RESULTS_BASE_DIR = CASE_STUDY_DIR / "results"
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
# LLM abstraction
# ---------------------------------------------------------------------------

def _call_judge(
    client: Any,
    model: str,
    system_prompt: str,
    user_prompt: str,
    provider: str,
) -> str:
    """Call the judge LLM and return the response text."""
    if provider == "openai":
        response = client.chat.completions.create(
            model=model,
            max_tokens=1024,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content or ""
    else:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(b.text for b in response.content if b.type == "text")


def _model_short_name(model: str) -> str:
    """Return a short name for output file naming."""
    if "claude" in model.lower():
        return "claude"
    if "gpt" in model.lower():
        return "gpt4o"
    return model.split("-")[0]


# ---------------------------------------------------------------------------
# Study directory helpers
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


# ---------------------------------------------------------------------------
# JSON parsing helpers
# ---------------------------------------------------------------------------

def _parse_judge_json(response_text: str) -> dict[str, Any]:
    """Parse judge response into a dict, handling markdown fences and extra text.

    Tries multiple strategies:
    1. Direct JSON parse
    2. Strip markdown code fences (```json ... ```)
    3. Extract first JSON object between { and } via brace matching
    """
    cleaned = response_text.strip()

    # Strategy 1: direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip markdown code fences
    if "```" in cleaned:
        # Extract content between first ``` and last ```
        fence_start = cleaned.find("```")
        fence_end = cleaned.rfind("```")
        if fence_start != fence_end:
            inner = cleaned[fence_start:fence_end]
            # Remove the opening fence line (```json or ```)
            first_newline = inner.find("\n")
            if first_newline != -1:
                inner = inner[first_newline + 1:]
            try:
                return json.loads(inner.strip())
            except json.JSONDecodeError:
                pass

    # Strategy 3: find first { and its matching } via brace counting
    start = cleaned.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start:i + 1])
                    except json.JSONDecodeError:
                        break

    # All strategies failed — raise with context for debugging
    preview = cleaned[:300] if len(cleaned) > 300 else cleaned
    raise json.JSONDecodeError(
        f"Could not extract JSON from judge response. Preview: {preview!r}",
        cleaned,
        0,
    )


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def evaluate_findings(
    results_dir: Path, env: dict[str, str], provider: str = "claude"
) -> None:
    """Run blind evaluation on all saved findings."""

    # Initialize judge client
    if provider == "openai":
        import openai as openai_mod

        azure_endpoint = env.get("AZURE_OPENAI_ENDPOINT", "")
        azure_key = env.get("AZURE_OPENAI_API_KEY", "")
        if azure_endpoint and azure_key:
            from openai import AzureOpenAI

            client = AzureOpenAI(
                api_key=azure_key,
                azure_endpoint=azure_endpoint,
                api_version=env.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
            )
            judge_model = env.get(
                "AZURE_OPENAI_DEPLOYMENT",
                env.get("OPENAI_MODEL", "gpt-4o"),
            )
        else:
            openai_key = env.get("OPENAI_API_KEY", "")
            if not openai_key:
                print("ERROR: OPENAI_API_KEY or AZURE_OPENAI_API_KEY is required for OpenAI judge")
                sys.exit(1)
            client = openai_mod.OpenAI(api_key=openai_key)
            judge_model = env.get("OPENAI_MODEL", "gpt-4o")
    else:
        import anthropic

        anthropic_key = env.get("ANTHROPIC_API_KEY", "")
        if not anthropic_key:
            print("ERROR: ANTHROPIC_API_KEY is required for Claude judge")
            sys.exit(1)
        client = anthropic.Anthropic(api_key=anthropic_key)
        judge_model = env.get("CLAUDE_MODEL", "claude-sonnet-4-20250514")

    model_short = _model_short_name(judge_model)

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
    print(f"  Judge provider: {provider}")
    print(f"  Judge model: {judge_model}")
    print(f"  Results dir: {results_dir}\n")

    # Build evaluation pairs (randomized for blind judging)
    eval_items: list[dict[str, Any]] = []
    for fpath in finding_files:
        fname = fpath.stem
        # Support both old format: "01_..._naive_run1"
        # and new format:          "01_..._naive_claude_run1"
        parts = fname.rsplit("_", 3)

        fixture_key = ""
        approach = ""
        run_label = ""
        finding_model = "unknown"

        if len(parts) >= 4 and parts[-1].startswith("run"):
            # New format: fixture_approach_model_runN
            fixture_key = parts[0]
            approach = parts[1]
            finding_model = parts[2]
            run_label = parts[3]
        elif len(parts) >= 3 and parts[-1].startswith("run"):
            # Fallback: try 2-part split (old format)
            old_parts = fname.rsplit("_", 2)
            fixture_key = old_parts[0]
            approach = old_parts[1]
            run_label = old_parts[2]
        else:
            continue

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
            "model": finding_model,
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
            response_text = _call_judge(
                client, judge_model, JUDGE_SYSTEM_PROMPT, prompt, provider
            )

            score_data = _parse_judge_json(response_text)

            scores.append({
                "file": item["file"],
                "scenario": item["scenario"]["label"],
                "approach": item["approach"],
                "model": item.get("model", "unknown"),
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

        except json.JSONDecodeError as jde:
            print(f"FAILED (invalid JSON from judge: {jde.msg[:120]})")
        except Exception as exc:
            print(f"FAILED ({exc})")

    # Write scores CSV with model-specific filename
    scores_path = results_dir / f"quality_scores_{model_short}.csv"
    fieldnames = [
        "file",
        "scenario",
        "approach",
        "model",
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

    # Print summary and write analysis file
    _print_quality_summary(scores, results_dir, model_short)


def _print_quality_summary(
    scores: list[dict[str, Any]],
    results_dir: Path,
    judge_model_short: str,
) -> None:
    """Print quality score summary by model and approach, and write analysis markdown."""
    from collections import defaultdict

    # Group by model and approach
    by_model_approach: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for s in scores:
        model = s.get("model", "unknown")
        by_model_approach[model][s["approach"]].append(s)

    print("\n=== Quality Score Summary (averages) ===\n")
    print(
        f"{'Model':<15} {'Approach':<12} {'Completeness':>14} {'Accuracy':>10} "
        f"{'Actionability':>15} {'Overall':>10}"
    )
    print("-" * 80)

    # Collect summary data for markdown output
    md_lines: list[str] = []
    md_lines.append(f"# Quality Analysis — Judge: {judge_model_short}")
    md_lines.append("")
    md_lines.append(
        f"Generated at {datetime.now(UTC).isoformat()} "
        f"using {judge_model_short} as the blind judge."
    )
    md_lines.append("")
    md_lines.append("## Overall Averages")
    md_lines.append("")
    md_lines.append(
        "| Model | Approach | Completeness | Accuracy | Actionability | Overall |"
    )
    md_lines.append("|---|---|---|---|---|---|")

    for model in sorted(by_model_approach.keys()):
        for approach in ["naive", "calseta"]:
            items = by_model_approach[model].get(approach, [])
            if not items:
                continue
            n = len(items)
            avg_c = sum(s["completeness"] for s in items) / n
            avg_a = sum(s["accuracy"] for s in items) / n
            avg_r = sum(s["actionability"] for s in items) / n
            avg_overall = (avg_c + avg_a + avg_r) / 3

            print(
                f"{model:<15} {approach:<12} {avg_c:>14.1f} {avg_a:>10.1f} "
                f"{avg_r:>15.1f} {avg_overall:>10.1f}"
            )
            md_lines.append(
                f"| {model} | {approach} | {avg_c:.1f} | {avg_a:.1f} "
                f"| {avg_r:.1f} | {avg_overall:.1f} |"
            )

    # Per-scenario breakdown grouped by model
    by_model_scenario: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = (
        defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    )
    for s in scores:
        model = s.get("model", "unknown")
        by_model_scenario[model][s["scenario"]][s["approach"]].append(s)

    print("\n=== Per-Scenario Breakdown ===\n")
    md_lines.append("")
    md_lines.append("## Per-Scenario Breakdown")
    md_lines.append("")

    for model in sorted(by_model_scenario.keys()):
        print(f"  [{model}]")
        md_lines.append(f"### {model}")
        md_lines.append("")
        md_lines.append(
            "| Scenario | Approach | Completeness | Accuracy | Actionability |"
        )
        md_lines.append("|---|---|---|---|---|")

        for scenario_label in dict.fromkeys(
            s["scenario"] for s in scores if s.get("model") == model
        ):
            print(f"    {scenario_label}:")
            for approach in ["naive", "calseta"]:
                items = by_model_scenario[model][scenario_label].get(approach, [])
                if not items:
                    continue
                n = len(items)
                avg_c = sum(s["completeness"] for s in items) / n
                avg_a = sum(s["accuracy"] for s in items) / n
                avg_r = sum(s["actionability"] for s in items) / n
                print(
                    f"      {approach:<10} — Completeness: {avg_c:.1f}, "
                    f"Accuracy: {avg_a:.1f}, Actionability: {avg_r:.1f}"
                )
                md_lines.append(
                    f"| {scenario_label} | {approach} | {avg_c:.1f} "
                    f"| {avg_a:.1f} | {avg_r:.1f} |"
                )
            print()

        md_lines.append("")

    # Write analysis markdown
    analysis_path = results_dir / f"quality_analysis_{judge_model_short}.md"
    with open(analysis_path, "w") as f:
        f.write("\n".join(md_lines) + "\n")
    print(f"  Quality analysis written to {analysis_path}")


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
    for key in [
        "ANTHROPIC_API_KEY",
        "CLAUDE_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "AZURE_OPENAI_ENDPOINT",
        "AZURE_OPENAI_API_KEY",
        "AZURE_OPENAI_DEPLOYMENT",
        "AZURE_OPENAI_API_VERSION",
    ]:
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
        default=None,
        help="Directory containing findings (overrides --study)",
    )
    parser.add_argument(
        "--model",
        choices=["claude", "openai"],
        default="claude",
        help="LLM provider to use as judge (default: claude)",
    )
    parser.add_argument(
        "--study",
        type=int,
        default=0,
        help="Study run number to evaluate (default: most recent)",
    )
    args = parser.parse_args()

    # Resolve results directory
    if args.results_dir is not None:
        results_dir = args.results_dir
    elif args.study > 0:
        results_dir = _resolve_study_dir(args.study)
    else:
        # Find most recent study dir
        results_dir = _resolve_study_dir(_latest_study_num())

    env = load_env()
    evaluate_findings(results_dir, env, provider=args.model)


if __name__ == "__main__":
    main()
