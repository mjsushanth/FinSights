# # ModelPipeline\finrag_ml_tg1\rag_modules_src\synthesis_pipeline\orchestrator.py

# from __future__ import annotations

# import json
# from typing import Dict, Optional, List
# import logging
# import concurrent.futures
# from pathlib import Path

# from finrag_ml_tg1.loaders.ml_config_loader import MLConfig
# from finrag_ml_tg1.rag_modules_src.metric_pipeline.src.pipeline import MetricPipeline
# from finrag_ml_tg1.rag_modules_src.utilities.query_embedder_v2 import QueryEmbedderV2
# from .bedrock_client import BedrockClient

# logger = logging.getLogger(__name__)




# class QueryOrchestrator:  
#     """Main orchestration pipeline for the RAG system."""
    
#     def __init__(self, config: Dict = None, config_path: str = None):
#         """
#         Initialize all components.
        
#         Args:
#             config: Configuration dictionary (optional)
#             config_path: Path to config YAML file (optional)
#         """
#         # Load configuration
#         if config is None:
#             if config_path is None:
#                 config_path = os.path.join(
#                     os.path.dirname(__file__), 
#                     '../../.aws_config/ml_config.yaml'
#                 )
#             ml_config = MLConfig(config_path)
#             self.config = ml_config.cfg
#             self.ml_config = ml_config
#         else:
#             self.config = config
#             self.ml_config = None
        
#         self.orchestrator_config = self.config.get('rag_orchestrator', {})
        
#         # Initialize components
#         self._init_embedder()
#         self._init_llm_client()
#         self._init_external_components()
        
#         logger.info("QueryOrchestrator initialized successfully")
    
#     def _init_embedder(self):
#         """Initialize query embedder."""
#         query_config = self.orchestrator_config.get('query_embedding', {})
#         self.embedder = QueryEmbedder(
#             region=query_config.get('region', 'us-east-1'),
#             model_id=query_config.get('model_id', 'cohere.embed-v4:0')
#         )
    
#     def _init_llm_client(self):
#         """Initialize LLM client."""
#         llm_config = self.orchestrator_config.get('llm', {})
#         self.llm_client = BedrockClient(
#             region=llm_config.get('region', 'us-east-1'),
#             model_id=llm_config.get('model_id', 'anthropic.claude-sonnet-4-20250514'),
#             max_tokens=llm_config.get('max_tokens', 4096),
#             temperature=llm_config.get('temperature', 0.7)
#         )
    
#     def _init_external_components(self):
#         """Initialize external pipeline components."""
#         try:
#             # Initialize metric pipeline with paths
#             base_path = Path(__file__).resolve().parents[2]  # Go to rag_modules_src
#             metrics_data_path = base_path / "rag_modules_src"/"metric_pipeline" / "data" / "downloaded_data.json"
#             company_dim_path = base_path / "data_cache" / "dimensions" / "finrag_dim_companies_21.parquet"
            
#             self.metric_pipeline = MetricPipeline(
#                 data_path=str(metrics_data_path),
#                 company_dim_path=str(company_dim_path)
#             )
#             logger.info("Metric pipeline initialized successfully")
#         except Exception as e:
#             logger.warning(f"Metric pipeline initialization failed: {e}")
#             self.metric_pipeline = None
        
#         # RAG search - placeholder until teammate's module is ready
#         self.rag_search = None
    
#     def process_query(self, user_query: str, parallel: bool = None) -> Dict:
#         """
#         Main pipeline execution.
        
#         Args:
#             user_query: User's question string
#             parallel: Whether to run steps 2&3 in parallel
            
#         Returns:
#             Dictionary with response and metadata
#         """
#         logger.info(f"Processing query: '{user_query}'")
        
#         if parallel is None:
#             parallel = self.orchestrator_config.get('execution', {}).get('parallel_processing', True)
        
#         if parallel:
#             with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
#                 metric_future = executor.submit(self._extract_metrics, user_query)
#                 embedding_future = executor.submit(self._generate_embedding, user_query)
                
#                 analytical_results = metric_future.result()
#                 query_embedding = embedding_future.result()
#         else:
#             analytical_results = self._extract_metrics(user_query)
#             query_embedding = self._generate_embedding(user_query)
        
#         # Extract filters for S3 metadata filtering (future use)
#         s3_filters = self._extract_s3_filters(analytical_results)
        
#         # Vector search (currently mock)
#         rag_context = self._search_documents(query_embedding, s3_filters)
        
