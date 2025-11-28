# ModelPipeline/finrag_ml_tg1/rag_modules_src/synthesis_pipeline/mlflow_utils.py

"""
MLflow Utilities for FinRAG Pipeline.

Handles metric extraction from pipeline results and integrates with MLflow tracking.

This module acts as a bridge between:
    - orchestrator.py (pipeline results)
    - mlflow_tracker.py (MLflow logging)

Usage:
    from mlflow_utils import (
        extract_retrieval_metrics,
        extract_llm_metrics,
        extract_all_metrics,
        run_with_mlflow_tracking
    )
    
    # Option 1: Extract metrics manually
    metrics = extract_all_metrics(result)
    
    # Option 2: Wrap entire pipeline call with tracking
    result = run_with_mlflow_tracking(
        query="What is NVIDIA's revenue?",
        model_root=model_root,
        experiment_name="FinRAG-Synthesis"
    )
"""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# DATA CLASSES FOR EXTRACTED METRICS
# ============================================================================

@dataclass
class RetrievalMetrics:
    """Metrics extracted from retrieval phase."""
    kpi_count: int = 0
    rag_count: int = 0
    tickers: List[str] = None
    years: List[int] = None
    sections: List[str] = None
    
    def __post_init__(self):
        self.tickers = self.tickers or []
        self.years = self.years or []
        self.sections = self.sections or []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'kpi_count': self.kpi_count,
            'rag_count': self.rag_count,
            'tickers': self.tickers,
            'years': self.years,
            'sections': self.sections
        }


@dataclass
class LLMMetrics:
    """Metrics extracted from LLM response."""
    model_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    stop_reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'model_id': self.model_id,
            'input_tokens': self.input_tokens,
            'output_tokens': self.output_tokens,
            'total_tokens': self.total_tokens,
            'cost_usd': self.cost_usd,
            'stop_reason': self.stop_reason
        }


@dataclass
class ContextMetrics:
    """Metrics about assembled context."""
    context_length: int = 0
    answer_length: int = 0
    kpi_included: bool = False
    rag_included: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'context_length': self.context_length,
            'answer_length': self.answer_length,
            'kpi_included': self.kpi_included,
            'rag_included': self.rag_included
        }


@dataclass
class PipelineMetrics:
    """All metrics from a pipeline run."""
    retrieval: RetrievalMetrics
    llm: LLMMetrics
    context: ContextMetrics
    latency_seconds: float = 0.0
    status: str = "success"
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'retrieval': self.retrieval.to_dict(),
            'llm': self.llm.to_dict(),
            'context': self.context.to_dict(),
            'latency_seconds': self.latency_seconds,
            'status': self.status,
            'error_message': self.error_message
        }


# ============================================================================
# METRIC EXTRACTION FUNCTIONS
# ============================================================================

