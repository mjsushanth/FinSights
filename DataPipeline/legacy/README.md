# DataPipeline/legacy

Archived, non-functional-going-forward artifacts from the original
Airflow + Docker-based pipeline design. Moved here (not deleted) on
2026-07-27 so `DataPipeline/`'s root reflects what's actually active today
- see `../CLOUD_SOURCE_OF_TRUTH.md` and `../src_edgar_incremental/PLAN.md`
for the current architecture (edgartools-based fetching, S3 as the source
of truth, no Docker/Airflow dependency).

## What's here and why

- **`dags/`** - the two Airflow DAGs (`sec_filings_pipeline_dag.py`,
  `sec_filings_KPI_metrics.py`) that used to orchestrate the pipeline.
  Superseded by direct script execution (`src_edgar_incremental/run_pipeline.py`,
  `src_metrics/run_pipeline.py`) - no scheduler needed for this project's
  scale.
- **`Dockerfile`** (empty, 0 bytes) and **`docker-compose.yaml`** (a
  stock Apache Airflow cluster compose file) - no longer needed now that
  nothing here runs inside a container or an Airflow cluster.
- **`config/`** - `config.json` (the old BeautifulSoup scraper's config,
  used by `src_legacy_bs4_scraper/`) and `airflow.cfg` (Airflow's own
  config file). Not a Python package - never actually importable as
  `from config import ...`.
- **`data-env/`** - an entire old Python virtualenv (pyvenv.cfg + bin/)
  that had been sitting in the repo, parallel to and competing with the
  conda-based `environment.yml` that's now the single source of truth for
  DataPipeline's dependencies. Not meant to be activated or maintained -
  kept only as a historical artifact.
- **`requirements.txt`** - the old pip-based dependency list (beautifulsoup4,
  nltk, pathos, cssutils, ...) tied to the legacy scraper stack. The
  active dependency file is `../environment.yml` (conda, `finsight-venv`).
- **`.env.template`** - environment-variable template for the old
  Airflow/Docker-Compose setup (`AIRFLOW_UID`, `_PIP_ADDITIONAL_REQUIREMENTS`,
  SMTP email settings). Current modules use `.aws_config/*.yaml` +
  `.aws_secrets/*.env` per-module config instead (see
  `../src_aws_etl/.aws_config/etl_config.yaml` for the pattern).
- **`SETUP_README.md`** - setup instructions for the old
  `conda + Docker Compose + Airflow UI` workflow. See the top-level
  `DataPipeline/README.md` for current setup.
- **`utils/`** - `notifier.py` (SMTP email alerting, with a hardcoded
  personal email address) and `helpers.py` (a logger factory), both only
  ever used by the legacy pipeline driver below.
- **`pipeline_runner.py`** - "a standalone pipeline runner that executes
  the same tasks as the Airflow DAG" (its own docstring) - a
  Docker/GitHub-Actions-oriented driver for the same legacy scraper
  pipeline. Superseded by the per-module `run_pipeline.py` entrypoints.
- **`datasets.dvc`** / **`datasets/`** - DVC pointer and (empty) local
  data directory for the old dataset-versioning setup. Not used by any
  current module - S3 is the source of truth now (see
  `../CLOUD_SOURCE_OF_TRUTH.md`).

## What's deliberately NOT here

`src_legacy_bs4_scraper/` (the old scraping logic itself) and
`src_metrics_legacy/` (the old KPI extraction logic) are kept as their own
top-level folders, not moved under `legacy/` - they're substantial code
modules with their own git history and are referenced directly from
`PLAN.md`/`LEGACY_MODULE_FINDINGS.md` documents as "what this was ported
from." This folder is for the surrounding tooling/config/environment
clutter, not for archived source code modules.
