"""
ECS service lifecycle for the FinSights task: register, scale, inspect, remove.

What this module does
---------------------
Registers a task definition revision, creates or updates the ECS service that
runs it, scales it up and down, reports where it is reachable, and deletes it.

The cost model this implements
-----------------------------
Fargate bills per *task*, per second, for the task-level cpu and memory
reservation - not per container and not for actual usage. Two consequences
shape every verb below.

  - Because billing is per task, putting two containers in one task is close
    to free. A second task would double the bill; a second container inside
    the same task costs nothing extra as long as the task shape is unchanged.

  - Because billing is per running task, desired-count zero costs nothing for
    compute. There is no stopped-container charge on Fargate, because there is
    no stopped container: the micro-VM is destroyed. `down` therefore reaches
    genuine zero compute spend while keeping the service, cluster, roles, log
    group and images in place, so `up` is a single API call away.

That leaves a small standing cost after `down` - ECR storage for the two
images, roughly $0.10/GB-month of compressed layers, plus whatever log data is
still inside its retention window. `destroy` exists for the case where even
that is unwanted: it removes the images and every other resource, and `up`
rebuilds the whole stack from the repository.

Inputs
------
An AwsSession, ProvisionedResources from the Provisioner.

Outputs
-------
Task definition ARNs, service state, the public URL of the frontend.

Usage
-----
    operator = ServiceOperator(aws)
    operator.deploy(resources)
    print(operator.public_url())

Author: Joel Markapudi
Date: 2026-07-31
"""

import logging
import time
from typing import Any, Dict, List, Optional

from botocore.exceptions import ClientError

from deploy_aws.aws_session import AwsSession
from deploy_aws.provisioner import ProvisionedResources
from deploy_aws.taskdef import TaskDefinitionBuilder

logger = logging.getLogger(__name__)