def extract_retrieval_metrics(context_metadata: Dict[str, Any]) -> RetrievalMetrics:
    """
    Extract retrieval metrics from context_metadata.
    
    Handles the EntityExtractionResult objects and RetrievalBundle
    returned by supply_lines.build_combined_context().
    
    Args:
        context_metadata: Metadata dict from build_combined_context()
            Expected keys:
            - kpi_entities: EntityExtractionResult object (or None)
            - rag_entities: EntityExtractionResult object (or None)
            - retrieval_bundle: RetrievalBundle object (or None)
            - metric_result: Dict from MetricPipeline (or None)
            - kpi_block: str (formatted KPI text)
    
    Returns:
        RetrievalMetrics dataclass with extracted values
    """
    metrics = RetrievalMetrics()
    
    tickers_set = set()
    years_set = set()
    sections_set = set()
    
    # ========================================================================
    # Extract from KPI entities (EntityExtractionResult object)
    # ========================================================================
    kpi_entities = context_metadata.get('kpi_entities')
    if kpi_entities is not None:
        try:
            # EntityExtractionResult.companies.tickers is a set
            if hasattr(kpi_entities, 'companies') and hasattr(kpi_entities.companies, 'tickers'):
                tickers_set.update(kpi_entities.companies.tickers or [])
            
            # EntityExtractionResult.years.years is a set
            if hasattr(kpi_entities, 'years') and hasattr(kpi_entities.years, 'years'):
                years_set.update(kpi_entities.years.years or [])
            
            # EntityExtractionResult.sections is a set
            if hasattr(kpi_entities, 'sections'):
                sections_set.update(kpi_entities.sections or [])
                
        except (AttributeError, TypeError) as e:
            logger.warning(f"Could not extract KPI entity metrics: {e}")
    
    # ========================================================================
    # Get KPI count from metric_result or estimate from kpi_block
    # ========================================================================
    metric_result = context_metadata.get('metric_result')
    if metric_result is not None:
        try:
            if isinstance(metric_result, dict):
                # Try common keys where row data might be stored
                for key in ['data', 'results', 'rows', 'metrics', 'records']:
                    if key in metric_result and isinstance(metric_result[key], (list, dict)):
                        metrics.kpi_count = len(metric_result[key])
                        break
                else:
                    # Fallback: count top-level items
                    metrics.kpi_count = len(metric_result)
            elif isinstance(metric_result, list):
                metrics.kpi_count = len(metric_result)
        except (TypeError, AttributeError) as e:
            logger.warning(f"Could not extract KPI count from metric_result: {e}")
    
    # Fallback: estimate from kpi_block content
    if metrics.kpi_count == 0:
        kpi_block = context_metadata.get('kpi_block', '')
        if kpi_block:
            data_lines = [line for line in kpi_block.split('\n') 
                          if line.strip() and not line.startswith('═') and ':' in line]
            metrics.kpi_count = len(data_lines)
    
    # ========================================================================
    # Extract from RAG entities (EntityExtractionResult object)
    # ========================================================================
    rag_entities = context_metadata.get('rag_entities')
    if rag_entities is not None:
        try:
            if hasattr(rag_entities, 'companies') and hasattr(rag_entities.companies, 'tickers'):
                tickers_set.update(rag_entities.companies.tickers or [])
            
            if hasattr(rag_entities, 'years') and hasattr(rag_entities.years, 'years'):
                years_set.update(rag_entities.years.years or [])
            
            if hasattr(rag_entities, 'sections'):
                sections_set.update(rag_entities.sections or [])
                
        except (AttributeError, TypeError) as e:
            logger.warning(f"Could not extract RAG entity metrics: {e}")
    
    # ========================================================================
    # Extract RAG count from retrieval_bundle
    # ========================================================================
    retrieval_bundle = context_metadata.get('retrieval_bundle')
    if retrieval_bundle is not None:
        try:
            if hasattr(retrieval_bundle, 'union_hits'):
                metrics.rag_count = len(retrieval_bundle.union_hits or [])
            elif hasattr(retrieval_bundle, 'total_hits'):
                metrics.rag_count = retrieval_bundle.total_hits
        except (AttributeError, TypeError) as e:
            logger.warning(f"Could not extract RAG count from bundle: {e}")
    
    # ========================================================================
    # Finalize: deduplicate and sort
    # ========================================================================
    metrics.tickers = sorted(list(tickers_set))
    metrics.years = sorted([int(y) for y in years_set if y])
    metrics.sections = sorted(list(sections_set))
    
    return metrics


def extract_llm_metrics(result: Dict[str, Any]) -> LLMMetrics:
    """
    Extract LLM metrics from pipeline result.
    
    Args:
        result: Result dict from answer_query()
    
    Returns:
        LLMMetrics dataclass with extracted values
    """
    metrics = LLMMetrics()
    
    llm_meta = result.get('metadata', {}).get('llm', {})
    
    if llm_meta:
        metrics.model_id = llm_meta.get('model_id', '')
        metrics.input_tokens = llm_meta.get('input_tokens', 0)
        metrics.output_tokens = llm_meta.get('output_tokens', 0)
        metrics.total_tokens = llm_meta.get('total_tokens', 0)
        metrics.cost_usd = llm_meta.get('cost', 0.0)
        metrics.stop_reason = llm_meta.get('stop_reason', '')
    
    return metrics


