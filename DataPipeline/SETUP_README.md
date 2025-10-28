# FinSights - DataPipeline 

### 1️⃣ Clone & Setup Environment
```bash
git clone https://github.com/Finsights-MLOps/MLOps_Final.git
cd MLOps_Final/DataPipeline
conda env create -f environment.yml
conda activate finsight-venv
```

### 2️⃣ Configure Credentials
```bash
cp .env.template .env
# Edit .env with AWS credentials. Please reach out to any team member of Group 4 for the access keys
```

### 3️⃣ Start Airflow
```bash
docker compose up airflow-init
docker compose up
```

### 4️⃣ Access UI
Open: http://localhost:8080
- Username: `airflow`
- Password: `airflow`

### 5️⃣ Trigger Pipeline
Click ▶️ next to `sec_filings_etl_pipeline`

---

## Common Commands
```bash
# View logs
docker compose logs -f

# Stop Airflow
docker compose down

# Restart services
docker compose restart

# Run tests
pytest tests/ -v
```
