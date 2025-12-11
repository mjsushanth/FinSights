"""
Entry point for the metric pipeline
ModelPipeline\finrag_ml_tg1\rag_modules_src\metric_pipeline\main.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# ============================================================================
# PATH SETUP - Ensure ModelPipeline root is in sys.path
# ============================================================================
def setup_paths():
    """Add ModelPipeline root to sys.path if not already there"""
    current = Path(__file__).resolve().parent  # metric_pipeline/
    
    # Navigate up to find ModelPipeline root
    for parent in [current] + list(current.parents):
        if parent.name == "ModelPipeline":
            model_root = parent
            break
    else:
        # Fallback: assume we're at metric_pipeline/, go up 3 levels
        model_root = current.parent.parent.parent
    
    if str(model_root) not in sys.path:
        sys.path.insert(0, str(model_root))
    
    return model_root

model_root = setup_paths()

# ============================================================================
# NOW IMPORT AFTER PATH IS SET
# ============================================================================
from finrag_ml_tg1.rag_modules_src.metric_pipeline.src.pipeline import MetricPipeline
from finrag_ml_tg1.loaders.data_loader_strategy import LocalCacheLoader


def main():
    """Run the metric pipeline with example queries"""
    
    # Initialize pipeline
    print("Initializing Metric Pipeline...")
    
    # Set paths relative to ModelPipeline root
    metrics_data_path = model_root / "finrag_ml_tg1/rag_modules_src/metric_pipeline/data/KPI_FACT_DATA_EDGAR.parquet"
    company_dim_path = model_root / "finrag_ml_tg1/data_cache/dimensions/finrag_dim_companies_21.parquet"
    
    # Check if files exist
    if not metrics_data_path.exists():
        print(f"❌ ERROR: KPI data file not found at:")
        print(f"   {metrics_data_path}")
        
        # Try alternative location
        alt_path = model_root / "finrag_ml_tg1/data_cache/KPI_FACT_DATA_EDGAR.parquet"
        if alt_path.exists():
            print(f"\n✅ Found at alternative location: {alt_path}")
            metrics_data_path = alt_path
        else:
            print(f"   Also tried: {alt_path}")
            return
    
    if not company_dim_path.exists():
        print(f"❌ ERROR: Company dimension file not found at:")
        print(f"   {company_dim_path}")
        return
    
    print(f"✅ Using KPI data: {metrics_data_path.name}")
    print(f"✅ Using company dim: {company_dim_path.name}")
    
    # Create data loader using your existing LocalCacheLoader
    # It needs model_root and config=None is fine for basic usage
    data_loader = LocalCacheLoader(
        model_root=model_root,
        config=None  # config is optional for basic file loading
    )
    
    # Override the paths in the loader instance
    data_loader._kpi_data_path = metrics_data_path
    data_loader._company_dim_path = company_dim_path
    
    # Initialize pipeline with data loader
    pipeline = MetricPipeline(data_loader=data_loader)
    
    print()
    
    # Example queries - UPDATED WITH WORKING METRICS
    test_queries = [
        # Single company, single year - USE METRICS THAT EXIST
        # "What is NVIDIA's net income in 2023?",
        
        # Multiple companies (by name), single year
        # "Compare Apple and Microsoft net income in 2023",
        
        # Multiple companies, multiple metrics
        # "Show me NVDA and AAPL net income and gross profit in 2023",
        
        # Year range
        # "NVIDIA net income from 2021 to 2023",
        
        # Complex: multiple companies, years, metrics
        # "What was Apple's, Microsoft's, and Nvidia's net income and gross profit in 2022 and 2023?",
        
        # Test Google alias (WILL FAIL until fixed)
        "What is Google's net income in 2023?",
        
        # Test Facebook alias (WILL FAIL until fixed)
        "What is Facebook's net income in 2023?",
        
        # Should skip metric layer
        # "Tell me about AI trends",
    ]
    
    print("=" * 70)
    print("TESTING METRIC PIPELINE")
    print("=" * 70)
    print()
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{'─' * 70}")
        print(f"Query {i}: {query}")
        print('─' * 70)
        
        # Process query
        result = pipeline.process(query)
        
        # Format and print response
        response = pipeline.format_response(result)
        print(response)
    
    print("\n" + "=" * 70)
    print("INTERACTIVE MODE")
    print("=" * 70)
    print("\nEnter queries (or 'quit' to exit):")
    print("Tip: Use 'net income', 'gross profit', 'operating cash flow'")
    print("     (Revenue data is incomplete in the dataset)\n")
    
    while True:
        try:
            query = input("Query: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nGoodbye!")
            break
        
        if query.lower() in ['quit', 'exit', 'q']:
            print("\nGoodbye!")
            break
        
        if not query:
            continue
        
        result = pipeline.process(query)
        response = pipeline.format_response(result)
        print(f"\n{response}\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()