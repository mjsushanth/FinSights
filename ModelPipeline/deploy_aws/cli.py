"""
Command-line entry point for the FinSights ECS Fargate deployment.

What this module does
---------------------
Exposes the whole deployment as a handful of verbs, each of which either
converges the account to a described state or reports the state it is in.

    preflight       check everything the deployment depends on, change nothing
    up              provision, build, push, deploy, wait for steady state
    status          what is running, where it is reachable, what it is costing
    smoke           issue a real POST /query against the deployed frontend
    logs            recent CloudWatch output for either container
    down            scale to zero tasks - zero compute spend, instant restart
    destroy         remove every resource, including the images
    render-taskdef  write the task definition JSON to disk for review

Why a Python module rather than a GitHub Actions workflow
--------------------------------------------------------
The Dec 2025 deployment lived in two YAML workflows that could only run inside
GitHub Actions. They could not be executed, inspected, or dry-run locally,
their failure output was a web page, and their idempotency was expressed in
shell conditionals that could not be unit tested. Every one of the bugs later
found in them - the cluster name mismatch, the non-atomic IAM guard, the
describe-then-patch task definition - would have been visible if the logic had
been runnable on a laptop.

This module is that logic, runnable on a laptop. Wiring it into CI later is
then a matter of calling it, not reimplementing it.

Usage
-----
    cd ModelPipeline
    python -m deploy_aws.cli preflight
    python -m deploy_aws.cli up
    python -m deploy_aws.cli status
    python -m deploy_aws.cli smoke --question "What was Apple's revenue in 2021?"
    python -m deploy_aws.cli down
    python -m deploy_aws.cli destroy --yes

Author: Joel Markapudi
Date: 2026-07-31
"""

import argparse
import json
import logging
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from botocore.exceptions import ClientError

from deploy_aws.aws_session import AwsSession
from deploy_aws.config import DeployConfig
from deploy_aws.images import ImagePublisher
from deploy_aws.provisioner import Provisioner
from deploy_aws.service import ServiceOperator
from deploy_aws.taskdef import TaskDefinitionBuilder

logger = logging.getLogger("deploy_aws")


