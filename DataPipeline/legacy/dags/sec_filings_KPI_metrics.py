from __future__ import annotations

import os
import sys

# Resolve project root so that `src_metrics` is importable
DAGS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(DAGS_DIR, os.pardir))
# PROJECT_ROOT now points to .../FinSights

if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)


from datetime import datetime, timedelta
import os
from pathlib import Path
import json

from dotenv import load_dotenv

from airflow import DAG
from airflow.operators.python import PythonOperator

import src_metrics.analytical_layer as al
from src_metrics.analytical_layer import (
    run_analytical_layer_pipeline,
    upload_results_to_s3,
    send_coverage_email,
    send_success_email,
    send_failure_email,
)

# ------------------------------------------------------------------------------
# ENV + CONFIG  (keep here)
# ------------------------------------------------------------------------------

ENV_PATH = Path(os.getenv("FINRAG_ENV_FILE", ".env"))
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
    print(f"Loaded .env from: {ENV_PATH}")

EDGAR_IDENTITY = os.getenv("EDGAR_IDENTITY", "nicholas.nehemia95@gmail.com")
al.set_identity(EDGAR_IDENTITY)

BASE_DIR = os.getenv(
    "ANALYTICAL_LAYER_BASE_DIR",
    r"D:\MLOps\FinalProject\MLOps\analyticalLayer",
)
os.makedirs(BASE_DIR, exist_ok=True)

POLITE_DELAY = float(os.getenv("EDGAR_POLITE_DELAY", "1.5"))

# ------------------------------------------------------------------------------
# TASK 1: full pipeline
# ------------------------------------------------------------------------------

def run_analytical_layer_task(**context):
    run_date = context.get("data_interval_end")

    if run_date is None:
        run_date = datetime.utcnow()  # or datetime.today()
    else:
        # make it naive (drop tz) if you want, but not strictly required
        try:
            run_date = run_date.replace(tzinfo=None)
        except Exception:
            pass

    result = run_analytical_layer_pipeline(
        base_dir=BASE_DIR,
        polite_delay=POLITE_DELAY,
        run_date=run_date,
    )
    return result["summary"]

# ------------------------------------------------------------------------------
# TASK 2: upload to S3
# ------------------------------------------------------------------------------

def upload_to_s3_task(**context):
    dag_id  = context["dag"].dag_id
    task_id = context["task"].task_id
    run_id  = context["dag_run"].run_id

    # Use same paths as pipeline
    final_parquet_path   = os.path.join(BASE_DIR, "analytical_layer_metrics_final.parquet")
    coverage_csv_path    = os.path.join(BASE_DIR, "analytical_layer_coverage_last2yrs.csv")
    metadata_json_path   = os.path.join(BASE_DIR, "analytical_layer_run_metadata.json")

    for p in [final_parquet_path, coverage_csv_path, metadata_json_path]:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Missing expected file before S3 upload: {p}")

    s3_info = upload_results_to_s3(
        final_parquet_path=final_parquet_path,
        metadata_path=metadata_json_path,
        coverage_csv_path=coverage_csv_path,
        dag_id=dag_id,
        task_id=task_id,
        run_id=run_id,
    )
    print("S3 upload info:", s3_info)

# ------------------------------------------------------------------------------
# TASK 3: email
# ------------------------------------------------------------------------------

def send_email_task(**context):
    metadata_json_path = os.path.join(BASE_DIR, "analytical_layer_run_metadata.json")
    coverage_csv_path  = os.path.join(BASE_DIR, "analytical_layer_coverage_last2yrs.csv")

    if not os.path.exists(metadata_json_path):
        raise FileNotFoundError(f"Metadata JSON not found at {metadata_json_path}")
    if not os.path.exists(coverage_csv_path):
        raise FileNotFoundError(f"Coverage CSV not found at {coverage_csv_path}")

    with open(metadata_json_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    send_coverage_email(summary, coverage_csv_path)

def notify_success_task(**context):
    ts = datetime.utcnow().isoformat()
    send_success_email(ts)

def notify_failure_task(context):
    # Airflow passes context on failure
    exception = context.get("exception")
    msg = str(exception) if exception else "Unknown failure"
    ts = datetime.utcnow().isoformat()
    send_failure_email(msg, ts)

# ------------------------------------------------------------------------------
# DAG definition
# ------------------------------------------------------------------------------

default_args = {
    "owner": "finrag",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="analytical_layer_monthly",
    description="Build + merge EDGAR analytical layer, upload to S3, and email coverage report",
    default_args=default_args,
    start_date=datetime(2025, 1, 1),
    schedule="@monthly",   # <<<< use `schedule` instead of `schedule_interval`
    catchup=False,
    tags=["finrag", "analytical_layer"],
) as dag:


    run_analytical_layer_op = PythonOperator(
        task_id="build_merge_and_coverage",
        python_callable=run_analytical_layer_task,
    )

    upload_to_s3_op = PythonOperator(
        task_id="upload_results_to_s3",
        python_callable=upload_to_s3_task,
    )

    send_email_op = PythonOperator(
        task_id="send_coverage_email",
        python_callable=send_email_task,
    )
    notify_success_op = PythonOperator(
    task_id="notify_success",
    python_callable=notify_success_task,
    trigger_rule="all_success",   # only if all tasks succeed
    )

    notify_failure_op = PythonOperator(
    task_id="notify_failure",
    python_callable=notify_failure_task,
    trigger_rule="one_failed",    # fire immediately when ANY upstream fails
    )


run_analytical_layer_op >> upload_to_s3_op >> send_email_op >> notify_success_op

# failure notification listens to ALL tasks
[
    run_analytical_layer_op,
    upload_to_s3_op,
    send_email_op
] >> notify_failure_op

