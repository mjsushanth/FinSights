"""
Configuration management for SEC Filings validation pipeline
Supports different schemas for validation (20 cols) and statistics (24 cols)
"""
import os
from pathlib import Path
from typing import Dict, List, Any
import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Base paths
BASE_DIR = Path(__file__).parent.parent.absolute()
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
GE_DIR = BASE_DIR / "great_expectations"
LOG_DIR = BASE_DIR / "logs"

# S3 Configuration  
S3_CONFIG = {
    'enabled': True,
    'bucket_name': 'sentence-data-ingestion',
    # Different S3 keys for different phases
    'validation_s3_key': 'INGESTION_ASSETS/MERGED-SETS/10-K_merged_.parquet',  # 20 columns
    'statistics_s3_key': 'DATA_MERGE_ASSETS/FINRAG_FACT_SENTENCES/finrag_fact_sentences.parquet',    # 24 columns
}

# Default data paths for each phase
DATA_PATHS = {
    'validation': {
        'local': DATA_DIR / 'merged' / 'merged_data_20cols.parquet',  # Default local path for validation
        'use_s3': True,  # Set to True to use S3 by default
        's3_bucket': S3_CONFIG['bucket_name'],
        's3_key': S3_CONFIG['validation_s3_key']
    },
    'statistics': {
        'local': DATA_DIR / 'final' / 'final_data_24cols.parquet',  # Default local path for statistics
        'use_s3': True,  # Set to True to use S3 by default
        's3_bucket': S3_CONFIG['bucket_name'],
        's3_key': S3_CONFIG['statistics_s3_key']
    }
}

# Data paths
RAW_DATA_PATH = f"s3://{S3_CONFIG['bucket_name']}/{S3_CONFIG['validation_s3_key']}"
PROCESSED_DATA_PATH = DATA_DIR / "processed"
REFERENCE_DATA_PATH = DATA_DIR / "reference"

# Great Expectations paths
GE_CONFIG_PATH = GE_DIR / "great_expectations.yml"
EXPECTATIONS_PATH = GE_DIR / "expectations"
CHECKPOINTS_PATH = GE_DIR / "checkpoints"
DATA_DOCS_PATH = GE_DIR / "data_docs"

# Validation settings
VALIDATION_CONFIG = {
    'missing_value_threshold': 0.1,  # 10% max missing
    'quality_score_threshold': 0.8,  # 80% min quality
    'anomaly_detection_threshold': 0.05,  # 5% max anomalies
    'batch_size': 10000,  # For chunked processing
}

# SCHEMA FOR PHASE 1: VALIDATION (20 columns - raw/merged data)
VALIDATION_SCHEMA_CONFIG = {
    'expected_columns': [
        'cik', 'name', 'report_year', 'docID', 'sentenceID',
        'section_name', 'section_item', 'section_ID', 'form', 'sentence_index',
        'sentence', 'SIC', 'filingDate', 'reportDate', 'temporal_bin',
        'sample_created_at', 'last_modified_date', 'sample_version',
        'source_file_path', 'load_method'
    ],
    'numeric_columns': {
        'report_year': {'min': 2000, 'max': 2030},
        'SIC': {'min': 0, 'max': 9999},
        'section_ID': {'min': 0, 'max': 20},
        'sentence_index': {'min': 0, 'max': 10000}
    },
    'categorical_columns': {
        'form': ['10-K'],
        'temporal_bin': ['bin_2006_2009', 'bin_2010_2015', 'bin_2016_2020', 'bin_2021_2025'],
        'load_method': ['stratified_sampling', 'random_sampling', 'full_load', 'extract_and_convert']
    },
    'text_columns': {
        'sentence': {'min_length': 10, 'max_length': 10000},
        'section_name': {'min_length': 3, 'max_length': 100}
    },
    'date_columns': ['filingDate', 'reportDate', 'sample_created_at', 'last_modified_date'],
    'identifier_columns': ['cik', 'docID', 'sentenceID'],
    'critical_columns': ['cik', 'name', 'docID', 'sentenceID', 'sentence']  # Must not be null
}

