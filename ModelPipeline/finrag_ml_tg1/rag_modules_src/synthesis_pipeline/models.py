# ModelPipeline\finrag_ml_tg1\rag_modules_src\synthesis_pipeline\models.py

"""
Response models for FinRAG synthesis pipeline.

Design: Structured dataclasses for internal type safety,
        with .to_dict() methods for external interoperability.

Usage:
    Internal (typed):
        response = QueryResponse(query="...", answer="...", ...)
        
    External (dict):
        result = response.to_dict()
        print(result['answer'])
"""

from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any, List
from datetime import datetime


# ============================================================================
# METADATA MODELS (Nested structures)
# ============================================================================

# ============================================================================
# LLMMetadata - Isolates Bedrock-specific details
# ContextMetadata - Isolates supply line details

# ResponseMetadata - Combines both + system info

# QueryResponse - Success case
# ErrorResponse - Failure case

#     create_success_response(...)  # Converts raw dicts → typed model
#     create_error_response(...)    # Converts exception → typed model
# ============================================================================


@dataclass
class LLMMetadata:
    """
    Metadata specific to LLM invocation.
    
    Captures everything related to the Bedrock API call:
    token usage, cost, model details, and completion status.
    """
    model_id: str                    # e.g., "anthropic.claude-3-5-sonnet-..."
    input_tokens: int                # Tokens in prompt
    output_tokens: int               # Tokens in response
    total_tokens: int                # input + output
    cost: float                      # Total cost in USD
    stop_reason: str                 # 'end_turn', 'max_tokens', etc.
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ContextMetadata:
    """
    Metadata about context assembly from supply lines.
    
    Captures what went into building the context:
    KPI data, RAG retrieval, entity extraction results.
    """
    kpi_included: bool                         # Was Supply Line 1 used?
    rag_included: bool                         # Was Supply Line 2 used?
    context_length: int                        # Total chars in context
    
    # Entity extraction results (from EntityAdapter)
    kpi_entities: Optional[Dict] = None        # Companies, years, metrics extracted
    rag_entities: Optional[Dict] = None        # Same, used for RAG
    
    # Retrieval statistics (from S3VectorsRetriever)
    retrieval_stats: Optional[Dict] = None     # Hits, sources, similarity scores
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ResponseMetadata:
    """
    Complete metadata for a query response.
    
    Combines LLM metadata and context metadata into a single
    structure for comprehensive tracking.
    """
    llm: LLMMetadata                 # LLM-specific metadata
    context: ContextMetadata         # Context-specific metadata
    timestamp: str                   # ISO format timestamp
    processing_time_ms: Optional[float] = None  # Total processing time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'llm': self.llm.to_dict(),
            'context': self.context.to_dict(),
            'timestamp': self.timestamp,
            'processing_time_ms': self.processing_time_ms
        }


# ============================================================================
# RESPONSE MODELS (Top-level)
# ============================================================================

