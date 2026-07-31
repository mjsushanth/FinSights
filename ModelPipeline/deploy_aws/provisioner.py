"""
Idempotent creation and deletion of the AWS resources the FinSights task needs.

What this module does
---------------------
Brings six things into existence, in dependency order, and can remove all of
them again: two ECR repositories, a CloudWatch log group, two IAM roles, a
security group, and an ECS cluster. Also discovers which subnets to place the
task in.

Why it exists, and the bug it is written against
------------------------------------------------
setup-infrastructure.yml guarded IAM creation like this:

    if aws iam get-role --role-name "$ROLE" 2>/dev/null; then
      echo "exists"
    else
      aws iam create-role ...
      aws iam attach-role-policy ...
    fi

The flaw is that the guard tests only whether the *role* exists, while the
body performs two operations. If create-role succeeded and
attach-role-policy then failed - a throttle, a transient error, a cancelled
workflow run - the role now exists with no policy attached. Every subsequent
run takes the "exists" branch, prints a reassuring message, and never repairs
the missing policy. The failure surfaces much later as AccessDenied from
inside a running container, a long way from its cause.

The rule this module follows instead: guard only the operation that is
genuinely not idempotent, and let the naturally idempotent operations run
unconditionally on every invocation.

  - CreateRole is not idempotent (EntityAlreadyExists). Guard it.
  - AttachRolePolicy and PutRolePolicy are idempotent by definition - they
    describe a desired end state. Never guard them. Running them every time is
    what makes a half-built role self-heal on the next run.
  - PutRetentionPolicy is idempotent. Run it every time, so changing the
    retention constant in config takes effect without a teardown.

Inputs
------
An AwsSession and its DeployConfig.

Outputs
-------
Resource identifiers (role ARNs, security group id, subnet ids) needed by the
task definition and the service.

Usage
-----
    provisioner = Provisioner(AwsSession(DeployConfig.from_env()))
    resources = provisioner.ensure_all()

Author: Joel Markapudi
Date: 2026-07-31
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from deploy_aws.aws_session import AwsSession
from deploy_aws.policies import EXECUTION_MANAGED_POLICY_ARN, IamPolicies

logger = logging.getLogger(__name__)


@dataclass
class ProvisionedResources:
    """Identifiers produced by a successful ensure_all()."""

    execution_role_arn: str
    task_role_arn: str
    security_group_id: str
    subnet_ids: List[str]
    cluster_arn: str
    backend_repo_uri: str
    frontend_repo_uri: str


class Provisioner:
    """Creates, repairs, and removes the FinSights AWS resources."""

    def __init__(self, aws: AwsSession, log: Optional[logging.Logger] = None) -> None:
        self._aws = aws
        self._config = aws.config
        self._log = log or logger
        self._policies = IamPolicies(aws.config)

    # -- ECR ----------------------------------------------------------------

    def ensure_ecr_repositories(self) -> Dict[str, str]:
        """Create both image repositories if absent; return their URIs."""
        client = self._aws.client("ecr")
        uris: Dict[str, str] = {}
        for repo in (self._config.backend_repo, self._config.frontend_repo):
            try:
                response = client.create_repository(
                    repositoryName=repo,
                    imageScanningConfiguration={"scanOnPush": False},
                    tags=[{"Key": k, "Value": v} for k, v in self._config.tags],
                )
                uris[repo] = response["repository"]["repositoryUri"]
                self._log.info("ECR repository created: %s", repo)
            except client.exceptions.RepositoryAlreadyExistsException:
                response = client.describe_repositories(repositoryNames=[repo])
                uris[repo] = response["repositories"][0]["repositoryUri"]
                self._log.info("ECR repository already present: %s", repo)

            # Idempotent, so applied unconditionally. Without this, every
            # rebuild leaves the previous untagged image behind and ECR
            # storage grows without bound. Each image pair is roughly 1.5 GB
            # uncompressed, so this is the difference between a few cents a
            # month and a slowly climbing line item.
            client.put_lifecycle_policy(
                repositoryName=repo,
                lifecyclePolicyText=json.dumps(
                    {
                        "rules": [
                            {
                                "rulePriority": 1,
                                "description": "Expire untagged images after 1 day",
                                "selection": {
                                    "tagStatus": "untagged",
                                    "countType": "sinceImagePushed",
                                    "countUnit": "days",
                                    "countNumber": 1,
                                },
                                "action": {"type": "expire"},
                            }
                        ]
                    }
                ),
            )
        return uris

    def delete_ecr_repositories(self) -> None:
        client = self._aws.client("ecr")
        for repo in (self._config.backend_repo, self._config.frontend_repo):
            try:
                client.delete_repository(repositoryName=repo, force=True)
                self._log.info("ECR repository deleted: %s", repo)
            except client.exceptions.RepositoryNotFoundException:
                self._log.info("ECR repository already absent: %s", repo)

    # -- CloudWatch Logs ----------------------------------------------------

    def ensure_log_group(self) -> str:
        """Create the log group and always reassert its retention."""
        client = self._aws.client("logs")
        group = self._config.log_group
        try:
            client.create_log_group(
                logGroupName=group,
                tags={k: v for k, v in self._config.tags},
            )
            self._log.info("log group created: %s", group)
        except client.exceptions.ResourceAlreadyExistsException:
            self._log.info("log group already present: %s", group)

        # Unconditional: retention defaults to "never expire", which is the
        # single most common way a hobby account accumulates CloudWatch cost.
        client.put_retention_policy(
            logGroupName=group,
            retentionInDays=self._config.log_retention_days,
        )
        self._log.info("log retention set to %d days", self._config.log_retention_days)
        return group

    def delete_log_group(self) -> None:
        client = self._aws.client("logs")
        try:
            client.delete_log_group(logGroupName=self._config.log_group)
            self._log.info("log group deleted: %s", self._config.log_group)
        except client.exceptions.ResourceNotFoundException:
            self._log.info("log group already absent: %s", self._config.log_group)

    # -- IAM ----------------------------------------------------------------

    def _ensure_role(self, role_name: str) -> str:
        """Create the role if it does not exist; return its ARN.

        This is the only guarded operation in the IAM path, because CreateRole
        is the only one that is not idempotent.
        """
        client = self._aws.client("iam")
        try:
            response = client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=self._policies.trust_policy_json(),
                Description="FinSights ECS role, managed by deploy_aws",
                Tags=[{"Key": k, "Value": v} for k, v in self._config.tags],
            )
            arn = response["Role"]["Arn"]
            self._log.info("IAM role created: %s", role_name)
            # IAM is eventually consistent. A role can exist and still not be
            # assumable for a few seconds, which surfaces as an opaque
            # "Unable to assume role" from CreateService.
            client.get_waiter("role_exists").wait(RoleName=role_name)
            time.sleep(8)
        except client.exceptions.EntityAlreadyExistsException:
            arn = client.get_role(RoleName=role_name)["Role"]["Arn"]
            self._log.info("IAM role already present: %s", role_name)
            # Reassert the trust policy. If a previous run created the role
            # and then died, or someone edited it by hand, this repairs it.
            client.update_assume_role_policy(
                RoleName=role_name,
                PolicyDocument=self._policies.trust_policy_json(),
            )
        return arn

    def ensure_execution_role(self) -> str:
        """The role the ECS agent uses to pull images and open log streams."""
        client = self._aws.client("iam")
        role_name = self._config.execution_role_name
        arn = self._ensure_role(role_name)
        # Unconditional and idempotent - the repair path for the Dec 2025 bug.
        client.attach_role_policy(
            RoleName=role_name,
            PolicyArn=EXECUTION_MANAGED_POLICY_ARN,
        )
        self._log.info("execution role policy asserted: %s", role_name)
        return arn

    def ensure_task_role(self) -> str:
        """The role the application assumes at request time."""
        client = self._aws.client("iam")
        role_name = self._config.task_role_name
        arn = self._ensure_role(role_name)
        # An inline policy rather than a managed one, deliberately: it is
        # versioned with this repository, it cannot be attached to anything
        # else by accident, and PutRolePolicy is a full replace - so editing
        # policies.py and re-running converges the live policy to the file
        # with no drift and no detach step.
        client.put_role_policy(
            RoleName=role_name,
            PolicyName=self._config.task_policy_name,
            PolicyDocument=self._policies.task_role_policy_json(self._aws.account_id),
        )
        self._log.info("task role least-privilege policy asserted: %s", role_name)
        return arn

    def delete_roles(self) -> None:
        client = self._aws.client("iam")
        # A role cannot be deleted while anything is attached to it.
        try:
            client.detach_role_policy(
                RoleName=self._config.execution_role_name,
                PolicyArn=EXECUTION_MANAGED_POLICY_ARN,
            )
        except ClientError as exc:
            self._log.debug("execution policy detach skipped: %s", exc)
        try:
            client.delete_role_policy(
                RoleName=self._config.task_role_name,
                PolicyName=self._config.task_policy_name,
            )
        except ClientError as exc:
            self._log.debug("task inline policy delete skipped: %s", exc)
        for role_name in (self._config.execution_role_name, self._config.task_role_name):
            try:
                client.delete_role(RoleName=role_name)
                self._log.info("IAM role deleted: %s", role_name)
            except client.exceptions.NoSuchEntityException:
                self._log.info("IAM role already absent: %s", role_name)

    # -- networking ---------------------------------------------------------

    def discover_network(self) -> Dict[str, Any]:
        """Find the default VPC and its internet-routable subnets.

        Why the default VPC is the right answer here rather than a laziness:
        every one of its subnets is associated with a route table whose
        0.0.0.0/0 route points at an internet gateway. An internet gateway is
        free. A task placed in such a subnet with a public IP has outbound
        internet access - which it needs, to reach Bedrock and S3 - at no
        charge.

        The alternative shape, private subnets, would need a NAT gateway for
        that same egress: about $32.85/mo per availability zone plus $0.045/GB
        processed. That single choice costs more per month than the compute
        this deployment is expected to use.
        """
        client = self._aws.client("ec2")
        vpcs = client.describe_vpcs(
            Filters=[{"Name": "isDefault", "Values": ["true"]}]
        )["Vpcs"]
        if not vpcs:
            raise RuntimeError(
                "No default VPC in this region. Create one with "
                "'aws ec2 create-default-vpc', or extend this module to "
                "build a VPC explicitly."
            )
        vpc_id = vpcs[0]["VpcId"]

        # Only accept subnets that genuinely route to an internet gateway.
        # MapPublicIpOnLaunch alone is not proof: public versus private is a
        # property of the associated route table, not of the subnet.
        route_tables = client.describe_route_tables(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )["RouteTables"]
        # Three facts are needed, and conflating any two of them gets the
        # answer wrong: which subnets route to an IGW via an explicit
        # association, which subnets are explicitly associated with anything
        # at all, and whether the VPC's main route table itself reaches an IGW.
        igw_subnets: set = set()
        explicitly_associated: set = set()
        main_routes_to_igw = False
        for table in route_tables:
            has_igw = any(
                route.get("GatewayId", "").startswith("igw-")
                for route in table.get("Routes", [])
            )
            for association in table.get("Associations", []):
                subnet_id = association.get("SubnetId")
                if subnet_id:
                    explicitly_associated.add(subnet_id)
                    if has_igw:
                        igw_subnets.add(subnet_id)
                elif association.get("Main") and has_igw:
                    main_routes_to_igw = True

        subnets = client.describe_subnets(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]
        )["Subnets"]
        usable = [
            subnet
            for subnet in subnets
            if subnet["SubnetId"] in igw_subnets
            # A subnet with no explicit association inherits the main table.
            # It is public only if the main table itself reaches an IGW - a
            # subnet explicitly bound to a private table must not be accepted
            # just because the main table happens to be public.
            or (
                main_routes_to_igw
                and subnet["SubnetId"] not in explicitly_associated
            )
        ]
        if not usable:
            raise RuntimeError(f"No internet-routable subnets found in {vpc_id}")

        # Spread across availability zones, one subnet per AZ, deterministic
        # order so repeated runs produce the same service configuration.
        by_az: Dict[str, str] = {}
        for subnet in sorted(usable, key=lambda s: s["AvailabilityZone"]):
            by_az.setdefault(subnet["AvailabilityZone"], subnet["SubnetId"])
        subnet_ids = list(by_az.values())[: self._config.subnet_count]

        self._log.info(
            "network: vpc=%s subnets=%s (azs=%s)",
            vpc_id,
            subnet_ids,
            list(by_az)[: self._config.subnet_count],
        )
        return {"vpc_id": vpc_id, "subnet_ids": subnet_ids}

    def ensure_security_group(self, vpc_id: str) -> str:
        """One ingress rule: the Streamlit port. Nothing else.

        The backend port is deliberately not opened. In the Dec 2025 design
        the security group allowed tcp/8000 from 0.0.0.0/0, which made the
        paid /query endpoint directly reachable from the internet without
        authentication and without metering - roughly $0.017-$0.06 of Bedrock
        spend per call, to anyone who found the IP.

        Co-locating the containers closes that at zero cost: the backend
        listens on the task's loopback interface, reachable only from inside
        the task's own network namespace. There is no rule to write, because
        there is no path to block.
        """
        client = self._aws.client("ec2")
        name = self._config.security_group_name
        existing = client.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [name]},
                {"Name": "vpc-id", "Values": [vpc_id]},
            ]
        )["SecurityGroups"]
        if existing:
            group_id = existing[0]["GroupId"]
            self._log.info("security group already present: %s (%s)", name, group_id)
        else:
            group_id = client.create_security_group(
                GroupName=name,
                Description="FinSights frontend ingress, managed by deploy_aws",
                VpcId=vpc_id,
                TagSpecifications=[
                    {
                        "ResourceType": "security-group",
                        "Tags": [{"Key": k, "Value": v} for k, v in self._config.tags],
                    }
                ],
            )["GroupId"]
            self._log.info("security group created: %s (%s)", name, group_id)

        # Unconditional; the duplicate case is the success case.
        try:
            client.authorize_security_group_ingress(
                GroupId=group_id,
                IpPermissions=[
                    {
                        "IpProtocol": "tcp",
                        "FromPort": self._config.frontend_port,
                        "ToPort": self._config.frontend_port,
                        "IpRanges": [
                            {
                                "CidrIp": "0.0.0.0/0",
                                "Description": "Streamlit UI - public by design",
                            }
                        ],
                    }
                ],
            )
            self._log.info("ingress authorised: tcp/%d", self._config.frontend_port)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "InvalidPermission.Duplicate":
                raise
            self._log.info("ingress rule already present: tcp/%d", self._config.frontend_port)
        return group_id

    def delete_security_group(self) -> None:
        client = self._aws.client("ec2")
        groups = client.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [self._config.security_group_name]}]
        )["SecurityGroups"]
        for group in groups:
            try:
                client.delete_security_group(GroupId=group["GroupId"])
                self._log.info("security group deleted: %s", group["GroupId"])
            except ClientError as exc:
                # A security group still attached to a draining ENI cannot be
                # deleted. This is expected immediately after service deletion.
                self._log.warning(
                    "security group %s not deleted yet (%s). Retry in a minute.",
                    group["GroupId"],
                    exc.response["Error"]["Code"],
                )

    # -- ECS cluster --------------------------------------------------------

    def ensure_service_linked_role(self) -> None:
        """Create AWSServiceRoleForECS if this account has never used ECS.

        A service-linked role is a role in your account that an AWS service
        assumes to act on your behalf - here, so ECS can manage elastic
        network interfaces, register targets, and place tasks. It is not the
        execution role and not the task role; it belongs to the service, not
        to the workload.

        The console creates it silently the first time anyone opens the ECS
        page, which is why this failure is almost never seen by people who
        clicked through a cluster once. Doing everything through the API on a
        genuinely untouched account exposes it:

            CreateCluster -> InvalidParameterException:
              Unable to assume the service linked role.

        Observed on account 908877262866 on 2026-07-31. This is precisely the
        gap that made setup-infrastructure.yml's claim of working on "a
        completely fresh AWS account" untrue - it never created this role, so
        its very first ECS call would have failed the same way.

        CreateServiceLinkedRole reports an existing role as InvalidInput
        rather than EntityAlreadyExists, so both are treated as success.
        """
        client = self._aws.client("iam")
        try:
            client.create_service_linked_role(AWSServiceName="ecs.amazonaws.com")
            self._log.info("ECS service-linked role created: AWSServiceRoleForECS")
            # Newly created roles are not immediately assumable.
            time.sleep(10)
        except (
            client.exceptions.InvalidInputException,
            client.exceptions.EntityAlreadyExistsException,
        ):
            self._log.info("ECS service-linked role already present")

    def ensure_cluster(self) -> str:
        """CreateCluster is idempotent - it returns the existing cluster."""
        client = self._aws.client("ecs")
        response = client.create_cluster(
            clusterName=self._config.cluster_name,
            capacityProviders=["FARGATE", "FARGATE_SPOT"],
            tags=self._config.tag_list(),
        )
        arn = response["cluster"]["clusterArn"]
        self._log.info(
            "cluster ready: %s (status=%s)",
            self._config.cluster_name,
            response["cluster"]["status"],
        )
        return arn

    def delete_cluster(self) -> None:
        client = self._aws.client("ecs")
        try:
            client.delete_cluster(cluster=self._config.cluster_name)
            self._log.info("cluster deleted: %s", self._config.cluster_name)
        except ClientError as exc:
            self._log.warning(
                "cluster not deleted: %s", exc.response["Error"]["Message"]
            )

    # -- orchestration ------------------------------------------------------

    def ensure_all(self) -> ProvisionedResources:
        """Bring every prerequisite into existence, in dependency order."""
        self._log.info("provisioning into account %s", self._aws.account_id)
        repos = self.ensure_ecr_repositories()
        self.ensure_log_group()
        execution_role_arn = self.ensure_execution_role()
        task_role_arn = self.ensure_task_role()
        network = self.discover_network()
        security_group_id = self.ensure_security_group(network["vpc_id"])
        self.ensure_service_linked_role()
        cluster_arn = self.ensure_cluster()
        return ProvisionedResources(
            execution_role_arn=execution_role_arn,
            task_role_arn=task_role_arn,
            security_group_id=security_group_id,
            subnet_ids=network["subnet_ids"],
            cluster_arn=cluster_arn,
            backend_repo_uri=repos[self._config.backend_repo],
            frontend_repo_uri=repos[self._config.frontend_repo],
        )

    def delete_all(self) -> None:
        """Remove everything this module creates.

        Order is the reverse of creation, and every step tolerates absence, so
        a partially built stack can still be torn down completely.
        """
        self.delete_cluster()
        self.delete_security_group()
        self.delete_roles()
        self.delete_log_group()
        self.delete_ecr_repositories()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from deploy_aws.config import DeployConfig

    # Read-only verification: discover the network without creating anything.
    provisioner = Provisioner(AwsSession(DeployConfig.from_env()))
    network = provisioner.discover_network()
    logger.info("discovered %d usable subnets: %s", len(network["subnet_ids"]), network["subnet_ids"])
