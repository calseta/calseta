# Cloud-Native Deployment — Terraform IaC for Azure & AWS

**Date**: 2026-03-26
**Author**: Jorge Castro
**Status**: Draft

## Problem Statement

Calseta ships with `docker compose up` for local dev and self-hosted deployment. This works well for getting started, but production deployment to cloud infrastructure requires manual resource provisioning, environment configuration, networking setup, and security hardening. There's no IaC (Infrastructure as Code) to stand up a production-grade Calseta instance on Azure or AWS.

Security teams evaluating Calseta need to deploy a sandbox quickly to test against their alert sources. Today that means either running Docker Compose on a VM (not production-grade) or hand-wiring cloud resources (hours of work, error-prone, undocumented). Neither option supports the "self-hostable without pain" principle.

The codebase is already well-abstracted for cloud portability — SQLAlchemy ORM with no raw SQL, `TaskQueueBase` ABC for the queue, `CacheBackendBase` for caching, Azure Key Vault and AWS Secrets Manager already implemented in `app/config.py`. But without Terraform modules, deployers must discover these integration points themselves and wire them manually.

## Solution

Ship production-ready Terraform modules for Azure and AWS that deploy a fully working Calseta instance with one command. Each module provisions all required infrastructure, runs database migrations, configures secrets management, and exposes the API + MCP endpoints behind a load balancer with TLS.

After this ships, the deployment experience is:

```bash
# Azure
cd terraform/azure
cp terraform.tfvars.example terraform.tfvars  # fill in values
terraform init && terraform apply

# AWS
cd terraform/aws
cp terraform.tfvars.example terraform.tfvars
terraform init && terraform apply
```

Output: API URL, MCP URL, and instructions to create the first API key. Total time from `git clone` to working instance: under 30 minutes.

## User Stories

1. As a security engineer evaluating Calseta, I want to deploy a sandbox to Azure with one Terraform command so that I can test it against my Sentinel alerts without spending a day on infrastructure.

2. As a security engineer evaluating Calseta, I want to deploy a sandbox to AWS with one Terraform command so that I can test it against my Elastic/Splunk alerts without spending a day on infrastructure.

3. As a deployer, I want all secrets (DB password, encryption key, API keys for enrichment providers) stored in the cloud-native secrets manager (Key Vault or Secrets Manager), not in env files or Terraform state, so that secrets are never written to disk.

4. As a deployer, I want the Terraform module to use managed identity / IAM roles for service-to-service auth (app → secrets manager, app → database) so that I don't manage service account credentials.

5. As a deployer, I want the database password and encryption key auto-generated during `terraform apply` and stored directly in the secrets manager, so that I never see or handle them.

6. As a deployer, I want the Terraform output to include the API URL, MCP URL, and a one-liner to create my first API key, so that I can start using Calseta immediately after deploy.

7. As a deployer, I want to configure which enrichment providers are active by setting API keys in `terraform.tfvars`, and have them flow into the secrets manager automatically.

8. As a deployer, I want TLS termination handled by the cloud load balancer (Azure App Gateway / AWS ALB) so that I don't manage certificates on the containers.

9. As a deployer, I want the Terraform module to be modular — I can deploy just the core (API + worker + DB) without MCP if I don't need it, or add MCP as an optional module.

10. As a deployer, I want health checks configured on all services so that unhealthy containers are automatically replaced.

11. As a deployer, I want to choose the database SKU / instance size via a Terraform variable so that I can start small (sandbox) and scale up (production) without changing the module.

12. As a deployer, I want database migrations to run automatically as part of the deployment so that I don't need to SSH into a container to run Alembic.

13. As a deployer, I want structured JSON logs forwarded to the cloud-native log aggregator (Azure Monitor / CloudWatch) with zero configuration, since Calseta already logs structured JSON to stdout.

14. As a contributor, I want a `make deploy-azure` and `make deploy-aws` target that wraps Terraform with sensible defaults for a sandbox deployment.

15. As a deployer, I want a `terraform destroy` to cleanly remove all resources so that sandbox evaluations don't leave orphaned infrastructure.

16. As a deployer, I want the Terraform module to configure network security (VNet/VPC, security groups) so that the database is not publicly accessible and only the API/MCP endpoints are exposed.

17. As a deployer on Azure, I want the option to use Azure Container Apps (serverless) or Azure Kubernetes Service (AKS) depending on my org's platform preference.

18. As a deployer on AWS, I want the option to use ECS Fargate (serverless) or EKS depending on my org's platform preference.

