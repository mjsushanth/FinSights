"""
Builds the ECS task definition for the FinSights stack.

What this module does
---------------------
Produces the exact dict passed to ecs:RegisterTaskDefinition: one task, two
containers, sharing a network namespace.

Why it exists
-------------
This is the file whose absence killed the December 2025 deployment. That
deployment's task definitions were created by hand in the AWS console and
existed nowhere else. deploy-ecs.yml could only read the live definition back,
patch the image URI into it, and re-register:

    aws ecs describe-task-definition --task-definition finsights-backend-task \\
      | jq 'del(.taskDefinitionArn, .revision, ...)' > task-def-clean.json

That works only while a previous revision already exists to be read. When the
account was closed, the definitions went with it, and nothing in the repository
could recreate them. The workflow's first step became a describe call against
something that had never existed.

Building the definition from code inverts that dependency: the repository is
the source of truth and AWS holds a copy, rather than AWS holding the truth and
the repository holding a patch script.

Design decisions encoded here
-----------------------------
1. One task, two containers. Both containers share a single network namespace,
   so the frontend reaches the backend at localhost:8000. This is why the
   deployment needs no load balancer (~$16.43/mo) and no Cloud Map private
   hosted zone (~$0.50/mo). The alternative - two services - buys independent
   scaling, but independent scaling is only useful with a load balancer to
   distribute across the replicas, so the cheaper option is also the more
   capable one at this scale.

2. The health check is restated here even though both Dockerfiles already
   carry a HEALTHCHECK instruction. Fargate ignores the image's HEALTHCHECK
   entirely. A container whose only probe lives in the Dockerfile reports
   health status UNKNOWN forever on Fargate, and dependsOn: HEALTHY against it
   never becomes satisfied, so the dependent container never starts.

3. dependsOn with condition HEALTHY reproduces docker-compose's
   `depends_on: {condition: service_healthy}`. ECS cannot express ordering
   between two *services* - it reconciles them independently and continuously -
   but it can express ordering between containers inside one task. Co-locating
   is what makes the local compose semantics survive the move to ECS.

4. AWS_EXECUTION_ENV is set explicitly. ml_config_loader.py detects a cloud
   runtime by checking AWS_EXECUTION_ENV, AWS_LAMBDA_FUNCTION_NAME, or
   ECS_CONTAINER_METADATA_URI, and switches to IAM_ROLE credentials when any
   is present. Modern Fargate platform versions inject the *v4* variable name
   (ECS_CONTAINER_METADATA_URI_V4), which that check does not look for.
   Setting AWS_EXECUTION_ENV ourselves makes the detection deterministic
   instead of dependent on platform-version trivia. It is one line of config
   against a failure that would otherwise surface as the container silently
   looking for a credentials file that is not in the image.

Inputs
------
A DeployConfig, the account id, and the two role ARNs.

Outputs
-------
A dict ready for RegisterTaskDefinition, and a JSON rendering for the repo.

Usage
-----
    builder = TaskDefinitionBuilder(cfg)
    document = builder.build(account_id, execution_role_arn, task_role_arn)

Author: Joel Markapudi
Date: 2026-07-31
"""

import json
import logging
from typing import Any, Dict, List

from deploy_aws.config import DeployConfig

logger = logging.getLogger(__name__)


