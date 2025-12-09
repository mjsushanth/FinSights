# Complete Infrastructure Setup Guide

## Overview

This guide shows you how to deploy FinSights to a **completely fresh AWS account** using GitHub Actions workflows. Everything is automated via Infrastructure-as-Code.

## Prerequisites

1. **AWS Account** (can be brand new, no manual setup required)
2. **GitHub Repository** with this code
3. **AWS Credentials** with admin permissions

## Step-by-Step Setup

### Step 1: Add AWS Credentials to GitHub

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Add these secrets:

| Secret Name | Value | Description |
|------------|-------|-------------|
| `AWS_ACCESS_KEY_ID` | Your AWS access key | From AWS IAM user |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key | From AWS IAM user |

**Creating AWS IAM User:**
```bash
# Create user
aws iam create-user --user-name github-actions-deployer

# Attach admin policy (or create custom policy with minimal permissions)
aws iam attach-user-policy \
  --user-name github-actions-deployer \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess

# Create access key
aws iam create-access-key --user-name github-actions-deployer
```

### Step 2: Run Infrastructure Setup Workflow

This creates **ALL** AWS resources from scratch.

1. Go to **Actions** tab in GitHub
2. Select **"Setup AWS Infrastructure (Fresh AWS Account)"**
3. Click **"Run workflow"**
4. Choose options:
   - **Environment**: `production` (or `staging`/`dev`)
   - **VPC ID**: Leave empty to use default VPC
   - **Force recreate**: `false` (unless you want to rebuild everything)
5. Click **"Run workflow"**

**What this creates:**

✅ **IAM Roles:**
- `ecsTaskExecutionRole` - For pulling Docker images and writing logs
- `aws_ecs_task_rules` - For Bedrock API + S3 access (attached to tasks)

✅ **Security Group:**
- `finsights-backend-sg` - Allows inbound on port 8000, all outbound

✅ **ECR Repositories:**
- `finsights-backend` - Backend Docker images
- `finsights-frontend` - Frontend Docker images

✅ **ECS Cluster:**
- `finsights-cluster` - Fargate cluster for running containers

✅ **Service Discovery (AWS Cloud Map):**
- Namespace: `finsights.local`
- Service: `backend` → DNS: `backend.finsights.local:8000`

**Monitoring the workflow:**
- Watch the Actions tab for progress
- Download the `infrastructure-config-production` artifact when complete
- This contains all resource IDs for reference

### Step 3: Update Deploy Workflow (Optional)

The setup workflow outputs all resource IDs. You can update `deploy-ecs.yml` to use these automatically, or manually update the environment variables:

```yaml
env:
  # Update these if needed (though setup uses same names)
  SECURITY_GROUP: sg-xxxxx  # From infrastructure-config.json
  SERVICE_DISCOVERY_NAMESPACE_ID: ns-xxxxx
  SERVICE_DISCOVERY_SERVICE_ID: srv-xxxxx
```

### Step 4: Deploy Your Application

Now that infrastructure is ready, deploy your app:

1. Go to **Actions** tab
2. Select **"Deploy to ECS with Service Discovery"**
3. Click **"Run workflow"**
4. The workflow will:
   - Build Docker images from source
   - Push to ECR
   - Create task definitions
   - Deploy services
   - Configure service discovery

### Step 5: Access Your Application

After deployment completes:

1. Check the workflow output for the **frontend public IP**
2. Access frontend at: `http://<public-ip>:8501`
3. Backend is accessible internally at: `http://backend.finsights.local:8000`

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    GitHub Actions                        │
│  ┌──────────────────┐      ┌───────────────────┐       │
│  │ setup-            │      │ deploy-ecs.yml    │       │
│  │ infrastructure.yml│ ───▶ │ (Build & Deploy)  │       │
│  └──────────────────┘      └───────────────────┘       │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                         AWS                              │
│                                                          │
│  ┌─────────────┐                                        │
│  │   ECR       │  (Docker Images)                       │
│  └─────────────┘                                        │
│         │                                                │
│         ▼                                                │
│  ┌─────────────────────────────────────────────┐       │
│  │          ECS Cluster (Fargate)              │       │
│  │                                              │       │
│  │  ┌──────────────┐    ┌─────────────────┐   │       │
│  │  │   Backend    │◀───│  Service Disc.  │   │       │
│  │  │   Service    │    │  (Cloud Map)    │   │       │
│  │  │              │    │                 │   │       │
│  │  │ Port: 8000   │    │ DNS: backend.   │   │       │
│  │  └──────────────┘    │ finsights.local │   │       │
│  │         ▲             └─────────────────┘   │       │
│  │         │                                    │       │
│  │  ┌──────────────┐                           │       │
│  │  │  Frontend    │                           │       │
│  │  │  Service     │                           │       │
│  │  │              │                           │       │
│  │  │ Port: 8501   │  (Public IP)             │       │
│  │  └──────────────┘                           │       │
│  └─────────────────────────────────────────────┘       │
│                                                          │
│  ┌─────────────┐                                        │
│  │ Bedrock API │  (Claude for LLM)                     │
│  └─────────────┘                                        │
│                                                          │
│  ┌─────────────┐                                        │
│  │     S3      │  (Data storage)                       │
│  └─────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