19. As a deployer, I want a `sandbox` preset that deploys the smallest viable configuration (1 replica each, burstable DB, sandbox mode enabled) for evaluation, and a `production` preset with recommended sizing.

20. As a deployer, I want the Terraform module to configure the `TRUSTED_PROXY_COUNT` automatically based on the cloud load balancer (1 for ALB/App Gateway) so that rate limiting works correctly.

## Implementation Decisions

### Directory Structure

```
deploy/
  terraform/
    modules/              # Reusable sub-modules
      database/           # PostgreSQL (Azure Flexible Server / AWS RDS)
      containers/         # Container orchestration (Container Apps / ECS Fargate)
      secrets/            # Secrets manager (Key Vault / Secrets Manager)
      networking/         # VNet+Subnets / VPC+Subnets+SGs
      registry/           # Container registry (ACR / ECR)
      load-balancer/      # App Gateway / ALB
      monitoring/         # Azure Monitor / CloudWatch
    azure/
      main.tf             # Root module — composes sub-modules
      variables.tf        # Input variables
      outputs.tf          # API URL, MCP URL, etc.
      terraform.tfvars.example
      presets/
        sandbox.tfvars    # Minimal config for evaluation
        production.tfvars # Recommended production sizing
    aws/
      main.tf
      variables.tf
      outputs.tf
      terraform.tfvars.example
      presets/
        sandbox.tfvars
        production.tfvars
```

### Why Separate Modules (Not a Single Monolith)

Each sub-module (database, containers, secrets, networking) is independent and composable. This lets deployers:
- Bring their own database (skip the database module, provide `DATABASE_URL`)
- Bring their own container registry (skip registry module, provide image URI)
- Bring their own networking (skip networking module, provide subnet IDs)

The root modules (`azure/main.tf`, `aws/main.tf`) compose all sub-modules with opinionated defaults. Power users override individual modules.

### Azure Architecture

```
Azure Resource Group
├── Azure Container Apps Environment
│   ├── api          (port 8000, min 1 / max 10 replicas)
│   ├── worker       (no ingress, min 1 / max 5 replicas)
│   ├── mcp          (port 8001, min 0 / max 5 replicas, optional)
│   └── migrate-job  (Container Apps Job, runs on deploy)
├── Azure Database for PostgreSQL (Flexible Server)
│   └── calseta database (pgcrypto enabled)
├── Azure Key Vault
│   └── all secrets (DB password, encryption key, provider API keys)
├── Azure Container Registry
│   └── calseta image (pushed during deploy)
├── Virtual Network
│   ├── containers-subnet (delegated to Container Apps)
│   ├── database-subnet (delegated to PostgreSQL)
│   └── NSG rules (deny public to DB, allow API/MCP via ingress)
└── Azure Monitor (log analytics workspace)
    └── Container Apps stdout → Log Analytics
```

Container Apps was chosen over AKS for the default because:
- No cluster management overhead (serverless)
- Native scaling on HTTP traffic or queue depth
- Built-in TLS termination and custom domain support
- Cheaper for small deployments (pay per vCPU-second)
- AKS variant can be added as a separate root module later

### AWS Architecture

```
AWS Account
├── ECS Cluster (Fargate)
│   ├── api-service     (port 8000, ALB target group, 1-10 tasks)
│   ├── worker-service  (no LB, 1-5 tasks)
│   ├── mcp-service     (port 8001, ALB target group, 0-5 tasks, optional)
│   └── migrate-task    (ECS run-task, runs on deploy)
├── RDS PostgreSQL (Flexible, db.t3.medium+)
│   └── calseta database (pgcrypto enabled)
├── AWS Secrets Manager
│   └── calseta/[environment] (JSON secret with all env vars)
├── ECR Repository
│   └── calseta image
├── VPC
│   ├── public subnets (ALB)
│   ├── private subnets (ECS tasks, RDS)
│   └── Security groups (ALB → ECS on 8000/8001, ECS → RDS on 5432)
├── Application Load Balancer
│   ├── HTTPS listener (443) → api target group
│   └── HTTPS listener (8001) → mcp target group (optional)
└── CloudWatch
    └── ECS stdout → CloudWatch Logs
```

ECS Fargate chosen over EKS for the same reasons as Container Apps over AKS — serverless, no cluster management, simpler for single-tenant deployments.

### Database Migration Strategy

Migrations run as a one-shot container job before services start:

- **Azure**: Container Apps Job (triggered by Terraform `null_resource` with `local-exec` provisioner calling `az containerapp job start`)
- **AWS**: ECS `run-task` (triggered by Terraform `null_resource` with `local-exec` provisioner calling `aws ecs run-task --launch-type FARGATE`)

