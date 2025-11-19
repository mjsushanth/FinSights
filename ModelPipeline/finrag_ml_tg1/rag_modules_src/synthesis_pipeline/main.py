# ModelPipeline\finrag_ml_tg1\rag_modules_src\synthesis_pipeline\main.py

"""
FinRAG CLI Demo - End-to-end query answering.

Usage:
    python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main
    python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --query "Your question"
    python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --model development
    python -m finrag_ml_tg1.rag_modules_src.synthesis_pipeline.main --export-response

Philosophy:
    - Minimal console output (not a log dumper)
    - Points to export files (don't print 40K char contexts)
    - Shows preview of answer (first 500 chars)
    - Clean success/error handling
    - No emojis, no clutter
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.orchestrator import answer_query
from finrag_ml_tg1.rag_modules_src.synthesis_pipeline.models import is_error_response


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


def print_result(result: dict):
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
    
    print_separator()
    
    # Helpful tip
    print("\nTip: Full answer saved in exports. Context and logs available above.")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

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
    if args.model:
        print(f"  Model: {args.model}")
    else:
        print(f"  Model: default (development_CH45 - Claude 4.5 Haiku)")
    print()
    
    # Process query
    try:
        result = answer_query(
            query=args.query,
            model_root=model_root,
            include_kpi=True,                          
            include_rag=True,                          
            model_key=args.model,
            export_context=not args.no_export_context,
            export_response=args.export_response
        )
        
        # Display result
        print_result(result)
        
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