### Trying to figure out docker-ECS aws fargate setup next:

- AWS ECR authentication using aws ecr get-login-password
- Docker build command: docker build -t finsights-frontend .
- Docker tag command: docker tag finsights-frontend:latest 729472661729.dkr.ecr.us-east-1.amazonaws.com/finsights-frontend:latest
- Docker push command: docker push 729472661729.dkr.ecr.us-east-1.amazonaws.com/finsights-frontend:latest

```
ECS Cluster (logical grouping)
    └── ECS Service (maintains desired task count)
        └── Task (running instance of Task Definition)
            └── Task Definition (blueprint - CPU, memory, container images, networking)
                └── Container(s) (Docker images from ECR)
```

1. Network Mode: MUST be awsvpc (each task gets its own ENI)
2. CPU/Memory: Must use valid Fargate combinations (e.g., 512 CPU / 1024 MB)
3. IAM Roles:
    - Task Execution Role - Allows ECS to pull images, write logs
    - Task Role (optional) - Allows your containers to call AWS APIs
4. Infrastructure: VPC, subnets, security groups
5. ECR Images: Your containers must be in ECR (not Docker Hub for private workloads)


### Needed files:
1. ECR repository for backend (or is it already created?)
2. Task Definition JSON files (one for backend, one for frontend, or combined)
3. ECS Cluster
4. VPC/Subnet/Security Group configuration
5. IAM roles (ecsTaskExecutionRole, task role)
6. ECS Service definitions
7. Load balancer (ALB) if frontend needs public access

---

**Phase 1: Image Preparation**
   - Build your Docker images locally (you've done this)
   - Authenticate to ECR (the command in your screenshot)
   - Tag images with ECR URI
   - Push to ECR repositories

**Phase 2: Infrastructure Setup**
   - Create/verify VPC, subnets (public for frontend, private for backend)
   - Create security groups (allow frontend → backend communication)
   - Create IAM roles (task execution, task roles)
   - Create ECS Cluster

**Phase 3: Task Definitions**
   - Write Task Definition JSON (specifies CPU, memory, container config)
   - Register Task Definition with ECS
   - Define container port mappings, environment variables

**Phase 4: Service Deployment**
   - Create ECS Service from Task Definition
   - Configure desired task count (e.g., 1 for demo)
   - Set up load balancer (if needed for public access)
   - Configure service discovery (if backend ↔ frontend communication needed)

---

**2 Container Plan**:
- Backend (512 CPU / 1024 MB): $0.02128/hour = ~$15/month
- Frontend (256 CPU / 512 MB): $0.01064/hour = ~$8/month

