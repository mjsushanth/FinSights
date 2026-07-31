"""
IAM policy documents for the FinSights ECS task.

What this module does
---------------------
Builds the two IAM documents the deployment needs: the trust policy that lets
ECS assume a role on the task's behalf, and a least-privilege permissions
policy scoped to exactly the Bedrock models, S3 prefixes, and S3 Vectors index
this application touches.

Why it exists
-------------
The Dec 2025 task role (aws_ecs_task_rules) carried AmazonBedrockFullAccess
and AmazonS3FullAccess. Between them those grant every Bedrock action on every
model, and every S3 action on every bucket in the account - including
DeleteObject on the vector staging tables that cost real money and days of
compute to regenerate. A public frontend fronted a container holding those
permissions.

The policy here is narrower in four specific ways:
  - Bedrock is limited to the two models actually invoked, and only to the
    two invoke actions. No ListFoundationModels, no CreateModelCustomizationJob.
  - S3 read is limited to one bucket.
  - S3 write is limited to one prefix inside that bucket, the query-log path.
    Nothing can overwrite the corpus or the embedding tables.
  - No delete action is granted anywhere.

The two roles are deliberately separate, because they are assumed at different
times by different components:
  - execution role: used by the ECS agent, before the container starts, to
    pull the image from ECR and create the log stream. Uses the AWS managed
    policy, which is the correct tool for that job.
  - task role: used by the application code inside the container, at request
    time. This is the one that must be narrow.

Inputs
------
A DeployConfig, plus the account id resolved at runtime.

Outputs
-------
Policy documents as plain dicts, ready for json.dumps into the IAM API.

Usage
-----
    from deploy_aws.policies import IamPolicies

    policies = IamPolicies(cfg)
    trust = policies.ecs_tasks_trust_policy()
    perms = policies.task_role_policy(account_id=session.account_id)

Author: Joel Markapudi
Date: 2026-07-31
"""

import json
import logging
from typing import Any, Dict, List

from deploy_aws.config import DeployConfig

logger = logging.getLogger(__name__)

# Managed policy for the execution role. This is the one place an AWS managed
# policy is the right answer: it grants ecr:GetAuthorizationToken,
# ecr:BatchGetImage and logs:CreateLogStream/PutLogEvents, which is exactly
# the ECS agent's job and nothing more.
EXECUTION_MANAGED_POLICY_ARN = (
    "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
)