## Resource Details

### IAM Roles Created

#### 1. ecsTaskExecutionRole
**Trust Policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ecs-tasks.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
```

**Managed Policy Attached:**
- `arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy`

**Purpose:** Allows ECS to pull Docker images from ECR and write logs to CloudWatch

#### 2. aws_ecs_task_rules
**Trust Policy:** Same as above

**Managed Policies Attached:**
- `arn:aws:iam::aws:policy/AmazonBedrockFullAccess`
- `arn:aws:iam::aws:policy/AmazonS3FullAccess`

**Purpose:** Grants running containers access to Bedrock (for Claude API) and S3 (for data)

### Security Group Rules

**Name:** `finsights-backend-sg`

**Inbound Rules:**
| Type | Protocol | Port | Source | Description |
|------|----------|------|--------|-------------|
| Custom TCP | TCP | 8000 | 0.0.0.0/0 | Backend API access |

**Outbound Rules:**
| Type | Protocol | Port | Destination | Description |
|------|----------|------|-------------|-------------|
| All traffic | All | All | 0.0.0.0/0 | Allow all outbound |

### Service Discovery

**Namespace:** `finsights.local` (private DNS)
**Service:** `backend`
**Full DNS:** `backend.finsights.local:8000`

**How it works:**
- Backend tasks automatically register when they start
- Frontend connects via DNS name (never needs IP updates)
- AWS Cloud Map updates DNS when tasks are replaced

## Cleaning Up

To **delete everything** (warning: irreversible):

```bash
# Delete ECS services
aws ecs update-service --cluster finsights-cluster --service finsights-backend --desired-count 0
aws ecs update-service --cluster finsights-cluster --service finsights-frontend --desired-count 0
aws ecs delete-service --cluster finsights-cluster --service finsights-backend --force
aws ecs delete-service --cluster finsights-cluster --service finsights-frontend --force

# Delete ECS cluster
aws ecs delete-cluster --cluster finsights-cluster

# Delete ECR repositories
aws ecr delete-repository --repository-name finsights-backend --force
aws ecr delete-repository --repository-name finsights-frontend --force

# Delete service discovery
NAMESPACE_ID=$(aws servicediscovery list-namespaces --query "Namespaces[?Name=='finsights.local'].Id" --output text)
SERVICE_ID=$(aws servicediscovery list-services --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" --query "Services[?Name=='backend'].Id" --output text)
aws servicediscovery delete-service --id $SERVICE_ID
aws servicediscovery delete-namespace --id $NAMESPACE_ID

# Delete security group
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=finsights-backend-sg" --query "SecurityGroups[0].GroupId" --output text)
aws ec2 delete-security-group --group-id $SG_ID

# Delete IAM roles
aws iam detach-role-policy --role-name aws_ecs_task_rules --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
aws iam detach-role-policy --role-name aws_ecs_task_rules --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam delete-role --role-name aws_ecs_task_rules

aws iam detach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
aws iam delete-role --role-name ecsTaskExecutionRole
```

## Troubleshooting

### Issue: "Role already exists" error
**Solution:** This is expected if you've run the workflow before. The workflow is **idempotent** and will reuse existing resources.

### Issue: "VPC not found"
**Solution:** Specify a VPC ID manually in the workflow inputs, or create a default VPC:
```bash
aws ec2 create-default-vpc
```

### Issue: "Insufficient permissions"
**Solution:** Ensure your GitHub Actions AWS credentials have these permissions:
- `iam:*`
- `ecs:*`
- `ecr:*`
- `ec2:*`
- `servicediscovery:*`

### Issue: "Docker build fails in Actions"
**Solution:** Check the Dockerfile paths in `deploy-ecs.yml` match your repository structure.

## Cost Estimates

**Monthly costs (1 backend + 1 frontend, 24/7):**
- ECS Fargate: ~$50/month (0.25 vCPU, 0.5GB per task)
- ECR storage: ~$1/month (for Docker images)
- CloudWatch Logs: ~$5/month
- Service Discovery: Free
- **Total: ~$56/month**

**Per-query costs:**
- Bedrock (Claude): ~$0.01-0.02 per complex query
- S3 data transfer: Negligible

## Support

For issues, check:
1. GitHub Actions workflow logs
2. ECS task logs in CloudWatch
3. This guide's troubleshooting section
