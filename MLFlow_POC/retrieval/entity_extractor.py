"""
Robust entity extraction for financial queries.
Extracts tickers, metrics, years, and other entities from natural language.
"""
import re
from typing import List, Optional, Set, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from data.loaders import data_loader


@dataclass
class ExtractedEntities:
    """Container for extracted entities from query"""
    ticker: Optional[str] = None
    metrics: List[str] = None
    years: List[int] = None
    year_range: Optional[tuple] = None
    comparison_terms: List[str] = None
    
    def __post_init__(self):
        """Initialize empty lists"""
        if self.metrics is None:
            self.metrics = []
        if self.years is None:
            self.years = []
        if self.comparison_terms is None:
            self.comparison_terms = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "ticker": self.ticker,
            "metrics": self.metrics,
            "years": self.years,
            "year_range": self.year_range,
            "comparison_terms": self.comparison_terms
        }


class EntityExtractor:
    """
    Extract financial entities from natural language queries.
    Updated to match actual parquet file structure.
    """
    
    def __init__(self):
        """Initialize entity extractor with financial knowledge"""
        
        # Common ticker symbols and company names
        self.ticker_mapping = {
            "nvidia": "NVDA",
            "nvda": "NVDA",
            "apple": "AAPL",
            "aapl": "AAPL",
            "microsoft": "MSFT",
            "msft": "MSFT",
            "google": "GOOGL",
            "alphabet": "GOOGL",
            "amazon": "AMZN",
            "amzn": "AMZN",
            "tesla": "TSLA",
            "tsla": "TSLA",
            "meta": "META",
            "facebook": "META",
        }
        
        # Financial metric mappings (term -> actual metric names in parquet)
        self.metric_mappings = {
            # Revenue
            "revenue": ["income_stmt_Revenue"],
            "sales": ["income_stmt_Revenue"],
            "top line": ["income_stmt_Revenue"],
            "topline": ["income_stmt_Revenue"],
            "total revenue": ["income_stmt_Revenue"],
            
            # Profit metrics
            "profit": ["income_stmt_Net Income", "income_stmt_Gross Profit"],
            "net income": ["income_stmt_Net Income"],
            "net profit": ["income_stmt_Net Income"],
            "earnings": ["income_stmt_Net Income"],
            "bottom line": ["income_stmt_Net Income"],
            "bottomline": ["income_stmt_Net Income"],
            "gross profit": ["income_stmt_Gross Profit"],
            
            # Cost metrics
            "cost of revenue": ["income_stmt_Cost of Revenue"],
            "cogs": ["income_stmt_Cost of Revenue"],
            "cost of goods sold": ["income_stmt_Cost of Revenue"],
            "operating expenses": ["income_stmt_Operating Expenses"],
            "opex": ["income_stmt_Operating Expenses"],
            
            # Margins
            "margin": ["Gross Profit Margin %"],
            "gross margin": ["Gross Profit Margin %"],
            "profit margin": ["Gross Profit Margin %"],
            
            # Returns
            "roa": ["Return on Assets (ROA) %"],
            "return on assets": ["Return on Assets (ROA) %"],
            
            # Balance sheet - Assets
            "assets": ["balance_sheet_Total Assets"],
            "total assets": ["balance_sheet_Total Assets"],
            "current assets": ["balance_sheet_Current Assets"],
            
            # Balance sheet - Liabilities
            "liabilities": ["balance_sheet_Total Liabilities"],
            "total liabilities": ["balance_sheet_Total Liabilities"],
            "current liabilities": ["balance_sheet_Current Liabilities"],
            
            # Balance sheet - Equity
            "equity": ["balance_sheet_Stockholders Equity"],
            "shareholders equity": ["balance_sheet_Stockholders Equity"],
            "stockholders equity": ["balance_sheet_Stockholders Equity"],
            "shareholder equity": ["balance_sheet_Stockholders Equity"],
            
            # Cash flow
            "cash flow": ["cash_flow_Operating Cash Flow"],
            "operating cash flow": ["cash_flow_Operating Cash Flow"],
            "ocf": ["cash_flow_Operating Cash Flow"],
            "investing cash flow": ["cash_flow_Investing Cash Flow"],
            "financing cash flow": ["cash_flow_Financing Cash Flow"],
            "free cash flow": ["cash_flow_Operating Cash Flow"],  # Can be calculated
            "fcf": ["cash_flow_Operating Cash Flow"],
            
            # Tax
            "tax": ["income_stmt_Provision for Income Tax"],
            "income tax": ["income_stmt_Provision for Income Tax"],
            "provision for income tax": ["income_stmt_Provision for Income Tax"],
            
            # Interest
            "interest": ["income_stmt_Interest Expense"],
            "interest expense": ["income_stmt_Interest Expense"],
        }
        
        # Comparison and trend terms
        self.comparison_terms_set = {
            "trend", "trends", "growth", "decline", "change", "increase", "decrease",
            "vs", "versus", "compared to", "compare", "comparison",
            "yoy", "year over year", "year-over-year",
            "qoq", "quarter over quarter",
            "cagr", "compound annual growth rate",
            "improve", "improvement", "worsen", "deteriorate"
        }
        
        # Load available data context
        self._load_available_entities()
    
    def _load_available_entities(self):
        """Load available tickers and metrics from data"""
        try:
            data_context = data_loader.load_all()
            self.available_tickers = set(data_context.metrics.ticker.unique())
            
            # Build metric name index (lowercase for matching)
            self.available_metrics_index = {}
            for ticker in self.available_tickers:
                metrics = data_context.metrics[
                    data_context.metrics.ticker == ticker
                ].metric.unique()
                for metric in metrics:
                    key = metric.lower()
                    if key not in self.available_metrics_index:
                        self.available_metrics_index[key] = []
                    self.available_metrics_index[key].append(metric)
            
            print(f"✅ Loaded {len(self.available_tickers)} tickers, "
                  f"{len(self.available_metrics_index)} unique metrics")
        except Exception as e:
            print(f"⚠️ Could not load data context: {e}")
            self.available_tickers = set()
            self.available_metrics_index = {}
    
    def extract(self, query: str) -> ExtractedEntities:
        """
        Extract all entities from a financial query.
        
        Args:
            query: Natural language financial question
            
        Returns:
            ExtractedEntities object
        """
        entities = ExtractedEntities()
        query_lower = query.lower()
        
        # Extract ticker
        entities.ticker = self._extract_ticker(query_lower)
        
        # Extract metrics
        entities.metrics = self._extract_metrics(query_lower, entities.ticker)
        
        # Extract years
        entities.years = self._extract_years(query)
        
        # Extract year range
        entities.year_range = self._extract_year_range(query)
        
        # Extract comparison terms
        entities.comparison_terms = self._extract_comparison_terms(query_lower)
        
        return entities
    
    def _extract_ticker(self, query_lower: str) -> Optional[str]:
        """
        Extract ticker symbol from query.
        
        Args:
            query_lower: Lowercase query string
            
        Returns:
            Ticker symbol or None
        """
        # Check for explicit ticker mentions
        for term, ticker in self.ticker_mapping.items():
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, query_lower):
                return ticker
        
        # Check for uppercase tickers (e.g., "NVDA")
        ticker_pattern = r'\b([A-Z]{2,5})\b'
        matches = re.findall(ticker_pattern, query_lower.upper())
        for match in matches:
            if match in self.available_tickers:
                return match
        
        # Default to NVDA if no ticker found
        return "NVDA"
    
    def _extract_metrics(self, query_lower: str, ticker: Optional[str]) -> List[str]:
        """
        Extract metric names from query.
        
        Args:
            query_lower: Lowercase query string
            ticker: Extracted ticker symbol
            
        Returns:
            List of actual metric names from parquet file
        """
        found_metrics = set()
        
        # Try to match against metric mappings
        for term, possible_metrics in self.metric_mappings.items():
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, query_lower):
                # Verify metrics exist in data
                for metric in possible_metrics:
                    if self._metric_exists(metric, ticker):
                        found_metrics.add(metric)
        
        # Try fuzzy matching against available metrics
        if ticker and not found_metrics:
            found_metrics.update(self._fuzzy_match_metrics(query_lower, ticker))
        
        return sorted(list(found_metrics))
    
    def _metric_exists(self, metric: str, ticker: Optional[str]) -> bool:
        """Check if metric exists in available data"""
        metric_lower = metric.lower()
        
        # Check in index
        if metric_lower in self.available_metrics_index:
            return True
        
        # Check for partial matches
        for available_metric in self.available_metrics_index.keys():
            if metric_lower in available_metric or available_metric in metric_lower:
                return True
        
        return False
    
    def _fuzzy_match_metrics(self, query_lower: str, ticker: str) -> Set[str]:
        """
        Fuzzy match query terms to available metrics.
        
        Args:
            query_lower: Lowercase query string
            ticker: Ticker symbol
            
        Returns:
            Set of matched metric names
        """
        matched = set()
        query_words = set(query_lower.split())
        
        for metric_key, metric_names in self.available_metrics_index.items():
            metric_words = set(metric_key.split())
            
            # Check for word overlap
            overlap = query_words & metric_words
            if len(overlap) > 0:
                # Add the first matching metric name
                matched.add(metric_names[0])
        
        return matched
    
    def _extract_years(self, query: str) -> List[int]:
        """
        Extract year mentions from query.
        
        Args:
            query: Query string
            
        Returns:
            List of years
        """
        years = []
        current_year = datetime.now().year
        
        # Pattern for 4-digit years
        year_pattern = r'\b(19\d{2}|20[0-2]\d|203\d)\b'
        matches = re.findall(year_pattern, query)
        
        for match in matches:
            year = int(match)
            if 1990 <= year <= current_year + 1:
                years.append(year)
        
        # Handle relative year references
        if re.search(r'\b(last year|previous year)\b', query.lower()):
            years.append(current_year - 1)
        
        if re.search(r'\b(this year|current year)\b', query.lower()):
            years.append(current_year)
        
        if re.search(r'\b(next year)\b', query.lower()):
            years.append(current_year + 1)
        
        return sorted(list(set(years)))
    
    def _extract_year_range(self, query: str) -> Optional[tuple]:
        """
        Extract year ranges from query.
        
        Args:
            query: Query string
            
        Returns:
            Tuple of (start_year, end_year) or None
        """
        # Pattern for "from YYYY to YYYY"
        range_pattern = r'\b(?:from|between)\s+(\d{4})\s+(?:to|-|and)\s+(\d{4})\b'
        match = re.search(range_pattern, query, re.IGNORECASE)
        
        if match:
            start_year = int(match.group(1))
            end_year = int(match.group(2))
            return (start_year, end_year)
        
        # Pattern for "YYYY-YYYY"
        dash_pattern = r'\b(\d{4})-(\d{4})\b'
        match = re.search(dash_pattern, query)
        
        if match:
            start_year = int(match.group(1))
            end_year = int(match.group(2))
            return (start_year, end_year)
        
        # If multiple years found, use as range
        years = self._extract_years(query)
        if len(years) >= 2:
            return (min(years), max(years))
        
        return None
    
    def _extract_comparison_terms(self, query_lower: str) -> List[str]:
        """
        Extract comparison and trend terms from query.
        
        Args:
            query_lower: Lowercase query string
            
        Returns:
            List of comparison terms found
        """
        found_terms = []
        
        for term in self.comparison_terms_set:
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, query_lower):
                found_terms.append(term)
        
        return found_terms
    
    def get_retrieval_params(self, entities: ExtractedEntities) -> Dict[str, Any]:
        """
        Convert extracted entities to retrieval parameters.
        
        Args:
            entities: ExtractedEntities object
            
        Returns:
            Dictionary with retrieval parameters
        """
        params = {
            "ticker": entities.ticker or "NVDA",
            "metrics": entities.metrics if entities.metrics else None,
            "year": entities.years[0] if len(entities.years) == 1 else None,
            "year_range": entities.year_range,
            "include_trends": len(entities.comparison_terms) > 0 or entities.year_range is not None
        }
        
        return params

# Global entity extractor instance
entity_extractor = EntityExtractor()