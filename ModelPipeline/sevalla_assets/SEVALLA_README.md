## Sevalla Architecture & Technical Internals

### What IS Sevalla? (Product Positioning)
Founded as managed WordPress hosting provider / Kinsta. Built on Google Cloud Platform (GCP) + Cloudflare. 120,000+ WordPress customers. Sevalla (Spinoff - 2023-2024), Replicate WordPress success in general PaaS market.

### Core Architecture: GKE + Cloudflare
```
┌─────────────────────────────────────────────────────────────────┐
│ USER REQUEST                                                    │
│ https://your-app.sevalla.app                                    │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ CLOUDFLARE GLOBAL NETWORK (260+ PoPs)                          │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Layer 1: Edge Functions & DDoS Protection                   │ │
│ │ - DNS Resolution                                             │ │
│ │ - SSL/TLS Termination                                        │ │
│ │ - WAF (Web Application Firewall)                             │ │
│ │ - DDoS Mitigation                                            │ │
│ └─────────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Layer 2: CDN & Static Asset Delivery                        │ │
│ │ - Cache static content (images, CSS, JS)                    │ │
│ │ - Serve from nearest PoP                                     │ │
│ │ - Zero egress fees for cached content                       │ │
│ └─────────────────────────────────────────────────────────────┘ │
└────────────────────┬────────────────────────────────────────────┘
                     │ (Dynamic requests pass through)
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│ GOOGLE CLOUD PLATFORM (25 Regions)                             │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ KUBERNETES ENGINE (GKE) - Managed by Sevalla                │ │
│ │                                                              │ │
│ │  ┌──────────────────────────────────────────────────────┐  │ │
│ │  │ Node Pool: User Applications                          │  │ │
│ │  │ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│  │ │
│ │  │ │ Pod (Your    │  │ Pod (Another │  │ Pod (Another ││  │ │
│ │  │ │ Backend)     │  │ User's App)  │  │ User's App)  ││  │ │
│ │  │ │              │  │              │  │              ││  │ │
│ │  │ │ Container:   │  │ Container:   │  │ Container:   ││  │ │
│ │  │ │ Python 3.11  │  │ Node.js 20   │  │ Go 1.21      ││  │ │
│ │  │ │ FastAPI      │  │ Express      │  │ Chi Framework││  │ │
│ │  │ │ Your code    │  │              │  │              ││  │ │
│ │  │ └──────────────┘  └──────────────┘  └──────────────┘│  │ │
│ │  │                                                        │  │ │
│ │  │ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│  │ │
│ │  │ │ Pod (Your    │  │ Pod          │  │ Pod          ││  │ │
│ │  │ │ Frontend)    │  │              │  │              ││  │ │
│ │  │ │              │  │              │  │              ││  │ │
│ │  │ │ Container:   │  │              │  │              ││  │ │
│ │  │ │ Streamlit    │  │              │  │              ││  │ │
│ │  │ └──────────────┘  └──────────────┘  └──────────────┘│  │ │
│ │  └──────────────────────────────────────────────────────┘  │ │
│ │                                                              │ │
│ │  ┌──────────────────────────────────────────────────────┐  │ │
│ │  │ Node Pool: Managed Databases                          │  │ │
│ │  │ ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│  │ │
│ │  │ │ PostgreSQL   │  │ MySQL        │  │ Redis        ││  │ │
│ │  │ │ Pod          │  │ Pod          │  │ Pod          ││  │ │
│ │  │ └──────────────┘  └──────────────┘  └──────────────┘│  │ │
│ │  └──────────────────────────────────────────────────────┘  │ │
│ │                                                              │ │
│ └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│ ┌─────────────────────────────────────────────────────────────┐ │
│ │ Additional GCP Services (Used by Sevalla internally)        │ │
│ │ - Cloud Build: Container image building                     │ │
│ │ - Container Registry: Image storage                         │ │
│ │ - Cloud Load Balancers: L4/L7 load balancing               │ │
│ │ - Persistent Disks: Storage for databases/volumes           │ │
│ │ - Cloud Storage: S3-compatible object storage               │ │
│ └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

1. GKE as choice, they evaluated LXD Linux Containers, AWS ECS, Heroku, Firecracker, HashiCorp Nomad. 
2. GKE (Managed Kubernetes) -> Kubernetes Features Critical for PaaS:
   1. Pod scheduling - Automatic workload placement
   2. Service discovery - DNS-based internal networking
   3. Rolling updates - Zero-downtime deployments
   4. Resource quotas - Multi-tenant isolation
   5. Horizontal autoscaling - Automatic pod replication
3. GKE-Specific Advantages:
   1. Managed control plane - Google handles master nodes
   2. Auto-upgrades - K8s versions updated automatically
   3. Integrated monitoring - Cloud Logging/Monitoring built-in
   4. 25 global regions - Low-latency deployment options
4. **Edge Layer**: Cloudflare provides:
   1. Global Edge Network (260+ PoPs), DDoS Protection, SSL/TLS Termination, Static Asset Caching.

---

### Build System (How Code Becomes Containers)

The Three Build Strategies:
- Strategy 1: Nixpacks (Default, Recommended) - Generates equivalent Dockerfile from project structure
- Strategy 2: Buildpacks (Legacy, Heroku-Compatible) - Heroku's original build system, CNCF standard, slower/heavier than Nixpacks. Nixpacks: Smaller images, faster builds, more languages.
- Strategy 3: Dockerfile (Maximum Control) - Write Dockerfile manually. Complex ML dependencies (CUDA, custom C++ libs).


### What **actually happens** when we click "Deploy":

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: SOURCE CODE FETCH (5-10 seconds)                       │
├─────────────────────────────────────────────────────────────────┤
│ Sevalla webhook receives GitHub push event                     │
│ Clones your repo (or pulls latest commit)                      │
│ Validates branch matches config                                │
│ Checkouts specific commit SHA                                  │
└─────────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: BUILD ENVIRONMENT SETUP (10-30 seconds)                │
├─────────────────────────────────────────────────────────────────┤
│ Sevalla spins up GCP Cloud Build VM                            │
│ Mounts your repo into build workspace                          │
│ Injects environment variables (AWS keys, etc.)                 │
│ Selects build strategy (Nixpacks/Buildpacks/Dockerfile)        │
└─────────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: DEPENDENCY INSTALLATION (2-10 minutes)                 │
├─────────────────────────────────────────────────────────────────┤
│ For Nixpacks/Python:                                            │
│   1. Detect Python version (requirements.txt or env var)       │
│   2. Download base image (python:3.11-slim)                    │
│   3. Run: pip install -r requirements.txt                      │
│      └─ Downloads: polars, boto3, fastapi, uvicorn, etc.       │
│      └─ For FinRAG: ~500MB of packages                    │
│   4. Cache dependencies for future builds                      │
│                                                                 │
│ Build Time Estimate for FinRAG:                                │
│   - First build: 8-12 minutes (no cache)                       │
│   - Subsequent: 2-4 minutes (cached layers)                    │
└─────────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: DOCKER IMAGE CREATION (1-2 minutes)                    │
├─────────────────────────────────────────────────────────────────┤
│ Nixpacks generates final Dockerfile layers                     │
│ Copies your application code into image                        │
│ Sets ENTRYPOINT (your start command)                           │
│ Builds multi-layer Docker image                                │
│                                                                 │
│ Image Layers (example):                                        │
│   Layer 1: Base Python image (150MB)                           │
│   Layer 2: System dependencies (50MB)                          │
│   Layer 3: Python packages (300MB)                             │
│   Layer 4: Your code (5MB)                                     │
│   Total: ~505MB                                                │
└─────────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: IMAGE PUSH TO REGISTRY (30-60 seconds)                 │
├─────────────────────────────────────────────────────────────────┤
│ Pushes to GCP Container Registry                               │
│ Only uploads changed layers (cached layers skipped)            │
│ Tags image with deployment ID                                  │
└─────────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: KUBERNETES ROLLOUT (30-90 seconds)                     │
├─────────────────────────────────────────────────────────────────┤
│ K8s creates new pod with your image                            │
│ Pulls image from registry into pod                             │
│ Runs health checks on new pod                                  │
│   └─ Hits http://your-backend:8000/health every 10s            │
│   └─ Must succeed 3 times consecutively                        │
│                                                                 │
│ Once healthy:                                                   │
│   1. Routes traffic to new pod                                 │
│   2. Keeps old pod running (zero downtime!)                    │
│   3. Waits 30 seconds                                          │
│   4. Terminates old pod                                        │
└─────────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│ STEP 7: SERVICE READY (TOTAL: 10-15 minutes first deploy)      │
├─────────────────────────────────────────────────────────────────┤
│ Public URL is live: https://your-app.sevalla.app              │
│ DNS updated (if needed)                                         │
│ Cloudflare routes traffic to GKE load balancer                │
│ Load balancer routes to your pod                               │
└─────────────────────────────────────────────────────────────────┘
```


