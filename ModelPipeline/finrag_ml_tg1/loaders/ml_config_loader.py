"""
ML Config Loader - Standalone Configuration for Embedding Pipeline
Loads AWS credentials and ML-specific settings from YAML configs

python loaders/ml_config_loader.py

"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv


class MLConfig:
    """
    Standalone ML configuration loader
    Manages AWS credentials, S3 paths, and embedding settings
    """
    
    def __init__(self, config_path=None):
        """Load YAML configuration and credentials"""
        
        # Load ML path config
        if config_path is None:
            config_path = Path(__file__).parent.parent / '.aws_config' / 'ml_config.yaml'
        
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)
        
        # Load credentials (AWS + ML APIs)
        self._load_aws_credentials()
        self._load_ml_credentials()
    
    # ========== Credential Loading ==========
    
    def _load_aws_credentials(self):
        """Load AWS credentials from .aws_secrets/aws_credentials.env"""
        aws_creds_path = Path(__file__).parent.parent / '.aws_secrets' / 'aws_credentials.env'
        
        if aws_creds_path.exists():
            load_dotenv(aws_creds_path, override=True)
            
            if os.getenv('AWS_ACCESS_KEY_ID') and os.getenv('AWS_SECRET_ACCESS_KEY'):
                print(f"[DEBUG] ✓ AWS credentials loaded from {aws_creds_path.name}")
                self._aws_creds_source = str(aws_creds_path.name)
            else:
                raise ValueError(f"AWS credentials file exists but is empty: {aws_creds_path}")
        else:
            raise FileNotFoundError(
                f"AWS credentials not found!\n"
                f"  Expected: {aws_creds_path.absolute()}\n"
                f"  Create file with:\n"
                f"    AWS_ACCESS_KEY_ID=AKIA...\n"
                f"    AWS_SECRET_ACCESS_KEY=..."
            )
    
    def _load_ml_credentials(self):
        """Load ML API keys from .aws_secrets/aws_credentials.env (same file)"""
        # Already loaded in _load_aws_credentials
        pass
    
    # ========== AWS Configuration ==========
    
    @property
    def bucket(self):
        """S3 bucket name"""
        return self.cfg['s3']['bucket_name']
    
    @property
    def region(self):
        """AWS region"""
        return os.getenv('AWS_DEFAULT_REGION', self.cfg['s3']['region'])
    
    @property
    def aws_access_key(self):
        """AWS access key from environment"""
        return os.getenv('AWS_ACCESS_KEY_ID')
    
    @property
    def aws_secret_key(self):
        """AWS secret key from environment"""
        return os.getenv('AWS_SECRET_ACCESS_KEY')
    
    # ========== Data Paths - Input (ETL Layer) ==========
    
    @property
    def input_sentences_path(self):
        """Stage 1: Original fact table from ETL (24 columns)"""
        d = self.cfg['data_etl']['sentence_fact']
        return f"{d['path']}/{d['filename']}"
    
    # ========== Data Paths - Output (ML Layer) ==========
    
    @property
    def meta_embeds_path(self):
        """Stage 2: Enhanced fact table with ML metadata (35 columns)"""
        d = self.cfg['data_ml']['meta_embeds']
        return f"{d['path']}/{d['filename']}"
    
    

    ## if provider is None: block needs to BUILD the provider string before trying to use it as a dict key.
    def embeddings_path(self, provider=None):
        """
        Embedding storage path for specific provider
        Auto-detects provider based on current model config if not specified
        """
        if provider is None:
            # Dynamic detection based on default model
            if self.embedding_provider == 'bedrock':
                model_key = self.bedrock_default_model_key
                dims = self.bedrock_dimensions
                
                # Map model to provider key
                if 'cohere' in model_key.lower():
                    provider = f"cohere_{dims}d"
                elif 'titan' in model_key.lower():
                    provider = f"titan_{dims}d"
                else:
                    # Fallback
                    provider = f"cohere_{dims}d"
            else:
                # Direct API provider fallback
                provider = 'cohere_768d'
        
        d = self.cfg['data_ml']['embeddings'][provider]
        return f"{d['path']}/{d['filename']}"


    def embeddings_metadata_path(self, provider='cohere_768d'):
        """Embedding metadata JSON path"""
        d = self.cfg['data_ml']['embeddings'][provider]
        return f"{d['path']}/{d['metadata_file']}"
    
    # ========== Embedding Configuration - Bedrock ==========
    
    @property
    def embedding_provider(self):
        """Default embedding provider (bedrock, cohere, openai)"""
        return self.cfg['embedding']['default_provider']
    
    @property
    def bedrock_region(self):
        """Bedrock region"""
        return self.cfg['embedding']['bedrock']['region']
    
    @property
    def bedrock_default_model_key(self):
        """Default Bedrock model key (cohere_embed_v3, titan_v2, etc.)"""
        return self.cfg['embedding']['bedrock']['default_model']
    
    @property
    def bedrock_model_id(self):
        """Get Bedrock model ID for default model"""
        model_key = self.bedrock_default_model_key
        return self.cfg['embedding']['bedrock']['models'][model_key]['model_id']
    
    @property
    def bedrock_dimensions(self):
        """Get embedding dimensions for default Bedrock model"""
        model_key = self.bedrock_default_model_key
        return self.cfg['embedding']['bedrock']['models'][model_key]['dimensions']
    
    @property
    def bedrock_batch_size(self):
        """Get batch size for default Bedrock model"""
        model_key = self.bedrock_default_model_key
        return self.cfg['embedding']['bedrock']['models'][model_key]['batch_size']
    
    @property
    def bedrock_input_type(self):
        """Get input_type for default Bedrock model"""
        model_key = self.bedrock_default_model_key
        return self.cfg['embedding']['bedrock']['models'][model_key]['input_type']
    
    def get_bedrock_model_config(self, model_key=None):
        """Get full config for a specific Bedrock model"""
        if model_key is None:
            model_key = self.bedrock_default_model_key
        return self.cfg['embedding']['bedrock']['models'][model_key]
    
    # ========== Legacy Properties (for backward compatibility) ==========
    
    @property
    def embedding_model(self):
        """Model ID for current provider"""
        if self.embedding_provider == 'bedrock':
            return self.bedrock_model_id
        else:
            provider = self.embedding_provider
            return self.cfg['embedding'][provider]['model']
    
    @property
    def embedding_dimensions(self):
        """Vector dimensions for current provider"""
        if self.embedding_provider == 'bedrock':
            return self.bedrock_dimensions
        else:
            provider = self.embedding_provider
            return self.cfg['embedding'][provider]['dimensions']
    
    @property
    def embedding_batch_size(self):
        """Batch size for current provider"""
        if self.embedding_provider == 'bedrock':
            return self.bedrock_batch_size
        else:
            provider = self.embedding_provider
            return self.cfg['embedding'][provider]['batch_size']
    
    @property
    def cohere_api_key(self):
        """Cohere API key from environment (for direct API access)"""
        return os.getenv('COHERE_API_KEY')
    
    @property
    def openai_api_key(self):
        """OpenAI API key from environment"""
        return os.getenv('OPENAI_API_KEY')
    
    # ========== Filtering Configuration ==========
    
    @property
    def min_char_length(self):
        """Minimum sentence character length"""
        return self.cfg['embedding']['filtering']['min_char_length']
    
    @property
    def max_char_length(self):
        """Maximum sentence character length"""
        return self.cfg['embedding']['filtering']['max_char_length']
    
    @property
    def max_token_count(self):
        """Maximum tokens per sentence"""
        return self.cfg['embedding']['filtering']['max_token_count']
    
    @property
    def exclude_sections(self):
        """List of sections to exclude from embedding"""
        return self.cfg['embedding']['filtering']['exclude_sections']
    
    # ========== Retrieval Configuration ==========
    
    @property
    def retrieval_top_k(self):
        """Number of top results to retrieve"""
        return self.cfg['retrieval']['top_k']
    
    @property
    def context_window(self):
        """Number of sentences to retrieve around target (±N)"""
        return self.cfg['retrieval']['context_window']
    
    @property
    def priority_sections(self):
        """High-priority sections for retrieval"""
        return self.cfg['retrieval']['priority_sections']
    
    @property
    def recent_years_threshold(self):
        """Filter to filings after this year"""
        return self.cfg['retrieval']['recent_years_threshold']
    
    # ========== Cost Tracking ==========
    
    @property
    def embedding_budget(self):
        """Total embedding budget in USD"""
        return self.cfg['costs']['embedding_budget_usd']
    
    @property
    def alert_threshold(self):
        """Alert when budget usage exceeds this percentage"""
        return self.cfg['costs']['alert_threshold_pct']
    
    def get_cost_per_1k(self, provider='cohere_768d'):
        """Get cost per 1K tokens for provider"""
        return self.cfg['costs']['rates'].get(provider, 0.0001)
    
    # ========== AWS Client Helper Methods ==========
    
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
    
    def get_bedrock_client(self):
        """Create Bedrock runtime client for embeddings"""
        import boto3
        return boto3.client(
            service_name='bedrock-runtime',
            region_name=self.bedrock_region,
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key
        )
    
    def get_storage_options(self):
        """Get Polars/PyArrow storage options for S3 access"""
        return {
            'aws_access_key_id': self.aws_access_key,
            'aws_secret_access_key': self.aws_secret_key,
            'aws_region': self.region
        }
    
    def download_from_s3(self, s3_key, local_path):
        """Download file from S3"""
        s3_client = self.get_s3_client()
        s3_client.download_file(self.bucket, s3_key, local_path)
        print(f"✓ Downloaded: s3://{self.bucket}/{s3_key} → {local_path}")
    
    def upload_to_s3(self, local_path, s3_key):
        """Upload file to S3"""
        s3_client = self.get_s3_client()
        s3_client.upload_file(local_path, self.bucket, s3_key)
        print(f"✓ Uploaded: {local_path} → s3://{self.bucket}/{s3_key}")


    @property
    def embedding_mode(self):
        return self.cfg['embedding_execution']['mode']

    @property
    def filter_cik(self):
        return self.cfg['embedding_execution']['filters']['cik_int']

    @property
    def filter_year(self):
        return self.cfg['embedding_execution']['filters']['year']
    
    @property
    def filter_sections(self):
        return self.cfg['embedding_execution']['filters']['sections']
    


# ============================================================================
    # S3 VECTORS STAGING PATHS (Stage 3)
    # ============================================================================

    @property
    def s3vectors_base_path(self):
        """Base path for S3 Vectors staging area"""
        return self.cfg['data_ml']['s3_vectors_staging']['base_path']

    def s3vectors_path(self, provider=None):
        """
        Get S3 Vectors staging path for specific provider or default
        
        Args:
            provider: Model provider key (e.g., 'cohere_1024d', 'titan_1024d')
                     If None, auto-detects from bedrock_default_model_key
        
        Returns:
            Full S3 key path: ML_EMBED_ASSETS/S3_VECTORS_STAGING/{provider}/{filename}
        """
        if provider is None:
            # Auto-detect provider (matches embeddings_path logic)
            model_key = self.bedrock_default_model_key
            dims = self.bedrock_dimensions
            
            if 'cohere' in model_key.lower():
                provider = f"cohere_{dims}d"
            elif 'titan' in model_key.lower():
                provider = f"titan_{dims}d"
            else:
                provider = f"cohere_{dims}d"
        
        provider_config = self.cfg['data_ml']['s3_vectors_staging'].get(provider)
        if not provider_config:
            available = [k for k in self.cfg['data_ml']['s3_vectors_staging'].keys() if k != 'base_path']
            raise ValueError(f"Unknown S3 Vectors provider: {provider}. Available: {available}")
        
        return f"{provider_config['path']}/{provider_config['filename']}"

    def s3vectors_dimensions(self, provider=None):
        """Get vector dimensions for specific provider"""
        if provider is None:
            model_key = self.bedrock_default_model_key
            dims = self.bedrock_dimensions
            
            if 'cohere' in model_key.lower():
                provider = f"cohere_{dims}d"
            elif 'titan' in model_key.lower():
                provider = f"titan_{dims}d"
            else:
                provider = f"cohere_{dims}d"
        
        provider_config = self.cfg['data_ml']['s3_vectors_staging'].get(provider)
        if not provider_config:
            raise ValueError(f"Unknown S3 Vectors provider: {provider}")
        
        return provider_config.get('dimensions', self.bedrock_dimensions)

    @property
    def s3vectors_providers(self):
        """List all configured S3 Vectors providers"""
        return [k for k in self.cfg['data_ml']['s3_vectors_staging'].keys() if k != 'base_path']

    def get_s3vectors_cache_path(self, provider):
        """
        Get local cache path for S3 Vectors staging table
        
        Args:
            provider: Model provider (e.g., 'cohere_1024d')
        
        Returns:
            Path: ../data_cache/stage3_s3vectors/{provider}/{filename}.parquet
        """
        s3_key = self.s3vectors_path(provider)
        filename = Path(s3_key).name
        
        cache_path = Path.cwd().parent / 'data_cache' / 'stage3_s3vectors' / provider / filename
        return cache_path



# ============================================================================
# TEST / DEMO
# ============================================================================

if __name__ == "__main__":
    try:
        config = MLConfig()
        
        print("=" * 70)
        print("ML PIPELINE CONFIGURATION TEST")
        print("=" * 70)
        
        print(f"\n[AWS Configuration]")
        print(f"  Credentials: {config._aws_creds_source}")
        print(f"  Bucket: {config.bucket}")
        print(f"  Region: {config.region}")
        print(f"  Access Key: {config.aws_access_key[:8]}..." if config.aws_access_key else "  ✗ Missing")
        
        print(f"\n[Data Paths - Input]")
        print(f"  Input: {config.s3_uri(config.input_sentences_path)}")
        
        print(f"\n[Data Paths - Output]")
        print(f"  Meta Embeds: {config.s3_uri(config.meta_embeds_path)}")
        print(f"  Embeddings: {config.s3_uri(config.embeddings_path())}")
        
        print(f"\n[Embedding Config - Bedrock]")
        print(f"  Provider: {config.embedding_provider}")
        print(f"  Default Model Key: {config.bedrock_default_model_key}")
        print(f"  Model ID: {config.bedrock_model_id}")
        print(f"  Dimensions: {config.bedrock_dimensions}")
        print(f"  Batch Size: {config.bedrock_batch_size}")
        print(f"  Input Type: {config.bedrock_input_type}")
        print(f"  Region: {config.bedrock_region}")
        
        print(f"\n[Filtering]")
        print(f"  Char Length: {config.min_char_length}-{config.max_char_length}")
        print(f"  Max Tokens: {config.max_token_count}")
        print(f"  Exclude: {', '.join(config.exclude_sections)}")
        
        print(f"\n[Retrieval]")
        print(f"  Top K: {config.retrieval_top_k}")
        print(f"  Context Window: ±{config.context_window}")
        print(f"  Priority Sections: {', '.join(config.priority_sections)}")
        
        print(f"\n[Cost]")
        print(f"  Budget: ${config.embedding_budget:.2f}")
        print(f"  Rate: ${config.get_cost_per_1k():.5f}/1K tokens")

        print(f"\n[Embedding Execution]")
        print(f"  Mode: {config.embedding_mode}")
        print(f"  Filter CIK: {config.filter_cik}")
        print(f"  Filter Year: {config.filter_year}")
        print(f"  Filter Sections: {config.filter_sections}")
        
        print(f"\n" + "=" * 70)
        print("✓ Configuration loaded successfully!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Configuration Error: {e}")
        import traceback
        traceback.print_exc()