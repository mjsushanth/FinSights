
"""Minimal config loader for FinRAG ETL"""

import yaml
from pathlib import Path

class ETLConfig:
    def __init__(self, config_path=None):
        """Load YAML configuration"""
        if config_path is None:
            # Look in src_aws_etl/config/ folder
            config_path = Path(__file__).parent.parent / '.aws_config' / 's3_config.yaml'

        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)

    @property
    def bucket(self): 
        return self.cfg['s3']['bucket_name']

    @property
    def hist_path(self): 
        i = self.cfg['input']['historical']
        return f"{i['path']}/{i['filename']}"

    # Read from credentials file instead    
        # @property
        # def region(self):                           # 
        #     return self.cfg['s3']['region']

    @property
    def incr_path(self): 
        i = self.cfg['input']['incremental']
        return f"{i['path']}/{i['filename']}"

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


    # Helper: Full S3 URI 
    def s3_uri(self, key):
        """Convert S3 key to full URI"""
        return f"s3://{self.bucket}/{key}"


if __name__ == "__main__":
    config = ETLConfig()
    print("ETL Configuration:")
    print(f"  Bucket: {config.bucket}")
    print(f"  Historical: {config.hist_path}")
    print(f"  Incremental: {config.incr_path}")
    print(f"  Final Output: {config.final_path}")
    print(f"  Archive Path: {config.archive_path}")
    # print(f"  Max Backups: {config.max_backups}")

    print(f"\nS3 URI Examples:")
    print(f"  {config.s3_uri(config.hist_path)}")
    print(f"  {config.s3_uri(config.incr_path)}")