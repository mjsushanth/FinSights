"""
Script to upload data to S3 bucket in AWS
Uploads CSV files, Parquet files, and merged files from different locations
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
import boto3
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
if os.path.exists(".env"):
    load_dotenv()

# Add project root to path
project_root = Path(__file__).parent.parent.parent  # Goes up to project root
sys.path.insert(0, str(project_root))

from src.aws_utils.s3_client import S3Client

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_files_to_upload(base_dir: Path) -> Dict[str, List[Path]]:
    """
    Collect all files to upload from different locations
    
    Args:
        base_dir: Base directory (AIRFLOW_HOME or project root)
        
    Returns:
        Dictionary with categories and their file paths
    """
    datasets_dir = base_dir / "datasets"
    
    files_to_upload = {
        "CSV-FILES": [],
        "PARQUET-FILES": [],
        "MERGED-SETS": [],
        "EXTRACTED-JSON": []
    }
    
    # Collect CSV files from CSV_FILES directory
    csv_dir = datasets_dir / "CSV_FILES"
    if csv_dir.exists():
        files_to_upload["CSV-FILES"] = list(csv_dir.glob("*.csv"))
        logger.info(f"Found {len(files_to_upload['CSV-FILES'])} CSV files")

    # Collect Parquet files from PARQUET_FILES directory
    parquet_dir = datasets_dir / "PARQUET_FILES"
    if parquet_dir.exists():
        files_to_upload["PARQUET-FILES"] = list(parquet_dir.glob("*.parquet"))
        logger.info(f"Found {len(files_to_upload['PARQUET-FILES'])} Parquet files")
    
    # Collect merged files (both CSV and Parquet)
    merged_dir = datasets_dir / "MERGED_EXTRACTED_FILINGS"
    if merged_dir.exists():
        merged_csv = list(merged_dir.glob("*.csv"))
        merged_parquet = list(merged_dir.glob("*.parquet"))
        files_to_upload["MERGED-SETS"] = merged_csv + merged_parquet
        logger.info(f"Found {len(files_to_upload['MERGED-SETS'])} merged files")
    
    # Collect extracted JSON files (optional)
    extracted_dir = datasets_dir / "EXTRACTED_FILINGS" / "10-K"
    if extracted_dir.exists():
        files_to_upload["EXTRACTED-JSON"] = list(extracted_dir.glob("*.json"))
        logger.info(f"Found {len(files_to_upload['EXTRACTED-JSON'])} extracted JSON files")
    
    return files_to_upload


def upload_file_to_s3(
    s3_client: S3Client,
    local_file: Path,
    bucket_name: str,
    s3_prefix: str,
    category: str
) -> Tuple[bool, str]:
    """
    Upload a single file to S3
    
    Args:
        s3_client: S3Client instance
        local_file: Local file path
        bucket_name: S3 bucket name
        s3_prefix: S3 key prefix (folder structure)
        category: File category (csv_files, parquet_files, etc.)
        
    Returns:
        Tuple of (success: bool, s3_key: str)
    """
    try:      
        # Construct S3 key with proper folder structure
        # Format: {prefix}/{category}/{filename}
        s3_key = f"{s3_prefix}/{category}/{local_file.name}"
        
        # Upload file
        success = s3_client.upload_file(
            local_path=str(local_file),
            bucket_name=bucket_name,
            s3_key=s3_key
        )
        
        if success:
            logger.info(f"✅ Uploaded: {local_file.name} -> s3://{bucket_name}/{s3_key}")
            return True, s3_key
        else:
            logger.error(f"❌ Failed to upload: {local_file.name}")
            return False, ""
            
    except Exception as e:
        logger.error(f"❌ Error uploading {local_file.name}: {e}")
        return False, ""


def upload_files_by_category(
    s3_client: S3Client,
    files_dict: Dict[str, List[Path]],
    bucket_name: str,
    s3_prefix: str
) -> Dict[str, int]:
    """
    Upload files organized by category
    
    Args:
        s3_client: S3Client instance
        files_dict: Dictionary of categorized files
        bucket_name: S3 bucket name
        s3_prefix: S3 key prefix
        
    Returns:
        Dictionary with upload statistics per category
    """
    stats = {
        "CSV-FILES": {"uploaded": 0, "failed": 0},
        "PARQUET-FILES": {"uploaded": 0, "failed": 0},
        "MERGED-SETS": {"uploaded": 0, "failed": 0},
        "EXTRACTED-JSON": {"uploaded": 0, "failed": 0}
    }    
    
    for category, files in files_dict.items():
        if not files:
            logger.info(f"No files to upload in category: {category}")
            continue
        
        logger.info(f"\n{'='*60}")
        logger.info(f"Uploading {len(files)} files from category: {category}")
        logger.info(f"{'='*60}")
        
        for file_path in files:
            success, s3_key = upload_file_to_s3(
                s3_client=s3_client,
                local_file=file_path,
                bucket_name=bucket_name,
                s3_prefix=s3_prefix,
                category=category
            )
            
            if success:
                stats[category]["uploaded"] += 1
            else:
                stats[category]["failed"] += 1
        
        # Upload to Merged bucket if category is MERGED-SETS
        if category == "MERGED-SETS":
            merged_bucket = os.getenv("S3_MERGED_BUCKET_NAME")
            if merged_bucket:
                logger.info(f"\nUploading merged files to separate bucket: {merged_bucket}")
                s3_key_prefix = f"{merged_bucket}/{file_path.name}"
                for file_path in files:
                    success = s3_client.upload_file(
                        local_path=str(file_path),
                        bucket_name=bucket_name,
                        s3_key=s3_key_prefix
                    )
                    if success:
                        logger.info(f"✅ Also uploaded to merged bucket: {file_path.name}")
    
    return stats


def print_upload_summary(stats: Dict[str, int]):
    """Print a summary of upload statistics"""
    logger.info("\n" + "="*60)
    logger.info("UPLOAD SUMMARY")
    logger.info("="*60)
    
    total_uploaded = 0
    total_failed = 0
    
    for category, counts in stats.items():
        uploaded = counts["uploaded"]
        failed = counts["failed"]
        total_uploaded += uploaded
        total_failed += failed
        
        if uploaded > 0 or failed > 0:
            logger.info(f"{category}:")
            logger.info(f"  ✅ Uploaded: {uploaded}")
            logger.info(f"  ❌ Failed: {failed}")
    
    logger.info("-" * 60)
    logger.info(f"TOTAL Uploaded: {total_uploaded}")
    logger.info(f"TOTAL Failed: {total_failed}")
    logger.info("="*60)


def main():
    """Main upload process"""
    
    # Read configuration from environment variables
    bucket_name = os.getenv("S3_BUCKET_NAME")
    s3_prefix = os.getenv("S3_INGESTION_BUCKET_NAME")
    #airflow_home = Path(os.getenv("AIRFLOW_HOME", "/opt/airflow"))
    airflow_home = base_dir = Path(__file__).parent.parent
    
    # Validate required parameters
    if not bucket_name:
        logger.error("❌ S3_BUCKET_NAME is required in .env file")
        sys.exit(1)
    
    logger.info(f"📤 Starting S3 upload process...")
    logger.info(f"Bucket: {bucket_name}")
    logger.info(f"Prefix: {s3_prefix}")
    logger.info(f"Base directory: {airflow_home}")
    
    # Test AWS connection
    try:
        session = boto3.Session()
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        
        logger.info(f"✅ Connected to AWS Account: {identity['Account']}")
        logger.info(f"User: {identity['Arn']}")
    except Exception as e:
        logger.error(f"❌ Failed to connect to AWS: {e}")
        logger.error("Please check your AWS credentials in .env file")
        sys.exit(1)
    
    # Initialize S3 client
    s3_client = S3Client()
    
    # Test connection
    if not s3_client.test_connection():
        logger.error("❌ Failed to connect to S3. Check your credentials in .env file")
        sys.exit(1)
    
    # Check if bucket exists
    if not s3_client.bucket_exists(bucket_name):
        logger.error(f"❌ Bucket {bucket_name} does not exist")
        sys.exit(1)
    
    # Collect files to upload
    logger.info("\n📂 Collecting files to upload...")
    files_to_upload = get_files_to_upload(airflow_home)
    
    # Check if there are any files to upload
    total_files = sum(len(files) for files in files_to_upload.values())
    if total_files == 0:
        logger.warning("⚠️  No files found to upload")
        logger.info("Locations checked:")
        logger.info(f"  - {airflow_home}/datasets/CSV_FILES/")
        logger.info(f"  - {airflow_home}/datasets/PARQUET_FILES/")
        logger.info(f"  - {airflow_home}/datasets/MERGED_EXTRACTED_FILINGS/")
        logger.info(f"  - {airflow_home}/datasets/EXTRACTED_FILINGS/10-K/")
        sys.exit(0)
    
    logger.info(f"📊 Total files to upload: {total_files}")
    
    # Upload files
    logger.info("\n🚀 Starting upload...")
    stats = upload_files_by_category(
        s3_client=s3_client,
        files_dict=files_to_upload,
        bucket_name=bucket_name,
        s3_prefix=s3_prefix
    )
    
    # Print summary
    print_upload_summary(stats)
    
    # Check for failures
    total_failed = sum(counts["failed"] for counts in stats.values())
    if total_failed > 0:
        logger.warning(f"⚠️  {total_failed} files failed to upload")
        sys.exit(1)
    
    logger.info("✅ Upload process completed successfully")


if __name__ == "__main__":
    main()