"""
Main pipeline for SEC filings validation
"""
import logging
from pathlib import Path
from typing import Dict, Any, Optional, Literal
import json
from datetime import datetime
import pandas as pd

from data_loader import SECDataLoader
from ge_validator import SECDataSchemaGeneratorGE
from ge_setup import initialize_great_expectations
from config import OUTPUT_DIR, LOG_DIR, S3_CONFIG, get_schema_for_phase
from email_alerter import EmailAlerter

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'pipeline.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SECValidationPipeline:
    """Main validation pipeline - now supports phase-based execution"""
    
    def __init__(self, data_path: Optional[str] = None, 
                 phase: Literal["validation", "statistics", "both"] = "both"):
        """
        Initialize pipeline with phase selection
        
        Args:
            data_path: Path to data file
            phase: Which phase to run:
                   - "validation": Schema validation only (for raw/merged data)
                   - "statistics": Statistics only (for final data with derived columns)
                   - "both": Full pipeline (backward compatible)
        """
        self.data_path = data_path
        self.phase = phase
        
        # Check if we should use S3 from config
        if S3_CONFIG['enabled'] and not data_path:
            # Use S3 configuration
            self.loader = SECDataLoader(
                use_s3=True,
                bucket_name=S3_CONFIG['bucket_name'],
                s3_key=S3_CONFIG.get(f'{phase}_s3_key', S3_CONFIG.get('s3_key')),
                phase=phase  # Pass phase to loader
            )
            logger.info(f"Using S3 data source for phase {phase}: s3://{S3_CONFIG['bucket_name']}/{self.loader.s3_key}")
        else:
            # Use local file
            self.loader = SECDataLoader(data_path, phase=phase)  # Pass phase to loader
            logger.info(f"Using local data source for phase {phase}: {data_path}")
        
        self.validator = SECDataSchemaGeneratorGE(data_path)
        self.context = initialize_great_expectations()
        self.results = {}
        self.alerter = EmailAlerter()
        
    def run(self, sample_size: Optional[int] = None) -> Dict[str, Any]:
        """Run validation pipeline based on selected phase"""
        
        logger.info("="*60)
        logger.info(f"Starting SEC Filings Pipeline - Phase: {self.phase.upper()}")
        logger.info("="*60)
        
        try:
            # Step 1: Load data
            logger.info("Step 1: Loading data...")
            df = self.loader.load_data(sample_size)
            self.results['data_loaded'] = {
                'rows': len(df),
                'columns': len(df.columns),
                'timestamp': datetime.now().isoformat(),
                'phase': self.phase
            }
            
            # Phase-specific execution
            if self.phase in ["validation", "both"]:
                # Step 2: Validate schema
                logger.info("Step 2: Validating schema...")
                is_valid, schema_validation = self.loader.validate_schema()
                self.results['schema_validation'] = schema_validation

                # Stop if schema is invalid
                if not is_valid:
                    logger.error("="*60)
                    logger.error("SCHEMA VALIDATION FAILED!")
                    logger.error("="*60)
                    if schema_validation['missing_columns']:
                        logger.error(f"Missing columns: {schema_validation['missing_columns']}")
                    if schema_validation['extra_columns']:
                        logger.error(f"Extra columns: {schema_validation['extra_columns']}")
                    
                    # Create failure summary
                    self.results['status'] = 'SCHEMA_FAILED'
                    self.results['error'] = 'Schema validation failed - dataset does not match expected schema'
                    
                    # Generate failure report
                    self._generate_summary()
                    self._send_alert(schema_failure=True)
                    
                    logger.error("Pipeline stopped due to schema validation failure")
                    
                    # For validation phase, this is the end
                    if self.phase == "validation":
                        return self.results
                    
                    # For both phase, we stop here
                    raise ValueError(f"Schema validation failed. Missing columns: {schema_validation['missing_columns']}")
                
                logger.info("✓ Schema validation passed")
                
                # Step 3: Generate expectations (only for validation phase)
                logger.info("Step 3: Generating Great Expectations suite...")
                self.validator.df = df
                expectations = self.validator.generate_schema_expectations()
                self.results['expectations_generated'] = True
                
                # Step 4: Validate quality (critical checks for validation phase)
                logger.info("Step 4: Validating data quality...")
                quality_report = self.validator.validate_data_quality()
                self.results['quality_report'] = quality_report
                
                # If validation phase only, send alert and return
                if self.phase == "validation":
                    self._generate_validation_summary()
                    self._send_validation_alert()
                    logger.info("✓ Validation phase completed")
                    return self.results
            
            # Statistics phase (runs for "statistics" or "both")
            if self.phase in ["statistics", "both"]:
                # For statistics-only phase, skip validation and go straight to stats
                if self.phase == "statistics":
                    logger.info("Running statistics generation on final data...")
                    self.validator.df = df
                
                # Step 5: Compute statistics
                step_num = 5 if self.phase == "both" else 2
                logger.info(f"Step {step_num}: Computing statistics...")
                stats = self.validator.generate_statistics()
                self.results['statistics'] = stats
                
                # Step 6: Export results
                step_num = 6 if self.phase == "both" else 3
                logger.info(f"Step {step_num}: Exporting results...")
                output_dir = OUTPUT_DIR / f"phase_{self.phase}"
                output_dir.mkdir(exist_ok=True)
                output_paths = self.validator.export_results(str(output_dir))
                self.results['output_paths'] = output_paths
                
                # Generate appropriate summary
                if self.phase == "statistics":
                    self._generate_statistics_summary()
                else:
                    self._generate_summary()  # Full summary for "both"
            
            logger.info(f"✓ Pipeline completed successfully - Phase: {self.phase}")

            # Send alert based on phase
            if self.phase == "both" and self.alerter and self.alerter.configured:
                self.alerter.send_validation_alert(self.results)
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            self.results['error'] = str(e)
            raise
        
        return self.results
    
    def _generate_validation_summary(self):
        """Generate summary for validation phase only"""
        summary = {
            'pipeline_run': datetime.now().isoformat(),
            'phase': 'VALIDATION',
            'data_shape': f"{self.results['data_loaded']['rows']:,} × {self.results['data_loaded']['columns']}",
            'schema_valid': self.results['schema_validation']['is_valid'],
            'quality_score': self.results['quality_report']['quality_score'],
            'status': 'PASSED' if self.results['quality_report']['quality_score'] >= 80 else 'FAILED'
        }
        
        self._print_and_save_summary(summary, "VALIDATION PHASE SUMMARY")
    
    def _generate_statistics_summary(self):
        """Generate summary for statistics phase only"""
        summary = {
            'pipeline_run': datetime.now().isoformat(),
            'phase': 'STATISTICS',
            'data_shape': f"{self.results['data_loaded']['rows']:,} × {self.results['data_loaded']['columns']}",
            'total_nulls': self.results['statistics']['data_quality_metrics']['total_null_values'],
            'duplicate_rows': self.results['statistics']['data_quality_metrics']['duplicate_rows']
        }
        
        # Add KPI metrics if available
        if 'kpi_detection_rate' in self.results['statistics'].get('sec_specific_metrics', {}):
            summary['kpi_detection_rate'] = f"{self.results['statistics']['sec_specific_metrics']['kpi_detection_rate']:.1f}%"
        
        self._print_and_save_summary(summary, "STATISTICS PHASE SUMMARY")
    
    def _generate_summary(self):
        """Generate full pipeline summary (backward compatible)"""
        
        # Check if schema validation failed
        if 'status' in self.results and self.results['status'] == 'SCHEMA_FAILED':
            summary = {
                'pipeline_run': datetime.now().isoformat(),
                'phase': self.phase,
                'data_shape': f"{self.results['data_loaded']['rows']:,} × {self.results['data_loaded']['columns']}",
                'schema_valid': self.results['schema_validation']['is_valid'],
                'missing_columns': self.results['schema_validation'].get('missing_columns', []),
                'extra_columns': self.results['schema_validation'].get('extra_columns', []),
                'status': 'SCHEMA_FAILED',
                'error': self.results.get('error', 'Schema validation failed')
            }
        else:
            # Normal summary
            summary = {
                'pipeline_run': datetime.now().isoformat(),
                'phase': self.phase,
                'data_shape': f"{self.results['data_loaded']['rows']:,} × {self.results['data_loaded']['columns']}",
                'schema_valid': self.results.get('schema_validation', {}).get('is_valid', 'N/A'),
                'quality_score': self.results.get('quality_report', {}).get('quality_score', 'N/A'),
                'status': 'PASSED' if self.results.get('quality_report', {}).get('quality_score', 0) >= 80 else 'FAILED'
            }
        
        self._print_and_save_summary(summary, "PIPELINE SUMMARY")
    
    def _print_and_save_summary(self, summary: Dict, title: str):
        """Helper to print and save summary"""
        # Print summary
        print("\n" + "="*60)
        print(title)
        print("="*60)
        for key, value in summary.items():
            print(f"{key:20}: {value}")
        print("="*60)
        
        # Save summary
        summary_path = OUTPUT_DIR / f"pipeline_summary_{self.phase}_{datetime.now():%Y%m%d_%H%M%S}.json"
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2)
        
        self.results['summary'] = summary
    
    def _send_validation_alert(self):
        """Send alert specifically for validation phase"""
        if not self.alerter or not self.alerter.configured:
            logger.info("Email alerts not configured")
            return
        
        quality_score = self.results.get('quality_report', {}).get('quality_score', 0)
        alert_type = "VALIDATION PASSED" if quality_score >= 80 else "VALIDATION FAILED"
        
        logger.info(f"Sending {alert_type} alert (Score: {quality_score:.1f}%)...")
        
        # Add phase information to results
        self.results['alert_phase'] = 'VALIDATION_ONLY'
        
        if self.alerter.send_validation_alert(self.results):
            logger.info(f"✅ {alert_type} alert sent successfully")
        else:
            logger.warning(f"❌ Failed to send {alert_type} alert")

    def _send_alert(self, schema_failure: bool = False, pipeline_error: bool = False):
        """Send email alert based on pipeline results (backward compatible)"""
        
        if not self.alerter or not self.alerter.configured:
            logger.info("Email alerts not configured")
            return
        
        try:
            # Determine alert type
            if schema_failure:
                alert_type = "SCHEMA FAILURE"
                logger.info(f"Sending {alert_type} alert...")
            elif pipeline_error:
                alert_type = "PIPELINE ERROR"
                logger.info(f"Sending {alert_type} alert...")
            else:
                quality_score = self.results.get('quality_report', {}).get('quality_score', 0)
                alert_type = "VALIDATION PASSED" if quality_score >= 80 else "VALIDATION FAILED"
                logger.info(f"Sending {alert_type} alert (Score: {quality_score:.1f}%)...")
            
            # Send email
            if self.alerter.send_validation_alert(self.results):
                logger.info(f"✅ {alert_type} alert sent successfully")
            else:
                logger.warning(f"❌ Failed to send {alert_type} alert")
                
        except Exception as e:
            logger.error(f"Error sending alert: {e}", exc_info=True)

def run_validation(data_path: Optional[str] = None, 
                  sample: bool = False,
                  phase: Literal["validation", "statistics", "both"] = "both"):
    """
    Convenience function to run validation with phase selection
    
    Args:
        data_path: Path to data file
        sample: Whether to use sample data
        phase: Which phase to run
    """
    
    pipeline = SECValidationPipeline(data_path, phase=phase)
    
    if sample:
        # Run with sample data
        results = pipeline.run(sample_size=1000)
    else:
        # Run with full data
        results = pipeline.run()
    
    return results

if __name__ == "__main__":
    import sys
    
    # Parse command line arguments for phase selection
    if len(sys.argv) > 1:
        if sys.argv[1] == "--validation":
            # Run validation only
            data_path = sys.argv[2] if len(sys.argv) > 2 else None
            results = run_validation(data_path, phase="validation")
        elif sys.argv[1] == "--statistics":
            # Run statistics only
            data_path = sys.argv[2] if len(sys.argv) > 2 else None
            results = run_validation(data_path, phase="statistics")
        else:
            # Default: run both
            data_path = sys.argv[1]
            results = run_validation(data_path, phase="both")
    else:
        # Run with default configuration (will use S3 if enabled)
        results = run_validation(phase="both")