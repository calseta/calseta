# Calseta — Validation Case Study

## Purpose

This document presents the methodology, results, and analysis of a controlled comparison between two approaches to AI-powered security alert investigation:

- **Approach A (Naive Agent):** An AI agent receives raw alert JSON from the source SIEM, extracts indicators via tool calls, calls enrichment APIs directly, parses raw API responses, and synthesizes findings with no pre-loaded context.
- **Approach B (Calseta Agent):** The same alert is ingested by Calseta, processed through the full normalization and enrichment pipeline, and delivered to the agent as a structured payload with pre-computed enrichment, detection rule documentation, and applicable runbooks.

The hypothesis: Approach B produces at least 50% fewer input tokens than Approach A across all five scenarios, with equal or better finding quality.

---

## Methodology

### Controlled Variables

| Variable | Value |
|---|---|
| LLMs | Claude Sonnet (latest), GPT-4o |
| Temperature | 0 |
| Max tokens | 4096 |
| Enrichment providers | VirusTotal, AbuseIPDB |
| Alert payloads | 5 synthetic fixtures (identical for both approaches) |
| Runs per scenario per approach per model | 3 |
| Total runs (single model) | 30 |
| Total runs (all models) | 60 |

### Approach A — Naive Agent

The agent receives the raw alert payload directly from the source system:

1. Raw alert JSON passed directly to the context window (full payload, including all nested fields)
2. Agent uses tool calls to identify and extract indicators from the unstructured payload
3. Agent calls enrichment APIs directly (VirusTotal, AbuseIPDB) via tool calls
4. Agent receives raw API responses (typically 2,000-10,000 tokens per response) and must parse them itself
5. Agent has no access to pre-loaded detection rule documentation or runbooks
6. Agent synthesizes findings and produces a structured investigation summary

The naive agent has access to 5 tools: `lookup_ip_virustotal`, `lookup_hash_virustotal`, `lookup_domain_virustotal`, `lookup_url_virustotal`, `lookup_ip_abuseipdb`.

### Approach B — Calseta Agent

The same alert is ingested by Calseta and processed through the full pipeline:

1. Agent receives an alert UUID and fetches structured data from Calseta's REST API
2. Alert data includes: normalized fields, enriched indicators (structured, not raw), detection rule documentation, applicable context documents
3. Agent builds a concise prompt from the pre-structured data — typically under 2,000 tokens
4. Agent produces its finding in a single LLM call with zero tool calls
5. Agent posts the finding back to Calseta via `POST /v1/alerts/{uuid}/findings`

### Quality Evaluation

Findings are evaluated by an independent LLM judge (blind — the judge does not know which approach produced the finding). Three dimensions scored on a 0-10 scale:

- **Completeness:** Did the finding cover all indicators of compromise?
- **Accuracy:** Were the conclusions and risk assessments correct?
- **Actionability:** Were the recommendations specific, useful, and operationally sound?

---

## Test Scenarios

### Scenario 1 — Brute Force from TOR (Sentinel)

**Alert:** Multiple failed sign-in attempts from a known TOR exit node IP (185.220.101.34) targeting user j.martinez@contoso.com. 47 failed attempts followed by one successful authentication.

**Indicators:** 1 IP (TOR exit relay), 1 account, 1 host domain

**Enrichment path:** AbuseIPDB (IP reputation)

### Scenario 2 — Known Malware Hash (Elastic)

**Alert:** Execution of svchost_update.exe on WORKSTATION12, whose SHA-256 hash matches the Emotet banking trojan. Parent process is Outlook (email vector).

**Indicators:** 1 SHA-256 hash, 1 source IP, 1 user account, 1 email

**Enrichment path:** VirusTotal (hash analysis, detection count), AbuseIPDB (IP)

### Scenario 3 — Anomalous Outbound Data Transfer (Splunk)

**Alert:** 2GB+ data transfer from internal server FILESERVER03 to external IP 45.33.32.156 via service account svc_backup using custom_sync.exe.

**Indicators:** 1 source IP (internal), 1 destination IP, 1 domain, 1 URL, 1 user account

**Enrichment path:** VirusTotal (IP, domain), AbuseIPDB (IP)

### Scenario 4 — Impossible Travel (Sentinel)

