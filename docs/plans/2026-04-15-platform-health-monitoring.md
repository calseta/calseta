# Platform Health Monitoring

**Date**: 2026-04-15
**Author**: Jorge Castro
**Status**: Draft

## Problem Statement

Calseta operators have no visibility into the health of the platform itself. Today, the only signal is a `/health` endpoint that returns "ok" or "down" for the database and queue. There's no way to answer:

- Are my agents healthy? How many are stalled, over-budget, or failing?
- Is my PostgreSQL instance running hot? How many connections are open?
- Is the task queue backing up? What's the oldest pending job?
- Is the API responsive? What's p99 latency through the load balancer?
- Did that Lambda function I use for webhook relay start erroring?

These questions require logging into AWS Console, Azure Portal, or Grafana — context-switching away from the platform where the operator is already working. For a self-hosted SOC platform, this is a gap: the tool that monitors security should be able to monitor itself.

This PRD adds a `/health` page to Calseta with three tabs:

1. **Agents** — fleet status, run metrics, costs, errors, stalls (data from the agent runtime)
2. **Infrastructure** — cloud service metrics pulled from AWS CloudWatch or Azure Monitor
3. **Custom** — user-configured metrics from any CloudWatch namespace or Azure Monitor resource

The infrastructure monitoring is fully configurable — any AWS service that emits CloudWatch metrics can be onboarded. Calseta ships with presets for the services it deploys on (ECS, RDS, SQS, ALB). Azure Monitor support follows the same pattern.

## Solution

When this ships, a Calseta operator will be able to:

- **See platform health at a glance** — navigate to `/health` and see agent fleet status, infrastructure metrics, and custom metrics in a tabbed view
- **Connect their AWS account** — provide an IAM role ARN, and Calseta assumes that role to pull CloudWatch metrics. No AWS credentials stored — just the role ARN and an external ID for cross-account trust.
- **Pick from presets** — one-click onboarding for ECS, RDS, SQS, ALB, Lambda. Calseta knows which metrics matter for each service and pre-configures the cards.
- **Add any CloudWatch metric** — specify namespace, metric name, dimensions, and stat (Average, Sum, Maximum). Calseta creates a card for it.
- **Connect their Azure subscription** — provide a Managed Identity or Service Principal. Same pattern, Azure Monitor API.
- **See agent health alongside infrastructure** — same page, different tabs. An operator investigating a stalled agent can check if the database is healthy without leaving Calseta.

## User Stories

### Infrastructure Monitoring (AWS)

1. As a platform engineer, I want to connect my AWS account to Calseta by providing an IAM role ARN so that Calseta can pull CloudWatch metrics without storing long-lived credentials.
2. As a platform engineer, I want to configure an external ID for cross-account role assumption so that my IAM trust policy follows AWS security best practices.
3. As a platform engineer, I want to select from presets (ECS, RDS, SQS, ALB, Lambda) so that I can onboard common services in one click without knowing CloudWatch metric names.
4. As a platform engineer, I want to add any CloudWatch metric by specifying namespace, metric name, dimensions, and statistic so that I can monitor custom services.
5. As a platform engineer, I want to configure the polling interval per health source (minimum 60s) so that I can balance freshness against API costs.
6. As a platform engineer, I want to see CloudWatch metrics rendered as time-series charts with configurable time windows (1h, 6h, 24h, 7d) so that I can spot trends.
7. As a platform engineer, I want to remove a configured metric without affecting other metrics so that I can clean up my view.
8. As a platform engineer, I want to test my IAM role connection before saving so that I know the credentials work before relying on them.

### Infrastructure Monitoring (Azure)

9. As a platform engineer, I want to connect my Azure subscription via Managed Identity or Service Principal so that Calseta can pull Azure Monitor metrics.
10. As a platform engineer, I want the same preset and custom metric experience for Azure Monitor as for AWS CloudWatch.

### Agent Health (Tab)

11. As a SOC manager, I want to see agent fleet health on the `/health` page so that I can monitor agents alongside infrastructure in one view.
12. As a SOC manager, I want agent health cards showing: fleet status, success rate, error rate, spend MTD, active investigations, stall detections, orphan recoveries.
13. As a platform engineer, I want to see per-agent error rates and run status distribution so that I can identify problematic agents.

### Configuration & Management

14. As a platform engineer, I want to manage health sources (create, update, delete, test) via both API and UI so that I can automate configuration.
15. As a platform engineer, I want health source credentials (role ARN, external ID) encrypted at rest so that they are secure.
16. As a platform engineer, I want to see the last successful metric fetch time and any errors so that I know if polling is working.
17. As a platform engineer, I want the health page to degrade gracefully if a cloud provider is unreachable — show stale data with a warning, not a blank page.