The migration container uses the same image as the API, with command override: `alembic upgrade head`. It runs in the same VNet/VPC with access to the database. Terraform waits for it to complete before deploying services.

### Secrets Flow

Secrets are never stored in Terraform state or `.tfvars`. The flow:

1. **Auto-generated secrets** (DB password, encryption key): Terraform generates them using `random_password` and `random_bytes` resources, writes them directly to the secrets manager, and references them by ARN/URI in container environment config. The values exist only in the secrets manager.

2. **User-provided secrets** (enrichment API keys, Slack tokens): User sets them in `terraform.tfvars` as `sensitive` variables. Terraform writes them to the secrets manager and clears the local reference. Users should rotate these in the secrets manager directly after initial deploy.

3. **Container access**: Containers receive `AZURE_KEY_VAULT_URL` or `AWS_SECRETS_MANAGER_SECRET_NAME` + `AWS_REGION` as environment variables. Calseta's existing `_AzureKeyVaultSource` / `_AWSSecretsManagerSource` in `app/config.py` loads all secrets at startup. No per-secret env var injection needed.

4. **Identity-based auth**: Containers use Managed Identity (Azure) or IAM Task Role (AWS) to access the secrets manager. No API keys or service account credentials.

### Container Image Strategy

Two options, controlled by a Terraform variable (`image_source`):

1. **`ghcr` (default)**: Pull from GitHub Container Registry (`ghcr.io/calseta/calseta:latest` or a pinned version tag). No build step. Fastest for evaluation.

2. **`build`**: Build locally and push to the cloud registry (ACR/ECR). For customized images or air-gapped environments. Terraform provisions the registry and uses a `null_resource` to run `docker build` + `docker push`.

### Networking Defaults

- Database is **never publicly accessible** — only reachable from the container subnet
- API endpoint is publicly accessible via load balancer (HTTPS)
- MCP endpoint is publicly accessible via load balancer (HTTPS) — can be restricted to VNet-only via variable
- All egress allowed (enrichment providers, webhook targets need outbound internet)
- `TRUSTED_PROXY_COUNT` auto-set to `1` (one load balancer hop)

### Presets

| Variable | Sandbox | Production |
|---|---|---|
| `db_sku` | `B_Standard_B1ms` (Azure) / `db.t3.micro` (AWS) | `GP_Standard_D2ds_v4` / `db.r6g.large` |
| `api_min_replicas` | 1 | 2 |
| `api_max_replicas` | 2 | 10 |
| `worker_replicas` | 1 | 3 |
| `mcp_enabled` | true | true |
| `mcp_min_replicas` | 1 | 2 |
| `sandbox_mode` | true | false |
| `queue_concurrency` | 5 | 10 |
| `log_level` | DEBUG | INFO |
| `https_enabled` | true | true |
| `db_backup_retention_days` | 7 | 35 |
| `db_high_availability` | false | true |

### Codebase Changes Required

Based on the component analysis, the application code needs **zero changes** for Path 1 (lift & shift with procrastinate on managed PostgreSQL). The following are **optional enhancements** that improve the cloud-native experience:

1. **Health check for worker process** — Current worker health check is `cat /proc/1/cmdline | grep app.worker` which doesn't verify the worker is actually processing jobs. Add a `/health` endpoint to the worker (or a sidecar health file that the supervisor writes to) so container orchestrators can detect stuck workers. Alternative: use the `heartbeat_runs` table once the control plane ships.

2. **Startup probe tuning** — The API needs ~15 seconds to seed enrichment providers and indicator mappings at startup. Document recommended startup probe settings for each cloud platform.

3. **Graceful shutdown** — Verify that `SIGTERM` handling in all three processes (API via uvicorn, worker via procrastinate, MCP via mcp SDK) completes in-flight work before exiting. Container orchestrators send `SIGTERM` → wait `terminationGracePeriodSeconds` → `SIGKILL`.

4. **Connection pool configuration** — Expose `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` as environment variables in `app/db/session.py` so Terraform can tune them based on the database SKU's connection limit. Currently uses SQLAlchemy defaults (pool_size=5).

## Testing Strategy

### Infrastructure Tests

- **Terraform validate**: `terraform validate` on both Azure and AWS modules (runs in CI, no cloud credentials needed)
- **Terraform plan**: `terraform plan` with sandbox preset against a mock backend (validates variable types, resource dependencies)
- **Integration smoke test**: Post-apply script that hits `/health`, creates an API key via CLI, ingests a test alert, and verifies enrichment runs. This is a shell script, not a Terraform test.

