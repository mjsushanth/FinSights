### Sevalla Design:


### **SEVALLA CLOUD (What Actually Happens)**
```
┌───────────────────────────────────────────────────────────────────┐
│ SEVALLA KUBERNETES CLUSTER (Google Cloud)                        │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Pod: finrag-backend                                        │  │
│  │ ┌─────────────────────────────────────────────────────┐   │  │
│  │ │ Container: backend                                   │   │  │
│  │ │ Internal IP: 10.244.0.5                              │   │  │
│  │ │ Listening: 0.0.0.0:8000                              │   │  │
│  │ │                                                      │   │  │
│  │ │ Uvicorn running...                                   │   │  │
│  │ └─────────────────────────────────────────────────────┘   │  │
│  │                                                            │  │
│  │ Service DNS Name: "backend"                                │  │
│  │ Internal Endpoint: backend:8000                            │  │
│  └──────────────────────┬─────────────────────────────────────┘  │
│                         │ Internal K8s Network                   │
│                         │ (ClusterIP: 10.96.0.10:8000)          │
│  ┌──────────────────────┴─────────────────────────────────────┐  │
│  │ Pod: finrag-frontend                                        │  │
│  │ ┌─────────────────────────────────────────────────────┐   │  │
│  │ │ Container: frontend                                  │   │  │
│  │ │ Internal IP: 10.244.0.6                              │   │  │
│  │ │ Listening: 0.0.0.0:8501                              │   │  │
│  │ │                                                      │   │  │
│  │ │ Streamlit code:                                      │   │  │
│  │ │   BACKEND_URL = "http://backend:8000"  ←───────────┐│   │  │
│  │ │   requests.post(BACKEND_URL + "/query")            ││   │  │
│  │ └─────────────────────────────────────────────────────┘   │  │
│  │                                                            │  │
│  │ Exposed to Internet via Load Balancer                     │  │
│  │ Public URL: https://finrag-abc123.sevalla.app             │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
                                │
                                │ HTTPS (port 443)
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│ USER'S BROWSER                                                    │
│ Accesses: https://finrag-abc123.sevalla.app                      │
│ (Routed to frontend pod on port 8501)                            │
└───────────────────────────────────────────────────────────────────┘
```


1. Service Discovery (DNS)
LOCAL: localhost = 127.0.0.1 (your computer)
CLOUD (Sevalla): backend = Kubernetes Service DNS name, Resolves to internal IP (e.g., 10.96.0.10)
No internet routing - stays within cluster network

```python
# Streamlit code
BACKEND_URL = "http://localhost:8000"
# Streamlit code (ONE LINE CHANGE!)
BACKEND_URL = "http://backend:8000"
```

2. Port Binding
```python
# Backend
uvicorn ... --host 0.0.0.0 --port 8000
# Frontend
streamlit run ... --server.address 0.0.0.0 --server.port 8501
```
- LOCAL: "Listen on all network interfaces (localhost, WiFi, ethernet)"
- CLOUD: "Listen on container's network interface (accessible to other containers)"
- The ports (8000, 8501) are:
  - Internal - Used for communication between services
  - Mapped - Sevalla maps internal 8501 → public HTTPS (443)

**Sevalla Handles This Automatically**
```yaml
# sevalla.yml
services:
  backend:
    startCommand: uvicorn ... --port 8000
    # No public exposure needed
  
  frontend:
    startCommand: streamlit ... --port 8501
    envVars:
      - key: BACKEND_URL
        value: http://backend:8000  # ← Service discovery!
    # Sevalla exposes this publicly
```

- What Sevalla Creates Automatically: Internal Service Routing, External Access, Security.
- Backend has NO public access (internal only), Frontend publicly accessible via HTTPS.


### Predicting Code Changes:

1. Change 1: Frontend Environment Variable

File: serving/frontend/chat.py (or wherever BACKEND_URL is set)
```python
import os

# Works both locally and in cloud!
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
#                        ↑ Cloud value    ↑ Local default
```

2. Change 2: AWS Credentials