@dataclass
class QueryResponse:
    """
    Successful query response from FinRAG pipeline.
    
    This is the standard response structure returned when
    query processing completes successfully.
    
    Example:
        >>> response = QueryResponse(
        ...     query="What were NVIDIA's 2020 revenues?",
        ...     answer="NVIDIA's fiscal year 2020 revenues were...",
        ...     context="=== [NVDA] NVIDIA CORP | FY 2020...",
        ...     metadata=ResponseMetadata(...)
        ... )
        >>> result = response.to_dict()
        >>> print(result['answer'])
    """
    query: str                       # Original user question
    answer: str                      # LLM-generated response
    context: str                     # Full assembled context (KPI + RAG)
    metadata: ResponseMetadata       # Complete metadata
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for external consumers.
        
        Returns flat structure for easy access:
            result['query']
            result['answer']
            result['context']
            result['metadata']['llm']['cost']
        """
        return {
            'query': self.query,
            'answer': self.answer,
            'context': self.context,
            'metadata': self.metadata.to_dict()
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=2)
    
    def get_cost(self) -> float:
        """Convenience method to get cost."""
        return self.metadata.llm.cost
    
    def get_tokens(self) -> Dict[str, int]:
        """Convenience method to get token counts."""
        return {
            'input': self.metadata.llm.input_tokens,
            'output': self.metadata.llm.output_tokens,
            'total': self.metadata.llm.total_tokens
        }


@dataclass
class ErrorResponse:
    """
    Error response when query processing fails.
    
    Returned when something goes wrong during processing:
    configuration errors, API failures, invalid input, etc.
    
    Example:
        >>> error = ErrorResponse(
        ...     query="What were NVIDIA's revenues?",
        ...     error="AWS Bedrock API rate limit exceeded",
        ...     error_type="ClientError",
        ...     stage="llm_invocation"
        ... )
        >>> result = error.to_dict()
        >>> if 'error' in result:
        ...     print(f"Failed: {result['error']}")
    """
    query: str                       # Original query that failed
    error: str                       # Error message
    error_type: str                  # Exception type name
    stage: str                       # Where failure occurred
    timestamp: str                   # ISO format timestamp
    
    # These are always None for errors (for consistent structure)
    answer: None = None
    context: None = None
    metadata: None = None
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for external consumers.
        
        Returns structure compatible with QueryResponse
        but with error fields populated.
        """
        return {
            'query': self.query,
            'answer': self.answer,
            'context': self.context,
            'error': self.error,
            'error_type': self.error_type,
            'stage': self.stage,
            'timestamp': self.timestamp,
            'metadata': None
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=2)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_success_response(
    query: str,
    answer: str,
    context: str,
    llm_response: Dict,
    context_metadata: Dict,
    processing_time_ms: Optional[float] = None
) -> QueryResponse:
    """
    Factory function to create QueryResponse from orchestrator data.
    
    Handles conversion from raw dicts to typed models.
    
    Args:
        query: User's question
        answer: LLM response text
        context: Full assembled context
        llm_response: Dict from BedrockClient.invoke()
        context_metadata: Dict from supply_lines.build_combined_context()
        processing_time_ms: Optional processing time
        
    Returns:
        Typed QueryResponse object
    """
    # Build LLM metadata
    llm_meta = LLMMetadata(
        model_id=llm_response['model_id'],
        input_tokens=llm_response['usage']['input_tokens'],
        output_tokens=llm_response['usage']['output_tokens'],
        total_tokens=(
            llm_response['usage']['input_tokens'] + 
            llm_response['usage']['output_tokens']
        ),
        cost=llm_response['cost'],
        stop_reason=llm_response['stop_reason']
    )
    
    # Build context metadata
    ctx_meta = ContextMetadata(
        kpi_included=bool(context_metadata.get('kpi_entities')),
        rag_included=bool(context_metadata.get('rag_entities')),
        context_length=len(context),
        kpi_entities=context_metadata.get('kpi_entities'),
        rag_entities=context_metadata.get('rag_entities'),
        retrieval_stats=context_metadata.get('retrieval_stats')
    )
    
    # Build complete metadata
    metadata = ResponseMetadata(
        llm=llm_meta,
        context=ctx_meta,
        timestamp=datetime.utcnow().isoformat() + 'Z',
        processing_time_ms=processing_time_ms
    )
    
    # Build response
    return QueryResponse(
        query=query,
        answer=answer,
        context=context,
        metadata=metadata
    )


def create_error_response(
    query: str,
    error: Exception,
    stage: str
) -> ErrorResponse:
    """
    Factory function to create ErrorResponse from exception.
    
    Args:
        query: Original query
        error: Exception that occurred
        stage: Pipeline stage where error occurred
               ('initialization', 'context_building', 'prompt_formatting', 
                'llm_invocation', 'response_packaging')
        
    Returns:
        Typed ErrorResponse object
    """
    return ErrorResponse(
        query=query,
        error=str(error),
        error_type=type(error).__name__,
        stage=stage,
        timestamp=datetime.utcnow().isoformat() + 'Z'
    )


def is_error_response(result: Dict) -> bool:
    """
    Check if a response dict represents an error.
    
    Args:
        result: Dictionary from answer_query()
        
    Returns:
        True if error response, False if success
        
    Example:
        >>> result = answer_query(...)
        >>> if is_error_response(result):
        ...     print(f"Error: {result['error']}")
        ... else:
        ...     print(f"Answer: {result['answer']}")
    """
    return 'error' in result and result['error'] is not None



"""
    Input → Query comes in
    Processing → Supply lines build context
    LLM Call → Bedrock returns response
    Output → Success or Error
"""