# SCHEMA FOR PHASE 2: STATISTICS (24 columns - with derived columns added)
STATISTICS_SCHEMA_CONFIG = {
    'expected_columns': [
        'cik', 'cik_int', 'name', 'tickers', 'docID', 'sentenceID',
        'section_ID', 'section_name', 'form', 'sic', 'sentence',
        'filingDate', 'report_year', 'reportDate', 'temporal_bin',
        'likely_kpi', 'has_numbers', 'has_comparison',  # Derived columns
        'sample_created_at', 'last_modified_date', 'sample_version',
        'source_file_path', 'load_method', 'row_hash'  # row_hash is also derived
    ],
    'numeric_columns': {
        'cik_int': {'min': 0, 'max': 9999999999},
        'report_year': {'min': 2000, 'max': 2030},
        'sic': {'min': 0, 'max': 9999},
        'section_ID': {'min': 0, 'max': 20}
    },
    'categorical_columns': {
        'form': ['10-K'],
        'section_name': ['ITEM_1', 'ITEM_1A', 'ITEM_2', 'ITEM_3', 'ITEM_7', 'ITEM_8', 'ITEM_9', 
                        'ITEM_10', 'ITEM_11', 'ITEM_12', 'ITEM_13', 'ITEM_14', 'ITEM_15'],
        'temporal_bin': ['bin_2006_2009', 'bin_2010_2015', 'bin_2016_2020', 'bin_2021_2025'],
        'load_method': ['stratified_sampling', 'random_sampling', 'full_load', 'extract_and_convert']
    },
    'boolean_columns': ['likely_kpi', 'has_numbers', 'has_comparison'],  # Derived columns
    'text_columns': {
        'sentence': {'min_length': 10, 'max_length': 10000},
        'section_name': {'min_length': 3, 'max_length': 100}
    },
    'date_columns': ['filingDate', 'reportDate', 'sample_created_at', 'last_modified_date'],
    'identifier_columns': ['cik', 'cik_int', 'docID', 'sentenceID', 'row_hash'],
    'list_columns': ['tickers'],  # Derived column
    'derived_columns': ['cik_int', 'tickers', 'likely_kpi', 'has_numbers', 'has_comparison', 'row_hash']
}

# Default to statistics schema for backward compatibility
SEC_SCHEMA_CONFIG = STATISTICS_SCHEMA_CONFIG

# Phase-specific configuration
PHASE_CONFIG = {
    'validation': {
        'schema': VALIDATION_SCHEMA_CONFIG,
        's3_key': S3_CONFIG.get('validation_s3_key'),
        'expected_column_count': 20,
        'send_alert': True,
        'generate_statistics': False,
        'output_dir': 'validation_results'
    },
    'statistics': {
        'schema': STATISTICS_SCHEMA_CONFIG,
        's3_key': S3_CONFIG.get('statistics_s3_key'),
        'expected_column_count': 24,
        'send_alert': False,
        'generate_statistics': True,
        'output_dir': 'statistics_results'
    },
    'both': {
        'schema': STATISTICS_SCHEMA_CONFIG,  # Uses full schema for backward compatibility
        's3_key': S3_CONFIG.get('statistics_s3_key'),
        'expected_column_count': 24,
        'send_alert': True,
        'generate_statistics': True,
        'output_dir': 'full_results'
    }
}

# Monitoring configuration
MONITORING_CONFIG = {
    'enable_metrics': True,
    'metrics_port': 8000,
    'log_level': os.getenv('LOG_LEVEL', 'INFO'),
    'alert_email': os.getenv('ALERT_EMAIL', 'data-team@company.com'),
}

# Airflow configuration
AIRFLOW_CONFIG = {
    'dag_id': 'sec_filings_validation',
    'schedule_interval': '@daily',
    'max_active_runs': 1,
    'catchup': False,
}

def get_schema_for_phase(phase: str = 'both') -> Dict[str, Any]:
    """Get the appropriate schema configuration for the given phase"""
    return PHASE_CONFIG.get(phase, PHASE_CONFIG['both'])['schema']

def get_s3_key_for_phase(phase: str = 'both') -> str:
    """Get the appropriate S3 key for the given phase"""
    return PHASE_CONFIG.get(phase, PHASE_CONFIG['both'])['s3_key']

def load_config(config_file: str = None) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if config_file and Path(config_file).exists():
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    return {}

def save_config(config: Dict[str, Any], config_file: str):
    """Save configuration to YAML file"""
    with open(config_file, 'w') as f:
        yaml.dump(config, f, default_flow_style=False)