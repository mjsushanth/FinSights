"""
Data loading utilities for SEC filings with S3 support
Supports different schemas for validation (20 cols) vs statistics (24 cols)
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Literal
import logging
from datetime import datetime
import pyarrow.parquet as pq
import boto3
from io import BytesIO
import os
from dotenv import load_dotenv

from config import (
    RAW_DATA_PATH, 
    VALIDATION_CONFIG,
    get_schema_for_phase,
    get_s3_key_for_phase
)

logger = logging.getLogger(__name__)

class SECDataLoader:
    """Handle data loading for SEC filings from local or S3"""
    
    def __init__(self, data_path: Optional[str] = None, 
                 use_s3: bool = False, 
                 bucket_name: Optional[str] = None, 
                 s3_key: Optional[str] = None,
                 phase: Literal["validation", "statistics", "both"] = "both"):
        """
        Initialize data loader
        
        Args:
            data_path: Local file path (used if use_s3=False)
            use_s3: Whether to load from S3
            bucket_name: S3 bucket name
            s3_key: S3 object key (path within bucket)
            phase: Which phase we're loading for (determines expected schema)
        """
        self.use_s3 = use_s3
        self.bucket_name = bucket_name
        self.s3_key = s3_key
        self.phase = phase
        
        # Get phase-specific schema
        self.schema_config = get_schema_for_phase(phase)
        
        if use_s3:
            # If no specific S3 key provided, use phase-specific default
            if not s3_key:
                self.s3_key = get_s3_key_for_phase(phase)
            
            # Initialize S3 client
            self._init_s3()
            self.data_path = f"s3://{bucket_name}/{self.s3_key}"
        else:
            # Use local path
            if data_path:
                self.data_path = Path(data_path) if isinstance(data_path, str) else data_path
            else:
                raise ValueError("No data path provided. Either provide a local file path or configure S3.")
        
        self.df = None
        self.metadata = {}
        
        logger.info(f"DataLoader initialized for phase: {phase}")
        logger.info(f"Expected columns: {len(self.schema_config['expected_columns'])}")
    
    def _init_s3(self):
        """Initialize S3 client with credentials"""
        # Load AWS credentials from .aws_secrets/aws_credentials.env
        secrets_path = Path(__file__).parent.parent / '.aws_secrets' / 'aws_credentials.env'
        if secrets_path.exists():
            load_dotenv(secrets_path)
            logger.info(f"Loaded AWS credentials from {secrets_path}")
        else:
            logger.warning(f"AWS credentials file not found at {secrets_path}, using default credentials")
        
        # Initialize S3 client
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        
        # Test connection
        try:
            self.s3.head_bucket(Bucket=self.bucket_name)
            logger.info(f"Successfully connected to S3 bucket: {self.bucket_name}")
        except Exception as e:
            logger.error(f"Failed to connect to S3 bucket {self.bucket_name}: {e}")
            raise
    
    def load_data_from_s3(self) -> pd.DataFrame:
        """Load data directly from S3"""
        logger.info(f"Loading data from S3: s3://{self.bucket_name}/{self.s3_key}")
        
        try:
            # Get object from S3
            response = self.s3.get_object(Bucket=self.bucket_name, Key=self.s3_key)
            
            # Check file extension
            if self.s3_key.endswith('.parquet'):
                # Read parquet directly from bytes
                self.df = pd.read_parquet(BytesIO(response['Body'].read()))
                
            elif self.s3_key.endswith('.csv'):
                # Read CSV directly from bytes
                self.df = pd.read_csv(BytesIO(response['Body'].read()))
                
            else:
                raise ValueError(f"Unsupported file type for S3 key: {self.s3_key}")
            
            logger.info(f"Successfully loaded {len(self.df):,} records from S3")
            logger.info(f"Columns found: {len(self.df.columns)} (Expected: {len(self.schema_config['expected_columns'])})")
            return self.df
            
        except Exception as e:
            logger.error(f"Error loading data from S3: {e}")
            raise
    
    def load_data(self, sample_size: Optional[int] = None) -> pd.DataFrame:
        """Load SEC filings data from local or S3"""
        
        if self.use_s3:
            # Load from S3
            self.df = self.load_data_from_s3()
        else:
            # Load from local file
            logger.info(f"Loading data from local file: {self.data_path}")
            
            try:
                # Ensure path is a Path object
                if not isinstance(self.data_path, Path):
                    self.data_path = Path(self.data_path)
                
                # Check if file exists
                if not self.data_path.exists():
                    raise FileNotFoundError(f"Data file not found: {self.data_path}")
                
                if self.data_path.suffix == '.parquet':
                    self.df = pd.read_parquet(self.data_path)
                elif self.data_path.suffix == '.csv':
                    self.df = pd.read_csv(self.data_path)
                else:
                    raise ValueError(f"Unsupported file type: {self.data_path.suffix}")
                    
            except Exception as e:
                logger.error(f"Error loading data: {e}")
                raise
        
        # Apply sampling if requested
        if sample_size and sample_size < len(self.df):
            self.df = self.df.sample(n=sample_size, random_state=42)
            logger.info(f"Sampled {sample_size} records from {len(self.df):,} total")
        
        self._collect_metadata()
        logger.info(f"Loaded {len(self.df):,} records with {len(self.df.columns)} columns for phase: {self.phase}")
        
        # Log column difference for debugging
        actual_cols = set(self.df.columns)
        expected_cols = set(self.schema_config['expected_columns'])
        if actual_cols != expected_cols:
            missing = expected_cols - actual_cols
            extra = actual_cols - expected_cols
            if missing:
                logger.warning(f"Missing columns for {self.phase} phase: {missing}")
            if extra:
                logger.info(f"Extra columns in data: {extra}")
        
        return self.df
    
    def _collect_metadata(self):
        """Collect metadata about loaded data"""
        self.metadata = {
            'file_path': str(self.data_path),
            'source': 'S3' if self.use_s3 else 'Local',
            'load_timestamp': datetime.now().isoformat(),
            'phase': self.phase,
            'num_rows': len(self.df),
            'num_columns': len(self.df.columns),
            'expected_columns': len(self.schema_config['expected_columns']),
            'columns': list(self.df.columns),
            'dtypes': {str(k): str(v) for k, v in self.df.dtypes.to_dict().items()},
            'memory_usage_mb': self.df.memory_usage(deep=True).sum() / 1024 / 1024
        }
        
        if self.use_s3:
            self.metadata['bucket'] = self.bucket_name
            self.metadata['s3_key'] = self.s3_key
    
    def validate_schema(self) -> Tuple[bool, Dict[str, Any]]:
        """Validate schema based on phase-specific requirements"""
        
        expected = set(self.schema_config['expected_columns'])
        actual = set(self.df.columns)
        
        validation_result = {
            'is_valid': True,
            'phase': self.phase,
            'expected_column_count': len(expected),
            'actual_column_count': len(actual),
            'missing_columns': list(expected - actual),
            'extra_columns': list(actual - expected)
        }
        
        # For validation phase, we're strict about schema
        if self.phase == "validation":
            if validation_result['missing_columns'] or validation_result['extra_columns']:
                validation_result['is_valid'] = False
                logger.warning(f"Schema validation failed for phase: {self.phase}")
                if validation_result['missing_columns']:
                    logger.warning(f"Missing columns: {validation_result['missing_columns']}")
                if validation_result['extra_columns']:
                    logger.warning(f"Extra columns: {validation_result['extra_columns']}")
        
        # For statistics phase, we expect the derived columns
        elif self.phase == "statistics":
            # Check if derived columns are present
            derived_cols = set(self.schema_config.get('derived_columns', []))
            missing_derived = derived_cols - actual
            
            if missing_derived:
                validation_result['is_valid'] = False
                validation_result['missing_derived_columns'] = list(missing_derived)
                logger.error(f"Missing derived columns: {missing_derived}")
        
        return validation_result['is_valid'], validation_result
    
    def list_s3_files(self, prefix: Optional[str] = None) -> list:
        """List files in S3 bucket (utility method)"""
        if not self.use_s3:
            raise ValueError("S3 not configured")
        
        try:
            response = self.s3.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix or ''
            )
            
            if 'Contents' in response:
                files = []
                for obj in response['Contents']:
                    files.append({
                        'key': obj['Key'],
                        'size_mb': obj['Size'] / (1024 * 1024),
                        'last_modified': obj['LastModified']
                    })
                return files
            return []
            
        except Exception as e:
            logger.error(f"Error listing S3 files: {e}")
            raise


def load_sec_data(path: Optional[str] = None, 
                  use_s3: bool = False,
                  bucket_name: Optional[str] = None,
                  s3_key: Optional[str] = None,
                  sample: bool = False,
                  phase: Literal["validation", "statistics", "both"] = "both") -> pd.DataFrame:
    """
    Convenience function to load SEC data from local or S3
    
    Args:
        path: Local file path (ignored if use_s3=True)
        use_s3: Whether to load from S3
        bucket_name: S3 bucket name
        s3_key: S3 object key
        sample: Whether to load sample data (will sample from loaded data)
        phase: Which phase we're loading for
    
    Returns:
        DataFrame with SEC filings data
        
    Raises:
        ValueError: If no data source is configured
        FileNotFoundError: If local file doesn't exist
    """
    
    if not use_s3 and not path:
        raise ValueError("Must provide either a file path or S3 configuration")
    
    loader = SECDataLoader(
        data_path=path,
        use_s3=use_s3,
        bucket_name=bucket_name,
        s3_key=s3_key,
        phase=phase
    )
    
    if sample:
        return loader.load_data(sample_size=1000)
    return loader.load_data()

if __name__ == "__main__":
    # Test loading for different phases
    import sys
    
    if len(sys.argv) > 1:
        phase = sys.argv[1]
    else:
        phase = "both"
    
    try:
        # Test for specified phase
        print(f"\nTesting {phase} phase data loading...")
        df = load_sec_data(
            use_s3=True,
            bucket_name='sentence-data-ingestion',
            phase=phase
        )
        print(f"Loaded data: {df.shape}")
        print(f"Columns ({len(df.columns)}): {list(df.columns)}")
        print(df.head())
    except Exception as e:
        print(f"Failed to load data for {phase} phase: {e}")