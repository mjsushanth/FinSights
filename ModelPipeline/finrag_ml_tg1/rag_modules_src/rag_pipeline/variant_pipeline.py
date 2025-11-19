"""
Semantic variant generation + embedding pipeline.

This module orchestrates the complete workflow for generating and embedding
semantic variants of user queries to improve retrieval coverage in the RAG system.

Architecture:
    Query → VariantGenerator (LLM) → ["variant1", "variant2", ...]
         ↓
    For each variant:
        variant → EntityAdapter.extract() → EntityExtractionResult
               ↓
        variant + entities → QueryEmbedderV2.embed_query() → 1024-d embedding
         ↓
    Return: (variant_queries, variant_embeddings) → S3VectorsRetriever

Design Decisions:
- Graceful degradation: Failures in variant generation don't crash the pipeline
- Per-variant entity extraction: Each variant gets its own entity context
- Config-driven: enable_variants toggle in ml_config.yaml
- Cost-conscious: Only generates variants when explicitly enabled
- Logging: Comprehensive logs for debugging and cost tracking

Usage:
    from finrag_ml_tg1.rag_pipeline.variant_pipeline import VariantPipeline
    
    pipeline = VariantPipeline(config, entity_adapter, query_embedder, bedrock_client)
    
    variant_queries, variant_embeddings = pipeline.generate(
        base_query="What was NVIDIA's revenue in 2021?"
    )
    # Returns: (["How much revenue did NVIDIA report...", ...], [emb1, emb2, ...])

Author: FinRAG Team
Date: November 2024
"""

from typing import List, Tuple, Optional
import logging

from finrag_ml_tg1.loaders.ml_config_loader import MLConfig
from finrag_ml_tg1.rag_modules_src.entity_adapter.entity_adapter import EntityAdapter
from finrag_ml_tg1.rag_modules_src.utilities.query_embedder_v2 import QueryEmbedderV2
from finrag_ml_tg1.rag_modules_src.rag_pipeline.variant_generator import VariantGenerator

logger = logging.getLogger(__name__)


