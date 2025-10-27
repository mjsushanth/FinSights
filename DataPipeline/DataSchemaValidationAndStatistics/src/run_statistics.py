#!/usr/bin/env python
"""
Statistics Phase Runner - For final DAG step
Generates statistics on 24-column final data with derived columns
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
@click.option('--output-dir', '-o', help='Output directory for reports')
def main(data_path, use_config, sample_size, output_dir):
    """
    Run statistics phase on 24-column final data with derived columns
    
    By default, uses data path from config.py
    """
    
    print("\n" + "="*60)
    print("STATISTICS PHASE - 24 COLUMN FINAL DATA")
    print("="*60 + "\n")
    
    try:
        # Get configuration for statistics phase
        statistics_config = DATA_PATHS['statistics']
        
        # Determine data source
        if data_path:
            # User provided explicit path - use it
            print(f"Using provided data path: {data_path}")
            pipeline = SECValidationPipeline(data_path=data_path, phase='statistics')
            
        elif use_config and statistics_config['use_s3']:
            # Use S3 from config
            from data_loader import SECDataLoader
            
            bucket = statistics_config['s3_bucket']
            key = statistics_config['s3_key']
            
            loader = SECDataLoader(
                use_s3=True,
                bucket_name=bucket,
                s3_key=key,
                phase='statistics'
            )
            
            print(f"Using S3 from config: s3://{bucket}/{key}")
            pipeline = SECValidationPipeline(data_path=None, phase='statistics')
            pipeline.loader = loader
            
        elif use_config:
            # Use local path from config
            local_path = statistics_config['local']
            print(f"Using local path from config: {local_path}")
            pipeline = SECValidationPipeline(data_path=str(local_path), phase='statistics')
            
        else:
            logger.error("No data source configured. Check config.py DATA_PATHS settings.")
            sys.exit(1)
        
        # Run statistics generation
        print("Generating statistics...")
        results = pipeline.run(sample_size=sample_size)
        
        # Extract key statistics
        stats = results.get('statistics', {})
        quality = results.get('quality_report', {})
        data_info = results.get('data_loaded', {})
        
        print("\n" + "="*60)
        print("STATISTICS RESULTS")
        print("="*60)
        print(f"Data Shape: {data_info.get('rows', 0):,} × {data_info.get('columns', 0)}")
        print(f"Expected Columns: 24")
        print(f"Actual Columns: {data_info.get('columns', 0)}")
        
        # Data quality metrics
        quality_metrics = stats.get('data_quality_metrics', {})
        print(f"\nData Quality:")
        print(f"  Total Nulls: {quality_metrics.get('total_null_values', 0):,}")
        print(f"  Duplicate Rows: {quality_metrics.get('duplicate_rows', 0):,}")
        
        # SEC-specific metrics
        sec_metrics = stats.get('sec_specific_metrics', {})
        if 'kpi_detection_rate' in sec_metrics:
            print(f"\nDerived Column Statistics:")
            print(f"  KPI Detection Rate: {sec_metrics['kpi_detection_rate']:.1f}%")
            print(f"  Sentences with Numbers: {sec_metrics.get('sentences_with_numbers', 0):.1f}%")
            print(f"  Sentences with Comparisons: {sec_metrics.get('sentences_with_comparison', 0):.1f}%")
        
        # Report outputs
        output_paths = results.get('output_paths', {})
        if output_paths:
            print(f"\nReports Generated:")
            for report_type, path in output_paths.items():
                print(f"  {report_type}: {path}")
        
        print("\nStatistics Status: COMPLETED ✓")
        print("="*60)
        
        # Always exit successfully for statistics (it's informational)
        sys.exit(0)
        
    except Exception as e:
        logger.error(f"Statistics generation failed with error: {e}", exc_info=True)
        sys.exit(2)

if __name__ == "__main__":
    main()