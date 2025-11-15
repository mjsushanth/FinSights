import sys
import os
import json
from typing import Dict, Optional, List
import logging
import concurrent.futures
from pathlib import Path

# Import your existing config loader
sys.path.append(os.path.join(os.path.dirname(__file__), '../../loaders'))
from ml_config_loader import MLConfig

# Import external pipelines
# sys.path.append(os.path.join(os.path.dirname(__file__), '../metric_pipeline/src'))
# from pipeline import MetricPipeline  

# Import local modules
from query_embedder import QueryEmbedder
from bedrock_client import BedrockClient

logger = logging.getLogger(__name__)


class QueryOrchestrator:  
    """Main orchestration pipeline for the RAG system."""
    
    def __init__(self, config: Dict = None, config_path: str = None):
        """
        Initialize all components.
        
        Args:
            config: Configuration dictionary (optional)
            config_path: Path to config YAML file (optional)
        """
        # Load configuration
        if config is None:
            if config_path is None:
                config_path = os.path.join(
                    os.path.dirname(__file__), 
                    '../../.aws_config/ml_config.yaml'
                )
            ml_config = MLConfig(config_path)
            self.config = ml_config.cfg  # Access the cfg attribute
            self.ml_config = ml_config  # Keep reference to MLConfig object
        else:
            self.config = config
            self.ml_config = None
        
        self.orchestrator_config = self.config.get('rag_orchestrator', {})
        
        # Initialize components
        self._init_embedder()
        self._init_llm_client()
        self._init_external_components()
        
        logger.info("QueryOrchestrator initialized successfully")
    
    def _init_embedder(self):
        """Initialize query embedder."""
        query_config = self.orchestrator_config.get('query_embedding', {})
        self.embedder = QueryEmbedder(
            region=query_config.get('region', 'us-east-1'),
            model_id=query_config.get('model_id', 'cohere.embed-v4:0')
        )
    
    def _init_llm_client(self):
        """Initialize LLM client."""
        llm_config = self.orchestrator_config.get('llm', {})
        self.llm_client = BedrockClient(
            region=llm_config.get('region', 'us-east-1'),
            model_id=llm_config.get('model_id', 'anthropic.claude-sonnet-4-20250514'),
            max_tokens=llm_config.get('max_tokens', 4096),
            temperature=llm_config.get('temperature', 0.7)
        )
    
    def _init_external_components(self):
        """Initialize external pipeline components."""
        try:
            self.metric_extractor = MetricPipeline()  # Using the aliased class
            logger.info("Metric extractor initialized")
        except Exception as e:
            logger.warning(f"Metric extractor initialization failed: {e}")
            self.metric_extractor = None
        
        # RAG search - placeholder until teammate's module is ready
        self.rag_search = None
    
    def process_query(self, user_query: str, parallel: bool = None) -> Dict:
        """
        Main pipeline execution.
        
        Args:
            user_query: User's question string
            parallel: Whether to run steps 2&3 in parallel
            
        Returns:
            Dictionary with response and metadata
        """
        logger.info(f"Processing query: '{user_query}'")
        
        if parallel is None:
            parallel = self.orchestrator_config.get('execution', {}).get('parallel_processing', True)
        
        if parallel:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                metric_future = executor.submit(self._extract_metrics, user_query)
                embedding_future = executor.submit(self._generate_embedding, user_query)
                
                analytical_results = metric_future.result()
                query_embedding = embedding_future.result()
        else:
            analytical_results = self._extract_metrics(user_query)
            query_embedding = self._generate_embedding(user_query)
        
        rag_context = self._search_documents(query_embedding)
        final_response = self._generate_response(user_query, analytical_results, rag_context)
        
        return {
            'query': user_query,
            'response': final_response,
            'metadata': {
                'analytical_results': analytical_results,
                'num_context_chunks': len(rag_context) if rag_context else 0,
                'top_sources': self._extract_top_sources(rag_context),
                'has_analytical_data': analytical_results is not None and bool(analytical_results.get('data')),
                'has_rag_context': bool(rag_context)
            }
        }
    
    def _extract_metrics(self, query: str) -> Optional[Dict]:
        """Step 2: Extract metrics from query."""
        if not self.metric_extractor:
            return None
        try:
            # Check what method the metric pipeline uses - might be .extract(), .process(), or .run()
            results = self.metric_extractor.extract(query)
            logger.info(f"Extracted metrics: {results}")
            return results
        except Exception as e:
            logger.warning(f"Metric extraction failed: {e}")
            return None
    
    def _generate_embedding(self, query: str) -> List[float]:
        """Step 3: Generate query embedding."""
        query_config = self.orchestrator_config.get('query_embedding', {})
        embedding = self.embedder.embed_query(
            query=query,
            input_type=query_config.get('input_type', 'search_query')
        )
        logger.info(f"Generated query embedding (dim: {len(embedding)})")
        return embedding
    
    def _search_documents(self, embedding: List[float]) -> List[Dict]:
        """Step 4: Vector search."""
        if not self.rag_search:
            logger.warning("RAG search not available - using mock data")
            return [{
                'text': 'Mock SEC filing content...',
                'company': 'AAPL',
                'year': 2023,
                'section': 'ITEM_1A',
                'similarity_score': 0.85
            }]
        
        try:
            search_config = self.orchestrator_config.get('vector_search', {})
            results = self.rag_search.search(
                embedding=embedding,
                top_k=search_config.get('top_k', 10)
            )
            logger.info(f"Found {len(results)} relevant chunks")
            return results
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise
    
    def _generate_response(self, query: str, analytical_results: Optional[Dict], 
                          rag_context: List[Dict]) -> str:
        """Step 5: Generate final response."""
        response_config = self.orchestrator_config.get('response', {})
        max_chunks = response_config.get('max_context_chunks', 5)
        limited_context = rag_context[:max_chunks] if rag_context else []
        
        response = self.llm_client.generate_response(
            user_query=query,
            analytical_results=analytical_results,
            rag_context=limited_context
        )
        logger.info("Generated final response")
        return response
    
    def _extract_top_sources(self, rag_context: List[Dict]) -> List[Dict]:
        """Extract top source metadata."""
        if not rag_context:
            return []
        return [
            {
                'company': chunk.get('company', 'Unknown'),
                'year': chunk.get('year', 'Unknown'),
                'section': chunk.get('section', 'Unknown'),
                'similarity_score': chunk.get('similarity_score', 0.0)
            }
            for chunk in rag_context[:3]
        ]
    
    def health_check(self) -> Dict[str, bool]:
        """Check health status of all components."""
        status = {
            'config_loaded': bool(self.config),
            'embedder': False,
            'llm_client': False,
            'metric_extractor': self.metric_extractor is not None,
            'rag_search': self.rag_search is not None
        }
        
        try:
            test_emb = self.embedder.embed_query("test")
            status['embedder'] = len(test_emb) > 0
        except:
            pass
        
        status['llm_client'] = self.llm_client is not None
        
        logger.info(f"Health check: {status}")
        return status


def create_orchestrator(config_path: str = None) -> QueryOrchestrator:
    """Factory function to create orchestrator."""
    return QueryOrchestrator(config_path=config_path)