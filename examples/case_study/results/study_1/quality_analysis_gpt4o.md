# Quality Analysis — Judge: gpt4o

Generated at 2026-03-08T05:04:47.655637+00:00 using gpt4o as the blind judge.

## Overall Averages

| Model | Approach | Completeness | Accuracy | Actionability | Overall |
|---|---|---|---|---|---|
| claude | naive | 8.2 | 7.6 | 9.1 | 8.3 |
| claude | calseta | 7.5 | 6.2 | 8.7 | 7.5 |
| gpt4o | naive | 8.1 | 7.6 | 8.6 | 8.1 |
| gpt4o | calseta | 7.9 | 6.7 | 8.9 | 7.8 |

## Per-Scenario Breakdown

### claude

| Scenario | Approach | Completeness | Accuracy | Actionability |
|---|---|---|---|---|
| Elastic: Known Malware Hash | naive | 5.0 | 3.0 | 7.0 |
| Elastic: Known Malware Hash | calseta | 7.7 | 6.7 | 8.7 |
| Sentinel: Brute Force from TOR | naive | 9.7 | 10.0 | 10.0 |
| Sentinel: Brute Force from TOR | calseta | 8.0 | 7.7 | 9.3 |
| Splunk: Anomalous Data Transfer | naive | 9.0 | 9.0 | 10.0 |
| Splunk: Anomalous Data Transfer | calseta | 7.7 | 5.7 | 8.7 |
| Elastic: Suspicious PowerShell | naive | 9.0 | 8.3 | 9.3 |
| Elastic: Suspicious PowerShell | calseta | 8.0 | 7.0 | 9.0 |
| Sentinel: Impossible Travel | naive | 8.3 | 7.7 | 9.3 |
| Sentinel: Impossible Travel | calseta | 6.0 | 4.0 | 8.0 |

### gpt4o

| Scenario | Approach | Completeness | Accuracy | Actionability |
|---|---|---|---|---|
| Sentinel: Brute Force from TOR | naive | 10.0 | 10.0 | 10.0 |
| Sentinel: Brute Force from TOR | calseta | 8.0 | 7.0 | 9.0 |
| Sentinel: Impossible Travel | naive | 8.3 | 8.0 | 9.0 |
| Sentinel: Impossible Travel | calseta | 7.7 | 6.7 | 8.7 |
| Elastic: Known Malware Hash | naive | 7.0 | 5.7 | 8.0 |
| Elastic: Known Malware Hash | calseta | 7.7 | 6.7 | 8.7 |
| Elastic: Suspicious PowerShell | naive | 7.3 | 6.0 | 7.3 |
| Elastic: Suspicious PowerShell | calseta | 8.0 | 7.0 | 9.0 |
| Splunk: Anomalous Data Transfer | naive | 8.0 | 8.3 | 8.7 |
| Splunk: Anomalous Data Transfer | calseta | 8.0 | 6.3 | 9.0 |