### Page Structure

18. As any user, I want the `/health` page to have three tabs: Agents, Infrastructure, Custom — so that I can navigate to the metrics I care about.
19. As a platform engineer, I want each tab to have its own set of configurable cards (independent of the home dashboard cards) so that health monitoring is self-contained.
20. As a platform engineer, I want to see a "last updated" timestamp on each card so that I know how fresh the data is.

## Implementation Decisions

### `/health` Page Structure

```
/health
  ├── Agents tab          ← data from Calseta's own DB (agent tables)
  ├── Infrastructure tab  ← data from CloudWatch / Azure Monitor
  └── Custom tab          ← user-defined CloudWatch / Azure Monitor metrics
```

The Agents tab uses the same card components as the home dashboard but is a separate card set — adding/removing cards on `/health` does not affect the home dashboard. The card catalog (from runtime hardening D5) is reused as a component but backed by a different card registry.

### Health Source Cards vs. Dashboard Cards

These are **separate systems**. The home dashboard (`/`) has its own card catalog with alert, workflow, and summary metrics. The health page (`/health`) has its own card set focused on operational health. They share the card rendering components (StatCard, KpiCard, ChartCard) but have independent registries and independent localStorage persistence.

Rationale: different audiences, different refresh rates, different data sources. A SOC analyst configuring their alert dashboard shouldn't accidentally affect the platform engineer's health view.

### Cloud Provider Integration Architecture

#### Option A: Periodic Worker Task (Recommended)

A procrastinate periodic task (`poll_health_metrics_task`) runs every N seconds (configurable per source, minimum 60s). For each active health source, it assumes the IAM role, calls `GetMetricData`, and writes results to a `health_metrics` table. The UI reads from this table via a REST endpoint.

```
┌─────────────────────┐
│  Worker Process      │
│  (periodic task)     │
│                      │
│  poll_health_metrics │──→ STS AssumeRole
│  every 60s           │──→ CloudWatch GetMetricData
│                      │──→ INSERT health_metrics
└──────────┬──────────┘
           │
     ┌─────┴──────┐
     │ PostgreSQL  │
     │ health_     │
     │ metrics     │
     └─────┬──────┘
           │
     ┌─────┴──────┐
     │ API Server  │
     │ GET /v1/    │
     │ health/     │
     │ metrics     │──→ React Query (refetchInterval: 60s)
     └────────────┘
```

**Pros:**
- Uses existing worker infrastructure (procrastinate). No new processes.
- Metrics are persisted — survives API restarts, queryable for historical trends.
- CloudWatch API calls are batched (up to 500 metrics per `GetMetricData` call) — efficient.
- Failure isolated: if CloudWatch is down, stale metrics are served from DB with a "last updated" warning.

**Cons:**
- Minimum latency = polling interval (60s). Not real-time.
- Worker must have network access to AWS/Azure APIs (already true for secrets backends).
- DB storage grows over time (mitigated by retention policy).

#### Option B: API-Server In-Memory Cache

The API server fetches metrics on-demand when the `/health` page is loaded. Results are cached in-memory with TTL. No worker involvement.

**Pros:**
- Simpler — no new task, no new table. Fewer moving parts.
- Fresher data — fetched when the user actually looks at the page.

**Cons:**
- No persistence — metrics lost on API restart. No historical trends.
- Cold cache on first load — user waits 2-5s for CloudWatch API round-trip.
- Thundering herd: if 10 users load `/health` simultaneously, 10 CloudWatch API calls (unless cache is shared, which requires careful locking).
- Doesn't work if API server can't reach AWS (network isolation between API and worker is common in enterprise deployments).

#### Option C: Dedicated Health Poller Process

A new lightweight process (separate from worker) dedicated to health metric polling. Writes to the same `health_metrics` table.

**Pros:**
- Isolated — health polling doesn't compete with alert enrichment/workflow tasks in the worker queue.
- Can run at higher frequency without impacting worker throughput.

**Cons:**
- Another process to manage in Docker Compose / ECS / K8s. Calseta currently has 3 processes (API, worker, MCP). Adding a 4th increases operational complexity.
- Marginal benefit — health polling is lightweight (a few API calls every 60s). Worker can handle it easily.

#### Recommendation: Option A (Periodic Worker Task)

Option A is the clear winner. It uses existing infrastructure, persists data for historical trends, handles failures gracefully, and adds zero operational complexity. The worker already runs periodic tasks (supervisor every 1 minute, routine evaluation every 1 minute, KB sync every 6 hours). Health metric polling is the same pattern.