### Application Compatibility Tests

- **Existing test suite against managed PostgreSQL**: Run `make test` with `DATABASE_URL` pointing at Azure DB for PostgreSQL / RDS. Validates that all SQLAlchemy queries, Alembic migrations, and procrastinate operations work against managed Postgres.
- **SSL connection test**: Verify `?ssl=require` works with both `asyncpg` (SQLAlchemy) and `psycopg` (procrastinate).

### CI Integration

- Add a `terraform-validate` job to CI that runs `terraform validate` on both modules (no cloud credentials, just syntax/type checking).
- Optionally: nightly or weekly `terraform plan` against a real cloud backend using CI secrets (catches provider API changes, deprecated resources, etc.).

## Out of Scope

- **Alternative queue backends** (Azure Service Bus, SQS) — procrastinate on managed PostgreSQL works identically to local. Queue backend swaps are a separate effort tracked in `docs/architecture/QUEUE_BACKENDS.md`.
- **Redis cache** — in-memory cache is sufficient for single-replica and small multi-replica deployments. Redis swap is a separate ~4h effort.
- **AKS / EKS modules** — Container Apps and ECS Fargate cover 90% of use cases. Kubernetes modules can be added later as additional root modules without changing sub-modules.
- **Multi-region / HA database failover** — the `production` preset enables single-region HA (zone-redundant). Multi-region is out of scope.
- **Custom domain and certificate provisioning** — Terraform outputs the cloud-assigned URL. Custom domains can be configured manually or via a separate Terraform resource. Not included in the module to avoid DNS provider coupling.
- **CI/CD pipeline for Terraform** — users bring their own CI. The modules are designed for `terraform apply` from a local machine or any CI system.
- **Monitoring dashboards** — logs flow to Azure Monitor / CloudWatch automatically (stdout). Pre-built dashboards (Grafana, CloudWatch Insights) are a future enhancement.
- **Private MCP endpoint** — MCP is public by default. Restricting to VNet/VPC-only is a variable toggle but the private networking setup (Private Link / PrivateLink) is not in v1.
- **Shared HTTP client pooling** — optional optimization (~4h effort), not required for correctness.

## Open Questions

- [x] ~~Should the Terraform modules live in the main Calseta repo or a separate repo?~~ **Decision: main repo at `./terraform/`.** Simpler for discovery, versioned alongside the app code.
- [ ] Should we support Terraform Cloud / Spacelift state backends out of the box, or just document how to configure them?
- [ ] For the migration job: should it run as part of `terraform apply` (via `null_resource`) or as a separate manual step? Auto-run is more "just works" but couples Terraform to `az`/`aws` CLI presence.
- [ ] Should the Terraform module create the first API key automatically and output it, or leave that as a manual post-deploy step? Auto-create is convenient but means the key appears in Terraform output (sensitive, but still in state).
- [ ] MCP transport: the current MCP server uses SSE on port 8001. Should the Terraform module expose this on a separate subdomain (e.g., `mcp.calseta.example.com`) or a separate port on the same domain?
- [ ] Should we provide a Pulumi alternative for teams that prefer it, or is Terraform-only sufficient for v1?

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Terraform provider API changes break modules | Deploy fails | Pin provider versions (`azurerm ~> 4.0`, `aws ~> 5.0`). Test in CI weekly. |
| Procrastinate `LISTEN/NOTIFY` issues on managed PostgreSQL | Worker stops processing jobs | Both Azure Flexible Server and RDS support `LISTEN/NOTIFY` natively. Tested and documented. Fallback: restart worker container (auto-healed by orchestrator). |
| Database connection limits exceeded | 503 errors under load | Terraform calculates required connections: `(api_replicas * pool_size) + (worker_replicas * 2) + (mcp_replicas * pool_size)` and validates against the DB SKU's max_connections. Warns if undersized. |
| Secrets in Terraform state | Security exposure | Use `sensitive = true` on all secret variables. Document that state should be stored in encrypted backend (Azure Storage with CMK, S3 with SSE-KMS). Auto-generated secrets never appear in `.tfvars`. |
| Container image pull failures from GHCR | Deploy fails | Provide `image_source = "build"` option to push to private registry. Document GHCR rate limits (anonymous: 100 pulls/hour). |
| SSL certificate issues with asyncpg | Database connection fails | Document SSL connection string format. Test both `ssl=require` and `ssl=verify-full` in integration tests. Provide `db_ssl_mode` variable. |
| Migration job fails mid-apply | Partial infrastructure deployed | Migration job is idempotent (Alembic `upgrade head` is safe to re-run). Terraform marks the job as failed; user re-runs `terraform apply`. |