class VariantPipeline:
    """
    Semantic variant generation + embedding pipeline.
    
    Coordinates three components to produce variant embeddings:
    1. VariantGenerator: LLM-based query rephrasing (Bedrock Claude Haiku)
    2. EntityAdapter: Entity extraction for each variant
    3. QueryEmbedderV2: Cohere v4 embedding generation
    
    The pipeline ensures each variant is treated as a complete query:
    - Entities are re-extracted (company/year/section may be phrased differently)
    - Embeddings respect entity context (guardrails applied per variant)
    - Failures are logged but don't crash the retrieval process
    
    Attributes:
        config: MLConfig instance (for retrieval + variant settings)
        entity_adapter: Pre-initialized EntityAdapter
        query_embedder: Pre-initialized QueryEmbedderV2 (with Bedrock client)
        variant_generator: VariantGenerator instance (created internally)
        enabled: Whether variants are enabled (from config)
    """
    
    def __init__(
        self,
        config: MLConfig,
        entity_adapter: EntityAdapter,
        query_embedder: QueryEmbedderV2,
        bedrock_client
    ):
        """
        Initialize variant pipeline with required dependencies.
        
        Args:
            config: MLConfig instance (must have 'retrieval' and 'semantic_variants' sections)
            entity_adapter: Initialized EntityAdapter for entity extraction
            query_embedder: Initialized QueryEmbedderV2 for embedding generation
            bedrock_client: boto3 bedrock-runtime client (for VariantGenerator)
        
        Raises:
            KeyError: If required config sections are missing
        """
        self.config = config
        self.entity_adapter = entity_adapter
        self.query_embedder = query_embedder
        
        # Get config sections
        try:
            retrieval_cfg = config.get_retrieval_config()
            variant_cfg = config.get_variant_config()
        except KeyError as e:
            logger.error(f"Missing required config section: {e}")
            raise
        
        # Read enabled flag from retrieval config
        self.enabled = retrieval_cfg.get("enable_variants", False)
        
        # Initialize VariantGenerator
        self.variant_generator = VariantGenerator(variant_cfg, bedrock_client)
        
        # Log initialization
        variant_count = variant_cfg.get("count", 3)
        model_id = variant_cfg.get("model_id", "unknown")
        
        logger.info(
            f"VariantPipeline initialized: enabled={self.enabled}, "
            f"count={variant_count}, model={model_id}"
        )
        
        if not self.enabled:
            logger.info("Variants DISABLED - pipeline will return empty lists")
    
    def generate(
        self, 
        base_query: str
    ) -> Tuple[List[str], List[List[float]]]:
        """
        Generate semantic variants and embed each one.
        
        This is the main entry point. Executes the full pipeline:
        1. Generate N variant queries (via LLM)
        2. For each variant: extract entities
        3. For each variant: generate embedding
        4. Return both queries (for logging) and embeddings (for retrieval)
        
        If variants are disabled or generation fails, returns empty lists.
        Partial failures (some variants succeed, some fail) are logged but
        don't prevent successful variants from being returned.
        
        Args:
            base_query: Original user query string
        
        Returns:
            Tuple of:
            - variant_queries: List[str] of generated variant strings (may be empty)
            - variant_embeddings: List[List[float]] of 1024-d embeddings (may be empty)
            
            Both lists will have same length (one embedding per query).
            If variants disabled, both lists are empty (no LLM calls, no cost).
        
        Examples:
            >>> pipeline = VariantPipeline(config, adapter, embedder, client)
            >>> vq, ve = pipeline.generate("What was NVDA revenue in 2021?")
            >>> len(vq), len(ve)
            (3, 3)
            >>> len(ve[0])
            1024
        """
        # ════════════════════════════════════════════════════════════════════
        # FAST PATH 1: Variants disabled
        # ════════════════════════════════════════════════════════════════════
        if not self.enabled:
            logger.debug("Variants disabled (enable_variants=false), returning empty")
            return [], []
        
        # ════════════════════════════════════════════════════════════════════
        # FAST PATH 2: Query too short
        # ════════════════════════════════════════════════════════════════════
        if not base_query or len(base_query.strip()) < 10:
            logger.warning(
                f"Query too short for variant generation (len={len(base_query)}): "
                f"'{base_query}'"
            )
            return [], []
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 1: Generate variant queries (LLM call via Bedrock)
        # ════════════════════════════════════════════════════════════════════
        try:
            logger.info(f"Generating variants for: '{base_query[:80]}...'")
            
            variant_queries = self.variant_generator.generate(base_query)
            
            if not variant_queries:
                logger.warning("VariantGenerator returned empty list")
                return [], []
            
            logger.info(f"✓ Generated {len(variant_queries)} variant queries")
            
        except Exception as e:
            logger.error(f"VariantGenerator failed: {e}", exc_info=True)
            # Graceful degradation - continue without variants
            return [], []
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 2: Extract entities + embed each variant
        # ════════════════════════════════════════════════════════════════════
        variant_embeddings = []
        successful_queries = []
        
        for i, variant_q in enumerate(variant_queries, start=1):
            try:
                logger.debug(f"Processing variant {i}/{len(variant_queries)}: '{variant_q[:60]}...'")
                
                # 2a. Extract entities from variant
                # (Variant phrasing may differ, so re-extract rather than reuse base entities)
                entities = self.entity_adapter.extract(variant_q)
                
                # 2b. Embed variant with entity context
                # (QueryEmbedderV2 applies guardrails based on entities)
                embedding = self.query_embedder.embed_query(variant_q, entities)
                
                # 2c. Store successful result
                variant_embeddings.append(embedding)
                successful_queries.append(variant_q)
                
                # Log success details
                logger.debug(
                    f"  ✓ Variant {i}: companies={entities.companies.tickers}, "
                    f"years={entities.years.years}, embedding_dims={len(embedding)}"
                )
            
            except Exception as e:
                logger.error(
                    f"  ✗ Variant {i} failed: {e.__class__.__name__}: {e}"
                )
                # Continue with other variants (partial success is OK)
                continue
        
        # ════════════════════════════════════════════════════════════════════
        # VALIDATION: Check results
        # ════════════════════════════════════════════════════════════════════
        if not variant_embeddings:
            logger.warning(
                "No variant embeddings generated (all variants failed processing)"
            )
            return variant_queries, []  # Return queries but no embeddings
        
        if len(variant_embeddings) < len(variant_queries):
            logger.warning(
                f"Partial success: {len(variant_embeddings)}/{len(variant_queries)} "
                f"variants successfully embedded"
            )
        
        # ════════════════════════════════════════════════════════════════════
        # SUCCESS: Return aligned lists
        # ════════════════════════════════════════════════════════════════════
        logger.info(
            f"✓ Variant pipeline complete: {len(successful_queries)} queries, "
            f"{len(variant_embeddings)} embeddings (all 1024-d)"
        )
        
        # Return only successful variants (queries + embeddings aligned)
        return successful_queries, variant_embeddings
    
    def is_enabled(self) -> bool:
        """
        Check if variant generation is enabled.
        
        Convenience method for checking enable_variants flag.
        Useful for conditional logic in orchestrators.
        
        Returns:
            True if variants are enabled, False otherwise
        """
        return self.enabled
    
    def get_variant_count(self) -> int:
        """
        Get configured number of variants to generate.
        
        Returns:
            Number of variants (from semantic_variants.count config)
        """
        try:
            variant_cfg = self.config.get_variant_config()
            return variant_cfg.get("count", 3)
        except Exception:
            return 0


