# ModelPipeline\finrag_ml_tg1\rag_modules_src\synthesis_pipeline\main.py

"""
FinRAG CLI Demo - End-to-end query answering.

Usage:
    # Basic usage (MLflow enabled by default)
    python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main
    # Custom query
    python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --query "Your question"
    # Different model
    python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --model development
    # Export full response to JSON
    python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --export-response
    
    # Custom experiment name for MLFlow tracking
    python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --experiment "FinRAG-Eval-Nov2025"
    
    # Disable MLflow tracking
    python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --no-tracking

Philosophy:
    - Minimal console output (not a log dumper)
    - Points to export files (don't print 40K char contexts)
    - Shows preview of answer (first 500 chars)
    - Clean success/error handling
    - No emojis, no clutter

MLflow Tracking:
    - Experiment: Configurable, defaults to "FinRAG-Integration"
    - Parameters: model, prompt versions, retrieval settings
    - Metrics: latency, tokens, cost, retrieval counts
    - Artifacts: prompts, context, full response
"""

import argparse
import sys
import time
import yaml
from pathlib import Path
from typing import Dict, Optional, Tuple

from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.orchestrator import answer_query
from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.models import is_error_response

# MLflow tracker
from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.mlflow_utils import (
    run_with_mlflow_tracking
)

# ============================================================================
# DEFAULT QUERY
# ============================================================================

DEFAULT_QUERY = (
    "For NVIDIA and Microsoft, what were revenue, operating income, and total assets "
    "in each year from 2018 to 2020, and how did management in the MD&A and Risk Factors "
    "sections explain these trends in terms of their AI strategy, competitive positioning, "
    "and supply chain risks?"
)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def find_model_root() -> Path:
    """
    Walk up directory tree to find ModelPipeline root.
    
    Returns:
        Path to ModelPipeline directory
        
    Raises:
        RuntimeError: If ModelPipeline not found
    """
    current = Path.cwd()
    
    for parent in [current] + list(current.parents):
        if parent.name == "ModelPipeline":
            return parent
    
    raise RuntimeError(
        "Cannot find 'ModelPipeline' root directory.\n"
        "Ensure you're running from within the project tree."
    )


def print_separator(char: str = "=", width: int = 70):
    """Print separator line."""
    print(char * width)


def print_result(result: dict, show_mlflow_info: bool = True, run_url: Optional[str] = None):
    """
    Print query result with minimal, clean output.
    
    Args:
        result: Dictionary from answer_query()
    """
    print_separator()
    print("FINRAG QUERY RESULT")
    print_separator()
    
    # Check if error
    if is_error_response(result):
        print(f"\nERROR: {result['error']}")
        print(f"Type: {result['error_type']}")
        print(f"Stage: {result['stage']}")
        print(f"Query: {result['query'][:80]}...")
        
        # Export info
        exports = result.get('exports', {})
        if exports.get('log_file'):
            print(f"\nLogged to: {exports['log_file']}")
        
        # MLflow info
        if show_mlflow_info and run_url:
            print(f"\nMLflow Run: {run_url}")
            
        print_separator()
        return
    
    # Success case
    query = result['query']
    answer = result['answer']
    metadata = result['metadata']
    exports = result.get('exports', {})
    
    # Query info
    print(f"\nQuery: {query[:100]}{'...' if len(query) > 100 else ''}")
    
    # Answer preview (first 500 chars)
    print(f"\nAnswer Preview:")
    print_separator("-")
    answer_preview = answer[:500] + ("..." if len(answer) > 500 else "")
    print(answer_preview)
    print_separator("-")
    
    # Metadata summary (one line)
    llm = metadata['llm']
    ctx = metadata['context']
    
    print(f"\nMetrics:")
    print(f"  Model: {llm['model_id'].split('.')[-1]}")  # Just model name
    print(f"  Tokens: {llm['input_tokens']:,} in / {llm['output_tokens']:,} out")
    print(f"  Cost: ${llm['cost']:.4f}")
    print(f"  Context: {ctx['context_length']:,} chars")
    
    # Export files (where to find full data)
    print(f"\nExports:")
    if exports.get('context_file'):
        print(f"  Context: {exports['context_file']}")
    if exports.get('response_file'):
        print(f"  Response: {exports['response_file']}")
    if exports.get('log_file'):
        print(f"  Logs: {exports['log_file']}")
    
    # Retrieval stats (if available)
    if 'retrieval' in metadata:
        ret = metadata['retrieval']
        print(f"  KPI Matches: {ret.get('kpi_count', 'N/A')}")
        print(f"  RAG Chunks: {ret.get('rag_count', 'N/A')}")
    
    # MLflow info
    if show_mlflow_info and run_url:
        print(f"\nMLflow:")
        print(f"  Run: {run_url}")
    
    print_separator()
    
    # Helpful tip
    print("\nTip: Full answer saved in exports. Context and logs available above.")

# ============================================================================
# CONFIGURATION LOADER FOR MLFLOW INTEGRATION
# ============================================================================
def load_model_config_display(model_root: Path, model_key: Optional[str] = None) -> Tuple[str, str]:
    """
    Load model config for display purposes only.
    
    Returns:
        Tuple of (model_key, display_name)
    """
    import yaml
    config_path = model_root / "finrag_ml_tg1" / "config" / "ml_config.yaml"
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        serving_models = config.get('serving_models', {})
        resolved_key = model_key or serving_models.get('default_serving_model', 'development_CH45')
        
        if resolved_key in serving_models:
            display_name = serving_models[resolved_key].get('display_name', resolved_key)
            return resolved_key, display_name
    except Exception:
        pass
    
    return model_key or 'default', 'Unknown'
