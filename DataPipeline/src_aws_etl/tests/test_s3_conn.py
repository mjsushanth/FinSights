"""
S3 Connection Test - FinRAG AWS ETL Pipeline
Purpose: Verify AWS credentials and S3 bucket access
Author: Joel Markapudi

Usage: python src_aws_etl\tests\test_s3_conn.py
"""

import sys
from pathlib import Path
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

# Import config (credentials loaded automatically!)
sys.path.append(str(Path(__file__).parent.parent / 'etl'))

from src_aws_etl.etl.config_loader import ETLConfig
from src_aws_etl.etl.preflight_check import PreflightChecker

# Import AWS SDK
import boto3
from botocore.exceptions import ClientError


def list_s3_structure(s3_client, bucket_name, max_keys=1000):
    """
    List S3 bucket structure with proper folder/file organization
    Returns organized structure without duplicates
    """
    try:
        # Use paginator to handle large buckets
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name, PaginationConfig={'MaxItems': max_keys})
        
        # Organize by folder structure
        structure = defaultdict(list)
        all_objects = []
        
        for page in pages:
            if 'Contents' not in page:
                continue
            
            for obj in page['Contents']:
                key = obj['Key']
                size_mb = obj['Size'] / (1024 * 1024)
                all_objects.append((key, size_mb))
                
                # Determine folder path
                if '/' in key:
                    folder = '/'.join(key.split('/')[:-1]) + '/'
                    file_name = key.split('/')[-1]
                    if file_name:  # Ignore folder markers (keys ending with /)
                        structure[folder].append((file_name, size_mb))
                else:
                    structure['[ROOT]'].append((key, size_mb))
        
        return structure, all_objects
    
    except ClientError as e:
        print(f"finsight-venv Error listing objects: {e.response['Error']['Code']}")
        return None, None


def print_tree_structure(structure):
    """Print S3 bucket structure in a tree format"""
    print("\n📂 Bucket Structure:")
    print("=" * 70)
    
    # Sort folders for consistent output
    sorted_folders = sorted(structure.keys())
    
    for folder in sorted_folders:
        if folder == '[ROOT]':
            print("\n📁 [ROOT LEVEL]")
        else:
            # Calculate folder depth for indentation
            depth = folder.count('/')
            indent = "  " * (depth - 1)
            folder_name = folder.rstrip('/').split('/')[-1]
            print(f"\n{indent}📁 {folder}/")
        
        # List files in this folder
        files = structure[folder]
        for file_name, size_mb in sorted(files):
            file_indent = "  " * folder.count('/')
            if size_mb < 0.01:
                size_str = f"{size_mb * 1024:.2f} KB"
            else:
                size_str = f"{size_mb:.2f} MB"
            print(f"{file_indent}  📄 {file_name} ({size_str})")


def get_folder_summary(structure):
    """Get summary statistics by top-level folder"""
    summary = defaultdict(lambda: {'count': 0, 'size_mb': 0})
    
    for folder, files in structure.items():
        if folder == '[ROOT]':
            top_folder = '[ROOT]'
        else:
            top_folder = folder.split('/')[0]
        
        for _, size_mb in files:
            summary[top_folder]['count'] += 1
            summary[top_folder]['size_mb'] += size_mb
    
    return summary


def test_s3_connection():
    """Test AWS S3 connection and credentials"""
    
    # Load config (credentials auto-loaded via fallback!)
    config = ETLConfig()
    
    print("=" * 70)
    print("FinRAG AWS ETL - S3 Connection Test")
    print("=" * 70)
    
    print(f"\n📁 Credentials loaded from: {config._credentials_source}")
    print(f"✓ Bucket: {config.bucket}")
    print(f"✓ Region: {config.region}")
    
    # Get S3 client from config
    print("\n🔌 Initializing S3 client...")
    
    try:
        s3_client = config.get_s3_client()
        print(f"✓ S3 client initialized")
    except Exception as e:
        print(f"finsight-venv Error initializing S3 client: {e}")
        return False
    
    # Test connection by listing buckets
    print("\n Testing AWS connection...")
    
    try:
        response = s3_client.list_buckets()
        buckets = [b['Name'] for b in response['Buckets']]
        print(f"✓ Successfully connected to AWS!")
        print(f"✓ Found {len(buckets)} accessible bucket(s)")
        
        if config.bucket in buckets:
            print(f"✓ Target bucket '{config.bucket}' is accessible finsight-venv")
        else:
            print(f"finsight-venv  Target bucket '{config.bucket}' not found")
            print(f"   Available: {', '.join(buckets)}")
            return False
            
    except ClientError as e:
        print(f"finsight-venv Connection failed: {e.response['Error']['Code']}")
        return False
    
    # List bucket contents with proper structure
    print(f"\n📂 Step 4: Analyzing bucket structure...")
    
    structure, all_objects = list_s3_structure(s3_client, config.bucket)
    
    if structure is None:
        return False
    
    if not all_objects:
        print("finsight-venv  Bucket is empty (no objects found)")
        return True
    
    # Print statistics
    print(f"✓ Total objects found: {len(all_objects)}")
    total_size_mb = sum(size for _, size in all_objects)
    print(f"✓ Total size: {total_size_mb:.2f} MB")
    
    # Print folder summary
    summary = get_folder_summary(structure)
    print("\nfinsight-venv Folder Summary:")
    print("-" * 70)
    for folder, stats in sorted(summary.items()):
        print(f"  {folder:30s} | {stats['count']:3d} files | {stats['size_mb']:8.2f} MB")
    
    # Print detailed tree structure
    print_tree_structure(structure)
    
    # Success!
    print("\n" + "=" * 70)
    print("finsight-venv SUCCESS! AWS S3 connection fully verified!")
    print("=" * 70)
    print("\nfinsight-venv Next Steps:")
    print("1. ✓ S3 connection working")
    print("2. ✓ Bucket structure analyzed")
    print("3. → Ready to build ETL merge pipeline")
    
    return True


if __name__ == "__main__":
    try:
        success = test_s3_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nfinsight-venv  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nfinsight-venv Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


        