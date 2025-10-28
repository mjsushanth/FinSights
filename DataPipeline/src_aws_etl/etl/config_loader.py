"""Minimal config loader for FinRAG ETL with credential management"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv


class ETLConfig:
    """Lightweight config loader with built-in credential loading"""
    
    def __init__(self, config_path=None):
        """Load YAML configuration and AWS credentials"""
        
        # Load YAML config
        if config_path is None:
            config_path = Path(__file__).parent.parent / '.aws_config' / 'etl_config.yaml'
        
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)
        
        # Load AWS credentials with fallback pattern
        self._load_credentials()
    


    """
    Dynamic approach. 
        First - try modular .aws_secrets/aws_credentials.env.
        Then, try - root .env as fallback.
    """
    def _load_credentials(self):
        """Load AWS credentials from modular or root .env (with fallback)"""
        
        # modular path first
        modular_path = Path(__file__).parent.parent / '.aws_secrets' / 'aws_credentials.env'
        root_path = Path(__file__).parent.parent.parent / '.env'
        
        # print(f"[DEBUG] Trying modular: {modular_path.absolute()}")
        # print(f"[DEBUG] Modular exists: {modular_path.exists()}")
        
        credentials_loaded = False
        
        # modular path first
        if modular_path.exists():
            load_dotenv(modular_path, override=True)
            
            # Check if credentials actually loaded
            if os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY'):
                print(f"[DEBUG] ✓ Credentials loaded from modular path")
                self._credentials_source = str(modular_path.name)
                credentials_loaded = True
            else:
                print(f"[DEBUG] Modular file exists but empty/invalid")
        
        # Fallback to root if modular didn't work
        if not credentials_loaded and root_path.exists():
            print(f"[DEBUG] Trying root fallback: {root_path.absolute()}")
            load_dotenv(root_path, override=True)
            
            if os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY'):
                print(f"[DEBUG] ✓ Credentials loaded from root .env")
                self._credentials_source = str(root_path.name)
                credentials_loaded = True
            else:
                print(f"[DEBUG]  Root .env exists but empty/invalid")
        
        # Final check
        if not credentials_loaded:
            raise FileNotFoundError(
                f"AWS credentials not found or invalid!\n"
                f"  Tried: {modular_path.absolute()}\n"
                f"  Tried: {root_path.absolute()}\n"
                f"  Ensure one file contains:\n"
                f"    AWS_ACCESS_KEY_ID=AKIA...\n"
                f"    AWS_SECRET_ACCESS_KEY=..."
            )
        
        # final verification
        access_key = os.getenv('AWS_ACCESS_KEY_ID')
        ## print(f"[DEBUG] Final AWS_ACCESS_KEY_ID: {access_key[:6] if access_key else 'MISSING'}...")
  
                

    # ========== S3 Configuration ==========
    
    @property
    def bucket(self):
        return self.cfg['s3']['bucket_name']
    
    @property
    def region(self):
        """Get AWS region from credentials (fallback to config)"""
        return os.getenv('AWS_DEFAULT_REGION', self.cfg['s3']['region'])
    
    # ========== AWS Credentials (from environment) ==========
    
    @property
    def aws_access_key(self):
        """Get AWS access key from loaded credentials"""
        return os.getenv('AWS_ACCESS_KEY_ID')
    
    @property
    def aws_secret_key(self):
        """Get AWS secret key from loaded credentials"""
        return os.getenv('AWS_SECRET_ACCESS_KEY')
    
    # ========== Input Paths ==========
    
    @property
    def hist_path(self):
        i = self.cfg['input']['historical']
        return f"{i['path']}/{i['filename']}"
    
    @property
    def incr_path(self):
        i = self.cfg['input']['incremental']
        return f"{i['path']}/{i['filename']}"
    
    # ========== Output Paths ==========
    
    @property
    def final_path(self):
        o = self.cfg['output']['final']
        return f"{o['path']}/{o['filename']}"
    
    @property
    def archive_path(self):
        return self.cfg['output']['archive']['path']
    
    @property
    def archive_pattern(self):
        return self.cfg['output']['archive']['filename_pattern']
    
    @property
    def max_backups(self):
        return self.cfg['output']['archive']['retention']['max_backups']
    
    @property
    def compression(self):
        return self.cfg['output']['final'].get('compression', 'zstd')
    
    # ========== Logging ==========
    
    @property
    def log_path(self):
        return self.cfg['output']['logging']['log_path']
    
    # ========== Helpers ==========
    
    def s3_uri(self, key):
        """Convert S3 key to full URI"""
        return f"s3://{self.bucket}/{key}"
    
    def get_s3_client(self):
        """Create boto3 S3 client with loaded credentials"""
        import boto3
        return boto3.client(
            's3',
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            region_name=self.region
        )
    
    def get_storage_options(self):
        """Get Polars storage options for S3 access"""
        return {'aws_region': self.region}


if __name__ == "__main__":
    config = ETLConfig()
    print("ETL Configuration:")
    print(f"  Credentials loaded from: {config._credentials_source}")
    print(f"  Bucket: {config.bucket}")
    print(f"  Region: {config.region}")
    print(f"  Historical: {config.hist_path}")
    print(f"  Incremental: {config.incr_path}")
    print(f"  Final Output: {config.final_path}")
    print(f"  Archive Path: {config.archive_path}")
    print(f"  Max Backups: {config.max_backups}")
    
    print(f"\nS3 URI Examples:")
    print(f"  {config.s3_uri(config.hist_path)}")
    print(f"  {config.s3_uri(config.incr_path)}")
    
    # print(f"\nCredentials loaded: {config.aws_access_key[:4] if config.aws_access_key else 'MISSING'}...")