# ============================================================================
# MAIN ENTRY POINT
# ============================================================================
def run_with_tracking(
    query: str,
    model_root: Path,
    model_key: Optional[str],
    include_kpi: bool,
    include_rag: bool,
    export_context: bool,
    export_response: bool,
    experiment_name: str,
    environment: str
) -> Tuple[dict, Optional[str]]:
    """
    Run query with MLflow tracking.
    
    Delegates to mlflow_utils.run_with_mlflow_tracking() which handles
    all metric extraction and logging.
    
    Returns:
        Tuple of (result_dict, mlflow_run_url)
    """
    return run_with_mlflow_tracking(
        query=query,
        model_root=model_root,
        model_key=model_key,
        include_kpi=include_kpi,
        include_rag=include_rag,
        export_context=export_context,
        export_response=export_response,
        experiment_name=experiment_name,
        environment=environment
    )


def run_without_tracking(
    query: str,
    model_root: Path,
    model_key: Optional[str],
    include_kpi: bool,
    include_rag: bool,
    export_context: bool,
    export_response: bool
) -> Tuple[dict, None]:
    """
    Run query without MLflow tracking.
    
    Returns:
        Tuple of (result_dict, None)
    """
    result = answer_query(
        query=query,
        model_root=model_root,
        include_kpi=include_kpi,
        include_rag=include_rag,
        model_key=model_key,
        export_context=export_context,
        export_response=export_response
    )
    
    return result, None

def main():
    """Main CLI entry point."""
    
    # Parse arguments
    parser = argparse.ArgumentParser(
        description="FinRAG - Query financial 10-K filings with AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use default query and model (Claude 4.5 Haiku from ml_config.yaml)
  python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main
  
  # Custom query
  python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --query "What were NVIDIA's 2020 revenues?"
  
  # Use different model
  python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --model development
  python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --model production_budget
  
  # Export full response to JSON
  python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --export-response
  
  # Skip context export (save disk space)
  python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --no-export-context
  
  # Disable MLflow tracking
  python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --no-tracking
  
  # Production run
  python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --environment production
  
  # View MLflow UI
  cd ModelPipeline && mlflow ui --backend-store-uri mlruns
        """
    )
    
    parser.add_argument(
        '--query', '-q',
        type=str,
        default=DEFAULT_QUERY,
        help='User question (default: production test query)'
    )
    
    parser.add_argument(
        '--model', '-m',
        type=str,
        default=None,
        help='Model key from ml_config.yaml (default: uses default_serving_model)'
    )
    
    parser.add_argument(
        '--no-export-context',
        action='store_true',
        help='Skip exporting context to file (saves disk space)'
    )
    
    parser.add_argument(
        '--export-response',
        action='store_true', default=True,  
        help='Export full response to JSON file (for debugging)'
    )
    
    # MLflow options
    parser.add_argument(
        '--no-tracking',
        action='store_true',
        help='Disable MLflow tracking'
    )
    
    parser.add_argument(
        '--experiment', '-e',
        type=str,
        default="FinRAG-Integration",
        help='MLflow experiment name (default: FinRAG-Integration)'
    )
    
    parser.add_argument(
        '--environment',
        type=str,
        choices=['development', 'production'],
        default='development',
        help='Environment tag for MLflow (default: development)'
    )
    
    args = parser.parse_args()
    
    # Find project root
    try:
        model_root = find_model_root()
        print(f"ModelPipeline root: {model_root}")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    # Display query info
    print(f"\nProcessing query...")
    # if args.model:
    #     print(f"  Model: {args.model}")
    # else:
    #     print(f"  Model: default (development_CH45 - Claude 4.5 Haiku)")
    # print()
    
    # Show model info
    try:
        resolved_key, model_config = load_model_config_display(model_root, args.model)
        print(f"  Model: {resolved_key} ({model_config.get('display_name', 'Unknown')})")
    except Exception as e:
        print(f"  Model: {args.model or 'default'}")
    
    # Show tracking info
    if not args.no_tracking:
        print(f"  MLflow: {args.experiment} ({args.environment})")
    else:
        print(f"  MLflow: disabled")
        
    print()
    
    # Process query
    # try:
    #     result = answer_query(
    #         query=args.query,
    #         model_root=model_root,
    #         include_kpi=True,                          
    #         include_rag=True,                          
    #         model_key=args.model,
    #         export_context=not args.no_export_context,
    #         export_response=args.export_response
    #     )
        
    #     # Display result
    #     print_result(result)
    try:
        if args.no_tracking:
            result, run_url = run_without_tracking(
                query=args.query,
                model_root=model_root,
                model_key=args.model,
                include_kpi=True,
                include_rag=True,
                export_context=not args.no_export_context,
                export_response=args.export_response
            )
        else:
            result, run_url = run_with_tracking(
                query=args.query,
                model_root=model_root,
                model_key=args.model,
                include_kpi=True,
                include_rag=True,
                export_context=not args.no_export_context,
                export_response=args.export_response,
                experiment_name=args.experiment,
                environment=args.environment
            )
        
        # Display result
        print_result(
            result,
            show_mlflow_info=not args.no_tracking,
            run_url=run_url
        )
           
        # Exit code
        sys.exit(0 if not is_error_response(result) else 1)
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()