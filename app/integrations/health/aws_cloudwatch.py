"""
AWS CloudWatch health metrics provider.

Uses STS AssumeRole with external ID for cross-account access.
Batches up to 500 metrics per GetMetricData call.
Graceful when boto3 is not installed — import errors are caught at init time.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.integrations.health.base import (
    DiscoveredResource,
    HealthConnectionResult,
    HealthMetricsProvider,
    MetricDatapoint,
    MetricQuery,
)

logger = structlog.get_logger(__name__)

# Maximum metrics per GetMetricData call (AWS limit)
_MAX_METRICS_PER_CALL = 500

# STS session duration (1 hour)
_STS_SESSION_DURATION = 3600

# Map our statistic names to CloudWatch stat strings
_STAT_MAP: dict[str, str] = {
    "Average": "Average",
    "Sum": "Sum",
    "Maximum": "Maximum",
    "Minimum": "Minimum",
    "p99": "p99",
    "p95": "p95",
    "p90": "p90",
    "p50": "p50",
}


class AWSCloudWatchProvider(HealthMetricsProvider):
    """CloudWatch metrics provider.

    Two credential modes:
      1. **Ambient credentials (default)** — uses boto3's default credential chain:
         ECS task role, EC2 instance profile, env vars, ~/.aws/credentials.
         This is the natural path when Calseta runs as an ECS task in the same
         account it monitors. No ``role_arn`` needed.
      2. **Cross-account role assumption** — when ``role_arn`` is provided, the
         provider calls STS AssumeRole with an external ID. Used for monitoring
         resources in a different AWS account.

    The mode is selected automatically: if ``role_arn`` is non-empty, mode 2 is
    used; otherwise mode 1.
    """

    provider_type = "aws"

    def __init__(
        self,
        *,
        role_arn: str = "",
        external_id: str = "",
        region: str,
        session_name: str = "calseta-health",
    ) -> None:
        self._role_arn = role_arn
        self._external_id = external_id
        self._region = region
        self._session_name = session_name
        self._use_role_assumption = bool(role_arn)

        # Cached STS credentials (only used in role-assumption mode)
        self._credentials: dict[str, Any] | None = None
        self._credentials_expiry: float = 0

    def _get_boto3(self) -> Any:
        """Import boto3; raises ImportError if not installed."""
        try:
            import boto3  # type: ignore[import-untyped]

            return boto3
        except ImportError as exc:
            raise ImportError(
                "boto3 is required for AWS CloudWatch health monitoring. "
                "Install with: pip install calseta[aws]"
            ) from exc

    def _assume_role(self) -> dict[str, Any]:
        """Assume IAM role via STS. Caches credentials for session duration."""
        now = time.time()
        if self._credentials and now < self._credentials_expiry:
            return self._credentials

        boto3 = self._get_boto3()
        sts = boto3.client("sts", region_name=self._region)
        params: dict[str, Any] = {
            "RoleArn": self._role_arn,
            "RoleSessionName": self._session_name,
            "DurationSeconds": _STS_SESSION_DURATION,
        }
        if self._external_id:
            params["ExternalId"] = self._external_id
        response = sts.assume_role(**params)
        creds = response["Credentials"]
        self._credentials = {
            "aws_access_key_id": creds["AccessKeyId"],
            "aws_secret_access_key": creds["SecretAccessKey"],
            "aws_session_token": creds["SessionToken"],
        }
        # Expire 5 minutes early to avoid edge-case failures
        self._credentials_expiry = now + _STS_SESSION_DURATION - 300
        logger.info(
            "aws_cloudwatch.role_assumed",
            role_arn=self._role_arn,
            region=self._region,
        )
        return self._credentials

    def _cloudwatch_client(self) -> Any:
        """Return a CloudWatch client — ambient or assumed-role credentials."""
        boto3 = self._get_boto3()
        if self._use_role_assumption:
            creds = self._assume_role()
            return boto3.client(
                "cloudwatch", region_name=self._region, **creds
            )
        return boto3.client("cloudwatch", region_name=self._region)

    def _service_client(self, service_name: str) -> Any:
        """Return an AWS service client — ambient or assumed-role credentials."""
        boto3 = self._get_boto3()
        if self._use_role_assumption:
            creds = self._assume_role()
            return boto3.client(
                service_name, region_name=self._region, **creds
            )
        return boto3.client(service_name, region_name=self._region)

    async def test_connection(self) -> HealthConnectionResult:
        try:
            cw = self._cloudwatch_client()
            # ListMetrics with a limit of 1 — cheapest possible validation
            response = cw.list_metrics(Namespace="AWS/ECS", MaxResults=1)
            metric_count = len(response.get("Metrics", []))
            mode = "role assumption" if self._use_role_assumption else "ambient credentials"
            return HealthConnectionResult.ok(
                f"Connected to CloudWatch in {self._region} via {mode}. "
                f"Found {metric_count} metric(s) in sample namespace."
            )
        except ImportError as exc:
            return HealthConnectionResult.fail(str(exc))
        except Exception as exc:
            logger.warning(
                "aws_cloudwatch.test_connection_failed",
                error=str(exc),
                role_arn=self._role_arn,
            )
            return HealthConnectionResult.fail(
                f"Failed to connect: {exc}",
                error_type=type(exc).__name__,
            )

    async def fetch_metrics(
        self,
        queries: list[MetricQuery],
        period: timedelta,
    ) -> list[MetricDatapoint]:
        if not queries:
            return []

        try:
            cw = self._cloudwatch_client()
        except (ImportError, Exception) as exc:
            logger.error("aws_cloudwatch.fetch_metrics_client_failed", error=str(exc))
            return []

        results: list[MetricDatapoint] = []
        now = datetime.now(UTC)
        start = now - period

        # Batch in groups of 500
        for batch_start in range(0, len(queries), _MAX_METRICS_PER_CALL):
            batch = queries[batch_start : batch_start + _MAX_METRICS_PER_CALL]
            try:
                datapoints = self._fetch_batch(cw, batch, start, now)
                results.extend(datapoints)
            except Exception as exc:
                logger.error(
                    "aws_cloudwatch.fetch_batch_failed",
                    error=str(exc),
                    batch_size=len(batch),
                )

        return results

    def _fetch_batch(
        self,
        cw: Any,
        queries: list[MetricQuery],
        start: datetime,
        end: datetime,
    ) -> list[MetricDatapoint]:
        """Execute a single GetMetricData call for a batch of queries."""
        metric_data_queries = []
        id_to_config: dict[str, int] = {}

        for i, q in enumerate(queries):
            query_id = f"m{i}"
            id_to_config[query_id] = q.config_id

            stat = _STAT_MAP.get(q.statistic, q.statistic)
            dimensions = [
                {"Name": k, "Value": v} for k, v in q.dimensions.items()
            ]

            if stat.startswith("p"):
                # Extended statistics (percentiles)
                metric_data_queries.append(
                    {
                        "Id": query_id,
                        "MetricStat": {
                            "Metric": {
                                "Namespace": q.namespace,
                                "MetricName": q.metric_name,
                                "Dimensions": dimensions,
                            },
                            "Period": 300,  # 5-minute resolution
                            "Stat": stat,
                        },
                        "ReturnData": True,
                    }
                )
            else:
                metric_data_queries.append(
                    {
                        "Id": query_id,
                        "MetricStat": {
                            "Metric": {
                                "Namespace": q.namespace,
                                "MetricName": q.metric_name,
                                "Dimensions": dimensions,
                            },
                            "Period": 300,
                            "Stat": stat,
                        },
                        "ReturnData": True,
                    }
                )

        response = cw.get_metric_data(
            MetricDataQueries=metric_data_queries,
            StartTime=start,
            EndTime=end,
        )

        results: list[MetricDatapoint] = []
        for metric_result in response.get("MetricDataResults", []):
            query_id = metric_result["Id"]
            config_id = id_to_config.get(query_id)
            if config_id is None:
                continue

            values = metric_result.get("Values", [])
            timestamps = metric_result.get("Timestamps", [])

            if values and timestamps:
                # Latest value (CloudWatch returns newest first)
                results.append(
                    MetricDatapoint(
                        metric_config_id=config_id,
                        value=values[0],
                        timestamp=timestamps[0],
                        raw_datapoints={
                            "values": values[:12],  # Keep last hour at 5m resolution
                            "timestamps": [
                                t.isoformat() for t in timestamps[:12]
                            ],
                        },
                    )
                )

        return results

    async def discover_resources(
        self,
        preset: str,
    ) -> list[DiscoveredResource]:
        try:
            discover_fn = {
                "ecs": self._discover_ecs,
                "rds": self._discover_rds,
                "sqs": self._discover_sqs,
                "alb": self._discover_alb,
                "lambda": self._discover_lambda,
            }.get(preset)

            if discover_fn is None:
                logger.warning("aws_cloudwatch.unknown_preset", preset=preset)
                return []

            return discover_fn()
        except ImportError as exc:
            logger.error("aws_cloudwatch.discover_import_error", error=str(exc))
            return []
        except Exception as exc:
            logger.error(
                "aws_cloudwatch.discover_failed",
                error=str(exc),
                preset=preset,
            )
            return []

    def _discover_ecs(self) -> list[DiscoveredResource]:
        ecs = self._service_client("ecs")
        resources: list[DiscoveredResource] = []

        clusters_resp = ecs.list_clusters()
        cluster_arns = clusters_resp.get("clusterArns", [])
        if not cluster_arns:
            return resources

        desc_resp = ecs.describe_clusters(clusters=cluster_arns)
        for cluster in desc_resp.get("clusters", []):
            cluster_name = cluster["clusterName"]

            # List services in this cluster
            svc_resp = ecs.list_services(cluster=cluster_name, maxResults=100)
            svc_arns = svc_resp.get("serviceArns", [])
            if not svc_arns:
                continue

            svc_desc = ecs.describe_services(
                cluster=cluster_name, services=svc_arns
            )
            for svc in svc_desc.get("services", []):
                svc_name = svc["serviceName"]
                resources.append(
                    DiscoveredResource(
                        resource_type="ecs_service",
                        resource_id=f"{cluster_name}/{svc_name}",
                        display_name=f"{svc_name}",
                        dimensions={
                            "ClusterName": cluster_name,
                            "ServiceName": svc_name,
                        },
                        metadata={
                            "cluster": cluster_name,
                            "desired_count": svc.get("desiredCount", 0),
                            "running_count": svc.get("runningCount", 0),
                        },
                    )
                )

        return resources

    def _discover_rds(self) -> list[DiscoveredResource]:
        rds = self._service_client("rds")
        resources: list[DiscoveredResource] = []

        resp = rds.describe_db_instances()
        for instance in resp.get("DBInstances", []):
            db_id = instance["DBInstanceIdentifier"]
            resources.append(
                DiscoveredResource(
                    resource_type="rds_instance",
                    resource_id=db_id,
                    display_name=db_id,
                    dimensions={"DBInstanceIdentifier": db_id},
                    metadata={
                        "engine": instance.get("Engine", ""),
                        "instance_class": instance.get("DBInstanceClass", ""),
                        "status": instance.get("DBInstanceStatus", ""),
                    },
                )
            )

        return resources

    def _discover_sqs(self) -> list[DiscoveredResource]:
        sqs = self._service_client("sqs")
        resources: list[DiscoveredResource] = []

        resp = sqs.list_queues()
        for queue_url in resp.get("QueueUrls", []):
            # Queue name is the last segment of the URL
            queue_name = queue_url.rsplit("/", 1)[-1]
            resources.append(
                DiscoveredResource(
                    resource_type="sqs_queue",
                    resource_id=queue_name,
                    display_name=queue_name,
                    dimensions={"QueueName": queue_name},
                    metadata={"queue_url": queue_url},
                )
            )

        return resources

    def _discover_alb(self) -> list[DiscoveredResource]:
        elbv2 = self._service_client("elbv2")
        resources: list[DiscoveredResource] = []

        resp = elbv2.describe_load_balancers()
        for lb in resp.get("LoadBalancers", []):
            if lb.get("Type") != "application":
                continue
            lb_arn = lb["LoadBalancerArn"]
            lb_name = lb["LoadBalancerName"]
            # CloudWatch dimension uses the ARN suffix after "loadbalancer/"
            if "loadbalancer/" in lb_arn:
                arn_suffix = lb_arn.split("loadbalancer/", 1)[-1]
            else:
                arn_suffix = lb_arn
            resources.append(
                DiscoveredResource(
                    resource_type="alb",
                    resource_id=lb_name,
                    display_name=lb_name,
                    dimensions={"LoadBalancer": f"app/{arn_suffix}"},
                    metadata={
                        "dns_name": lb.get("DNSName", ""),
                        "state": lb.get("State", {}).get("Code", ""),
                    },
                )
            )

        return resources

    def _discover_lambda(self) -> list[DiscoveredResource]:
        lam = self._service_client("lambda")
        resources: list[DiscoveredResource] = []

        resp = lam.list_functions(MaxItems=200)
        for fn in resp.get("Functions", []):
            fn_name = fn["FunctionName"]
            resources.append(
                DiscoveredResource(
                    resource_type="lambda_function",
                    resource_id=fn_name,
                    display_name=fn_name,
                    dimensions={"FunctionName": fn_name},
                    metadata={
                        "runtime": fn.get("Runtime", ""),
                        "memory_mb": fn.get("MemorySize", 0),
                        "timeout_seconds": fn.get("Timeout", 0),
                    },
                )
            )

        return resources