#         # Generate final response
#         final_response = self._generate_response(user_query, analytical_results, rag_context)
        
#         return {
#             'query': user_query,
#             'response': final_response,
#             'metadata': {
#                 'analytical_results': analytical_results,
#                 's3_filters': s3_filters,
#                 'num_context_chunks': len(rag_context) if rag_context else 0,
#                 'top_sources': self._extract_top_sources(rag_context),
#                 'has_analytical_data': analytical_results is not None and len(analytical_results) > 0,  # String check
#                 'has_rag_context': bool(rag_context)
#             }
#         }
    
#     def _extract_metrics(self, query: str) -> Optional[Dict]:
#         """
#         Step 2: Extract metrics from query using MetricPipeline.
        
#         Returns:
#             Compact analytical results or None
#         """
#         if not self.metric_pipeline:
#             logger.warning("Metric pipeline not available")
#             return None
        
#         try:
#             # Run metric pipeline
#             result = self.metric_pipeline.process(query)
            
#             if not result.get('success', False):
#                 logger.info(f"Metric pipeline: {result.get('reason', 'No data')}")
#                 return None
            
#             # Format results compactly for LLM
#             compact_result = self._format_analytical_compact(result)
            
#             # === NEW: Print what's being sent to LLM ===
#             print("\n" + "="*60)
#             print("📊 METRIC PIPELINE OUTPUT → LLM")
#             print("="*60)
#             print(json.dumps(compact_result, indent=2))
#             print("="*60 + "\n")
            
#             logger.info(f"Extracted {result.get('count', 0)} data points from metric pipeline")
#             return compact_result
        
#         except Exception as e:
#             logger.error(f"Metric extraction failed: {e}", exc_info=True)
#             return None
    
#     def _format_analytical_compact(self, raw_result: Dict) -> Optional[str]:
#         """
#         Format metric pipeline output as PURE STRING to minimize LLM tokens.
        
#         Format: "TICKER YEAR: metric1=$X, metric2=$Y"
        
#         Args:
#             raw_result: Raw output from metric_pipeline.process()
            
#         Returns:
#             Ultra-compact string or None
#         """
#         if not raw_result.get('success'):
#             return None
        
#         data = raw_result.get('data', [])
        
#         if not data:
#             return None
        
#         # Group by ticker and year
#         from collections import defaultdict
#         grouped = defaultdict(lambda: defaultdict(dict))
        
#         for item in data:
#             if item.get('found'):
#                 ticker = item['ticker']
#                 year = item['year']
#                 metric = item['metric']
#                 value = item['value']
                
#                 # Ultra-short metric names (remove prefixes and underscores)
#                 metric_short = (metric.replace('income_stmt_', '')
#                                     .replace('balance_sheet_', '')
#                                     .replace('cash_flow_', '')
#                                     .replace('_', ''))
                
#                 grouped[ticker][year][metric_short] = value
        
#         # Convert to string format
#         lines = []
#         for ticker, years_data in sorted(grouped.items()):
#             for year, metrics in sorted(years_data.items()):
#                 # Format values compactly
#                 metrics_str = ', '.join([
#                     f"{k}={self._format_value_compact(v)}" 
#                     for k, v in metrics.items()
#                 ])
#                 lines.append(f"{ticker} {year}: {metrics_str}")
        
#         return '\n'.join(lines)

#     def _format_value_compact(self, value: float) -> str:
#         """Format financial values ultra-compactly."""
#         if abs(value) >= 1_000_000_000:
#             return f"${value/1_000_000_000:.1f}B"
#         elif abs(value) >= 1_000_000:
#             return f"${value/1_000_000:.1f}M"
#         elif abs(value) >= 1_000:
#             return f"${value/1_000:.0f}K"
#         else:
#             return f"${value:.0f}"
    
#     def _extract_s3_filters(self, analytical_results: Optional[str]) -> Dict:
#         """
#         Extract clean S3 metadata filters from analytical results string.
        
#         Args:
#             analytical_results: Compact string format "TICKER YEAR: ..."
            
#         Returns:
#             Dictionary with S3 filter lists
#         """
#         if not analytical_results:
#             return {
#                 'tickers': [],
#                 'year': [],
#                 'sec_item_canonical': []
#             }
        
#         # Parse the string to extract tickers and years
#         import re
#         tickers = set()
#         years = set()
        
#         # Pattern: "TICKER YEAR: ..."
#         pattern = r'([A-Z]+)\s+(\d{4}):'
#         matches = re.findall(pattern, analytical_results)
        