CloudWatch `GetMetricData` supports up to 500 metrics in a single call with 5-minute resolution. Even a large deployment with 50 configured metrics is a single API call every 60 seconds — negligible load.

### IAM Role Assumption Flow

Same recommendation applies: **periodic worker task assumes the role.**

```
1. User configures health source:
   POST /v1/health-sources
   {
     "provider": "aws",
     "name": "Production AWS",
     "role_arn": "arn:aws:iam::123456789012:role/CalsetaHealthReadOnly",
     "external_id": "calseta-health-abc123",   ← generated by Calseta, user puts in trust policy
     "region": "us-east-1"
   }

2. User creates IAM role in their AWS account:
   Trust policy:
   {
     "Effect": "Allow",
     "Principal": { "AWS": "arn:aws:iam::<calseta-account>:root" },
     "Action": "sts:AssumeRole",
     "Condition": {
       "StringEquals": { "sts:ExternalId": "calseta-health-abc123" }
     }
   }
   Permission policy:
   {
     "Effect": "Allow",
     "Action": [
       "cloudwatch:GetMetricData",
       "cloudwatch:ListMetrics",
       "ecs:DescribeServices",
       "ecs:DescribeClusters",
       "rds:DescribeDBInstances",
       "sqs:GetQueueAttributes",
       "lambda:GetFunctionConfiguration",
       "elasticloadbalancing:DescribeTargetHealth"
     ],
     "Resource": "*"
   }

3. User clicks "Test Connection":
   POST /v1/health-sources/{uuid}/test
   → Worker assumes role via STS, calls cloudwatch:ListMetrics
   → Returns success/failure with error details

4. Periodic polling begins:
   Worker assumes role, calls GetMetricData for configured metrics
   → Writes to health_metrics table
   → STS credentials cached for 1 hour (default session duration)
```

**Security:**
- Role ARN and external ID stored encrypted at rest (same encryption as enrichment provider auth configs).
- No long-lived AWS credentials stored. STS session credentials are ephemeral (1 hour).
- External ID prevents confused deputy attacks.
- Permissions are read-only — Calseta never modifies AWS resources.

### Data Model

#### `health_sources` table

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL PK | — |
| uuid | UUID | External ID |
| name | TEXT | Display name ("Production AWS") |
| provider | TEXT | `aws`, `azure`, `calseta` |
| is_active | BOOLEAN | Enable/disable polling |
| config | JSONB | Provider-specific config (role_arn, region, subscription_id, etc.) |
| auth_config_encrypted | TEXT | Encrypted credentials (role ARN, external ID, client secret) |
| polling_interval_seconds | INTEGER | Default 60, minimum 60 |
| last_poll_at | TIMESTAMPTZ | Last successful poll |
| last_poll_error | TEXT | Last error (null if healthy) |
| created_at | TIMESTAMPTZ | — |
| updated_at | TIMESTAMPTZ | — |

#### `health_metrics_config` table

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL PK | — |
| uuid | UUID | External ID |
| health_source_id | BIGINT FK | Parent source |
| display_name | TEXT | Card title ("ECS CPU Utilization") |
| namespace | TEXT | CloudWatch namespace ("AWS/ECS") or Azure resource type |
| metric_name | TEXT | "CPUUtilization" |
| dimensions | JSONB | `{"ClusterName": "calseta", "ServiceName": "api"}` |
| statistic | TEXT | `Average`, `Sum`, `Maximum`, `Minimum`, `p99` |
| unit | TEXT | `Percent`, `Count`, `Bytes`, `Milliseconds` |
| category | TEXT | `compute`, `database`, `queue`, `network`, `storage`, `custom` |
| card_size | TEXT | `small` (1x1), `wide` (2x1), `large` (2x2) |
| warning_threshold | FLOAT | Yellow when exceeded |
| critical_threshold | FLOAT | Red when exceeded |
| is_active | BOOLEAN | — |
| created_at | TIMESTAMPTZ | — |

#### `health_metrics` table (time-series data)

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL PK | — |
| metric_config_id | BIGINT FK | Which metric |
| value | DOUBLE PRECISION | Metric value |
| timestamp | TIMESTAMPTZ | Metric timestamp |
| raw_datapoints | JSONB | Full CloudWatch response for the period (optional) |

Partitioned by timestamp (monthly) for efficient retention and queries. Retention configurable via `HEALTH_METRICS_RETENTION_DAYS` (default 30).

### Service Presets

When a user adds a health source, they can select presets that auto-configure common metrics:

