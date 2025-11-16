"""
Main metric pipeline orchestration
"""

from typing import Dict, Optional
import re

## old- imports.
# from src.filter_extractor import FilterExtractor, simple_fuzzy_match
# from src.metric_lookup import MetricLookup
# from config.metric_mappings import METRIC_KEYWORDS, QUANTITATIVE_INDICATORS

# new- imports. relative structure.
from .filter_extractor import FilterExtractor, simple_fuzzy_match
from .metric_lookup import MetricLookup
from ..config.metric_mappings import METRIC_KEYWORDS

class MetricPipeline:
    """Orchestrate the full metric extraction and lookup pipeline"""
    
    def __init__(self, data_path: str):
        """
        Initialize pipeline
        
        Args:
            data_path: Path to metrics JSON data
        """
        self.extractor = FilterExtractor()
        self.lookup = MetricLookup(data_path)
    
    def needs_metric_layer(self, query: str) -> bool:
        """
        Determine if query requires metric lookup with FULL FUZZY MATCHING
        Handles any typo in metric keywords automatically
        
        Args:
            query: User's query string
            
        Returns:
            True if metric layer should be activated
        """
        query_lower = query.lower()
        
        # Check for quantitative indicators (exact match is fine)
        has_quantitative = any(ind in query_lower for ind in QUANTITATIVE_INDICATORS)
        
        # Check for year
        has_year = bool(re.search(r'\b(19|20)\d{2}\b', query))
        
        # Check for ticker
        has_ticker = bool(re.search(r'\b[A-Za-z]{2,5}\b', query))
        
        # Check for metric keywords with fuzzy matching
        has_metric = False
        
        # First try exact match (fast)
        if any(keyword in query_lower for keyword in METRIC_KEYWORDS):
            has_metric = True
        else:
            # Fuzzy match each word against metric keywords
            words = query_lower.split()
            
            for word in words:
                # Skip very short words and common words
                if len(word) < 4:
                    continue
                if word in ['the', 'and', 'what', 'how', 'was', 'is', 'are', 'were', 'from', 'with', 'that', 'this']:
                    continue
                if word.isdigit():
                    continue
                
                best_match, score = simple_fuzzy_match(
                    word,
                    METRIC_KEYWORDS,
                    threshold=0.70  # 70% similarity
                )
                
                if best_match and score >= 70:
                    has_metric = True
                    break
        
        # Trigger if: (has_metric AND (year OR ticker)) OR (quantitative AND ticker)
        return (has_metric and (has_year or has_ticker)) or \
               (has_quantitative and has_ticker)
    
    def process(self, query: str) -> Dict[str, any]:
        """
        Main processing pipeline
        
        Args:
            query: User's natural language query
            
        Returns:
            Dictionary with results or error information
        """
        # Step 1: Check if metric layer needed
        if not self.needs_metric_layer(query):
            return {
                'success': False,
                'reason': 'Query does not require metric lookup',
                'query': query
            }
        
        # Step 2: Extract filters
        filters = self.extractor.extract(query)
        
        # Step 3: Validate filters
        if not self.extractor.is_valid(filters):
            return {
                'success': False,
                'reason': 'Could not extract all required filters (ticker, year, metrics)',
                'extracted_filters': filters,
                'query': query
            }
        
        # Step 4: Lookup data for ALL metrics
        results = self.lookup.query_multiple(
            ticker=filters['ticker'],
            year=filters['year'],
            metrics=filters['metrics']
        )
        
        # Step 5: Handle results
        if not results:
            return {
                'success': False,
                'reason': 'No data found for any of the requested metrics',
                'filters': filters,
                'query': query
            }
        
        # Filter out None results and results with no data
        valid_results = [r for r in results if r and r.get('found', False)]
        
        if not valid_results:
            return {
                'success': False,
                'reason': 'Data found but all values are missing/NaN',
                'filters': filters,
                'query': query
            }
        
        # Success!
        return {
            'success': True,
            'data': valid_results,  # Returns a LIST of results
            'filters': filters,
            'query': query,
            'count': len(valid_results)
        }
    
    def format_response(self, pipeline_result: Dict[str, any]) -> str:
        """
        Format pipeline result into human-readable response
        
        Args:
            pipeline_result: Output from process() method
            
        Returns:
            Formatted string response
        """
        if not pipeline_result['success']:
            msg = f"❌ {pipeline_result['reason']}\n"
            msg += f"Query: '{pipeline_result['query']}'\n"
            
            if 'extracted_filters' in pipeline_result:
                filters = pipeline_result['extracted_filters']
                msg += f"\nExtracted filters:\n"
                msg += f"  - Ticker: {filters.get('ticker', 'NOT FOUND')}\n"
                msg += f"  - Year: {filters.get('year', 'NOT FOUND')}\n"
                msg += f"  - Metrics: {filters.get('metrics', 'NOT FOUND')}\n"
            
            if 'available_years' in pipeline_result:
                years = pipeline_result['available_years']
                if years:
                    msg += f"\n💡 Data available for years: {years}\n"
            
            return msg
        
        # Success case - handle multiple results
        data_list = pipeline_result['data']
        count = pipeline_result['count']
        
        msg = f"✓ Found {count} metric{'s' if count > 1 else ''}!\n"
        
        # Get ticker and year from first result (same for all)
        ticker = data_list[0]['ticker']
        year = data_list[0]['year']
        
        msg += f"\n{ticker} in {year}:\n"
        
        for data in data_list:
            value = data['value']
            metric_name = data['metric'].replace('_', ' ')
            
            # Format value based on magnitude
            if abs(value) >= 1_000_000_000:
                formatted_value = f"${value/1_000_000_000:.2f}B"
            elif abs(value) >= 1_000_000:
                formatted_value = f"${value/1_000_000:.2f}M"
            elif value < 0:
                formatted_value = f"-${abs(value):,.2f}"
            else:
                formatted_value = f"${value:,.2f}"
            
            msg += f"  • {metric_name}: {formatted_value}\n"
        
        return msg