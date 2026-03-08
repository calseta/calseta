# Case Study Quality Analysis — Blind Evaluation Results

## Overview

After running the 60-run token comparison (Phase 3), we conducted a blind quality evaluation using Claude as an independent judge. Findings were randomized and scored on three dimensions (0-10 each): Completeness, Accuracy, and Actionability.

## Aggregate Scores by Model + Approach

| Model | Approach | N | Completeness | Accuracy | Actionability | Overall |
|-------|----------|---|-------------|----------|---------------|---------|
| Claude Sonnet | Naive | 15 | **8.9** | **8.1** | 9.0 | **8.7** |
| Claude Sonnet | Calseta | 15 | 7.3 | 6.6 | 9.0 | 7.6 |
| GPT-4o | Naive | 15 | 8.4 | 6.7 | 7.4 | 7.5 |
| GPT-4o | Calseta | 15 | 7.9 | 6.7 | **8.5** | **7.7** |

**Key finding:** On GPT-4o, quality is roughly equivalent (7.7 vs 7.5 overall) with Calseta slightly ahead. On Claude, the naive agent outperforms by a full point (8.7 vs 7.6), driven by higher Completeness and Accuracy.

## Per-Scenario Breakdown (Claude)

| Scenario | Approach | Completeness | Accuracy | Actionability |
|----------|----------|-------------|----------|---------------|
| Brute Force from TOR | Naive | 10.0 | 10.0 | 10.0 |
| Brute Force from TOR | Calseta | 8.0 | 8.3 | 9.7 |
| Known Malware Hash | Naive | 4.7 | **2.0** | 6.0 |
| Known Malware Hash | **Calseta** | **8.0** | **8.3** | **9.0** |
| Anomalous Data Transfer | Naive | 10.0 | 10.0 | 10.0 |
| Anomalous Data Transfer | Calseta | 6.7 | 4.7 | 8.3 |
| Impossible Travel | Naive | 10.0 | 9.3 | 10.0 |
| Impossible Travel | Calseta | 6.0 | 4.0 | 9.0 |
| Suspicious PowerShell | Naive | 10.0 | 9.0 | 9.0 |
| Suspicious PowerShell | Calseta | 8.0 | 7.7 | 9.0 |

## Per-Scenario Breakdown (GPT-4o)

| Scenario | Approach | Completeness | Accuracy | Actionability |
|----------|----------|-------------|----------|---------------|
| Brute Force from TOR | Naive | 10.0 | 10.0 | 9.0 |
| Brute Force from TOR | Calseta | 9.7 | 8.3 | 8.7 |
| Known Malware Hash | Naive | 7.3 | 4.0 | 6.7 |
| Known Malware Hash | **Calseta** | **7.3** | **7.0** | **8.7** |
| Anomalous Data Transfer | Naive | 8.3 | 7.7 | 7.3 |
| Anomalous Data Transfer | Calseta | 8.0 | 6.0 | 8.7 |
| Impossible Travel | Naive | 8.3 | 6.7 | 7.3 |
| Impossible Travel | Calseta | 6.7 | 4.7 | 8.3 |
| Suspicious PowerShell | Naive | 8.0 | 5.3 | 6.7 |
| Suspicious PowerShell | Calseta | 8.0 | 7.7 | 8.0 |

## Identified Failure Modes

### 1. Calseta agent hallucinates enrichment data
The Calseta agent fabricates threat intelligence — inventing Tor associations, adding fictional threat scores, and inserting indicators not present in the actual data. This happens most on scenarios where the normalized payload is concise, suggesting the agent fills contextual gaps with confabulation.

**Affected scenarios:** Anomalous Data Transfer (all 3 Claude runs), Impossible Travel (all 3 Claude runs)

### 2. Calseta agent loses contextual detail from normalization
Key attack-pattern details present in raw SIEM payloads are lost during normalization:
- "47 failed + 1 successful authentication" (Brute Force)
- "32-minute gap between sign-ins" (Impossible Travel)
- Execution from Temp directory via Outlook parent process (Malware Hash)

These details ground the naive agent's analysis but aren't surfaced in the Calseta normalized payload.

### 3. Account identity confusion
In the Impossible Travel scenario, the Calseta agent confuses r.chen (the actual alert subject) with j.martinez in all 3 Claude runs, suggesting insufficient grounding on identity data.

### 4. Naive Claude agent catastrophically fails on malware hash
Without pre-enrichment, Claude's naive agent incorrectly concludes Emotet malware is a false positive (Accuracy: 2.0/10). This is the strongest argument for pre-enrichment — it prevents dangerous misclassification that could lead to uncontained malware.

## Conclusions

1. **On GPT-4o, Calseta achieves quality parity with 87% fewer tokens** — a clean efficiency win.
2. **On Claude, there is a real quality tradeoff** — Calseta prevents catastrophic failures (malware hash) but loses contextual richness that Claude leverages well.
3. **Actionability consistently improves** with structured input (8.5-9.0 vs 7.4-9.0).
4. **The quality gap is addressable** — better prompt grounding, preserving contextual signals in normalization, and anti-hallucination instructions should close the gap.
5. **The malware hash scenario is the strongest case for pre-enrichment** — it shows the approach isn't just about cost reduction, it's about investigation safety.

## Recommended Improvements

1. Ground the Calseta agent prompt to explicitly state: only analyze data provided, do not invent enrichment results
2. Surface key contextual details (attack patterns, timing, counts) from raw_payload in the alert context
3. Ensure the normalized alert preserves identity information clearly (who is the subject of the alert)
4. Re-run the study after improvements to measure quality impact

## Methodology Notes

- Judge model: Claude Sonnet (claude-sonnet-4-20250514)
- Temperature: 0 (deterministic judging)
- Findings evaluated in randomized order (blind — judge didn't know which approach produced each finding)
- Ground truth: hand-crafted expected indicators and conclusions per scenario
- N=3 runs per scenario per approach per model = 60 total evaluations
