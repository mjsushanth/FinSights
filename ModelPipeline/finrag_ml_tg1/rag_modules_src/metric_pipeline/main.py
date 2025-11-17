"""
Entry point for the metric pipeline
"""

from src.pipeline import MetricPipeline
from pathlib import Path


def main():
    """Run the metric pipeline with example queries"""
    
    # Initialize pipeline
    print("Initializing Metric Pipeline...")
    
    # Set paths
    metrics_data_path = 'data/downloaded_data.json'
    
    # Optional: specify company dimension path
    # If None, FilterExtractor will use default path
    base_path = Path(__file__).resolve().parents[1]  # Go up to rag_modules_src
    company_dim_path = base_path / "data_cache" / "dimensions" / "finrag_dim_companies_21.parquet"
    
    pipeline = MetricPipeline(
        data_path=metrics_data_path,
        company_dim_path=company_dim_path
    )
    print()
    
    # Example queries - NOW WITH MULTI-COMPANY SUPPORT
    test_queries = [
        # Single company, single year
        "What is NVIDIA's revenue in 2024?",
        
        # Multiple companies (by name), single year
        "Compare Apple and Microsoft revenue in 2023",
        
        # Multiple companies, multiple metrics
        "Show me NVDA and AAPL profit and revenue in 2023",
        
        # Year range
        "NVIDIA revenue from 2020 to 2023",
        
        # Complex: multiple companies, years, metrics
        "What was Apple's, Microsoft's, and Nvidia's revenue and net income in 2021, 2022, and 2023?",
        
        # Fuzzy company name matching
        "Compare nvida and microsft total assets in 2022",
        
        # Should skip metric layer
        "Tell me about AI trends",
    ]
    
    print("=" * 60)
    print("TESTING METRIC PIPELINE")
    print("=" * 60)
    print()
    
    for i, query in enumerate(test_queries, 1):
        print(f"\n{'─' * 60}")
        print(f"Query {i}: {query}")
        print('─' * 60)
        
        # Process query
        result = pipeline.process(query)
        
        # Format and print response
        response = pipeline.format_response(result)
        print(response)
    
    print("\n" + "=" * 60)
    print("INTERACTIVE MODE")
    print("=" * 60)
    print("Enter queries (or 'quit' to exit):\n")
    
    while True:
        query = input("Query: ").strip()
        
        if query.lower() in ['quit', 'exit', 'q']:
            print("\nGoodbye!")
            break
        
        if not query:
            continue
        
        result = pipeline.process(query)
        response = pipeline.format_response(result)
        print(f"\n{response}\n")


if __name__ == "__main__":
    main()