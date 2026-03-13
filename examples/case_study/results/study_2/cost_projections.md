# Calseta Case Study — Cost Projections

Generated from observed metrics in `raw_metrics.csv`. All costs are LLM API costs only (no infrastructure).

## Per-Alert Cost (Observed Averages)

| Model | Approach | Avg Input Tokens | Avg Output Tokens | Avg Total Tokens | Avg Tool Calls | Avg Cost ($) |
|---|---|---|---|---|---|---|
| GPT-4o | calseta | 2,656 | 759 | 3,414 | 0.0 | $0.014227 |
| GPT-4o | naive | 20,218 | 802 | 21,020 | 4.1 | $0.058567 |
| Claude Sonnet | calseta | 3,035 | 1,032 | 4,067 | 0.0 | $0.024590 |
| Claude Sonnet | naive | 105,707 | 1,797 | 107,505 | 5.1 | $0.344078 |

## Monthly Cost at Scale (LLM Only)

| Model | Approach | 1 alerts/day | 10 alerts/day | 100 alerts/day | 1000 alerts/day |
|---|---|---|---|---|---|
| GPT-4o | calseta | $0.43 | $4.27 | $42.68 | $426.81 |
| GPT-4o | naive | $1.76 | $17.57 | $175.70 | $1,757.01 |
| Claude Sonnet | calseta | $0.74 | $7.38 | $73.77 | $737.69 |
| Claude Sonnet | naive | $10.32 | $103.22 | $1,032.24 | $10,322.35 |

## Engineering Time Comparison

Building an AI SOC agent requires different levels of engineering effort depending on the approach.

| Component | Naive Agent | Calseta Agent |
|---|---|---|
| Tool definitions & API integration | 40-80 hrs | 0 hrs |
| Enrichment pipeline (rate limits, caching, retry) | Included above | 0 hrs (platform handles) |
| Prompt engineering for raw payloads | 10-20 hrs | 0 hrs |
| Agent integration with Calseta REST API | N/A | 1-2 hrs |
| **Total estimated** | **40-80 hrs** | **1-2 hrs** |

## Year 1 Total Cost of Ownership

Combines engineering time (one-time) + 12 months of LLM API costs.

| Component | GPT-4o Naive | GPT-4o Calseta | Claude Sonnet Naive | Claude Sonnet Calseta |
|---|---|---|---|---|
| Engineering (one-time) | $4,000-$8,000 | $100-$200 | $4,000-$8,000 | $100-$200 |
| LLM costs (12 mo, 10 alerts/day) | $213.77 | $51.93 | $1,255.89 | $89.75 |
| LLM costs (12 mo, 100 alerts/day) | $2,137.70 | $519.29 | $12,558.86 | $897.53 |

## Token Reduction Summary

| Model | Input Token Reduction | Cost Reduction |
|---|---|---|
| GPT-4o | +86.9% | +75.7% |
| Claude Sonnet | +97.1% | +92.9% |

---

*These projections are based on observed metrics from the validation case study using synthetic alert fixtures. Production costs will vary based on alert complexity, payload size, and enrichment depth.*
