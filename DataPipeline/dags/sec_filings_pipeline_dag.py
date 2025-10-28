"""
Airflow DAG for SEC Filings ETL Pipeline
"""

from pathlib import Path
import os
import sys
import logging
import shutil
from datetime import datetime, timedelta

# Lightweight imports only
from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator
from airflow.task.trigger_rule import TriggerRule

# ============================================================================
# Setup 
# ============================================================================

AIRFLOW_HOME = Path(os.environ.get("AIRFLOW_HOME", "/opt/airflow"))
SRC_DIR = AIRFLOW_HOME / "src"

# Add src to path (fast)
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

LOG = logging.getLogger(__name__)


# ============================================================================
# Task Callables 
# ============================================================================

def _check_companies_and_config():
    """Check required files exist - imports done inside function"""
    CONFIG_DIR = AIRFLOW_HOME / "config"
    DATASETS_DIR = AIRFLOW_HOME / "datasets"
    CONFIG_PATH = CONFIG_DIR / "config.json"
    companies_csv = CONFIG_DIR / "companies.csv"
    
    missing = [str(p) for p in [CONFIG_PATH, companies_csv, DATASETS_DIR] if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Required files/dirs missing: {missing}")
    
    LOG.info("✅ Inputs present.")
    LOG.info(f"CONFIG_PATH={CONFIG_PATH}")
    LOG.info(f"DATASETS_DIR={DATASETS_DIR}")


def _run_module(module: str, args: list[str] | None = None):
    """Run a Python module - subprocess imported only when called"""
    import subprocess
    
    cmd = [sys.executable, "-m", module]
    if args:
        cmd.extend(args)
    
    LOG.info(f"▶ Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=str(AIRFLOW_HOME))
    LOG.info(f"✅ Finished: {module}")

def task_get_companies_list():
    """Connect to AWS S3 and get companies.csv"""
    _run_module("src.download_from_s3")
    
def task_download_sec_filings():
    """Download filings from SEC EDGAR"""
    _run_module("src.download_filings")

def task_extract_and_convert():
    """Extract items and convert to parquet"""
    _run_module("src.extract_and_convert")

def task_validate_data():
    """Validate extracted data using Great Expectations"""
    _run_module("data_auto_stats.src.run_validation")
    
def task_upload_files_to_s3():
    """Connect to AWS S3 and upload processed files"""
    _run_module("src.upload_to_s3")
    #LOG.info(f"🎉 Pipeline succeeded for upload")
    
def task_cleanup_temp_files(keep_json: bool = True):
    """Clean up temporary files and folders"""    
    
    DATASETS_DIR = AIRFLOW_HOME / "datasets"
    CONFIG_DIR = AIRFLOW_HOME / "config"
    
    # Directories to completely remove
    dirs_to_remove = [
        DATASETS_DIR / "CSV_FILES",
        DATASETS_DIR / "PARQUET_FILES",
        DATASETS_DIR / "MERGED_EXTRACTED_FILINGS",        
        DATASETS_DIR / "RAW_FILINGS" / "10-K",
        DATASETS_DIR / "EXTRACTED_FILINGS" / "10-K"
    ]
    
    # Remove specified directories
    for d in dirs_to_remove:
        if d.exists():
            try:
                shutil.rmtree(d)
                LOG.info(f"🧹 Deleted directory: {d}")
            except Exception as e:
                LOG.warning(f"⚠️  Failed to delete {d}: {e}")
    
    indices_dir = DATASETS_DIR / "INDICES"
    
    if indices_dir.exists():
        for child in indices_dir.iterdir():
            if child.is_file():
                child.unlink(missing_ok=True)
            elif child.is_dir():
                for sub in child.iterdir():
                    if sub.is_file():
                        sub.unlink(missing_ok=True)
        LOG.info("🧹 Cleaned %s", d)
    
    # Delete specific CSV files 
    csv_files_to_delete = [
        {
            "path": DATASETS_DIR / "FILINGS_METADATA.csv"
        },
        {
            "path": CONFIG_DIR / "companies.csv"
        }
    ]
    
    for file_config in csv_files_to_delete:
        csv_file = file_config["path"]        
        if csv_file.exists():
            try:
                csv_file.unlink(missing_ok=True)
                LOG.info(f"🧹 Deleted: {csv_file.name}")
            except Exception as e:
                LOG.warning(f"⚠️  Failed to delete {csv_file.name}: {e}")
        else:
            LOG.debug(f"File not found: {csv_file.name}")
    
    
    # Optionally delete JSON files from EXTRACTED_FILINGS
    # if not keep_json:
    #     extracted = DATASETS_DIR / "EXTRACTED_FILINGS" / "10-K"
    #     if extracted.exists():
    #         for child in extracted.iterdir():
    #             if child.is_dir():
    #                 # Delete JSON files inside subdirectories (like 10-K folder)
    #                 for json_file in child.glob("*.json"):
    #                     try:
    #                         json_file.unlink(missing_ok=True)
    #                     except Exception as e:
    #                         LOG.warning(f"⚠️  Failed to delete {json_file}: {e}")
    #             elif child.is_file() and child.suffix == ".json":
    #                 try:
    #                     child.unlink(missing_ok=True)
    #                 except Exception as e:
    #                     LOG.warning(f"⚠️  Failed to delete {child}: {e}")
    #         LOG.info("🧹 Deleted EXTRACTED_FILINGS JSONs")
    
    LOG.info("✅ Cleanup completed")

def task_merge_s3_data():
    """
    Merge historical/final + incremental data on S3
    Runs src_aws_etl.etl.merge_pipeline module
    """
    _run_module("src_aws_etl.etl.merge_pipeline")
    LOG.info("S3 merge pipeline completed")

def task_statistics_data():
    """Validate extracted data using Great Expectations"""
    _run_module("data_auto_stats.src.run_statistics")

def task_success_notify(execution_date: str):
    """Log success message"""
    LOG.info(f"🎉 Pipeline succeeded for {execution_date}")


def task_failure_notify(execution_date: str):
    """Log failure message"""
    LOG.error(f"❌ Pipeline failed for {execution_date}")


# ============================================================================
# DAG Definition
# ============================================================================

default_args = {
    "owner": "Sridipta Roy",
    "depends_on_past": False,
    "email": ["roy.sr@northeastern.com"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 1,  # Reduced for faster debugging
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=30),  # Reduced from 6 hours
}

with DAG(
    dag_id="sec_filings_etl_pipeline",
    description="Daily ETL: Download → Extract → Convert → Merge",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["sec", "etl", "daily"],
) as dag:
    
    get_companies_list = PythonOperator(
        task_id="get_companies_list",
        python_callable=task_get_companies_list,
    )

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

    validate_data = PythonOperator(
        task_id="validate_data",
        python_callable=task_validate_data,
    )
    
    upload_processed_files = PythonOperator(
        task_id="upload_processed_files",
        python_callable=task_upload_files_to_s3,
    )

    cleanup = PythonOperator(
        task_id="cleanup_temp_files",
        python_callable=task_cleanup_temp_files,
        op_kwargs={"keep_json": False},
    )

    # Merge S3 data - AWS.
    merge_s3_data = PythonOperator(
        task_id="merge_s3_incremental_data",
        python_callable=task_merge_s3_data,
        execution_timeout=timedelta(minutes=15),
    )

    statistics_data = PythonOperator(
        task_id="statistics_data",
        python_callable=task_statistics_data,
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

    # Task dependencies
    
    get_companies_list >> check_inputs >> download_filings >> extract_convert_merge >> validate_data >> upload_processed_files >> cleanup >> merge_s3_data >> statistics_data >> success_notify
    [get_companies_list, check_inputs, download_filings, extract_convert_merge, validate_data, upload_processed_files, cleanup, merge_s3_data, statistics_data] >> failure_notify