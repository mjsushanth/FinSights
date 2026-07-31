"""
deploy_aws - ECS Fargate deployment control plane for FinSights.

Owns every AWS resource required to serve the FinSights backend and frontend on
ECS Fargate, and owns the lifecycle verbs used to operate them: up, down,
status, destroy.

Why this package exists
-----------------------
The December 2025 deployment died because its task definitions existed only as
console state inside an AWS account that was later closed. Nothing in the
repository could recreate them. This package is the correction: every resource
is declared in code, created idempotently, and reproducible from a clean
account with a single command.

Author: Joel Markapudi
Date: 2026-07-31
"""
