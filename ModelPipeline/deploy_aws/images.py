"""
Builds the backend and frontend images and pushes them to ECR.

What this module does
---------------------
Runs docker build for both services against the ModelPipeline build context,
authenticates docker to ECR, and pushes.

Why there is only one set of Dockerfiles
---------------------------------------
This module builds from finrag_docker_loc_tg1/, the same Dockerfiles local
development uses. There is deliberately no AWS-specific pair.

The finrag_docker_loc_tg1_aws/ directory did once contain its own
backend.Dockerfile, frontend.Dockerfile and docker-compose.yml. Inspection on
2026-07-31 showed they were December-era copies that nothing referenced: the
compose file there still pointed its build.dockerfile at
finrag_docker_loc_tg1/, so it never built the files sitting beside it, and its
inline curl health check would fail against the current runtime images, which
ship no apt layer and therefore no curl.

The deeper reason is that nothing about the image needs to differ. Everything
that separates local from ECS is injected, not built in:

    credentials   local: static keys via compose env_file
                  ECS:   task role, over the container credential endpoint
    BACKEND_URL   local: http://backend:8000  (compose DNS)
                  ECS:   http://localhost:8000 (shared network namespace)
    health probe  local: honoured from the image HEALTHCHECK
                  ECS:   restated in the task definition, image one ignored

All three are start-time inputs. An image that behaves differently in the two
places would mean the thing tested locally is not the thing deployed - which is
the entire property containers exist to provide.

Platform note
-------------
The target is ARM64 Fargate and the build host is an Apple Silicon Mac, so the
native build is also the correct build: no emulation, no cross-compilation.
--platform is passed explicitly anyway, so the command produces the same
artifact if it is ever run on an x86 machine or in CI.

Inputs
------
An AwsSession, and a build context path (ModelPipeline/).

Outputs
-------
Image URIs pushed to ECR.

Usage
-----
    publisher = ImagePublisher(aws, context_dir=Path("."))
    publisher.publish_all()

Author: Joel Markapudi
Date: 2026-07-31
"""

import base64
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from deploy_aws.aws_session import AwsSession

logger = logging.getLogger(__name__)


class ImagePublisher:
    """Builds and pushes the two service images."""

    def __init__(
        self,
        aws: AwsSession,
        context_dir: Path,
        log: Optional[logging.Logger] = None,
    ) -> None:
        self._aws = aws
        self._config = aws.config
        self._context = context_dir.resolve()
        self._log = log or logger
        if not (self._context / "finrag_ml_tg1").is_dir():
            raise RuntimeError(
                f"{self._context} does not look like ModelPipeline/ "
                f"(no finrag_ml_tg1 subdirectory). Run from ModelPipeline/."
            )

    @property
    def platform(self) -> str:
        """Docker platform string matching the task definition architecture."""
        return "linux/arm64" if self._config.cpu_architecture == "ARM64" else "linux/amd64"

    def _run(self, command: List[str], step: str) -> None:
        """Run a subprocess, streaming failure output into the log."""
        self._log.info("%s: %s", step, " ".join(command[:6]) + (" ..." if len(command) > 6 else ""))
        result = subprocess.run(
            command,
            cwd=str(self._context),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Docker writes progress to stderr, so the tail of stderr is where
            # the actual error is.
            tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-25:])
            raise RuntimeError(f"{step} failed (exit {result.returncode}):\n{tail}")
        self._log.info("%s: ok", step)

    def docker_login(self) -> str:
        """Authenticate the local docker daemon to this account's ECR.

        The password is a 12-hour ECR authorization token fetched through the
        API, not a stored secret, and it is handed to docker on stdin rather
        than as an argv element so it never appears in the process table.
        """
        client = self._aws.client("ecr")
        auth = client.get_authorization_token()["authorizationData"][0]
        username, password = (
            base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)
        )
        registry = auth["proxyEndpoint"].replace("https://", "")
        result = subprocess.run(
            ["docker", "login", "--username", username, "--password-stdin", registry],
            input=password,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"docker login to {registry} failed: {result.stderr.strip()}")
        self._log.info("docker authenticated to %s", registry)
        return registry

    def build_and_push(self, repo: str, dockerfile: str) -> str:
        """Build one image for the target platform and push it."""
        image_uri = self._config.image_uri(self._aws.account_id, repo)
        self._run(
            [
                "docker",
                "build",
                "--platform",
                self.platform,
                "-f",
                dockerfile,
                "-t",
                image_uri,
                ".",
            ],
            step=f"build {repo}",
        )
        self._run(["docker", "push", image_uri], step=f"push {repo}")
        return image_uri

    def publish_all(self) -> Dict[str, str]:
        """Login, then build and push both images."""
        self.docker_login()
        uris = {
            self._config.backend_repo: self.build_and_push(
                self._config.backend_repo, self._config.backend_dockerfile
            ),
            self._config.frontend_repo: self.build_and_push(
                self._config.frontend_repo, self._config.frontend_dockerfile
            ),
        }
        for repo, uri in uris.items():
            self._log.info("published %s -> %s", repo, uri)
        return uris


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from deploy_aws.config import DeployConfig

    # Read-only verification: confirm context detection and platform choice
    # without building or pushing anything.
    publisher = ImagePublisher(AwsSession(DeployConfig.from_env()), Path("."))
    logger.info("build context=%s", publisher._context)
    logger.info("target platform=%s", publisher.platform)
    for dockerfile in (
        publisher._config.backend_dockerfile,
        publisher._config.frontend_dockerfile,
    ):
        path = publisher._context / dockerfile
        assert path.is_file(), f"dockerfile missing: {path}"
        logger.info("dockerfile present: %s", dockerfile)