File: ModelPipeline/finrag_ml_tg1/loaders/ml_config_loader.py
```python
def _load_aws_credentials(self):
    env_path = self.model_root / ".aws_secrets" / "aws_credentials.env"
    
    if env_path.exists():
        load_dotenv(env_path)  # Local
    else:
        pass  # Cloud - boto3 reads from os.environ automatically
```

3. Hidden Aspects
- Build Process Location - Based issues, File System Differences (Ephemeral disk), Only /tmp and mounted volumes persist.
- Gotcha: Don't rely on local file caching in cloud. S3-first architecture already handles this (Atleast, 99% OF IT. ???)

LOCAL: 16GB RAM, my goated gpu laptop.
CLOUD (Sevalla): 2GB RAM, 1 CPU (backend) + 512MB RAM, 0.5 CPU (frontend)
Hard limits - process killed if exceeded

4. Logging issues
- Use logger.debug() extensively, view logs in Sevalla dashboard.

5. Cold Starts?? This is a Lambda problem, NOT a Sevalla problem.
6. Look into - Health Checks & Auto-Restart. Sevalla hitting `http://backend:8000/health` every 30s or Ns. Restarting if need.
7. Environment Variable Injection Timing: Sevalla injects `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, etc. Available as `os.environ` when container starts. 
8. Network Latency: Study on this soon. (To be investigated.)


## How to enable manual-only deployments:

```
GitHub Workflow -- Dont want this rn.
┌─────────────────────────────────────────┐
│ You: git push origin main               │
│        ↓ (automatic webhook)            │
│ Sevalla: Detects push → Builds → $0.20 │
│        ↓                                │
│ Pod: Deploys → $20/month billing starts │
└─────────────────────────────────────────┘

Manual-Controlled Workflow:
┌─────────────────────────────────────────┐
│ You: git push origin main               │
│        ↓ (NO automatic action)          │
│ Sevalla: Does NOTHING                   │
│        ↓ (waits for manual trigger)     │
│ You: Click "Deploy now" in dashboard    │
│        ↓                                │
│ Sevalla: Builds → Deploys               │
└─────────────────────────────────────────┘
```

- Sevalla Dashboard → Application Settings → Source: Automatic deployment on commit. Disable this.

---

## Pay for RUNTIME HOURS, Not Deployments. Cost Model - Per-Second Billing (Not Per-Instantiation).

**Sevalla's billing formula:**
```
┌─────────────────────────────────────────────────────────┐
│ COST COMPONENT 1: BUILD TIME                            │
├─────────────────────────────────────────────────────────┤
│ Rate: $0.02/minute ($0.0003333/second)                  │
│                                                         │
│ FinRAG build time:                                      │
│   First build: 10 mins = $0.20                          │
│   Subsequent: 3 mins = $0.06                            │
│                                                         │
│ This is charged ONCE per deployment                     │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ COST COMPONENT 2: RUNTIME (POD HOURS)                   │
├─────────────────────────────────────────────────────────┤
│ Rate: Charged PER SECOND the pod is running             │
│                                                         │
│ Medium pod (2GB RAM, 1 CPU):                            │
│   $20/month = $0.027/hour = $0.0000076/second           │
│                                                         │
│ Micro pod (512MB RAM, 0.25 CPU):                        │
│   $5/month = $0.007/hour = $0.0000019/second            │
│                                                         │
│ CRITICAL: Charged every second pod exists!              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ COST COMPONENT 3: BANDWIDTH                             │
├─────────────────────────────────────────────────────────┤
│ Rate: $0.10/GB egress (negligible for your use case)    │
└─────────────────────────────────────────────────────────┘
```

**Deploy → Test 1 Hour → SUSPEND**
> "Suspending the application doesn't change or remove anything from it. **You will not incur any costs for the application during the suspension.**"

SUSPEND (Recommended for testing):                     
   - Stops all pods immediately                         
   - Billing stops instantly ($0/hour)                  
   - Configuration saved                                
   - Environment variables saved                        
   - Click "Activate" to resume                         
   - Resume time: ~30 seconds  