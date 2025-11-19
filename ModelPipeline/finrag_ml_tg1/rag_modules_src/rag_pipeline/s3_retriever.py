"""
S3 Vectors retrieval module with filtered + global strategy.

DESIGN DECISIONS: (joel.)
- Base query: Always run BOTH filtered + global calls (unless global disabled in config)
- Variant queries: Run filtered calls ONLY (semantic coverage, not temporal diversity)
- Deduplication: By (sentence_id, embedding_id) at retriever stage (before window expansion)
  * Keep best (lowest) distance per (sentence_id, embedding_id) pair
  * Aggregate sources {"filtered", "global"} and variant_ids {0, 1, 2, ...}
- Error handling: Graceful degradation - empty lists on S3 failures, don't crash pipeline
- Similarity filtering: Apply min_similarity threshold during parse (filter weak hits early)

ARCHITECTURAL INTEGRATION:
┌─────────────────────────────────────────────────────────┐
│           S3VectorsRetriever                            │
│  (Owns complete retrieval strategy)                     │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │ Retrieval Strategy:                             │    │
│  │                                                  │    │
│  │ 1. Generate variants (via VariantPipeline)      │    │
│  │ 2. Base query → filtered + global               │    │
│  │ 3. Variants → filtered only                     │    │
│  │ 4. Deduplicate by (sentence_id, embedding_id)   │    │
│  │ 5. Track provenance (sources, variant_ids)      │    │
│  └────────────────────────────────────────────────┘    │
│                                                          │
│  Dependencies:                                          │
│  - boto3 S3Vectors client (AWS API)                     │
│  - VariantPipeline (variant generation + embedding)     │
│                                                          │
│  Control:                                               │
│  - Config: enable_variants, enable_global               │
└─────────────────────────────────────────────────────────┘

USAGE:
    from finrag_ml_tg1.rag_pipeline.s3_retriever import S3VectorsRetriever
    from finrag_ml_tg1.rag_pipeline.variant_pipeline import VariantPipeline
    
    # Initialize once with all dependencies
    retriever = S3VectorsRetriever(
        retrieval_config=config.get_retrieval_config(),
        aws_access_key_id=config.aws_access_key,
        aws_secret_access_key=config.aws_secret_key,
        region=config.region,
        variant_pipeline=variant_pipeline  # Pass in initialized pipeline
    )
    
    # Use it (variants handled internally if enabled)
    bundle = retriever.retrieve(
        base_embedding=base_embedding,
        base_query="What was NVIDIA's revenue in 2021?",
        filtered_filters={"cik_int": {"$in": [1045810]}, ...},
        global_filters={"cik_int": {"$in": [1045810]}, "report_year": {"$gte": 2015}}
    )
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict
import logging

import boto3
from botocore.exceptions import ClientError

from finrag_ml_tg1.rag_modules_src.rag_pipeline.models import S3Hit, RetrievalBundle
from finrag_ml_tg1.rag_modules_src.rag_pipeline.variant_pipeline import VariantPipeline

logger = logging.getLogger(__name__)


class S3VectorsRetriever:
    """
    Retrieves sentence-level hits from S3 Vectors using complete retrieval strategy.
    
    Owns the full retrieval workflow:
    - Variant generation (via VariantPipeline) if enabled
    - Base query retrieval (filtered + global)
    - Variant queries retrieval (filtered only)
    - Deduplication by (sentence_id, embedding_id)
    - Provenance tracking (sources, variant_ids)
    
    This is the main retrieval engine - developers just call retrieve() with
    base_embedding + base_query, and all strategy execution happens internally.
    
    Attributes:
        config: Retrieval configuration dict from ml_config.yaml
        s3v_client: boto3 S3 Vectors client
        variant_pipeline: VariantPipeline instance for variant generation
        enable_variants: Whether variants are enabled (from config)
        enable_global: Whether global calls are enabled (from config)
        vector_bucket: S3 Vectors bucket name
        index_name: S3 Vectors index name
        dimensions: Embedding dimensions (1024 for Cohere v4)
        top_k_filtered: Max results per filtered call
        top_k_global: Max results per global call
        top_k_filtered_variants: Max results per variant filtered call
        min_similarity: Minimum similarity threshold for filtering
    """
    
    def __init__(
        self, 
        retrieval_config: Dict[str, Any],
        aws_access_key_id: str,
        aws_secret_access_key: str,
        region: str,
        variant_pipeline: VariantPipeline
    ):
        """
        Initialize S3 Vectors retriever with complete strategy.
        
        Args:
            retrieval_config: Dict from ml_config.yaml['retrieval']
            aws_access_key_id: AWS access key
            aws_secret_access_key: AWS secret key
            region: AWS region (e.g., 'us-east-1')
            variant_pipeline: Initialized VariantPipeline instance
        
        Raises:
            ValueError: If required config keys are missing
        """
        self.config = retrieval_config
        self.variant_pipeline = variant_pipeline
        
        # Initialize S3 Vectors client
        self.s3v_client = boto3.client(
            's3vectors',
            region_name=region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key
        )
        
        # Cache config values
        self.vector_bucket = retrieval_config['vector_bucket']
        self.index_name = retrieval_config['index_name']
        self.dimensions = retrieval_config['dimensions']
        self.top_k_filtered = retrieval_config['top_k_filtered']
        self.top_k_global = retrieval_config['top_k_global']
        self.top_k_filtered_variants = retrieval_config.get('top_k_filtered_variants', 15)
        self.enable_global = retrieval_config.get('enable_global', True)
        self.enable_variants = retrieval_config.get('enable_variants', False)
        self.min_similarity = retrieval_config.get('min_similarity', 0.3)

        # NEW: Hit sampling parameters
        self.max_hits_before_expansion = retrieval_config.get('max_hits_before_expansion', 30)
        self.filtered_proportion = retrieval_config.get('filtered_proportion', 0.75)
        self.global_proportion = retrieval_config.get('global_proportion', 0.25)


        logger.info(
            f"S3VectorsRetriever initialized: "
            f"bucket={self.vector_bucket}, index={self.index_name}, "
            f"topK_filt={self.top_k_filtered}, topK_glob={self.top_k_global}, "
            f"topK_variants={self.top_k_filtered_variants}, "
            f"global={self.enable_global}, variants={self.enable_variants}"
        )
    
    def retrieve(
        self,
        base_embedding: List[float],
        base_query: str,
        filtered_filters: Optional[Dict[str, Any]],
        global_filters: Optional[Dict[str, Any]]
    ) -> RetrievalBundle:
        """
        Execute complete retrieval strategy.
        
        This is the main entry point. Handles:
        1. Variant generation (if enabled)
        2. Base query retrieval (filtered + global)
        3. Variant queries retrieval (filtered only)
        4. Deduplication
        5. Bundle assembly
        
        Args:
            base_embedding: Query embedding vector (1024-d float32)
            base_query: Original user query string (needed for variant generation)
            filtered_filters: Strong metadata filters (company, year, section)
            global_filters: Relaxed metadata filters (company, year >= threshold)
        
        Returns:
            RetrievalBundle with filtered_hits, global_hits, union_hits, 
            base_query, and variant_queries
        
        Example:
            >>> bundle = retriever.retrieve(
            ...     base_embedding=[0.01, -0.02, ...],  # 1024-d
            ...     base_query="What was NVIDIA's revenue in 2021?",
            ...     filtered_filters={"cik_int": {"$in": [1045810]}, ...},
            ...     global_filters={"cik_int": {"$in": [1045810]}, "report_year": {"$gte": 2015}}
            ... )
            >>> bundle.union_hits  # Deduplicated hits from all sources
        """
        logger.info(
            f"═══════════════════════════════════════════════════════════════\n"
            f"Starting retrieval for: '{base_query[:80]}...'\n"
            f"Config: global={self.enable_global}, variants={self.enable_variants}\n"
            f"═══════════════════════════════════════════════════════════════"
        )
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 1: VARIANT GENERATION (Internal)
        # ════════════════════════════════════════════════════════════════════
        variant_queries = []
        variant_embeddings = []
        
        if self.enable_variants:
            logger.info("→ Generating variants via VariantPipeline...")
            try:
                variant_queries, variant_embeddings = self.variant_pipeline.generate(base_query)
                logger.info(
                    f"  ✓ Generated {len(variant_queries)} variant queries, "
                    f"{len(variant_embeddings)} embeddings"
                )
            except Exception as e:
                logger.error(f"  ✗ Variant generation failed: {e}", exc_info=True)
                # Continue without variants (graceful degradation)
                variant_queries, variant_embeddings = [], []
        else:
            logger.info("→ Variants disabled (enable_variants=false)")
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 2: BASE QUERY RETRIEVAL (variant_id=0)
        # ════════════════════════════════════════════════════════════════════
        logger.info("→ Retrieving base query (filtered + global)...")
        base_hits = self._retrieve_for_embedding(
            embedding=base_embedding,
            filtered_filters=filtered_filters,
            global_filters=global_filters,
            variant_id=0,
            enable_global=self.enable_global,
            top_k_filtered=self.top_k_filtered,
            top_k_global=self.top_k_global
        )
        logger.info(f"  ✓ Base query: {len(base_hits)} raw hits")
        
        all_hits = base_hits.copy()
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 3: VARIANT QUERIES RETRIEVAL (filtered only)
        # ════════════════════════════════════════════════════════════════════
        if variant_embeddings:
            logger.info(f"→ Retrieving {len(variant_embeddings)} variant queries (filtered only)...")
            for i, var_emb in enumerate(variant_embeddings, start=1):
                var_hits = self._retrieve_for_embedding(
                    embedding=var_emb,
                    filtered_filters=filtered_filters,
                    global_filters=None,  # No global for variants
                    variant_id=i,
                    enable_global=False,
                    top_k_filtered=self.top_k_filtered_variants,
                    top_k_global=0  # Not used
                )
                all_hits.extend(var_hits)
                logger.info(f"  ✓ Variant {i}: {len(var_hits)} hits")
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 4: DEDUPLICATION
        # ════════════════════════════════════════════════════════════════════
        logger.info(f"→ Deduplicating: {len(all_hits)} raw hits...")
        union_hits = self._deduplicate_hits(all_hits)
        logger.info(f"  ✓ Deduplicated: {len(union_hits)} unique (sentence_id, embedding_id) pairs")
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 5: BUNDLE ASSEMBLY
        # ════════════════════════════════════════════════════════════════════
        filtered_hits = [h for h in union_hits if "filtered" in h.sources]
        global_hits = [h for h in union_hits if "global" in h.sources]
        
        logger.info(
            f"→ Bundle composition:\n"
            f"  • Filtered: {len(filtered_hits)} hits\n"
            f"  • Global:   {len(global_hits)} hits\n"
            f"  • Union:    {len(union_hits)} hits\n"
            f"═══════════════════════════════════════════════════════════════"
        )
        
        return RetrievalBundle(
            filtered_hits=filtered_hits,
            global_hits=global_hits,
            union_hits=union_hits,
            base_query=base_query,
            variant_queries=variant_queries
        )
    
    def _retrieve_for_embedding(
        self,
        embedding: List[float],
        filtered_filters: Optional[Dict[str, Any]],
        global_filters: Optional[Dict[str, Any]],
        variant_id: int,
        enable_global: bool,
        top_k_filtered: int,
        top_k_global: int
    ) -> List[S3Hit]:
        """
        Run filtered + optional global retrieval for one embedding.
        
        Args:
            embedding: Query vector (1024-d)
            filtered_filters: Strong metadata filters
            global_filters: Relaxed metadata filters
            variant_id: 0 = base, 1+ = variants
            enable_global: Whether to run global call
            top_k_filtered: Max results for filtered call
            top_k_global: Max results for global call
        
        Returns:
            List of S3Hit objects from both calls (filtered + global)
        """
        hits = []
        
        # ────────────────────────────────────────────────────────────────────
        # FILTERED CALL
        # ────────────────────────────────────────────────────────────────────
        try:
            filt_resp = self._call_s3_vectors(
                embedding=embedding,
                filters=filtered_filters,
                top_k=top_k_filtered
            )
            filt_hits = self._parse_response(filt_resp, "filtered", variant_id)
            hits.extend(filt_hits)
            logger.debug(
                f"    Variant {variant_id} filtered: {len(filt_hits)} hits "
                f"(after similarity filter)"
            )
        except Exception as e:
            logger.error(f"    ✗ Filtered call failed for variant {variant_id}: {e}")
            # Continue with empty filtered hits (graceful degradation)
        
        # ────────────────────────────────────────────────────────────────────
        # GLOBAL CALL (optional)
        # ────────────────────────────────────────────────────────────────────
        if enable_global and global_filters:
            try:
                glob_resp = self._call_s3_vectors(
                    embedding=embedding,
                    filters=global_filters,
                    top_k=top_k_global
                )
                glob_hits = self._parse_response(glob_resp, "global", variant_id)
                hits.extend(glob_hits)
                logger.debug(
                    f"    Variant {variant_id} global: {len(glob_hits)} hits "
                    f"(after similarity filter)"
                )
            except Exception as e:
                logger.error(f"    ✗ Global call failed for variant {variant_id}: {e}")
                # Continue with empty global hits (graceful degradation)
        
        return hits
    
    def _call_s3_vectors(
        self,
        embedding: List[float],
        filters: Optional[Dict[str, Any]],
        top_k: int
    ) -> Dict[str, Any]:
        """
        Raw S3 Vectors QueryVectors API call.
        
        Args:
            embedding: Query vector (1024-d float32)
            filters: Metadata filter JSON (or None for open retrieval)
            top_k: Maximum results to return
        
        Returns:
            Raw API response dict
        
        Raises:
            ClientError: If S3 Vectors API call fails
        """
        params = {
            "vectorBucketName": self.vector_bucket,
            "indexName": self.index_name,
            "queryVector": {"float32": embedding},
            "topK": top_k,
            "returnMetadata": True,
            "returnDistance": True
        }
        
        # Add filters if provided
        if filters:
            params["filter"] = filters
        
        return self.s3v_client.query_vectors(**params)
    
    def _parse_response(
        self,
        response: Dict[str, Any],
        source: str,
        variant_id: int
    ) -> List[S3Hit]:
        """
        Parse S3 Vectors response into S3Hit objects.
        
        Args:
            response: Raw S3 Vectors API response
            source: "filtered" or "global"
            variant_id: 0 = base, 1+ = variants
        
        Returns:
            List of S3Hit objects (filtered by min_similarity)
        """
        hits = []
        
        for vec in response.get("vectors", []):
            md = vec.get("metadata", {})
            distance = vec.get("distance", 999.0)
            
            # Apply similarity threshold (early filtering)
            similarity = 1.0 - (distance / 2.0)
            if similarity < self.min_similarity:
                continue
            
            # Parse metadata - ALL fields as correct types
            try:
                sentence_id_str = md.get("sentenceID", "")  # String (business key)
                sentence_id_surrogate = int(md.get("sentenceID_numsurrogate", 0))  # From S3
                embedding_id_str = md.get("embedding_id", "")  # Critical for joins
                
                cik_int = int(md.get("cik_int", 0))
                report_year = int(md.get("report_year", 0))
                section_name = md.get("section_name", "")
                sic = md.get("sic", "")
                sentence_pos = int(md.get("sentence_pos", -1))
                section_sentence_count = int(md.get("section_sentence_count", 0))
                
                # Validation (critical fields must exist)
                if not sentence_id_str or not embedding_id_str:
                    logger.warning(f"Missing sentenceID or embedding_id: {md}")
                    continue
                
                hits.append(S3Hit(
                    sentence_id=sentence_id_str,
                    sentence_id_numsurrogate=sentence_id_surrogate,
                    embedding_id=embedding_id_str,
                    distance=distance,
                    cik_int=cik_int,
                    report_year=report_year,
                    section_name=section_name,
                    sic=sic,
                    sentence_pos=sentence_pos,
                    source=source,
                    variant_id=variant_id,
                    section_sentence_count=section_sentence_count,
                    raw_metadata=md
                ))
            
            except (ValueError, KeyError) as e:
                logger.warning(f"Failed to parse S3 hit: {e}, metadata={md}")
                continue
        
        return hits
    


    def _deduplicate_hits(self, all_hits: List[S3Hit]) -> List[S3Hit]:
        """
        Deduplicate by (sentence_id, embedding_id) composite key + proportional sampling.
        
        CRITICAL: sentence_id alone is insufficient - we need embedding_id too
        because one sentence can have multiple embeddings from different runs.
        
        Strategy:
        1. GROUP BY (sentence_id, embedding_id)
        2. KEEP hit with best (lowest) distance per group
        3. AGGREGATE sources {filtered, global} and variant_ids {0, 1, 2, ...}
        4. SORT by distance (best first)
        5. APPLY proportional topK if over limit (keeps best hits from each source)
        
        Args:
            all_hits: Raw hits from all retrieval calls
        
        Returns:
            Deduplicated hits (possibly sampled), sorted by distance (best first)
        """
        if not all_hits:
            return []
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 1: Group by (sentence_id, embedding_id) composite key
        # ════════════════════════════════════════════════════════════════════
        groups = defaultdict(list)
        for hit in all_hits:
            key = (hit.sentence_id, hit.embedding_id)
            groups[key].append(hit)
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 2: Keep best distance per group, aggregate provenance
        # ════════════════════════════════════════════════════════════════════
        deduped = []
        
        for (sentence_id, embedding_id), hits in groups.items():
            # Keep hit with best (lowest) distance
            best = min(hits, key=lambda h: h.distance)
            
            # Aggregate provenance from all hits for this (sentence, embedding) pair
            best.sources = {h.source for h in hits}
            best.variant_ids = {h.variant_id for h in hits}
            
            deduped.append(best)
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 3: Sort by distance (best matches first)
        # ════════════════════════════════════════════════════════════════════
        deduped.sort(key=lambda h: h.distance)
        
        logger.debug(
            f"    Deduplication: {len(all_hits)} raw → "
            f"{len(deduped)} unique (sentence_id, embedding_id) pairs"
        )
        
        # ════════════════════════════════════════════════════════════════════
        # STEP 4: Apply proportional topK if over limit
        # ════════════════════════════════════════════════════════════════════
        if len(deduped) > self.max_hits_before_expansion:
            deduped = self._proportional_topk(deduped)
        
        return deduped



    def _proportional_topk(self, hits: List[S3Hit]) -> List[S3Hit]:
        """
        Proportional sampling to limit total hits before window expansion.
        
        Strategy:
        - Separate by primary source (filtered vs global-only)
        - Take top K from each proportionally (default: 70% filtered, 30% global)
        - Within each source, keeps BEST hits (lowest distances)
        - Avoids cross-pool distance comparison issues
        
        Edge cases handled:
        1. Under limit: Returns all hits (no sampling)
        2. Filtered empty: Takes all from global up to limit
        3. Global empty: Takes all from filtered up to limit
        4. One source exhausted: Backfills from other source
        
        Args:
            hits: Deduplicated union hits (already sorted by distance)
        
        Returns:
            Subset of hits (up to max_hits_before_expansion)
        """
        limit = self.max_hits_before_expansion
        
        # ════════════════════════════════════════════════════════════════════
        # EDGE CASE 1: Under limit - no sampling needed
        # ════════════════════════════════════════════════════════════════════
        if len(hits) <= limit:
            logger.debug(
                f"    Hits ({len(hits)}) under limit ({limit}), no sampling needed"
            )
            return hits
        
        # ════════════════════════════════════════════════════════════════════
        # Separate by primary source
        # ════════════════════════════════════════════════════════════════════
        # Primary source = "filtered" if present, else "global"
        filtered_primary = [h for h in hits if "filtered" in h.sources]
        global_primary = [h for h in hits if "global" in h.sources and "filtered" not in h.sources]
        
        # ════════════════════════════════════════════════════════════════════
        # EDGE CASE 2: Filtered is empty (very rare)
        # ════════════════════════════════════════════════════════════════════
        if not filtered_primary:
            logger.warning(
                f"    No filtered hits - taking top {limit} from global only"
            )
            global_sorted = sorted(global_primary, key=lambda h: h.distance)
            return global_sorted[:limit]
        
        # ════════════════════════════════════════════════════════════════════
        # EDGE CASE 3: Global is empty (possible if enable_global=false)
        # ════════════════════════════════════════════════════════════════════
        if not global_primary:
            logger.debug(
                f"    No global-only hits - taking top {limit} from filtered"
            )
            filtered_sorted = sorted(filtered_primary, key=lambda h: h.distance)
            return filtered_sorted[:limit]
        
        # ════════════════════════════════════════════════════════════════════
        # Normal case: Both sources present
        # ════════════════════════════════════════════════════════════════════
        # Calculate proportional targets
        target_filtered = int(limit * self.filtered_proportion)
        target_global = int(limit * self.global_proportion)
        
        # Sort each group by distance (best first) - may already be sorted, but ensure
        filtered_sorted = sorted(filtered_primary, key=lambda h: h.distance)
        global_sorted = sorted(global_primary, key=lambda h: h.distance)
        
        # Take top K from each (capped at available)
        sampled_filtered = filtered_sorted[:min(target_filtered, len(filtered_sorted))]
        sampled_global = global_sorted[:min(target_global, len(global_sorted))]
        
        # ════════════════════════════════════════════════════════════════════
        # EDGE CASE 4: Backfill if one source exhausted
        # ════════════════════════════════════════════════════════════════════
        total_sampled = len(sampled_filtered) + len(sampled_global)
        
        if total_sampled < limit:
            shortage = limit - total_sampled
            
            # Try to backfill from filtered (if it has more)
            if len(sampled_filtered) < len(filtered_sorted):
                backfill_start = len(sampled_filtered)
                backfill_end = min(backfill_start + shortage, len(filtered_sorted))
                backfill = filtered_sorted[backfill_start:backfill_end]
                sampled_filtered.extend(backfill)
                logger.debug(f"    Backfilled {len(backfill)} from filtered")
            
            # Otherwise try global
            elif len(sampled_global) < len(global_sorted):
                backfill_start = len(sampled_global)
                backfill_end = min(backfill_start + shortage, len(global_sorted))
                backfill = global_sorted[backfill_start:backfill_end]
                sampled_global.extend(backfill)
                logger.debug(f"    Backfilled {len(backfill)} from global")
        
        # Combine final result
        sampled_hits = sampled_filtered + sampled_global
        
        logger.info(
            f"    Proportional sampling: {len(hits)} → {len(sampled_hits)} hits\n"
            f"      Filtered: {len(filtered_primary)} → {len(sampled_filtered)} "
            f"({len(sampled_filtered)/limit:.0%} of limit)\n"
            f"      Global:   {len(global_primary)} → {len(sampled_global)} "
            f"({len(sampled_global)/limit:.0%} of limit)"
        )
        
        return sampled_hits