class IamPolicies:
    """Builds the IAM documents for the FinSights task roles."""

    def __init__(self, config: DeployConfig) -> None:
        self._config = config

    def ecs_tasks_trust_policy(self) -> Dict[str, Any]:
        """Who may assume the role.

        ecs-tasks.amazonaws.com is the ECS task service principal. Note this
        is not ecs.amazonaws.com - that is the cluster service principal, and
        using it produces a role that looks correct in the console and then
        fails at task start with an unhelpful message.
        """
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

    def _bedrock_resources(self, account_id: str) -> List[str]:
        """Every ARN Bedrock needs for a cross-region inference call.

        A CRIS ("us.*") model id is not a foundation model - it is an
        inference profile that fans requests out across regions. Invoking it
        requires permission on two distinct kinds of resource:

          1. the inference profile itself, which is account-scoped, and
          2. the underlying foundation model in every region the profile can
             route to, which is account-agnostic (note the empty account
             field in those ARNs).

        Granting only (1), or granting (2) in us-east-1 alone, produces the
        worst kind of failure: it works most of the time and throws
        AccessDeniedException whenever Bedrock happens to route elsewhere.
        The region list comes from bedrock:GetInferenceProfile, not from a
        guess - see DeployConfig.cris_regions.
        """
        cfg = self._config
        resources = [
            f"arn:aws:bedrock:{cfg.region}:{account_id}:inference-profile/"
            f"{cfg.llm_inference_profile_id}"
        ]
        for region in cfg.cris_regions:
            resources.append(
                f"arn:aws:bedrock:{region}::foundation-model/{cfg.llm_foundation_model_id}"
            )
        # The embedding model is invoked on demand, directly, with no CRIS
        # prefix - so it needs only its own region.
        resources.append(
            f"arn:aws:bedrock:{cfg.region}::foundation-model/{cfg.embed_model_id}"
        )
        return resources

    def task_role_policy(self, account_id: str) -> Dict[str, Any]:
        """The permissions the application itself needs at request time."""
        cfg = self._config
        bucket_arn = f"arn:aws:s3:::{cfg.data_bucket}"
        index_arn = (
            f"arn:aws:s3vectors:{cfg.region}:{account_id}:bucket/"
            f"{cfg.vector_bucket}/index/{cfg.vector_index}"
        )
        vector_bucket_arn = (
            f"arn:aws:s3vectors:{cfg.region}:{account_id}:bucket/{cfg.vector_bucket}"
        )

        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "BedrockInvokeOnly",
                    "Effect": "Allow",
                    "Action": [
                        "bedrock:InvokeModel",
                        "bedrock:InvokeModelWithResponseStream",
                    ],
                    "Resource": self._bedrock_resources(account_id),
                },
                {
                    "Sid": "S3ReadCorpusAndTables",
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:GetObjectVersion"],
                    "Resource": [f"{bucket_arn}/*"],
                },
                {
                    "Sid": "S3ListForPolarsScan",
                    "Effect": "Allow",
                    # Polars object_store lists a prefix before it reads any
                    # parquet part files, so ListBucket is not optional.
                    # GetBucketLocation is what botocore calls to confirm the
                    # regional endpoint.
                    "Action": ["s3:ListBucket", "s3:GetBucketLocation"],
                    "Resource": [bucket_arn],
                },
                {
                    "Sid": "S3WriteQueryLogsOnly",
                    "Effect": "Allow",
                    # QueryLogger appends to query_logs.parquet and writes
                    # per-query context and response artifacts. All three live
                    # under this one prefix, so write access stops here and
                    # cannot reach ML_EMBED_ASSETS.
                    "Action": ["s3:PutObject"],
                    "Resource": [f"{bucket_arn}/DATA_MERGE_ASSETS/LOGS/FINRAG/*"],
                },
                {
                    "Sid": "S3VectorsQueryOnly",
                    "Effect": "Allow",
                    # Read path only. PutVectors and DeleteVectors are
                    # deliberately absent: bulk ingestion is an offline
                    # platform_core job, not something a serving container
                    # should ever be able to do.
                    "Action": [
                        "s3vectors:QueryVectors",
                        "s3vectors:GetVectors",
                        "s3vectors:GetIndex",
                    ],
                    "Resource": [index_arn, vector_bucket_arn],
                },
            ],
        }

    def task_role_policy_json(self, account_id: str) -> str:
        return json.dumps(self.task_role_policy(account_id))

    def trust_policy_json(self) -> str:
        return json.dumps(self.ecs_tasks_trust_policy())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = DeployConfig.from_env()
    policies = IamPolicies(cfg)
    doc = policies.task_role_policy("000000000000")

    # Verification: the policy must grant no wildcard action and no delete.
    for statement in doc["Statement"]:
        for action in statement["Action"]:
            assert action != "*", f"wildcard action in {statement['Sid']}"
            assert not action.endswith(":*"), f"service wildcard in {statement['Sid']}"
            assert "Delete" not in action, f"delete granted in {statement['Sid']}"
    logger.info("policy has %d statements, no wildcards, no deletes", len(doc["Statement"]))

    bedrock = [s for s in doc["Statement"] if s["Sid"] == "BedrockInvokeOnly"][0]
    logger.info("bedrock resources (%d):", len(bedrock["Resource"]))
    for resource in bedrock["Resource"]:
        logger.info("  %s", resource)
    logger.info("trust policy: %s", policies.trust_policy_json())
