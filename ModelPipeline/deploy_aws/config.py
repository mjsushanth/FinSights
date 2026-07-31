"""
Deployment configuration for the FinSights ECS Fargate stack.

What this module does
---------------------
Holds every name, size, port, and identifier the deployment needs, in one
place, as a single immutable object. Nothing else in this package hardcodes an
AWS resource name.

Why it exists
-------------
The Dec 2025 workflows scattered resource identifiers across two YAML files
that disagreed with each other: setup-infrastructure.yml created a cluster
called "finsights-cluster" while deploy-ecs.yml deployed into
"finsights-cluster-new". The teardown block therefore deleted the wrong
cluster and left the real one running and billing. One config object with one
name per resource makes that class of bug unrepresentable.

Inputs
------
Optional environment overrides (see DeployConfig.from_env). Otherwise defaults.

Outputs
-------
A frozen DeployConfig consumed by every other module in deploy_aws.

Notably absent
--------------
The AWS account ID. It is never written down; it is resolved at runtime from
STS GetCallerIdentity, so this file is safe to commit and portable to any
account.

Config keys read
----------------
None from ml_config.yaml. The resource names below intentionally duplicate a
few values that also appear in ml_config.yaml (data bucket, vector bucket,
vector index, model ids) because they are needed to build an IAM policy before
any application code is importable. They are asserted against the live account
by `deploy_aws.cli preflight`.

Usage
-----
    from deploy_aws.config import DeployConfig

    cfg = DeployConfig.from_env()
    print(cfg.cluster_name, cfg.task_cpu, cfg.task_memory)

Author: Joel Markapudi
Date: 2026-07-31
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Tuple

logger = logging.getLogger(__name__)

# Fargate only accepts specific (cpu, memory) pairs. Full table for the two
# smallest cpu values, which are the only ones this workload needs.
# Reference: task-level cpu is in vCPU units of 1024.
_VALID_FARGATE_SHAPES = {
    "512": {"1024", "2048", "3072", "4096"},
    "1024": {"2048", "3072", "4096", "5120", "6144", "7168", "8192"},
    "2048": {str(m) for m in range(4096, 16385, 1024)},
    "4096": {str(m) for m in range(8192, 30721, 1024)},
}


@dataclass(frozen=True)
class DeployConfig:
    """Immutable description of the target FinSights deployment.

    Every field has a default that reflects the decisions recorded in
    ECS_DEPLOYMENT_DESIGN.md. Override via from_env() or by constructing
    directly in a test.
    """

    # -- identity -----------------------------------------------------------
    aws_profile: str = "mjsushanth_mlops"
    region: str = "us-east-1"

    # -- ECS naming ---------------------------------------------------------
    cluster_name: str = "finsights-cluster"
    service_name: str = "finsights-app"
    task_family: str = "finsights-app"

    # -- ECR ----------------------------------------------------------------
    backend_repo: str = "finsights-backend"
    frontend_repo: str = "finsights-frontend"
    image_tag: str = "latest"

    # -- IAM ----------------------------------------------------------------
    execution_role_name: str = "finsightsEcsExecutionRole"
    task_role_name: str = "finsightsEcsTaskRole"
    task_policy_name: str = "finsightsTaskLeastPrivilege"

    # -- networking ---------------------------------------------------------
    security_group_name: str = "finsights-app-sg"
    # Only the Streamlit port is exposed. The backend is reachable solely from
    # inside the task's own network namespace, so it needs no ingress rule at
    # all - see ECS_DEPLOYMENT_DESIGN.md section "why 8501 only".
    frontend_port: int = 8501
    backend_port: int = 8000
    assign_public_ip: str = "ENABLED"
    # Number of default-VPC public subnets to hand the service. More subnets
    # means more AZs available for placement, at no cost.
    subnet_count: int = 3

    # -- task sizing --------------------------------------------------------
    # Measured 2026-07-31 on the local ARM images against real queries:
    # backend peaked at 1220 MiB serving a 10-company query, frontend stayed
    # flat at 146 MiB. 1 vCPU / 3 GB leaves roughly 2x headroom on memory
    # without stepping up to the next cpu tier.
    task_cpu: str = "1024"
    task_memory: str = "3072"
    # Per-container soft limits. They must sum to at most task_memory. A soft
    # limit lets a container burst above its reservation while the sum is
    # under the task total, which is what we want for a bursty RAG request.
    backend_memory_reservation: int = 2560
    frontend_memory_reservation: int = 384
    # Graviton. The local images are already aarch64 and served real queries
    # on 2026-07-31, so the whole dependency set is known to work on ARM.
    cpu_architecture: str = "ARM64"
    operating_system_family: str = "LINUX"

    # -- logging ------------------------------------------------------------
    log_group: str = "/ecs/finsights"
    # Retention is set explicitly. The default is "never expire", which turns
    # CloudWatch into a slowly growing bill for data nobody reads.
    log_retention_days: int = 7

    # -- application resources (used to scope the IAM task policy) ----------
    data_bucket: str = "sentence-data-ingestion-mjs"
    vector_bucket: str = "finrag-embeddings-s3vectors"
    vector_index: str = "finrag-sentence-fact-embed-1024d"
    llm_inference_profile_id: str = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    llm_foundation_model_id: str = "anthropic.claude-haiku-4-5-20251001-v1:0"
    embed_model_id: str = "cohere.embed-v4:0"
    # The regions the us.* cross-region inference profile fans out to.
    # Confirmed 2026-07-31 via bedrock get-inference-profile: the profile
    # reports us-east-1, us-east-2, us-west-2. An IAM policy that names only
    # us-east-1 will fail intermittently, whenever Bedrock happens to route
    # the request to another region.
    cris_regions: Tuple[str, ...] = ("us-east-1", "us-east-2", "us-west-2")

    # -- service ------------------------------------------------------------
    desired_count: int = 1
    # Fargate ignores the Dockerfile HEALTHCHECK instruction entirely, so the
    # probe is restated in the task definition. Measured cold start to a
    # healthy /health was about 5 s on 2026-07-31; 60 s of grace is ample.
    health_start_period: int = 60
    health_interval: int = 30
    health_timeout: int = 10
    health_retries: int = 3

    # -- build --------------------------------------------------------------
    # Build context is ModelPipeline/; the Dockerfiles live in the local
    # docker directory and are shared with local development. There is
    # deliberately no separate set of AWS Dockerfiles - see design doc.
    docker_context: str = "."
    backend_dockerfile: str = "finrag_docker_loc_tg1/backend.Dockerfile"
    frontend_dockerfile: str = "finrag_docker_loc_tg1/frontend.Dockerfile"

    # -- derived ------------------------------------------------------------
    tags: Tuple[Tuple[str, str], ...] = field(
        default=(
            ("Project", "FinSights"),
            ("ManagedBy", "deploy_aws"),
        )
    )

    def __post_init__(self) -> None:
        self._validate_shape()
        self._validate_container_memory()

    def _validate_shape(self) -> None:
        """Reject cpu/memory pairs Fargate will not accept.

        Caught here rather than at RegisterTaskDefinition, because the API
        error for an invalid pair names neither the offending value nor the
        valid alternatives.
        """
        allowed = _VALID_FARGATE_SHAPES.get(self.task_cpu)
        if allowed is None:
            raise ValueError(
                f"task_cpu={self.task_cpu!r} is not a Fargate cpu tier. "
                f"Valid tiers here: {sorted(_VALID_FARGATE_SHAPES)}"
            )
        if self.task_memory not in allowed:
            raise ValueError(
                f"task_memory={self.task_memory!r} is not valid for "
                f"task_cpu={self.task_cpu!r}. Valid: {sorted(allowed, key=int)}"
            )

    def _validate_container_memory(self) -> None:
        """Container soft limits must fit inside the task allocation."""
        total = self.backend_memory_reservation + self.frontend_memory_reservation
        if total > int(self.task_memory):
            raise ValueError(
                f"container memoryReservation sum ({total} MiB) exceeds "
                f"task_memory ({self.task_memory} MiB)"
            )

    @property
    def container_backend(self) -> str:
        return "backend"

    @property
    def container_frontend(self) -> str:
        return "frontend"

    @property
    def backend_url(self) -> str:
        """What the frontend uses to reach the backend.

        Both containers share one network namespace because they are in one
        task, so localhost is the backend. This is the wiring that costs
        nothing: no Cloud Map hosted zone, no load balancer.
        """
        return f"http://localhost:{self.backend_port}"

    def ecr_uri(self, account_id: str, repo: str) -> str:
        return f"{account_id}.dkr.ecr.{self.region}.amazonaws.com/{repo}"

    def image_uri(self, account_id: str, repo: str) -> str:
        return f"{self.ecr_uri(account_id, repo)}:{self.image_tag}"

    def tag_list(self) -> list:
        """Tags in the shape the ECS and ECR APIs expect."""
        return [{"key": k, "value": v} for k, v in self.tags]

    @classmethod
    def from_env(cls) -> "DeployConfig":
        """Build a config, letting a few environment variables override.

        Only the values that legitimately differ between operators are
        overridable. Resource names are not, because two operators using
        different names for the same resource is precisely the Dec 2025 bug.
        """
        overrides = {}
        if os.getenv("AWS_PROFILE"):
            overrides["aws_profile"] = os.environ["AWS_PROFILE"]
        if os.getenv("AWS_DEFAULT_REGION"):
            overrides["region"] = os.environ["AWS_DEFAULT_REGION"]
        if os.getenv("FINSIGHTS_IMAGE_TAG"):
            overrides["image_tag"] = os.environ["FINSIGHTS_IMAGE_TAG"]
        if os.getenv("FINSIGHTS_DESIRED_COUNT"):
            overrides["desired_count"] = int(os.environ["FINSIGHTS_DESIRED_COUNT"])
        if overrides:
            logger.info("DeployConfig overrides from environment: %s", overrides)
        return cls(**overrides)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = DeployConfig.from_env()
    logger.info("cluster=%s service=%s family=%s", cfg.cluster_name, cfg.service_name, cfg.task_family)
    logger.info("shape=%s cpu / %s MiB on %s", cfg.task_cpu, cfg.task_memory, cfg.cpu_architecture)
    logger.info("frontend reaches backend at %s", cfg.backend_url)
    logger.info("cris regions=%s", cfg.cris_regions)
    logger.info("image uri example=%s", cfg.image_uri("000000000000", cfg.backend_repo))

    # Negative check: an invalid Fargate shape must be rejected up front.
    try:
        DeployConfig(task_cpu="512", task_memory="512")
    except ValueError as exc:
        logger.info("shape validation works: %s", exc)
    else:
        raise AssertionError("invalid Fargate shape was not rejected")
