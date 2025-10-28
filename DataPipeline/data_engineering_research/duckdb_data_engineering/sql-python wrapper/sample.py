"""
----------------------------------------------------------------------------
finrag_sampling.py

**Wrapper for DuckDB sampling on AWS**

DEPLOYMENT: AWS SageMaker Notebook or EC2 with Airflow
STORAGE: S3 buckets, optional MotherDuck connection
AUTHOR: Joel Markapudi.
----------------------------------------------------------------------------

# Store SQL script in S3
    aws s3 cp 31_run_stratified.sql s3://finrag-scripts/

    # Download in notebook
    aws s3 cp s3://finrag-scripts/31_run_stratified.sql ./

More usage instructions:

    # Cell 1: Install dependencies
    !pip install duckdb boto3

    # Cell 2: Run sampling
    from finrag_sampling import run_sampling
    row_count = run_sampling()

    # Cell 3: Verify export
    import boto3
    s3 = boto3.client('s3')
    s3.head_object(Bucket='finrag-samples', Key='sec_finrag_1M_sample.parquet')
    print("✓ File exported to S3")
"""

import duckdb
from pathlib import Path
from datetime import datetime

# Optional Airflow imports
try:
    from airflow import DAG
    from airflow.operators.python import PythonOperator
except ImportError:
    pass


# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    'parquet_source': 's3://finrag-data/sec_filings_large_full.parquet',
    'export_path': 's3://finrag-samples',
    'sql_script': '/home/ec2-user/finrag/duckdb/31_run_stratified.sql',
    'sample_size': 1000000,
}


# ============================================================================
# CORE FUNCTION
# ============================================================================

def run_sampling(**kwargs):
    """Execute DuckDB sampling pipeline"""
    
    print(f"Starting sampling - {datetime.now()}")
    
    # Connect (use :memory: for cloud, or MotherDuck connection string)
    conn = duckdb.connect(':memory:')
    # For MotherDuck: conn = duckdb.connect('md:finrag_db?motherduck_token=xxx')
    
    # Install S3 support
    conn.execute("INSTALL httpfs; LOAD httpfs;")
    conn.execute(f"SET s3_region='us-east-1';")
    
    # Set variables
    conn.execute(f"SET VARIABLE parquet_source_path = '{CONFIG['parquet_source']}';")
    conn.execute(f"SET VARIABLE result_save_path = '{CONFIG['export_path']}';")
    conn.execute(f"SET VARIABLE result_parquet_name = 'sec_finrag_1M_sample';")
    conn.execute(f"SET VARIABLE sample_size_n = {CONFIG['sample_size']};")
    conn.execute(f"SET VARIABLE sample_version = 'v1.0_prod';")
    
    # Load and execute SQL
    with open(CONFIG['sql_script'], 'r') as f:
        sql_script = f.read()
    
    conn.execute(sql_script)
    
    # Get result count
    row_count = conn.execute("SELECT COUNT(*) FROM sample_1m_finrag").fetchone()[0]
    print(f"✓ Complete - Sampled {row_count:,} sentences")
    
    conn.close()
    return row_count


# ============================================================================
# AIRFLOW DAG (Optional)
# ============================================================================

def create_dag():
    """Single-task DAG for sampling"""
    
    dag = DAG(
        'finrag_sampling',
        schedule_interval=None,
        start_date=datetime(2024, 10, 1),
        catchup=False,
    )
    
    PythonOperator(
        task_id='run_sampling',
        python_callable=run_sampling,
        dag=dag,
    )
    
    return dag


# Standalone execution
if __name__ == '__main__':
    run_sampling()

# Airflow auto-registration
try:
    dag = create_dag()
except:
    pass