def extract_context_metrics(result: Dict[str, Any]) -> ContextMetrics:
    """
    Extract context metrics from pipeline result.
    
    Args:
        result: Result dict from answer_query()
    
    Returns:
        ContextMetrics dataclass with extracted values
    """
    metrics = ContextMetrics()
    
    ctx_meta = result.get('metadata', {}).get('context', {})
    
    if ctx_meta:
        metrics.context_length = ctx_meta.get('context_length', 0)
        metrics.kpi_included = ctx_meta.get('kpi_included', False)
        metrics.rag_included = ctx_meta.get('rag_included', False)
    
    # Answer length from result
    answer = result.get('answer', '')
    metrics.answer_length = len(answer) if answer else 0
    
    return metrics


def extract_all_metrics(
    result: Dict[str, Any],
    context_metadata: Optional[Dict[str, Any]] = None,
    latency_seconds: float = 0.0
) -> PipelineMetrics:
    """
    Extract all metrics from a pipeline run.
    
    Args:
        result: Result dict from answer_query()
        context_metadata: Optional metadata from build_combined_context()
                         (if not available, retrieval metrics will be limited)
        latency_seconds: Total pipeline latency
    
    Returns:
        PipelineMetrics dataclass with all extracted metrics
    """
    # Determine status
    is_error = result.get('error') is not None
    status = "failed" if is_error else "success"
    error_message = result.get('error') if is_error else None
    
    # Extract retrieval metrics
    if context_metadata:
        retrieval = extract_retrieval_metrics(context_metadata)
    else:
        # Try to extract from result metadata if context_metadata not provided
        retrieval = RetrievalMetrics()
        ret_meta = result.get('metadata', {}).get('retrieval', {})
        if ret_meta:
            retrieval.kpi_count = ret_meta.get('kpi_count', 0)
            retrieval.rag_count = ret_meta.get('rag_count', 0)
            retrieval.tickers = ret_meta.get('tickers', [])
            retrieval.years = ret_meta.get('years', [])
            retrieval.sections = ret_meta.get('sections', [])
    
    return PipelineMetrics(
        retrieval=retrieval,
        llm=extract_llm_metrics(result),
        context=extract_context_metrics(result),
        latency_seconds=latency_seconds,
        status=status,
        error_message=error_message
    )


# ============================================================================
# MLFLOW INTEGRATION WRAPPER
# ============================================================================

def run_with_mlflow_tracking(
    query: str,
    model_root: Path,
    model_key: Optional[str] = None,
    include_kpi: bool = True,
    include_rag: bool = True,
    export_context: bool = True,
    export_response: bool = False,
    experiment_name: str = "FinRAG-Integration",
    environment: str = "development",
    run_name: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None
) -> Tuple[Dict[str, Any], Optional[str]]:
    """
    Run query with full MLflow tracking.    
    
    """
    # Import here to avoid circular imports
    from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.orchestrator import answer_query
    from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.mlflow_tracker import (
        create_tracker,
        FinRAGTracker
    )
    
    # Load model config for logging parameters
    model_config = _load_model_config(model_root, model_key)
    resolved_model_key = model_config.get('_resolved_key', model_key or 'default')
    
    # Create tracker
    tracker = create_tracker(
        experiment_name=experiment_name,
        model_root=model_root,
        environment=environment
    )
    
    run_url = None
    result = None
    
    with tracker.start_run(
        query=query,
        model_key=resolved_model_key,
        model_config=model_config,
        prompt_versions={"system": "v1", "query": "v1"},
        include_kpi=include_kpi,
        include_rag=include_rag,
        run_name=run_name,
        tags=tags
    ) as run_id:
        
        # Track timing
        start_time = time.time()
        
        # Run pipeline
        result = answer_query(
            query=query,
            model_root=model_root,
            include_kpi=include_kpi,
            include_rag=include_rag,
            model_key=model_key,
            export_context=export_context,
            export_response=export_response
        )
        
        # Calculate latency
        latency = time.time() - start_time
        tracker.log_latency(total=latency)
        
        # Extract and log metrics
        is_error = result.get('error') is not None
        
        if not is_error:
            # LLM metrics
            llm_metrics = extract_llm_metrics(result)
            tracker.log_llm_metrics(
                input_tokens=llm_metrics.input_tokens,
                output_tokens=llm_metrics.output_tokens,
                cost=llm_metrics.cost_usd,
                model_id=llm_metrics.model_id
            )
            
            # Context metrics
            ctx_metrics = extract_context_metrics(result)
            tracker.log_context_metrics(
                context_length=ctx_metrics.context_length,
                answer_length=ctx_metrics.answer_length
            )
            
            # Retrieval metrics (from result if available)
            ret_meta = result.get('metadata', {}).get('retrieval', {})
            if ret_meta:
                tracker.log_retrieval_metrics(
                    kpi_count=ret_meta.get('kpi_count', 0),
                    rag_count=ret_meta.get('rag_count', 0),
                    tickers=ret_meta.get('tickers', []),
                    years=ret_meta.get('years', []),
                    sections=ret_meta.get('sections', [])
                )
            
            # Log artifacts
            tracker.log_artifacts(
                query=query,
                full_response=result
            )
        
        run_url = tracker.get_run_url()
    
    return result, run_url