class TaskDefinitionBuilder:
    """Renders the FinSights ECS task definition."""

    def __init__(self, config: DeployConfig) -> None:
        self._config = config

    @staticmethod
    def _http_probe(url: str) -> List[str]:
        """A health check that needs no curl in the image.

        Both runtime images are built from python:3.12-slim with no apt layer
        at all, so curl is absent by design. The CMD form (rather than
        CMD-SHELL) is used so the probe argv is passed straight to exec with
        no shell quoting in the middle.
        """
        return [
            "CMD",
            "python",
            "-c",
            (
                "import urllib.request,sys; "
                f"sys.exit(0 if urllib.request.urlopen('{url}', timeout=5).status == 200 "
                "else 1)"
            ),
        ]

    def _log_configuration(self, stream_prefix: str) -> Dict[str, Any]:
        cfg = self._config
        return {
            "logDriver": "awslogs",
            "options": {
                "awslogs-group": cfg.log_group,
                "awslogs-region": cfg.region,
                "awslogs-stream-prefix": stream_prefix,
            },
        }

    def _backend_container(self, account_id: str) -> Dict[str, Any]:
        cfg = self._config
        return {
            "name": cfg.container_backend,
            "image": cfg.image_uri(account_id, cfg.backend_repo),
            "essential": True,
            "memoryReservation": cfg.backend_memory_reservation,
            "portMappings": [
                {
                    "containerPort": cfg.backend_port,
                    "protocol": "tcp",
                }
            ],
            "environment": [
                # Deterministic cloud-runtime detection - see module docstring.
                {"name": "AWS_EXECUTION_ENV", "value": "AWS_ECS_FARGATE"},
                # Polars reaches S3 through the Rust object_store crate, which
                # does its own credential and region resolution rather than
                # going through botocore. Naming the region explicitly removes
                # one way that path can differ from boto3's.
                {"name": "AWS_DEFAULT_REGION", "value": cfg.region},
                {"name": "AWS_REGION", "value": cfg.region},
                # Also baked into the image, restated so the task definition
                # reads as a complete description of the runtime. Losing it
                # silently selects LOCAL_CACHE mode and the container then
                # fails looking for parquet tables that are not in the image.
                {"name": "MODEL_PIPELINE_ROOT", "value": "/app"},
            ],
            "healthCheck": {
                "command": self._http_probe(f"http://localhost:{cfg.backend_port}/health"),
                "interval": cfg.health_interval,
                "timeout": cfg.health_timeout,
                "retries": cfg.health_retries,
                "startPeriod": cfg.health_start_period,
            },
            "logConfiguration": self._log_configuration("backend"),
        }

    def _frontend_container(self, account_id: str) -> Dict[str, Any]:
        cfg = self._config
        return {
            "name": cfg.container_frontend,
            "image": cfg.image_uri(account_id, cfg.frontend_repo),
            "essential": True,
            "memoryReservation": cfg.frontend_memory_reservation,
            "portMappings": [
                {
                    "containerPort": cfg.frontend_port,
                    "protocol": "tcp",
                }
            ],
            "environment": [
                # The whole cost argument in one line: localhost, not a
                # service-discovery DNS name, not a load balancer DNS name.
                {"name": "BACKEND_URL", "value": cfg.backend_url},
                {"name": "STREAMLIT_SERVER_HEADLESS", "value": "true"},
                {"name": "STREAMLIT_BROWSER_GATHER_USAGE_STATS", "value": "false"},
            ],
            # Reproduces the local compose ordering guarantee.
            "dependsOn": [
                {"containerName": cfg.container_backend, "condition": "HEALTHY"}
            ],
            "healthCheck": {
                "command": self._http_probe(
                    f"http://localhost:{cfg.frontend_port}/_stcore/health"
                ),
                "interval": cfg.health_interval,
                "timeout": cfg.health_timeout,
                "retries": cfg.health_retries,
                "startPeriod": cfg.health_start_period,
            },
            "logConfiguration": self._log_configuration("frontend"),
        }

    def build(
        self,
        account_id: str,
        execution_role_arn: str,
        task_role_arn: str,
    ) -> Dict[str, Any]:
        """Assemble the full RegisterTaskDefinition payload."""
        cfg = self._config
        document = {
            "family": cfg.task_family,
            # awsvpc is the only network mode Fargate supports. It is also
            # what gives the task its own ENI and its own private IP, and what
            # makes "localhost" mean "this task" rather than "this host".
            "networkMode": "awsvpc",
            "requiresCompatibilities": ["FARGATE"],
            "cpu": cfg.task_cpu,
            "memory": cfg.task_memory,
            "runtimePlatform": {
                "cpuArchitecture": cfg.cpu_architecture,
                "operatingSystemFamily": cfg.operating_system_family,
            },
            # Two roles, two different assumers, two different moments.
            # executionRoleArn is used by the ECS agent before the container
            # exists, to pull from ECR and open the log stream. taskRoleArn is
            # used by the application process at request time.
            "executionRoleArn": execution_role_arn,
            "taskRoleArn": task_role_arn,
            "containerDefinitions": [
                self._backend_container(account_id),
                self._frontend_container(account_id),
            ],
            "tags": cfg.tag_list(),
        }
        logger.debug("task definition built for family=%s", cfg.task_family)
        return document

    def to_json(
        self,
        account_id: str,
        execution_role_arn: str,
        task_role_arn: str,
    ) -> str:
        """Render for committing to the repo alongside the code."""
        return json.dumps(
            self.build(account_id, execution_role_arn, task_role_arn), indent=2
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = DeployConfig.from_env()
    builder = TaskDefinitionBuilder(cfg)
    document = builder.build(
        account_id="000000000000",
        execution_role_arn="arn:aws:iam::000000000000:role/exec",
        task_role_arn="arn:aws:iam::000000000000:role/task",
    )

    # Verification: the invariants that actually break deployments.
    assert document["networkMode"] == "awsvpc", "Fargate requires awsvpc"
    containers = {c["name"]: c for c in document["containerDefinitions"]}
    assert set(containers) == {"backend", "frontend"}, "expected exactly two containers"
    for name, container in containers.items():
        assert "healthCheck" in container, f"{name} has no healthCheck restated for Fargate"
        assert "logConfiguration" in container, f"{name} would produce no logs"
    frontend_env = {e["name"]: e["value"] for e in containers["frontend"]["environment"]}
    assert frontend_env["BACKEND_URL"] == "http://localhost:8000", "wiring is not localhost"
    assert containers["frontend"]["dependsOn"][0]["condition"] == "HEALTHY", "no ordering"
    backend_env = {e["name"]: e["value"] for e in containers["backend"]["environment"]}
    assert backend_env["AWS_EXECUTION_ENV"] == "AWS_ECS_FARGATE", "cred detection not pinned"
    reserved = sum(c["memoryReservation"] for c in containers.values())
    assert reserved <= int(document["memory"]), "container reservations exceed task memory"

    logger.info(
        "task definition valid: %s cpu / %s MiB, arch=%s, reservations=%d MiB",
        document["cpu"],
        document["memory"],
        document["runtimePlatform"]["cpuArchitecture"],
        reserved,
    )
    logger.info("no load balancer, no service discovery: frontend -> %s", frontend_env["BACKEND_URL"])
