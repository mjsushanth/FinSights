#!/usr/bin/env python
"""
Validation Phase Runner - For early DAG step
Validates 20-column merged data and sends pass/fail alert
"""

import sys
import logging
from pathlib import Path
import click

# Add src to path
sys.path.append(str(Path(__file__).parent / 'src'))

from pipeline import SECValidationPipeline
from config import DATA_PATHS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option('--data-path', '-d', help='Override default data path')
@click.option('--use-config', is_flag=True, default=True, help='Use path from config (default: True)')
@click.option('--sample-size', '-n', type=int, help='Sample size for testing')
def main(data_path, use_config, sample_size):
    """
    Run validation phase on 20-column merged data
    
    By default, uses data path from config.py
    """
    
    print("\n" + "="*60)
    print("VALIDATION PHASE - 20 COLUMN SCHEMA CHECK")
    print("="*60 + "\n")
    
    try:
        # Get configuration for validation phase
        validation_config = DATA_PATHS['validation']
        
        # Determine data source
        if data_path:
            # User provided explicit path - use it
            print(f"Using provided data path: {data_path}")
            pipeline = SECValidationPipeline(data_path=data_path, phase='validation')
            
        elif use_config and validation_config['use_s3']:
            # Use S3 from config
            from data_loader import SECDataLoader
            
            bucket = validation_config['s3_bucket']
            key = validation_config['s3_key']
            
            loader = SECDataLoader(
                use_s3=True,
                bucket_name=bucket,
                s3_key=key,
                phase='validation'
            )
            
            print(f"Using S3 from config: s3://{bucket}/{key}")
            pipeline = SECValidationPipeline(data_path=None, phase='validation')
            pipeline.loader = loader
            
        elif use_config:
            # Use local path from config
            local_path = validation_config['local']
            print(f"Using local path from config: {local_path}")
            pipeline = SECValidationPipeline(data_path=str(local_path), phase='validation')
            
        else:
            logger.error("No data source configured. Check config.py DATA_PATHS settings.")
            sys.exit(1)
        
        # Run validation
        print("Running schema validation...")
        results = pipeline.run(sample_size=sample_size)
        
        # Check results
        schema_valid = results.get('schema_validation', {}).get('is_valid', False)
        quality_score = results.get('quality_report', {}).get('quality_score', 0)
        
        print("\n" + "="*60)
        print("VALIDATION RESULTS")
        print("="*60)
        print(f"Schema Valid: {schema_valid}")
        print(f"Expected Columns: 20")
        print(f"Actual Columns: {results.get('data_loaded', {}).get('columns', 0)}")
        print(f"Quality Score: {quality_score:.1f}%")
        
        if not schema_valid:
            missing = results.get('schema_validation', {}).get('missing_columns', [])
            extra = results.get('schema_validation', {}).get('extra_columns', [])
            if missing:
                print(f"Missing Columns: {missing}")
            if extra:
                print(f"Extra Columns: {extra}")
        
        # Determine pass/fail
        passed = schema_valid and quality_score >= 80
        
        print(f"\nValidation Status: {'PASSED ✓' if passed else 'FAILED ✗'}")
        print("="*60)
        
        # Exit with appropriate code for DAG
        sys.exit(0 if passed else 1)
        
    except Exception as e:
        logger.error(f"Validation failed with error: {e}", exc_info=True)
        sys.exit(2)

if __name__ == "__main__":
    main()