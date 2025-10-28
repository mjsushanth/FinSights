"""
Tests for AWS S3 operations
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from botocore.exceptions import ClientError
import os
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.aws_utils.s3_client import S3Client


class TestS3Client:
    """Core S3Client tests"""
    
    @pytest.fixture
    def mock_s3_client(self):
        with patch('boto3.client'), patch('boto3.resource'):
            with patch.dict(os.environ, {
                'AWS_ACCESS_KEY_ID': 'test_key',
                'AWS_SECRET_ACCESS_KEY': 'test_secret',
                'AWS_REGION_NAME': 'us-east-1'
            }):
                client = S3Client()
                client.s3_client = MagicMock()
                client.s3_resource = MagicMock()
                return client
    
    def test_connection_success(self, mock_s3_client):
        """Test successful S3 connection"""
        mock_s3_client.s3_client.list_buckets.return_value = {'Buckets': []}
        
        assert mock_s3_client.test_connection() is True
        mock_s3_client.s3_client.list_buckets.assert_called_once()
    
    
    def test_bucket_exists(self, mock_s3_client):
        """Test bucket existence check"""
        mock_s3_client.s3_client.head_bucket.return_value = {}
        
        assert mock_s3_client.bucket_exists('test-bucket') is True
        mock_s3_client.s3_client.head_bucket.assert_called_with(Bucket='test-bucket')   


class TestDownloadScript:
    """Tests for download_from_s3.py"""
    
    @pytest.fixture
    def mock_env(self):
        """Mock environment variables"""
        return {
            'S3_BUCKET_NAME': 'test-bucket',
            'S3_CONFIG_FILE_KEY': 'config.json',
            'LOCAL_DATA_PATH': '/tmp/data.json'
        }
    
    @patch('src.download_from_s3.S3Client')
    def test_download_function(self, mock_client_class):
        """Test download_file function"""
        from src.download_from_s3 import download_file
        
        mock_client = MagicMock()
        mock_client.download_file.return_value = True
        
        result = download_file(mock_client, 'bucket', 'key', '/tmp/file')
        
        assert result is True
        mock_client.download_file.assert_called_once()


class TestUploadScript:
    """Tests for upload_to_s3.py"""
    
    def test_get_files_to_upload(self, tmp_path):        
        from src.upload_to_s3 import get_files_to_upload
        
        # Create test structure
        csv_dir = tmp_path / "datasets" / "CSV_FILES"
        csv_dir.mkdir(parents=True)
        (csv_dir / "test.csv").write_text("data")
        
        files = get_files_to_upload(tmp_path)
        
        assert len(files["CSV-FILES"]) == 1
        assert files["CSV-FILES"][0].name == "test.csv"
    
    def test_upload_file_success(self, tmp_path):
        """Test single file upload"""
        from src.upload_to_s3 import upload_file_to_s3
        
        test_file = tmp_path / "test.csv"
        test_file.write_text("data")
        
        mock_client = MagicMock()
        mock_client.upload_file.return_value = True
        
        success, key = upload_file_to_s3(
            mock_client, test_file, 'bucket', 'prefix', 'CSV-FILES'
        )
        
        assert success is True
        assert key == 'prefix/CSV-FILES/test.csv'


# Run with: pytest tests/test_aws_s3.py -v