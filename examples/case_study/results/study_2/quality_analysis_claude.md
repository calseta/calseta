# Quality Analysis — Judge: claude

Generated at 2026-03-08T12:15:36.376831+00:00 using claude as the blind judge.

## Overall Averages

| Model | Approach | Completeness | Accuracy | Actionability | Overall |
|---|---|---|---|---|---|
| claude | naive | 8.5 | 7.7 | 8.5 | 8.2 |
| claude | calseta | 8.2 | 7.7 | 9.2 | 8.4 |
| gpt4o | naive | 8.3 | 6.6 | 7.3 | 7.4 |
| gpt4o | calseta | 8.3 | 7.1 | 8.9 | 8.1 |

## Per-Scenario Breakdown

### claude

| Scenario | Approach | Completeness | Accuracy | Actionability |
|---|---|---|---|---|
| Elastic: Suspicious PowerShell | naive | 10.0 | 9.7 | 9.3 |
| Elastic: Suspicious PowerShell | calseta | 8.0 | 7.7 | 9.0 |
| Splunk: Anomalous Data Transfer | naive | 9.7 | 9.7 | 10.0 |
| Splunk: Anomalous Data Transfer | calseta | 6.0 | 4.0 | 8.0 |
| Sentinel: Impossible Travel | naive | 9.0 | 7.3 | 9.3 |
| Sentinel: Impossible Travel | calseta | 9.0 | 8.0 | 10.0 |
| Elastic: Known Malware Hash | naive | 4.0 | 1.7 | 4.3 |
| Elastic: Known Malware Hash | calseta | 8.0 | 9.0 | 9.0 |
| Sentinel: Brute Force from TOR | naive | 10.0 | 10.0 | 9.3 |
| Sentinel: Brute Force from TOR | calseta | 10.0 | 10.0 | 10.0 |

### gpt4o

| Scenario | Approach | Completeness | Accuracy | Actionability |
|---|---|---|---|---|
| Elastic: Known Malware Hash | naive | 7.7 | 4.0 | 6.3 |
| Elastic: Known Malware Hash | calseta | 7.7 | 8.7 | 9.0 |
| Elastic: Suspicious PowerShell | naive | 7.7 | 4.7 | 6.7 |
| Elastic: Suspicious PowerShell | calseta | 8.0 | 8.3 | 9.0 |
| Sentinel: Impossible Travel | naive | 8.0 | 6.0 | 7.0 |
| Sentinel: Impossible Travel | calseta | 8.0 | 6.0 | 9.0 |
| Splunk: Anomalous Data Transfer | naive | 8.0 | 8.3 | 7.7 |
| Splunk: Anomalous Data Transfer | calseta | 8.3 | 4.3 | 8.7 |
| Sentinel: Brute Force from TOR | naive | 10.0 | 10.0 | 9.0 |
| Sentinel: Brute Force from TOR | calseta | 9.7 | 8.3 | 9.0 |

