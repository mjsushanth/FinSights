## Prerequisites
- Python 3.11+ installed
- Git (to clone the repository)
- Windows: PowerShell | Mac/Linux: Terminal


### Clone the Repository
```bash
git clone 
cd FinSights/ModelPipeline
```

### Configure AWS Credentials
Create or update `finrag_ml_tg1/.aws_secrets/aws_credentials.env`:
```
AWS_ACCESS_KEY_ID=your_key_here
AWS_SECRET_ACCESS_KEY=your_secret_here
AWS_REGION=us-east-1
```

### Make Scripts Executable (Mac/Linux Only)
```bash
cd ModelPipeline
chmod +x start_finrag.sh
```

## Quick Setup (Automated)

### Windows
1. Navigate to `ModelPipeline/` folder
2. **Double-click** `setup_finrag.bat`
3. Wait 1-2 minutes for setup to complete
4. UV will be installed automatically for fast dependency resolution
5. Will automatically handle the issues of terminating Python processes and safely deleting old environment if the user wishes to delete, recreate. Graceful handling. ( Process killing, Rename Fallback, Cleanup utility. )

### Mac/Linux
1. Navigate to `ModelPipeline/` folder
2. Make script executable: `chmod +x setup_finrag.sh`
3. **Double-click** `setup_finrag.sh` (or run `./setup_finrag.sh`)
4. Wait 1-2 minutes for setup to complete
5. UV will be installed automatically for fast dependency resolution


## Starting FinRAG
1. After setup, just double-click `start_finrag.bat` (Windows) or `start_finrag.sh` (Mac/Linux).
2. Give it roughly 20s. There's an intentional 8-second backend, 6-second frontend sleep.
3. You should see like three terminals popping up and finally your browser would automatically open the streamlit interface through which communication can be done and queries sent.


### Quick check:
1. virtual environments MUST be in these exact locations:
    - `ModelPipeline/finrag_ml_tg1/venv_ml_rag/`
    - `ModelPipeline/serving/frontend/venv_frontend/`
```
ModelPipeline/
├── finrag_ml_tg1/
│   └── (no venv_ml_rag yet)
└── serving/frontend/
    └── (no venv_frontend yet)
```

2. UV auto-install - (need) 20x faster dependency installation than pip.
3. Workflow 1: "Just check if UV is installed"
4. Workflow 2: "I broke my backend environment" - Just re-run `setup_finrag` script.
5. Workflow 3: "Fresh start everything/ New PC setup" - Just re-run `setup_finrag` script! `:)` 