## Project Management

### Overview

| Chunk | Wave | Status | Dependencies |
|-------|------|--------|-------------|
| Terraform module structure + variables | 1 | pending | — |
| Azure networking module | 1 | pending | — |
| AWS networking module | 1 | pending | — |
| Azure database module | 2 | pending | Azure networking |
| AWS database module | 2 | pending | AWS networking |
| Azure secrets module | 2 | pending | — |
| AWS secrets module | 2 | pending | — |
| Azure registry module | 2 | pending | — |
| AWS registry module | 2 | pending | — |
| App: expose DB pool config as env vars | 2 | pending | — |
| Azure container module | 3 | pending | Azure networking, database, secrets, registry |
| AWS container module | 3 | pending | AWS networking, database, secrets, registry |
| Azure migration job | 3 | pending | Azure database, container module |
| AWS migration job | 3 | pending | AWS database, container module |
| Azure root module + presets | 4 | pending | All Azure modules |
| AWS root module + presets | 4 | pending | All AWS modules |
| Azure monitoring module | 4 | pending | Azure container module |
| AWS monitoring module | 4 | pending | AWS container module |
| Smoke test script | 4 | pending | — |
| Documentation + Makefile targets | 5 | pending | All modules |
| CI terraform-validate job | 5 | pending | Module structure |

### Wave 1 — Scaffolding + Networking

No dependencies. Sets up the directory structure and the foundational networking layer.

#### Chunk: Terraform module structure + variables

- **What**: Create the `terraform/` directory structure, shared variable definitions (`variables.tf` for both Azure and AWS), provider version pins, backend configuration templates, and `terraform.tfvars.example` files.
- **Why this wave**: Foundation — everything else references these variable names.
- **Modules/files touched**: `terraform/azure/`, `terraform/aws/`, `terraform/modules/`
- **Depends on**: None
- **Produces**: Variable names and types that all other modules reference. Provider version constraints.
- **Acceptance criteria**:
  - [ ] `terraform validate` passes on both `azure/` and `aws/` root modules (empty but valid)
  - [ ] `terraform.tfvars.example` documents every variable with comments
  - [ ] `sandbox.tfvars` and `production.tfvars` presets exist with documented values
- **Verification**: `cd terraform/azure && terraform init && terraform validate` (same for `aws/`)

#### Chunk: Azure networking module

- **What**: VNet, subnets (containers, database), NSG rules, service endpoints for PostgreSQL and Key Vault. Output subnet IDs for downstream modules.
- **Why this wave**: No dependencies. Networking is the first resource created in any Azure deployment.
- **Modules/files touched**: `terraform/modules/networking/azure/`
- **Depends on**: None
- **Produces**: `container_subnet_id`, `database_subnet_id`, `vnet_id` outputs
- **Acceptance criteria**:
  - [ ] VNet with configurable CIDR range
  - [ ] Container subnet delegated to `Microsoft.App/environments`
  - [ ] Database subnet delegated to `Microsoft.DBforPostgreSQL/flexibleServers`
  - [ ] NSG denies public access to database subnet
  - [ ] All resource names include a configurable `environment` prefix
- **Verification**: `terraform validate` + `terraform plan` with mock variables

#### Chunk: AWS networking module

- **What**: VPC, public subnets (ALB), private subnets (ECS, RDS), internet gateway, NAT gateway, security groups (ALB → ECS on 8000/8001, ECS → RDS on 5432, ECS → internet for enrichment APIs).
- **Why this wave**: No dependencies. Same rationale as Azure networking.
- **Modules/files touched**: `terraform/modules/networking/aws/`
- **Depends on**: None
- **Produces**: `vpc_id`, `public_subnet_ids`, `private_subnet_ids`, `ecs_security_group_id`, `rds_security_group_id`, `alb_security_group_id` outputs
- **Acceptance criteria**:
  - [ ] VPC with configurable CIDR
  - [ ] 2 public subnets (ALB, multi-AZ)
  - [ ] 2 private subnets (ECS + RDS, multi-AZ)
  - [ ] NAT gateway for private subnet egress
  - [ ] Security groups restrict DB to ECS-only access
- **Verification**: `terraform validate` + `terraform plan`

### Wave 2 — Data Layer + Secrets + Registry

Depends on networking outputs from Wave 1. These modules are independent of each other and can run in parallel.

#### Chunk: Azure database module

