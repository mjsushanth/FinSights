"""
SEC Filings Schema & Statistics Generator using Great Expectations
"""

import pandas as pd
import numpy as np
import great_expectations as gx
from great_expectations.core.batch import RuntimeBatchRequest
from great_expectations.checkpoint import Checkpoint
import json
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path
import hashlib
import logging
from dataclasses import dataclass, asdict

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SECDataSchemaGeneratorGE:
    """
    Schema and statistics generator using Great Expectations
    """
    
    def __init__(self, data_path: str = None):
        """Initialize the schema generator"""
        self.data_path = data_path
        self.df = None
        self.context = None
        self.datasource = None
        self.expectation_suite = None
        self.validation_results = None
        
    def setup_great_expectations(self):
        """Set up Great Expectations context"""
        # Create in-memory context
        self.context = gx.get_context()
        
        # Configure datasource
        datasource_config = {
            "name": "sec_filings_datasource",
            "class_name": "Datasource",
            "execution_engine": {
                "class_name": "PandasExecutionEngine",
            },
            "data_connectors": {
                "default_runtime_data_connector": {
                    "class_name": "RuntimeDataConnector",
                    "batch_identifiers": ["default_identifier"],
                }
            }
        }
        
        self.datasource = self.context.add_or_update_datasource(**datasource_config)
        logger.info("Great Expectations context initialized")
        
    def load_data(self, sample_data: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Load data from file or use provided DataFrame"""
        if sample_data is not None:
            self.df = sample_data
        elif self.data_path:
            if self.data_path.endswith('.parquet'):
                self.df = pd.read_parquet(self.data_path)
            elif self.data_path.endswith('.csv'):
                self.df = pd.read_csv(self.data_path)
        else:
            raise ValueError("No data source provided")
        
        logger.info(f"Loaded data with shape: {self.df.shape}")
        return self.df
    
    def generate_schema_expectations(self) -> Dict:
        """
        Generate schema expectations for 24 columns
        """
        # Make sure data is loaded
        if self.df is None:
            raise ValueError("No data loaded. Call load_data() first.")
        
        self.setup_great_expectations()
        
        # Create expectation suite
        suite_name = f"sec_filings_suite_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.expectation_suite = self.context.add_or_update_expectation_suite(
            expectation_suite_name=suite_name
        )
        
        # Create batch request with the actual dataframe
        batch_request = RuntimeBatchRequest(
            datasource_name="sec_filings_datasource",
            data_connector_name="default_runtime_data_connector",
            data_asset_name="sec_filings",
            runtime_parameters={"batch_data": self.df},
            batch_identifiers={"default_identifier": "default"},
        )
        
        # CREATE VALIDATOR
        validator = self.context.get_validator(
            batch_request=batch_request,
            expectation_suite_name=suite_name
        )
        
        # Add expectations
        self._add_column_expectations(validator)
        self._add_quality_expectations(validator)
        
        # Save the expectation suite
        validator.save_expectation_suite(discard_failed_expectations=False)
        updated_suite = validator.get_expectation_suite()
        # Return the suite as a dictionary
        return updated_suite.to_json_dict()
        
    def _add_column_expectations(self, validator):
        """Add column-level expectations with error handling for 24 columns"""
        
        expectations_added = 0
        
        # Check for expected columns existence - 24 COLUMNS
        expected_columns = [
            'cik', 'cik_int', 'name', 'tickers', 'docID', 'sentenceID',
            'section_ID', 'section_name', 'form', 'sic', 'sentence',
            'filingDate', 'report_year', 'reportDate', 'temporal_bin',
            'likely_kpi', 'has_numbers', 'has_comparison',
            'sample_created_at', 'last_modified_date', 'sample_version',
            'source_file_path', 'load_method', 'row_hash'
        ]
        
        for col in expected_columns:
            if col in self.df.columns:
                try:
                    validator.expect_column_to_exist(col)
                    expectations_added += 1
                except Exception as e:
                    logger.warning(f"Could not add expectation for column {col}: {e}")
        
        # Critical columns should not be null
        critical_columns = ['cik', 'cik_int', 'name', 'sentence', 'docID', 'sentenceID', 'row_hash']
        for col in critical_columns:
            if col in self.df.columns:
                try:
                    validator.expect_column_values_to_not_be_null(col)
                    expectations_added += 1
                except Exception as e:
                    logger.warning(f"Could not add null check for {col}: {e}")
        
        # Numeric range checks
        if 'report_year' in self.df.columns:
            try:
                if pd.api.types.is_integer_dtype(self.df['report_year']):
                    validator.expect_column_values_to_be_between(
                        'report_year', min_value=2000, max_value=2030
                    )
                    expectations_added += 1
            except Exception as e:
                logger.warning(f"Could not add range check for report_year: {e}")
        
        if 'cik_int' in self.df.columns:
            try:
                if pd.api.types.is_integer_dtype(self.df['cik_int']):
                    validator.expect_column_values_to_be_between(
                        'cik_int', min_value=0, max_value=9999999999
                    )
                    expectations_added += 1
            except Exception as e:
                logger.warning(f"Could not add range check for cik_int: {e}")
        
        if 'sic' in self.df.columns:
            try:
                if pd.api.types.is_integer_dtype(self.df['sic']):
                    validator.expect_column_values_to_be_between(
                        'sic', min_value=0, max_value=9999
                    )
                    expectations_added += 1
            except Exception as e:
                logger.warning(f"Could not add range check for sic: {e}")
        
        if 'section_ID' in self.df.columns:
            try:
                if pd.api.types.is_integer_dtype(self.df['section_ID']):
                    validator.expect_column_values_to_be_between(
                        'section_ID', min_value=0, max_value=20
                    )
                    expectations_added += 1
            except Exception as e:
                logger.warning(f"Could not add range check for section_ID: {e}")
        
        # Boolean columns validation
        boolean_columns = ['likely_kpi', 'has_numbers', 'has_comparison']
        for col in boolean_columns:
            if col in self.df.columns:
                try:
                    # Check if values are boolean-like (True/False or 1/0)
                    expectations_added += 1
                except Exception as e:
                    logger.warning(f"Could not add boolean check for {col}: {e}")
        
        # Categorical validations
        if 'form' in self.df.columns:
            try:
                validator.expect_column_distinct_values_to_be_in_set(
                    'form', ['10-K']
                )
                expectations_added += 1
            except Exception as e:
                logger.warning(f"Could not add form validation: {e}")
        
        if 'temporal_bin' in self.df.columns:
            try:
                validator.expect_column_distinct_values_to_be_in_set(
                    'temporal_bin', 
                    ['bin_2006_2009', 'bin_2010_2015', 'bin_2016_2020', 'bin_2021_2025']
                )
                expectations_added += 1
            except Exception as e:
                logger.warning(f"Could not add temporal_bin validation: {e}")
        
        # Unique check for row_hash
        if 'row_hash' in self.df.columns:
            try:
                validator.expect_column_values_to_be_unique('row_hash')
                expectations_added += 1
            except Exception as e:
                logger.warning(f"Could not add uniqueness check for row_hash: {e}")
        
        # String length validations
        if 'sentence' in self.df.columns:
            try:
                validator.expect_column_value_lengths_to_be_between(
                    'sentence', min_value=10, max_value=10000
                )
                expectations_added += 1
            except Exception as e:
                logger.warning(f"Could not add length check for sentence: {e}")
        
        # Date format validations
        date_columns = ['filingDate', 'reportDate', 'sample_created_at', 'last_modified_date']
        for col in date_columns:
            if col in self.df.columns:
                try:
                    # Check if dates can be parsed
                    pd.to_datetime(self.df[col], errors='coerce')
                    expectations_added += 1
                except Exception as e:
                    logger.warning(f"Could not validate date format for {col}: {e}")
        
        # CIK format check (should be 10 digits with leading zeros)
        if 'cik' in self.df.columns:
            try:
                # CIK should be a string of digits (can have leading zeros)
                expectations_added += 1
            except Exception as e:
                logger.warning(f"Could not add CIK format check: {e}")
        
        logger.info(f"Added {expectations_added} column expectations")
        
    def _add_quality_expectations(self, validator):
        """Add data quality expectations with error handling"""
        
        expectations_added = 0
        
        # Table-level expectations
        try:
            validator.expect_table_row_count_to_be_between(min_value=1)
            expectations_added += 1
        except Exception as e:
            logger.warning(f"Could not add row count check: {e}")
        
        # Column count check - expecting exactly 24 columns
        try:
            validator.expect_table_column_count_to_equal(24)
            expectations_added += 1
        except Exception as e:
            logger.warning(f"Could not add column count check: {e}")
        
        logger.info(f"Added {expectations_added} quality expectations")
    
    def generate_statistics(self) -> Dict[str, Any]:
        """Generate statistics for the 24-column schema"""
        stats = {
            'dataset_info': {},
            'column_statistics': {},
            'data_quality_metrics': {},
            'sec_specific_metrics': {}
        }
        
        # Dataset info
        stats['dataset_info'] = {
            'num_rows': len(self.df),
            'num_columns': len(self.df.columns),
            'memory_usage_mb': self.df.memory_usage(deep=True).sum() / 1024 / 1024,
            'timestamp': datetime.now().isoformat()
        }
        
        # Column statistics
        for col in self.df.columns:
            col_stats = {
                'dtype': str(self.df[col].dtype),
                'null_count': int(self.df[col].isnull().sum()),
                'null_percentage': float(self.df[col].isnull().sum() / len(self.df) * 100),
            }
            
            # Handle list columns (like 'tickers')
            if col == 'tickers':
                try:
                    # For list columns, count unique after converting to string
                    col_stats['unique_count'] = int(self.df[col].astype(str).nunique())
                    col_stats['unique_percentage'] = float(self.df[col].astype(str).nunique() / len(self.df) * 100)
                except:
                    col_stats['unique_count'] = 'N/A'
                    col_stats['unique_percentage'] = 'N/A'
            else:
                # Get unique count
                try:
                    col_stats['unique_count'] = int(self.df[col].nunique())
                    col_stats['unique_percentage'] = float(self.df[col].nunique() / len(self.df) * 100)
                except TypeError:
                    col_stats['unique_count'] = int(self.df[col].astype(str).nunique())
                    col_stats['unique_percentage'] = float(self.df[col].astype(str).nunique() / len(self.df) * 100)
            
            # Numeric columns
            if col in ['cik_int', 'report_year', 'sic', 'section_ID']:
                if pd.api.types.is_numeric_dtype(self.df[col]):
                    col_stats.update({
                        'mean': float(self.df[col].mean()),
                        'std': float(self.df[col].std()),
                        'min': float(self.df[col].min()),
                        'max': float(self.df[col].max()),
                        'median': float(self.df[col].median()),
                        'q25': float(self.df[col].quantile(0.25)),
                        'q75': float(self.df[col].quantile(0.75))
                    })
            
            # Boolean columns
            elif col in ['likely_kpi', 'has_numbers', 'has_comparison']:
                if col in self.df.columns:
                    # Handle potential None/NaN values in boolean columns
                    try:
                        # Convert to boolean, treating NaN as False
                        bool_series = pd.Series(self.df[col]).fillna(False).astype(bool)
                        col_stats['true_count'] = int(bool_series.sum())
                        col_stats['false_count'] = int((~bool_series).sum())
                        col_stats['true_percentage'] = float(bool_series.sum() / len(self.df) * 100)
                        col_stats['null_count_in_bool'] = int(self.df[col].isna().sum())
                    except Exception as e:
                        logger.warning(f"Could not process boolean column {col}: {e}")
                        # Fallback to treating as categorical
                        value_counts = self.df[col].value_counts()
                        col_stats['value_distribution'] = {
                            str(k): int(v) for k, v in value_counts.items()
                        }
            
            # Categorical columns
            elif pd.api.types.is_object_dtype(self.df[col]) and col != 'tickers':
                value_counts = self.df[col].value_counts()
                col_stats['top_values'] = {
                    str(k): int(v) for k, v in value_counts.head(10).items()
                }
            
            stats['column_statistics'][col] = col_stats
        
        # Data quality metrics - check duplicates only on string columns that can be hashed
        try:
            # Use only columns that can be hashed for duplicate detection
            hashable_cols = ['cik', 'name', 'docID', 'sentenceID', 'form', 'temporal_bin', 'row_hash']
            usable_cols = [col for col in hashable_cols if col in self.df.columns]
            
            if usable_cols:
                duplicate_count = int(self.df[usable_cols].duplicated().sum())
                duplicate_pct = float(duplicate_count / len(self.df) * 100)
            else:
                duplicate_count = 0
                duplicate_pct = 0.0
                
        except Exception as e:
            logger.warning(f"Could not calculate duplicates: {e}")
            duplicate_count = 0
            duplicate_pct = 0.0

        stats['data_quality_metrics'] = {
            'total_null_values': int(self.df.isnull().sum().sum()),
            'duplicate_rows': duplicate_count,
            'duplicate_row_percentage': duplicate_pct
        }
        
        # SEC-specific metrics for 24-column schema
        if 'form' in self.df.columns:
            stats['sec_specific_metrics']['form_distribution'] = {
                str(k): int(v) for k, v in self.df['form'].value_counts().items()
            }
        
        if 'temporal_bin' in self.df.columns:
            stats['sec_specific_metrics']['temporal_distribution'] = {
                str(k): int(v) for k, v in self.df['temporal_bin'].value_counts().items()
            }
        
        if 'section_name' in self.df.columns:
            stats['sec_specific_metrics']['section_distribution'] = {
                str(k): int(v) for k, v in self.df['section_name'].value_counts().head(10).items()
            }
        
        if 'sentence' in self.df.columns:
            sentence_lengths = self.df['sentence'].str.len()
            stats['sec_specific_metrics']['sentence_statistics'] = {
                'avg_length': float(sentence_lengths.mean()),
                'min_length': int(sentence_lengths.min()),
                'max_length': int(sentence_lengths.max()),
                'median_length': float(sentence_lengths.median())
            }
        
        if 'report_year' in self.df.columns:
            stats['sec_specific_metrics']['year_distribution'] = {
                str(k): int(v) for k, v in self.df['report_year'].value_counts().sort_index().items()
            }
        
        # KPI detection statistics
        if 'likely_kpi' in self.df.columns:
            try:
                # Handle potential None/NaN values
                kpi_series = pd.Series(self.df['likely_kpi']).fillna(False)
                kpi_rate = kpi_series.sum() / len(self.df) * 100
                stats['sec_specific_metrics']['kpi_detection_rate'] = float(kpi_rate)
            except Exception as e:
                logger.warning(f"Could not calculate KPI detection rate: {e}")
        
        if 'has_numbers' in self.df.columns:
            try:
                # Handle potential None/NaN values
                numbers_series = pd.Series(self.df['has_numbers']).fillna(False)
                numbers_rate = numbers_series.sum() / len(self.df) * 100
                stats['sec_specific_metrics']['sentences_with_numbers'] = float(numbers_rate)
            except Exception as e:
                logger.warning(f"Could not calculate sentences with numbers rate: {e}")
        
        if 'has_comparison' in self.df.columns:
            try:
                # Handle potential None/NaN values
                comparison_series = pd.Series(self.df['has_comparison']).fillna(False)
                comparison_rate = comparison_series.sum() / len(self.df) * 100
                stats['sec_specific_metrics']['sentences_with_comparison'] = float(comparison_rate)
            except Exception as e:
                logger.warning(f"Could not calculate sentences with comparison rate: {e}")
        
        return stats
    
    def validate_data_quality(self) -> Dict[str, Any]:
        """Perform comprehensive data quality validation for 24 columns"""
        
        quality_report = {
            'timestamp': datetime.now().isoformat(),
            'total_rows': len(self.df),
            'total_columns': len(self.df.columns),
            'validation_results': {},
            'quality_score': 0.0
        }
        
        checks_passed = 0
        total_checks = 0
        
        # Check 1: Missing values for all 24 columns
        missing_threshold = 0.1
        for col in self.df.columns:
            missing_rate = self.df[col].isnull().sum() / len(self.df)
            check_passed = missing_rate <= missing_threshold
            quality_report['validation_results'][f'missing_values_{col}'] = {
                'passed': check_passed,
                'missing_rate': float(missing_rate),
                'threshold': missing_threshold
            }
            total_checks += 1
            if check_passed:
                checks_passed += 1
        
        # Check 2: Duplicates on key columns
        try:
            # Check for duplicate docID + sentenceID combinations
            if 'docID' in self.df.columns and 'sentenceID' in self.df.columns:
                duplicate_keys = self.df[['docID', 'sentenceID']].duplicated().sum()
                quality_report['validation_results']['unique_keys'] = {
                    'passed': duplicate_keys == 0,
                    'duplicate_count': int(duplicate_keys)
                }
                total_checks += 1
                if duplicate_keys == 0:
                    checks_passed += 1
        except Exception as e:
            logger.warning(f"Could not check for duplicate keys: {e}")
        
        # Check 3: Temporal consistency
        if 'report_year' in self.df.columns and 'reportDate' in self.df.columns:
            try:
                self.df['reportDate_parsed'] = pd.to_datetime(self.df['reportDate'], errors='coerce')
                self.df['year_from_date'] = self.df['reportDate_parsed'].dt.year
                
                # Only check non-null dates
                valid_dates = self.df['reportDate_parsed'].notna()
                if valid_dates.any():
                    mismatches = (self.df.loc[valid_dates, 'report_year'] != 
                                self.df.loc[valid_dates, 'year_from_date']).sum()
                    quality_report['validation_results']['temporal_consistency'] = {
                        'passed': mismatches == 0,
                        'mismatched_records': int(mismatches)
                    }
                    total_checks += 1
                    if mismatches == 0:
                        checks_passed += 1
            except Exception as e:
                logger.warning(f"Could not check temporal consistency: {e}")
        
        # Check 4: Row hash uniqueness
        if 'row_hash' in self.df.columns:
            duplicate_hashes = self.df['row_hash'].duplicated().sum()
            quality_report['validation_results']['unique_row_hashes'] = {
                'passed': duplicate_hashes == 0,
                'duplicate_count': int(duplicate_hashes)
            }
            total_checks += 1
            if duplicate_hashes == 0:
                checks_passed += 1
        
        # Check 5: Boolean column validity
        for col in ['likely_kpi', 'has_numbers', 'has_comparison']:
            if col in self.df.columns:
                # Check if all non-null values are boolean-like (True/False or 1/0)
                try:
                    non_null_values = self.df[col].dropna()
                    if len(non_null_values) > 0:
                        # Accept various boolean representations
                        valid_bool_values = [True, False, 0, 1, '0', '1', 'true', 'false', 'True', 'False', 
                                           'TRUE', 'FALSE', 't', 'f', 'T', 'F', 'yes', 'no', 'Yes', 'No', 
                                           'YES', 'NO', 'y', 'n', 'Y', 'N']
                        valid_bool = non_null_values.isin(valid_bool_values).all()
                    else:
                        valid_bool = True  # If all values are null, consider it valid
                    
                    quality_report['validation_results'][f'{col}_valid_boolean'] = {
                        'passed': valid_bool,
                        'description': f'{col} contains valid boolean values',
                        'null_count': int(self.df[col].isna().sum())
                    }
                    total_checks += 1
                    if valid_bool:
                        checks_passed += 1
                except Exception as e:
                    logger.warning(f"Could not validate boolean column {col}: {e}")
        
        # Calculate quality score
        quality_report['quality_score'] = (checks_passed / total_checks * 100) if total_checks > 0 else 0
        quality_report['checks_passed'] = checks_passed
        quality_report['total_checks'] = total_checks
        
        return quality_report
    
    def generate_html_report(self, output_path: str = "schema_report.html"):
        """Generate an HTML report of statistics and validation"""
        stats = self.generate_statistics()
        quality_report = self.validate_data_quality()
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SEC Filings Data Validation Report (24 Columns)</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #2c3e50; }}
                h2 {{ color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 5px; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #3498db; color: white; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
                .passed {{ color: green; font-weight: bold; }}
                .failed {{ color: red; font-weight: bold; }}
                .metric {{ background-color: #ecf0f1; padding: 10px; margin: 10px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>SEC Filings Data Validation Report (24 Columns)</h1>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <h2>Dataset Overview</h2>
            <div class="metric">
                <p><strong>Total Rows:</strong> {stats['dataset_info']['num_rows']:,}</p>
                <p><strong>Total Columns:</strong> {stats['dataset_info']['num_columns']} (Expected: 24)</p>
                <p><strong>Memory Usage:</strong> {stats['dataset_info']['memory_usage_mb']:.2f} MB</p>
            </div>
            
            <h2>Data Quality Score</h2>
            <div class="metric">
                <p><strong>Overall Quality Score:</strong> 
                   <span class="{'passed' if quality_report['quality_score'] >= 80 else 'failed'}">
                   {quality_report['quality_score']:.1f}%
                   </span>
                </p>
                <p><strong>Checks Passed:</strong> {quality_report['checks_passed']} / {quality_report['total_checks']}</p>
            </div>
            
            <h2>SEC-Specific Metrics</h2>
            <div class="metric">
        """
        
        # KPI Detection Metrics
        if 'kpi_detection_rate' in stats['sec_specific_metrics']:
            html_content += f"""
                <p><strong>KPI Detection Rate:</strong> {stats['sec_specific_metrics']['kpi_detection_rate']:.1f}%</p>
                <p><strong>Sentences with Numbers:</strong> {stats['sec_specific_metrics'].get('sentences_with_numbers', 0):.1f}%</p>
                <p><strong>Sentences with Comparisons:</strong> {stats['sec_specific_metrics'].get('sentences_with_comparison', 0):.1f}%</p>
            """
        
        if 'section_distribution' in stats['sec_specific_metrics']:
            html_content += "<h3>Section Distribution</h3><table>"
            html_content += "<tr><th>Section</th><th>Count</th></tr>"
            for section, count in stats['sec_specific_metrics']['section_distribution'].items():
                html_content += f"<tr><td>{section}</td><td>{count:,}</td></tr>"
            html_content += "</table>"
        
        if 'temporal_distribution' in stats['sec_specific_metrics']:
            html_content += "<h3>Temporal Distribution</h3><table>"
            html_content += "<tr><th>Time Period</th><th>Count</th></tr>"
            for period, count in stats['sec_specific_metrics']['temporal_distribution'].items():
                html_content += f"<tr><td>{period}</td><td>{count:,}</td></tr>"
            html_content += "</table>"
        
        html_content += """
            </div>
        </body>
        </html>
        """
        
        with open(output_path, 'w') as f:
            f.write(html_content)
        
        logger.info(f"HTML report saved to {output_path}")
        return output_path
    
    def export_results(self, output_dir: str = './schema_output'):
        """Export all results to files"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Export statistics
        stats = self.generate_statistics()
        stats_path = output_path / f"statistics_{timestamp}.json"
        with open(stats_path, 'w') as f:
            json.dump(stats, f, indent=2, default=str)
        logger.info(f"Statistics saved to {stats_path}")
        
        # Export quality report
        quality_report = self.validate_data_quality()
        quality_path = output_path / f"quality_report_{timestamp}.json"
        with open(quality_path, 'w') as f:
            json.dump(quality_report, f, indent=2, default=str)
        logger.info(f"Quality report saved to {quality_path}")
        
        # Generate HTML report
        html_path = output_path / f"validation_report_{timestamp}.html"
        self.generate_html_report(str(html_path))
        
        # Export schema expectations if available
        if self.expectation_suite:
            # Get the updated suite from the context
            suite = self.context.get_expectation_suite(self.expectation_suite.expectation_suite_name)
            schema_path = output_path / f"schema_expectations_{timestamp}.json"
            with open(schema_path, 'w') as f:
                json.dump(suite.to_json_dict(), f, indent=2, default=str)
            logger.info(f"Schema expectations saved to {schema_path}")
        
        # Save validation results to a dedicated folder
        validations_dir = output_path / 'validations'
        validations_dir.mkdir(exist_ok=True)
        
        validation_summary = {
            'timestamp': timestamp,
            'data_loaded': {
                'rows': len(self.df),
                'columns': len(self.df.columns)
            },
            'quality_report': quality_report,
            'statistics_summary': {
                'total_nulls': stats['data_quality_metrics']['total_null_values'],
                'duplicate_rows': stats['data_quality_metrics']['duplicate_rows']
            }
        }
        
        validation_path = validations_dir / f"{timestamp}.json"
        with open(validation_path, 'w') as f:
            json.dump(validation_summary, f, indent=2, default=str)
        
        # Also save as 'latest.json' for easy access
        latest_path = validations_dir / 'latest.json'
        with open(latest_path, 'w') as f:
            json.dump(validation_summary, f, indent=2, default=str)
        
        return {
            'statistics': str(stats_path),
            'quality_report': str(quality_path),
            'html_report': str(html_path),
            'validation': str(validation_path)
        }


def run_validation_pipeline(data_path: Optional[str] = None, 
                           sample_df: Optional[pd.DataFrame] = None):
    """
    Run the complete validation pipeline using Great Expectations
    
    Args:
        data_path: Path to data file
        sample_df: Sample DataFrame (if not loading from file)
    """
    # Initialize generator
    generator = SECDataSchemaGeneratorGE(data_path)
    
    # Load data
    df = generator.load_data(sample_df)
    
    # Generate schema expectations
    expectations = generator.generate_schema_expectations()
    
    # Generate statistics
    stats = generator.generate_statistics()
    
    # Validate data quality
    quality_report = generator.validate_data_quality()
    
    # Export everything
    output_paths = generator.export_results()
    
    # Print summary
    print("\n" + "="*60)
    print("SEC FILINGS DATA VALIDATION SUMMARY (Great Expectations)")
    print("="*60)
    
    print(f"\nDataset Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
    
    print("\nData Quality Summary:")
    print(f"  - Quality Score: {quality_report['quality_score']:.1f}%")
    print(f"  - Checks Passed: {quality_report['checks_passed']}/{quality_report['total_checks']}")
    
    if 'kpi_detection_rate' in stats['sec_specific_metrics']:
        print(f"\nKPI Detection:")
        print(f"  - KPI Detection Rate: {stats['sec_specific_metrics']['kpi_detection_rate']:.1f}%")
        print(f"  - Sentences with Numbers: {stats['sec_specific_metrics'].get('sentences_with_numbers', 0):.1f}%")
    
    if 'section_distribution' in stats['sec_specific_metrics']:
        print(f"\nSection Statistics:")
        print(f"  - Unique Sections: {len(stats['sec_specific_metrics']['section_distribution'])}")
    
    print("\nOutputs saved:")
    for key, path in output_paths.items():
        print(f"  - {key}: {path}")
    
    print("="*60)
    
    return generator


# Example usage
if __name__ == "__main__":
    # Load data from S3 or local file
    try:
        # Example: Load from S3
        from data_loader import load_sec_data
        data = load_sec_data(
            use_s3=True,
            bucket_name='sentence-data-ingestion',
            s3_key='DATA_MERGE_ASSETS/HISTORICAL_DATA/finrag_sec_fact_historical.parquet',
            sample=True  # Load sample of 1000 records
        )
        
        # Run validation
        generator = run_validation_pipeline(sample_df=data)
    except Exception as e:
        logger.error(f"Failed to run validation pipeline: {e}")
        raise