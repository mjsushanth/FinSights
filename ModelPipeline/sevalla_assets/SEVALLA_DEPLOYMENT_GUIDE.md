# FinRAG Sevalla Deployment Guide

## Prerequisites
- [ ] Sevalla account created 
- [ ] GitHub repo pushed with latest code
- [ ] AWS credentials ready (Access Key ID + Secret)
- [ ] Code changes applied (see below)


## Sevalla Setup

### Step 1: Create Sevalla Account
1. Go to https://sevalla.com
2. Sign up with GitHub OAuth

### Step 2: Connect GitHub Repository
1. Sevalla Dashboard → "Add Service" → "Application"
2. Select "Git Repository"
3. Authorize Sevalla GitHub App
4. Select `ModelPipeline` repository
5. Branch: `main`
6. **UNCHECK** "Automatic deployment on commit"

### Step 3: Configure Backend Service
1. Name: `finrag-backend`
2. Region: Choose nearest to you (e.g., `us-east-1`)
3. Build Strategy: Nixpacks
4. Build Path: `.` (root)
5. Build Command: `pip install -r sevalla_assets/requirements-sevalla.txt`
6. Start Command: `uvicorn serving.backend.api_service:app --host 0.0.0.0 --port 8000`
7. Resources: Medium (2GB RAM, 1 CPU)
8. Health Check Path: `/health`

**Environment Variables (Add in Dashboard):**
```
AWS_ACCESS_KEY_ID = <your-key>
AWS_SECRET_ACCESS_KEY = <your-secret>
AWS_DEFAULT_REGION = us-east-1
LOG_LEVEL = INFO
```

### Step 4: Configure Frontend Service
1. Name: `finrag-frontend`
2. Same repo/branch as backend
3. Build Command: `pip install -r sevalla_assets/requirements-sevalla.txt`
4. Start Command: `streamlit run serving/frontend/chat.py --server.port 8501 --server.address 0.0.0.0 --server.headless true`
5. Resources: Micro (512MB RAM, 0.25 CPU)

**Environment Variables:**
```
BACKEND_URL = http://backend:8000
```

### Step 5: Deploy Manually
1. Backend → "Deployments" → "Deploy now"
2. Wait for build (10-15 min first time)
3. Check logs for errors
4. Frontend → "Deploy now"
5. Wait for build (3-5 min)

### Step 6: Enable Hibernation (Cost Savings)
1. Backend → Settings → Hibernation
2. Enable: 15 minutes idle timeout
3. Frontend → Settings → Hibernation
4. Enable: 15 minutes idle timeout

### Step 7: Test Deployment
1. Copy frontend public URL (e.g., `https://finrag-xxx.sevalla.app`)
2. Open in browser
3. Submit test query: "What was Apple's revenue in 2020?"
4. Verify answer appears
5. Check backend logs for AWS Bedrock calls

## Cost Management

**To avoid charges:**
- After testing → Suspend both services
- Before expo → Activate services
- After expo → Suspend again

**Suspend:**
1. Application → Settings → Danger Zone
2. Click "Suspend app"
3. Billing stops immediately ($0/hour)

**Activate:**
1. Application → Settings
2. Click "Activate app"
3. Wait 30 seconds for boot

## Troubleshooting

### Build Fails: "Module not found"
→ Add missing package to `requirements-sevalla.txt`

### Runtime Error: "AWS credentials not found"
→ Check environment variables in Sevalla dashboard

### Frontend Can't Reach Backend
→ Verify `BACKEND_URL=http://backend:8000` (no typo!)

### Health Check Failing
→ Check backend logs, ensure `/health` endpoint works

---

---

## Potential Code Changes Required (3 Files) -- Ignore, this is for developers

### 1. Frontend Service Discovery
**File:** `serving/frontend/chat.py`

**Change:**
```python
import os
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
```

### 2. AWS Credentials Fallback  --- done.
**File:** `finrag_ml_tg1/loaders/ml_config_loader.py`
**Modify `_load_aws_credentials` method** 

### 3. Verify Path Resolution (Optional) --- i think done, 99%. 
**File:** `serving/backend/config.py`
**Ensure:** `model_pipeline_root` uses absolute paths

### 4. Requirements File for Sevalla --- just done.
Ensure `requirements_sevalla.txt` is in environments, and craete backend, serving and frontend with the sh1 and bat scripts.
Maintain all 3, minimals. Application serving is minimal, Developers can use full.
Key Insight: Environment selection happens at shell level, not code level. Python code is completely unaware.

### 5. Potential: Backend Code Analysis.
- Backend Code Analysis: 
```python
allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    #               ^^^^^^^^^^^^^^^^^^^^ Hardcoded local frontend URL
```
- environment-aware for cloud? CORS might not matter (both services in same K8s cluster)
- need to test. pause.
- Backend Config (config.py) -- Environment-Aware. 
```python
class BackendConfig(BaseSettings):
    backend_host: str = Field(default="0.0.0.0", ...)  # ✅ Already correct!
    backend_port: int = Field(default=8000, ...)        # ✅ Already correct!
    
    model_config = SettingsConfigDict(
        env_file=".env",        # Reads from .env if exists
        case_sensitive=False,   # Reads BACKEND_PORT or backend_port
        extra="ignore"
    )
```
- Local: Uses defaults (8000, 0.0.0.0)
- Cloud: Sevalla can override via environment variables if needed

---

### Check Environment Sizes (for reference)
```powershell

# Navigate to ModelPipeline first
cd "D:\JoelDesktop folds_24\NEU FALL2025\MLops IE7374 Project\FinSights\ModelPipeline"

Write-Host "Environment Sizes:" -ForegroundColor Cyan; "venv_ml_rag", "venv_serving", "serving\frontend\venv_frontend" | ForEach-Object { $path = if($_ -eq "serving\frontend\venv_frontend"){"serving\frontend\venv_frontend"}else{"finrag_ml_tg1\$_"}; $size = (Get-ChildItem -Path $path -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1GB; Write-Host ("  {0,-20} {1:N2} GB" -f $_, $size) -ForegroundColor Yellow }

```