class ServiceOperator:
    """Owns the ECS service and task definition for FinSights."""

    def __init__(self, aws: AwsSession, log: Optional[logging.Logger] = None) -> None:
        self._aws = aws
        self._config = aws.config
        self._log = log or logger
        self._builder = TaskDefinitionBuilder(aws.config)

    # -- task definition ----------------------------------------------------

    def register_task_definition(self, resources: ProvisionedResources) -> str:
        """Register a new revision from the code in this repository.

        Note what is absent: any describe-then-patch step. The document is
        built from taskdef.py, so a fresh account with no prior revision works
        identically to an account with fifty.
        """
        document = self._builder.build(
            account_id=self._aws.account_id,
            execution_role_arn=resources.execution_role_arn,
            task_role_arn=resources.task_role_arn,
        )
        response = self._aws.client("ecs").register_task_definition(**document)
        arn = response["taskDefinition"]["taskDefinitionArn"]
        self._log.info(
            "task definition registered: %s (revision %d)",
            arn.split("/")[-1],
            response["taskDefinition"]["revision"],
        )
        return arn

    # -- service ------------------------------------------------------------

    def _describe_service(self) -> Optional[Dict[str, Any]]:
        response = self._aws.client("ecs").describe_services(
            cluster=self._config.cluster_name,
            services=[self._config.service_name],
        )
        for service in response.get("services", []):
            if service["status"] != "INACTIVE":
                return service
        return None

    def _network_configuration(self, resources: ProvisionedResources) -> Dict[str, Any]:
        return {
            "awsvpcConfiguration": {
                "subnets": resources.subnet_ids,
                "securityGroups": [resources.security_group_id],
                # Without a public IP the task has no return path to the
                # internet in a public subnet, and image pull itself fails -
                # a confusing symptom, because the task never starts and so
                # produces no application logs to explain why.
                "assignPublicIp": self._config.assign_public_ip,
            }
        }

    def deploy(self, resources: ProvisionedResources, desired_count: Optional[int] = None) -> str:
        """Create the service, or point the existing one at a new revision."""
        client = self._aws.client("ecs")
        task_definition_arn = self.register_task_definition(resources)
        count = self._config.desired_count if desired_count is None else desired_count
        existing = self._describe_service()

        if existing is None:
            client.create_service(
                cluster=self._config.cluster_name,
                serviceName=self._config.service_name,
                taskDefinition=task_definition_arn,
                desiredCount=count,
                launchType="FARGATE",
                networkConfiguration=self._network_configuration(resources),
                # One task, so there is nothing to roll between. Allowing the
                # old task to stop before the new one starts keeps the account
                # inside one task's worth of spend during a deploy.
                deploymentConfiguration={
                    "maximumPercent": 100,
                    "minimumHealthyPercent": 0,
                },
                enableExecuteCommand=False,
                tags=self._config.tag_list(),
                propagateTags="SERVICE",
            )
            self._log.info("service created: %s", self._config.service_name)
        else:
            client.update_service(
                cluster=self._config.cluster_name,
                service=self._config.service_name,
                taskDefinition=task_definition_arn,
                desiredCount=count,
                networkConfiguration=self._network_configuration(resources),
                forceNewDeployment=True,
            )
            self._log.info(
                "service updated to %s (desired=%d)",
                task_definition_arn.split("/")[-1],
                count,
            )
        return task_definition_arn

    def scale(self, desired_count: int) -> None:
        """Change the running task count. Zero means zero compute spend."""
        if self._describe_service() is None:
            raise RuntimeError(
                f"Service {self._config.service_name!r} does not exist. "
                f"Run 'up' first."
            )
        self._aws.client("ecs").update_service(
            cluster=self._config.cluster_name,
            service=self._config.service_name,
            desiredCount=desired_count,
        )
        self._log.info("desired count set to %d", desired_count)

    def wait_for_steady_state(self, timeout: int = 600) -> bool:
        """Poll until running count matches desired, or time out.

        The boto3 services_stable waiter is deliberately not used: it gives up
        after a fixed 40 attempts and, on failure, reports only that the
        service did not stabilise. Polling directly lets the reason be logged -
        which for a first deployment is almost always an image pull failure or
        a health check that never passes.
        """
        client = self._aws.client("ecs")
        deadline = time.time() + timeout
        last_state = ""
        while time.time() < deadline:
            service = self._describe_service()
            if service is None:
                raise RuntimeError("service disappeared while waiting")
            running = service["runningCount"]
            desired = service["desiredCount"]
            pending = service["pendingCount"]
            state = f"running={running} pending={pending} desired={desired}"
            if state != last_state:
                self._log.info("waiting: %s", state)
                last_state = state
            if running == desired and pending == 0:
                self._log.info("steady state reached: %s", state)
                return True
            # Surface the most recent failure reason rather than waiting mute.
            for event in service.get("events", [])[:1]:
                message = event.get("message", "")
                if any(word in message for word in ("unable", "failed", "error")):
                    self._log.warning("service event: %s", message)
            time.sleep(10)
        self._log.error("timed out after %ds waiting for steady state", timeout)
        return False

    def delete_service(self) -> None:
        """Scale to zero and remove the service definition."""
        client = self._aws.client("ecs")
        if self._describe_service() is None:
            self._log.info("service already absent: %s", self._config.service_name)
            return
        try:
            client.update_service(
                cluster=self._config.cluster_name,
                service=self._config.service_name,
                desiredCount=0,
            )
            client.delete_service(
                cluster=self._config.cluster_name,
                service=self._config.service_name,
                force=True,
            )
            self._log.info("service deleted: %s", self._config.service_name)
        except ClientError as exc:
            self._log.warning("service delete: %s", exc.response["Error"]["Message"])

    def deregister_task_definitions(self) -> int:
        """Deregister every revision of the family.

        Deregistered revisions are not billed and are eventually purged by
        AWS, but leaving them active means a later 'destroy' claims to have
        removed everything while the family is still listed in the console.
        """
        client = self._aws.client("ecs")
        removed = 0
        paginator = client.get_paginator("list_task_definitions")
        for page in paginator.paginate(familyPrefix=self._config.task_family, status="ACTIVE"):
            for arn in page["taskDefinitionArns"]:
                client.deregister_task_definition(taskDefinition=arn)
                removed += 1
        if removed:
            self._log.info("deregistered %d task definition revision(s)", removed)
        return removed

    # -- inspection ---------------------------------------------------------

    def _running_task_arns(self) -> List[str]:
        response = self._aws.client("ecs").list_tasks(
            cluster=self._config.cluster_name,
            serviceName=self._config.service_name,
            desiredStatus="RUNNING",
        )
        return response.get("taskArns", [])

    def public_ip(self) -> Optional[str]:
        """The public IP of the running task's elastic network interface.

        With awsvpc networking the task gets its own ENI. The IP changes every
        time the task is replaced, which is exactly the churn a load balancer
        or a service-discovery record would paper over. At one task and no
        load balancer, reading it on demand is the honest answer.
        """
        task_arns = self._running_task_arns()
        if not task_arns:
            return None
        tasks = self._aws.client("ecs").describe_tasks(
            cluster=self._config.cluster_name, tasks=task_arns
        )["tasks"]
        for task in tasks:
            for attachment in task.get("attachments", []):
                for detail in attachment.get("details", []):
                    if detail.get("name") != "networkInterfaceId":
                        continue
                    interfaces = self._aws.client("ec2").describe_network_interfaces(
                        NetworkInterfaceIds=[detail["value"]]
                    )["NetworkInterfaces"]
                    for interface in interfaces:
                        ip = interface.get("Association", {}).get("PublicIp")
                        if ip:
                            return str(ip)
        return None

    def public_url(self) -> Optional[str]:
        ip = self.public_ip()
        return f"http://{ip}:{self._config.frontend_port}" if ip else None

    def status(self) -> Dict[str, Any]:
        """A single readable snapshot of what is running and what it costs."""
        service = self._describe_service()
        if service is None:
            return {"exists": False, "running": 0, "desired": 0, "url": None}
        running = service["runningCount"]
        return {
            "exists": True,
            "status": service["status"],
            "running": running,
            "desired": service["desiredCount"],
            "pending": service["pendingCount"],
            "task_definition": service["taskDefinition"].split("/")[-1],
            "url": self.public_url() if running else None,
            "billing": "charged while running" if running else "zero compute spend",
            "last_event": (service.get("events") or [{}])[0].get("message", ""),
        }

    def container_health(self) -> List[Dict[str, str]]:
        """Per-container health as Fargate sees it.

        Useful because a task can be RUNNING while a container inside it is
        UNKNOWN - the signature of a health check that was defined only in the
        Dockerfile, which Fargate does not read.
        """
        task_arns = self._running_task_arns()
        if not task_arns:
            return []
        tasks = self._aws.client("ecs").describe_tasks(
            cluster=self._config.cluster_name, tasks=task_arns
        )["tasks"]
        return [
            {
                "name": container.get("name", "?"),
                "lastStatus": container.get("lastStatus", "?"),
                "healthStatus": container.get("healthStatus", "UNKNOWN"),
            }
            for task in tasks
            for container in task.get("containers", [])
        ]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    from deploy_aws.config import DeployConfig

    # Read-only verification: report current state, create nothing.
    operator = ServiceOperator(AwsSession(DeployConfig.from_env()))
    snapshot = operator.status()
    for key, value in snapshot.items():
        logger.info("%-16s %s", key, value)
