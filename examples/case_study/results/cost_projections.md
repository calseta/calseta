# Calseta Case Study — Cost Projections

Generated from observed metrics in `raw_metrics.csv`. All costs are LLM API costs only (no infrastructure).

## Per-Alert Cost (Observed Averages)

| Model | Approach | Avg Input Tokens | Avg Output Tokens | Avg Total Tokens | Avg Tool Calls | Avg Cost ($) |
|---|---|---|---|---|---|---|
| GPT-4o | calseta | 2,487 | 793 | 3,280 | 0.0 | $0.014144 |
| GPT-4o | naive | 19,196 | 806 | 20,001 | 4.1 | $0.056047 |
| Claude Sonnet | calseta | 2,844 | 999 | 3,844 | 0.0 | $0.023522 |
| Claude Sonnet | naive | 105,101 | 1,803 | 106,904 | 5.1 | $0.342345 |

## Monthly Cost at Scale (LLM Only)

| Model | Approach | 1 alerts/day | 10 alerts/day | 100 alerts/day | 1000 alerts/day |
|---|---|---|---|---|---|
| GPT-4o | calseta | $0.42 | $4.24 | $42.43 | $424.32 |
| GPT-4o | naive | $1.68 | $16.81 | $168.14 | $1,681.40 |
| Claude Sonnet | calseta | $0.71 | $7.06 | $70.57 | $705.67 |
| Claude Sonnet | naive | $10.27 | $102.70 | $1,027.03 | $10,270.34 |

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
| LLM costs (12 mo, 10 alerts/day) | $204.57 | $51.63 | $1,249.56 | $85.86 |
| LLM costs (12 mo, 100 alerts/day) | $2,045.70 | $516.26 | $12,495.58 | $858.56 |

## Token Reduction Summary

| Model | Input Token Reduction | Cost Reduction |
|---|---|---|
| GPT-4o | +87.0% | +74.8% |
| Claude Sonnet | +97.3% | +93.1% |

---

*These projections are based on observed metrics from the validation case study using synthetic alert fixtures. Production costs will vary based on alert complexity, payload size, and enrichment depth.*