# ════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FACTORY FUNCTION
# ════════════════════════════════════════════════════════════════════════════

def create_variant_pipeline(config: MLConfig) -> VariantPipeline:
    """
    Factory function to create VariantPipeline with all dependencies.
    
    Convenience function that initializes EntityAdapter, QueryEmbedderV2,
    and VariantPipeline in one call. Useful for notebooks and tests.
    
    Args:
        config: MLConfig instance
    
    Returns:
        Fully initialized VariantPipeline
    
    Example:
        >>> from finrag_ml_tg1.loaders.ml_config_loader import MLConfig
        >>> from finrag_ml_tg1.rag_pipeline.variant_pipeline import create_variant_pipeline
        >>> 
        >>> config = MLConfig()
        >>> pipeline = create_variant_pipeline(config)
        >>> vq, ve = pipeline.generate("What was NVDA revenue?")
    """
    from finrag_ml_tg1.rag_modules_src.utilities.query_embedder_v2 import (
        EmbeddingRuntimeConfig
    )
    
    # Bedrock client
    bedrock_client = config.get_bedrock_client()
    
    # Entity adapter (need dimension paths)
    # Note: Assumes standard paths - adjust if your setup differs
    from pathlib import Path
    model_root = Path(__file__).resolve().parents[3]  # Up to ModelPipeline/
    
    dim_companies = model_root / "finrag_ml_tg1/data_cache/dimensions/finrag_dim_companies_21.parquet"
    dim_sections = model_root / "finrag_ml_tg1/data_cache/dimensions/finrag_dim_sec_sections.parquet"
    
    entity_adapter = EntityAdapter(
        company_dim_path=dim_companies,
        section_dim_path=dim_sections
    )
    
    # Query embedder
    embedding_cfg = config.cfg["embedding"]
    runtime_cfg = EmbeddingRuntimeConfig.from_ml_config(embedding_cfg)
    query_embedder = QueryEmbedderV2(runtime_cfg, boto_client=bedrock_client)
    
    # Variant pipeline
    pipeline = VariantPipeline(
        config=config,
        entity_adapter=entity_adapter,
        query_embedder=query_embedder,
        bedrock_client=bedrock_client
    )
    
    return pipeline



"""
Input:  base_query (str)
Output: (variant_queries: List[str], variant_embeddings: List[List[float]])

Process:
1. VariantGenerator.generate(base_query) → ["variant1", "variant2", "variant3"]
2. For each variant:
   - EntityAdapter.extract(variant) → EntityExtractionResult
   - QueryEmbedderV2.embed_query(variant, entities) → 1024-d embedding
3. Return both lists (queries for logging, embeddings for retrieval)
"""