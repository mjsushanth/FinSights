"""
 ┣ context_assembler.py
 ┣ context_window.py
 ┣ deduplicator.py
 ┣ deduplicator_stage2.py
 ┣ metadata_filters.py
 ┣ models.py
 ┣ reranker.py
 ┣ s3_retriever.py
 ┣ s3_retriever_contract.py
 ┣ sentence_expander.py
 ┣ sentence_expander_contract.py
 ┣ text_fetcher.py
 ┣ variant_generator.py
 ┗ variant_pipeline.py
"""


"""
Data models (DTOs) for the RAG retrieval pipeline.
This module defines all dataclasses used across Steps 4-10 of the retrieval spine.
Each class represents data at a specific pipeline stage, ensuring type safety and
clear contracts between modules.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Set, Dict, Any


# ════════════════════════════════════════════════════════════════════════════
# STEP 5: S3 VECTORS RETRIEVAL RESULTS
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class S3Hit:
    """
    Single sentence-level hit from S3 Vectors QueryVectors API.
    
    Represents one retrieved sentence with its similarity score and metadata.
    Preserves both business key (sentenceID) and technical key (surrogate).
    """
    # PRIMARY KEYS
    sentence_id: str                    #  Business key - composite string
    sentence_id_numsurrogate: int       #  Technical key - mmh3 hash (from S3)
    embedding_id: str                   #  Which embedding run (critical for joins)
    
    # SIMILARITY
    distance: float  # Cosine distance from query
    
    # FILTERABLE METADATA
    cik_int: int
    report_year: int
    section_name: str  # Canonical format (ITEM_7, ITEM_1A, etc.)
    sic: str
    sentence_pos: int  # Position within section
    
    # RETRIEVAL PROVENANCE
    source: str  # "filtered" | "global"
    variant_id: int  # 0 = base query, 1+ = semantic variants
    
    # CONTEXT METADATA (from S3 non-filterable)
    section_sentence_count: int  # For window expansion bounds
    
    # RAW (for debugging)
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def similarity_score(self) -> float:
        """Convert distance to similarity (higher = better)."""
        return max(0.0, 1.0 - (self.distance / 2.0))
    



@dataclass
class RetrievalBundle:
    """
    Collection of all S3 hits from a multi-mode retrieval operation.
    
    Aggregates results from:
    - Filtered calls (strong metadata constraints)
    - Global calls (relaxed constraints)
    - Base query + optional semantic variants
    
    The union_hits list contains deduplicated results by sentence_id,
    keeping the best score when a sentence appears multiple times.
    
    Attributes:
        filtered_hits: All hits from filtered S3 calls
        global_hits: All hits from global S3 calls
        union_hits: Deduplicated by sentence_id (stage 1 dedup)
        base_query: Original user query string
        variant_queries: Generated semantic variants (if enabled)
    """
    filtered_hits: List[S3Hit]
    global_hits: List[S3Hit]
    union_hits: List[S3Hit]  # Deduplicated by sentence_id
    
    base_query: str = ""
    variant_queries: List[str] = field(default_factory=list)
    
    def __repr__(self) -> str:
        return (
            f"RetrievalBundle(filtered={len(self.filtered_hits)}, "
            f"global={len(self.global_hits)}, union={len(self.union_hits)})"
        )


# ════════════════════════════════════════════════════════════════════════════
# STEP 6: CONTEXT WINDOW EXPANSION
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ContextSpan:
    """
    Windowed span of sentences around retrieval hits.
    
    Represents a contiguous block of sentences (±N window around hits) within
    a single document/section. Multiple hits may contribute to one span if their
    windows overlap.
    
    Attributes:
        doc_id: Document identifier (from Stage 1/2 metadata)
        cik_int: Company CIK
        report_year: Fiscal year
        sec_item_canonical: SEC section
        sentence_ids: Ordered list of sentence IDs in the window
        base_score: Best similarity score from contributing hits
        sources: Set of retrieval sources that contributed
        variant_ids: Set of query variant IDs that contributed
    """
    doc_id: str
    cik_int: int
    report_year: int
    sec_item_canonical: Optional[str]
    
    sentence_ids: List[int]  # Ordered, contiguous window
    base_score: float  # Max similarity from contributing S3Hits
    
    sources: Set[str] = field(default_factory=set)  # {"filtered", "global"}
    variant_ids: Set[int] = field(default_factory=set)  # {0, 1, 2, ...}
    
    def span_key(self) -> tuple:
        """
        Generate unique key for span-level deduplication.
        
        Two spans are considered duplicates if they have the same:
        - Company, year, section
        - Start and end sentence IDs
        """
        return (
            self.cik_int,
            self.report_year,
            self.sec_item_canonical or "UNKNOWN",
            min(self.sentence_ids) if self.sentence_ids else 0,
            max(self.sentence_ids) if self.sentence_ids else 0,
        )
    
    def __repr__(self) -> str:
        return (
            f"ContextSpan(cik={self.cik_int}, year={self.report_year}, "
            f"sec={self.sec_item_canonical}, sentences={len(self.sentence_ids)}, "
            f"score={self.base_score:.3f})"
        )


# ════════════════════════════════════════════════════════════════════════════
# STEP 7: FULL TEXT BLOCKS
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class ContextBlock:
    """
    Text-enriched context block ready for reranking and assembly.
    
    Extends ContextSpan with full sentence text joined from Stage 1/2 parquet.
    This is the primary unit of information that flows through reranking,
    deduplication, and final context assembly.
    
    Attributes:
        doc_id: Document identifier
        cik_int: Company CIK
        report_year: Fiscal year
        sec_item_canonical: SEC section
        company_name: Human-readable company name (joined from dimensions)
        text: Concatenated sentence text with line breaks
        sentence_ids: Ordered list of sentence IDs
        base_score: Similarity score from retrieval
        final_score: Score after hybrid reranking
        sources: Retrieval sources that contributed
        variant_ids: Query variants that contributed
    """
    doc_id: str
    cik_int: int
    report_year: int
    sec_item_canonical: Optional[str]
    company_name: Optional[str] = None
    
    text: str = ""
    sentence_ids: List[int] = field(default_factory=list)
    
    base_score: float = 0.0  # From retrieval (similarity)
    final_score: float = 0.0  # After reranking
    
    sources: Set[str] = field(default_factory=set)
    variant_ids: Set[int] = field(default_factory=set)

    # Helps answer: "Does this block contain actual retrieved hits or just neighbors?"
    core_hit_count: int = 0         # How many is_core_hit sentences in block
    

    def block_key(self) -> tuple:
        """
        Generate unique key for block-level deduplication (stage 2).
        
        Same logic as ContextSpan.span_key() - maintains consistency
        across window expansion and text fetching stages.
        """
        return (
            self.cik_int,
            self.report_year,
            self.sec_item_canonical or "UNKNOWN",
            min(self.sentence_ids) if self.sentence_ids else 0,
            max(self.sentence_ids) if self.sentence_ids else 0,
        )
    
    def preview(self, chars: int = 100) -> str:
        """Return truncated text preview for debugging."""
        if len(self.text) <= chars:
            return self.text
        return self.text[:chars] + "..."
    
    def __repr__(self) -> str:
        return (
            f"ContextBlock(cik={self.cik_int}, year={self.report_year}, "
            f"sec={self.sec_item_canonical}, score={self.final_score:.3f}, "
            f"text_len={len(self.text)})"
        )


# ════════════════════════════════════════════════════════════════════════════
# UTILITY TYPES
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class RetrievalConfig:
    """
    Configuration for retrieval pipeline behavior.
    
    Loaded from ml_config.yaml and passed to retrieval components.
    Centralizes all tunable parameters for easy experimentation.
    
    Attributes:
        top_k_filtered: Max results per filtered S3 call
        top_k_global: Max results per global S3 call
        enable_global: Whether to run global calls
        enable_variants: Whether to generate semantic variants
        variant_count: Number of variants to generate
        window_size: Context window (±N sentences)
        min_similarity: Minimum similarity threshold (0.0-1.0)
        recent_year_threshold: Cutoff for "recent" in global calls
    """
    top_k_filtered: int = 30
    top_k_global: int = 15
    enable_global: bool = True
    enable_variants: bool = False
    variant_count: int = 3
    window_size: int = 3  # ±3 sentences
    min_similarity: float = 0.3  # Filter very weak hits
    recent_year_threshold: int = 2015  # For global time-relaxed calls
    
    def __repr__(self) -> str:
        return (
            f"RetrievalConfig(topK_filt={self.top_k_filtered}, "
            f"topK_glob={self.top_k_global}, global={self.enable_global}, "
            f"variants={self.enable_variants})"
        )
    


@dataclass
class SentenceRecord:
    """
    Individual sentence from window expansion.
    Intermediate representation before block grouping.
    """
    # Identity & Position
    sentence_id: str
    sentence_pos: int
    
    # Context
    cik_int: int
    report_year: int
    section_name: str
    doc_id: str
    company_name: str
    
    # Content
    text: str  # Single sentence text
    
    # Provenance
    is_core_hit: bool           # True if S3 retrieval hit, False if neighbor
    parent_hit_distance: float  # Best distance from contributing hits
    sources: Set[str]           # {"filtered", "global"}
    variant_ids: Set[int]       # {0, 1, 2, ...}
    
    # Navigation (for safety/debugging - optional usage)
    prev_sentence_id: Optional[str] = None
    next_sentence_id: Optional[str] = None
    section_sentence_count: Optional[int] = None