#### AWS ECS Preset
| Metric | Namespace | Statistic | Thresholds |
|--------|-----------|-----------|------------|
| CPU Utilization | AWS/ECS | Average | warn: 70%, crit: 90% |
| Memory Utilization | AWS/ECS | Average | warn: 75%, crit: 90% |
| Running Task Count | AWS/ECS | Average | warn: <desired, crit: 0 |

#### AWS RDS Preset
| Metric | Namespace | Statistic | Thresholds |
|--------|-----------|-----------|------------|
| CPU Utilization | AWS/RDS | Average | warn: 70%, crit: 90% |
| Database Connections | AWS/RDS | Average | warn: 80% of max, crit: 95% |
| Free Storage Space | AWS/RDS | Average | warn: <20%, crit: <5% |
| Read/Write Latency | AWS/RDS | Average | warn: 20ms, crit: 50ms |

#### AWS SQS Preset
| Metric | Namespace | Statistic | Thresholds |
|--------|-----------|-----------|------------|
| Queue Depth | AWS/SQS | Sum | warn: 100, crit: 1000 |
| Age of Oldest Message | AWS/SQS | Maximum | warn: 300s, crit: 900s |
| Messages Received | AWS/SQS | Sum | — (trend only) |

#### AWS ALB Preset
| Metric | Namespace | Statistic | Thresholds |
|--------|-----------|-----------|------------|
| Request Count | AWS/ApplicationELB | Sum | — (trend only) |
| Target Response Time | AWS/ApplicationELB | p99 | warn: 1s, crit: 5s |
| HTTP 5xx Count | AWS/ApplicationELB | Sum | warn: 10/min, crit: 50/min |
| Healthy Host Count | AWS/ApplicationELB | Minimum | crit: 0 |

#### AWS Lambda Preset
| Metric | Namespace | Statistic | Thresholds |
|--------|-----------|-----------|------------|
| Invocations | AWS/Lambda | Sum | — (trend only) |
| Errors | AWS/Lambda | Sum | warn: 5/min, crit: 20/min |
| Duration | AWS/Lambda | p99 | warn: 80% of timeout, crit: 95% |
| Throttles | AWS/Lambda | Sum | warn: 1, crit: 10 |

### Metric Auto-Discovery

When a user connects an AWS account and selects a preset, Calseta calls `cloudwatch:ListMetrics` and `ecs:DescribeServices` (or equivalent) to discover available dimensions. For example:

1. User selects "ECS" preset
2. Calseta calls `ecs:DescribeClusters` → finds cluster "calseta"
3. Calls `ecs:DescribeServices` → finds services: api, worker, mcp
4. Auto-creates 3 metric configs per service (CPU, Memory, Task Count) = 9 cards
5. User can remove any they don't want

This eliminates manual dimension entry for standard services.

### Cloud Provider Abstraction

```python
class HealthMetricsProvider(ABC):
    """Port for cloud metric providers."""

    @abstractmethod
    async def test_connection(self) -> HealthConnectionResult: ...

    @abstractmethod
    async def fetch_metrics(
        self, configs: list[HealthMetricConfig], period: timedelta
    ) -> list[MetricDatapoint]: ...

    @abstractmethod
    async def discover_resources(self, preset: str) -> list[DiscoveredResource]: ...
```

Two implementations:
- `AWSCloudWatchProvider` — boto3 + STS AssumeRole + GetMetricData
- `AzureMonitorProvider` — azure-monitor-query + DefaultAzureCredential

Both are optional dependencies (`pip install calseta[aws]` / `pip install calseta[azure]`). If the SDK isn't installed and a user tries to create a health source for that provider, the API returns a clear error.

### UI: `/health` Page

**Tab: Agents**
- Reuses agent card components from the runtime hardening dashboard design
- Cards: Fleet Status, Success Rate (7d), Spend MTD, Error Rate (7d), Active Investigations, Stall Detections, Runs by Status (chart), Cost by Agent (chart)
- Refresh: React Query with `refetchInterval: 30000` (30s)

**Tab: Infrastructure**

**Visual reference**: `tmp/health-metric-card-option-b.html` — approved wide 2-column layout.

- **Card layout**: Wide 2-column grid. Each card has value+unit on the left, sparkline chart on the right (side-by-side). Larger sparklines for readable trend shapes.
- **Threshold accent**: 2px top bar (teal=OK at 0.3 opacity, amber=WARN at 0.6, red=CRIT at 0.8). Threshold badge in metric metadata (OK/WARN/CRIT).
- **Card content**: 9px uppercase label, 28px Manrope value, unit, service name, threshold badge, "2s ago" timestamp (bottom-right, subtle)
- **Sparklines**: SVG area charts with colored fill at 0.06 opacity. Dashed threshold line overlay when approaching limit.
- **Section dividers**: Service groups (e.g., "ECS · calseta cluster", "RDS · calseta-db") with 10px uppercase labels
- **Toolbar**: Time window selector (1h/6h/24h/7d), source health indicator (green dot + "Production AWS · us-east-1 · polling OK"), "Add Service" button (teal outline)
- "Add Service" button → preset selector (ECS, RDS, SQS, ALB, Lambda) with auto-discovery
- "Add Custom Metric" button → form for namespace/metric/dimensions/stat
- Refresh: React Query with `refetchInterval: 60000` (60s, matches polling interval)

