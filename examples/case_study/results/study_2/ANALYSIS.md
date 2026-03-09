# Study 2 Analysis — Study 1 → Study 2 Comparison

## What Changed in Study 2

Three targeted fixes based on Study 1's identified failure modes:

1. **Anti-hallucination grounding** — System prompt explicitly instructs the agent to ONLY use data provided, never fabricate enrichment results or threat scores.
2. **Alert description field** — Agent now receives the full alert description (narrative context from SIEM), including attack patterns, timing, and scope.
3. **Description extraction** — Source-specific extraction from `raw_payload` as fallback (Sentinel: `properties.description`, Elastic: `rule.description/reason`, Splunk: `signature/_raw`).

## Quality: Did We Get Better?

### Study 1 → Study 2 Overall Scores (Claude as Judge)

| Agent | Study 1 | Study 2 | Delta |
|-------|---------|---------|-------|
| Claude + Calseta | 7.6 | **8.4** | **+0.8** |
| Claude + Naive | 8.7 | 8.2 | -0.5 |
| GPT-4o + Calseta | 7.7 | **8.1** | **+0.4** |
| GPT-4o + Naive | 7.5 | 7.4 | -0.1 |

The quality gap flipped for the Claude judge. In Study 1, Claude naive led Calseta by 1.1 points. In Study 2, Calseta leads by 0.2.

### Study 1 → Study 2 Overall Scores (GPT-4o as Judge)

| Agent | Study 1 | Study 2 | Delta |
|-------|---------|---------|-------|
| Claude + Calseta | 7.5 | **7.8** | **+0.3** |
| Claude + Naive | 8.3 | 8.3 | 0.0 |
| GPT-4o + Calseta | 7.8 | 7.6 | -0.2 |
| GPT-4o + Naive | 8.1 | 8.1 | 0.0 |

GPT-4o judge tells a more conservative story — Claude Calseta improved, but baseline still leads by 0.5 (down from 0.8).

### Biggest Per-Scenario Improvements (Claude Judge)

| Scenario | Metric | Study 1 | Study 2 |
|----------|--------|---------|---------|
| Impossible Travel (Claude, Calseta) | Accuracy | **4.0** | **8.0** |
| Impossible Travel (Claude, Calseta) | Completeness | 6.0 | 9.0 |
| Brute Force (Claude, Calseta) | All 3 | 8.0/8.3/9.7 | **10.0/10.0/10.0** |
| Known Malware Hash (Claude, Calseta) | Accuracy | 8.3 | **9.0** |

The identity confusion on Impossible Travel (r.chen vs j.martinez) and the hallucinated enrichment data — both Study 1's top failure modes — are largely resolved.

## The Judge Disagreement Problem

The two judges disagree on who wins overall:

**Claude as judge** — Calseta wins on both models:
- Claude agent: 8.4 vs 8.2 (Calseta +0.2)
- GPT-4o agent: 8.1 vs 7.4 (Calseta +0.7)

**GPT-4o as judge** — Baseline wins on both models:
- Claude agent: 8.3 vs 7.8 (Baseline +0.5)
- GPT-4o agent: 8.1 vs 7.6 (Baseline +0.5)

### Why They Disagree

The judges weight dimensions differently:

- **Claude as judge** heavily rewards **actionability** — where Calseta consistently outperforms (9.2 vs 8.5, 8.9 vs 7.3). Structured input → structured recommendations.
- **GPT-4o as judge** weights **completeness and accuracy** more — and penalizes Calseta for missing raw details the baseline agent had access to.

Neither judge is wrong. They measure different things.

### What's Defensible

- **Actionability**: Calseta is definitively better. Both judges agree.
- **Accuracy**: Roughly even (Claude judge) or baseline slightly ahead (GPT-4o judge). The malware hash scenario is the exception — Calseta is dramatically better there (9.0 vs 1.7).
- **Completeness**: Baseline slightly ahead. Expected — the naive agent has access to more verbose raw data.
- **Overall gap**: Less than 1 point in the worst case (GPT-4o judge).

## Cost: Effectively Unchanged

| Model | Calseta Cost (S1) | Calseta Cost (S2) | Token Reduction |
|-------|-------------------|-------------------|-----------------|
| GPT-4o | $0.01414 | $0.01423 | 86.9% (was 87.0%) |
| Claude | $0.02352 | $0.02459 | 97.1% (was 97.3%) |

The description field adds ~170–190 tokens per alert — negligible impact on the cost story.

## Study 1 Failure Modes — Resolution Status

| Failure Mode | Study 1 | Study 2 | Status |
|-------------|---------|---------|--------|
| Hallucinated enrichment data | Calseta agent fabricated threat scores on Anomalous Data Transfer and Impossible Travel | Anti-hallucination prompt grounding added | Largely resolved — accuracy improved significantly |
| Lost contextual detail from normalization | Key attack patterns (47 failed + 1 successful auth, 32-min travel gap) missing from normalized payload | Alert description field now surfaces these details | Resolved — completeness scores improved |
| Account identity confusion | r.chen confused with j.martinez on Impossible Travel | Description field provides explicit identity context | Resolved — Impossible Travel accuracy 4.0 → 8.0 |
| Naive Claude fails on malware hash | Baseline scored 2.0/10 accuracy without pre-enrichment | Still fails (1.7/10 with Claude judge) | Not our bug — strongest argument for pre-enrichment |

## Marketing Implications

The original marketing copy claimed "matches or exceeds baseline quality." This is only true from the Claude judge's perspective. Updated to:

- **Claim**: "Comparable quality with dramatically better efficiency and safety"
- **Lead with**: Actionability improvement (defensible from both judges)
- **Lead with**: Safety — malware misclassification prevention (1.7 vs 9.0)
- **Acknowledge**: Quality gap is < 1 point even in worst case
- **Present both judges**: Let readers draw conclusions

## Open Questions for Study 3

1. Can the Anomalous Data Transfer completeness gap be closed? Calseta scores 6.0–7.0 vs baseline 9.0–9.7 — the largest remaining gap.
2. Would adding more structured context (e.g., data transfer volume, source/destination details) to the normalized payload help?
3. Is the GPT-4o judge's preference for completeness a bias, or does it reflect genuine information loss in normalization?
4. Would human SOC analyst evaluation align more with Claude judge or GPT-4o judge?