def _load_model_config(model_root: Path, model_key: Optional[str]) -> Dict[str, Any]:
    """Load model configuration from ml_config.yaml."""
    import yaml
    
    config_path = model_root / "finrag_ml_tg1" / "config" / "ml_config.yaml"
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        serving_models = config.get('serving_models', {})
        
        # Determine which model to use
        resolved_key = model_key or serving_models.get('default_serving_model', 'development_CH45')
        
        if resolved_key in serving_models:
            model_config = serving_models[resolved_key].copy()
            model_config['_resolved_key'] = resolved_key
            return model_config
        
    except Exception as e:
        logger.warning(f"Could not load model config: {e}")
    
    return {'_resolved_key': model_key or 'unknown'}


# ============================================================================
# STANDALONE TEST
# ============================================================================

if __name__ == "__main__":
    """
    Test metric extraction functions.
    
    Run:
        cd ModelPipeline
        python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.mlflow_utils
    """
    print("=" * 70)
    print("MLFLOW UTILS TEST")
    print("=" * 70)
    
    # Test with mock data
    mock_result = {
        'query': 'What was NVIDIA revenue in 2020?',
        'answer': 'NVIDIA reported revenue of $10.9 billion in fiscal year 2020.',
        'metadata': {
            'llm': {
                'model_id': 'us.anthropic.claude-haiku-4-5-20251001-v1:0',
                'input_tokens': 5000,
                'output_tokens': 150,
                'total_tokens': 5150,
                'cost': 0.0058,
                'stop_reason': 'end_turn'
            },
            'context': {
                'context_length': 25000,
                'kpi_included': True,
                'rag_included': True
            }
        }
    }
    
    # Test LLM metrics extraction
    llm_metrics = extract_llm_metrics(mock_result)
    print(f"\nLLM Metrics:")
    print(f"  Model: {llm_metrics.model_id}")
    print(f"  Tokens: {llm_metrics.input_tokens} in / {llm_metrics.output_tokens} out")
    print(f"  Cost: ${llm_metrics.cost_usd:.4f}")
    
    # Test context metrics extraction
    ctx_metrics = extract_context_metrics(mock_result)
    print(f"\nContext Metrics:")
    print(f"  Context length: {ctx_metrics.context_length}")
    print(f"  Answer length: {ctx_metrics.answer_length}")
    print(f"  KPI included: {ctx_metrics.kpi_included}")
    
    # Test full extraction
    all_metrics = extract_all_metrics(mock_result, latency_seconds=5.2)
    print(f"\nFull Pipeline Metrics:")
    print(f"  Status: {all_metrics.status}")
    print(f"  Latency: {all_metrics.latency_seconds:.2f}s")
    
    print("\n" + "=" * 70)
    print("SUCCESS - All extraction functions working")
    print("=" * 70)