#         for ticker, year in matches:
#             tickers.add(ticker)
#             years.add(int(year))
        
#         return {
#             'tickers': sorted(list(tickers)),
#             'year': sorted(list(years)),
#             'sec_item_canonical': []
#         }
    
#     def _generate_embedding(self, query: str) -> List[float]:
#         """Step 3: Generate query embedding."""
#         query_config = self.orchestrator_config.get('query_embedding', {})
#         embedding = self.embedder.embed_query(
#             query=query,
#             input_type=query_config.get('input_type', 'search_query')
#         )
#         logger.info(f"Generated query embedding (dim: {len(embedding)})")
#         return embedding
    
#     def _search_documents(self, embedding: List[float], s3_filters: Dict) -> List[Dict]:
#         """
#         Step 4: Vector search with metadata filtering.
        
#         Args:
#             embedding: Query embedding vector
#             s3_filters: Metadata filters (tickers, years, sections)
#         """
#         if not self.rag_search:
#             logger.warning("RAG search not available - using mock data")
#             # Mock data that respects filters if available
#             mock_data = [{
#                 'text': 'Mock SEC filing content about revenue growth and market conditions...',
#                 'company': s3_filters.get('tickers', ['AAPL'])[0] if s3_filters.get('tickers') else 'AAPL',
#                 'year': s3_filters.get('year', [2023])[0] if s3_filters.get('year') else 2023,
#                 'section': 'ITEM_7',
#                 'similarity_score': 0.85
#             }]
#             return mock_data
        
#         try:
#             search_config = self.orchestrator_config.get('vector_search', {})
            
#             # Call RAG search with metadata filters
#             results = self.rag_search.search(
#                 embedding=embedding,
#                 top_k=search_config.get('top_k', 10),
#                 metadata_filters=s3_filters  # Pass filters to S3 Vectors
#             )
#             logger.info(f"Found {len(results)} relevant chunks with filters: {s3_filters}")
#             return results
#         except Exception as e:
#             logger.error(f"Vector search failed: {e}")
#             raise
    
#     def _generate_response(self, query: str, analytical_results: Optional[Dict], 
#                           rag_context: List[Dict]) -> str:
#         """Step 5: Generate final response."""
#         response_config = self.orchestrator_config.get('response', {})
#         max_chunks = response_config.get('max_context_chunks', 5)
#         limited_context = rag_context[:max_chunks] if rag_context else []
        
#         response = self.llm_client.generate_response(
#             user_query=query,
#             analytical_results=analytical_results,
#             rag_context=limited_context
#         )
#         logger.info("Generated final response")
#         return response
    
#     def _extract_top_sources(self, rag_context: List[Dict]) -> List[Dict]:
#         """Extract top source metadata."""
#         if not rag_context:
#             return []
#         return [
#             {
#                 'company': chunk.get('company', 'Unknown'),
#                 'year': chunk.get('year', 'Unknown'),
#                 'section': chunk.get('section', 'Unknown'),
#                 'similarity_score': chunk.get('similarity_score', 0.0)
#             }
#             for chunk in rag_context[:3]
#         ]
    
#     def health_check(self) -> Dict[str, bool]:
#         """Check health status of all components."""
#         status = {
#             'config_loaded': bool(self.config),
#             'embedder': False,
#             'llm_client': False,
#             'metric_pipeline': self.metric_pipeline is not None,
#             'rag_search': self.rag_search is not None
#         }
        
#         try:
#             test_emb = self.embedder.embed_query("test")
#             status['embedder'] = len(test_emb) > 0
#         except:
#             pass
        
#         status['llm_client'] = self.llm_client is not None
        
#         logger.info(f"Health check: {status}")
#         return status


# def create_orchestrator(config_path: str = None) -> QueryOrchestrator:
#     """Factory function to create orchestrator."""
#     return QueryOrchestrator(config_path=config_path)




# """ Old- No sys hacks
# # Import your existing config loader
# sys.path.append(os.path.join(os.path.dirname(__file__), '../../loaders'))
# from ml_config_loader import MLConfig

# # Import metric pipeline
# sys.path.append(os.path.join(os.path.dirname(__file__), '../metric_pipeline'))
# from src.pipeline import MetricPipeline

# # Import local modules
# from utilities.query_embedder import QueryEmbedder
# from bedrock_client import BedrockClient

# logger = logging.getLogger(__name__)
# """
