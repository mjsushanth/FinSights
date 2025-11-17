import logging
import json
from orchestrator import create_orchestrator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point with test queries."""
    orchestrator = create_orchestrator()
    
    # Health check
    print("\n" + "="*60)
    print("HEALTH CHECK")
    print("="*60)
    health = orchestrator.health_check()
    for component, status in health.items():
        status_icon = "✓" if status else "✗"
        print(f"  {status_icon} {component}: {'OK' if status else 'FAILED'}")
    print()
    
    # Test queries
    test_queries = [
        "What were Microsoft's and NVIDIA's total assets and revenue from 2021 to 2023?",
    ]
    
    for i, query in enumerate(test_queries, 1):
        print("\n" + "="*70)
        print(f"QUERY {i}: {query}")
        print("="*70)
        
        try:
            result = orchestrator.process_query(query)
            
            # Show what metric pipeline sent to LLM (string format)
            if result['metadata'].get('analytical_results'):
                print("\n--- METRIC PIPELINE → LLM ---")
                analytical = result['metadata']['analytical_results']
                print(analytical)
                
                # Calculate token usage
                tokens = len(analytical) // 4
                print(f"\nToken estimate: ~{tokens} tokens")
            
            # Show S3 filters that were extracted
            if result['metadata'].get('s3_filters'):
                print("\n--- S3 METADATA FILTERS ---")
                filters = result['metadata']['s3_filters']
                print(f"Tickers: {filters.get('tickers', [])}")
                print(f"Years: {filters.get('year', [])}")
                if filters.get('sec_item_canonical'):
                    print(f"Sections: {filters.get('sec_item_canonical', [])}")
            
            # Show final LLM response
            print("\n--- FINAL LLM RESPONSE ---")
            print(result['response'])
            
            # Show metadata summary
            print("\n--- METADATA SUMMARY ---")
            metadata = result['metadata']
            print(f"  Has Analytical Data: {metadata['has_analytical_data']}")
            
            if metadata.get('analytical_results'):
                # Count data points (lines in the string)
                data_points = len(metadata['analytical_results'].strip().split('\n'))
                print(f"  Data Points: {data_points}")
            else:
                print(f"  Data Points: 0")
            
            print(f"  Has RAG Context: {metadata['has_rag_context']}")
            print(f"  Context Chunks: {metadata['num_context_chunks']}")
            
            if metadata.get('top_sources'):
                print(f"\n  Top Sources:")
                for idx, source in enumerate(metadata['top_sources'], 1):
                    print(f"    {idx}. {source['company']} {source['year']} "
                          f"{source['section']} (score: {source['similarity_score']:.2f})")
        
        except Exception as e:
            logger.error(f"Query failed: {e}", exc_info=True)
            print(f"\n❌ Error: {str(e)}")
    
    # Interactive mode
    print("\n" + "="*70)
    print("INTERACTIVE MODE")
    print("="*70)
    print("Enter queries (or 'quit' to exit):\n")
    
    while True:
        try:
            query = input("Query: ").strip()
            
            if query.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if not query:
                continue
            
            print("\nProcessing...\n")
            result = orchestrator.process_query(query)
            
            # Show metric pipeline output if available
            if result['metadata'].get('analytical_results'):
                print("--- METRIC DATA ---")
                print(result['metadata']['analytical_results'])
                print()
            
            # Show response
            print("--- RESPONSE ---")
            print(result['response'])
            print()
        
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            logger.error(f"Query failed: {e}", exc_info=True)
            print(f"\n❌ Error: {str(e)}\n")


if __name__ == "__main__":
    main()