**Alert:** User r.chen@contoso.com (Global Administrator) authenticated from New York at 09:15 UTC and Moscow at 09:47 UTC — 32-minute gap, ~7,500km distance.

**Indicators:** 1 account (Global Admin), 2 IPs (NY + Moscow), 1 host domain, 1 URL

**Enrichment path:** AbuseIPDB (IPs)

### Scenario 5 — Suspicious PowerShell Execution (Elastic)

**Alert:** Encoded PowerShell command on DC01 (domain controller) bypassing execution policy, running as SYSTEM, downloading a stager from c2-relay.darkops.net.

**Indicators:** 1 C2 domain, 1 destination IP, 1 URL, 1 process hash, 1 DNS query

**Enrichment path:** VirusTotal (domain, URL, hash), AbuseIPDB (IP)

---

## Results

> **Note:** The tables below are templates. Run the study (`python run_study.py --ingest --run`) and evaluation (`python evaluate_findings.py`) to populate with actual data.

### Token Usage and Cost

| Scenario | Approach | Avg Input Tokens | Avg Output Tokens | Avg Total Tokens | Avg Tool Calls | Avg API Calls | Avg Duration (s) | Avg Cost ($) |
|---|---|---|---|---|---|---|---|---|
| Brute Force TOR | Naive | — | — | — | — | — | — | — |
| Brute Force TOR | Calseta | — | — | — | — | — | — | — |
| Malware Hash | Naive | — | — | — | — | — | — | — |
| Malware Hash | Calseta | — | — | — | — | — | — | — |
| Data Transfer | Naive | — | — | — | — | — | — | — |
| Data Transfer | Calseta | — | — | — | — | — | — | — |
| Impossible Travel | Naive | — | — | — | — | — | — | — |
| Impossible Travel | Calseta | — | — | — | — | — | — | — |
| PowerShell | Naive | — | — | — | — | — | — | — |
| PowerShell | Calseta | — | — | — | — | — | — | — |

### Overall Averages

| Metric | Naive (Avg) | Calseta (Avg) | Reduction |
|---|---|---|---|
| Input tokens | — | — | —% |
| Output tokens | — | — | —% |
| Total tokens | — | — | —% |
| Tool calls | — | 0 | —% |
| External API calls | — | 0 | —% |
| Duration (seconds) | — | — | —% |
| Cost per alert ($) | — | — | —% |

### Quality Scores

| Scenario | Approach | Completeness (0-10) | Accuracy (0-10) | Actionability (0-10) | Overall |
|---|---|---|---|---|---|
| Brute Force TOR | Naive | — | — | — | — |
| Brute Force TOR | Calseta | — | — | — | — |
| Malware Hash | Naive | — | — | — | — |
| Malware Hash | Calseta | — | — | — | — |
| Data Transfer | Naive | — | — | — | — |
| Data Transfer | Calseta | — | — | — | — |
| Impossible Travel | Naive | — | — | — | — |
| Impossible Travel | Calseta | — | — | — | — |
| PowerShell | Naive | — | — | — | — |
| PowerShell | Calseta | — | — | — | — |

---

## Analysis

### Input Token Reduction

**Target:** >=50% input token reduction for Approach B vs. Approach A.

**Result:** — (run the study to populate)

**Why the reduction is expected:**

1. **Raw SIEM payloads are verbose.** A single Sentinel incident webhook is 2,000-5,000 tokens. An Elastic alert with ECS fields is 1,500-4,000 tokens. These include nested metadata, GUIDs, ARM resource paths, and redundant fields that are irrelevant to investigation.

2. **Raw enrichment API responses are massive.** A VirusTotal file hash response is 5,000-15,000 tokens (72 engine results, full metadata). AbuseIPDB returns verbose report arrays. The naive agent dumps all of this into its context window via tool call responses.

3. **Calseta delivers structured, minimal data.** The normalized alert is ~200 tokens. Each enriched indicator with extracted fields is ~100-200 tokens. Total context for the Calseta agent: typically 500-2,000 tokens vs. 10,000-50,000 for the naive agent.

4. **Calseta eliminates tool call overhead.** Each tool call round-trip re-sends the entire conversation history (all previous messages). The naive agent's 3-8 tool calls cause cumulative token inflation that grows with each enrichment step.

### Quality Comparison

The Calseta agent is expected to produce equal or better quality findings because:

- **Complete enrichment coverage:** Calseta's pipeline enriches all indicators in parallel. The naive agent may skip enrichment for some indicators due to tool call limits or model decisions.
- **Structured context:** Pre-labeled fields (malice verdict, enrichment source, indicator type) reduce the chance of misinterpretation.
- **Detection rule documentation:** The Calseta agent receives the detection rule's documentation field, providing context the naive agent lacks entirely.
- **Applicable runbooks:** Context documents matched by targeting rules give the Calseta agent specific operational guidance.

### Cross-Provider Validation

The study runs on both Claude Sonnet and GPT-4o to confirm that Calseta's token reduction is not model-specific. Both models use the same:
- Alert fixtures and enrichment data
- System prompts and tool definitions
- Temperature (0) and max tokens (4096)

Token accounting differs slightly between providers (Anthropic reports `input_tokens`/`output_tokens`; OpenAI reports `prompt_tokens`/`completion_tokens`), but both count BPE tokens similarly.

### Cost Projections

Run `python cost_projections.py` after the study to generate:
- Per-alert cost comparison by model and approach
- Monthly cost projections at 1/10/100/1000 alerts per day
- Year 1 TCO including engineering time estimates

Results are written to `results/cost_projections.md`.

### Limitations

1. **Synthetic fixtures.** The alert payloads are realistic but synthetic. Production payloads may vary in size and complexity.

2. **Enrichment provider availability.** If enrichment APIs are unavailable during the study, the naive agent's tool calls will fail, biasing results. The Calseta agent uses pre-computed enrichment, so provider availability affects ingestion but not the agent's investigation.

3. **Two models tested.** Results cover Claude Sonnet and GPT-4o. Other models may show different token usage patterns.

4. **Three runs per scenario.** While sufficient to account for basic non-determinism, a larger sample would provide tighter confidence intervals.

---

## Reproducing the Study

### Prerequisites

- A running Calseta instance: `docker compose up`
- Python 3.12+ with `anthropic`, `openai`, and `httpx` packages
- API keys: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `VIRUSTOTAL_API_KEY`, `ABUSEIPDB_API_KEY`, `CALSETA_API_KEY`

### Steps

```bash
# 1. Navigate to the case study directory
cd examples/case_study

# 2. Create a .env file with your API keys
cat > .env << 'EOF'
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
VIRUSTOTAL_API_KEY=...
ABUSEIPDB_API_KEY=...
CALSETA_BASE_URL=http://localhost:8000
CALSETA_API_KEY=cai_...
EOF

# 3. Install dependencies
pip install anthropic openai httpx

# 4. Ingest fixtures and run the study
python run_study.py --ingest --run

# 5. Run with both models (Claude + GPT-4o)
python run_study.py --run --models all

# 6. Evaluate finding quality
python evaluate_findings.py

# 7. Generate cost projections
python cost_projections.py

# 8. Results are in results/
#    - raw_metrics.csv       — token counts, costs, timing
#    - quality_scores.csv    — blind judge quality scores
#    - cost_projections.md   — cost analysis and projections
#    - findings/             — raw finding text from each run
#    - alert_uuids.json      — UUIDs of ingested fixtures
```

The `--models` flag accepts `claude` (default), `openai`, or `all`.

---

## Output Artifacts

| File | Description |
|---|---|
| `examples/case_study/fixtures/` | 5 synthetic alert payloads in source-native format |
| `examples/case_study/naive_agent.py` | Approach A — Anthropic Claude agent |
| `examples/case_study/calseta_agent.py` | Approach B — Anthropic Claude agent |
| `examples/case_study/openai_agent.py` | Cross-provider validation — OpenAI GPT-4o agents |
| `examples/case_study/run_study.py` | Study runner (ingestion + benchmark, multi-model) |
| `examples/case_study/evaluate_findings.py` | Blind LLM judge evaluator |
| `examples/case_study/cost_projections.py` | Cost projection calculator |
| `examples/case_study/results/raw_metrics.csv` | Token usage, costs, timing per run |
| `examples/case_study/results/quality_scores.csv` | Quality scores per finding |
| `examples/case_study/results/cost_projections.md` | Cost analysis and scale projections |
| `examples/case_study/results/findings/` | Raw finding text from each agent run |
| `docs/project/VALIDATION_CASE_STUDY.md` | This document |
