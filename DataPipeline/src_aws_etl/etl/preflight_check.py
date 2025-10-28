"""
Pre-flight Checks & Archive Management
Verifies source files and handles single backup
"""

import os
import sys
import boto3
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Add project root
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))


from src_aws_etl.etl.config_loader import ETLConfig

try:
    import polars as pl
    POLARS_AVAILABLE = True
except ImportError:
    POLARS_AVAILABLE = False



class PreflightChecker:
    """Handles pre-flight validation and archiving"""
    
    def __init__(self):
        # Load config
        self.config = ETLConfig()
        
        # --- replaced. # Load AWS credentials
        # secrets_path = Path(__file__).parent.parent / '.aws_secrets' / 'aws_credentials.env'
        # load_dotenv(secrets_path)
        
        # S3 client using config helper
        self.s3 = self.config.get_s3_client()

        """ -- Replaced: 
        # Initialize S3 client
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        )
        """

    
    def file_exists(self, s3_key):
        """Check if S3 file exists and return size in MB"""
        try:
            response = self.s3.head_object(Bucket=self.config.bucket, Key=s3_key)
            size_mb = response['ContentLength'] / (1024 * 1024)
            return True, size_mb
        except self.s3.exceptions.ClientError:
            return False, None
    
    
# --------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------

    def run_checks(self):
        """Run all pre-flight checks"""
        print("=" * 70)
        print("PRE-FLIGHT CHECKS")
        print("=" * 70)
        
        all_good = True
        
        # Check 1: Historical file
        print("\n✓ Check 1: Historical data")
        exists, size = self.file_exists(self.config.hist_path)
        if exists:
            print(f"  Found: {self.config.hist_path} ({size:.2f} MB)")
        else:
            print(f"  MISSING: {self.config.hist_path}")
            all_good = False
        
        # Check 2: Incremental file
        print("\n✓ Check 2: Incremental data")
        exists, size = self.file_exists(self.config.incr_path)
        if exists:
            print(f"  Found: {self.config.incr_path} ({size:.2f} MB)")
        else:
            print(f"  MISSING: {self.config.incr_path}")
            all_good = False
        
        # Check 3: S3 permissions
        print("\n✓ Check 3: S3 permissions")
        try:
            self.s3.list_objects_v2(
                Bucket=self.config.bucket,
                Prefix=self.config.archive_path,
                MaxKeys=1
            )
            print(f"  Can access: {self.config.archive_path}")
        except Exception as e:
            print(f"  ERROR: {e}")
            all_good = False
        

        return all_good    


# --------------------------------------------------------------------------------------------------------------------
# This function archives the existing final file if it exists, keeping only one backup.
# Based on max_backups from config, it deletes old backups.
# --------------------------------------------------------------------------------------------------------------------

    def archive_existing(self):
        """Archive current final file if it exists (keep only 1 backup)"""
        print("\n" + "=" * 70)
        print("ARCHIVE CHECK")
        print("=" * 70)
        
        # Check if final file exists
        exists, size = self.file_exists(self.config.final_path)
        
        if not exists:
            print("\n  No existing file - first merge")
            print("  No backup needed")
            return None
        
        print(f"\n  Existing file found ({size:.2f} MB)")
        print(f"  Creating backup...")
        
        # Delete old backup first (keep only 1)
        self._delete_old_backups()
        
        # Create new backup
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archive_file = self.config.archive_pattern.format(timestamp=timestamp)
        archive_key = f"{self.config.archive_path}/{archive_file}"
        
        try:
            self.s3.copy_object(
                CopySource={'Bucket': self.config.bucket, 'Key': self.config.final_path},
                Bucket=self.config.bucket,
                Key=archive_key
            )
            print(f"  ✓ Backed up to: {archive_file}")
            return archive_file
        
        except Exception as e:
            print(f"  ERROR: Failed to backup - {e}")
            raise
    
    def _delete_old_backups(self):
        """Delete existing backups (keep only newest)"""
        try:
            # List all archives
            response = self.s3.list_objects_v2(
                Bucket=self.config.bucket,
                Prefix=f"{self.config.archive_path}/finrag_fact_sentences_"
            )
            
            if 'Contents' not in response:
                return
            
            archives = response['Contents']
            
            if len(archives) >= self.config.max_backups:
                print(f"  Deleting old backup(s)...")
                for archive in archives:
                    self.s3.delete_object(
                        Bucket=self.config.bucket,
                        Key=archive['Key']
                    )
                    print(f"    Deleted: {archive['Key'].split('/')[-1]}")
        
        except Exception as e:
            print(f"  Warning: Cleanup failed - {e}")


# --------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------

def main():
    """Run pre-flight checks and archiving"""
    try:
        checker = PreflightChecker()
        
        # Run checks
        if not checker.run_checks():
            print("\n Pre-flight failed! Cannot proceed.")
            return False
        
        # Handle archiving
        archive_file = checker.archive_existing()
        
        print("\n" + "=" * 70)
        print("READY FOR MERGE")
        print("=" * 70)
        
        return True
    
    except Exception as e:
        print(f"\n Error: {e}")
        import traceback
        traceback.print_exc()
        return False


# --------------------------------------------------------------------------------------------------------------------
# --------------------------------------------------------------------------------------------------------------------

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)




