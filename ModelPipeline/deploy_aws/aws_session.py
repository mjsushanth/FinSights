"""
Single boto3 session and client factory for the deployment control plane.

What this module does
---------------------
Creates one boto3 Session from a named profile, hands out cached service
clients, and resolves the AWS account id at runtime.

Why it exists
-------------
Two reasons, both about not writing secrets down.

1. The account id is never committed. Every ARN this package builds is
   assembled from the account id that STS reports for whoever is running the
   command. The Dec 2025 deploy-ecs.yml hardcoded account 729472661729 in
   eight places; when that account was closed, the workflow became
   unrunnable and the hardcoded value became actively misleading.

2. Credentials are never read by this package. It names a profile and lets
   botocore resolve it from ~/.aws/credentials. The application's own
   credentials file at finrag_ml_tg1/.aws_secrets/ is not touched, and in the
   deployed container there are no static credentials at all - the task role
   supplies them over the container credential endpoint.

Inputs
------
A DeployConfig (for profile name and region).

Outputs
-------
Cached boto3 clients; the account id; the caller ARN.

Usage
-----
    from deploy_aws.aws_session import AwsSession
    from deploy_aws.config import DeployConfig

    aws = AwsSession(DeployConfig.from_env())
    print(aws.account_id)
    aws.client("ecs").list_clusters()

Author: Joel Markapudi
Date: 2026-07-31
"""

import logging
import os
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError, NoCredentialsError, ProfileNotFound

from deploy_aws.config import DeployConfig

logger = logging.getLogger(__name__)


class AwsSession:
    """Owns the boto3 Session and the clients built from it."""

    def __init__(self, config: DeployConfig, log: Optional[logging.Logger] = None) -> None:
        self._config = config
        self._log = log or logger
        self._session: Optional[boto3.Session] = None
        self._clients: Dict[str, Any] = {}
        self._account_id: Optional[str] = None
        self._caller_arn: Optional[str] = None
        # Retries matter here: CreateService and RegisterTaskDefinition are
        # both throttled APIs, and IAM is eventually consistent, so a fresh
        # role is briefly unassumable after creation.
        self._boto_config = BotoConfig(
            retries={"max_attempts": 8, "mode": "standard"},
            region_name=config.region,
        )

    @property
    def config(self) -> DeployConfig:
        return self._config

    @property
    def session(self) -> boto3.Session:
        """The single Session, created on first use.

        Two credential situations have to work, and they are mutually
        exclusive:

        - **A developer laptop**, where credentials live in a named profile in
          ~/.aws/credentials and nothing is in the environment.
        - **CI**, where credentials arrive as environment variables (or an OIDC
          web-identity token) and no ~/.aws/credentials file exists at all.

        Naming a profile unconditionally breaks the second case: boto3 raises
        ProfileNotFound before it ever consults the environment. So static
        environment credentials, when present, take precedence, and a missing
        profile degrades to the default chain rather than failing.
        """
        if self._session is None:
            env_credentials = bool(
                os.getenv("AWS_ACCESS_KEY_ID")
                or os.getenv("AWS_WEB_IDENTITY_TOKEN_FILE")
                or os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI")
            )
            if env_credentials:
                self._session = boto3.Session(region_name=self._config.region)
                self._log.debug(
                    "boto3 session from the default credential chain "
                    "(environment credentials present)"
                )
            else:
                try:
                    self._session = boto3.Session(
                        profile_name=self._config.aws_profile,
                        region_name=self._config.region,
                    )
                    self._log.debug(
                        "boto3 session created (profile=%s region=%s)",
                        self._config.aws_profile,
                        self._config.region,
                    )
                except ProfileNotFound:
                    self._session = boto3.Session(region_name=self._config.region)
                    self._log.warning(
                        "AWS profile %r not found - falling back to the default "
                        "credential chain",
                        self._config.aws_profile,
                    )
        return self._session

    def client(self, service: str) -> Any:
        """Return a cached client for the named service."""
        if service not in self._clients:
            self._clients[service] = self.session.client(service, config=self._boto_config)
            self._log.debug("client created: %s", service)
        return self._clients[service]

    @property
    def account_id(self) -> str:
        """The account id of the calling identity, from STS.

        Resolved once. Every ARN in this package is built from this value
        rather than a committed constant.
        """
        if self._account_id is None:
            self._identify()
        return str(self._account_id)

    @property
    def caller_arn(self) -> str:
        if self._caller_arn is None:
            self._identify()
        return str(self._caller_arn)

    def _identify(self) -> None:
        try:
            identity = self.client("sts").get_caller_identity()
        except NoCredentialsError as exc:
            raise RuntimeError(
                f"No credentials resolved for profile "
                f"{self._config.aws_profile!r}. Nothing was created."
            ) from exc
        except ClientError as exc:
            raise RuntimeError(f"STS GetCallerIdentity failed: {exc}") from exc
        self._account_id = identity["Account"]
        self._caller_arn = identity["Arn"]
        self._log.info(
            "authenticated: account=%s arn=%s region=%s",
            self._account_id,
            self._caller_arn,
            self._config.region,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    aws = AwsSession(DeployConfig.from_env())
    logger.info("account_id=%s", aws.account_id)
    logger.info("caller_arn=%s", aws.caller_arn)
    # Client caching: the same object must come back on a second request.
    assert aws.client("ecs") is aws.client("ecs"), "client cache is not working"
    logger.info("client cache verified")
