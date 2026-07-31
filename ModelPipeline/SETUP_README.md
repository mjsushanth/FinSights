# FinSights - Setup and Startup

**One click: double-click `ModelPipeline/finsights.command`.** It checks the
environment, builds the Docker images if they are missing, starts backend and
frontend, waits for both health checks, and opens the browser - all in a single
terminal window.

Everything below explains what that script does and how to run it by hand.

---

## Prerequisites

- **Docker Desktop.** That is the only real requirement. The images carry the
  entire Python environment (interpreter, boto3, polars, FastAPI, Streamlit), so
  there is no Python, venv, conda, or `uv` step for a normal run.
- **AWS credentials** at `finrag_ml_tg1/.aws_secrets/aws_credentials.env`
  (gitignored). The backend cannot reach Bedrock or S3 Vectors without them:

  ```
  AWS_ACCESS_KEY_ID=your_key_here
  AWS_SECRET_ACCESS_KEY=your_secret_here
  AWS_DEFAULT_REGION=us-east-1
  ```

  The file is passed to the container by Docker Compose `env_file` at runtime and
  is deliberately excluded from the image, so credentials are never baked into a
  layer.

### Clone

```bash
git clone https://github.com/Finsights-MLOps/FinSights.git
cd FinSights/ModelPipeline
```

If the launcher is not executable after cloning:

```bash
chmod +x finsights.command
```

---

## The launcher

Double-click `finsights.command`, or run `./finsights.command`. It reports status
first - Docker CLI, daemon, credentials, compose file, whether each image is
built, and whether ports 8000 / 8501 are free or already served by the stack -
then offers:

| Option | What it does |
| :-- | :-- |
| 1 | Start the app; builds images if they are missing |
| 2 | Restart with a rebuild, reusing valid cache |
| 3 | Full clean rebuild (`--no-cache`), several minutes |
| 4 | Stop the app (`docker compose down`) |
| 5 | Stream logs (Ctrl+C returns to the menu) |
| 6 | Refresh status |
| q | Quit, leaving the stack as it is |

If the Docker daemon is not running, the launcher offers to start Docker Desktop
and waits for it.

---

## Manual equivalent

```bash
cd ModelPipeline/finrag_docker_loc_tg1
docker compose up -d --build      # start
docker compose ps                 # status
docker compose logs -f            # logs
docker compose down               # stop
```

Endpoints:

- Frontend  <http://localhost:8501>
- Backend health  <http://localhost:8000/health>
- API docs  <http://localhost:8000/docs>

Full Docker notes: [Dockerized Setup Guide](./finrag_docker_loc_tg1/LOC_DOCKER_README.md).

**AWS/ECS deployment:** [ECS Fargate Design and Runbook](./finrag_docker_loc_tg1_aws/ECS_FARGATE_RUNBOOK.md)
- the live deployment. Double-click `finsights_aws.command`, or run
`python -m deploy_aws.cli up` from `ModelPipeline/`. `down` scales to zero so it stops
billing; `destroy` removes everything including the images.
Historical only: [Dec 2025 ECS record](./finrag_docker_loc_tg1_aws/HISTORICAL_2025-12_ECS_DEPLOYMENT_GUIDE.md) - a decommissioned account, not a runbook.

---

## What to expect from a query

- **Cost:** $0.017-$0.06+ per query (real Bedrock spend, scales with query complexity).
- **Latency:** 25-50 seconds. This is a deliberate cost-over-latency trade-off,
  not a bug - see `finrag_ml_tg1/PIPELINE_LATENCY_ANALYSIS.md`.
- Answers end with grouped, per-company source citations.

---

## Service shapes (for reference)

**Backend (FastAPI)**
- Code root: `ModelPipeline/`
- Entrypoint: `serving/backend/api_service:app`, port 8000
- Deps: `finrag_ml_tg1/environments/requirements_app_backend.txt`
- Needs AWS credentials plus `MODEL_PIPELINE_ROOT`

**Frontend (Streamlit)**
- Code under `serving/frontend/`, port 8501
- Deps: `serving/frontend/requirements.txt`
- Reads `BACKEND_URL`, which Compose sets to `http://backend:8000`

---

## Notes

- **No local data is needed.** In a container the app runs in `S3_STREAMING` mode
  and reads its tables from S3 directly; `finrag_ml_tg1/data_cache/` is
  intentionally empty. The `MODEL_PIPELINE_ROOT=/app` env var in
  `backend.Dockerfile` is what selects that mode - do not remove it.
- **Shut the stack down before quitting Docker Desktop** (launcher option 4).
  Quitting Docker Desktop with containers still running has hung its shutdown
  path on macOS.
- **Retired 2026-07-30:** `setup_finrag.command` / `.ps1` / `.bat`,
  `start_finrag.command` / `.ps1` / `.bat`, and `serving/sh files - outdated/`.
  They created three virtualenvs that no longer exist, spawned multiple Terminal
  windows via `osascript`, and one ran a global `pkill -9 python`.
  `finsights.command` replaces all of them. They remain recoverable in git history.