- **What**: Azure Database for PostgreSQL Flexible Server. Configurable SKU, storage, backup retention. Enables `pgcrypto` extension. Creates `calseta` database and user. Stores password in Key Vault (depends on secrets module output, or accepts a Key Vault URI as input).
- **Modules/files touched**: `terraform/modules/database/azure/`
- **Depends on**: Azure networking (subnet ID)
- **Produces**: `database_url` (connection string with `+asyncpg` prefix), `database_host`, `database_name`
- **Acceptance criteria**:
  - [ ] Flexible Server deployed in database subnet
  - [ ] `pgcrypto` extension enabled via `azurerm_postgresql_flexible_server_configuration`
  - [ ] SSL enforced
  - [ ] Password auto-generated via `random_password`, stored in Key Vault
  - [ ] Configurable SKU via variable (sandbox: `B_Standard_B1ms`, production: `GP_Standard_D2ds_v4`)
  - [ ] Backup retention configurable (7 or 35 days)
- **Verification**: `terraform plan` shows correct resource types and configuration

#### Chunk: AWS database module

- **What**: RDS PostgreSQL instance. Same configurability as Azure. Stores password in Secrets Manager. Enables `pgcrypto` via parameter group.
- **Modules/files touched**: `terraform/modules/database/aws/`
- **Depends on**: AWS networking (subnet IDs, security group ID)
- **Produces**: `database_url`, `database_host`, `database_name`
- **Acceptance criteria**:
  - [ ] RDS in private subnet, multi-AZ configurable
  - [ ] Password auto-generated, stored in Secrets Manager
  - [ ] Parameter group enables `pgcrypto` (`shared_preload_libraries`)
  - [ ] SSL enforced via `rds.force_ssl = 1`
  - [ ] Configurable instance class
- **Verification**: `terraform plan`

#### Chunk: Azure secrets module

- **What**: Azure Key Vault. Auto-generates DB password and Fernet encryption key. Stores user-provided enrichment API keys. Grants Managed Identity access.
- **Modules/files touched**: `terraform/modules/secrets/azure/`
- **Depends on**: None (creates its own identity; container module assigns it later)
- **Produces**: `key_vault_url`, `managed_identity_id`
- **Acceptance criteria**:
  - [ ] Key Vault with soft delete enabled
  - [ ] User-assigned Managed Identity created
  - [ ] DB password and encryption key auto-generated and stored
  - [ ] Enrichment API keys stored if provided in variables
  - [ ] Access policy grants Managed Identity `Secret Get` + `Secret List`
- **Verification**: `terraform plan`

#### Chunk: AWS secrets module

- **What**: AWS Secrets Manager secret (JSON object). Auto-generates DB password and encryption key. Stores user-provided enrichment keys. Creates IAM policy for ECS task role.
- **Modules/files touched**: `terraform/modules/secrets/aws/`
- **Depends on**: None
- **Produces**: `secret_arn`, `secret_name`, `task_role_arn`
- **Acceptance criteria**:
  - [ ] Single JSON secret with all Calseta env vars
  - [ ] IAM policy for `secretsmanager:GetSecretValue` scoped to this secret
  - [ ] Auto-generated password and encryption key
  - [ ] Enrichment keys included if provided
- **Verification**: `terraform plan`

#### Chunk: Azure registry module

- **What**: Azure Container Registry. Optional — only created if `image_source = "build"`. Grants Managed Identity `AcrPull`.
- **Modules/files touched**: `terraform/modules/registry/azure/`
- **Depends on**: Azure secrets module (for Managed Identity)
- **Produces**: `registry_url`, `image_uri`
- **Acceptance criteria**:
  - [ ] ACR created only when `image_source = "build"`
  - [ ] When `image_source = "ghcr"`, outputs GHCR image URI directly
  - [ ] `AcrPull` role assigned to Managed Identity
- **Verification**: `terraform plan` with both `image_source` values

#### Chunk: AWS registry module

- **What**: ECR repository. Same conditional logic as Azure.
- **Modules/files touched**: `terraform/modules/registry/aws/`
- **Depends on**: None
- **Produces**: `repository_url`, `image_uri`
- **Acceptance criteria**:
  - [ ] ECR created only when `image_source = "build"`
  - [ ] Lifecycle policy to keep last 10 images
  - [ ] When `image_source = "ghcr"`, outputs GHCR URI
- **Verification**: `terraform plan`

#### Chunk: App — expose DB pool config as env vars

- **What**: Make `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` configurable via environment variables in `app/db/session.py`. Default to current behavior (SQLAlchemy defaults) when not set.
- **Modules/files touched**: `app/db/session.py`, `app/config.py`
- **Depends on**: None
- **Produces**: Env var support for Terraform to tune pool size per DB SKU
- **Acceptance criteria**:
  - [ ] `DB_POOL_SIZE` env var respected (default: 5)
  - [ ] `DB_MAX_OVERFLOW` env var respected (default: 10)
  - [ ] Existing behavior unchanged when vars not set
  - [ ] Existing tests pass
