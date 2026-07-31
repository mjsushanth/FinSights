"""
Airflow DAG for SEC Filings ETL Pipeline
Daily pipeline to download, extract, and convert SEC filings to parquet format
"""

from __future__ import annotations
from datetime import datetime, timedelta
import logging
import os
import sys
import subprocess
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.task.trigger_rule import TriggerRule

from pathlib import Path
import os, sys, logging

DAG_FILE = Path(__file__).resolve()

# Airflow’s home in the official image is /opt/airflow
AIRFLOW_HOME = Path(os.environ.get("AIRFLOW_HOME", "/opt/airflow"))

# Everything you mount in docker-compose is under /opt/airflow/*
PROJECT_ROOT   = AIRFLOW_HOME                     # /opt/airflow
CONFIG_DIR     = PROJECT_ROOT / "config"          # /opt/airflow/config
DATASETS_DIR   = PROJECT_ROOT / "datasets"        # /opt/airflow/datasets
SRC_DIR        = PROJECT_ROOT / "src"             # /opt/airflow/src
CONFIG_PATH    = CONFIG_DIR / "config.json"

LOG = logging.getLogger(__name__)

# Make src/ importable for task callables
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ------------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------------
def _check_companies_and_config():
    companies_csv = CONFIG_DIR / "companies.csv"
    missing = [str(p) for p in [CONFIG_PATH, companies_csv, DATASETS_DIR] if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Required files/dirs missing: {missing}")
    LOG.info("✅ Inputs present.")
    LOG.info("CONFIG_PATH=%s", CONFIG_PATH)
    LOG.info("DATASETS_DIR=%s", DATASETS_DIR)


# def _run_python_script(script_relpath: str, args: list[str] | None = None):
#     """
#     Run a Python script relative to /opt/airflow/src (inside container)
#     """
#     script = SRC_DIR / Path(script_relpath).name
#     if not script.exists():
#         raise FileNotFoundError(f"Script not found: {script}")
#     cmd = [sys.executable, str(script)]
#     if args:
#         cmd.extend(args)
#     LOG.info("▶ Running: %s", " ".join(cmd))
#     subprocess.run(cmd, check=True)
#     LOG.info("✅ Finished: %s", script_relpath)
def _run_module(module: str, args: list[str] | None = None):
    cmd = [sys.executable, "-m", module]
    if args:
        cmd.extend(args)
    LOG.info("▶ Running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=str(AIRFLOW_HOME))
    LOG.info("✅ Finished: %s", module)


def task_download_sec_filings():
    _run_module("src_legacy_bs4_scraper.download_filings") 

def task_extract_and_convert():
    _run_module("src_legacy_bs4_scraper.extract_and_convert")


def task_cleanup_temp_files(keep_json: bool = True):
    raw_dir = DATASETS_DIR / "RAW_FILINGS"
    indices_dir = DATASETS_DIR / "INDICES"

    for d in [raw_dir, indices_dir]:
        if d.exists():
            for child in d.iterdir():
                if child.is_file():
                    child.unlink(missing_ok=True)
                elif child.is_dir():
                    for sub in child.iterdir():
                        if sub.is_file():
                            sub.unlink(missing_ok=True)
            LOG.info("🧹 Cleaned %s", d)

    if not keep_json:
        extracted = DATASETS_DIR / "EXTRACTED_FILINGS"
        if extracted.exists():
            for child in extracted.iterdir():
                if child.is_file():
                    child.unlink(missing_ok=True)
            LOG.info("🧹 Deleted EXTRACTED_FILINGS JSONs")

def task_success_notify(execution_date: str):
    LOG.info("🎉 Pipeline succeeded for %s", execution_date)

def task_failure_notify(execution_date: str):
    LOG.error("❌ Pipeline failed for %s", execution_date)

# ------------------------------------------------------------------------------------
# DAG
# ------------------------------------------------------------------------------------
default_args = {
    "owner": "Tooba Ali",
    "depends_on_past": False,
    "email": ["ali.syeda@northeastern.com"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=6),
}

with DAG(
    dag_id="sec_filings_etl_pipeline",
    description="Daily ETL: Download → Extract → Convert → Merge",
    default_args=default_args,
    #schedule="0 2 * * *",   # 2 AM daily
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["sec", "etl", "daily"],
) as dag:

    check_inputs = PythonOperator(
        task_id="check_inputs",
        python_callable=_check_companies_and_config,
    )

    download_filings = PythonOperator(
        task_id="download_sec_filings",
        python_callable=task_download_sec_filings,
    )

    extract_convert_merge = PythonOperator(
        task_id="extract_convert_merge",
        python_callable=task_extract_and_convert,
    )

    cleanup = PythonOperator(
        task_id="cleanup_temp_files",
        python_callable=task_cleanup_temp_files,
        op_kwargs={"keep_json": True},
    )

    success_notify = PythonOperator(
        task_id="send_success_notification",
        python_callable=task_success_notify,
        op_kwargs={"execution_date": "{{ ds }}"},
    )

    failure_notify = PythonOperator(
        task_id="send_failure_notification",
        python_callable=task_failure_notify,
        op_kwargs={"execution_date": "{{ ds }}"},
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    # Orchestration
    check_inputs >> download_filings >> extract_convert_merge >> cleanup >> success_notify
    [check_inputs, download_filings, extract_convert_merge, cleanup] >> failure_notify
    
    
    # If this script is run directly, allow command-line interaction with the DAG
    if __name__ == "__main__":
        dag.test()
