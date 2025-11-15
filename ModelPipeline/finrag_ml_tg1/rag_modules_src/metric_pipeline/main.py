"""
Entry point for the metric pipeline
"""

from src.pipeline import MetricPipeline


def main():
    """Run the metric pipeline with example queries"""
    
    # Initialize pipeline
    print("Initializing Metric Pipeline...")
    pipeline = MetricPipeline(data_path='data/downloaded_data.json')
    print()
    
    # Example queries
    test_queries = [
        "What is NVIDIA's revenue in the year 2024?",
        "What was NVDA's net income in 2023?",
        "Show me NVDA profit and revenue in 2013",  # Multiple metrics
        "MSFT total assets and liabilities 2025",  # Multiple metrics
        "What are nvidia's current assets, liabilities, and equity in 2022?",  # 3 metrics
        "Microsoft operating cash flow 2022",
        "Show me NVDA gross profit margin for 2025",
        "Tell me about AI trends",  # Should skip metric layer
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