"""
Script to download data from S3 bucket in AWS

"""

import os
import sys
from pathlib import Path
from time import time
from datetime import datetime
from typing import List, Dict
import boto3
from dotenv import load_dotenv
import json

# Load environment variables from .env file
if os.path.exists(".env"):
    load_dotenv()

# Add project root to path
project_root = Path(__file__).parent.parent.parent  # Goes up to MLOPS_FINAL
sys.path.insert(0, str(project_root))

from src_legacy_bs4_scraper.aws_utils.s3_client import S3Client
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def download_file(
        s3_client: S3Client,
        bucket_name: str,
        s3_key: str,
        local_path: str = None
    ) -> bool:
    """
    Download a single file from S3
   
    Args:
        s3_client: S3Client instance
        bucket_name: Name of the S3 bucket
        s3_key: S3 object key
        local_path: Local path to save to
    Returns:
        bool: Success status
    """
    try:        
        local_path = Path(local_path)
       
        # Download file
        success = s3_client.download_file(
            bucket_name,
            s3_key,
            str(local_path)
        )       
        return success
       
    except Exception as e:
        logger.error(f"❌ Failed to download {s3_key}: {e}")
        return False

def main():
    # Read configuration from environment variables
    bucket_name = os.getenv("S3_BUCKET_NAME")
    s3_key = os.getenv("S3_CONFIG_FILE_KEY")
    output_path = os.getenv("LOCAL_DATA_PATH") 
    
    # Validate required parameters
    if not bucket_name:
        logger.error("S3_BUCKET_NAME is required in .env file")
        sys.exit(1)
    
    if not s3_key:
        logger.error("S3_CONFIG_FILE_KEY is required in .env file")
        sys.exit(1)

    logger.info(f"Starting S3 download process...")
    logger.info(f"Bucket: {bucket_name}")
    logger.info(f"File Key: {s3_key}")
    
    # AWS connection check
    try:
        session = boto3.Session()
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        
        logger.info(f"Connected to AWS Account: {identity['Account']}")
        logger.info(f"User: {identity['Arn']}")
    except Exception as e:
        logger.error(f"Failed to connect to AWS: {e}")
        logger.error("Please check your AWS credentials in .env file")
        sys.exit(1)
    
    # Initialize S3 client
    s3_client = S3Client()

    # Test connection
    if not s3_client.test_connection():
        logger.error("Failed to connect to S3. Check your credentials in .env file")
        sys.exit(1)
    
    # Check if bucket exists
    if not s3_client.bucket_exists(bucket_name):
        logger.error(f"Bucket {bucket_name} does not exist")
        sys.exit(1)   
       
    # Download file
    logger.info(f"Downloading file: {s3_key}")
    success = download_file(
        s3_client=s3_client,
        bucket_name=bucket_name,
        s3_key=s3_key,
        local_path=output_path
    )
    
    if not success:
        logger.error(f"Failed to download {s3_key}")
        sys.exit(1)       
    
    logger.info("✅ Download process completed successfully")

if __name__ == "__main__":
    main()