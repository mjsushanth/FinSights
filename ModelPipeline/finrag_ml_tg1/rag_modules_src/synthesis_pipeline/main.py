import logging
from orchestrator import create_orchestrator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point."""
    orchestrator = create_orchestrator()
    
    # Health check
    print("\nHealth Status:", orchestrator.health_check())
    
    # Test query
    query = "What was Apple's revenue in 2023?"
    print(f"\nQuery: {query}")
    
    result = orchestrator.process_query(query)
    print(f"\nResponse: {result['response']}")
    print(f"\nMetadata: {result['metadata']}")


if __name__ == "__main__":
    main()