- **Verification**: `make test`

### Wave 3 — Container Orchestration + Migrations

Depends on networking, database, secrets, and registry from Waves 1-2.

#### Chunk: Azure container module

- **What**: Container Apps Environment + 3 Container Apps (api, worker, mcp). Configured with Managed Identity, Key Vault URL, database URL. Health probes on `/health`. Scaling rules. MCP optional via variable.
- **Modules/files touched**: `terraform/modules/containers/azure/`
- **Depends on**: Azure networking, database, secrets, registry
- **Produces**: `api_url`, `mcp_url` (Container Apps FQDN)
- **Acceptance criteria**:
  - [ ] Container Apps Environment in container subnet
  - [ ] API app: port 8000, health probe on `/health`, min/max replicas configurable
  - [ ] Worker app: no ingress, replicas configurable
  - [ ] MCP app: port 8001, health probe, optional via `mcp_enabled` variable
  - [ ] All apps use Managed Identity for Key Vault access
  - [ ] Environment variables: `DATABASE_URL`, `AZURE_KEY_VAULT_URL`, `TRUSTED_PROXY_COUNT=1`, `LOG_FORMAT=json`, `HTTPS_ENABLED=true`
  - [ ] Startup probe: 15s initial delay, 5s period, 10 failure threshold
- **Verification**: `terraform plan` shows all 3 container apps with correct config

#### Chunk: AWS container module

- **What**: ECS Cluster + 3 Fargate services. ALB with target groups for API and MCP. Task definitions with Secrets Manager integration. IAM task role. CloudWatch log groups.
- **Modules/files touched**: `terraform/modules/containers/aws/`
- **Depends on**: AWS networking, database, secrets, registry
- **Produces**: `api_url` (ALB DNS), `mcp_url`
- **Acceptance criteria**:
  - [ ] ECS cluster with Fargate capacity provider
  - [ ] API service: ALB target group, port 8000, health check `/health`
  - [ ] Worker service: no LB, desired count configurable
  - [ ] MCP service: ALB target group, port 8001, optional
  - [ ] Task definitions reference Secrets Manager secret ARN
  - [ ] IAM task execution role with `secretsmanager:GetSecretValue` and `ecr:GetAuthorizationToken`
  - [ ] CloudWatch log group per service
  - [ ] `TRUSTED_PROXY_COUNT=1`, `LOG_FORMAT=json`
- **Verification**: `terraform plan`

#### Chunk: Azure migration job

- **What**: Container Apps Job that runs `alembic upgrade head` using the same image and environment as the API. Triggered by Terraform `null_resource` after database and container environment are ready.
- **Modules/files touched**: `terraform/modules/containers/azure/` (migration sub-resource)
- **Depends on**: Azure database, container module (for environment)
- **Produces**: Migrated database schema
- **Acceptance criteria**:
  - [ ] Job uses same image and env vars as API container
  - [ ] Command override: `["alembic", "upgrade", "head"]`
  - [ ] Terraform waits for job completion before deploying services
  - [ ] Job is idempotent (safe to re-run)
  - [ ] Failure causes `terraform apply` to fail with clear error
- **Verification**: `terraform plan` shows job resource

#### Chunk: AWS migration job

- **What**: ECS run-task that runs Alembic migration. Same approach as Azure.
- **Modules/files touched**: `terraform/modules/containers/aws/` (migration sub-resource)
- **Depends on**: AWS database, container module
- **Produces**: Migrated database schema
- **Acceptance criteria**:
  - [ ] Uses same task definition as API with command override
  - [ ] Runs as Fargate task in private subnet
  - [ ] Terraform waits for task completion
  - [ ] Idempotent
- **Verification**: `terraform plan`

### Wave 4 — Root Modules + Monitoring + Smoke Test

Depends on all infrastructure modules.

#### Chunk: Azure root module + presets

- **What**: `terraform/azure/main.tf` that composes all Azure sub-modules with opinionated defaults. Wires outputs between modules. Includes `sandbox.tfvars` and `production.tfvars` presets.
- **Modules/files touched**: `terraform/azure/`
- **Depends on**: All Azure sub-modules
- **Produces**: Complete deployable Azure configuration
- **Acceptance criteria**:
  - [ ] `terraform init && terraform validate` passes
  - [ ] `terraform plan -var-file=presets/sandbox.tfvars` produces a valid plan
  - [ ] Outputs include `api_url`, `mcp_url`, `key_vault_name`
  - [ ] All module outputs correctly wired (networking → database, secrets → containers, etc.)
