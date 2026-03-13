# Study 1 — Baseline

Initial case study run. No prompt engineering or normalization changes.

## Agent Configuration
- Naive agent: raw SIEM JSON + tool calls for enrichment
- Calseta agent: normalized alert + pre-enriched indicators
- No anti-hallucination grounding in system prompt
- No alert description in Calseta agent context

## Key Findings
- GPT-4o: 87% input token reduction, ~75% cost reduction
- Claude: 97% input token reduction, ~93% cost reduction
- Quality gap identified: Calseta agent hallucinated enrichment data and lost contextual details
