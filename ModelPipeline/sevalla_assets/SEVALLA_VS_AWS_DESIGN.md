## Sevalla vs AWS: Solution Architecture Justification

### Developer's retrospection notes and insight notes.
### (Author/Experience: Joel Markapudi. FinSights, MLOps course)
1. Executive Summary: Why Sevalla for FinRAG
2. Decision: Deploy to Sevalla (GKE + Cloudflare PaaS)
3. Alternatives Evaluated: AWS Lambda, AWS ECS Fargate, AWS EC2, Docker Compose on EC2, Railway, Render
4. Evaluation Criteria: Deployment complexity, time-to-production, cost efficiency, operational overhead, learning time
5. Outcome: Sevalla provides 95% complexity reduction with comparable costs for academic use case

---

- To start off, I personally have already spent good amount of time, like roughly 6 days of day and night overnight coding, 90+ hours but couldnt get it right to config lambda perfectly on this project. Refer to my AWS Lambda attempts here: `ModelPipeline\lambda_assets`. This could definitely be cloud computing learning issues and lack of perfect experience or corporate experience for large scale heavy ML projects when using Lambda or when trying to use any other AWS items such as ECS or ECR. 
- Particularly, I was able to test complete refactors of streaming models and lambda mocking with environment variables and also some SAM-based CLI commands, but I just couldn't get SAM-build to completely happen locally or the SAM-deploy with guide to happen accurately.
- Later I realized that AWS Lambda's architecture fit itself was not truly correct for my project use case or design use case. Maybe on AWS stack, AWS ECS Fargate or AWS EC2 were the right fits or correct fits.
- Instead of forcing individual function refactor and API gateway communication architecture, I realized that our core project was a persistent web app with long running fast API backend and stateful instance of Streamlit frontend.
- Communication was with HTTP REST.
- There's also the specific lambda zip limits or package size limits, the execution times, the ephemeral storage concerns present in the lambda's internal directory. Concerns in this area.

---

- Sevalla (40x cheaper for low-volume academic use)
- The reason Sevalla is cheaper is that it offers this perfect ability to host back-end runtime and front-end runtime, to have two specific deploys, and to also have options for pod termination, pod suspension, automatic hibernation, or the abilities to simply pause and not incur costs.
- At 100K queries/month, Lambda becomes cheaper (~$800 vs $25 with hibernation). **However, not relevant for our case now.**


- Here is a setup complexity that I observed in ECS Fargate.
Setup Complexity:
```
  - Create ECR repository (container registry)
  - Build Docker images locally - Compose, network-volume mounts.
  - Push images to ECR
  - Create ECS cluster
  - Define task definitions (backend + frontend)
  - Configure service discovery (Cloud Map)
  - Set up Application Load Balancer
  - Configure target groups
  - Set up CloudWatch logging
  - IAM roles for task execution
  - VPC/subnet configuration
  - Security groups
```

### **ECS vs Sevalla Comparison:**

| Aspect | ECS Fargate | Sevalla |
|--------|-------------|---------|
| **Container Registry** | ECR (manual push) | Built-in (auto-build) |
| **Image Building** | Local Docker build | Nixpacks (auto) |
| **Load Balancing** | ALB setup required | Automatic |
| **SSL Certificates** | ACM + manual config | Automatic (Let's Encrypt) |
| **Service Discovery** | Cloud Map setup | K8s DNS (automatic) |
| **Logging** | CloudWatch config | Built-in dashboard |
| **Auto-Scaling** | Manual policies | UI slider |
| **Deployment** | CLI commands | Git push or UI click |

### **Cost Comparison (Always-On):**
```
ECS Fargate:
  Backend (0.5 vCPU, 2GB): $36/month
  Frontend (0.25 vCPU, 0.5GB): $18/month
  ALB: $16/month
  Data Transfer: $5/month
  ────────────────────────────────────
  Total: $75/month

Sevalla (Always-On):
  Backend (1 CPU, 2GB): $20/month
  Frontend (0.5 CPU, 512MB): $5/month
  Load Balancer: Included
  SSL/CDN: Included
  ────────────────────────────────────
  Total: $25/month
```

### **Cost Analysis (t3.medium: 2 vCPU, 4GB RAM):**
```
EC2 Costs:
  Instance: $30/month (on-demand)
  EBS storage: $8/month (80GB)
  Elastic IP: $3.60/month
  Data transfer: $5/month
  ────────────────────────────────────
  Total: $46.60/month
  
Plus:
  Your time: 4-6 hours/month maintenance
  Risk: Server crashes, no auto-recovery
```

**Verdict:** Cheapest compute, but highest operational overhead. Not worth it for academic project.
**Verdict:** ECS gives more control, but 3x more expensive and 8-9x more complex??


### "DIY Kubernetes" Approach or Docker-Compose manual ON EC2:
```
  - Docker Compose orchestration
  - Nginx reverse proxy
  - Let's Encrypt SSL automation
  - Health check scripts
  - Auto-restart on failure
  - Log aggregation
  - Monitoring dashboard
```

### More overview:
FinRAG is a persistent web application with:
  - Long-running FastAPI backend (event loop architecture)
  - Stateful Streamlit frontend (session-based UI)
  - HTTP-based microservices communication
  - S3-external data layer (no local state)

- Sevalla's GKE foundation natively supports: Multi-service deployments (backend + frontend), Internal networking (K8s service discovery), External data access, Persistent containers instead of ephemeral functions or step functions.
- Sevalla shockingly provides proper container orchestration, container lifecycle management, Service mesh networking (K8s DNS), load balancing, SSL automation, health checks and automatic recovery, hibernations, auto restarts, suspensions, logging, monitoring, CI/CD workflows (Git-based deploy), proper pod architectures - all built-in. all managed.

```
Sevalla Cost (with hibernation):
  Backend: 33h × $0.027/h = $0.89
  Frontend: 33h × $0.007/h = $0.23
  Builds: 5 deploys × $0.04 = $0.20
  Total: $1.32 (97% under budget)
```


### GKE + Cloudflare Synergy: Infrastructure Stack Benefits:

GOOGLE KUBERNETES ENGINE:
  - Enterprise-grade orchestration (Fortune 500 companies use)
  - 25 global regions (low-latency deployment)
  - Managed control plane (Google handles master nodes)
  - Auto-healing (pod crashes → automatic restart)
  - Resource quotas (multi-tenant isolation)  
CLOUDFLARE EDGE:
  - 260+ Points of Presence (global CDN)
  - DDoS mitigation (Layer 3/4/7 protection)
  - Free SSL/TLS (automatic renewal)
  - Static asset caching (Streamlit CSS/JS at edge)
  - Zero bandwidth cost for cached content

COMBINED ADVANTAGE:
```
  User Request → Cloudflare (1-5ms routing)
               → GKE Pod (150-200ms processing)
               → AWS Bedrock (200-300ms LLM)
  
  Total latency: ~350-500ms
  vs Direct AWS: ~400-600ms (no edge caching)
  
  Improvement: 15-20% faster for end users
```