**Tab: Custom**
- Same card rendering as Infrastructure but for user-defined metrics
- Full CRUD: add, edit thresholds, remove

**Health Source Configuration** (accessible from Infrastructure/Custom tabs):
- "Configure Sources" button → settings sheet (right-edge slide-out)
- List of configured health sources with status indicators (green dot = polling OK, red = error)
- Add source: provider selector (AWS/Azure) → role ARN / credential entry → test connection → save
- Per-source: view polling status, last error, configured metrics count

## Testing Strategy

### Unit Tests
- `AWSCloudWatchProvider`: mock boto3 STS + CloudWatch responses, verify metric parsing
- `AzureMonitorProvider`: mock azure SDK responses, verify metric parsing
- Health metric polling task: mock provider, verify DB writes
- Preset auto-discovery: mock AWS describe calls, verify metric config generation
- Retention cleanup: verify old metrics are purged correctly

### Integration Tests
- Health source CRUD: create, update, test connection (mocked provider), delete
- Metric config CRUD: create from preset, create custom, update thresholds, delete
- Polling lifecycle: create source → configure metrics → trigger poll → verify metrics in DB → verify API returns them
- Graceful degradation: provider unreachable → stale data served with warning

### Test Patterns
- Mock cloud SDKs at the provider level (not HTTP) — `unittest.mock.patch` on boto3 client methods
- Use `freeze_time` for retention policy tests
- Follow existing patterns in `tests/integration/`

## Out of Scope

- **Alerting/paging on health metrics** — no PagerDuty/Slack alerts when thresholds are breached. That's a v2 feature. Users can set up CloudWatch Alarms directly for now.
- **GCP Cloud Monitoring** — AWS and Azure only for v1. GCP follows the same abstraction pattern.
- **Kubernetes metrics** — no direct K8s API integration. Users deploying on K8s can expose metrics via CloudWatch Container Insights or Azure Monitor for containers.
- **Custom metric push** — Calseta pulls metrics. No StatsD/Prometheus endpoint for pushing custom metrics into Calseta.
- **Historical analysis / anomaly detection** — metrics are stored for 30 days for sparklines and trend charts. No ML-based anomaly detection.
- **Cost optimization recommendations** — showing cost metrics but not analyzing them for savings.

## Open Questions

1. **Metric resolution** — CloudWatch supports 1-minute, 5-minute, and 1-hour resolution. Higher resolution = more API calls = higher CloudWatch cost. Default to 5-minute? Make configurable?
2. **Multi-region** — Should a single health source support multiple AWS regions, or does the user create one source per region?
3. **Retention cost** — At 50 metrics x 1 datapoint/minute x 30 days = 2.16M rows. Is this acceptable, or should we aggregate older data (e.g., 1-minute for 24h, 5-minute for 7d, 1-hour for 30d)?
4. **Azure Monitor parity** — Azure Monitor has a different metric model (resource IDs instead of namespace/dimensions). How closely should the UI match between providers? Propose: unified card rendering, provider-specific configuration forms.
5. **Calseta-as-its-own-source** — The "Agents" tab pulls from Calseta's own database. Should this also be modeled as a `health_source` with `provider: "calseta"`, or hardcoded? Recommend hardcoded — it's always available, no configuration needed.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| AWS API rate limits on CloudWatch GetMetricData | Batch up to 500 metrics per call. Default 60s polling. Monitor for throttling errors and back off. |
| Stale credentials after role policy change | Test connection on every source edit. Polling errors surface in UI with "last error" field. |
| Large metric tables slow down queries | Partition `health_metrics` by month. Retention cleanup periodic task. Index on `(metric_config_id, timestamp)`. |
| User configures 500 custom metrics | Enforce per-source metric limit (default 100). GetMetricData handles 500 per call so this is technically fine. |
| Network isolation — worker can't reach AWS | Same risk as existing secrets backends (AWS Secrets Manager). Document network requirements. If unreachable, polling errors are surfaced, stale data served. |
| boto3/azure SDK not installed | Provider returns clear error at source creation time. Health page works without cloud providers (Agents tab is always available). |

## Project Management