### Runtime Architecture:
```
┌───────────────────────────────────────────────────────────────┐
│ KUBERNETES POD: finrag-backend-7f8d9c-abc123                  │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ CONTAINER: backend                                       │ │
│  ├─────────────────────────────────────────────────────────┤ │
│  │ Image: gcr.io/sevalla-prod/user123/finrag:v42           │ │
│  │ Internal IP: 10.244.1.5                                  │ │
│  │ Ports: 8000/TCP (exposed internally)                    │ │
│  │                                                          │ │
│  │ ┌─────────────────────────────────────────────────────┐ │ │
│  │ │ PROCESS TREE                                         │ │ │
│  │ ├─────────────────────────────────────────────────────┤ │ │
│  │ │ PID 1: /bin/sh (init)                                │ │ │
│  │ │  └─ PID 7: uvicorn                                   │ │ │
│  │ │      └─ Worker threads (handling requests)           │ │ │
│  │ └─────────────────────────────────────────────────────┘ │ │
│  │                                                          │ │
│  │ ┌─────────────────────────────────────────────────────┐ │ │
│  │ │ RESOURCE LIMITS (enforced by K8s)                   │ │ │
│  │ ├─────────────────────────────────────────────────────┤ │ │
│  │ │ CPU: 1.0 core (throttled if exceeded)               │ │ │
│  │ │ Memory: 2048MB (killed if exceeded)                 │ │ │
│  │ │ Storage: Ephemeral (lost on restart!)               │ │ │
│  │ └─────────────────────────────────────────────────────┘ │ │
│  │                                                          │ │
│  │ ┌─────────────────────────────────────────────────────┐ │ │
│  │ │ ENVIRONMENT VARIABLES (injected by Sevalla)         │ │ │
│  │ ├─────────────────────────────────────────────────────┤ │ │
│  │ │ AWS_ACCESS_KEY_ID=AKIAXXXXXXX                       │ │ │
│  │ │ AWS_SECRET_ACCESS_KEY=xxxxxxxx                      │ │ │
│  │ │ AWS_DEFAULT_REGION=us-east-1                        │ │ │
│  │ │ PORT=8000 (auto-injected)                           │ │ │
│  │ └─────────────────────────────────────────────────────┘ │ │
│  │                                                          │ │
│  │ ┌─────────────────────────────────────────────────────┐ │ │
│  │ │ FILESYSTEM                                           │ │ │
│  │ ├─────────────────────────────────────────────────────┤ │ │
│  │ │ /app/ (your code)                                    │ │ │
│  │ │ /tmp/ (writable, ephemeral)                         │ │ │
│  │ │ /home/user/.cache/ (ephemeral!)                     │ │ │
│  │ │                                                      │ │ │
│  │ │ NOTE: No persistent /home! S3-only strategy works.  │ │ │
│  │ └─────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```


### **Pod Sizes**
Sevalla offers **granular resource selection**:

| Tier | CPU | RAM | Price/Month* | Use Case |
|------|-----|-----|-------------|---------------|
| **Nano** | 0.1 | 256MB | $2 | Lightweight APIs |
| **Micro** | 0.25 | 512MB | $5 | **Frontend (Streamlit)** | -- ( Potential choice )
| **Small** | 0.5 | 1GB | $10 | Medium APIs |
| **Medium** | 1.0 | 2GB | $20 | **Backend (FastAPI + Polars)** | -- ( Potential choice )
| **Large** | 2.0 | 4GB | $40 | Heavy ML workloads |
| **XL** | 4.0 | 8GB | $80 | Data processing |



**Think of Sevalla as:**
```
Sevalla = Kubernetes-as-a-Service + Smart Defaults

What we write:
  - Python code
  - requirements.txt
  - Simple YAML config

What Sevalla gives us:
  - Container orchestration (K8s)
  - Auto-scaling (if needed)
  - Load balancing (automatic)
  - SSL certificates (free)
  - Zero-downtime deploys (built-in)
  - Monitoring (dashboard)
  - Global CDN (Cloudflare)