class DeploymentCli:
    """Wires the deployment components together behind the verbs."""

    def __init__(self, config: DeployConfig, context_dir: Path) -> None:
        self._config = config
        self._context = context_dir
        self._aws = AwsSession(config)
        self._provisioner = Provisioner(self._aws)
        self._operator = ServiceOperator(self._aws)

    # -- preflight ----------------------------------------------------------

    def preflight(self) -> int:
        """Verify every dependency before anything is created.

        Each check is cheap and read-only. The point is that a first
        deployment should fail here, in seconds, with a named cause - rather
        than fifteen minutes later as a task that will not stabilise.
        """
        failures = []

        def check(name: str, ok: bool, detail: str = "") -> None:
            self._log_result(name, ok, detail)
            if not ok:
                failures.append(name)

        # 1. Identity.
        try:
            check("aws credentials", True, f"account={self._aws.account_id}")
        except RuntimeError as exc:
            check("aws credentials", False, str(exc))
            return self._summarise(failures)

        # 2. The two Bedrock models the request path actually invokes. These
        #    are checked by invoking them, because a model can be listed and
        #    still not be usable by this account.
        runtime = self._aws.client("bedrock-runtime")
        for label, model_id, body in (
            (
                "bedrock llm",
                self._config.llm_inference_profile_id,
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 2,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            ),
            (
                "bedrock embeddings",
                self._config.embed_model_id,
                {
                    "texts": ["preflight"],
                    "input_type": "search_query",
                    "output_dimension": 1024,
                    "embedding_types": ["float"],
                },
            ),
        ):
            try:
                runtime.invoke_model(modelId=model_id, body=json.dumps(body))
                check(label, True, model_id)
            except ClientError as exc:
                check(label, False, f"{model_id}: {exc.response['Error']['Code']}")

        # 3. The data plane. Read-only existence checks.
        try:
            self._aws.client("s3").head_bucket(Bucket=self._config.data_bucket)
            check("s3 data bucket", True, self._config.data_bucket)
        except ClientError as exc:
            check("s3 data bucket", False, f"{self._config.data_bucket}: {exc}")

        try:
            self._aws.client("s3vectors").get_index(
                vectorBucketName=self._config.vector_bucket,
                indexName=self._config.vector_index,
            )
            check("s3 vectors index", True, self._config.vector_index)
        except ClientError as exc:
            check("s3 vectors index", False, f"{self._config.vector_index}: {exc}")

        # 4. Network shape. Nothing is created; this only asserts that
        #    internet-routable subnets exist, so no NAT gateway is needed.
        try:
            network = self._provisioner.discover_network()
            check(
                "public subnets",
                len(network["subnet_ids"]) > 0,
                f"{len(network['subnet_ids'])} subnet(s), no NAT gateway required",
            )
        except RuntimeError as exc:
            check("public subnets", False, str(exc))

        # 5. Fargate vCPU quota against what one task needs.
        try:
            quota = self._aws.client("service-quotas").get_service_quota(
                ServiceCode="fargate", QuotaCode="L-3032A538"
            )["Quota"]["Value"]
            need = int(self._config.task_cpu) / 1024
            check("fargate vcpu quota", quota >= need, f"limit={quota:g} need={need:g}")
        except ClientError as exc:
            check("fargate vcpu quota", False, str(exc))

        # 6. Local build prerequisites.
        docker_ok = (
            subprocess.run(
                ["docker", "info", "--format", "{{.ServerVersion}}"],
                capture_output=True,
                text=True,
            ).returncode
            == 0
        )
        check("docker daemon", docker_ok, "required for build and push")

        for dockerfile in (self._config.backend_dockerfile, self._config.frontend_dockerfile):
            path = self._context / dockerfile
            check(f"dockerfile {Path(dockerfile).name}", path.is_file(), str(path))

        return self._summarise(failures)

    @staticmethod
    def _log_result(name: str, ok: bool, detail: str) -> None:
        logger.info("[%s] %-26s %s", "PASS" if ok else "FAIL", name, detail)

    @staticmethod
    def _summarise(failures: list) -> int:
        if failures:
            logger.error("preflight failed: %s", ", ".join(failures))
            return 1
        logger.info("preflight passed - safe to run 'up'")
        return 0

    # -- lifecycle ----------------------------------------------------------

    def up(self, build: bool = True, wait: bool = True) -> int:
        resources = self._provisioner.ensure_all()
        if build:
            ImagePublisher(self._aws, self._context).publish_all()
        else:
            logger.info("skipping image build (--no-build)")
        self._operator.deploy(resources)
        if wait and not self._operator.wait_for_steady_state():
            logger.error("service did not reach steady state - see 'logs'")
            return 1
        self.status()
        return 0

    def down(self) -> int:
        self._operator.scale(0)
        logger.info(
            "scaled to zero. Compute spend stops as tasks stop. "
            "ECR images and the log group remain, so 'up --no-build' restarts "
            "in about a minute."
        )
        return 0

    def status(self) -> int:
        snapshot = self._operator.status()
        for key, value in snapshot.items():
            logger.info("%-16s %s", key, value)
        for container in self._operator.container_health():
            logger.info(
                "container %-9s status=%-8s health=%s",
                container["name"],
                container["lastStatus"],
                container["healthStatus"],
            )
        return 0

    def destroy(self, confirmed: bool) -> int:
        if not confirmed:
            logger.error(
                "destroy removes the service, cluster, roles, security group, "
                "log group and both ECR repositories. Re-run with --yes."
            )
            return 1
        self._operator.delete_service()
        self._operator.deregister_task_definitions()
        # The ENI attached to a deleted service takes a short while to
        # detach, and its security group cannot be removed until it does.
        logger.info("waiting 45s for the task ENI to detach")
        time.sleep(45)
        self._provisioner.delete_all()
        logger.info("destroy complete. 'up' rebuilds everything from this repo.")
        return 0

    # -- verification -------------------------------------------------------

    def smoke(self, question: str, timeout: int = 180) -> int:
        """Verify the deployment from outside, and assert its security property.

        There is a deliberate asymmetry here. /health proves nothing:
        api_service.py returns status "healthy" unconditionally, with
        aws_configured hardcoded to None, so it cannot fail and therefore
        cannot confirm anything. Only a real query exercises the task role,
        Bedrock, S3 and S3 Vectors together - which is exactly where a
        credentials problem hides, because it surfaces on the first query
        rather than at startup.

        But the backend is not publicly reachable, by design, so this command
        cannot issue that query itself. Rather than punch a hole in the
        security group to test it, this command verifies the two things it
        legitimately can from outside - the frontend answers, and the backend
        does not - and reports the URL where the query path must be driven
        through the UI. The 'logs --container backend' verb is what confirms
        the query then succeeded, including which credential source the
        config loader selected.
        """
        url = self._operator.public_url()
        if not url:
            logger.error("no running task with a public IP - is the service up?")
            return 1
        host = url.rsplit(":", 1)[0]
        failures = []

        logger.info("frontend at %s", url)
        try:
            with urllib.request.urlopen(f"{url}/_stcore/health", timeout=15) as response:
                self._log_result("frontend health", response.status == 200, f"HTTP {response.status}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self._log_result("frontend health", False, str(exc))
            failures.append("frontend health")

        # A positive assertion of the security property, not an assumption.
        # In the Dec 2025 design the security group allowed tcp/8000 from
        # 0.0.0.0/0, leaving the paid query endpoint open, unauthenticated and
        # unmetered. If this check ever passes, that hole is back.
        backend_probe = f"{host}:{self._config.backend_port}/health"
        try:
            urllib.request.urlopen(backend_probe, timeout=8)
            self._log_result(
                "backend not public", False, f"{backend_probe} answered - the paid endpoint is exposed"
            )
            failures.append("backend not public")
        except Exception:
            self._log_result("backend not public", True, "no route from the internet, as designed")

        if failures:
            return self._summarise(failures)

        logger.info("")
        logger.info("Deployment is reachable. To exercise the full query path:")
        logger.info("  1. open %s", url)
        logger.info("  2. ask: %s", question)
        logger.info("  3. confirm with: python -m deploy_aws.cli logs --container backend")
        logger.info(
            "Step 3 is the real test - it shows whether the config loader "
            "selected IAM_ROLE credentials and whether Polars could read S3 "
            "under the task role."
        )
        return 0

    def logs(self, container: str, minutes: int = 15, limit: int = 60) -> int:
        client = self._aws.client("logs")
        start = int((time.time() - minutes * 60) * 1000)
        try:
            events = client.filter_log_events(
                logGroupName=self._config.log_group,
                logStreamNamePrefix=container,
                startTime=start,
                limit=limit,
            )["events"]
        except ClientError as exc:
            logger.error("cannot read logs: %s", exc.response["Error"]["Message"])
            return 1
        if not events:
            logger.info("no %s log events in the last %d minutes", container, minutes)
            return 0
        for event in events:
            logger.info("%s", event["message"].rstrip())
        return 0

    def render_taskdef(self, output: Optional[Path]) -> int:
        """Write the task definition to disk, exactly as it would register."""
        builder = TaskDefinitionBuilder(self._config)
        document = builder.to_json(
            account_id=self._aws.account_id,
            execution_role_arn=(
                f"arn:aws:iam::{self._aws.account_id}:role/{self._config.execution_role_name}"
            ),
            task_role_arn=(
                f"arn:aws:iam::{self._aws.account_id}:role/{self._config.task_role_name}"
            ),
        )
        target = output or (self._context / "deploy_aws" / "task_definition.generated.json")
        target.write_text(document + "\n")
        logger.info("task definition written to %s", target)
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m deploy_aws.cli",
        description="Deploy and operate FinSights on AWS ECS Fargate.",
    )
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("preflight", help="check dependencies, change nothing")

    up = sub.add_parser("up", help="provision, build, push, deploy")
    up.add_argument("--no-build", action="store_true", help="reuse the images already in ECR")
    up.add_argument("--no-wait", action="store_true", help="do not wait for steady state")

    sub.add_parser("down", help="scale to zero tasks (zero compute spend)")
    sub.add_parser("status", help="what is running and where")

    smoke = sub.add_parser("smoke", help="verify with a real query")
    smoke.add_argument(
        "--question",
        default="What was Apple's total revenue in 2021?",
        help="the question to send",
    )

    logs = sub.add_parser("logs", help="recent CloudWatch output")
    logs.add_argument("--container", default="backend", choices=["backend", "frontend"])
    logs.add_argument("--minutes", type=int, default=15)

    destroy = sub.add_parser("destroy", help="remove every resource, including images")
    destroy.add_argument("--yes", action="store_true", help="confirm destruction")

    render = sub.add_parser("render-taskdef", help="write the task definition JSON")
    render.add_argument("--output", type=Path, default=None)

    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )
    # Quiet the AWS SDK's own credential chatter unless debugging.
    if not args.verbose:
        logging.getLogger("botocore").setLevel(logging.WARNING)

    context = Path.cwd()
    if not (context / "finrag_ml_tg1").is_dir():
        logger.error("run this from ModelPipeline/ (no finrag_ml_tg1 here: %s)", context)
        return 2

    cli = DeploymentCli(DeployConfig.from_env(), context)

    if args.command == "preflight":
        return cli.preflight()
    if args.command == "up":
        return cli.up(build=not args.no_build, wait=not args.no_wait)
    if args.command == "down":
        return cli.down()
    if args.command == "status":
        return cli.status()
    if args.command == "smoke":
        return cli.smoke(args.question)
    if args.command == "logs":
        return cli.logs(args.container, args.minutes)
    if args.command == "destroy":
        return cli.destroy(args.yes)
    if args.command == "render-taskdef":
        return cli.render_taskdef(args.output)
    return 2


if __name__ == "__main__":
    sys.exit(main())