### Overview

| Chunk | Wave | Status | Dependencies |
|-------|------|--------|-------------|
| H1: Health source & metric config schema | 1 | pending | — |
| H2: Cloud provider abstraction + AWS implementation | 1 | pending | — |
| H3: Health metric polling task | 2 | pending | H1, H2 |
| H4: Health metrics REST API | 2 | pending | H1 |
| H5: Service presets + auto-discovery | 2 | pending | H2 |
| H6: Azure Monitor implementation | 2 | pending | H2 |
| H7: `/health` page — Agents tab (UI) | 3 | pending | H4 |
| H8: `/health` page — Infrastructure tab (UI) | 3 | pending | H4, H5 |
| H9: Health source configuration sheet (UI) | 3 | pending | H4 |
| H10: Metric retention cleanup task | 3 | pending | H1 |

### Wave 1 — Foundation

#### Chunk H1: Health Source & Metric Config Schema

- **What**: Create `health_sources`, `health_metrics_config`, and `health_metrics` tables. ORM models, repositories with basic CRUD. Migration.
- **Why this wave**: Schema foundation for everything else
- **Modules touched**: New migration, new `app/db/models/health_source.py`, `app/db/models/health_metric_config.py`, `app/db/models/health_metric.py`, new `app/repositories/health_source_repository.py`, `app/repositories/health_metric_repository.py`, `app/db/models/__init__.py`
- **Depends on**: None
- **Produces**: Schema + repositories for Waves 2-3
- **Acceptance criteria**:
  - [ ] Migration creates all three tables with correct types, FKs, and indexes
  - [ ] `health_metrics` has index on `(metric_config_id, timestamp)` for time-range queries
  - [ ] ORM models with relationships (source → metric_configs → metrics)
  - [ ] Repository: create/update/delete/list for sources and metric configs
  - [ ] Repository: bulk insert for metric datapoints, range query with time window
  - [ ] Migration is reversible
