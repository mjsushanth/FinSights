import boto3
import os
from typing import Optional
from botocore.exceptions import ClientError
import logging
from dotenv import load_dotenv
from pathlib import Path

if os.path.exists(".env"):
    load_dotenv()
    
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class S3Client:
    """Wrapper for AWS S3 operations"""
    
    def __init__(
        self,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: str = "us-east-1",
        profile_name: Optional[str] = None
    ):
        """
        Initialize S3 client with credentials
        
        Args:
            aws_access_key_id: AWS access key (defaults to env variable)
            aws_secret_access_key: AWS secret key (defaults to env variable)
            region_name: AWS region
        """
        self.aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region_name = region_name or os.getenv("AWS_REGION_NAME")
        
        # if profile_name: # For local development with AWS profiles
        #     logger.info(f"Using AWS profile: {profile_name}")
        #     session = boto3.Session(profile_name=profile_name)
        #     self.s3_client = session.client('s3', region_name=region_name)
        #     self.s3_resource = session.resource('s3', region_name=region_name)
        # else:            
        self.aws_access_key_id = aws_access_key_id or os.getenv("AWS_ACCESS_KEY_ID")
        self.aws_secret_access_key = aws_secret_access_key or os.getenv("AWS_SECRET_ACCESS_KEY")
        
    
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name
        )
        
        self.s3_resource = boto3.resource(
            's3',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=self.region_name
        )
    
    def test_connection(self) -> bool:
        """Test S3 connection by listing buckets"""
        try:
            self.s3_client.list_buckets()
            logger.info("✅ Successfully connected to AWS S3")
            return True
        except ClientError as e:
            logger.error(f"❌ Failed to connect to AWS S3: {e}")
            return False
        
    def bucket_exists(self, bucket_name: str) -> bool:
        """Check if bucket exists"""
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            return True
        except ClientError:
            return False
    
    def download_file(
        self,
        bucket_name: str,
        s3_key: str,
        local_path: str,
        create_dirs: bool = True
    ) -> bool:
        """
        Download a single file from S3
        
        Args:
            bucket_name: S3 bucket name
            s3_key: S3 object key (path in bucket)
            local_path: Local file path to save to
            create_dirs: Create parent directories if they don't exist
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            from pathlib import Path
            
            local_path = Path(local_path)
            
            # Create parent directories if needed
            if create_dirs:
                local_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Download file
            self.s3_client.download_file(bucket_name, s3_key, str(local_path))
            
            logger.info(f"✅ Downloaded: s3://{bucket_name}/{s3_key} → {local_path}")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'NoSuchKey':
                logger.error(f"❌ File not found in S3: s3://{bucket_name}/{s3_key}")
            elif error_code == 'NoSuchBucket':
                logger.error(f"❌ Bucket not found: {bucket_name}")
            else:
                logger.error(f"❌ Failed to download {s3_key}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error downloading {s3_key}: {e}")
            return False
        

    def upload_file(self, local_path: str, bucket_name: str, s3_key: str, 
                extra_args: Optional[dict] = None) -> bool:
        """
        Upload a file to S3
        
        Args:
            local_path: Local file path to upload
            bucket_name: S3 bucket name
            s3_key: S3 object key (destination path in bucket)
            extra_args: Optional extra arguments for upload (e.g., ContentType, Metadata)
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Verify local file exists
            if not os.path.exists(local_path):
                logger.error(f"❌ Local file not found: {local_path}")
                return False
            
            file_size = os.path.getsize(local_path)
            logger.info(f"📤 Uploading {local_path} ({file_size / 1024:.2f} KB)")
            logger.info(f"   to s3://{bucket_name}/{s3_key}")
            
            # Upload file
            if extra_args:
                self.s3_client.upload_file(local_path, bucket_name, s3_key, ExtraArgs=extra_args)
            else:
                self.s3_client.upload_file(local_path, bucket_name, s3_key)
            
            logger.info(f"✅ Successfully uploaded to s3://{bucket_name}/{s3_key}")
            return True
            
        except ClientError as e:
            logger.error(f"❌ Upload failed: {e}")
            return False
        except FileNotFoundError:
            logger.error(f"❌ Local file not found: {local_path}")
            return False
        except Exception as e:
            logger.error(f"❌ Unexpected error during upload: {e}")
            return False