- **Verification**: `terraform validate` + `terraform plan` with sandbox preset

#### Chunk: AWS root module + presets

- **What**: Same as Azure root module but for AWS.
- **Modules/files touched**: `terraform/aws/`
- **Depends on**: All AWS sub-modules
- **Produces**: Complete deployable AWS configuration
- **Acceptance criteria**:
  - [ ] `terraform init && terraform validate` passes
  - [ ] `terraform plan -var-file=presets/sandbox.tfvars` produces a valid plan
  - [ ] Outputs include `api_url`, `mcp_url`, `secret_name`, `alb_dns_name`
- **Verification**: `terraform validate` + `terraform plan`

#### Chunk: Azure monitoring module

- **What**: Log Analytics Workspace. Container Apps diagnostic settings to forward stdout to Log Analytics. Optional: alert rules for health check failures.
- **Modules/files touched**: `terraform/modules/monitoring/azure/`
- **Depends on**: Azure container module
- **Produces**: `log_analytics_workspace_id`
- **Acceptance criteria**:
  - [ ] Log Analytics Workspace created
  - [ ] Container Apps stdout → Log Analytics
  - [ ] Configurable retention period
- **Verification**: `terraform plan`

#### Chunk: AWS monitoring module

- **What**: CloudWatch Log Groups for each ECS service. Optional: CloudWatch alarms for health check failures and high error rates.
- **Modules/files touched**: `terraform/modules/monitoring/aws/`
- **Depends on**: AWS container module
- **Produces**: `log_group_arns`
- **Acceptance criteria**:
  - [ ] Log group per service with configurable retention
  - [ ] ECS task definitions reference log groups
- **Verification**: `terraform plan`

#### Chunk: Smoke test script

- **What**: A shell script (`terraform/scripts/smoke-test.sh`) that validates a deployed Calseta instance. Accepts API URL as argument. Tests: health endpoint, API key creation, alert ingestion, enrichment pipeline.
- **Modules/files touched**: `terraform/scripts/`
- **Depends on**: None (runs post-deploy, not a Terraform resource)
- **Produces**: Pass/fail validation of deployed instance
- **Acceptance criteria**:
  - [ ] `GET /health` returns 200 with `status: ok`
  - [ ] `POST /v1/api-keys` creates a key (using a bootstrap mechanism or pre-seeded admin key)
  - [ ] `POST /v1/alerts` ingests a test alert and returns 202
  - [ ] `GET /v1/alerts` returns the ingested alert
  - [ ] Script exits 0 on success, 1 on failure with clear error messages
- **Verification**: Run script against local Docker Compose instance

### Wave 5 — Documentation + CI

Final wave. Depends on all modules being complete.

#### Chunk: Documentation + Makefile targets

- **What**: `docs/guides/HOW_TO_DEPLOY_AZURE.md`, `docs/guides/HOW_TO_DEPLOY_AWS.md`, Makefile targets (`make deploy-azure`, `make deploy-aws`, `make destroy-azure`, `make destroy-aws`). Update main README with deployment section.
- **Modules/files touched**: `docs/guides/`, `Makefile`
- **Depends on**: All Terraform modules (to document accurately)
- **Produces**: User-facing deployment guides
- **Acceptance criteria**:
  - [ ] Step-by-step guide from `git clone` to working instance
  - [ ] Prerequisites documented (Terraform, az/aws CLI, Docker)
  - [ ] All `terraform.tfvars` variables documented with examples
  - [ ] Troubleshooting section for common issues (connection limits, SSL, migration failures)
  - [ ] `make deploy-azure` wraps `terraform init + apply` with sandbox preset
- **Verification**: Follow the guide on a clean machine

#### Chunk: CI terraform-validate job

- **What**: GitHub Actions job that runs `terraform init -backend=false && terraform validate` on both Azure and AWS modules. Runs on every PR that touches `deploy/`.
- **Modules/files touched**: `.github/workflows/ci.yml`
- **Depends on**: Module structure (Wave 1)
- **Produces**: CI validation of Terraform syntax and types
- **Acceptance criteria**:
  - [ ] Job runs on PRs touching `terraform/**`
  - [ ] Validates both `azure/` and `aws/` root modules
  - [ ] No cloud credentials required (validate only)
  - [ ] Fails PR if validation fails
- **Verification**: Open a PR with an intentional Terraform syntax error and confirm CI catches it