- **Verification**: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head && pytest tests/ -k "health" --no-header -q`

#### Chunk H2: Cloud Provider Abstraction + AWS Implementation

- **What**: Define `HealthMetricsProvider` ABC. Implement `AWSCloudWatchProvider` with STS role assumption, `GetMetricData`, `ListMetrics`, and resource discovery for presets. Graceful handling when boto3 is not installed.
- **Why this wave**: Provider implementation independent of schema (uses only dataclasses, not ORM)
- **Modules touched**: New `app/integrations/health/base.py` (ABC), new `app/integrations/health/aws_cloudwatch.py`, new `app/integrations/health/factory.py`
- **Depends on**: None
- **Produces**: Working AWS CloudWatch provider for Wave 2 polling task
- **Acceptance criteria**:
  - [ ] `HealthMetricsProvider` ABC with `test_connection()`, `fetch_metrics()`, `discover_resources()`
  - [ ] `AWSCloudWatchProvider` assumes role via STS with external ID
  - [ ] `fetch_metrics()` batches up to 500 metrics per `GetMetricData` call
  - [ ] `discover_resources("ecs")` calls DescribeClusters + DescribeServices, returns resources
  - [ ] Graceful import: if `boto3` not installed, factory returns clear error, doesn't crash
  - [ ] STS credentials cached for session duration (1 hour default)
  - [ ] Unit tests with mocked boto3 clients
- **Verification**: `pytest tests/ -k "cloudwatch or health_provider" --no-header -q`

### Wave 2 — Core Mechanics

#### Chunk H3: Health Metric Polling Task

- **What**: Procrastinate periodic task that polls all active health sources. For each source, instantiate the provider, call `fetch_metrics()`, write results to `health_metrics` table. Handle errors gracefully (update `last_poll_error`, continue to next source).
- **Why this wave**: Needs schema (H1) and provider (H2)
- **Modules touched**: `app/queue/registry.py` (new periodic task), new `app/queue/handlers/poll_health_metrics.py`, `app/services/health_service.py`
- **Depends on**: H1, H2
- **Produces**: Automated metric collection pipeline
- **Acceptance criteria**:
  - [ ] Periodic task runs at configurable interval (default 60s)
  - [ ] For each active health source: assume role, fetch metrics, bulk insert to DB
  - [ ] `last_poll_at` and `last_poll_error` updated on the health source
  - [ ] If a source fails, other sources still polled (error isolated)
  - [ ] If provider SDK not installed, source is skipped with error logged
  - [ ] Integration test: mock provider, verify metrics appear in DB after task run
- **Verification**: `pytest tests/ -k "poll_health" --no-header -q`

#### Chunk H4: Health Metrics REST API

- **What**: CRUD endpoints for health sources, metric configs, and metric data. Test connection endpoint. Metric data endpoint with time-range query.
- **Why this wave**: Needs schema (H1)
- **Modules touched**: New `app/api/v1/health.py`, `app/api/v1/router.py` (include), `app/schemas/health.py`
- **Depends on**: H1
- **Produces**: API for UI to consume
- **Acceptance criteria**:
  - [ ] `POST /v1/health-sources` — create source (provider, name, config, auth)
  - [ ] `GET /v1/health-sources` — list sources with status
  - [ ] `PATCH /v1/health-sources/{uuid}` — update source config
  - [ ] `DELETE /v1/health-sources/{uuid}` — delete source and all its metrics
  - [ ] `POST /v1/health-sources/{uuid}/test` — test connection (calls provider.test_connection)
  - [ ] `POST /v1/health-sources/{uuid}/metrics` — add metric config (or from preset)
  - [ ] `POST /v1/health-sources/{uuid}/presets/{preset_name}` — apply preset with auto-discovery
  - [ ] `GET /v1/health-sources/{uuid}/metrics` — list metric configs
  - [ ] `DELETE /v1/health-metrics-config/{uuid}` — remove a metric
  - [ ] `GET /v1/health/metrics?source_id=&metric_id=&from=&to=&resolution=` — time-series data
  - [ ] `GET /v1/health/agents/summary` — agent fleet health summary (built-in, no cloud source needed)
  - [ ] Auth required (admin scope)
- **Verification**: `pytest tests/ -k "health_api" --no-header -q`

#### Chunk H5: Service Presets + Auto-Discovery

- **What**: Define preset configurations for ECS, RDS, SQS, ALB, Lambda. Implement auto-discovery that calls AWS describe APIs to find available resources and pre-populates metric configs with correct dimensions.
- **Why this wave**: Needs provider (H2) for describe API calls
- **Modules touched**: New `app/integrations/health/presets.py`, extend `app/integrations/health/aws_cloudwatch.py` (discover_resources per preset)
- **Depends on**: H2
- **Produces**: One-click service onboarding for Wave 3 UI
- **Acceptance criteria**:
  - [ ] Preset definitions for ECS, RDS, SQS, ALB, Lambda with metrics, stats, thresholds
  - [ ] `discover_resources("ecs")` returns cluster/service names with correct dimensions
  - [ ] `discover_resources("rds")` returns DB instance identifiers
  - [ ] `discover_resources("sqs")` returns queue names
  - [ ] Applying a preset creates metric configs with discovered dimensions
  - [ ] User can review discovered resources before applying (returns preview, not auto-creates)
  - [ ] Unit tests with mocked describe responses
- **Verification**: `pytest tests/ -k "preset or discover" --no-header -q`

#### Chunk H6: Azure Monitor Implementation

- **What**: Implement `AzureMonitorProvider` using `azure-monitor-query` SDK. Same ABC contract as AWS. Support Managed Identity and Service Principal auth. Azure-specific presets (App Service, Azure SQL, Service Bus, Application Gateway).
- **Why this wave**: Needs ABC (H2), independent of AWS-specific chunks
- **Modules touched**: New `app/integrations/health/azure_monitor.py`, extend `app/integrations/health/factory.py`, extend `app/integrations/health/presets.py` (Azure presets)
- **Depends on**: H2
- **Produces**: Azure parity with AWS
- **Acceptance criteria**:
  - [ ] `AzureMonitorProvider` implements `HealthMetricsProvider` ABC
  - [ ] Supports DefaultAzureCredential (Managed Identity) and ClientSecretCredential (Service Principal)
  - [ ] `fetch_metrics()` uses `MetricsQueryClient.query_resource()` for each configured resource
  - [ ] Azure presets for App Service, Azure SQL, Service Bus, Application Gateway
  - [ ] Graceful import: if azure SDK not installed, factory returns clear error
  - [ ] Unit tests with mocked azure SDK
- **Verification**: `pytest tests/ -k "azure_monitor" --no-header -q`

### Wave 3 — UI + Maintenance

#### Chunk H7: `/health` Page — Agents Tab (UI)

- **What**: Create the `/health` route with tabbed layout. Agents tab shows fleet health cards using data from existing agent API endpoints and the new `GET /v1/health/agents/summary` endpoint.
- **Why this wave**: Needs API (H4)
- **Modules touched**: New `ui/src/pages/health/index.tsx`, `ui/src/router.tsx`, `ui/src/components/layout/sidebar.tsx` (add nav item), `ui/src/hooks/use-api.ts` (new hooks)
- **Depends on**: H4
- **Produces**: Working `/health` page with Agents tab
- **Acceptance criteria**:
  - [ ] `/health` route with three tabs: Agents, Infrastructure, Custom
  - [ ] Sidebar navigation includes "Health" item (Heart or Activity icon)
  - [ ] Agents tab: Fleet Status, Success Rate, Spend MTD, Error Rate, Active Investigations, Stall Detections, Runs by Status (chart), Cost by Agent (chart)
  - [ ] Cards use existing StatCard/KpiCard/ChartCard components
  - [ ] 30s polling interval for agent data
  - [ ] Follows design system: surface depth, semantic colors, micro-labels
- **Verification**: Manual — navigate to `/health`, verify agent cards render with real data

#### Chunk H8: `/health` Page — Infrastructure + Custom Tabs (UI)

- **What**: Infrastructure and Custom tabs rendering metric cards from `health_metrics_config`. Each card shows current value, sparkline, threshold indicator. "Add Service" button with preset selector. "Add Custom Metric" form.
- **Why this wave**: Needs API (H4) and presets (H5)
- **Modules touched**: `ui/src/pages/health/index.tsx` (Infrastructure + Custom tab content), new `ui/src/components/health/metric-card.tsx`, new `ui/src/components/health/preset-selector.tsx`, new `ui/src/components/health/custom-metric-form.tsx`, `ui/src/hooks/use-api.ts` (health metric hooks), `ui/src/lib/types.ts` (health types)
- **Depends on**: H4, H5
- **Produces**: Full infrastructure monitoring UI
- **Acceptance criteria**:
  - [ ] Metric cards show: title, current value (large text), sparkline (last 1h), threshold badge (green/amber/red)
  - [ ] "Add Service" button opens preset selector with icons for ECS, RDS, SQS, ALB, Lambda
  - [ ] Selecting a preset triggers auto-discovery, shows preview of resources found, user confirms
  - [ ] "Add Custom Metric" button opens form: namespace, metric, dimensions (key-value pairs), statistic, thresholds
  - [ ] Cards removable via X on hover (same pattern as dashboard)
  - [ ] Time window selector: 1h, 6h, 24h, 7d
  - [ ] 60s polling interval for metric data
  - [ ] "Last updated" timestamp on each card
  - [ ] Empty state: "No infrastructure monitoring configured. Add a service to get started."
- **Verification**: Manual — configure a health source (mocked), verify cards render with sparklines

#### Chunk H9: Health Source Configuration Sheet (UI)

- **What**: Right-edge sheet for managing health sources. List of configured sources with status. Add source flow: provider → credentials → test → save. Per-source status: polling indicator, last error, metric count.
- **Why this wave**: Needs API (H4)
- **Modules touched**: New `ui/src/components/health/source-config-sheet.tsx`, `ui/src/hooks/use-api.ts` (source CRUD hooks)
- **Depends on**: H4
- **Produces**: Health source management UI
- **Acceptance criteria**:
  - [ ] "Configure Sources" button in Infrastructure tab header opens sheet
  - [ ] Sheet lists all health sources with: name, provider icon (AWS/Azure), status dot (green/red), metric count, last poll time
  - [ ] Add source: step 1 (provider selector) → step 2 (credentials form: role ARN + external ID for AWS, or subscription + credentials for Azure) → step 3 (test connection with result) → step 4 (save)
  - [ ] External ID auto-generated by Calseta, displayed for user to copy into IAM trust policy
  - [ ] IAM policy template shown (copyable) with required permissions
  - [ ] Per-source actions: edit, disable/enable, delete (with confirmation)
  - [ ] Error state: if last poll failed, show error message with timestamp
- **Verification**: Manual — add a health source, test connection, verify polling status

#### Chunk H10: Metric Retention Cleanup Task

- **What**: Procrastinate periodic task that deletes `health_metrics` rows older than `HEALTH_METRICS_RETENTION_DAYS` (default 30). Runs daily.
- **Why this wave**: Needs schema (H1), independent of UI
- **Modules touched**: `app/queue/registry.py` (new periodic task), `app/repositories/health_metric_repository.py` (delete_before method)
- **Depends on**: H1
- **Produces**: Automatic disk space management
- **Acceptance criteria**:
  - [ ] Periodic task runs daily (cron: `0 3 * * *` — 3 AM)
  - [ ] Deletes `health_metrics` rows where `timestamp < now - retention_days`
  - [ ] `HEALTH_METRICS_RETENTION_DAYS` configurable via env var (default 30)
  - [ ] Logs: rows deleted count, execution time
  - [ ] Does not lock tables for extended periods (batch delete in chunks of 10000)
- **Verification**: `pytest tests/ -k "retention" --no-header -q`
