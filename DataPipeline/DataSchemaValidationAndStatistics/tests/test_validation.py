
"""

Test suite for SEC filings validation

"""

import pytest

import pandas as pd

import numpy as np

from pathlib import Path

import sys

sys.path.append(str(Path(__file__).parent.parent / 'src'))

from data_loader import SECDataLoader

from ge_validator import SECDataSchemaGeneratorGE

from pipeline import SECValidationPipeline

class TestDataLoader:

    """Test data loading functionality"""

    

    def test_create_sample_data(self):

        """Test sample data creation"""

        loader = SECDataLoader()

        df = loader.create_sample_data()

        

        assert len(df) == 30

        assert 'cik_int' in df.columns

        assert 'likely_kpi' in df.columns

    

    def test_schema_validation(self):

        """Test schema validation"""

        loader = SECDataLoader()

        loader.df = loader.create_sample_data()

        

        is_valid, result = loader.validate_schema()

        

        assert isinstance(is_valid, bool)

        assert 'missing_columns' in result

        assert 'extra_columns' in result

class TestGEValidator:

    """Test Great Expectations validator"""

    

    @pytest.fixture

    def validator(self):

        """Create validator instance"""

        return SECDataSchemaGeneratorGE()

    

    @pytest.fixture

    def sample_data(self):

        """Create sample DataFrame"""

        return pd.DataFrame({

            'cik_int': [1234567, 2345678, 3456789],

            'report_year': [2019, 2020, 2021],

            'likely_kpi': ['TRUE', 'FALSE', 'TRUE'],

            'sentence': ['Test sentence 1', 'Test sentence 2', 'Test sentence 3']

        })

    

    def test_load_data(self, validator, sample_data):

        """Test data loading"""

        df = validator.load_data(sample_data)

        assert df.shape == (3, 4)

    

    def test_generate_statistics(self, validator, sample_data):

        """Test statistics generation"""

        validator.load_data(sample_data)

        stats = validator.generate_statistics()

        

        assert 'dataset_info' in stats

        assert 'column_statistics' in stats

        assert stats['dataset_info']['num_rows'] == 3

    

    def test_quality_validation(self, validator, sample_data):

        """Test quality validation"""

        validator.load_data(sample_data)

        report = validator.validate_data_quality()

        

        assert 'quality_score' in report

        assert 'validation_results' in report

        assert report['quality_score'] >= 0

        assert report['quality_score'] <= 100

class TestPipeline:

    """Test complete pipeline"""

    

    def test_pipeline_with_sample(self):

        """Test pipeline with sample data"""

        pipeline = SECValidationPipeline()

        results = pipeline.run(sample_size=10)

        

        assert 'data_loaded' in results

        assert 'quality_report' in results

        assert results['data_loaded']['rows'] == 10

def test_end_to_end():

    """End-to-end integration test"""

    from pipeline import run_validation

    

    results = run_validation(sample=True)

    

    assert results is not None

    assert 'quality_report' in results

    assert 'summary' in results

if __name__ == "__main__":

    pytest.main([__file__, '-v'])

