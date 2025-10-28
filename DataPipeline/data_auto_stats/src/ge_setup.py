"""
Great Expectations setup and configuration
"""
import great_expectations as gx
from great_expectations.data_context.types.base import DataContextConfig
from great_expectations.core.batch import RuntimeBatchRequest
from pathlib import Path
import yaml
import logging
from typing import Dict, Any

from config import GE_DIR, GE_CONFIG_PATH, SEC_SCHEMA_CONFIG

logger = logging.getLogger(__name__)

def setup_great_expectations_config():
    """Setup Great Expectations configuration"""
    
    ge_config = {
        'config_version': 3.0,
        'datasources': {
            'sec_filings_datasource': {
                'class_name': 'Datasource',
                'module_name': 'great_expectations.datasource',
                'execution_engine': {
                    'class_name': 'PandasExecutionEngine',
                    'module_name': 'great_expectations.execution_engine'
                },
                'data_connectors': {
                    'runtime_data_connector': {
                        'class_name': 'RuntimeDataConnector',
                        'module_name': 'great_expectations.datasource.data_connector',
                        'batch_identifiers': ['run_id']
                    },
                    'filesystem_data_connector': {
                        'class_name': 'InferredAssetFilesystemDataConnector',
                        'module_name': 'great_expectations.datasource.data_connector',
                        'base_directory': str(Path('data/raw').absolute()),
                        'default_regex': {
                            'group_names': ['data_asset_name'],
                            'pattern': '(.*)\.parquet'
                        }
                    }
                }
            }
        },
        'stores': {
            'expectations_store': {
                'class_name': 'ExpectationsStore',
                'store_backend': {
                    'class_name': 'TupleFilesystemStoreBackend',
                    'base_directory': str(GE_DIR / 'expectations')
                }
            },
            'validations_store': {
                'class_name': 'ValidationsStore',
                'store_backend': {
                    'class_name': 'TupleFilesystemStoreBackend',
                    'base_directory': str(GE_DIR / 'uncommitted/validations')
                }
            },
            'evaluation_parameter_store': {
                'class_name': 'EvaluationParameterStore'
            },
            'checkpoint_store': {
                'class_name': 'CheckpointStore',
                'store_backend': {
                    'class_name': 'TupleFilesystemStoreBackend',
                    'base_directory': str(GE_DIR / 'checkpoints')
                }
            }
        },
        'expectations_store_name': 'expectations_store',
        'validations_store_name': 'validations_store',
        'evaluation_parameter_store_name': 'evaluation_parameter_store',
        'checkpoint_store_name': 'checkpoint_store',
        'data_docs_sites': {
            'local_site': {
                'class_name': 'SiteBuilder',
                'store_backend': {
                    'class_name': 'TupleFilesystemStoreBackend',
                    'base_directory': str(GE_DIR / 'uncommitted/data_docs/local_site')
                },
                'site_index_builder': {
                    'class_name': 'DefaultSiteIndexBuilder'
                }
            }
        }
    }
    
    # Create directories
    GE_DIR.mkdir(exist_ok=True)
    (GE_DIR / 'expectations').mkdir(exist_ok=True)
    (GE_DIR / 'checkpoints').mkdir(exist_ok=True)
    (GE_DIR / 'uncommitted').mkdir(exist_ok=True)
    
    # Save configuration
    with open(GE_CONFIG_PATH, 'w') as f:
        yaml.dump(ge_config, f, default_flow_style=False)
    
    logger.info(f"Great Expectations config saved to {GE_CONFIG_PATH}")
    return ge_config

def create_sec_expectations_suite(context: gx.DataContext) -> Dict[str, Any]:
    """Create SEC filings specific expectation suite - UPDATED FOR NEW SCHEMA"""
    
    suite_name = "sec_filings_expectations"
    
    # Create or update expectation suite
    suite = context.add_or_update_expectation_suite(
        expectation_suite_name=suite_name
    )
    
    expectations_config = {
        'suite_name': suite_name,
        'expectations': []
    }
    
    # Column existence expectations - NEW 20 COLUMNS
    for col in SEC_SCHEMA_CONFIG['expected_columns']:
        expectations_config['expectations'].append({
            'expectation_type': 'expect_column_to_exist',
            'kwargs': {'column': col}
        })
    
    # Numeric column expectations
    for col, bounds in SEC_SCHEMA_CONFIG['numeric_columns'].items():
        expectations_config['expectations'].extend([
            {
                'expectation_type': 'expect_column_values_to_be_between',
                'kwargs': {
                    'column': col,
                    'min_value': bounds['min'],
                    'max_value': bounds['max']
                }
            },
            {
                'expectation_type': 'expect_column_values_to_not_be_null',
                'kwargs': {'column': col}
            }
        ])
    
    # Categorical column expectations
    for col, values in SEC_SCHEMA_CONFIG['categorical_columns'].items():
        if values:  # Only add if there are expected values
            expectations_config['expectations'].append({
                'expectation_type': 'expect_column_values_to_be_in_set',
                'kwargs': {
                    'column': col,
                    'value_set': values,
                    'mostly': 0.95  # Allow for some flexibility
                }
            })
    
    # Identifier columns should not be null
    for col in SEC_SCHEMA_CONFIG['identifier_columns']:
        expectations_config['expectations'].append({
            'expectation_type': 'expect_column_values_to_not_be_null',
            'kwargs': {'column': col}
        })
    
    # Text column length expectations
    for col, constraints in SEC_SCHEMA_CONFIG['text_columns'].items():
        expectations_config['expectations'].append({
            'expectation_type': 'expect_column_value_lengths_to_be_between',
            'kwargs': {
                'column': col,
                'min_value': constraints['min_length'],
                'max_value': constraints['max_length']
            }
        })
    
    return expectations_config

def initialize_great_expectations() -> gx.DataContext:
    """Initialize Great Expectations context"""
    
    # Setup configuration
    setup_great_expectations_config()
    
    # Create context
    context = gx.get_context(context_root_dir=str(GE_DIR))
    
    # Create expectations suite
    create_sec_expectations_suite(context)
    
    logger.info("Great Expectations initialized successfully")
    return context

if __name__ == "__main__":
    context = initialize_great_expectations()
    print(f"✓ Great Expectations context created at {GE_DIR}")