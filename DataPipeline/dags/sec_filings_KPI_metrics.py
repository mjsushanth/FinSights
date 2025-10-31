import sys
from pathlib import Path

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))



from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from src_metrics import data_ingestion
from src_metrics import data_loading
from src_metrics import data_preprocessing
from utils import notifier
from utils.helpers import setup_logger

logger = setup_logger()

def ingest_data_task(**context):
    """Wrapper for data ingestion task."""
    return data_ingestion.ingest_data(n=2)

def preprocess_data_task(**context):
    """Wrapper for data preprocessing task."""
    ti = context['ti']
    raw_data = ti.xcom_pull(task_ids='qualitative_extraction')
    
    if not raw_data:
        logger.warning("No raw data received from ingestion task")
        return None
    
    processed_data = []
    for ticker, facts in raw_data.items():
        processed = data_preprocessing.process_company_data(ticker, facts)
        processed_data.extend(processed)
    
    return processed_data

def load_data_task(**context):
    """Wrapper for data loading task."""
    ti = context['ti']
    processed_data = ti.xcom_pull(task_ids='preprocess_data')
    
    if not processed_data:
        logger.warning("No processed data to save")
        return None
    
    return data_loading.save_to_s3(processed_data)

default_args = {
    "owner": "Finsights",
    "depends_on_past": False,
    "email_on_failure": False,  # we'll handle manually
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}




with DAG(
    dag_id="sec_10k_pipeline",
    default_args=default_args,
    description="End-to-end SEC 10-K RAG + Metric Extraction Pipeline",
    schedule="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["sec", "rag", "financial-analysis"],
    is_paused_upon_creation=True,
) as dag:

    data_ingest = PythonOperator(
        task_id="qualitative_extraction",
        python_callable=ingest_data_task,
    )

    data_preprocess = PythonOperator(
        task_id="preprocess_data",
        python_callable=preprocess_data_task,
    )

    data_load = PythonOperator(
        task_id="load_to_s3",
        python_callable=load_data_task,
    )

    notify_failure_task = PythonOperator(
        task_id="notify_failure",
        python_callable=lambda: notifier.send_notification(
            "SEC 10-K Pipeline Failure ",
            "One or more pipeline tasks failed. Please review Airflow logs."
        ),
        trigger_rule="one_failed",  # triggers only if a previous task fails
    )

    notify_success_task = PythonOperator(
        task_id="notify_success",
        python_callable=lambda: notifier.send_notification(
            "SEC 10-K Pipeline Success ",
            "All pipeline tasks completed successfully."
        ),
        trigger_rule="all_success",  # triggers only if all previous tasks succeed
    )

    # Define task dependencies
    data_ingest >> data_preprocess >> data_load
    
    # Both notification tasks depend on data_load, but trigger based on different rules
    data_load >> [notify_failure_task, notify_success_task]
